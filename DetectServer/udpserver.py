# udp_server.py
import json
from multiprocessing import Process, Queue,Lock
import socket

from hk.getimgfromDVRBySDK import capture_camera_image_at_preset
from common.mysqloptor import db
import time
import datetime,os
import subprocess
import random
import string
from ultralytics import YOLO
import cv2
from datetime import datetime, timedelta
from PIL import Image,ImageDraw
import uuid

qDetectTask = Queue()

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

def getModelFileNameAndCurErrLevel():
    systemsetting = {}
    sqltotal = "select a.filename,a.id from m_model a where a.flag = 1"
    totaldata = db.select_db(sqltotal)
    #print("getSystemConfig:", totaldata[0]["filename"])
    systemsetting["filename"] = totaldata[0]["filename"]
    systemsetting["fileid"] = totaldata[0]["id"]
    sqltotal = "select curerrlevel from m_systemsetting"
    totaldata = db.select_db(sqltotal)
    #print("getSystemConfig:",totaldata[0]["curerrlevel"])
    systemsetting["curerrlevel"] = totaldata[0]["curerrlevel"]
    return systemsetting

'''生成唯一码'''
def generate_unique_code():
    unique_id = uuid.uuid4()
    return str(unique_id)

def getModelFileTypeErrLevel(modelid, syslevel):
    li = {}
    sqltotal = "select modelid, errtypeindex, errtypename, errtypelevel from m_modelinfo where modelid = {}".format( modelid)
    totaldata = db.select_db(sqltotal)

    for item in totaldata:
        if item['errtypelevel'] >= syslevel:
            li[str(item['errtypeindex'])] = 1
        else:
            li[str(item['errtypeindex'])] = 0
    #print("getModelFileTypeErrLevel:",li)

    return li


def is_file_readable_with_content(file_path):
    """
    检查文件是否存在、可读以及不为空。

    :param file_path: 文件的路径
    :return: 如果文件存在、可读且不为空，则返回True；否则返回False
    """
    # 检查文件是否存在
    if not os.path.exists(file_path):
        return False

        # 检查文件是否有读取权限
    if not os.access(file_path, os.R_OK):
        return False

        # 检查文件是否为空
    # 使用os.stat()获取文件大小，如果大小为0，则认为是空文件
    file_size = os.stat(file_path).st_size
    if file_size == 0:
        return False
    print("file_size:",file_size)
        # 如果通过了所有检查，则文件是可读的且不为空
    return True


# 更新对应巡视任务的上一次执行时间和当前任务的任务唯一码
def updateTaskPlanPreTimeAndMagicCode(planid,mgcode):
    print("updateTaskPlanPreTimeAndMagicCode:", planid,mgcode)
    #nowTime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sqlstr = "update m_visitationplan set  curmagicserial='{}',curprogress=0 where id ={}".format(mgcode, planid)
    print("updateTaskPlanPreTimeAndMagicCode:",sqlstr)
    db.execute_db(sqlstr)


# 更新巡视计划的进度百分比
def updateTaskPlanState(planid, val):
    sqlstr = "update m_visitationplaninfo set curprogress={}  where id ={}".format(val, planid)
    db.execute_db(sqlstr)

#获取对应表的下一个ID号，用于insert
def getTableNextID(TableName):
    select_maxid_sql = 'select max(id) as maxid from {}'.format(TableName)
    select_maxid_result = db.select_db(select_maxid_sql)
    id = 0
    if select_maxid_result[0]['maxid'] is None:
        id = 1
    else:
        id = int(select_maxid_result[0]['maxid']) + 1
    return id

#巡视任务子项 执行函数
def sendOptInfoToDev(optipaddr, yiqiid,port=8081, timeout=30):
    """
    通过TCP发送命令并根据响应或超时判断结果

    参数:
        host (str): 服务器IP地址
        port (int): 服务器端口
        command (str): 要发送的命令
        timeout (int): 超时时间（秒），默认10秒

    返回:
        bool: True表示成功，False表示失败
    """
    print("sendOptInfoToDev:", optipaddr, yiqiid, port)
    try:
        # 创建TCP套接字
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            # 设置超时时间
            s.settimeout(timeout)
            # 连接服务器
            # 连接到服务器
            print(f"正在连接到:{optipaddr}:{port}...")
            s.connect((optipaddr, port))
            print(f"已成功连接到 {optipaddr}:{port}")

            # 发送消息（需要先将字符串编码为字节）
            message_bytes = str(yiqiid).encode('utf-8')
            s.sendall(message_bytes)
            print(f"已发送消息: {str(yiqiid)}")
            # 发送命令
            # 记录开始时间
            start_time = time.time()
            try:
                # 接收响应
                response = s.recv(1024).decode().strip()
                print(f"收到响应: {response}")

                # 根据响应内容判断结果
                if response == "1":
                    return True
                else:  # 包括"0"和其他情况
                    return False
            except socket.timeout:
                # 超时处理
                elapsed_time = time.time() - start_time
                print(f"超时({elapsed_time:.2f}秒): 未收到响应，视为成功")
                return True

    except Exception as e:
        print(f"通信异常: {e}")
        return False


def getNVRInfo(imgid):
    sqlstr = "select * from m_camera aa LEFT JOIN m_dvr bb on aa.dvr_id=bb.dvr_id where  camera_id = {}".format(imgid)
    print("getNVRInfo sql:", sqlstr)
    totaldata = db.select_db(sqlstr)
    print("NVR",totaldata)
    if totaldata is not None and len(totaldata) > 0:
        return totaldata[0]
    return None


def InsertSubPlanInfoToHis(taskinfoid, mgcode, imgfilenameonly):
    TableName = "m_visitationplaninfohistory"
    select_maxid_sql = 'select max(id) as maxid from {}'.format(TableName)
    select_maxid_result = db.select_db(select_maxid_sql)
    id = 0
    if select_maxid_result[0]['maxid'] is None:
        id = 1
    else:
        id = int(select_maxid_result[0]['maxid']) + 1

    insert_dic = {
        'id': id,
        'taskinfoid': taskinfoid,
        'imgfilename': os.path.basename(imgfilenameonly),
        'detectresult': 0,
        'errtype': 0,
        'errid': 0,
        'errinfo': "",
        'taskmagicserial': mgcode,
    }
    db.insertData(TableName, insert_dic)
    return id


def UpdateSubPlanCheckResultByHisid(hisid, errinfo, errid, errtype, detectresult):
    sqlstr = '''
    UPDATE m_visitationplaninfohistory
        SET 
        errinfo = '{}',
        errid = {},
        errtype = {},
        detectresult = {}
        WHERE 
        id = {}
    '''.format(errinfo,errid, errtype, detectresult, hisid )
    db.execute_db(sqlstr)
def PlanSubItemAction(iitem, mgcode):
    if iitem["id"] is None:
        return

    if iitem["ctlopt"] is None:
        return

    status_data = {
        "OptJiQiRen": "",
        "DownLoadImage": "",
        "DetectImage": "",
    }

    # 检测
    errstr = ""
    errid = 0
    errtype = 0
    resultstr = 0

    #增加检测记录
    imgfilenameonly = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runs", "images",
                                   generate_unique_code() + ".jpg")
    print("PlanSubItemAction:", iitem["id"], mgcode, iitem,imgfilenameonly)
    hisid = InsertSubPlanInfoToHis(iitem["id"] ,mgcode, imgfilenameonly)
    print("123123 will send opt msg:",  iitem["ctlopt"])
    # 1、是否在检修区域
    OverhaulAreaCameras_bool, OverhaulArea_starttime, OverhaulArea_endtime = getOverhaulArearoom_Cameras(int(iitem["camid"]))
    print("1111:", OverhaulAreaCameras_bool, OverhaulArea_starttime, OverhaulArea_endtime)
    if OverhaulAreaCameras_bool != False and OverhaulArea_starttime != '' and OverhaulArea_endtime != '':
        print("在检修区域")
        print(OverhaulAreaCameras_bool, OverhaulArea_starttime, OverhaulArea_endtime)
        time_format = "%Y-%m-%d %H:%M:%S"
        current_time = str(datetime.now())
        try:
            # 尝试解析带微秒的格式
            target_time = datetime.strptime(current_time, "%Y-%m-%d %H:%M:%S.%f")
        except ValueError:
            # 如果失败，尝试解析不带微秒的格式
            target_time = datetime.strptime(current_time, "%Y-%m-%d %H:%M:%S")
        print('当前时间{}'.format(target_time))
        start_time = datetime.strptime(str(OverhaulArea_starttime), time_format)
        end_time = datetime.strptime(str(OverhaulArea_endtime), time_format)
        # current_time= datetime.datetime.now()
        if target_time >= start_time and target_time <= end_time and OverhaulAreaCameras_bool == True:
            print('{}该摄像头处于检修时间'.format(iitem["camid"]))
            # return
    #2、是否需要控制
    elif int(iitem["ctlopt"]) == 1:
        print("start send opt msg:", iitem["ctlopt"])
        isok = sendOptInfoToDev(iitem["optipaddr"], iitem["yiqiid"])
        print("send opt over msg:", isok)
        if isok == False:
            status_data["OptJiQiRen"] = "send command info to JiQiRen failed!"
            errid = 10002
            resultstr = 1
            errstr = json.dumps(status_data, ensure_ascii=False)
            UpdateSubPlanCheckResultByHisid(hisid, errstr, errid, errtype, resultstr)
            return

        imgid = iitem["camid"]
        watchpoint = iitem["watchpoint"]

        NVRInfo = getNVRInfo(imgid)
        if NVRInfo is None:
            status_data["DownLoadImage"] = "NVR Info empty"
            errid = 10001
            resultstr = 2
            errstr = json.dumps(status_data, ensure_ascii=False)
            UpdateSubPlanCheckResultByHisid(hisid, errstr, errid, errtype, resultstr)
            return

        success = capture_camera_image_at_preset(
            NVRInfo["ip"],
            NVRInfo["port"],
            NVRInfo["user"],
            NVRInfo["pwd"],
            NVRInfo["channel"],  # 通道号
            watchpoint,  # 预置点编号
            imgfilenameonly,  # 输出文件名
            5  # 等待时间（秒）
        )
        if success == False:
            status_data["DownLoadImage"] = "Download Image Failed"
        else:
            status_data["DownLoadImage"] = "Download Image Successed!"
        resultstr = 3
        errstr = json.dumps(status_data, ensure_ascii=False)
        UpdateSubPlanCheckResultByHisid(hisid, errstr, errid, errtype, resultstr)
        # 判断在可控制情况下是否表计检测：
        # 不是表计是检测任务的话
        if int(iitem["checktype"])!=1:
            print("该摄像头可控的是检测任务")
            print("参数:", hisid, errstr, errid, errtype, resultstr)
            try:
                systemsetting = getModelFileNameAndCurErrLevel()
                systemsetting["info"] = getModelFileTypeErrLevel(systemsetting["fileid"],
                                                                 systemsetting["curerrlevel"])
                # 检测图片并返回检测类型、检测state
                print(imgfilenameonly, systemsetting)
                detectImage_sigleresult = DetectImage(imgfilenameonly, systemsetting)
            except Exception as e:
                print(e)
            stat1 = detectImage_sigleresult.get("state")
            # print("stat1:", stat1)
            errortype1 = detectImage_sigleresult.get("errortype")
            # print("errortype1:", errortype1)
            errorimg1 = os.path.basename(imgfilenameonly)
            # print("errorimg1:", errorimg1)
            print("NVRInfo", NVRInfo)
            InsertErrorSigleImage(NVRInfo, errorimg1, errortype1, stat1)

        else:
            # 是表计情况下执行下恻方法：
            print("该摄像头可控的是表计任务")
            print("参数:", hisid, errstr, errid, errtype, resultstr)
            try:
                systemsetting = getModelFileNameAndCurErrLevel()
                systemsetting["info"] = getModelFileTypeErrLevel(systemsetting["fileid"],
                                                                 systemsetting["curerrlevel"])
                # 检测图片并返回检测类型、检测state
                print(imgfilenameonly, systemsetting)
                detectImage_sigleresult = DetectImage(imgfilenameonly, systemsetting)
            except Exception as e:
                print(e)
            stat1 = detectImage_sigleresult.get("state")
            # print("stat1:", stat1)
            errortype1 = detectImage_sigleresult.get("errortype")
            # print("errortype1:", errortype1)
            errorimg1 = os.path.basename(imgfilenameonly)
            # print("errorimg1:", errorimg1)
            print("NVRInfo", NVRInfo)
            InsertErrorSigleImage(NVRInfo, errorimg1, errortype1, stat1)

    else:
        # 3、其他情况（没有检修区域，没有可控制状态   直接检测or表计任务）
        print("该摄像头是不可控的")
        imgid = iitem["camid"]
        watchpoint = iitem["watchpoint"]

        NVRInfo = getNVRInfo(imgid)
        if NVRInfo is None:
            status_data["DownLoadImage"] = "NVR Info empty"
            errid = 10001
            resultstr = 2
            errstr = json.dumps(status_data, ensure_ascii=False)
            UpdateSubPlanCheckResultByHisid(hisid, errstr, errid, errtype, resultstr)
            return

        success = capture_camera_image_at_preset(
            NVRInfo["ip"],
            NVRInfo["port"],
            NVRInfo["user"],
            NVRInfo["pwd"],
            NVRInfo["channel"],  # 通道号
            watchpoint,  # 预置点编号
            imgfilenameonly,  # 输出文件名
            5  # 等待时间（秒）
        )
        if success == False:
            status_data["DownLoadImage"] = "Download Image Failed"
        else:
            status_data["DownLoadImage"] = "Download Image Successed!"
        resultstr = 3
        errstr = json.dumps(status_data, ensure_ascii=False)
        UpdateSubPlanCheckResultByHisid(hisid, errstr, errid, errtype, resultstr)
        # 是检测任务的话
        if int(iitem["checktype"]) != 1:
            print("该摄像头不可控的是检测任务")
            print("参数:", hisid, errstr, errid, errtype, resultstr)
            try:
                systemsetting = getModelFileNameAndCurErrLevel()
                systemsetting["info"] = getModelFileTypeErrLevel(systemsetting["fileid"],
                                                                 systemsetting["curerrlevel"])
                # 检测图片并返回检测类型、检测state
                print(imgfilenameonly, systemsetting)
                detectImage_sigleresult = DetectImage(imgfilenameonly, systemsetting)
            except Exception as e:
                print(e)
            stat1 = detectImage_sigleresult.get("state")
            # print("stat1:", stat1)
            errortype1 = detectImage_sigleresult.get("errortype")
            # print("errortype1:", errortype1)
            errorimg1 = os.path.basename(imgfilenameonly)
            # print("errorimg1:", errorimg1)
            print("NVRInfo", NVRInfo)
            InsertErrorSigleImage(NVRInfo, errorimg1, errortype1, stat1)

        else:
            # 是表计情况下执行下恻方法：
            print("该摄像头不可可控的是表计任务")
            print("参数:", hisid, errstr, errid, errtype, resultstr)
            try:
                systemsetting = getModelFileNameAndCurErrLevel()
                systemsetting["info"] = getModelFileTypeErrLevel(systemsetting["fileid"],
                                                                 systemsetting["curerrlevel"])
                # 检测图片并返回检测类型、检测state
                print(imgfilenameonly, systemsetting)
                detectImage_sigleresult = DetectImage(imgfilenameonly, systemsetting)
            except Exception as e:
                print(e)
            stat1 = detectImage_sigleresult.get("state")
            # print("stat1:", stat1)
            errortype1 = detectImage_sigleresult.get("errortype")
            # print("errortype1:", errortype1)
            errorimg1 = os.path.basename(imgfilenameonly)
            # print("errorimg1:", errorimg1)
            print("NVRInfo", NVRInfo)
            InsertErrorSigleImage(NVRInfo, errorimg1, errortype1, stat1)


    # #需要控制
    # if int(iitem["ctlopt"]) == 1:
    #     print("start send opt msg:", iitem["ctlopt"])
    #     isok = sendOptInfoToDev(iitem["optipaddr"], iitem["yiqiid"])
    #     print("send opt over msg:", isok)
    #     if isok == False:
    #         status_data["OptJiQiRen"] = "send command info to JiQiRen failed!"
    #         errid = 10002
    #         resultstr = 1
    #         errstr = json.dumps(status_data,ensure_ascii=False)
    #         UpdateSubPlanCheckResultByHisid(hisid, errstr, errid, errtype, resultstr)
    #         return
    #
    #     imgid = iitem["camid"]
    #     watchpoint = iitem["watchpoint"]
    #
    #     NVRInfo = getNVRInfo(imgid)
    #     if NVRInfo is None:
    #         status_data["DownLoadImage"]  = "NVR Info empty"
    #         errid = 10001
    #         resultstr = 2
    #         errstr = json.dumps(status_data, ensure_ascii=False)
    #         UpdateSubPlanCheckResultByHisid(hisid, errstr, errid, errtype, resultstr)
    #         return
    #
    #     success = capture_camera_image_at_preset(
    #         NVRInfo["ip"],
    #         NVRInfo["port"],
    #         NVRInfo["user"],
    #         NVRInfo["pwd"],
    #         NVRInfo["channel"],  # 通道号
    #         watchpoint,  # 预置点编号
    #         imgfilenameonly,  # 输出文件名
    #         5  # 等待时间（秒）
    #     )
    #     if success == False:
    #         status_data["DownLoadImage"] = "Download Image Failed"
    #     else:
    #         status_data["DownLoadImage"] = "Download Image Successed!"
    #     resultstr = 3
    #     errstr = json.dumps(status_data, ensure_ascii=False)
    #     UpdateSubPlanCheckResultByHisid(hisid, errstr, errid, errtype, resultstr)
    # else:
    #     OverhaulAreaCameras_bool, OverhaulArea_starttime, OverhaulArea_endtime =getOverhaulArearoom_Cameras(iitem["cmid"])
    #     if OverhaulAreaCameras_bool !=False and OverhaulArea_starttime !='' and OverhaulArea_endtime !='':
    #         print(OverhaulAreaCameras_bool, OverhaulArea_starttime, OverhaulArea_endtime)
    #         time_format = "%Y-%m-%d %H:%M:%S"
    #         current_time = str(datetime.now())
    #         try:
    #             # 尝试解析带微秒的格式
    #             target_time = datetime.strptime(current_time, "%Y-%m-%d %H:%M:%S.%f")
    #         except ValueError:
    #             # 如果失败，尝试解析不带微秒的格式
    #             target_time = datetime.strptime(current_time, "%Y-%m-%d %H:%M:%S")
    #         print('当前时间{}'.format(target_time))
    #         start_time = datetime.strptime(str(OverhaulArea_starttime), time_format)
    #         end_time = datetime.strptime(str(OverhaulArea_endtime), time_format)
    #         # current_time= datetime.datetime.now()
    #         if target_time >= start_time and target_time <= end_time and OverhaulAreaCameras_bool==True:
    #             print('{}该摄像头处于检修时间'.format(iitem["camid"]))
    #         else:
    #             print("start send opt msg:", iitem["ctlopt"])
    #             imgid = iitem["camid"]
    #             watchpoint = iitem["watchpoint"]
    #             NVRInfo = getNVRInfo(imgid)
    #             if NVRInfo is None:
    #                 status_data["DownLoadImage"] = "NVR Info empty"
    #                 errid = 10001
    #                 resultstr = 2
    #                 errstr = json.dumps(status_data, ensure_ascii=False)
    #                 UpdateSubPlanCheckResultByHisid(hisid, errstr, errid, errtype, resultstr)
    #                 return
    #             print("NVRInfo", NVRInfo)
    #             success = capture_camera_image_at_preset(
    #                 NVRInfo["ip"],
    #                 NVRInfo["port"],
    #                 NVRInfo["user"],
    #                 NVRInfo["pwd"],
    #                 NVRInfo["channel"],  # 通道号
    #                 watchpoint,  # 预置点编号
    #                 imgfilenameonly,  # 输出文件名
    #                 5  # 等待时间（秒）
    #             )
    #             if success == False:
    #                 status_data["DownLoadImage"] = "Download Image Failed"
    #             else:
    #                 status_data["DownLoadImage"] = "Download Image Successed!"
    #             resultstr = 3
    #             errstr = json.dumps(status_data, ensure_ascii=False)
    #             UpdateSubPlanCheckResultByHisid(hisid, errstr, errid, errtype, resultstr)
    #
    #             print("参数:", hisid, errstr, errid, errtype, resultstr)
    #             try:
    #                 systemsetting = getModelFileNameAndCurErrLevel()
    #                 systemsetting["info"] = getModelFileTypeErrLevel(systemsetting["fileid"],
    #                                                                  systemsetting["curerrlevel"])
    #                 # 检测图片并返回检测类型、检测state
    #                 print(imgfilenameonly, systemsetting)
    #                 detectImage_sigleresult = DetectImage(imgfilenameonly, systemsetting)
    #             except Exception as e:
    #                 print(e)
    #             stat1 = detectImage_sigleresult.get("state")
    #             # print("stat1:", stat1)
    #             errortype1 = detectImage_sigleresult.get("errortype")
    #             # print("errortype1:", errortype1)
    #             errorimg1 = os.path.basename(imgfilenameonly)
    #             # print("errorimg1:", errorimg1)
    #             print("NVRInfo", NVRInfo)
    #             InsertErrorSigleImage(NVRInfo, errorimg1, errortype1, stat1)
    #     else:
    #         print("start send opt msg:", iitem["ctlopt"])
    #         imgid = iitem["camid"]
    #         watchpoint = iitem["watchpoint"]
    #         NVRInfo = getNVRInfo(imgid)
    #         if NVRInfo is None:
    #             status_data["DownLoadImage"] = "NVR Info empty"
    #             errid = 10001
    #             resultstr = 2
    #             errstr = json.dumps(status_data, ensure_ascii=False)
    #             UpdateSubPlanCheckResultByHisid(hisid, errstr, errid, errtype, resultstr)
    #             return
    #         print("NVRInfo", NVRInfo)
    #         success = capture_camera_image_at_preset(
    #             NVRInfo["ip"],
    #             NVRInfo["port"],
    #             NVRInfo["user"],
    #             NVRInfo["pwd"],
    #             NVRInfo["channel"],  # 通道号
    #             watchpoint,  # 预置点编号
    #             imgfilenameonly,  # 输出文件名
    #             5  # 等待时间（秒）
    #         )
    #         if success == False:
    #             status_data["DownLoadImage"] = "Download Image Failed"
    #         else:
    #             status_data["DownLoadImage"] = "Download Image Successed!"
    #         resultstr = 3
    #         errstr = json.dumps(status_data, ensure_ascii=False)
    #         UpdateSubPlanCheckResultByHisid(hisid, errstr, errid, errtype, resultstr)
    #
    #         print("参数:", hisid, errstr, errid, errtype, resultstr)
    #         try:
    #             systemsetting = getModelFileNameAndCurErrLevel()
    #             systemsetting["info"] = getModelFileTypeErrLevel(systemsetting["fileid"],
    #                                                              systemsetting["curerrlevel"])
    #             # 检测图片并返回检测类型、检测state
    #             print(imgfilenameonly, systemsetting)
    #             detectImage_sigleresult = DetectImage(imgfilenameonly, systemsetting)
    #         except Exception as e:
    #             print(e)
    #         stat1 = detectImage_sigleresult.get("state")
    #         # print("stat1:", stat1)
    #         errortype1 = detectImage_sigleresult.get("errortype")
    #         # print("errortype1:", errortype1)
    #         errorimg1 = os.path.basename(imgfilenameonly)
    #         # print("errorimg1:", errorimg1)
    #         print("NVRInfo", NVRInfo)
    #         InsertErrorSigleImage(NVRInfo, errorimg1, errortype1, stat1)








        #开始检测，并记录结果
        #if iitem["ctlopt"] == 0: #异常缺陷检测
        #
        #    UpdateSubPlanCheckResultByHisid(hisid, errstr, errid, errtype, resultstr)
        #else:#表计读数
        #
        #    UpdateSubPlanCheckResultByHisid(hisid, errstr, errid, errtype, resultstr)
        #status_data["DetectImage"] = "Result"

  # 检测单张图片告警后添加到errorinfo表

# 获取房间下的摄像头列表    2025年8月8日
# 修改更新該方法，多條目檢修區域，房間的時間的重叠和連續2025年10月29日
def getOverhaulArearoom_Cameras(Camera_id):
    # select_maxid_sql = 'select max(id) as maxid from m_overhaularea'
    # select_maxid_result = db.select_db(select_maxid_sql)
    # id = 1
    # 初始化布尔类型摄像头
    OverhaulAreaCameras_bool = False
    OverhaulArea_starttime = ''
    OverhaulArea_endtime = ''
    Overhaulproomresults=None
    # if select_maxid_result[0]['maxid']==id:
    #     Overhaulsql = "select * from m_overhaularea where  id= {}".format(id)
    #     totaldata = db.select_db(Overhaulsql)
    #     print("OverhaulAreaCameras:", totaldata)
    #     for iitem in totaldata:
    #         OverhaulArea_endtime=iitem['endtime']
    #         OverhaulArea_starttime=iitem['starttime']
    #         OverhaulAreaRooms=iitem['roomids'].split(",")
    #         print(OverhaulAreaRooms)
    #         int_room_list = [int(num) for num in OverhaulAreaRooms]
    #         roomids_str= ', '.join(map(str, int_room_list))
    #         selectroomcamerasql="select camera_id from m_camera where  roomid in ({})".format(roomids_str)
    #         totaldata1 = db.select_db(selectroomcamerasql)
    #         print(totaldata1)
    #         for cameraid in totaldata1:
    #             OverhaulAreaCameras.append(cameraid['camera_id'])
    #         print("OverhaulAreaCameras",OverhaulAreaCameras)
    #     return OverhaulAreaCameras,OverhaulArea_starttime,OverhaulArea_endtime
    # else:
    #     return OverhaulAreaCameras, OverhaulArea_starttime, OverhaulArea_endtime
    print("判断该摄像头是否在检修区", Camera_id)
    select_roomid_bycamera_id = 'select roomid from m_camera where camera_id={}'.format(Camera_id)
    select_roomid_result = db.select_db(select_roomid_bycamera_id)
    if select_roomid_result == None or select_roomid_result == '':
        print("room id not found ")
        OverhaulAreaCameras_bool = False
        OverhaulArea_starttime = ''
        OverhaulArea_endtime = ''

    else:
        roomid = select_roomid_result[0]["roomid"]
        Overhaulproomsql = "select * from v_overhaularea where  room_id= {}".format(roomid)
        Overhaulproomresults = db.select_db(Overhaulproomsql)
        if Overhaulproomresults is None or Overhaulproomresults == '':
            OverhaulAreaCameras_bool = False
            OverhaulArea_starttime = ''
            OverhaulArea_endtime = ''
        else:
            OverhaulAreaCameras_bool = True
            print("Overhaulproomresults:", Overhaulproomresults)
            for items in Overhaulproomresults:
                OverhaulArea_endtime = items['merged_end']
                OverhaulArea_starttime = items['merged_start']

    return OverhaulAreaCameras_bool, OverhaulArea_starttime, OverhaulArea_endtime


def InsertErrorSigleImage(NVRInfo,errorimg,errortype,state):
    nvrip=NVRInfo["ip"]
    nvrport=NVRInfo["port"]
    nvruser=NVRInfo["user"]
    nvrpasswd=NVRInfo["pwd"]
    nvrchannel=NVRInfo["channel"]
    print(NVRInfo)
    TableName = "m_errorinfo"
    select_maxid_sql = 'select max(id) as maxid from {}'.format(TableName)
    select_maxid_result = db.select_db(select_maxid_sql)
    id = 0
    nowTime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if select_maxid_result[0]['maxid'] is None:
        id = 1
    else:
        id = int(select_maxid_result[0]['maxid']) + 1
    insert_dic = {
        'id': id,
        'devid': 'bj200100',
        'errdatetime': nowTime,
        'nvrip': nvrip,
        'nvrport': nvrport,
        'nvruser': nvruser,
        'nvrpasswd': nvrpasswd,
        'nvrchannel': nvrchannel,
        'errorimg': errorimg,
        'errortype': errortype,
        'errfrom': 0,
        'revint': 0,
        'revstr': "0",
        'state': state,
        'flag': 0,
        'gifname': '',
        'optflag1': 0,
        'confirm': 0
    }
    db.insertData(TableName, insert_dic)
    return id
def InsertPlanInfoToHis(planid, mgcode):
    TableName = "m_visitationplanhistory"
    select_maxid_sql = 'select max(id) as maxid from {}'.format(TableName)
    select_maxid_result = db.select_db(select_maxid_sql)
    id = 0
    if select_maxid_result[0]['maxid'] is None:
        id = 1
    else:
        id = int(select_maxid_result[0]['maxid']) + 1

    insert_dic = {
        'id': id,
        'taskplanid': planid,
        'taskstarttime': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'taskendtime': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'taskprogress': 0,
        'taskmagicserial': mgcode,
        'errcount': 0,
    }
    db.insertData(TableName, insert_dic)
    return id

def UpdatePlanInfoToHis(planid, mgcode, taskprogress):
    print("UpdatePlanInfoToHis:", mgcode, taskprogress)
    sqlstr = '''
    UPDATE m_visitationplanhistory
        SET 
        taskendtime = '{}',
        taskprogress = {} 
        WHERE 
        taskmagicserial = '{}'
    '''.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S'),taskprogress, mgcode )
    #print("UpdatePlanInfoToHis:", sqlstr)
    db.execute_db(sqlstr)

def UpdatePlanInfoToPlan(planid, val):
    print("UpdatePlanInfoToPlan:", val)
    sqlstr = '''
    UPDATE m_visitationplan
        SET 
        predatetime = '{}',
        curprogress = {} 
        WHERE 
        id = {}
    '''.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S'),val, planid )
    db.execute_db(sqlstr)

def VisitationPlanWorkerThread(mqDetectTask):
    print("VisitationPlanWorkerThread start")
    systemsetting = getModelFileNameAndCurErrLevel()
    systemsetting["info"] = getModelFileTypeErrLevel(systemsetting["fileid"], systemsetting["curerrlevel"])
    type_counts = {str(k): 0 for k in systemsetting["info"].keys()}
    model = YOLO(systemsetting["filename"])
    print("CheckNvrChannelStateThread start over, wait task!")
    while 1:
        try:
            t = mqDetectTask.get(timeout=1)
            print("VisitationPlanWorkerThread task  start: ", t)
            planid = t[0]
            # 获取计划子项信息
            subitemsql = "select * from m_visitationplaninfo where taskplanid = {}".format(planid)
            totaldata = db.select_db(subitemsql)
            print("VisitationPlanWorkerThread subitem:", totaldata)
            mgcode = generate_unique_code()
            print("________1111_________")
            if totaldata is None or len(totaldata) == 0:
                updateTaskPlanPreTimeAndMagicCode(planid,mgcode)
                updateTaskPlanState(planid, 100)
                continue
            print("________2222_________")
            updateTaskPlanPreTimeAndMagicCode(planid, mgcode)
            print("InsertPlanInfoToHis")
            InsertPlanInfoToHis(planid,mgcode)

            loop = 0
            for iitem in totaldata:
                PlanSubItemAction(iitem, mgcode)
                loop = loop + 1
                UpdatePlanInfoToPlan(planid, (loop/len(totaldata))*100)

            UpdatePlanInfoToHis(planid,mgcode,100)
        except Exception as e:
            pass

def udp_server(mqDetectTask,host='0.0.0.0', port=8009):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind((host, port))
        print(f"UDP server up and listening on {host}:{port}")
        TableName = "m_errorinfo"
        while True:
            data, addr = s.recvfrom(1024)  # 缓冲区大小设置为1024字节
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Received {len(data)} bytes from {addr}: {data.decode()}")

            select_maxid_sql = 'select max(id) as maxid from {}'.format(TableName)
            select_maxid_result = db.select_db(select_maxid_sql)
            id = 0
            if select_maxid_result[0]['maxid'] is None:
                id = 1
            else:
                id = int(select_maxid_result[0]['maxid']) + 1
            pd = data.decode().split(",,")
            nowTime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            insert_dic = {
                'id': id,
                'devid': pd[0],
                'errdatetime': nowTime,
                'nvrip': pd[1],
                'nvrport': int(pd[2]),
                'nvruser': pd[3],
                'nvrpasswd': pd[4],
                'nvrchannel': pd[5],
                'errorimg': "",
                'errortype': 0,
                'errfrom': 0,
                'revint': 0,
                'revstr': "0",
                'state': 0,
                'flag': 0,
                'gifname':pd[6],
                'optflag1':0,
                'confirm':0
            }
            db.insertData(TableName, insert_dic)
            # devid = pd[0]
            # nvrip = pd[1]
            # nvrport = int(pd[2])
            # nvruser = pd[3]
            # nvrpasswd = pd[4]
            # nvrchannel = pd[5]
            # print("qDetectTask.put")
            # mqDetectTask.put([id, devid, nvrip, nvrport, nvruser, nvrpasswd, nvrchannel])
def compare_time_parts_with_tolerance(time_a, time_b, tolerance=2):
    # 比较小时和分钟
    if time_a.hour != time_b.hour or time_a.minute != time_b.minute:
        return False

        # 比较秒数，允许有tolerance秒的偏差
    diff = abs(time_a.second - time_b.second)
    return diff <= tolerance
def VisitationPlanWorker(id,mqDetectTask):
    mqDetectTask.put([id])


# def is_within_one_minute(target_time_str):
#     """
#     判断当前时间与设定的时间是否相差1分钟以内。
#
#     :param target_time_str: 设定的时间字符串，格式为 "HH:MM:SS"
#     :return: 如果相差1分钟以内返回 True，否则返回 False
#     """
#     # 获取当前时间
#     now = datetime.now()
#
#     # 将当前时间的时间部分提取出来（虽然这里直接用 now 也行，但为了展示如何处理时间部分）
#     current_time = now.time()  # 实际上不需要单独提取，因为后续会用整个 now
#
#     # 将设定的时间字符串转换为 datetime.time 对象
#     target_time = datetime.strptime(target_time_str, "%H:%M:%S").time()
#     print("时间:",target_time_str)
#     # 为了计算时间差，我们需要将 target_time 与一个任意日期结合
#     # 这里我们使用一个固定的日期，比如 1900-01-01
#     base_date = datetime(2025, 7, 17)
#     target_datetime = datetime.combine(base_date, target_time)
#     time_difference = abs(target_datetime - now)
#     print("time_difference:{%s},type:{%s}", time_difference, type(time_difference))
#     # 判断差值是否小于等于1分钟
#     return time_difference <= timedelta(minutes=1)

# 比较当前时间与设定时间大小
def time_sec_compare(target_time_str):
    """
    将当前时间与设定的时间做比较，返回结果可以为负值

    :param target_time_str: 设定的时间字符串，格式为 "HH:MM:SS"
    :return: 当前时间大于设定时间为正数；当前时间小于设定时间为负数；0：当前时间等于设定时间；
    """
    # 获取当前时间
    now = datetime.now()

    # 计算当前时间从当天午夜开始的秒数
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    current_seconds = (now - start_of_day).total_seconds()

    # 解析目标时间并计算秒数
    target_time = datetime.strptime(target_time_str, "%H:%M:%S").time()
    target_seconds = target_time.hour * 3600 + target_time.minute * 60 + target_time.second

    # 计算最小时间差（考虑跨天情况）
    diff = abs(current_seconds - target_seconds)
    # min_diff = min(diff, 86400 - diff)  # 86400秒=24小时
    return diff

def is_within_one_minute(target_time_str):
    """
    判断当前时间与设定的时间是否相差1分钟以内。

    :param target_time_str: 设定的时间字符串，格式为 "HH:MM:SS"
    :return: 如果相差1分钟以内返回 True，否则返回 False
    """
    # 计算最小时间差（考虑跨天情况）
    diff = abs(time_sec_compare(target_time_str))
    min_diff = min(diff, 86400 - diff)  # 86400秒=24小时

    # 判断差值是否小于等于60秒（1分钟）
    return min_diff <= 30

def VisitationPlanAction(mqDetectTask):
    while True:
        try:
            t = mqDetectTask.get(timeout=3)
            print("VisitationPlanAction:",t)
            if (t[0] == "exit"):
                print("task %d: exit")
                os._exit(0)

        except:
            pass

# 配置调用巡视任务的次数
# planeid:  巡视计划的ID
# count:    设置巡视次数
def set_visitation_plan_count(planid, count):
    """
    设置巡视计划的状态。

    :param planid: 巡视计划的ID
    :param count:  巡视次数
    """
    sqlstr = "UPDATE m_visitationplan SET taskplancount = {} WHERE id = {}".format(count, planid)
    db.execute_db(sqlstr)

'''
time_difference = future_time - now
minutes_difference = time_difference.total_seconds()
'''
#taskplantype（0：间隔周期，1：间隔定时单次，2：每天定时循环,3:立即执行）
#taskplanstate 状态： 0：未使能  1：使能  2：检测中
#taskplanclass： 0：巡视任务   1：检测任务
def VisitationPlanThread(mqDetectTask):
    print("--VisitationPlan Thread Start!--")
    # preVisitationPlanTime = datetime.now()
    sqltotal = "select * from m_visitationplan"
    sqlcheckifrunnow = "select * from m_visitationplan where isrunnow = 1"
    while True:
        #新增判断任务中是否有需要立即执行的任务
        runnowdata = db.select_db(sqlcheckifrunnow)
        if len(runnowdata) <= 0:
            print("runnow plan not found, go as normal.")
        else:
            for index in range(len(runnowdata)):
                id = runnowdata[index]["id"]
                taskplanname    = runnowdata[index]["taskplanname"]
                taskplanclass   = runnowdata[index]["taskplanclass"]    # 立即执行操作，不再判断类型
                taskplantype    = runnowdata[index]["taskplantype"]     # type中不在包含3（立即执行）
                taskplanstate   = runnowdata[index]["taskplanstate"]    # 立即执行操作，不再判断状态
                print(f"runnow plan starting to put to the MQ, id={id}, taskplanname={taskplanname}.")
                VisitationPlanWorker(id, mqDetectTask)
                # 执行完，更新isrunnow标记位为0
                isrunnow_dic                = {}
                isrunnow_dic['isrunnow']    = 0
                wheresql                    = 'id={};'.format(id)
                db.updateData("m_visitationplan", isrunnow_dic, wheresql)
            print("runnow plan all put done, go back.")
            continue

        totaldata = db.select_db(sqltotal)
        if len(totaldata) <= 0:
            time.sleep(10)
            continue
        #print("totaldata:",totaldata)
        for index in range(len(totaldata)):
            id = totaldata[index]["id"]
            taskplanname = totaldata[index]["taskplanname"]
            taskplanclass = totaldata[index]["taskplanclass"]
            taskplantype = totaldata[index]["taskplantype"]
            taskplanstate = totaldata[index]["taskplanstate"]
            taskpanh = totaldata[index]["taskpanh"]
            taskplanf = totaldata[index]["taskplanf"]
            taskplanm = totaldata[index]["taskplanm"]
            predatetime = totaldata[index]["predatetime"]
            taskplancount=totaldata[index]["taskplancount"]
            predatetime1 = None
            if predatetime is not None:
                predatetime1 = predatetime.strftime('%Y-%m-%d %H:%M:%S')
            createtime = totaldata[index]["createtime"].strftime('%Y-%m-%d %H:%M:%S')

            #不使能检测或者正在检测中和巡视任务，则返回
            if taskplanstate == 0 or taskplanstate == 2  or taskplanclass == 0:
                time.sleep(10)
                continue
            #--------- 周期任务 start----------
            if taskplantype == 0:  # 周期任务
                biTime = datetime.strptime(predatetime1, '%Y-%m-%d %H:%M:%S')
                if 0 == taskplancount:  # 第一次执行，则用当前时间与创建时间比较
                    createtime_obj = datetime.strptime(createtime, '%Y-%m-%d %H:%M:%S')
                now = datetime.now()
                time_difference = now - biTime
                sec_difference = time_difference.total_seconds()
                totalsec = taskpanh * 3600 + taskplanf * 60 + taskplanm
                if sec_difference > totalsec:
                    VisitationPlanWorker(id, mqDetectTask)
                    set_visitation_plan_count(id, taskplancount + 1)
            # --------- 周期任务 end----------

            # --------- 单次执行 start----------
            # 元代码
            # if taskplantype == 1:
            #     if predatetime1 is None: #如果不为空，则执行过 就不在执行
            #     if taskplancount==0:
            #         createtime_obj = datetime.strptime(createtime, '%Y-%m-%d %H:%M:%S')
            #         now = datetime.now()
            #         time_difference = now - createtime_obj
            #         sec_difference = time_difference.total_seconds()
            #         totalsec = taskpanh * 3600 + taskplanf * 60 + taskplanm
            #         if sec_difference > totalsec:
            #             VisitationPlanWorker(id, mqDetectTask)
            # 修改代码 2025年7月22日15:18
            if taskplantype == 1:
                # if predatetime1 is None: #如果不为空，则执行过 就不在执行
                if taskplancount == 0:
                    # createtime_obj = datetime.strptime(predatetime1, '%Y-%m-%d %H:%M:%S')
                    # now = datetime.now()

                    #  '''
                    # #时间字符串
                    # #时间格式化匹配
                    # '''
                    # bdtime="00:00:00"
                    # bdtime_format='%H:%M:%S'
                    # bdtime1=datetime.strptime(bdtime,bdtime_format)
                    # time_difference = (datetime.now()).strftime('%H:%M:%S')-bdtime1
                    # sec_difference = time_difference.total_seconds()
                    # totalsec = taskpanh * 3600 + taskplanf * 60 + taskplanm
                    # if sec_difference > totalsec:
                    if 0 < time_sec_compare(str(taskpanh)+":"+str(taskplanf)+":"+str(taskplanm)):
                        VisitationPlanWorker(id, mqDetectTask)
                        set_visitation_plan_count(id, taskplancount + 1)
            # --------- 单次执行 end----------

            # --------- 每天定时循环 start----------
            if taskplantype == 2:
                if is_within_one_minute(str(taskpanh)+":"+str(taskplanf)+":"+str(taskplanm)) is True:
                # if is_within_one_minute(taskpanh + ":" + taskplanf + ":" + taskplanm) is True:
                    print("执行每天定时任务")
                    VisitationPlanWorker(id, mqDetectTask)
                    set_visitation_plan_count(id, taskplancount + 1)
                else:
                    print("没有执行每天定时任务")
            # --------- 每天定时循环 end----------

            # --------- 立即执行 start----------
            if taskplantype == 3:
                print(f"[Attention]This taskplantype {taskplantype} has been removed from current version.")
                # if predatetime1 is None:  # 如果不为空，则执行过 就不在执行
                # print('taskplancount:',taskplancount)
                # if taskplancount == 0:
                #     VisitationPlanWorker(id, mqDetectTask)
                #     set_visitation_plan_count(id, taskplancount + 1)
                # else:
                #     pass
                #     print("没有执行立即任务")

            # --------- 立即执行 end----------

        time.sleep(61)

# 检测任务子项
def DetectImage(imgfilenameonly,systemsetting):
    detectImage_result={
        "errortype":"",
        "state":""
    }
    print("DetectImage:", imgfilenameonly,systemsetting)
    type_counts = {str(k): 0 for k in systemsetting["info"].keys()}# 初始化类型计数器
    model = YOLO(systemsetting["filename"])
    if is_file_readable_with_content(imgfilenameonly):
        with Image.open(imgfilenameonly) as img:
            rgb_img = img.convert("RGB")
            result=model.predict(source=imgfilenameonly)
            # print("result:",result)
            boxes = result[0].boxes.data.cpu().numpy()
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
                    # draw.rectangle([x1, y1, x2, y2],  width=2)
                    draw.text((x1, y1 - 10), f"{class_name} {conf:.2f}", fill=color)
                    # draw.text((x1, y1 - 10), f"{class_name} {conf:.2f}")
                    # print("class_name:", class_name, [x1, y1, x2, y2], color)
                    # 增加对应类别的计数
                    type_counts[str(int(cls))] += 1
            # rgb_img.save(imgfilenameonly, format="JPG")
            rgb_img.save(imgfilenameonly)
            # 确定出现最多的类型
            most_common_type = max(type_counts, key=type_counts.get)
            print(f"Most common type: {most_common_type} with count {type_counts[most_common_type]}")
            state = 0
            if (type_counts[most_common_type] == 0):
                state = 1
            elif (type_counts[most_common_type] >= 3):
                state = 3
            else:
                state = 1
            detectImage_result["state"]=state
            detectImage_result["errortype"]=most_common_type
            # print(detectImage_result)
            return detectImage_result


""" 2025年8月12日 检查并删除检修区域过期数据"""
def _check_and_delete():
    print("--check endtime and currenttime delete!--")
    # preVisitationPlanTime = datetime.now()
    sqltotal = "select * from m_overhaularea"
    while True:
        totaldata = db.select_db(sqltotal)
        if len(totaldata) <= 0:
            time.sleep(10)
            continue
        # print("totaldata:",totaldata)
        for index in range(len(totaldata)):
            id = totaldata[index]["id"]
            endtime_str = totaldata[index]["endtime"]
        # 解析时间字符串，根据实际格式调整
        try:
            # 假设时间格式为: %Y-%m-%d %H:%M:%S
            endtime = datetime.strptime(str(endtime_str), "%Y-%m-%d %H:%M:%S")
            current_time = datetime.now()

            # 检查是否过期
            if current_time > endtime:
                print(f"当前时间 {current_time} 已超过结束时间 {endtime}，执行删除操作")
                db.execute_db("DELETE FROM m_overhaularea WHERE id = {}".format(id))
                print("ID为1的数据已删除")
            else:
                print(f"当前时间 {current_time} 未超过结束时间 {endtime}，不执行操作")
        except ValueError as e:
            print(f"时间格式解析错误: {e}")
        time.sleep(10)


if __name__ == "__main__":


    # imgfilenameonly1 = r"E:\work\detect\proj\DetectServerAndUdpServer\DetectServer\runs\images\fef652b4-e800-479c-9af8-5899f863d808.jpg"
    #
    #
    # detectImage_resulttest=DetectImage(imgfilenameonly1,systemsetting)
    # print(detectImage_resulttest)

    p = Process(target=udp_server, args=(qDetectTask,))
    p.start()
    #pd = Process(target=CheckNvrChannelState, args=(id, pd[0], nvrip, nvrport, nvruser, nvrpasswd, nvrchannel))
    pd = Process(target=VisitationPlanWorkerThread, args=(qDetectTask,))
    pd.start()

    pdplan = Process(target=VisitationPlanThread, args=(qDetectTask,))
    pdplan.start()

    # 增加检修区域因当前时间到期删除记录进程

    overhaularea_time = Process(target=_check_and_delete)
    overhaularea_time.start()
    # pdplana = Process(target=VisitationPlanAction, args=(qDetectTask,))
    # pdplana.start()


    # # 测试
    # print("测试方法")
    # sqltotal ="select * from m_visitationplaninfo where taskplanid = 11"
    # result = db.select_db(sqltotal)
    # print(result[0])
    # mgcode = generate_unique_code()
    # PlanSubItemAction(result[0],mgcode)

