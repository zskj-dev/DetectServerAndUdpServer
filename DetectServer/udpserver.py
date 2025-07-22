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
    systemsetting["filename"] = totaldata[0].get("filename")  # 避免 KeyError
    systemsetting["fileid"] = totaldata[0].get("id")
    sqltotal = "select curerrlevel from m_systemsetting"
    totaldata = db.select_db(sqltotal)
    #print("getSystemConfig:",totaldata[0]["curerrlevel"])
    systemsetting["curerrlevel"] = totaldata[0].get("curerrlevel")
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
    print(totaldata)
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
    print("will send opt msg:",  iitem["ctlopt"])
    #需要控制
    if int(iitem["ctlopt"]) == 1:
        print("start send opt msg:", iitem["ctlopt"])
        isok = sendOptInfoToDev(iitem["optipaddr"], iitem["yiqiid"])
        print("send opt over msg:", isok)
        if isok == False:
            status_data["OptJiQiRen"] = "send command info to JiQiRen failed!"
            errid = 10002
            resultstr = 1
            errstr = json.dumps(status_data,ensure_ascii=False)
            UpdateSubPlanCheckResultByHisid(hisid, errstr, errid, errtype, resultstr)
            return

        imgid = iitem["camid"]
        watchpoint = iitem["watchpoint"]

        NVRInfo = getNVRInfo(imgid)
        if NVRInfo is None:
            status_data["DownLoadImage"]  = "NVR Info empty"
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

        #开始检测，并记录结果
        #if iitem["ctlopt"] == 0: #异常缺陷检测
        #
        #    UpdateSubPlanCheckResultByHisid(hisid, errstr, errid, errtype, resultstr)
        #else:#表计读数
        #
        #    UpdateSubPlanCheckResultByHisid(hisid, errstr, errid, errtype, resultstr)
        #status_data["DetectImage"] = "Result"

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
            if totaldata is None or len(totaldata) == 0:
                print("--VisitationPlanWorkerThread no subitem, will update plan state and continue--")
                updateTaskPlanPreTimeAndMagicCode(planid,mgcode)
                updateTaskPlanState(planid, 100)
                continue;

            print("VisitationPlanWorkerThread totaldata:", totaldata)
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
                'optflag1':0,   # 新增字段，默认为0
                'confirm':0     # 新增字段，默认为0
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


def is_within_one_minute(target_time_str):
    """
    判断当前时间与设定的时间是否相差1分钟以内。

    :param target_time_str: 设定的时间字符串，格式为 "HH:MM:SS"
    :return: 如果相差1分钟以内返回 True，否则返回 False
    """
    # 获取当前时间
    now = datetime.now()

    # 将当前时间的时间部分提取出来（虽然这里直接用 now 也行，但为了展示如何处理时间部分）
    current_time = now.time()  # 实际上不需要单独提取，因为后续会用整个 now

    # 将设定的时间字符串转换为 datetime.time 对象
    target_time = datetime.strptime(target_time_str, "%H:%M:%S").time()

    # 为了计算时间差，我们需要将 target_time 与一个任意日期结合
    # 这里我们使用一个固定的日期，比如 1900-01-01
    base_date = datetime(1900, 1, 1)
    target_datetime = datetime.combine(base_date, target_time)
    time_difference = abs(now - target_datetime)

    # 判断差值是否小于等于1分钟
    return time_difference <= timedelta(minutes=1)

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
    while True:
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
            taskplanecount = totaldata[index]["taskplancount"]
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
                if 0 == taskplanecount: #第一次执行，则用当前时间与创建时间比较
                    createtime_obj = datetime.strptime(createtime, '%Y-%m-%d %H:%M:%S')
                now = datetime.now()
                time_difference = now - biTime
                sec_difference = time_difference.total_seconds()
                totalsec = taskpanh * 3600 + taskplanf * 60 + taskplanm
                if sec_difference > totalsec:
                    VisitationPlanWorker(id,mqDetectTask)
                    set_visitation_plan_count(id, taskplanecount + 1)
            # --------- 周期任务 end----------

            # --------- 单次执行 start----------
            if taskplantype == 1:
                if 0 == taskplanecount: #如果不为空，则执行过 就不在执行
                    createtime_obj = datetime.strptime(createtime, '%Y-%m-%d %H:%M:%S')
                    now = datetime.now()
                    time_difference = now - createtime_obj
                    sec_difference = time_difference.total_seconds()
                    totalsec = taskpanh * 3600 + taskplanf * 60 + taskplanm
                    if sec_difference > totalsec:
                        VisitationPlanWorker(id, mqDetectTask)
                        set_visitation_plan_count(id, taskplanecount + 1)
            # --------- 单次执行 end----------

            # --------- 每天定时循环 start----------
            if taskplantype == 2:
                if is_within_one_minute( taskpanh+":"+taskplanf+":"+taskplanm) is True:
                    VisitationPlanWorker(id, mqDetectTask)
                    set_visitation_plan_count(id, taskplanecount + 1)
            # --------- 每天定时循环 end----------

            # --------- 立即执行 start----------
            if taskplantype == 3:
                if 0 == taskplanecount:  # 如果不为空，则执行过 就不在执行
                    VisitationPlanWorker(id, mqDetectTask)
                    set_visitation_plan_count(id, taskplanecount + 1)
            # --------- 立即执行 end----------
        time.sleep(61)

if __name__ == "__main__":
    p = Process(target=udp_server, args=(qDetectTask,))
    p.start()
    #pd = Process(target=CheckNvrChannelState, args=(id, pd[0], nvrip, nvrport, nvruser, nvrpasswd, nvrchannel))
    pd = Process(target=VisitationPlanWorkerThread, args=(qDetectTask,))
    pd.start()

    pdplan = Process(target=VisitationPlanThread, args=(qDetectTask,))
    pdplan.start()

    # pdplana = Process(target=VisitationPlanAction, args=(qDetectTask,))
    # pdplana.start()
