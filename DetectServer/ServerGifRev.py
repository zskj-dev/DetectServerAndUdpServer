import json

import requests
from PIL import Image, ImageDraw, ImageFont
import struct
from multiprocessing import Process, Queue,Lock
import socket
from common.mysqloptor import db
import time
import datetime,os
import subprocess
import random
import string
from ultralytics import YOLO
import cv2
from PIL import Image
import io
qDetectTask = Queue()

#url = 'http://127.0.0.1:5000/api/endpoint'
url='http://192.168.20.2:8001/api/AddVideoAlarm' # 首钢用尚主站服务器IP


file_save_path = "./runs/errorgifs"

localcolors = [
    "severe_alert",  # 严重告警
    "high_warning",  # 高优先级警告
    "medium_warning",  # 中等优先级警告
    "low_notice",  # 低优先级通知
    "critical_error",  # 关键错误
    "minor_issue",  # 次要问题
    "emergency_alert",  # 紧急告警
    "resolved_alert",  # 已解决的告警（可选）
]
# 定义颜色名称到RGB元组的映射
color_mapping = {
    "severe_alert": (255, 0, 0),        # 鲜艳的红色，用于严重告警
    "high_warning": (255, 69, 0),       # 橙红色，用于高优先级警告
    "medium_warning": (255, 140, 0),    # 亮橙色（偏红），用于中等优先级警告
    "low_notice": (255, 192, 203),      # 浅粉红色，用于低优先级通知
    "critical_error": (139, 0, 0),      # 深红色，用于关键错误
    "minor_issue": (255, 20, 147),      # 紫红色，用于次要问题
    "emergency_alert": (255, 99, 71),   # 鲜亮的番茄红，用于紧急告警
    "resolved_alert": (188, 143, 143),  # 淡玫瑰红色，用于已解决的告警（可选）
}


def receive_file(file_path, buffer_size=1024):
    file_name = ""
    # 创建TCP/IP套接字
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # 绑定到本地地址和端口
    server_address = ('0.0.0.0', 65432)
    server_socket.bind(server_address)

    # 监听连接
    server_socket.listen(10)

    print(f"[*] Listening on {server_address}")

    # 等待连接
    connection, client_address = server_socket.accept()
    try:
        print(f"[*] Connection from {client_address}")

        # 接收文件名长度（使用struct模块来解包）
        file_name_length_packed = connection.recv(4)  # 假设文件名长度使用4字节表示
        file_name_length = struct.unpack('>I', file_name_length_packed)[0]  # '>I' 表示无符号长整型（4字节），大端序

        # 接收文件名
        file_name = connection.recv(file_name_length).decode()
        print(f"[*] Receiving file: {file_name}")

        # 创建文件并写入数据
        with open(os.path.join(file_path, file_name), 'wb') as f:
            while True:
                data = connection.recv(buffer_size)
                if not data:
                    break
                f.write(data)

        print(f"[*] File {file_name} received successfully")

    finally:
        # 清理连接
        connection.close()
    return file_name

def getSystemConfig():
    sqltotal = "select errortype,errorname,alarmtype  from m_errortype"
    totaldata = db.select_db(sqltotal)
    print("getSystemConfig info:",totaldata)
    return totaldata

def checkErrorTypeAlarm(typeval):

    dictinfo = getSystemConfig()
    if len(dictinfo) == 0:
        return 1

    for item in dictinfo:
        if item['errortype'] == typeval:
            return item['alarmtype']

    return 1

def getModelFileNameAndCurErrLevel(flag_name="flag"):
    systemsetting = {}
    sqltotal = "select a.filename,a.id from m_model a where a.{} = 1".format(flag_name)
    totaldata = db.select_db(sqltotal)
    print("getSystemConfig using model name:", totaldata[0]["filename"])
    systemsetting["filename"] = totaldata[0]["filename"]
    systemsetting["fileid"] = totaldata[0]["id"]
    sqltotal = "select curerrlevel from m_systemsetting"
    totaldata = db.select_db(sqltotal)
    print("getSystemConfig using errlv:",totaldata[0]["curerrlevel"])
    systemsetting["curerrlevel"] = totaldata[0]["curerrlevel"]
    return systemsetting


def getModelFileTypeErrLevel(modelid, syslevel):
    li = {}
    sqltotal = "select modelid, errtypeindex, errtypename, errtypelevel from m_modelinfo where modelid = {}".format( modelid)
    totaldata = db.select_db(sqltotal)

    for item in totaldata:
        if item['errtypelevel'] >= syslevel:
            li[str(item['errtypeindex'])] = 1
        else:
            li[str(item['errtypeindex'])] = 0
    print("getModelFileTypeErrLevel:",li)

    return li

# 根据告警等级从高到低排序，并返回对应的errtypeindex列表
def getModelFileTypeErrLevelPriority():
    table_name_model = "m_model"
    table_name_modelinfo = "m_modelinfo"
    errtype_priority = []
    # 先从m_model中找到使能的id，然后根据这个id从m_modelinfo中查询对应的errtypeindex和errtypelevel，最后根据errtypelevel从高到低排序，并返回对应的errtypeindex列表
    sqltotal = "select id from {} where flag = 1".format(table_name_model)
    totaldata = db.select_db(sqltotal)
    if len(totaldata) <= 0:
        print("get id error: not found",totaldata)
        return errtype_priority

    modelid = totaldata[0]["id"]
    sqltotal = "select errtypeindex from {} where modelid = {} order by errtypelevel desc".format(table_name_modelinfo,modelid)
    totaldata = db.select_db(sqltotal)
    print("getModelFileTypeErrLevelPriority totaldata:", totaldata)

    for item in totaldata:
        errtypeindex = item['errtypeindex']
        errtype_priority.append(errtypeindex)
    print("get errtpyeindex_list:", errtype_priority)
    return errtype_priority

def gif_to_frames(gif_bytes):
    # 从字节流中打开GIF文件
    with Image.open(io.BytesIO(gif_bytes)) as img:
        frames = []
        for frame_number in range(img.n_frames):
            img.seek(frame_number)
            # 将当前帧保存到内存中的字节流
            frame_bytes = io.BytesIO()
            img.save(frame_bytes, format="PNG")
            frames.append(frame_bytes.getvalue())
    return frames


# 根据输入的告警类型优先级顺序，修改process_frame函数，使其只检测指定的错误类型，并返回该类型的计数
def process_frame_priority(frame_bytes, model, systemsetting, target_error_type):
    """
    修改版的process_frame，只检测指定的错误类型
    """
    type_counts = {str(target_error_type): 0}

    with Image.open(io.BytesIO(frame_bytes)) as img:
        rgb_img = img.convert("RGB")
        #print(rgb_img.mode)
        results = model.predict(source=rgb_img, stream=True)
        for result in results:
            boxes = result.boxes.data.cpu().numpy()
            for box in boxes:
                x1, y1, x2, y2, conf, cls = box
                if str(int(cls)) == str(target_error_type) and systemsetting["info"].get(str(int(cls)), 0) == 1:
                    class_name = model.names[int(cls)]
                    draw = ImageDraw.Draw(rgb_img)
                    color = localcolors[int(cls) % len(localcolors)]
                    color = color_mapping[color]
                    draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
                    draw.text((x1, y1 - 10), f"{class_name} {conf:.2f}", fill=color)
                    print("class_name:", class_name, [x1, y1, x2, y2], color)
                    type_counts[str(int(cls))] += 1

        processed_bytes = io.BytesIO()
        rgb_img.save(processed_bytes, format="PNG")
        return processed_bytes.getvalue(), type_counts

def frames_to_gif(frames, output_gif_path, duration=100):
    # 从第一帧获取模式和尺寸
    try:
        with Image.open(io.BytesIO(frames[0])) as img:
            mode = img.mode
            size = img.size

            # 创建新的GIF文件
            new_gif = Image.new(mode, size)
            new_gif.save(output_gif_path, save_all=True, append_images=[Image.open(io.BytesIO(frame)) for frame in frames],
                         duration=duration, loop=0)
    except Exception as e:
        pass

def DetectGifThread(mqDetectTask, systemsetting):
    print("DetectGifThread start")
    model = YOLO(systemsetting["filename"])

    while 1:
        try:
            t = mqDetectTask.get(timeout=1)
            giffilename = t[0]
            print("get task:",giffilename)
            giffilenamefile_path = os.path.join(file_save_path, giffilename)

            with open(giffilenamefile_path, "rb") as f:
                gif_bytes = f.read()
                frames = gif_to_frames(gif_bytes)

                # 获取错误类型及其优先级顺序
                error_types = getModelFileTypeErrLevelPriority()

                # 初始化检测结果
                detected_error = None
                error_count = 0
                processed_frames = []

                # 按优先级顺序检查错误
                for priority_error in error_types:
                    print(f"Checking for priority error type: {priority_error}")
                    current_error_count = 0
                    current_processed_frames = []

                    # 处理所有帧，统计当前优先级错误的出现次数
                    for frame in frames:
                        processed_frame, type_counts = process_frame_priority(
                            frame, model, systemsetting, priority_error
                        )
                        # 累加当前优先级错误的计数
                        current_processed_frames.append(processed_frame)
                        current_error_count += type_counts.get(str(priority_error), 0)  # 使用get方法更安全

                    print(f"Priority error {priority_error} total count: {current_error_count}")

                    # 如果当前优先级错误达到阈值，立即采用这个结果
                    if current_error_count >= 3:
                        detected_error = priority_error
                        error_count = current_error_count
                        processed_frames = current_processed_frames
                        print(f"Found priority error: {priority_error} with count {error_count}")
                        break

                # 如果所有优先级都没有找到错误（计数<3），使用第一个优先级作为默认
                if not detected_error:
                    detected_error = error_types[0] if error_types else "0"
                    error_count = 0
                    # 重新处理所有帧，使用默认错误类型
                    processed_frames = []
                    for frame in frames:
                        processed_frame, type_counts = process_frame_priority(
                            frame, model, systemsetting, detected_error
                        )
                        processed_frames.append(processed_frame)
                        if detected_error in type_counts:
                            error_count += type_counts[detected_error]
                    print(f"No errors detected, using default: {detected_error} with count {error_count}")

                # 将处理后的帧重新组合成GIF并保存
                frames_to_gif(processed_frames, giffilenamefile_path, duration=400)

                # 确定状态
                state = 1  # 默认状态
                if error_count == 0:
                    state = 1
                elif error_count >= 3:
                    state = 3

                sql = "update m_errorinfo set errortype={},state={} where gifname='{}'".format(
                    detected_error, state, giffilename
                )
                print("----AlarmInfoHandler sql:", sql)
                db.execute_db(sql)
                print("----AlarmInfoHandler sql over!")

                if state == 3:
                    SendErrInfoToServer(giffilename)
        except Exception as e:
            pass

class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()  # 转换为 ISO 8601 格式的字符串
        return super().default(obj)

def SendErrInfoToServer(giffilename):
    selectsql = '''select id as AlarmSerial, meaning as AlarmType, updatetime as HappenTime, 
    stationname as StationName, roomname as RoomName, nvrip as NVRIP,nvrport as NVRPort, 
    nvruser as NVRUser, nvrpasswd as NVRPasswd,nvrchannel as NVRChannel,taskfrom as TaskFrom, gifname as AlarmGif,
     errorimg as AlarmImg  from v_errlist where gifname='{}' '''.format(giffilename)
    totaldata = db.select_db(selectsql)

    if totaldata is None:
        return
    if len(totaldata) == 0:
        return

    first_record = totaldata[0]
    if first_record["HappenTime"] != None:
        print("time modify")
        first_record["HappenTime"] = first_record["HappenTime"].strftime("%Y-%m-%d %H:%M:%S")
    # 将第一组数据转换为 JSON 字符串
    json_data = json.dumps(first_record, ensure_ascii=False)
    print(json_data)
    # 目标服务器的 URL

    response = requests.post(url, headers={'Content-Type': 'application/json'}, json=first_record)#data=json_data) #, headers={'Content-Type': 'application/json'}
    print("Status Code:", response.status_code,"Response Body:", response.text)


if __name__ == "__main__":
    systemsetting = getModelFileNameAndCurErrLevel()
    systemsetting["info"] = getModelFileTypeErrLevel(systemsetting["fileid"], systemsetting["curerrlevel"])
    print(systemsetting)
    p = Process(target=DetectGifThread, args=(qDetectTask,systemsetting, ))
    p.start()
    qDetectTask.put(["1.gif", 0])
    #qDetectTask.put(["2.gif", 0])
    #qDetectTask.put(["bj200301_1_17_16_0_151.gif", 0])
    if not os.path.exists(file_save_path):
        os.makedirs(file_save_path)

    while(1):
        file_name = receive_file(file_save_path)
        if (len(file_name) > 3):
            qDetectTask.put([file_name, 0])
        print("waiting!")

