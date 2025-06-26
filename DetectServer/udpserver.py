# udp_server.py
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
from datetime import datetime, timedelta
from PIL import Image,ImageDraw

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
def CheckNvrChannelStateThread(mqDetectTask):
    print("CheckNvrChannelStateThread start")
    systemsetting = getModelFileNameAndCurErrLevel()
    systemsetting["info"] = getModelFileTypeErrLevel(systemsetting["fileid"], systemsetting["curerrlevel"])
    type_counts = {str(k): 0 for k in systemsetting["info"].keys()}
    model = YOLO(systemsetting["filename"])
    print("CheckNvrChannelStateThread start over, wait task!")
    while 1:
        try:
            t = mqDetectTask.get(timeout=1)
            print("task  start")
            id = t[0]
            devid =t[1]
            nvrip=t[2]
            nvrport=t[3]
            nvruser=t[4]
            nvrpasswd=t[5]
            nvrchannel=t[6]

            print(nvrip, nvrport, nvruser, nvrpasswd, nvrchannel)
            exepath = b"C:\\NVRDownloadImg\\NVRDownloadImg.exe"
            script_path = os.path.abspath(__file__)
            script_dir = os.path.dirname(script_path)
            random_str = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
            imgpath = os.path.join(script_dir,"runs", "images", devid+random_str+str(nvrchannel)+".jpeg")
            arguments = [nvrip,str(nvrport), nvruser, nvrpasswd, str(nvrchannel) , imgpath]
            result = subprocess.run([exepath]+arguments , capture_output=True, text=True)
            print("down over",result)

            """
            test alarm !!!!!!!!!!!!
            """
            #imgorgfilename = "1.jpg"
            #imgpath = os.path.join(script_dir, "images", imgorgfilename)

            time.sleep(3)
            waitloop = 0
            while 1:
                if not is_file_readable_with_content(imgpath):
                    time.sleep(1)
                else:
                    break
                waitloop = waitloop + 1
                if waitloop > 10:
                    break
            time.sleep(2)
            state = 1
            if os.path.isfile(imgpath):
                print(imgpath," is found！, start detect!",waitloop)
                t0 = time.time()
                results = None
                img = cv2.imread(imgpath)
                rgb_img = img.convert("RGB")
                results = model.predict(source=img, save=False)  # save predictions as labels
                t1 = time.time()
                print('Done. (%.3fs)' % (t1 - t0))
                result = results[0]
                print("Detect cnt:", len(result.boxes.cls))
                for result in results:
                    boxes = result.boxes.data.cpu().numpy()
                    for box in boxes:
                        x1, y1, x2, y2, conf, cls = box
                        if systemsetting["info"].get(str(int(cls)), 0) == 1:
                            # 获取类别名称（根据你的模型类别定义）
                            class_name = model.names[int(cls)]
                            # class_name = systemsetting["info"]
                            # 在图像上绘制边界框和类别名称
                            draw = ImageDraw.Draw(rgb_img)
                            color = localcolors[int(cls) % len(localcolors)]
                            color = color_mapping[color]
                            draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
                            # draw.rectangle([x1, y1, x2, y2],  width=2)
                            draw.text((x1, y1 - 10), f"{class_name} {conf:.2f}", fill=color)
                            # draw.text((x1, y1 - 10), f"{class_name} {conf:.2f}")
                            # 增加对应类别的计数
                            type_counts[str(int(cls))] += 1
                # if len(result.boxes.cls) != 0:
                #     state = 2
                #     boxes = result.boxes
                #     conflist = boxes.conf.tolist()
                #     clslist = boxes.cls.tolist()
                #     xyxylist = boxes.xyxy.tolist()
                #     strlist = []
                #     isneedAlarm = False
                #     for itm in clslist:
                #         alarmtype = checkErrorTypeAlarm(int(itm))
                #         print(itm, alarmtype)
                #         if (alarmtype > 0):
                #             isneedAlarm = True
                #             break;
                #     if isneedAlarm== True:
                #         state = 3
                #
                #     for xyxyitem in xyxylist:
                #         # xyxyitem = xyxylist[i]
                #         cv2.rectangle(img, (int(xyxyitem[0]), int(xyxyitem[1])), (int(xyxyitem[2]), int(xyxyitem[3])), (0, 0,255), 2)
                #     #output_path = os.path.join(imgpath)
                #     cv2.imwrite(imgpath, img)
                rgb_img.save(imgpath)
            else:
                print("down failed！")
                state = 4
            sql = "update m_errorinfo set errorimg='{}',state={} where id={}".format(devid+random_str+str(nvrchannel)+".jpeg",state,id)
            print("----AlarmInfoHandler sql:",sql)
            db.execute_db(sql)
            print("----AlarmInfoHandler sql over!")
        except Exception as e:
            try:
                if len(str(e)):
                    sql = "update m_errorinfo set errorimg='{}',state={} where id={}".format(
                        devid + random_str + str(nvrchannel) + ".jpeg", 4, id)
                    db.execute_db(sql)
                    print(f"发生了一个错误: {e}")
            except TypeError:
                pass
            pass

"""
直接启动线程检测

def CheckNvrChannelState(id, devid, nvrip, nvrport, nvruser, nvrpasswd, nvrchannel):
    print(nvrip, nvrport, nvruser, nvrpasswd, nvrchannel)
    exepath = b"C:\\NVRDownloadImg\\NVRDownloadImg.exe"
    script_path = os.path.abspath(__file__)
    script_dir = os.path.dirname(script_path)
    random_str = ''.join(random.choices(string.ascii_letters + string.digits, k=6))

    imgorgfilename=devid+random_str+str(nvrchannel)+".jpeg"
    imgpath = os.path.join(script_dir, "images", imgorgfilename)
    arguments = [nvrip,str(nvrport), nvruser, nvrpasswd, str(nvrchannel) , imgpath]
    result = subprocess.run([exepath]+arguments , capture_output=True, text=True)
    print("down over")

    imgorgfilename = "1.jpg"
    imgpath = os.path.join(script_dir, "images", imgorgfilename)

    waitloop = 0
    while 1:
        if not os.path.isfile(imgpath):
            time.sleep(1)
        else:
            waitloop = waitloop + 1
        if waitloop > 3:
            break
    time.sleep(1)
    state = 1
    if os.path.isfile(imgpath):
        print(imgpath," is found！, start detect!")
        model = YOLO("../huobest.pt")
        t0 = time.time()
        results = model.predict(source=imgpath, save=False)  # save predictions as labels
        t1 = time.time()
        print('Done. (%.3fs)' % (t1 - t0))
        result = results[0]
        print("Detect cnt:", len(result.boxes.cls))
        if len(result.boxes.cls) != 0:
            state = 2
            boxes = result.boxes
            conflist = boxes.conf.tolist()
            clslist = boxes.cls.tolist()
            xyxylist = boxes.xyxy.tolist()
            strlist = []
            img = cv2.imread(imgpath)
            for xyxyitem in xyxylist:
                # xyxyitem = xyxylist[i]
                cv2.rectangle(img, (int(xyxyitem[0]), int(xyxyitem[1])), (int(xyxyitem[2]), int(xyxyitem[3])), (0, 0,255), 2)
            #output_path = os.path.join(imgpath)
            cv2.imwrite(imgpath, img)
    else:
        print("down failed！")
    sql = "update m_errorinfo set errorimg='{}',state={} where id={}".format(devid+random_str+str(nvrchannel)+".jpeg",state,id)
    print("----AlarmInfoHandler sql:",sql)
    db.execute_db(sql)
    print("----AlarmInfoHandler sql over!")
"""

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
                'optflag': 0,   # 新增字段，默认为0
                'confirm': 0    # 新增字段，默认为0
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
    print("----------------VisitationPlanWorker--------------------")
    sqltotal = "select * from v_dvrcamlist"
    TableName = "m_errorinfo"
    totaldata = db.select_db(sqltotal)
    for item in totaldata:
        nvrip = item["ip"]
        nvrport = item["port"]
        nvruser = item["user"]
        nvrpwd = item["pwd"]
        nvrchannel = item["channel"]
        if nvrip == None or nvrport == None or \
                nvruser == None or nvrpwd == None or nvrchannel == None:
            continue
        select_maxid_sql = 'select max(id) as maxid from {}'.format(TableName)
        select_maxid_result = db.select_db(select_maxid_sql)
        id = 0
        if select_maxid_result[0]['maxid'] is None:
            id = 1
        else:
            id = int(select_maxid_result[0]['maxid']) + 1
        nowTime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        insert_dic = {
            'id': id,
            'devid': "",
            'errdatetime': nowTime,
            'nvrip': nvrip,
            'nvrport': int(nvrport),
            'nvruser': nvruser,
            'nvrpasswd': nvrpwd,
            'nvrchannel': nvrchannel,
            'errorimg': "",
            'errortype': 0,
            'revint': 0,
            'revstr': "0",
            'state': 0,
            'flag': 0
        }
        db.insertData(TableName, insert_dic)
        print("qDetectTask.put")
        mqDetectTask.put([id, "", nvrip, int(nvrport), nvruser, nvrpwd, nvrchannel])


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


'''
time_difference = future_time - now
minutes_difference = time_difference.total_seconds()
'''
#（0：周期，1：定时单次，2：定时循环,3:立即执行）
#状态： 0：新建  1：正在进行  2：检测完成
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
            predatetime1 = None
            if predatetime is not None:
                predatetime1 = predatetime.strftime('%Y-%m-%d %H:%M:%S')

            #不使能检测或者正在检测中和巡视任务，则返回
            if taskplanstate == 0 or taskplanstate == 1  or taskplanclass == 0:
                time.sleep(10)
                continue
           #如果是立即执行或者时定时单次循环任务，则查看状态为已完成 2 ，则不执行
            if taskplanstate == 2 and taskplantype == 1:
                time.sleep(10)
                continue
                #如果是立即执行的，
            if taskplanstate == 2 and taskplantype == 3:
                time.sleep(10)
                continue
            #周期
            if taskplantype == 0:
                #第一次
                if predatetime1 is None:
                    VisitationPlanWorker(id, mqDetectTask)
                #判断间隔时间是否已到
                now = datetime.now()
                # 将predatetime1类型从string改成datetime格式,修改报错：TypeError: unsupported operand type(s) for -: 'datetime.datetime' and 'str'
                predatetime_obj = datetime.strptime(predatetime1, "%Y-%m-%d %H:%M:%S")
                time_difference = now - predatetime_obj
                sec_difference = time_difference.total_seconds()
                totalsec = taskpanh * 3600 + taskplanf * 60 + taskplanm
                if sec_difference > totalsec:
                    VisitationPlanWorker(id,mqDetectTask)

            elif taskplantype == 1 or taskplantype == 2:  #定时每天
                if is_within_one_minute( taskpanh+":"+taskplanf+":"+taskplanm) is True:
                    VisitationPlanWorker(id, mqDetectTask)

        time.sleep(61)

if __name__ == "__main__":
    p = Process(target=udp_server, args=(qDetectTask,))
    p.start()
    #pd = Process(target=CheckNvrChannelState, args=(id, pd[0], nvrip, nvrport, nvruser, nvrpasswd, nvrchannel))
    pd = Process(target=CheckNvrChannelStateThread, args=(qDetectTask,))
    pd.start()

    pdplan = Process(target=VisitationPlanThread, args=(qDetectTask,))
    pdplan.start()
