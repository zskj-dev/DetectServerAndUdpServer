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

qDetectTask = Queue()

def getSystemConfig():
    sqltotal = "select errortype,errorname,alarmtype  from m_errortype"
    totaldata = db.select_db(sqltotal)
    print("getSystemConfig:",totaldata)
    return totaldata

def checkErrorTypeAlarm(typeval):

    dictinfo = getSystemConfig()
    if len(dictinfo) == 0:
        return 1

    for item in dictinfo:
        if item['errortype'] == typeval:
            return item['alarmtype']

    return 1

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
    model = YOLO("huobest.pt")
    print("CheckNvrChannelStateThread start over, wait task!")
    while 1:
        try:
            #print("get task")
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
                results = model.predict(source=img, save=False)  # save predictions as labels
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
                    isneedAlarm = False
                    for itm in clslist:
                        alarmtype = checkErrorTypeAlarm(int(itm));
                        print(itm, alarmtype)
                        if (alarmtype > 0):
                            isneedAlarm = True
                            break;
                    if isneedAlarm== True:
                        state = 3

                    for xyxyitem in xyxylist:
                        # xyxyitem = xyxylist[i]
                        cv2.rectangle(img, (int(xyxyitem[0]), int(xyxyitem[1])), (int(xyxyitem[2]), int(xyxyitem[3])), (0, 0,255), 2)
                    #output_path = os.path.join(imgpath)
                    cv2.imwrite(imgpath, img)
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
            print(f"Received {len(data)} bytes from {addr}: {data.decode()}")

            select_maxid_sql = 'select max(id) as maxid from {}'.format(TableName)
            select_maxid_result = db.select_db(select_maxid_sql)
            id = 0
            if select_maxid_result[0]['maxid'] is None:
                id = 1
            else:
                id = int(select_maxid_result[0]['maxid']) + 1
            pd = data.decode().split(",,")
            nowTime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
                'revint': 0,
                'revstr': "0",
                'state': 0,
                'flag': 0,
                'gifname':pd[6]
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
        nowTime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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

'''
time_difference = future_time - now
minutes_difference = time_difference.total_seconds()
'''
#（0：周期，1：定时  2.立即）
def VisitationPlanThread(mqDetectTask):
    print("--VisitationPlan Thread Start!--")
    VisitationPlanTActive = 0
    preVisitationPlanTime = datetime.datetime.now()
    sqltotal = "select * from m_visitationplan"
    while True:
        totaldata = db.select_db(sqltotal)
        if len(totaldata) > 0:
            id = totaldata[0]["id"]
            taskplantype = totaldata[0]["taskplantype"]
            taskplanstate = totaldata[0]["taskplanstate"]
            taskpanh = totaldata[0]["taskpanh"]
            taskplanf = totaldata[0]["taskplanf"]
            taskplanm = totaldata[0]["taskplanm"]

            #不使能检测，则返回等待任务使能
            if taskplanstate == 0:
                VisitationPlanTActive = 0
                time.sleep(10)
                continue
            if taskplantype == 0:
                VisitationPlanTActive = 0
                now = datetime.datetime.now()
                time_difference = now - preVisitationPlanTime
                sec_difference = time_difference.total_seconds()
                totalsec = taskpanh * 3600 + taskplanf * 60 + taskplanm
                if sec_difference > totalsec:
                    VisitationPlanWorker(id,mqDetectTask)
                    preVisitationPlanTime = datetime.datetime.now()
            elif  taskplantype == 1:
                VisitationPlanTActive = 0
                now = datetime.datetime.now()
                time1 = datetime.datetime(2024, 11, 11, taskpanh, taskplanf, taskplanm)  #
                if compare_time_parts_with_tolerance(time1, now):
                    VisitationPlanWorker(id,mqDetectTask)
                    preVisitationPlanTime = datetime.datetime.now()
                    time.sleep(4)
            elif  taskplantype == 2:
                if VisitationPlanTActive ==0:
                    preVisitationPlanTime = datetime.datetime.now()
                    VisitationPlanWorker(id,mqDetectTask)
                    VisitationPlanTActive = 1
        time.sleep(1)

if __name__ == "__main__":
    p = Process(target=udp_server, args=(qDetectTask,))
    p.start()
    #pd = Process(target=CheckNvrChannelState, args=(id, pd[0], nvrip, nvrport, nvruser, nvrpasswd, nvrchannel))
    pd = Process(target=CheckNvrChannelStateThread, args=(qDetectTask,))
    pd.start()

    pdplan = Process(target=VisitationPlanThread, args=(qDetectTask,))
    pdplan.start()
