import cv2  # 需要安装：pip install opencv-python
import numpy as np
from PIL import Image  # 需要安装：pip install Pillow
import os
import os
import ctypes
from ctypes import *
import datetime # 创建抓取图像的时间戳


import sys
import time
import ctypes
import atexit
import logging
import threading
import traceback
from ctypes import *
from typing import Tuple, Optional
import weakref
import subprocess

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('hikvision_sdk.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ==================== 全局SDK管理器（单例）====================

class _HikvisionSDKManager:
    """海康SDK全局管理器 - 单例模式"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = False
            self._initialize_manager()
    
    def _initialize_manager(self):
        """初始化管理器"""
        with self._lock:
            self.hcnetsdk = None
            self.playctrllib = None
            self._sdk_path = None
            self._init_count = 0
            self._active_sessions = weakref.WeakSet()  # 弱引用跟踪活动会话
            
            # 注册退出清理
            atexit.register(self._global_cleanup)
            
            self._initialized = True
            logger.info("海康SDK管理器初始化完成")
    
    def get_sdk_path(self, user_sdk_path: str) -> str:
        """获取安全的SDK路径"""
        if self._sdk_path:
            return self._sdk_path
        
        # 检查用户提供的路径
        if user_sdk_path and os.path.exists(os.path.join(user_sdk_path, "HCNetSDK.dll")):
            self._sdk_path = user_sdk_path
        else:
            # 尝试常见路径
            possible_paths = [
                os.environ.get('HIK_SDK_PATH', ''),
                r"C:\HikSDK",
                r"D:\HikSDK",
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "hk"),
                os.path.dirname(os.path.abspath(__file__)),
            ]
            
            for path in possible_paths:
                if path and os.path.exists(os.path.join(path, "HCNetSDK.dll")):
                    self._sdk_path = path
                    break
        
        if not self._sdk_path:
            raise FileNotFoundError("找不到海康SDK文件")
        
        logger.info(f"使用SDK路径: {self._sdk_path}")
        return self._sdk_path
    
    def initialize_sdk(self) -> bool:
        """初始化SDK（线程安全）"""
        with self._lock:
            if self.hcnetsdk is not None:
                self._init_count += 1
                logger.debug(f"SDK已初始化，引用计数: {self._init_count}")
                return True
            
            try:
                sdk_path = self._sdk_path or self.get_sdk_path("")
                hcnet_dll = os.path.join(sdk_path, "HCNetSDK.dll")
                play_dll = os.path.join(sdk_path, "PlayCtrl.dll")
                
                if not os.path.exists(hcnet_dll):
                    logger.error(f"找不到HCNetSDK.dll: {hcnet_dll}")
                    return False
                
                # 添加DLL搜索路径
                if hasattr(os, 'add_dll_directory'):
                    os.add_dll_directory(sdk_path)
                
                # 设置环境变量
                os.environ['PATH'] = sdk_path + os.pathsep + os.environ['PATH']
                
                # 加载DLL
                logger.info(f"加载SDK: {hcnet_dll}")
                self.hcnetsdk = CDLL(hcnet_dll)
                
                if os.path.exists(play_dll):
                    self.playctrllib = CDLL(play_dll)
                    logger.info(f"加载播放库: {play_dll}")
                
                # 初始化SDK
                if not self.hcnetsdk.NET_DVR_Init():
                    error_code = self.hcnetsdk.NET_DVR_GetLastError()
                    logger.error(f"SDK初始化失败，错误码: {error_code}")
                    self.hcnetsdk = None
                    self.playctrllib = None
                    return False
                
                # 设置连接参数
                self.hcnetsdk.NET_DVR_SetConnectTime(2000, 1)
                self.hcnetsdk.NET_DVR_SetReconnect(10000, True)
                
                # 禁用SDK内部日志（避免文件泄漏）
                self._disable_sdk_logging()
                
                self._init_count = 1
                logger.info("海康SDK初始化成功")
                return True
                
            except Exception as e:
                logger.error(f"SDK初始化异常: {e}")
                logger.error(traceback.format_exc())
                self.hcnetsdk = None
                self.playctrllib = None
                return False
    
    def _disable_sdk_logging(self):
        """禁用SDK内部日志"""
        try:
            # 尝试设置日志级别为0（不记录）
            # 不同版本SDK函数名可能不同
            set_log_func = getattr(self.hcnetsdk, 'NET_DVR_SetLogToFile', None)
            if set_log_func:
                # 参数: 日志级别, 日志路径, 是否记录到文件
                set_log_func(0, None, False)
                logger.info("SDK内部日志已禁用")
        except:
            pass
    
    def register_session(self, session):
        """注册会话"""
        with self._lock:
            self._active_sessions.add(session)
            logger.debug(f"注册会话，当前活动会话数: {len(self._active_sessions)}")
    
    def unregister_session(self, session):
        """注销会话"""
        with self._lock:
            if session in self._active_sessions:
                self._active_sessions.remove(session)
                logger.debug(f"注销会话，剩余活动会话数: {len(self._active_sessions)}")
    
    def _global_cleanup(self):
        """全局清理"""
        logger.info("执行全局SDK资源清理...")
        
        try:
            # 清理所有活动会话
            sessions_to_clean = list(self._active_sessions)
            for session in sessions_to_clean:
                try:
                    session._force_logout()
                except:
                    pass
            
            # 清理SDK
            if self.hcnetsdk:
                try:
                    # 清理SDK资源
                    cleanup_result = self.hcnetsdk.NET_DVR_Cleanup()
                    if cleanup_result:
                        logger.info(f"SDK清理成功")
                    else:
                        error_code = self.hcnetsdk.NET_DVR_GetLastError()
                        logger.warning(f"SDK清理失败，错误码: {error_code}")
                except Exception as e:
                    logger.error(f"SDK清理异常: {e}")
                finally:
                    self.hcnetsdk = None
                    self.playctrllib = None
            
        except Exception as e:
            logger.error(f"全局清理异常: {e}")
        
        finally:
            self._initialized = False
            logger.info("全局资源清理完成")

# 全局管理器实例
_global_manager = _HikvisionSDKManager()


# ==================== 保持原有接口的类 ====================
SDK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)))#, "hk"
class HikvisionCapture:
    def __init__(self, sdk_path):
        """初始化SDK环境"""
        self.sdk_path = sdk_path
        self.user_id = -1
        self.device_info = None
        self.hcnetsdk = None
        self.playctrllib = None
        self.current_preset = None  # 记录当前预置点

        # 新增：会话管理
        self._session_id = None
        self._sdk_initialized = False
        self._logged_in = False

        logger.info(f"HikvisionCapture初始化，SDK路径: {sdk_path}")

        # 注册到全局管理器
        _global_manager.register_session(self)

    def initialize(self):
        """加载SDK库并初始化"""
        try:
            # 使用全局管理器初始化SDK
            if not _global_manager.initialize_sdk():
                error_msg = "SDK初始化失败"
                logger.error(error_msg)
                raise Exception(error_msg)
            
            self.hcnetsdk = _global_manager.hcnetsdk
            self.playctrllib = _global_manager.playctrllib
            self._sdk_initialized = True
            
            return True

        except Exception as e:
            print(f"SDK初始化异常: {e}")
            return False

    def login(self, ip, port, username, password):
        """登录设备"""
        if not self._sdk_initialized:
            if not self.initialize():
                return False

        # 设备结构体定义
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

        self.device_info = NET_DVR_DEVICEINFO_V30()

        # 登录设备 - 使用GBK编码
        self.user_id = self.hcnetsdk.NET_DVR_Login_V30(
            ip.encode('gbk'),
            c_ushort(port),
            username.encode('gbk'),
            password.encode('gbk'),
            byref(self.device_info)
        )

        if self.user_id < 0:
            error_code = self.hcnetsdk.NET_DVR_GetLastError()
            error_msg = self._get_error_message(error_code)
            logger.error(f"登录失败，错误码: {error_code} - {error_msg}")
            return False

        self._logged_in = True
        print(f"登录成功，用户ID: {self.user_id}")
        return True

    def _get_error_message(self, error_code: int) -> str:
        """获取错误码对应的描述"""
        error_messages = {
            206: "文件名或扩展名太长 (WinError 206)",
            1: "用户名或密码错误",
            2: "权限不足",
            3: "SDK未初始化",
            4: "通道错误",
            5: "连接超时",
            6: "连接被拒绝",
            7: "设备不在线",
            8: "网络错误",
            9: "内存不足",
            10: "设备繁忙",
        }
        return error_messages.get(error_code, f"未知错误: {error_code}")

    def _get_safe_filepath(self, output_file: str) -> str:
        """获取安全的文件路径"""
        # 检查路径长度
        if len(output_file) > 200:
            logger.warning(f"文件路径过长 ({len(output_file)}字符): {output_file}")
            
            # 使用短路径
            try:
                import win32api
                short_path = win32api.GetShortPathName(output_file)
                if len(short_path) <= 200:
                    logger.info(f"使用短路径名: {short_path}")
                    return short_path
            except:
                pass
            
            # 使用临时目录
            import tempfile
            temp_dir = tempfile.gettempdir()
            import uuid
            safe_name = f"hik_{uuid.uuid4().hex[:8]}.jpg"
            safe_path = os.path.join(temp_dir, safe_name)
            
            logger.info(f"使用临时文件: {safe_path}")
            return safe_path
        
        # 确保目录存在
        output_dir = os.path.dirname(output_file)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        
        return output_file

    def capture(self, channel, output_file):
        """抓取指定通道的图像（增强版：支持预览和获取尺寸）"""
        if self._logged_in < 0:
            print("请先登录设备")
            return False

        # 使用安全的文件路径
        safe_output_file = self._get_safe_filepath(output_file)

        # 抓图参数结构体
        class NET_DVR_JPEGPARA(Structure):
            _fields_ = [
                ("wPicQuality", c_ushort),  # 图片质量: 0-最好，1-较好，2-一般
                ("wPicSize", c_ushort)  # 图片尺寸: 0-160x120, 1-320x240, 2-640x480, 3-800x600等
            ]

        jpeg_para = NET_DVR_JPEGPARA()
        jpeg_para.wPicQuality = 0  # 最好质量
        jpeg_para.wPicSize = 2  # 640x480

        # 调用SDK抓图函数 - 使用GBK编码
        result = self.hcnetsdk.NET_DVR_CaptureJPEGPicture(
            self.user_id,
            channel,
            byref(jpeg_para),
            safe_output_file.encode('gbk')
        )

        if result:
            logger.info(f"抓图成功，保存至: {safe_output_file}")
            
            # 如果使用了临时文件，复制到目标位置
            final_file = output_file
            if safe_output_file != output_file:
                try:
                    import shutil
                    shutil.copy2(safe_output_file, output_file)
                    logger.info(f"文件已复制到目标位置: {output_file}")
                    final_file = output_file
                except Exception as e:
                    logger.error(f"复制文件失败: {e}")
                    final_file = safe_output_file  # 使用临时文件
            
            # ========== 新增功能1：获取图片尺寸 ==========
            try:
                img_size = self._get_image_size(final_file)
                logger.info(f"图片尺寸: {img_size[0]}x{img_size[1]}")
            except Exception as e:
                logger.error(f"获取图片尺寸失败: {e}")
            
            # ========== 新增功能2：图像预览（可选） ==========
            preview_option = os.environ.get('HIK_PREVIEW', '0')  # 0:不预览, 1:预览
            if preview_option == '1':
                try:
                    self._preview_image(final_file)
                except Exception as e:
                    logger.error(f"图像预览失败: {e}")
            
            # 清理临时文件
            if safe_output_file != output_file and safe_output_file != final_file:
                try:
                    os.remove(safe_output_file)
                except:
                    pass
            
            return True
        else:
            error_code = self.hcnetsdk.NET_DVR_GetLastError()
            error_msg = self._get_error_message(error_code)
            logger.error(f"抓图失败，错误码: {error_code} - {error_msg}")
            
            if error_code == 206:
                logger.error("WinError 206: 文件名或扩展名太长")
                logger.error(f"尝试的路径: {safe_output_file}")
                logger.error(f"路径长度: {len(safe_output_file)} 字符")
            
            return False
    
    def _get_image_size(self, image_path):
        """
        获取图片尺寸
        
        参数:
            image_path: 图片文件路径
            
        返回:
            tuple: (宽度, 高度)
        """
        try:
            # 方法1: 使用PIL（推荐）
            try:
                from PIL import Image
                with Image.open(image_path) as img:
                    width, height = img.size
                    return width, height
            except:
                pass
            
            # 方法2: 使用OpenCV
            try:
                import cv2
                img = cv2.imread(image_path)
                if img is not None:
                    height, width = img.shape[:2]
                    return width, height
            except:
                pass
            
            # 方法3: 使用struct读取文件头（JPEG格式）
            try:
                with open(image_path, 'rb') as f:
                    f.seek(0)
                    data = f.read(11)
                    
                    # 检查JPEG文件头
                    if data[:3] == b'\xff\xd8\xff':
                        # JPEG文件
                        f.seek(0)
                        while True:
                            marker, = struct.unpack('>H', f.read(2))
                            if marker == 0xFFC0 or marker == 0xFFC1 or marker == 0xFFC2:
                                # SOF标记
                                f.read(3)  # 长度
                                bits = struct.unpack('B', f.read(1))[0]
                                height = struct.unpack('>H', f.read(2))[0]
                                width = struct.unpack('>H', f.read(2))[0]
                                return width, height
                            else:
                                # 跳过其他段
                                length = struct.unpack('>H', f.read(2))[0]
                                f.seek(length - 2, 1)
            except:
                pass
            
            logger.warning("无法获取图片尺寸")
            return (0, 0)
            
        except Exception as e:
            logger.error(f"获取图片尺寸异常: {e}")
            return (0, 0)
    
    def _preview_image(self, image_path, window_title="图像预览", max_width=800, max_height=600):
        """
        预览图像
        
        参数:
            image_path: 图片文件路径
            window_title: 窗口标题
            max_width: 最大显示宽度
            max_height: 最大显示高度
        """
        try:
            import cv2
            import numpy as np
            
            # 读取图像
            img = cv2.imread(image_path)
            if img is None:
                logger.error("无法读取图像文件")
                return False
            
            # 获取原始尺寸
            height, width = img.shape[:2]
            logger.info(f"原始图像尺寸: {width}x{height}")
            
            # 计算缩放比例
            scale = min(max_width / width, max_height / height)
            if scale < 1:  # 需要缩小
                new_width = int(width * scale)
                new_height = int(height * scale)
                img = cv2.resize(img, (new_width, new_height))
                logger.info(f"缩放后尺寸: {new_width}x{new_height}")
            
            # 显示图像
            cv2.imshow(window_title, img)
            
            # 添加文字信息
            info_text = f"Size: {width}x{height}"
            cv2.putText(img, info_text, (10, 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            # 显示带信息的图像
            cv2.imshow(window_title, img)
            
            # 等待按键（0表示无限等待，5000表示5秒后自动关闭）
            wait_time = int(os.environ.get('HIK_PREVIEW_TIME', '5000'))
            key = cv2.waitKey(wait_time) & 0xFF
            
            # 如果按了's'键，保存调整后的图像
            if key == ord('s'):
                save_path = image_path.replace('.jpg', '_preview.jpg')
                cv2.imwrite(save_path, img)
                logger.info(f"预览图已保存: {save_path}")
            
            # 关闭窗口
            cv2.destroyAllWindows()
            
            return True
            
        except Exception as e:
            logger.error(f"图像预览异常: {e}")
            return False
    
    # ========== 新增功能3：实时视频预览（使用海康SDK） ==========
    def start_realplay_preview(self, channel, hwnd=None, preview_type=0):
        """
        开始实时视频预览
        
        参数:
            channel: 通道号
            hwnd: 窗口句柄（None则创建新窗口）
            preview_type: 预览类型 0-主码流 1-子码流
            
        返回:
            int: 预览句柄，失败返回-1
        """
        if not self._logged_in:
            logger.error("请先登录设备")
            return -1
        
        try:
            # 实时预览参数结构体
            class NET_DVR_CLIENTINFO(Structure):
                _fields_ = [
                    ("lChannel", c_long),
                    ("hPlayWnd", c_void_p),
                    ("lLinkMode", c_long),
                    ("sMultiCastIP", c_char * 16),
                ]
            
            # 创建预览参数
            client_info = NET_DVR_CLIENTINFO()
            client_info.lChannel = channel
            client_info.hPlayWnd = hwnd if hwnd else 0
            client_info.lLinkMode = preview_type  # 0-TCP, 1-UDP, 2-多播
            
            # 开始实时预览
            preview_handle = self.hcnetsdk.NET_DVR_RealPlay_V40(
                self.user_id,
                byref(client_info),
                None,  # 回调函数
                None,  # 用户数据
                True   # 直接播放
            )
            
            if preview_handle < 0:
                error_code = self.hcnetsdk.NET_DVR_GetLastError()
                error_msg = self._get_error_message(error_code)
                logger.error(f"开始实时预览失败，错误码: {error_code} - {error_msg}")
                return -1
            
            logger.info(f"实时预览开始成功，句柄: {preview_handle}")
            return preview_handle
            
        except Exception as e:
            logger.error(f"开始实时预览异常: {e}")
            return -1
    
    def stop_realplay_preview(self, preview_handle):
        """
        停止实时视频预览
        
        参数:
            preview_handle: 预览句柄
        """
        try:
            if preview_handle >= 0:
                result = self.hcnetsdk.NET_DVR_StopRealPlay(preview_handle)
                if result:
                    logger.info(f"停止实时预览成功，句柄: {preview_handle}")
                else:
                    error_code = self.hcnetsdk.NET_DVR_GetLastError()
                    logger.error(f"停止实时预览失败，错误码: {error_code}")
        except Exception as e:
            logger.error(f"停止实时预览异常: {e}")
    
    # ========== 新增功能4：从预览中抓图 ==========
    def capture_from_preview(self, preview_handle, output_file, quality=100):
        """
        从实时预览中抓图
        
        参数:
            preview_handle: 预览句柄
            output_file: 输出文件路径
            quality: JPEG质量 (1-100)
            
        返回:
            bool: 是否成功
        """
        if preview_handle < 0:
            logger.error("预览句柄无效")
            return False
        
        try:
            # 抓图参数
            class NET_DVR_JPEGPARA(Structure):
                _fields_ = [
                    ("wPicQuality", c_ushort),
                    ("wPicSize", c_ushort)
                ]
            
            jpeg_para = NET_DVR_JPEGPARA()
            jpeg_para.wPicQuality = min(max(quality, 1), 100)  # 限制在1-100
            jpeg_para.wPicSize = 0  # 原始尺寸
            
            # 从预览抓图
            result = self.hcnetsdk.NET_DVR_CapturePicture(
                preview_handle,
                output_file.encode('gbk'),
                byref(jpeg_para)
            )
            
            if result:
                logger.info(f"从预览抓图成功: {output_file}")
                
                # 获取图片尺寸
                try:
                    width, height = self._get_image_size(output_file)
                    logger.info(f"预览抓图尺寸: {width}x{height}")
                except:
                    pass
                
                return True
            else:
                error_code = self.hcnetsdk.NET_DVR_GetLastError()
                error_msg = self._get_error_message(error_code)
                logger.error(f"从预览抓图失败，错误码: {error_code} - {error_msg}")
                return False
                
        except Exception as e:
            logger.error(f"从预览抓图异常: {e}")
            return False
    
    # ========== 新增功能5：批量处理增强 ==========
    def capture_with_info(self, channel, output_file, preview_option=False, 
                          get_size=True, resize=None):
        """
        增强版抓图：支持预览、获取尺寸、调整大小
        
        参数:
            channel: 通道号
            output_file: 输出文件路径
            preview_option: 是否预览
            get_size: 是否获取尺寸
            resize: (宽度, 高度) 调整尺寸，None表示不调整
            
        返回:
            dict: 包含抓图结果和信息的字典
        """
        result = {
            'success': False,
            'filepath': output_file,
            'size': (0, 0),
            'message': ''
        }
        
        # 执行抓图
        success = self.capture(channel, output_file)
        result['success'] = success
        
        if success:
            # 获取图片尺寸
            if get_size:
                try:
                    width, height = self._get_image_size(output_file)
                    result['size'] = (width, height)
                    
                    # 调整图片大小
                    if resize and width > 0 and height > 0:
                        new_width, new_height = resize
                        if new_width > 0 and new_height > 0:
                            resized_path = self._resize_image(output_file, new_width, new_height)
                            if resized_path:
                                result['resized_file'] = resized_path
                                result['resized_size'] = (new_width, new_height)
                except Exception as e:
                    result['message'] = f"获取尺寸失败: {str(e)}"
            
            # 预览图像
            if preview_option:
                try:
                    self._preview_image(output_file)
                except Exception as e:
                    if result['message']:
                        result['message'] += f"; 预览失败: {str(e)}"
                    else:
                        result['message'] = f"预览失败: {str(e)}"
        
        return result
    
    def _resize_image(self, image_path, new_width, new_height):
        """
        调整图片大小
        
        参数:
            image_path: 原图路径
            new_width: 新宽度
            new_height: 新高度
            
        返回:
            str: 调整后的文件路径，失败返回None
        """
        try:
            from PIL import Image
            
            # 生成新文件名
            dir_name = os.path.dirname(image_path)
            file_name = os.path.basename(image_path)
            name, ext = os.path.splitext(file_name)
            new_file = os.path.join(dir_name, f"{name}_{new_width}x{new_height}{ext}")
            
            # 调整大小
            with Image.open(image_path) as img:
                resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                resized_img.save(new_file, quality=95)
            
            logger.info(f"图片已调整大小: {new_file}")
            return new_file
            
        except Exception as e:
            logger.error(f"调整图片大小失败: {e}")
            return None

    def goto_preset(self, channel, preset_id):
        """转动摄像头到指定预置点"""
        if self._logged_in < 0:
            print("请先登录设备")
            return False

        # 云台控制命令 - 转到预置点
        command = 25  # 云台定位到预置点
        param = preset_id  # 预置点编号

        # 调用SDK云台控制函数
        result = self.hcnetsdk.NET_DVR_PTZControlWithSpeed_Other(
            self.user_id,
            channel,
            command,
            param,
            1  # 速度，范围1-7
        )

        if result:
            print(f"成功转动到预置点 {preset_id}")
            self.current_preset = preset_id
            return True
        else:
            error_code = self.hcnetsdk.NET_DVR_GetLastError()
            error_msg = self._get_error_message(error_code)
            logger.error(f"转动到预置点失败，错误码: {error_code} - {error_msg}")
            return False
    
    # 新增函数:调用/设置/清除预置点位，返回状态码和消息
    def net_dvr_ptzPreset(self, channel, PresetCmd,  preset_id):

        """转动摄像头到指定预置点"""
        if self._logged_in < 0:
            return 3, "设备未登录, 请先登录设备"
        
        # 云台控制命令 - 转到预置点
        # 宏定义	宏定义值	含义
        # SET_PRESET	8	设置预置点
        # CLE_PRESET	9	清除预置点
        # GOTO_PRESET	39	转到预置点  
        command = PresetCmd   # 云台定位到预置点
        param = preset_id       # 预置点编号

        # 调用SDK云台控制函数
        result = self.hcnetsdk.NET_DVR_PTZPreset_Other(
            self.user_id,
            channel,
            command,
            param
        )

        if result:
            logger.info(f"预置点操作成功: 命令={command}, 预置点={preset_id}")
            self.current_preset = preset_id
            return 0, "操作成功"
        else:
            error_code = self.hcnetsdk.NET_DVR_GetLastError()
            error_msg = self._get_error_message(error_code)
            return 4, f"预置点操作失败，错误码: {error_code} - {error_msg}"

    def capture_at_preset(self, channel, preset_id, output_file, wait_seconds=3):
        """转动到预置点，抓图，然后恢复原位"""
        if self._logged_in < 0:
            print("请先登录设备")
            return False

        # 记录当前预置点（假设当前位置已设为某个预置点）
        # original_preset = self.current_preset

        try:
            # 转动到目标预置点
            if preset_id != 0:
                # 操作码39是调用预置点位的命令
                code, msg = self.net_dvr_ptzPreset(channel, 39, preset_id)
                if code != 0:
                    logger.error(f"转动到预置点失败: {msg}")
                    # 即使转动失败，也尝试在当前位抓图
                    logger.warning("预置点转动失败，尝试在当前位抓图")

                # 等待摄像头移动到位
                logger.info(f"等待 {wait_seconds} 秒，让摄像头移动到位...")
                time.sleep(wait_seconds)

            # 抓图
            return self.capture(channel, output_file)

        except Exception as e:
            logger.error(f"预置点抓图异常: {e}")
            logger.error(traceback.format_exc())
            return False

    def logout(self):
        """登出设备并释放资源"""
        logger.info("开始释放资源...")
        
        try:
            # 登出设备
            if self._logged_in and self.user_id >= 0:
                result = self.hcnetsdk.NET_DVR_Logout(self.user_id)
                if result:
                    logger.info(f"已登出设备，用户ID: {self.user_id}")
                else:
                    error_code = self.hcnetsdk.NET_DVR_GetLastError()
                    error_msg = self._get_error_message(error_code)
                    logger.warning(f"登出设备失败，错误码: {error_code} - {error_msg}")
        
        except Exception as e:
            logger.error(f"登出设备异常: {e}")
        
        finally:
            # 重置状态
            self.user_id = -1
            self._logged_in = False
            self.current_preset = None
            
            # 从全局管理器注销
            _global_manager.unregister_session(self)
            
            # 重要：不调用 NET_DVR_Cleanup()，由全局管理器统一处理
            
            logger.info("资源释放完成")

    def _force_logout(self):
        """强制登出（供全局管理器调用）"""
        if self._logged_in and self.user_id >= 0:
            try:
                self.hcnetsdk.NET_DVR_Logout(self.user_id)
            except:
                pass
            
            self.user_id = -1
            self._logged_in = False

    # 调用云台控制函数:支持摄像头云台上下左右移动
    def ptz_control(self, channel, command, switch=0, speed=3):
        command_print_map = {
            21: "云台上仰",
            22: "云台下俯",
            23: "云台左转",
            24: "云台右转",
            25: "云台上仰和左转",
            26: "云台上仰和右转",
            27: "云台下俯和左转",
            28: "云台下俯和右转"
        }

        switch_map = {
            1: "停止",
            0: "开始"
        }

         # 检查命令是否有效

        if command not in command_print_map:
            print(f"不支持的云台控制命令: {command}")
            return False

        # 调用云台控制函数
        # b_ptzcontrol = self.hcnetsdk.NET_DVR_PTZControl_Other(self.user_id, channel, command, param, speed) 
        b_ptzcontrol = self.hcnetsdk.NET_DVR_PTZControlWithSpeed_Other(self.user_id, channel, command, switch, speed)

        if not b_ptzcontrol:
            error_code = self.hcnetsdk.NET_DVR_GetLastError()
            error_msg = self._get_error_message(error_code)
            logger.error(f"{switch_map[switch]}{command_print_map[command]}失败，错误码: {error_code} - {error_msg}")
            return False
        else:
            logger.info(f"设置'{switch_map[switch]}{command_print_map[command]}'成功")
            return True

    def __del__(self):
        """析构函数"""
        try:
            if self._logged_in:
                self.logout()
        except:
            pass

# ========== 新增工具函数 ==========

def capture_image_with_preview(ip, port, username, password, channel, 
                               output_file, preview=True, wait_seconds=3):
    """
    带有预览功能的抓图函数
    
    参数:
        preview: 是否预览图像
    """
    capturer = HikvisionCapture(SDK_PATH)
    
    try:
        if not capturer.initialize():
            return False
        
        if not capturer.login(ip, port, username, password):
            return False
        
        # 使用增强版抓图
        result = capturer.capture_with_info(
            channel=channel,
            output_file=output_file,
            preview_option=preview,
            get_size=True,
            resize=None  # 可以设置为 (640, 480) 等
        )
        
        return result['success']
        
    finally:
        capturer.logout()

def realtime_preview_demo(ip, port, username, password, channel, 
                          preview_time=10000):
    """
    实时预览演示
    
    参数:
        preview_time: 预览时间（毫秒）
    """
    import tkinter as tk
    from tkinter import messagebox
    
    capturer = HikvisionCapture(SDK_PATH)
    
    try:
        if not capturer.initialize():
            messagebox.showerror("错误", "SDK初始化失败")
            return
        
        if not capturer.login(ip, port, username, password):
            messagebox.showerror("错误", "设备登录失败")
            return
        
        # 创建预览窗口
        root = tk.Tk()
        root.title("海康摄像头实时预览")
        root.geometry("800x600")
        
        # 获取窗口句柄（不同平台获取方式不同）
        # 这里简化处理，实际需要根据平台获取
        hwnd = root.winfo_id()
        
        # 开始预览
        preview_handle = capturer.start_realplay_preview(channel, hwnd)
        if preview_handle < 0:
            messagebox.showerror("错误", "开始预览失败")
            return
        
        # 添加控制按钮
        def capture_from_preview():
            output_file = "preview_capture.jpg"
            if capturer.capture_from_preview(preview_handle, output_file):
                messagebox.showinfo("成功", f"抓图成功: {output_file}")
            else:
                messagebox.showerror("错误", "抓图失败")
        
        btn_capture = tk.Button(root, text="抓图", command=capture_from_preview)
        btn_capture.pack(side=tk.BOTTOM, pady=10)
        
        # 定时关闭
        root.after(preview_time, root.destroy)
        
        root.mainloop()
        
        # 停止预览
        capturer.stop_realplay_preview(preview_handle)
        
    except Exception as e:
        messagebox.showerror("异常", f"预览演示异常: {str(e)}")
        
    finally:
        capturer.logout()

# 使用示例
def capture_camera_image_at_preset(ip, port, username, password, channel, preset_id, output_file,
                                   wait_seconds=3):
    """
    在指定预置点抓取海康威视摄像头图像

    参数:
        sdk_path (str): SDK库路径
        ip (str): 设备IP地址
        port (int): 设备端口
        username (str): 登录用户名
        password (str): 登录密码
        channel (int): 通道号
        preset_id (int): 预置点编号
        output_file (str): 输出图片文件名
        wait_seconds (int): 转动后等待时间，单位秒
    """
    # 创建抓图对象
    capturer = HikvisionCapture(SDK_PATH)

    try:
        # 初始化SDK
        if not capturer.initialize():
            return False

        # 登录设备
        if not capturer.login(ip, port, username, password):
            return False

        # 在预置点抓图并恢复原位
        return capturer.capture_at_preset(channel, preset_id, output_file, wait_seconds)

    except Exception as e:
        logger.error(f"预置点抓图异常: {e}")
        logger.error(traceback.format_exc())
        return False
        
    finally:
        # 确保资源释放
        capturer.logout()

# 手动控制摄像头移动
def camera_control_move(ip, port, username, password, channel, command, switch=0,
                                   speed=3):
    """
    在指定预置点抓取海康威视摄像头图像

    参数:
        sdk_path (str): SDK库路径
        ip (str): 设备IP地址
        port (int): 设备端口
        username (str): 登录用户名
        password (str): 登录密码
        channel (int): 通道号
        preset_id (int): 预置点编号
        output_file (str): 输出图片文件名
        wait_seconds (int): 转动后等待时间，单位秒
    """
    # 创建抓图对象
    capturer = HikvisionCapture(SDK_PATH)
    try:
        # 初始化SDK
        if not capturer.initialize():
            return False

        # 登录设备
        if not capturer.login(ip, port, username, password):
            return False

        # 在预置点抓图并恢复原位
        return capturer.ptz_control(channel, command, switch, speed)

    except Exception as e:
        logger.error(f"云台控制异常: {e}")
        logger.error(traceback.format_exc())
        return False
        
    finally:
        # 确保资源释放
        capturer.logout()

#摄像头预置点位控制
def camera_control_preset(ip, port, username, password, channel, command, preset_id):
    """
      预置点位信息的设置和调用

    参数:
        ip (str): 设备IP地址
        port (int): 设备端口
        username (str): 登录用户名
        password (str): 登录密码
        channel (int): 通道号
        command (int): 预置点命令
        preset_id (int): 预置点编号
    """
    # 创建抓图对象
    capturer = HikvisionCapture(SDK_PATH)
    try:
        # 初始化SDK
        if not capturer.initialize():
            return 1, "SDK初始化失败"

        # 登录设备
        if not capturer.login(ip, port, username, password):
            return 2, "登录设备失败"

        # 在预置点
        return capturer.net_dvr_ptzPreset(channel, command, preset_id)

    except Exception as e:
        logger.error(f"预置点控制异常: {e}")
        logger.error(traceback.format_exc())
        return 5, f"预置点控制异常: {str(e)}"
        
    finally:
        # 确保资源释放
        capturer.logout()

# ==================== 测试和诊断工具 ====================

def test_resource_leak():
    """测试资源泄漏"""
    import psutil
    
    print("="*60)
    print("资源泄漏测试")
    print("="*60)
    
    process = psutil.Process()
    initial_handles = process.num_handles()
    initial_memory = process.memory_info().rss / 1024 / 1024
    
    print(f"初始状态: {initial_handles} 句柄, {initial_memory:.2f} MB")
    
    test_count = 20
    for i in range(test_count):
        output_file = f"test_{i}.jpg"
        
        success = capture_camera_image_at_preset(
            "192.168.20.30", 9001, "admin", "password",
            35, 1, output_file, 1
        )
        
        current_handles = process.num_handles()
        current_memory = process.memory_info().rss / 1024 / 1024
        
        print(f"测试 {i+1}/{test_count}: 句柄={current_handles}(+{current_handles-initial_handles}), "
              f"内存={current_memory:.2f}MB(+{current_memory-initial_memory:.2f}MB)")
    
    final_handles = process.num_handles()
    final_memory = process.memory_info().rss / 1024 / 1024
    
    print("\n测试结果:")
    print(f"句柄增长: {final_handles - initial_handles}")
    print(f"内存增长: {final_memory - initial_memory:.2f} MB")
    
    if final_handles - initial_handles > 10:
        print("❌ 检测到句柄泄漏")
        return False
    else:
        print("✅ 未检测到明显句柄泄漏")
        return True

def check_system_resources():
    """检查系统资源"""
    import psutil
    
    print("="*60)
    print("系统资源检查")
    print("="*60)
    
    process = psutil.Process()
    
    # 句柄数
    handles = process.num_handles()
    print(f"当前句柄数: {handles}")
    
    # 内存
    memory = process.memory_info().rss / 1024 / 1024
    print(f"内存使用: {memory:.2f} MB")
    
    # 系统总内存
    system_mem = psutil.virtual_memory()
    print(f"系统总内存: {system_mem.total / 1024 / 1024:.0f} MB")
    print(f"系统可用内存: {system_mem.available / 1024 / 1024:.0f} MB")
    
    # 活跃会话
    print(f"活跃SDK会话数: {len(_global_manager._active_sessions)}")
    
    print("-"*60)


def run_exe_realtime_output(nvrip, nvrport, username, password, channel, output_file):
    exe_path = r"D:\x64\DetectAndDownload.exe"
    params = [nvrip, str(nvrport), username, password, str(channel), output_file]
    
    cmd = [exe_path] + params
    
    try:
        # 启动进程
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            # cwd=r"D:\x64", # 不设置目录，否则生成的图片路径会有问题
            shell=True
        )
        
        # 实时读取输出
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                print(f"输出: {output.strip()}")
        
        # 获取剩余输出和返回码
        stdout, stderr = process.communicate()
        return_code = process.returncode
        
        if stdout:
            print(f"剩余输出: {stdout}")
        if stderr:
            print(f"错误: {stderr}")

        # 判断是否生成了图片文件
        if not os.path.exists(output_file):
            return_code = -2  # 图片文件未生成
    
        return return_code
        
    except Exception as e:
        print(f"执行出错: {e}")
        return -1


# ========== 测试代码 ==========

if __name__ == "__main__":
    # 测试1: 普通抓图带预览
    # print("测试1: 普通抓图带预览")
    # success = capture_image_with_preview(
    #     ip="192.168.20.30",
    #     port=9001,
    #     username="admin",
    #     password="zskj1225",
    #     channel=35,
    #     output_file="test_with_preview.jpg",
    #     preview=True
    # )
    # print(f"抓图结果: {'成功' if success else '失败'}")
    
    # # 测试2: 增强版抓图
    # print("\n测试2: 增强版抓图")
    # capturer = HikvisionCapture(SDK_PATH)
    # if capturer.initialize() and capturer.login("192.168.20.30", 9001, "admin", "zskj1225"):
    #     result = capturer.capture_with_info(
    #         channel=35,
    #         output_file="enhanced_capture.jpg",
    #         preview_option=True,
    #         get_size=True,
    #         resize=(640, 480)  # 调整为640x480
    #     )
    #     print(f"抓图结果: {result}")
    #     capturer.logout()

    # 测试3: 调用外部EXE
    ret = run_exe_realtime_output("192.168.20.30", 9001, "admin", "zskj1225", 37, "test_channel_37_03.jpg")
    print(f"\n测试3: 外部EXE返回码: {ret}")

    print("测试4: 控制摄像头移动")
    camera_control_move("192.168.20.30", 9001, "admin", "zskj1225", 37, 21, 0, 1)  # 上仰开始
    time.sleep(2)
    camera_control_move("192.168.20.30", 9001, "admin", "zskj1225", 37, 21, 1, 1)  # 上仰停止

    camera_control_move("192.168.20.30", 9001, "admin", "zskj1225", 37, 22, 0, 1)  # 左右移动开始
    time.sleep(2)
    camera_control_move("192.168.20.30", 9001, "admin", "zskj1225", 37, 22, 1, 1)  # 左右移动停止

    camera_control_move("192.168.20.30", 9001, "admin", "zskj1225", 37, 23, 0, 1)  # 云台左转开始
    time.sleep(2)
    camera_control_move("192.168.20.30", 9001, "admin", "zskj1225", 37, 23, 1, 1)  # 云台左转停止

    camera_control_move("192.168.20.30", 9001, "admin", "zskj1225", 38, 24, 0, 1)  # 云台右转开始
    time.sleep(2)
    camera_control_move("192.168.20.30", 9001, "admin", "zskj1225", 38, 24, 1, 1)  # 云台右转停止
    print("摄像头移动测试完成")

    # 测试3: 实时预览（需要GUI环境）
    # print("\n测试3: 实时预览")
    # realtime_preview_demo(
    #     ip="192.168.20.30",
    #     port=9001,
    #     username="admin",
    #     password="password",
    #     channel=35,
    #     preview_time=10000  # 10秒
    # )