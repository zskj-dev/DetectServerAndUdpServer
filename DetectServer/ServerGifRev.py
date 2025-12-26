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


def process_frame(frame_bytes,model,systemsetting):
    type_counts = {str(k): 0 for k in systemsetting["info"].keys()}  # 初始化类型计数器
    # 从字节流中打开帧
    with Image.open(io.BytesIO(frame_bytes)) as img:
        rgb_img = img.convert("RGB")
        #print(rgb_img.mode)
        results = model.predict(source=rgb_img, stream=True)
        for result in results:
            boxes = result.boxes.data.cpu().numpy()
            for box in boxes:
                x1, y1, x2, y2, conf, cls = box
                if systemsetting["info"].get(str(int(cls)), 0) == 1:
                    # 获取类别名称（根据你的模型类别定义）
                    class_name = model.names[int(cls)]
                    # 在图像上绘制边界框和类别名称
                    draw = ImageDraw.Draw(rgb_img)
                    color = localcolors[int(cls) % len(localcolors)]
                    color = color_mapping[color]
                    draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
                    #draw.rectangle([x1, y1, x2, y2],  width=2)
                    draw.text((x1, y1 - 10), f"{class_name} {conf:.2f}", fill=color)
                    #draw.text((x1, y1 - 10), f"{class_name} {conf:.2f}")
                    print("class_name:", class_name, [x1, y1, x2, y2],color)
                    # 增加对应类别的计数
                    type_counts[str(int(cls))] += 1
        # 将处理后的帧保存到内存中的字节流
        processed_bytes = io.BytesIO()
        rgb_img.save(processed_bytes, format="PNG")
        return processed_bytes.getvalue(),type_counts
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
                # 对帧进行处理（在内存中）
                processed_frames = []
                total_type_counts = {str(k): 0 for k in systemsetting["info"].keys()}  # 初始化总计数器
                for frame in frames:
                    processed_frame, type_counts = process_frame(frame, model, systemsetting)
                    processed_frames.append(processed_frame)
                    #print("detect:", type_counts)
                    # 更新总计数器
                    for key, count in type_counts.items():
                        total_type_counts[key] += count
                #processed_frames = [process_frame(frame,model,systemsetting) for frame in frames]

                # 确定出现最多的类型
                most_common_type = max(total_type_counts, key=total_type_counts.get)
                print(f"Most common type: {most_common_type} with count {total_type_counts[most_common_type]}")
                # 将处理后的帧重新组合成GIF并保存到本地
                frames_to_gif(processed_frames, giffilenamefile_path, duration=400)
                state = 0
                if (total_type_counts[most_common_type] == 0):
                    state = 1
                elif (total_type_counts[most_common_type] >= 3):
                    state = 3
                else:
                    state = 1

                sql = "update m_errorinfo set errortype={},state={} where gifname='{}'".format(most_common_type,state,giffilename)
                print("----AlarmInfoHandler sql:",sql)
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

