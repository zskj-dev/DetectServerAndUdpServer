import os
import ctypes
from ctypes import *

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

    def initialize(self):
        """加载SDK库并初始化"""
        try:
            # 添加SDK库路径
            os.add_dll_directory(self.sdk_path)

            # 加载SDK动态链接库
            self.hcnetsdk = CDLL(os.path.join(self.sdk_path, "HCNetSDK.dll"))
            self.playctrllib = CDLL(os.path.join(self.sdk_path, "PlayCtrl.dll"))

            # 初始化SDK
            if not self.hcnetsdk.NET_DVR_Init():
                error_code = self.hcnetsdk.NET_DVR_GetLastError()
                raise Exception(f"SDK初始化失败，错误码: {error_code}")

            # 设置连接时间与重连功能
            self.hcnetsdk.NET_DVR_SetConnectTime(2000, 1)
            self.hcnetsdk.NET_DVR_SetReconnect(10000, True)
            return True

        except Exception as e:
            print(f"SDK初始化异常: {e}")
            return False

    def login(self, ip, port, username, password):
        """登录设备"""

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

        # 登录设备
        self.user_id = self.hcnetsdk.NET_DVR_Login_V30(
            ip.encode(),
            c_ushort(port),
            username.encode(),
            password.encode(),
            byref(self.device_info)
        )

        if self.user_id < 0:
            error_code = self.hcnetsdk.NET_DVR_GetLastError()
            print(f"登录失败，错误码: {error_code}")
            return False

        print(f"登录成功，用户ID: {self.user_id}")
        return True

    def capture(self, channel, output_file):
        """抓取指定通道的图像"""
        if self.user_id < 0:
            print("请先登录设备")
            return False

        # 抓图参数结构体
        class NET_DVR_JPEGPARA(Structure):
            _fields_ = [
                ("wPicQuality", c_ushort),  # 图片质量: 0-最好，1-较好，2-一般
                ("wPicSize", c_ushort)  # 图片尺寸: 0-160x120, 1-320x240, 2-640x480, 3-800x600等
            ]

        jpeg_para = NET_DVR_JPEGPARA()
        jpeg_para.wPicQuality = 0  # 最好质量
        jpeg_para.wPicSize = 2  # 640x480

        # 调用SDK抓图函数
        result = self.hcnetsdk.NET_DVR_CaptureJPEGPicture(
            self.user_id,
            channel,
            byref(jpeg_para),
            output_file.encode()
        )

        if result:
            print(f"抓图成功，保存至: {output_file}")
            return True
        else:
            error_code = self.hcnetsdk.NET_DVR_GetLastError()
            print(f"抓图失败，错误码: {error_code}")
            return False

    def goto_preset(self, channel, preset_id):
        """转动摄像头到指定预置点"""
        if self.user_id < 0:
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
            print(f"转动到预置点失败，错误码: {error_code}")
            return False

    # 新增函数:调用/设置/清除预置点位，返回状态码和消息
    def net_dvr_ptzPreset(self, channel, PresetCmd,  preset_id):

        """转动摄像头到指定预置点"""
        if self.user_id < 0:
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
            print(f"成功转动到预置点 {preset_id}")
            self.current_preset = preset_id
            return 0, "成功转动到预置点"
        else:
            error_code = self.hcnetsdk.NET_DVR_GetLastError()
            return 4, f"转动到预置点失败，错误码: {error_code}"

    def capture_at_preset(self, channel, preset_id, output_file, wait_seconds=3):
        """转动到预置点，抓图，然后恢复原位"""
        if self.user_id < 0:
            print("请先登录设备")
            return False

        # 记录当前预置点（假设当前位置已设为某个预置点）
        # original_preset = self.current_preset

        try:
            # 转动到目标预置点
            if preset_id != 0:
                # 操作码39是调用预置点位的命令
                if not self.net_dvr_ptzPreset(channel, 39, preset_id):
                    return False

                # 等待摄像头移动到位
                import time
                print(f"等待 {wait_seconds} 秒，让摄像头移动到位...")
                time.sleep(wait_seconds)

            # 抓图
            return self.capture(channel, output_file)

        finally:
            # 恢复到原来的预置点（如果之前记录了）
            # if original_preset is not None:
            #     print(f"正在恢复到原始预置点 {original_preset}")
            #     self.goto_preset(channel, original_preset)
            #     # 等待恢复到位
            #     time.sleep(wait_seconds)
            pass

    def logout(self):
        """登出设备并释放资源"""
        if self.user_id >= 0:
            self.hcnetsdk.NET_DVR_Logout(self.user_id)
            self.user_id = -1

        if self.hcnetsdk:
            self.hcnetsdk.NET_DVR_Cleanup()

        print("已登出设备并释放资源")


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
            print(f"{switch_map[switch]}{command_print_map[command]}失败，错误码{self.hcnetsdk.NET_DVR_GetLastError()}")
            return False
        else:
            print(f"设置'{switch_map[switch]}{command_print_map[command]}'成功")
            return True


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

    finally:
        # 确保资源释放
        capturer.logout()


# 直接调用示例
if __name__ == "__main__":
    print(SDK_PATH)
    #SDK_PATH = r"C:\\NVRDownloadImg"
    DEVICE_IP = "192.168.20.30"
    DEVICE_PORT = 9001
    USERNAME = "admin"
    PASSWORD = "zskj1225"
    CHANNEL = 35
    PRESET_ID = 1  # 目标预置点编号
    OUTPUT_FILE = "preset_capture1.jpg"
    WAIT_SECONDS = 10  # 转动后等待时间
    SPEED = 3

    # success = capture_camera_image_at_preset(
    #     # SDK_PATH,
    #     DEVICE_IP,
    #     DEVICE_PORT,
    #     USERNAME,
    #     PASSWORD,
    #     CHANNEL,
    #     PRESET_ID,
    #     OUTPUT_FILE,
    #     WAIT_SECONDS
    # )

    success = camera_control_move(
        # SDK_PATH,
        DEVICE_IP,
        DEVICE_PORT,
        USERNAME,
        PASSWORD,
        CHANNEL,
        22,
        0,
        SPEED
    )

    # success = camera_control_preset(
    #     # SDK_PATH,
    #     DEVICE_IP,
    #     DEVICE_PORT,
    #     USERNAME,
    #     PASSWORD,
    #     CHANNEL,
    #     39,
    #     PRESET_ID
    # )

    if success:
        print("预置点图像抓取成功")
    else:
        print("预置点图像抓取失败")