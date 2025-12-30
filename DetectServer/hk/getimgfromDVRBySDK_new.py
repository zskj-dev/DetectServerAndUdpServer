
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
海康威视摄像头SDK - 修复资源泄漏版本
解决运行一段时间后出现WinError 206的问题
"""

import os
import sys
import time
import ctypes
import atexit
import logging
import threading
import traceback
from ctypes import *
from pathlib import Path
from typing import Optional, Dict, Tuple, List, Set
from collections import defaultdict
from contextlib import contextmanager
import weakref

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('hikvision_sdk.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 资源监控
import psutil
process = psutil.Process()

class ResourceTracker:
    """资源跟踪器，监控句柄泄漏"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_tracker()
        return cls._instance
    
    def _init_tracker(self):
        self.active_handles = set()  # 活跃句柄ID
        self.handle_types = defaultdict(int)  # 句柄类型统计
        self.leak_detected = False
        self.max_handles = 1000  # 最大句柄数警告阈值
        self.start_time = time.time()
        self.last_check = self.start_time
        
        # 启动监控线程
        self.monitor_thread = threading.Thread(target=self._monitor_resources, daemon=True)
        self.monitor_thread.start()
        logger.info("资源监控器已启动")
    
    def register_handle(self, handle_id: int, handle_type: str):
        """注册新句柄"""
        if handle_id > 0:
            self.active_handles.add(handle_id)
            self.handle_types[handle_type] += 1
            logger.debug(f"注册句柄: {handle_type}[{handle_id}]，当前总数: {len(self.active_handles)}")
    
    def unregister_handle(self, handle_id: int, handle_type: str):
        """注销句柄"""
        if handle_id in self.active_handles:
            self.active_handles.remove(handle_id)
            self.handle_types[handle_type] -= 1
            if self.handle_types[handle_type] <= 0:
                del self.handle_types[handle_type]
            logger.debug(f"注销句柄: {handle_type}[{handle_id}]，剩余: {len(self.active_handles)}")
    
    def _monitor_resources(self):
        """监控资源使用情况"""
        while True:
            try:
                current_time = time.time()
                if current_time - self.last_check > 30:  # 每30秒检查一次
                    self._check_resource_leak()
                    self.last_check = current_time
                
                time.sleep(5)
            except Exception as e:
                logger.error(f"资源监控异常: {e}")
    
    def _check_resource_leak(self):
        """检查资源泄漏"""
        try:
            # 获取系统句柄数
            system_handles = process.num_handles()
            
            # 获取内存使用
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            
            runtime = time.time() - self.start_time
            runtime_str = time.strftime("%H:%M:%S", time.gmtime(runtime))
            
            logger.info(f"资源监控报告 - 运行时间: {runtime_str}")
            logger.info(f"系统句柄数: {system_handles}，跟踪句柄: {len(self.active_handles)}")
            logger.info(f"内存使用: {memory_mb:.2f} MB")
            logger.info(f"句柄类型分布: {dict(self.handle_types)}")
            
            # 泄漏检测
            if system_handles > self.max_handles:
                logger.warning(f"警告：系统句柄数({system_handles})超过阈值({self.max_handles})")
                self.leak_detected = True
            
            # 如果有大量未跟踪的句柄
            if system_handles - len(self.active_handles) > 500:
                logger.warning(f"警告：可能存在未跟踪的句柄泄漏")
                
        except Exception as e:
            logger.error(f"资源检查失败: {e}")
    
    def force_cleanup(self):
        """强制清理所有资源"""
        logger.warning("执行强制资源清理")
        leak_count = len(self.active_handles)
        if leak_count > 0:
            logger.warning(f"清理前存在 {leak_count} 个未释放句柄")
            self.active_handles.clear()
            self.handle_types.clear()

resource_tracker = ResourceTracker()

class HikvisionConstants:
    """海康SDK常量"""
    # 预置点命令
    SET_PRESET = 8
    CLE_PRESET = 9
    GOTO_PRESET = 39
    
    # 云台控制
    PTZ_UP = 21
    PTZ_DOWN = 22
    PTZ_LEFT = 23
    PTZ_RIGHT = 24
    
    # 错误码
    ERROR_FILE_OPEN_FAILED = 206  # 文件名或扩展名太长
    
    # 资源类型
    RESOURCE_DEVICE = "device"
    RESOURCE_PREVIEW = "preview"
    RESOURCE_PLAYBACK = "playback"
    RESOURCE_FILE = "file"

class HikvisionSDKManager:
    """
    SDK管理器 - 单例模式，确保SDK只初始化一次
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            with self._lock:
                if not self._initialized:
                    self.sdk_path = self._get_safe_sdk_path()
                    self.hcnetsdk = None
                    self.playctrllib = None
                    self.devices = {}  # device_key -> (user_id, login_time)
                    self.preview_handles = {}  # preview_key -> handle
                    self.playback_handles = {}  # playback_key -> handle
                    self.file_handles = set()  # 打开的文件句柄
                    
                    self._init_count = 0
                    self._cleanup_count = 0
                    
                    # 注册清理钩子
                    atexit.register(self._global_cleanup)
                    
                    self._initialized = True
                    logger.info("SDK管理器初始化完成")
    
    def _get_safe_sdk_path(self) -> str:
        """获取安全的SDK路径"""
        # 尝试多个可能的位置
        possible_paths = [
            os.environ.get('HIK_SDK_PATH', ''),
            r"C:\HikSDK",
            r"D:\HikSDK",
            os.path.join(os.path.dirname(__file__), "hk"),
            os.path.join(os.path.dirname(__file__), "sdk"),
        ]
        
        for path in possible_paths:
            if not path:
                continue
                
            hcnet_dll = os.path.join(path, "HCNetSDK.dll")
            if os.path.exists(hcnet_dll):
                # 检查路径长度
                if len(path) > 150:
                    logger.warning(f"SDK路径较长 ({len(path)}字符): {path}")
                    # 尝试获取短路径
                    try:
                        import win32api
                        short_path = win32api.GetShortPathName(path)
                        if os.path.exists(os.path.join(short_path, "HCNetSDK.dll")):
                            logger.info(f"使用短路径: {short_path}")
                            return short_path
                    except:
                        pass
                
                logger.info(f"使用SDK路径: {path}")
                return path
        
        raise FileNotFoundError("找不到海康SDK文件")
    
    def initialize(self) -> bool:
        """初始化SDK（线程安全）"""
        with self._lock:
            if self.hcnetsdk is not None:
                self._init_count += 1
                logger.debug(f"SDK已初始化，引用计数: {self._init_count}")
                return True
            
            try:
                # 加载DLL
                hcnet_dll_path = os.path.join(self.sdk_path, "HCNetSDK.dll")
                play_dll_path = os.path.join(self.sdk_path, "PlayCtrl.dll")
                
                if not os.path.exists(hcnet_dll_path):
                    logger.error(f"找不到HCNetSDK.dll: {hcnet_dll_path}")
                    return False
                
                # 设置DLL搜索路径
                os.environ['PATH'] = self.sdk_path + os.pathsep + os.environ['PATH']
                
                logger.info(f"加载SDK库: {hcnet_dll_path}")
                self.hcnetsdk = CDLL(hcnet_dll_path)
                
                if os.path.exists(play_dll_path):
                    self.playctrllib = CDLL(play_dll_path)
                    logger.info(f"加载播放库: {play_dll_path}")
                
                # 初始化SDK
                init_result = self.hcnetsdk.NET_DVR_Init()
                if not init_result:
                    error_code = self.hcnetsdk.NET_DVR_GetLastError()
                    logger.error(f"SDK初始化失败，错误码: {error_code}")
                    self.hcnetsdk = None
                    self.playctrllib = None
                    return False
                
                # 设置连接参数
                self.hcnetsdk.NET_DVR_SetConnectTime(2000, 1)
                self.hcnetsdk.NET_DVR_SetReconnect(10000, True)
                
                # 设置日志（避免SDK内部日志文件泄漏）
                self._setup_sdk_logging()
                
                self._init_count = 1
                logger.info("海康SDK初始化成功")
                return True
                
            except Exception as e:
                logger.error(f"SDK初始化异常: {e}")
                logger.error(traceback.format_exc())
                self.hcnetsdk = None
                self.playctrllib = None
                return False
    
    def _setup_sdk_logging(self):
        """配置SDK日志，避免日志文件泄漏"""
        try:
            # 创建日志目录
            log_dir = r"C:\HikLogs"
            os.makedirs(log_dir, exist_ok=True)
            
            # 设置SDK日志参数
            # 注意：具体函数名称可能因SDK版本而异
            log_level = 3  # 普通日志级别
            log_to_file = True
            
            # 尝试设置日志
            try:
                # NET_DVR_SetLogToFile 函数（可能不存在于所有版本）
                set_log_func = getattr(self.hcnetsdk, 'NET_DVR_SetLogToFile', None)
                if set_log_func:
                    set_log_func(log_level, log_dir.encode('gbk'), log_to_file)
                    logger.info(f"SDK日志已设置到: {log_dir}")
            except:
                pass
                
        except Exception as e:
            logger.warning(f"设置SDK日志失败: {e}")
    
    def login_device(self, ip: str, port: int, username: str, password: str) -> int:
        """登录设备"""
        if not self.initialize():
            return -1
        
        device_key = f"{ip}:{port}"
        
        # 检查是否已登录
        if device_key in self.devices:
            user_id, login_time = self.devices[device_key]
            logger.debug(f"设备 {device_key} 已登录 (登录于 {login_time})")
            return user_id
        
        # 设备信息结构体
        class NET_DVR_DEVICEINFO_V30(Structure):
            _fields_ = [
                ("sSerialNumber", c_char * 48),
                ("byAlarmInPortNum", c_byte),
                ("byAlarmOutPortNum", c_byte),
                ("byDiskNum", c_byte),
                ("byDVRType", c_byte),
                ("byChanNum", c_byte),
                ("byStartChan", c_byte),
                ("byAudioChanNum", c_byte),
                ("byIPChanNum", c_byte),
                ("byZeroChanNum", c_byte),
                ("byMainProto", c_byte),
                ("bySubProto", c_byte),
                ("bySupport", c_byte),
                ("bySupport1", c_byte),
                ("bySupport2", c_byte),
                ("wDevType", c_ushort),
                ("bySupport3", c_byte),
                ("byMultiStreamProto", c_byte),
                ("byStartDChan", c_byte),
                ("byStartDTalkChan", c_byte),
                ("byHighDChanNum", c_byte),
                ("bySupport4", c_byte),
                ("byLanguageType", c_byte),
                ("byVoiceInChanNum", c_byte),
                ("byStartVoiceInChanNo", c_byte),
                ("byRes1", c_byte * 2),
            ]
        
        device_info = NET_DVR_DEVICEINFO_V30()
        
        # 登录设备
        user_id = self.hcnetsdk.NET_DVR_Login_V30(
            ip.encode('gbk'),
            c_ushort(port),
            username.encode('gbk'),
            password.encode('gbk'),
            byref(device_info)
        )
        
        if user_id < 0:
            error_code = self.hcnetsdk.NET_DVR_GetLastError()
            logger.error(f"设备登录失败 {device_key}，错误码: {error_code}")
            return -1
        
        # 记录登录
        self.devices[device_key] = (user_id, time.strftime("%Y-%m-%d %H:%M:%S"))
        resource_tracker.register_handle(user_id, HikvisionConstants.RESOURCE_DEVICE)
        
        logger.info(f"设备登录成功 {device_key}，用户ID: {user_id}")
        return user_id
    
    def logout_device(self, ip: str, port: int) -> bool:
        """登出设备"""
        device_key = f"{ip}:{port}"
        
        if device_key not in self.devices:
            logger.warning(f"设备 {device_key} 未登录")
            return True
        
        user_id, login_time = self.devices[device_key]
        
        try:
            # 先停止该设备的所有预览
            self._stop_device_previews(user_id)
            
            # 登出设备
            logout_result = self.hcnetsdk.NET_DVR_Logout(user_id)
            
            if logout_result:
                del self.devices[device_key]
                resource_tracker.unregister_handle(user_id, HikvisionConstants.RESOURCE_DEVICE)
                logger.info(f"设备登出成功 {device_key}，用户ID: {user_id}")
                return True
            else:
                error_code = self.hcnetsdk.NET_DVR_GetLastError()
                logger.error(f"设备登出失败 {device_key}，错误码: {error_code}")
                return False
                
        except Exception as e:
            logger.error(f"设备登出异常 {device_key}: {e}")
            return False
    
    def _stop_device_previews(self, user_id: int):
        """停止设备的所有预览"""
        previews_to_stop = []
        for preview_key, (preview_user_id, handle) in self.preview_handles.items():
            if preview_user_id == user_id:
                previews_to_stop.append((preview_key, handle))
        
        for preview_key, handle in previews_to_stop:
            try:
                self.hcnetsdk.NET_DVR_StopRealPlay(handle)
                del self.preview_handles[preview_key]
                resource_tracker.unregister_handle(handle, HikvisionConstants.RESOURCE_PREVIEW)
                logger.debug(f"停止预览 {preview_key}")
            except Exception as e:
                logger.error(f"停止预览异常 {preview_key}: {e}")
    
    def capture_jpeg(self, user_id: int, channel: int, output_file: str) -> bool:
        """抓取JPEG图片"""
        # 检查文件路径长度
        if len(output_file) > 200:
            logger.warning(f"文件路径过长 ({len(output_file)}字符)，自动缩短")
            output_file = self._get_short_filepath(output_file)
        
        # 确保目录存在
        output_dir = os.path.dirname(output_file)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        
        # 抓图参数
        class NET_DVR_JPEGPARA(Structure):
            _fields_ = [
                ("wPicQuality", c_ushort),
                ("wPicSize", c_ushort)
            ]
        
        jpeg_para = NET_DVR_JPEGPARA()
        jpeg_para.wPicQuality = 0  # 最好质量
        jpeg_para.wPicSize = 2     # 640x480
        
        # 抓图
        result = self.hcnetsdk.NET_DVR_CaptureJPEGPicture(
            user_id,
            channel,
            byref(jpeg_para),
            output_file.encode('gbk')
        )
        
        if result:
            logger.info(f"抓图成功: {output_file}")
            # 注册文件句柄跟踪
            resource_tracker.register_handle(hash(output_file), HikvisionConstants.RESOURCE_FILE)
            return True
        else:
            error_code = self.hcnetsdk.NET_DVR_GetLastError()
            logger.error(f"抓图失败，错误码: {error_code}")
            
            # 如果是206错误，可能是文件句柄耗尽
            if error_code == HikvisionConstants.ERROR_FILE_OPEN_FAILED:
                logger.error("WinError 206: 文件名或扩展名太长，可能是文件句柄耗尽")
                self._handle_file_handle_exhaustion()
            
            return False
    
    def _get_short_filepath(self, long_path: str) -> str:
        """获取短文件路径"""
        try:
            import win32api
            short_path = win32api.GetShortPathName(long_path)
            return short_path
        except:
            # 使用临时目录
            import uuid
            temp_dir = r"C:\HikTemp"
            os.makedirs(temp_dir, exist_ok=True)
            
            unique_name = f"{uuid.uuid4().hex[:8]}.jpg"
            return os.path.join(temp_dir, unique_name)
    
    def _handle_file_handle_exhaustion(self):
        """处理文件句柄耗尽的情况"""
        logger.warning("检测到可能的文件句柄耗尽，尝试清理")
        
        # 强制垃圾回收
        import gc
        gc.collect()
        
        # 检查系统句柄数
        try:
            handles = process.num_handles()
            logger.warning(f"当前系统句柄数: {handles}")
            
            if handles > 800:
                logger.warning("系统句柄数过高，建议重启程序")
                
                # 尝试清理资源
                self._emergency_cleanup()
        except:
            pass
    
    def _emergency_cleanup(self):
        """紧急清理资源"""
        logger.warning("执行紧急资源清理")
        
        # 清理文件句柄
        for file_hash in list(resource_tracker.active_handles):
            resource_tracker.unregister_handle(file_hash, HikvisionConstants.RESOURCE_FILE)
        
        # 强制清理SDK内部资源
        if self.hcnetsdk:
            try:
                # 尝试多次清理
                for i in range(3):
                    cleanup_result = self.hcnetsdk.NET_DVR_Cleanup()
                    if cleanup_result:
                        logger.info(f"紧急清理成功 (尝试{i+1})")
                        break
                    else:
                        time.sleep(0.1)
            except:
                pass
    
    def ptz_preset(self, user_id: int, channel: int, command: int, preset_id: int) -> Tuple[int, str]:
        """预置点操作"""
        result = self.hcnetsdk.NET_DVR_PTZPreset_Other(
            user_id,
            channel,
            command,
            preset_id
        )
        
        if result:
            return 0, "操作成功"
        else:
            error_code = self.hcnetsdk.NET_DVR_GetLastError()
            return 4, f"操作失败，错误码: {error_code}"
    
    def ptz_control(self, user_id: int, channel: int, command: int, switch: int, speed: int) -> bool:
        """云台控制"""
        result = self.hcnetsdk.NET_DVR_PTZControlWithSpeed_Other(
            user_id,
            channel,
            command,
            switch,
            speed
        )
        
        if not result:
            error_code = self.hcnetsdk.NET_DVR_GetLastError()
            logger.error(f"云台控制失败，错误码: {error_code}")
        
        return result
    
    def _global_cleanup(self):
        """全局清理所有资源"""
        logger.info("执行全局SDK资源清理...")
        
        # 1. 登出所有设备
        devices_to_logout = list(self.devices.keys())
        for device_key in devices_to_logout:
            try:
                ip_port = device_key.split(":")
                if len(ip_port) == 2:
                    ip, port_str = ip_port
                    port = int(port_str)
                    self.logout_device(ip, port)
            except Exception as e:
                logger.error(f"登出设备 {device_key} 失败: {e}")
        
        # 2. 停止所有预览和回放
        self.preview_handles.clear()
        self.playback_handles.clear()
        
        # 3. 清理SDK
        if self.hcnetsdk:
            try:
                # 先释放播放库资源
                if self.playctrllib:
                    try:
                        # 停止音频
                        stop_sound = getattr(self.playctrllib, 'PlayM4_StopSound', None)
                        if stop_sound:
                            stop_sound()
                    except:
                        pass
                
                # 清理SDK
                cleanup_result = self.hcnetsdk.NET_DVR_Cleanup()
                if cleanup_result:
                    self._cleanup_count += 1
                    logger.info(f"SDK清理成功 (总清理次数: {self._cleanup_count})")
                else:
                    error_code = self.hcnetsdk.NET_DVR_GetLastError()
                    logger.warning(f"SDK清理失败，错误码: {error_code}")
                    
                    # 尝试强制清理
                    for i in range(3):
                        try:
                            cleanup_result = self.hcnetsdk.NET_DVR_Cleanup()
                            if cleanup_result:
                                logger.info(f"强制清理成功 (尝试{i+1})")
                                break
                        except:
                            pass
                
            except Exception as e:
                logger.error(f"SDK清理异常: {e}")
            
            finally:
                # 释放DLL引用
                self.hcnetsdk = None
                self.playctrllib = None
        
        # 4. 清理文件句柄
        self.file_handles.clear()
        
        # 5. 强制资源跟踪器清理
        resource_tracker.force_cleanup()
        
        logger.info("全局资源清理完成")
    
    def __del__(self):
        """析构函数，确保资源释放"""
        try:
            if self._initialized:
                self._global_cleanup()
        except:
            pass

class HikvisionSession:
    """
    海康会话管理器 - 使用上下文管理器确保资源释放
    """
    
    def __init__(self, ip: str, port: int, username: str, password: str):
        self.ip = ip
        self.port = port
        self.username = username
        self.password = password
        self.sdk_manager = HikvisionSDKManager()
        self.user_id = -1
        self._logged_in = False
    
    def __enter__(self):
        """进入上下文"""
        self.user_id = self.sdk_manager.login_device(
            self.ip, self.port, self.username, self.password
        )
        self._logged_in = self.user_id >= 0
        return self
    
    def capture(self, channel: int, output_file: str) -> bool:
        """抓图"""
        if not self._logged_in:
            logger.error("设备未登录")
            return False
        return self.sdk_manager.capture_jpeg(self.user_id, channel, output_file)
    
    def ptz_preset(self, channel: int, command: int, preset_id: int) -> Tuple[int, str]:
        """预置点操作"""
        if not self._logged_in:
            return 3, "设备未登录"
        return self.sdk_manager.ptz_preset(self.user_id, channel, command, preset_id)
    
    def ptz_control(self, channel: int, command: int, switch: int = 0, speed: int = 3) -> bool:
        """云台控制"""
        if not self._logged_in:
            logger.error("设备未登录")
            return False
        return self.sdk_manager.ptz_control(self.user_id, channel, command, switch, speed)
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文，确保资源释放"""
        if self._logged_in:
            self.sdk_manager.logout_device(self.ip, self.port)
            self._logged_in = False
        
        if exc_type:
            logger.error(f"会话异常: {exc_val}")
            logger.error(traceback.format_exception(exc_type, exc_val, exc_tb))
        
        return False  # 不捕获异常

# 高层API函数（保持向后兼容）
def capture_camera_image_at_preset(ip: str, port: int, username: str, password: str,
                                   channel: int, preset_id: int, output_file: str,
                                   wait_seconds: int = 3) -> bool:
    """在指定预置点抓图"""
    with HikvisionSession(ip, port, username, password) as session:
        if not session._logged_in:
            return False
        
        # 转动到预置点
        if preset_id != 0:
            code, msg = session.ptz_preset(channel, HikvisionConstants.GOTO_PRESET, preset_id)
            if code != 0:
                logger.error(f"转动到预置点失败: {msg}")
                return False
            
            # 等待
            time.sleep(wait_seconds)
        
        # 抓图
        return session.capture(channel, output_file)

def camera_control_move(ip: str, port: int, username: str, password: str,
                        channel: int, command: int, switch: int = 0,
                        speed: int = 3) -> bool:
    """云台控制"""
    with HikvisionSession(ip, port, username, password) as session:
        if not session._logged_in:
            return False
        return session.ptz_control(channel, command, switch, speed)

def camera_control_preset(ip: str, port: int, username: str, password: str,
                          channel: int, command: int, preset_id: int) -> Tuple[int, str]:
    """预置点控制"""
    with HikvisionSession(ip, port, username, password) as session:
        if not session._logged_in:
            return 2, "登录设备失败"
        return session.ptz_preset(channel, command, preset_id)

# 定期清理函数
def periodic_cleanup():
    """定期清理函数，可以定时调用"""
    logger.info("执行定期资源清理")
    sdk_manager = HikvisionSDKManager()
    
    # 清理超过1小时的会话
    current_time = time.time()
    for device_key, (user_id, login_time_str) in list(sdk_manager.devices.items()):
        try:
            # 解析登录时间
            login_time = time.mktime(time.strptime(login_time_str, "%Y-%m-%d %H:%M:%S"))
            if current_time - login_time > 3600:  # 1小时
                logger.info(f"清理超时会话: {device_key}")
                ip_port = device_key.split(":")
                if len(ip_port) == 2:
                    sdk_manager.logout_device(ip_port[0], int(ip_port[1]))
        except:
            pass
    
    # 强制垃圾回收
    import gc
    gc.collect()
    
    logger.info("定期清理完成")

# 测试函数
def test_resource_leak():
    """测试资源泄漏"""
    import random
    
    test_cases = [
        ("192.168.20.30", 9001, "admin", "zskj1225", 35, 1, "test_capture.jpg"),
        # 可以添加更多测试用例
    ]
    
    for i in range(100):  # 测试100次，模拟长时间运行
        logger.info(f"测试迭代 {i+1}/100")
        
        for ip, port, username, password, channel, preset_id, output_file in test_cases:
            # 每次使用不同的文件名
            unique_file = f"test_{i}_{random.randint(1000, 9999)}.jpg"
            
            success = capture_camera_image_at_preset(
                ip, port, username, password,
                channel, preset_id, unique_file,
                wait_seconds=1
            )
            
            if not success:
                logger.error(f"第{i+1}次测试失败")
                break
        
        # 每10次执行一次定期清理
        if (i + 1) % 10 == 0:
            periodic_cleanup()
        
        time.sleep(0.5)
    
    logger.info("资源泄漏测试完成")

if __name__ == "__main__":
    # 简单测试
    DEVICE_IP = "192.168.20.30"
    DEVICE_PORT = 9001
    USERNAME = "admin"
    PASSWORD = "zskj1225"
    CHANNEL = 35
    
    print("海康SDK资源泄漏修复测试")
    print("=" * 50)
    
    # 测试1: 简单抓图
    print("\n测试1: 简单抓图")
    success = capture_camera_image_at_preset(
        DEVICE_IP, DEVICE_PORT, USERNAME, PASSWORD,
        CHANNEL, 1, "test_capture_1.jpg", 3
    )
    print(f"抓图结果: {'成功' if success else '失败'}")
    
    # 测试2: 云台控制
    print("\n测试2: 云台控制")
    success = camera_control_move(
        DEVICE_IP, DEVICE_PORT, USERNAME, PASSWORD,
        CHANNEL, HikvisionConstants.PTZ_DOWN, 0, 2
    )
    time.sleep(1)
    success = camera_control_move(
        DEVICE_IP, DEVICE_PORT, USERNAME, PASSWORD,
        CHANNEL, HikvisionConstants.PTZ_DOWN, 1, 2
    )
    print(f"云台控制结果: {'成功' if success else '失败'}")
    
    # 显示资源状态
    print("\n资源状态:")
    print(f"当前进程句柄数: {process.num_handles()}")
    print(f"当前进程内存: {process.memory_info().rss / 1024 / 1024:.2f} MB")
    
    # 执行资源泄漏测试（取消注释以运行）
    # print("\n开始资源泄漏测试...")
    # test_resource_leak()
    
    print("\n测试完成")