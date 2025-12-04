from flask import Blueprint, render_template, redirect,request,current_app,send_file
from flask import Flask, render_template, request, jsonify, make_response
from common.mysqloptor import db
from common.reqresult import ReqResult
from werkzeug.utils import secure_filename
import xlwt
import json
import shutil
import time
import datetime
import os
import zipfile
import os.path
from ultralytics import YOLO
import cv2
import random
import string
import csv
from PIL import Image,ImageDraw
import io

import socket  # 下发机器人通知使用
from hk.getimgfromDVRBySDK import *

set_upload_path = 'images'
set_result_path = 'images'

ALLOWED_EXTENSIONS = set(['png', 'jpg', 'JPG', 'PNG', 'bmp'])

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
realtimealarm = Blueprint('RealtimeAlarm',__name__)

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


'''
    2.图片下载预览
'''
@realtimealarm.route('/download/<filename>',methods=["post","get"])
def download_image(filename):

    gifpath = "errorgifs"
    imgpath = "images"
    # 构造文件的完整路径
    basepath = "./runs"
    file_path = ""
    _, file_extension = os.path.splitext(filename)
    print(file_extension)
    if file_extension == ".gif":
        outputpath = os.path.join(basepath, gifpath)
        file_path = os.path.join(outputpath, filename)
    else:
        outputpath = os.path.join(basepath, imgpath)
        file_path = os.path.join(outputpath, filename)
    print(file_path)
    # 检查文件是否存在
    if os.path.exists(file_path):
        # 使用send_file函数返回文件，作为下载响应
        # as_attachment=True 告诉浏览器这是一个应该被下载的文件
        # ceshi
        print("我是测试gif")
        return send_file(file_path, as_attachment=True)
    else:
        # 如果文件不存在，返回404错误
        return "File not found", 404

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1] in ALLOWED_EXTENSIONS
'''
    1.检测
'''
@realtimealarm.route('/detection',methods=["post","get"])
def DetectionImg():
    if request.method == 'POST':
        systemsetting = getModelFileNameAndCurErrLevel()
        systemsetting["info"] = getModelFileTypeErrLevel(systemsetting["fileid"], systemsetting["curerrlevel"])
        type_counts = {str(k): 0 for k in systemsetting["info"].keys()}
        model = YOLO(systemsetting["filename"])
        # data = request.get_data()
        # json_data = json.loads(data)
        f = request.files['file']
        # sss = request.form["identifier"]
        # print(sss)
        # glo.set_value("identifier",sss)
        if not (f and allowed_file(f.filename)):
            return jsonify({"error": 1001, "msg": "File type exception !"})
        # t = f.filename
        # filename_ = t.split('.')[0]
        # user_input = request.form.get("name")
        basepath = "./runs"
        outputpath = os.path.join(basepath, set_upload_path)
        if not os.path.exists(outputpath):
            os.makedirs(outputpath)
        t0 = time.time()
        # 从字节流中打开帧
        with Image.open(io.BytesIO(f.read())) as img:
            rgb_img = img.convert("RGB")
            # print(rgb_img.mode)
            results = model.predict(source=rgb_img, stream=True)
            for result in results:
                boxes = result.boxes.data.cpu().numpy()
                for box in boxes:
                    x1, y1, x2, y2, conf, cls = box
                    if systemsetting["info"].get(str(int(cls)), 0) == 1:
                        # 获取类别名称（根据你的模型类别定义）
                        class_name = model.names[int(cls)]
                        #class_name = systemsetting["info"]
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
                # 文件上传目录地址
                random_str = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
                filenamea = secure_filename(random_str + f.filename)
                upload_path = os.path.join(outputpath, filenamea)
                rgb_img.save(upload_path)
                #img.save(processed_bytes, format="PNG")

        t1 = time.time()
        print('Done. (%.3fs)' % (t1 - t0))

        res = ReqResult()
        res.code = 0
        res.msg = "success"
        res.data = []
        res.filepath = filenamea

        # 确定出现最多的类型
        most_common_type = max(type_counts, key=type_counts.get)
        print(f"Most common type: {most_common_type} with count {type_counts[most_common_type]}")

        item = {
             "cls": most_common_type,
            "clsname":model.names[int(most_common_type)]
        }
        # strlist.append(item)

        res.data = item

        # 检测结果写到的目录
        # cv2.imwrite(os.path.join(basepath, set_result_path, filename_+'_res.jpg'), img)
        return json.dumps(res.__dict__)
    return render_template('upload.html')


'''
    3.获取触发信息最大ID
'''
@realtimealarm.route('/GetCurMsgMaxID', methods=["post"])
def GetCurMsgMaxID():
    print("token",request.form.get("token"))
    token=request.form.get("token")
    current_app.logger.info('GetCurAlarmMaxID   token:{}'.format(token))

    sql = "select max(id) as id from v_errlist where state != 3"
    maxid = db.select_db(sql)
    req = ReqResult()
    if len(maxid) == 0:
        req.code = 1
        req.msg = "获取数据失败"
    else:
        req.data = maxid[0]["id"]
    return json.dumps(req.__dict__, ensure_ascii=False)

'''
    3.1获取告警最大ID
'''
@realtimealarm.route('/GetCurAlarmMaxID', methods=["post"])
def GetCurAlarmMaxID():
    print("token",request.form.get("token"))
    token=request.form.get("token")
    current_app.logger.info('GetCurAlarmMaxID   token:{}'.format(token))

    sql = "select max(id) as id from v_errlist where state = 3"
    maxid = db.select_db(sql)
    req = ReqResult()
    if len(maxid) == 0:
        req.code = 1
        req.msg = "获取数据失败"
    else:
        req.data = maxid[0]["id"]
    return json.dumps(req.__dict__, ensure_ascii=False)


'''
    4.获取实时告警列表
'''
@realtimealarm.route('/GetCurAlarmList', methods=["post"])
def GetCurAlarmList():
    print("token", request.form.get("token"))
    print("pagesize", request.form.get("pagesize"))
    print("pagenum", request.form.get("pagenum"))

    pagesize = request.form.get("pagesize")
    pagenum = request.form.get("pagenum")
    token = request.form.get("token")
    req = ReqResult()
    if pagesize == None or pagenum == None :
        req.code = 1
        req.msg= "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('GetCurAlarmList   token:{},pagesize:{},pagenum:{}'.format(token, pagesize, pagenum))
    return getlist(0, pagesize, pagenum)

'''
    4.1获取实时告警列表
'''
@realtimealarm.route('/GetCurMsgList', methods=["post"])
def GetCurMsgList():

    print("token", request.form.get("token"))
    print("pagesize", request.form.get("pagesize"))
    print("pagenum", request.form.get("pagenum"))

    pagesize = request.form.get("pagesize")
    pagenum = request.form.get("pagenum")
    token = request.form.get("token")
    req = ReqResult()
    if pagesize == None or pagenum == None :
        req.code = 1
        req.msg= "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('GetCurAlarmList   token:{},pagesize:{},pagenum:{}'.format(token, pagesize, pagenum))
    return getlist(1, pagesize, pagenum)

'''
    4.2获取列表
'''
@realtimealarm.route('/GetAllMsgList', methods=["post"])
def GetAllMsgList():

    print("token", request.form.get("token"))
    print("pagesize", request.form.get("pagesize"))
    print("pagenum", request.form.get("pagenum"))

    pagesize = request.form.get("pagesize")
    pagenum = request.form.get("pagenum")
    token = request.form.get("token")
    req = ReqResult()
    if pagesize == None or pagenum == None :
        req.code = 1
        req.msg= "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('GetCurAlarmList   token:{},pagesize:{},pagenum:{}'.format(token, pagesize, pagenum))
    return getlist(3, pagesize, pagenum)

'''
    4.3 获取触发信息数据数据
'''
@realtimealarm.route('/GetAllMsgFlagList', methods=["post"])
def GetAllMsgFlagList():

    print("token", request.form.get("token"))
    print("pagesize", request.form.get("pagesize"))
    print("pagenum", request.form.get("pagenum"))

    pagesize = request.form.get("pagesize")
    pagenum = request.form.get("pagenum")
    token = request.form.get("token")
    req = ReqResult()
    if pagesize == None or pagenum == None :
        req.code = 1
        req.msg= "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('GetAllMsgFlagList   token:{},pagesize:{},pagenum:{}'.format(token, pagesize, pagenum))
    return getlist(4, pagesize, pagenum)


'''
0. 获取没有处理的告警信息
1. 获取告警提示信息（检测后没发现异常的信息）
2. 获取所有确定并标记误报的信息
3. 获取所有告警数据信息
4. 获取所有标记的信息
'''
def getlist(para_type, pagesize, pagenum):
    req = ReqResult()
    sql = ""
    if para_type == 0:
        sql = "select * from v_errlist where optflag1 =0 and confirm =0 and state = 3 ORDER BY id desc limit {},{}".format(
            str((int(pagenum) - 1) * int(pagesize)), str(pagesize))
    elif para_type == 1:
        sql = "select * from v_errlist where state != 3 ORDER BY id desc limit {},{}".format(
            str((int(pagenum) - 1) * int(pagesize)), str(pagesize))
    elif para_type == 2:
        sql = "select * from v_errlist where optflag1 =1 and confirm =1 and state = 3 ORDER BY id desc limit {},{}".format(
            str((int(pagenum) - 1) * int(pagesize)), str(pagesize))
    elif para_type == 3:
        sql = "select * from v_errlist  ORDER BY id desc limit {},{}".format(
            str((int(pagenum) - 1) * int(pagesize)), str(pagesize))
    elif para_type == 4:
        sql = "select * from v_errlist where flag=1 ORDER BY id desc limit {},{}".format(
            str((int(pagenum) - 1) * int(pagesize)), str(pagesize))
    else:
        sql = "select * from v_errlist ORDER BY id desc limit {},{}".format(
            str((int(pagenum) - 1) * int(pagesize)), str(pagesize))

    print("--------getlist sql:",sql)
    listdata = db.select_db(sql)
    print("--------getlist listdatalen:",len(listdata))

    json_list = []

    for i in listdata:
        if i["updatetime"] != None:
            i["updatetime"] = i["updatetime"].strftime("%Y-%m-%d %H:%M:%S")
            json_list.append(i)

    sqltotal = ""  # "select count(*) as cnt from v_errlist where opsts != 20"
    if para_type == 0:
        sqltotal = "select count(*) as cnt from v_errlist where optflag1 =0 and confirm =0 and state = 3"
    elif para_type == 1:
        sqltotal = "select count(*) as cnt from v_errlist where state != 3"
    elif para_type == 2:
        sqltotal = "select count(*) as cnt from v_errlist where optflag1 =1 and confirm =1 and state = 3 "
    elif para_type == 3:
        sqltotal = "select count(*) as cnt from v_errlist"
    elif para_type == 4:
        sqltotal = "select count(*) as cnt from v_errlist where flag=1"
    else:
        sqltotal = "select count(*) as cnt from v_errlist"

    totaldata = db.select_db(sqltotal)
    current_app.logger.info('getlist totaldata:{}'.format(totaldata))
    #print(json_list)
    #ret1 = json.dumps(json_list)
    #print(ret1)

    dateInfo = {}
    dateInfo["datas"] = json_list
    dateInfo["count"] = len(json_list)
    dateInfo["total"] = totaldata[0]["cnt"]
    #req.data = dateInfo
    #if len(listdata) == 0:
    if listdata is None:
        req.code = 1
        req.msg = "获取数据失败"
    else:
        req.data = dateInfo
    return json.dumps(req.__dict__, ensure_ascii=False)
    #return json.dumps(req.__dict__)

'''
    4.4. 标记信息
'''
@realtimealarm.route('/UpdateMsgFlag', methods=["post"])
def UpdateMsgFlag():

    print("token", request.form.get("token"))
    print("id", request.form.get("id"))
    print("flag", request.form.get("flag"))
    id = request.form.get("id")
    flag = request.form.get("flag")
    req = ReqResult()
    if id == None or flag == None :
        req.code = 1
        req.msg= "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('UpdateMsgFlag   id:{},flag:{}'.format(id, flag))
    sql = "update m_errorinfo set flag={} where id={}".format(flag, id)
    db.execute_db(sql)
    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
    5. 获取模型列表
'''


@realtimealarm.route('/GetModelsList', methods=["post"])
def GetModelsList():
    sqltotal = "select id,filename,flag from m_model"
    totaldata = db.select_db(sqltotal)
    print("GetModelsList:", totaldata)

    req = ReqResult()
    req.code = 0
    req.msg = "读取成功"
    req.data = totaldata

    return json.dumps(req.__dict__, ensure_ascii=False)


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
    print("file_size:", file_size)
    # 如果通过了所有检查，则文件是可读的且不为空
    return True


'''
   5.1 添加模型
'''


@realtimealarm.route('/AddModelInfo', methods=["post"])
def AddModelInfo():
    req = ReqResult()
    f = request.files['file']
    if '.' in f.filename and f.filename.rsplit('.', 1)[1] != "pt":
        req.code = 1
        req.msg = "文件后缀名类型异常"
        return json.dumps(req.__dict__, ensure_ascii=False)
    upload_path = os.path.join("./", f.filename)
    f.save(upload_path)
    time.sleep(1)
    if not is_file_readable_with_content(upload_path):
        req.code = 1
        req.msg = "模型文件保存异常"
        return json.dumps(req.__dict__, ensure_ascii=False)
    TableName = "m_model"
    select_maxid_sql = 'select max(id) as maxid from {}'.format(TableName)
    select_maxid_result = db.select_db(select_maxid_sql)
    id = 0
    if select_maxid_result[0]['maxid'] is None:
        id = 1
    else:
        id = int(select_maxid_result[0]['maxid']) + 1
    insert_dic = {
        'id': id,
        'filename': f.filename,
        'flag': 0
    }
    db.insertData(TableName, insert_dic)
    req1 = ReqResult()
    req1.code = 0
    req1.msg = "success"

    return json.dumps(req1.__dict__, ensure_ascii=False)


'''
    5.2 删除模型
'''


@realtimealarm.route('/DeleteModelInfo', methods=["post"])
def DeleteModelInfo():
    print("id", request.form.get("id"))
    id = request.form.get("id")
    req = ReqResult()
    if id == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('DeleteStationInfo   id:{}'.format(id))

    sql = "delete from m_model where id={}".format(id)
    print("----DeleteModelInfo sql:", sql)
    db.execute_db(sql)
    print("----DeleteModelInfo sql over!")

    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
   5.3. 修改模型使用状态
'''


@realtimealarm.route('/UpdateModelUseFlag', methods=["post"])
def UpdateModelUseFlag():
    print("id", request.form.get("id"))
    print("flag", request.form.get("flag"))
    id = request.form.get("id")
    flag = request.form.get("flag")
    req = ReqResult()
    if id == None or flag == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('UpdateMsgFlag   id:{},flag:{}'.format(id, flag))
    sql = "update m_model set flag={} where id={}".format(flag, id)
    db.execute_db(sql)
    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
    6.告警类型以及处理方式列表
'''
@realtimealarm.route('/GetErrorTypeList', methods=["post"])
def GetErrorTypeList():

    print("token", request.form.get("token"))
    print("pagesize", request.form.get("pagesize"))
    print("pagenum", request.form.get("pagenum"))
    id = request.form.get("modelid")
    pagesize = request.form.get("pagesize")
    pagenum = request.form.get("pagenum")
    token = request.form.get("token")
    req = ReqResult()
    if pagesize == None or pagenum == None  or id == None :
        req.code = 1
        req.msg= "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('GetCurAlarmList   token:{},pagesize:{},pagenum:{}'.format(token, pagesize, pagenum))

    sql = "select * from m_modelinfo  where modelid={} ORDER BY errtypeindex desc limit {},{}".format(id,
        str((int(pagenum) - 1) * int(pagesize)), str(pagesize))

    print("--------GetErrorTypeList sql:",sql)
    listdata = db.select_db(sql)
    print("--------GetErrorTypeList listdatalen:",len(listdata))
    sqltotal = "select count(*) as cnt from m_modelinfo where modelid={}".format(id)
    totaldata = db.select_db(sqltotal)
    dateInfo = {}
    dateInfo["datas"] = listdata
    dateInfo["count"] = len(listdata)
    dateInfo["total"] = totaldata[0]["cnt"]

    if len(listdata) == 0:
        req.code = 1
        req.msg = "获取数据失败"
    else:
        req.data = dateInfo
    return json.dumps(req.__dict__, ensure_ascii=False)

'''
    6.1 修改告警类型处理方式
'''
@realtimealarm.route('/ModifyErrorTypeAlarm', methods=["post"])
def ModifyErrorTypeAlarm():
    id = request.form.get("id")
    errtypeindex = request.form.get("errtypeindex")
    errtypename = request.form.get("errtypename")
    errtypelevel = request.form.get("errtypelevel")
    tips = request.form.get("tips")
    sql = "update m_modelinfo set errtypeindex={}, errtypename='{}',  errtypelevel={},tips='{}'  where id={}".format(errtypeindex,errtypename,errtypelevel,tips,id)
    print("----ModifyErrorTypeAlarm sql:", sql)
    db.execute_db(sql)
    print("----ModifyErrorTypeAlarm sql over!")
    req = ReqResult()
    req.code = 0
    req.msg = "修改成功"

    return json.dumps(req.__dict__, ensure_ascii=False)

'''
   6.2 添加告警类型处理方式
'''
@realtimealarm.route('/AddErrorTypeAlarm', methods=["post"])
def AddErrorTypeAlarm():
    modelid = request.form.get("modelid")
    errtypeindex = request.form.get("errtypeindex")
    errtypename = request.form.get("errtypename")
    errtypelevel = request.form.get("errtypelevel")
    tips = request.form.get("tips")
    req = ReqResult()
    if modelid == None or errtypeindex == None or errtypename == None or errtypelevel == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('AddErrorTypeAlarm  modelid:{}  errortype:{},errorname:{},alarmtype:{},tips:{}'.format(modelid,errtypeindex, errtypename,errtypelevel,tips))

    select_maxid_sql = 'select max(id) as maxid from m_modelinfo'
    select_maxid_result = db.select_db(select_maxid_sql)
    id = 0
    if select_maxid_result[0]['maxid'] is None:
        id = 1
    else:
        id = int(select_maxid_result[0]['maxid']) + 1
    insert_dic = {
        'id': id,
        'modelid': modelid,
        'errtypeindex': errtypeindex,
        'errtypename': errtypename,
        'errtypelevel': errtypelevel,
        'tips':tips
    }
    db.insertData("m_modelinfo", insert_dic)

    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)

'''
    6.3 删除告警类型处理方式
'''
@realtimealarm.route('/DeleteErrorTypeAlarm', methods=["post"])
def DeleteErrorTypeAlarm():
    print("errortype", request.form.get("errortype"))
    id = request.form.get("id")
    req = ReqResult()
    if id == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('DeleteErrorTypeAlarm   errortype:{}'.format(id))

    sql = "delete from m_modelinfo where id={}".format( id)
    print("----DeleteErrorTypeAlarm sql:", sql)
    db.execute_db(sql)
    print("----DeleteErrorTypeAlarm sql over!")

    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)

'''
    7. 获取变电站列表
'''
@realtimealarm.route('/GetStationList', methods=["post"])
def GetStationList():
    sqltotal = "select id,stationname,type,position  from m_stationinfo"
    totaldata = db.select_db(sqltotal)
    print("GetStationList:",totaldata)

    req = ReqResult()
    req.code = 0
    req.msg = "读取成功"
    req.data = totaldata

    return json.dumps(req.__dict__, ensure_ascii=False)

'''
   8 获取指定变电站的摄像头列表
'''
@realtimealarm.route('/GetCamListByStation', methods=["post"])
def GetCamListByStation():
    id = request.form.get("id")
    req = ReqResult()
    if id == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('GetCamListByStation   id:{}'.format(id))

    sqltotal = """select aa.camera_id , aa.camera_name , bb.roomname , cc.stationname, cc.position, 
    dd.ip as dvrip, dd.`port` as dvrport , dd.`user` as dvruser, dd.pwd as dvrpwd from m_camera aa 
    LEFT JOIN m_stationroom bb on aa.roomid = bb.id LEFT JOIN m_stationinfo cc on cc.id = bb.stationid
    LEFT JOIN m_dvr dd on dd.dvr_id = aa.dvr_id where cc.id ={} ORDER BY camera_id; """.format(id)
    totaldata = db.select_db(sqltotal)
    print("GetCamListByStation:",totaldata)

    req = ReqResult()
    req.code = 0
    req.msg = "读取成功"
    req.data = totaldata

    return json.dumps(req.__dict__, ensure_ascii=False)

'''
    9. 告警数据下载（get）
'''
@realtimealarm.route('/GetAllMsgInfoFile/<msgtype>', methods=["post","get"])
def GetAllMsgInfoFile(msgtype):
    #msgtype = request.form.get("msgtype")
    msgtype = int(msgtype)
    print(msgtype)
    sqltotal  = ""
    if msgtype == 0:
        sqltotal =  """select * from v_errlist  where state = 3 ORDER BY id; """
    elif msgtype == 1:
        sqltotal = """select * from v_errlist  where state != 3 ORDER BY id; """
    elif msgtype == 2:
        sqltotal = """select * from v_errlist  where flag = 1 ORDER BY id; """
    else:
        sqltotal = """select * from v_errlist  ORDER BY id; """
    print("GetCamListByStation sqltotal:", sqltotal)
    totaldata = db.select_db(sqltotal)
    print("GetCamListByStation:",totaldata)
    random_str = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
    filename = random_str + '_output.csv'
    fipath = os.path.join("./files" , filename)
    if len(totaldata) > 0:
        # 写入CSV文件
        with open(fipath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            ite = totaldata[0]
            keys = ite.keys()
            writer.writerow(keys)
            for row in totaldata:
                writer.writerow(row.values())

    return send_file(fipath, as_attachment=False)

'''
   7.1 添加变电站
'''
@realtimealarm.route('/AddStationInfo', methods=["post"])
def AddStationInfo():
    print("stationname", request.form.get("stationname"))
    print("type", request.form.get("type"))
    print("position", request.form.get("position"))
    stationname = request.form.get("stationname")
    station_type = request.form.get("type")
    position = request.form.get("position")
    req = ReqResult()
    if station_type == None or position == None or stationname == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('AddStationInfo   stationname:{},type:{},position:{}'.format(stationname, station_type, position))

    select_maxid_sql = 'select max(id) as maxid from m_stationinfo'
    select_maxid_result = db.select_db(select_maxid_sql)
    id = 0
    if select_maxid_result[0]['maxid'] is None:
        id = 1
    else:
        id = int(select_maxid_result[0]['maxid']) + 1
    insert_dic = {
        'id': id,
        'stationname': stationname,
        'type': station_type,
        'position': position,
        'optchargeid': 0
    }
    db.insertData("m_stationinfo", insert_dic)

    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)

'''
  7.2 修改变电站
'''
@realtimealarm.route('/ModifyStationInfo', methods=["post"])
def ModifyStationInfo():
    print("id", request.form.get("id"))
    print("stationname", request.form.get("stationname"))
    print("type", request.form.get("type"))
    print("position", request.form.get("position"))

    id = request.form.get("id")
    stationname = request.form.get("stationname")
    type = request.form.get("type")
    position = request.form.get("position")
    req = ReqResult()
    if type == None or position == None or stationname == None or id == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('ModifyStationInfo   id:{}, stationname:{},type:{},position:{}'.format(id, stationname, type,position))

    sql = "update m_stationinfo set stationname='{}',type='{}',position='{}' where id={}".format(
        stationname, type,position, id)
    print("----ModifyStationInfo sql:", sql)
    db.execute_db(sql)
    print("----ModifyStationInfo sql over!")

    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)

'''
    7.3 删除变电站
'''
@realtimealarm.route('/DeleteStationInfo', methods=["post"])
def DeleteStationInfo():
    print("id", request.form.get("id"))
    id = request.form.get("id")
    req = ReqResult()
    if id == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('DeleteStationInfo   id:{}'.format(id))

    sql = "delete from m_stationinfo where id={}".format( id)
    print("----ModifyStationInfo sql:", sql)
    db.execute_db(sql)
    print("----ModifyStationInfo sql over!")

    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
   10. 获取变电站房间列表
'''
@realtimealarm.route('/GetStationRoomList', methods=["post"])
def GetStationRoomList():
    req = ReqResult()
    print("stationid", request.form.get("stationid"))
    stationid = request.form.get("stationid")
    if stationid == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    sqltotal = "select * from m_stationroom  where stationid={}".format(stationid)
    totaldata = db.select_db(sqltotal)
    print("GetStationList:",totaldata)
    req.code = 0
    req.msg = "读取成功"
    req.data = totaldata

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
   10.1 添加变电站房间
'''
@realtimealarm.route('/AddStationRoom', methods=["post"])
def AddStationRoom():
    print("stationid", request.form.get("stationid"))
    print("roomname", request.form.get("roomname"))
    roomname = request.form.get("roomname")
    stationid = request.form.get("stationid")
    req = ReqResult()
    if roomname == None or stationid == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('AddStationRoom   roomname:{},stationid:{}'.format(roomname, stationid))

    select_maxid_sql = 'select max(id) as maxid from m_stationroom'
    select_maxid_result = db.select_db(select_maxid_sql)

    id = 0
    if select_maxid_result[0]['maxid'] is None:
        id = 1
    else:
        id = int(select_maxid_result[0]['maxid']) + 1
    insert_dic = {
        'id': id,
        'stationid': int(stationid),
        'roomname': roomname,
        'optflag': 0
    }
    print("----111111111-----",insert_dic)
    db.insertData("m_stationroom", insert_dic)
    print("---22222222222------")
    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)



'''
  10.2 修改变电站
'''
@realtimealarm.route('/ModifyStationRoomInfo', methods=["post"])
def ModifyStationRoomInfo():
    print("id", request.form.get("id"))
    print("stationid", request.form.get("stationid"))
    print("roomname", request.form.get("roomname"))
    roomname = request.form.get("roomname")
    stationid = request.form.get("stationid")
    id = request.form.get("id")

    req = ReqResult()
    if id == None or stationid == None or roomname == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('ModifyStationRoomInfo   id:{}, stationid:{},roomname:{}'.format(id, stationid, roomname))

    sql = "update m_stationroom set stationid='{}',roomname='{}' where id={}".format(stationid, roomname, id)
    print("----ModifyStationRoomInfo sql:", sql)
    db.execute_db(sql)
    print("----ModifyStationRoomInfo sql over!")

    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)



'''
    10.3 删除变电站
'''
@realtimealarm.route('/DeleteStationRoom', methods=["post"])
def DeleteStationRoom():
    print("id", request.form.get("id"))
    id = request.form.get("id")
    req = ReqResult()
    if id == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('DeleteStationRoom   id:{}'.format(id))

    sql = "delete from m_stationroom where id={}".format( id)
    print("----DeleteStationRoom sql:", sql)
    db.execute_db(sql)
    print("----DeleteStationRoom sql over!")

    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)



'''
11.DVR/NVR信息列表
'''
@realtimealarm.route('/GetStationDVRList', methods=["post"])
def GetStationDVRList():
    req = ReqResult()
    print("stationid", request.form.get("stationid"))
    stationid = request.form.get("stationid")
    if stationid == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('GetStationDVRList   stationid:{}'.format(stationid))
    sqltotal = "select * from m_dvr  where stationid={}".format(stationid)
    totaldata = db.select_db(sqltotal)

    print("total:", totaldata)

    json_list = []
    for i in totaldata:
        i["create_time"] = i["create_time"].strftime("%Y-%m-%d %H:%M:%S")
        json_list.append(i)

    print("GetStationDVRList:",json_list)
    req.code = 0
    req.msg = "读取成功"
    req.data = json_list

    return json.dumps(req.__dict__, ensure_ascii=False)



'''
   11.1 添加DVR/NVR信息
'''
@realtimealarm.route('/AddStationDVR', methods=["post"])
def AddStationDVR():

    dvr_name = request.form.get("dvr_name")
    ip = request.form.get("ip")
    port = request.form.get("port")
    user = request.form.get("user")
    pwd = request.form.get("pwd")
    stationid = request.form.get("stationid")

    req = ReqResult()
    if dvr_name == None or ip == None\
            or port == None or user == None or pwd == None or stationid == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('AddStationDVR   dvr_id:{},dvr_name:{},ip:{},'
                            'port:{},user:{},pwd:{},stationid:{}'
                            .format(0, dvr_name, ip, port, user, pwd, stationid))

    select_maxid_sql = 'select max(dvr_id) as maxid from m_dvr'
    select_maxid_result = db.select_db(select_maxid_sql)

    dvr_id = 0
    if select_maxid_result[0]['maxid'] is None:
        dvr_id = 1
    else:
        dvr_id = int(select_maxid_result[0]['maxid']) + 1
    nowTime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    insert_dic = {
        'dvr_id': dvr_id,
        'dvr_name': dvr_name,
        'ip': ip,
        'port': port,
        'user': user,
        'pwd': pwd,
        'is_need_trans': 0,
        'sts': 1,
        'stationid': stationid,
        'create_time': nowTime
    }
    print("----111111111-----",insert_dic)
    db.insertData("m_dvr", insert_dic)
    print("---22222222222------")
    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)



'''
   11.2 修改DVR/NVR信息
'''
@realtimealarm.route('/ModifyStationDVR', methods=["post"])
def ModifyStationDVR():
    dvr_id = request.form.get("dvr_id")
    dvr_name = request.form.get("dvr_name")
    ip = request.form.get("ip")
    port = request.form.get("port")
    user = request.form.get("user")
    pwd = request.form.get("pwd")
    stationid = request.form.get("stationid")

    req = ReqResult()
    if dvr_id == None or dvr_name == None or ip == None\
            or port == None or user == None or pwd == None or stationid == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('ModifyStationDVR   dvr_id:{},dvr_name:{},ip:{},'
                            'port:{},user:{},pwd:{},stationid:{}'
                            .format(dvr_id, dvr_name, ip, port, user, pwd, stationid))

    sql = "update m_dvr set dvr_name='{}',ip='{}' ,port='{}',user='{}',pwd='{}',stationid='{}' where dvr_id={}".format(
        dvr_name, ip, port, user, pwd, stationid, dvr_id)
    print("----ModifyStationRoomInfo sql:", sql)
    db.execute_db(sql)
    print("----ModifyStationRoomInfo sql over!")

    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)

'''
    11.3 删除DVR/NVR信息
'''
@realtimealarm.route('/DeleteStationDVR', methods=["post"])
def DeleteStationDVR():
    print("dvr_id", request.form.get("dvr_id"))
    dvr_id = request.form.get("dvr_id")
    req = ReqResult()
    if id == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('DeleteStationRoom   dvr_id:{}'.format(dvr_id))

    sql = "delete from m_dvr where dvr_id={}".format( dvr_id)
    print("----DeleteStationDVR sql:", sql)
    db.execute_db(sql)
    print("----DeleteStationDVR sql over!")

    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)

'''
12.0 通过摄像头ID获取DVR/NVR 信息
'''
@realtimealarm.route('/GetStationDVRByCamID', methods=["post"])
def GetStationDVRByCamID():
    req = ReqResult()
    cam_id = request.form.get("cam_id")
    if cam_id == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('GetStationDVRByCamID   cam_id:{}'.format(cam_id))
    sqltotal = "Select bb.ip,bb.`port`, bb.`user`,bb.pwd, aa.channel from m_camera aa LEFT JOIN m_dvr bb on aa.dvr_id = bb.dvr_id where camera_id={}".format(cam_id)
    totaldata = db.select_db(sqltotal)

    print("GetStationDVRByCamID:", totaldata[0])
    req.code = 0
    req.msg = "读取成功"
    req.data = totaldata[0]

    return json.dumps(req.__dict__, ensure_ascii=False)



'''
12.DVR/NVR 摄像头信息列表
'''
@realtimealarm.route('/GetStationDVRCamList', methods=["post"])
def GetStationDVRCamList():
    req = ReqResult()
    print("dvr_id", request.form.get("dvr_id"))
    dvr_id = request.form.get("dvr_id")
    if dvr_id == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('GetStationDVRCamList   stationid:{}'.format(dvr_id))
    sqltotal = "select * from m_camera  where dvr_id={}".format(dvr_id)
    totaldata = db.select_db(sqltotal)
    json_list = []
    for i in totaldata:
        i["create_time"] = i["create_time"].strftime("%Y-%m-%d %H:%M:%S")
        json_list.append(i)

    print("GetStationDVRList:",json_list)
    req.code = 0
    req.msg = "读取成功"
    req.data = json_list

    return json.dumps(req.__dict__, ensure_ascii=False)



'''
   12.1 添加DVR/NVR 摄像头信息
'''
@realtimealarm.route('/AddStationDVRCam', methods=["post"])
def AddStationDVRCam():

    camera_name = request.form.get("camera_name")
    dvr_id = request.form.get("dvr_id")
    channel = request.form.get("channel")
    roomid = request.form.get("roomid")
    realserialnum = request.form.get("realserialnum")

    optipaddr = request.form.get("optipaddr")
    optserial = request.form.get("optserial")

    req = ReqResult()
    if camera_name == None or dvr_id == None\
            or channel == None or roomid == None or realserialnum == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('AddStationDVRCam   camera_name:{},dvr_id:{},channel:{},'
                            'roomid:{},realserialnum:{}'
                            .format(camera_name, dvr_id, channel, roomid, realserialnum))

    select_maxid_sql = 'select max(camera_id) as maxid from m_camera'
    select_maxid_result = db.select_db(select_maxid_sql)

    cam_id = 0
    if select_maxid_result[0]['maxid'] is None:
        cam_id = 1
    else:
        cam_id = int(select_maxid_result[0]['maxid']) + 1
    nowTime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    insert_dic = {
        'camera_id': cam_id,
        'camera_name': camera_name,
        'dvr_id': dvr_id,
        'channel': channel,
        'alert': 1,
        'sts': 1,
        'roomid': roomid,
        'realserialnum': realserialnum,
        'create_time': nowTime,
        'optipaddr': optipaddr,
        'optserial': optserial

    }
    print("----111111111-----",insert_dic)
    db.insertData("m_camera", insert_dic)
    print("---22222222222------")
    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
   12.2 修改DVR/NVR 摄像头信息
'''
@realtimealarm.route('/ModifyStationDVRCam', methods=["post"])
def ModifyStationDVRCam():
    camera_id = request.form.get("camera_id")
    camera_name = request.form.get("camera_name")
    dvr_id = request.form.get("dvr_id")
    channel = request.form.get("channel")
    roomid = request.form.get("roomid")
    realserialnum = request.form.get("realserialnum")
    optipaddr = request.form.get("optipaddr")
    optserial = request.form.get("optserial")
    req = ReqResult()
    if camera_id == None or camera_name == None or dvr_id == None\
            or channel == None or roomid == None or realserialnum == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('AddStationDVRCam   camera_id:{},camera_name:{},dvr_id:{},channel:{},'
                            'roomid:{},realserialnum:{}'
                            .format(camera_id,camera_name, dvr_id, channel, roomid, realserialnum))

    sql = "update m_camera set camera_name='{}',dvr_id='{}' ,channel='{}',roomid='{}',realserialnum='{}',optipaddr='{}',optserial='{}' where camera_id={}".format(
        camera_name, dvr_id, channel, roomid, realserialnum,optipaddr,optserial,  camera_id)
    print("----ModifyStationDVRCam sql:", sql)
    db.execute_db(sql)
    print("----ModifyStationDVRCam sql over!")

    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)

'''
    12.3 删除DVR/NVR摄像头信息
'''
@realtimealarm.route('/DeleteStationDVRCam', methods=["post"])
def DeleteStationDVRCam():
    print("camera_id", request.form.get("camera_id"))
    camera_id = request.form.get("camera_id")
    req = ReqResult()
    if camera_id == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('DeleteStationDVRCam   camera_id:{}'.format(camera_id))

    sql = "delete from m_camera where camera_id={}".format( camera_id)
    print("----DeleteStationDVRCam sql:", sql)
    db.execute_db(sql)
    print("----DeleteStationDVRCam sql over!")

    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)




'''
13.检测设备机器类型列表
'''
@realtimealarm.route('/GetStationDevTypeList', methods=["post"])
def GetStationDevTypeList():
    req = ReqResult()
    current_app.logger.info('GetStationDevTypeList')
    sqltotal = "select * from m_devbaseinfo"
    totaldata = db.select_db(sqltotal)

    print("GetStationDVRList:",totaldata)
    req.code = 0
    req.msg = "读取成功"
    req.data = totaldata

    return json.dumps(req.__dict__, ensure_ascii=False)



'''
   13.1 添加设备机器类型
'''
@realtimealarm.route('/AddStationDevType', methods=["post"])
def AddStationDevType():

    devmodel = request.form.get("devmodel")
    cpu = request.form.get("cpu")
    mem = request.form.get("mem")
    length = request.form.get("length")
    width = request.form.get("width")
    high = request.form.get("high")
    lannum = request.form.get("lannum")
    videotype = request.form.get("videotype")

    req = ReqResult()
    if devmodel == None or cpu == None\
            or mem == None or length == None or width == None \
            or high == None or lannum == None or videotype == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('AddStationDevType   devmodel:{},cpu:{},mem:{},'
                            'length:{},width:{} high:{},lannum:{},videotype:{},'
                            .format(devmodel, cpu, mem, length, width,
                                    high, lannum, videotype))

    select_maxid_sql = 'select max(id) as maxid from m_devbaseinfo'
    select_maxid_result = db.select_db(select_maxid_sql)

    dvr_id = 0
    if select_maxid_result[0]['maxid'] is None:
        dvr_id = 1
    else:
        dvr_id = int(select_maxid_result[0]['maxid']) + 1
    nowTime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    insert_dic = {
        'id': dvr_id,
        'devmodel': devmodel,
        'cpu': cpu,
        'mem': mem,
        'length': length,
        'width': width,
        'high': high,
        'lannum': lannum,
        'videotype': videotype
    }
    print("----111111111-----",insert_dic)
    db.insertData("m_devbaseinfo", insert_dic)
    print("---22222222222------")
    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
   13.2 修改设备机器类型
'''
@realtimealarm.route('/ModifyStationDevType', methods=["post"])
def ModifyStationDevType():
    id = request.form.get("id")
    devmodel = request.form.get("devmodel")
    cpu = request.form.get("cpu")
    mem = request.form.get("mem")
    length = request.form.get("length")
    width = request.form.get("width")
    high = request.form.get("high")
    lannum = request.form.get("lannum")
    videotype = request.form.get("videotype")

    req = ReqResult()
    if devmodel == None or cpu == None or id == None\
            or mem == None or length == None or width == None \
            or high == None or lannum == None or videotype == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('ModifyStationDevType   id:{},devmodel:{},cpu:{},mem:{},'
                            'length:{},width:{} high:{},lannum:{},videotype:{},'
                            .format(id,devmodel, cpu, mem, length, width,
                                    high, lannum, videotype))

    sql = "update m_devbaseinfo set devmodel='{}',cpu='{}' ,mem='{}',length='{}',width='{}',high='{}',lannum='{}',videotype='{}' where id={}".format(
        devmodel, cpu, mem, length, width, high, lannum, videotype,id)
    print("----ModifyStationDevType sql:", sql)
    db.execute_db(sql)
    print("----ModifyStationDevType sql over!")

    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)

'''
    13.3 删除设备机器类型
'''
@realtimealarm.route('/DeleteStationDevType', methods=["post"])
def DeleteStationDevType():
    print("id", request.form.get("id"))
    id = request.form.get("id")
    req = ReqResult()
    if id == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('DeleteStationDevType   id:{}'.format(id))

    sql = "delete from m_devbaseinfo where id={}".format( id)
    print("----DeleteStationDevType sql:", sql)
    db.execute_db(sql)
    print("----DeleteStationDevType sql over!")

    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
14.检测设备列表
'''
@realtimealarm.route('/GetStationDetectDevList', methods=["post"])
def GetStationDetectDevList():
    req = ReqResult()
    current_app.logger.info('GetStationDetectDevList')
    sqltotal = "select * from m_devinfo"
    totaldata = db.select_db(sqltotal)

    print("GetStationDevList:",totaldata)
    req.code = 0
    req.msg = "读取成功"
    req.data = totaldata

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
14.4 检测设备列表
'''
@realtimealarm.route('/GetStationDetectDevListByStationId', methods=["post"])
def GetStationDetectDevListByStationId():
    id = request.form.get("id")
    req = ReqResult()
    if id == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('GetStationDetectDevListByStationId   id:{}'.format(id))

    sqltotal = "select * from m_devrunconfig aa LEFT JOIN m_dvr bb" \
               " on aa.dvrinfoid = bb.dvr_id where bb.stationid = {} group by devid".format(id)
    # sql = "delete from m_camera where camera_id={}".format(camera_id)
    totaldata = db.select_db(sqltotal)
    print("GetStationDetectDevListByStationId:", totaldata)
    json_list = []
    for i in totaldata:
        i["create_time"] = i["create_time"].strftime("%Y-%m-%d %H:%M:%S")
        json_list.append(i)

    req.code = 0
    req.msg = "读取成功"
    req.data = json_list
    # totaldata[0]['create_time'] = totaldata[0]['create_time'].isoformat()
    return json.dumps(req.__dict__, ensure_ascii=False)


'''
   14.1 添加设备
'''
@realtimealarm.route('/AddStationDetectDev', methods=["post"])
def AddStationDetectDev():
    devid = request.form.get("devid")
    address = request.form.get("address")
    modelid = request.form.get("modelid")
    req = ReqResult()
    if modelid == None or address == None or devid == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('AddStationDetectDev   devid:{},address:{},modelid:{},'
                            .format(devid, address, modelid))

    select_maxid_sql = 'select max(id) as maxid from m_devinfo'
    select_maxid_result = db.select_db(select_maxid_sql)

    dvr_id = 0
    if select_maxid_result[0]['maxid'] is None:
        dvr_id = 1
    else:
        dvr_id = int(select_maxid_result[0]['maxid']) + 1

    insert_dic = {
        'id': dvr_id,
        'devid': devid,
        'address': address,
        'modelid': modelid
    }
    print("----111111111-----",insert_dic)
    db.insertData("m_devinfo", insert_dic)
    print("---22222222222------")
    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
   14.2 修改设备
'''
@realtimealarm.route('/ModifyStationDetectDev', methods=["post"])
def ModifyStationDetectDev():
    id = request.form.get("id")
    devid = request.form.get("devid")
    address = request.form.get("address")
    modelid = request.form.get("modelid")

    req = ReqResult()
    if id == None or devid == None or address == None\
            or modelid == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('ModifyStationDetectDev   id:{},devid:{},address:{},modelid:{},'
                            .format(id,devid, address, modelid))

    sql = "update m_devinfo set devid='{}',address='{}' ,modelid='{}' where id={}".format(
        devid, address, modelid,id)
    print("----ModifyStationDetectDev sql:", sql)
    db.execute_db(sql)
    print("----ModifyStationDetectDev sql over!")

    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)

'''
    14.3 删除设备
'''
@realtimealarm.route('/DeleteStationDetectDev', methods=["post"])
def DeleteStationDetectDev():
    print("id", request.form.get("id"))
    id = request.form.get("id")
    req = ReqResult()
    if id == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('DeleteStationDetectDev   id:{}'.format(id))

    sql = "delete from m_devinfo where id={}".format(id)
    print("----DeleteStationDetectDev sql:", sql)
    db.execute_db(sql)
    print("----DeleteStationDetectDev sql over!")

    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)

'''
15.检测设备通道参数列表
'''
@realtimealarm.route('/GetDetectDevChParamsList', methods=["post"])
def GetDetectDevChParamsList():
    req = ReqResult()
    print("devid", request.form.get("devid"))
    devid = request.form.get("devid")
    if devid == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('GetDetectDevChParamsList   devid:{}'.format(devid))
    sqltotal = "select * from m_devrunconfig  where devid='{}' order by devchannel".format(devid)
    totaldata = db.select_db(sqltotal)
    print("GetDetectDevChParamsList:",totaldata)
    req.code = 0
    req.msg = "读取成功"
    req.data = totaldata
    return json.dumps(req.__dict__, ensure_ascii=False)

'''
   15.1添加检测设备通道参数
'''
@realtimealarm.route('/AddDetectDevChParams', methods=["post"])
def AddDetectDevChParams():
    devid = request.form.get("devid")
    devchannel = request.form.get("devchannel")
    dvrinfoid = request.form.get("dvrinfoid")
    dvrchannel = request.form.get("dvrchannel")
    state = request.form.get("state")
    ThredMultiple = request.form.get("ThredMultiple")
    SelThredMultipleEnable = request.form.get("SelThredMultipleEnable")
    LearnValOne = request.form.get("LearnValOne")
    ThredMultipleOne = request.form.get("ThredMultipleOne")
    LearnValTwo = request.form.get("LearnValTwo")
    ThredMultipleTwo = request.form.get("ThredMultipleTwo")
    LearnValThree = request.form.get("LearnValThree")
    ThredMultipleThree = request.form.get("ThredMultipleThree")
    runenable = request.form.get("runenable")

    req = ReqResult()
    if devid == None or devchannel == None  or dvrinfoid == None or dvrchannel == None \
            or state == None or ThredMultiple == None or SelThredMultipleEnable == None \
            or LearnValOne == None or ThredMultipleOne == None or LearnValTwo == None\
            or ThredMultipleTwo == None or LearnValThree == None or ThredMultipleThree == None or runenable == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('AddDetectDevChParams   devid:{},devchannel:{},dvrinfoid:{},dvrchannel:{},'
                            'state:{},ThredMultiple:{},SelThredMultipleEnable:{},LearnValOne:{},'
                            'ThredMultipleOne:{},LearnValTwo:{},ThredMultipleTwo:{},LearnValThree:{},'                            
                            'ThredMultipleThree:{},runenable:{}'
                            .format(devid, devchannel, dvrinfoid, dvrchannel, state,
                                    ThredMultiple, SelThredMultipleEnable, LearnValOne, ThredMultipleOne, LearnValTwo,
                                    ThredMultipleTwo, LearnValThree, ThredMultipleThree, runenable))

    select_maxid_sql = 'select max(id) as maxid from m_devrunconfig'
    select_maxid_result = db.select_db(select_maxid_sql)

    dvr_id = 0
    if select_maxid_result[0]['maxid'] is None:
        dvr_id = 1
    else:
        dvr_id = int(select_maxid_result[0]['maxid']) + 1
    nowTime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    insert_dic = {
        'id': dvr_id,
        'devid': devid,
        'devchannel': devchannel,
        'dvrinfoid': dvrinfoid,
        'dvrchannel': dvrchannel,
        'state': state,
        'ThredMultiple': ThredMultiple,
        'SelThredMultipleEnable': SelThredMultipleEnable,
        'LearnValOne': LearnValOne,
        'ThredMultipleOne': ThredMultipleOne,
        'LearnValTwo': LearnValTwo,
        'ThredMultipleTwo': ThredMultipleTwo,
        'LearnValThree': LearnValThree,
        'ThredMultipleThree': ThredMultipleThree,
        'runenable': runenable
    }
    print("----111111111-----",insert_dic)
    db.insertData("m_devrunconfig", insert_dic)
    print("---22222222222------")
    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)

'''
   15.2 修改检测设备通道参数
'''
@realtimealarm.route('/ModifyDetectDevChParams', methods=["post"])
def ModifyDetectDevChParams():
    id = request.form.get("id")
    devid = request.form.get("devid")
    devchannel = request.form.get("devchannel")
    dvrinfoid = request.form.get("dvrinfoid")
    dvrchannel = request.form.get("dvrchannel")
    state = request.form.get("state")
    ThredMultiple = request.form.get("ThredMultiple")
    SelThredMultipleEnable = request.form.get("SelThredMultipleEnable")
    LearnValOne = request.form.get("LearnValOne")
    ThredMultipleOne = request.form.get("ThredMultipleOne")
    LearnValTwo = request.form.get("LearnValTwo")
    ThredMultipleTwo = request.form.get("ThredMultipleTwo")
    LearnValThree = request.form.get("LearnValThree")
    ThredMultipleThree = request.form.get("ThredMultipleThree")
    runenable = request.form.get("runenable")

    req = ReqResult()
    if id == None or devid == None or devchannel == None  or dvrinfoid == None or dvrchannel == None \
            or state == None or ThredMultiple == None or SelThredMultipleEnable == None \
            or LearnValOne == None or ThredMultipleOne == None or LearnValTwo == None\
            or ThredMultipleTwo == None or LearnValThree == None or ThredMultipleThree == None or runenable == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('ModifyDetectDevChParams   id:{},devid:{},devchannel:{},dvrinfoid:{},dvrchannel:{},'
                            'state:{},ThredMultiple:{},SelThredMultipleEnable:{},LearnValOne:{},'
                            'ThredMultipleOne:{},LearnValTwo:{},ThredMultipleTwo:{},LearnValThree:{},'                            
                            'ThredMultipleThree:{},runenable:{}'
                            .format(id,devid, devchannel, dvrinfoid, dvrchannel, state,
                                    ThredMultiple, SelThredMultipleEnable, LearnValOne, ThredMultipleOne, LearnValTwo,
                                    ThredMultipleTwo, LearnValThree, ThredMultipleThree, runenable))

    sql = "update m_devrunconfig set devid='{}',devchannel='{}' ,dvrinfoid='{}',dvrchannel='{}'," \
          "state='{}',ThredMultiple='{}',SelThredMultipleEnable='{}',LearnValOne='{}',ThredMultipleOne='{}' ," \
          "LearnValTwo='{}',ThredMultipleTwo='{}',LearnValThree='{}' ,ThredMultipleThree='{}' ,runenable='{}'" \
          " where id='{}'"\
        .format( devid, devchannel, dvrinfoid, dvrchannel,
                 state, ThredMultiple,SelThredMultipleEnable, LearnValOne, ThredMultipleOne,
                 LearnValTwo, ThredMultipleTwo, LearnValThree,ThredMultipleThree,runenable, id)

    print("----ModifyStationDVRCam sql:", sql)
    db.execute_db(sql)
    print("----ModifyStationDVRCam sql over!")

    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)

'''
    15.3 删除检测设备通道参数
'''
@realtimealarm.route('/DeleteDetectDevChParams', methods=["post"])
def DeleteDetectDevChParams():
    print("id", request.form.get("id"))
    id = request.form.get("id")
    req = ReqResult()
    if id == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('DeleteDetectDevChParams   id:{}'.format(id))

    sql = "delete from m_devrunconfig where id={}".format( id)
    print("----DeleteDetectDevChParams sql:", sql)
    db.execute_db(sql)
    print("----DeleteDetectDevChParams sql over!")

    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)

'''
16.检测设备温度信息列表
'''
@realtimealarm.route('/GetDetectDevTempList', methods=["post"])
def GetDetectDevTempList():
    req = ReqResult()

    current_app.logger.info('GetDetectDevTempList ')
    sqltotal = "select * from m_devtemp"
    totaldata = db.select_db(sqltotal)

    json_list = []
    for i in totaldata:
        if i["updatetime"] != None:
            i["updatetime"] = i["updatetime"].strftime("%Y-%m-%d %H:%M:%S")
        json_list.append(i)
    print("GetDetectDevTempList:",json_list)
    req.code = 0
    req.msg = "读取成功"
    req.data = json_list
    return json.dumps(req.__dict__, ensure_ascii=False)

'''
17.检测设备温度信息
'''
@realtimealarm.route('/GetDetectDevTempBydevid', methods=["post"])
def GetDetectDevTempBydevid():
    req = ReqResult()
    print("devid", request.form.get("devid"))
    devid = request.form.get("devid")
    if devid == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('GetDetectDevTempBydevid   devid:{}'.format(devid))
    sqltotal = "select * from m_devtemp  where devid='{}'".format(devid)
    totaldata = db.select_db(sqltotal)

    json_list = []
    for i in totaldata:
        if i["updatetime"] != None:
            i["updatetime"] = i["updatetime"].strftime("%Y-%m-%d %H:%M:%S")
        json_list.append(i)

    print("GetDetectDevTempBydevid:",json_list)
    req.code = 0
    req.msg = "读取成功"
    req.data = json_list
    return json.dumps(req.__dict__, ensure_ascii=False)

'''
18.检测设备状态列表
'''
@realtimealarm.route('/GetDetectDevStateList', methods=["post"])
def GetDetectDevStateList():
    req = ReqResult()

    current_app.logger.info('GetDetectDevStateList ')
    sqltotal = "select * from m_devstate"
    totaldata = db.select_db(sqltotal)
    print("GetDetectDevStateList:",totaldata)
    req.code = 0
    req.msg = "读取成功"
    req.data = totaldata
    return json.dumps(req.__dict__, ensure_ascii=False)

'''
19.检测设备状态
'''
@realtimealarm.route('/GetDetectDevStateBydevid', methods=["post"])
def GetDetectDevStateBydevid():
    req = ReqResult()
    print("devid", request.form.get("devid"))
    devid = request.form.get("devid")
    if devid == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('GetDetectDevStateBydevid   devid:{}'.format(devid))
    sqltotal = "select * from m_devstate  where devid='{}'".format(devid)
    totaldata = db.select_db(sqltotal)
    json_list = []
    for i in totaldata:
        if i["updatetime"] != None:
            i["updatetime"] = i["updatetime"].strftime("%Y-%m-%d %H:%M:%S")
        json_list.append(i)
    print("GetDetectDevStateBydevid:",json_list)
    req.code = 0
    req.msg = "读取成功"
    req.data = totaldata
    return json.dumps(req.__dict__, ensure_ascii=False)



'''
20.获取巡视计划表
'''
@realtimealarm.route('/GetVisitationPlan', methods=["post"])
def GetVisitationPlan():
    req = ReqResult()
    current_app.logger.info('GetVisitationPlan ')
    sqltotal = "select * from m_visitationplan"
    totaldata = db.select_db(sqltotal)
    print("GetVisitationPlan:",totaldata)
    req.code = 0
    req.msg = "读取成功"
    req.data = totaldata
    return json.dumps(req.__dict__, ensure_ascii=False)

'''
21.0获取巡视当前执行表
'''
@realtimealarm.route('/GetCurVisitationPlan', methods=["post"])
def GetCurVisitationPlan():
    req = ReqResult()
    current_app.logger.info('GetCurVisitationPlan ')
    sqltotal = "select * from m_visitationplan where taskplanstate=1 and taskplanclass = 1"
    totaldata = db.select_db(sqltotal)
    for i in totaldata:
        if i["predatetime"] is not None:
            i["predatetime"] = i["predatetime"].strftime("%Y-%m-%d %H:%M:%S")
        if i["createtime"] is not None:
            i["createtime"] = i["createtime"].strftime("%Y-%m-%d %H:%M:%S")

    print("GetCurVisitationPlan:", totaldata)
    req.code = 0
    req.msg = "读取成功"
    req.data = totaldata
    return json.dumps(req.__dict__, ensure_ascii=False)



'''
21.01 获取摄像头巡视任务计划
'''
@realtimealarm.route('/GetViewVisitationPlan', methods=["post"])
def GetViewVisitationPlan():
    req = ReqResult()
    current_app.logger.info('GetVisitationPlan ')
    sqltotal = "select * from m_visitationplan where taskplanclass=0"
    totaldata = db.select_db(sqltotal)
    for i in totaldata:
        if i["predatetime"] is not None:
            i["predatetime"] = i["predatetime"].strftime("%Y-%m-%d %H:%M:%S")
        if i["createtime"] is not None:
            i["createtime"] = i["createtime"].strftime("%Y-%m-%d %H:%M:%S")
    print("GetVisitationPlan:", totaldata)
    req.code = 0
    req.msg = "读取成功"
    req.data = totaldata
    return json.dumps(req.__dict__, ensure_ascii=False)

'''
21.02 获取检测任务计划id list
'''
@realtimealarm.route('/GetVisitationPlanIDList', methods=["post"])
def GetVisitationPlanIDList():
    req = ReqResult()
    current_app.logger.info('GetVisitationPlanIDList ')
    sqltotal = "select id,taskplanname from m_visitationplan where taskplanclass=1"
    totaldata = db.select_db(sqltotal)
    # for i in totaldata:
    #     if i["predatetime"] is not None:
    #         i["predatetime"] = i["predatetime"].strftime("%Y-%m-%d %H:%M:%S")
    #     if i["createtime"] is not None:
    #         i["createtime"] = i["createtime"].strftime("%Y-%m-%d %H:%M:%S")
    print("GetVisitationPlanIDList:", totaldata)
    req.code = 0
    req.msg = "读取成功"
    req.data = totaldata
    return json.dumps(req.__dict__, ensure_ascii=False)


'''
21.1 添加巡视计划
'''


@realtimealarm.route('/AddVisitationPlan', methods=["post"])
def AddVisitationPlan():
    req = ReqResult()
    taskplanname = request.form.get("taskplanname")
    taskplanclass = request.form.get("taskplanclass")
    taskplantype = request.form.get("taskplantype")
    taskplanstate = request.form.get("taskplanstate")
    taskpanh = request.form.get("taskpanh")
    taskplanf = request.form.get("taskplanf")
    taskplanm = request.form.get("taskplanm")
    if taskplanname == None or taskplanclass == None or taskplantype == None \
            or taskplanstate == None or taskpanh == None or taskplanf == None or taskplanm == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)

    TableName = "m_visitationplan"
    select_maxid_sql = 'select max(id) as maxid from {}'.format(TableName)
    select_maxid_result = db.select_db(select_maxid_sql)
    id = 0
    if select_maxid_result[0]['maxid'] is None:
        id = 1
    else:
        id = int(select_maxid_result[0]['maxid']) + 1
    insert_dic = {
        'id': id,
        'taskplanname': taskplanname,
        'taskplanclass': taskplanclass,
        'taskplantype': taskplantype,
        'taskplanstate': taskplanstate,
        'taskpanh': taskpanh,
        'taskplanf': taskplanf,
        'taskplanm': taskplanm,
        'curmagicserial': '',
        'curprogress': 0,
        'predatetime': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'createtime': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'taskplancount':0
    }
    print("AddVisitationPlan Inserting data:", insert_dic)
    db.insertData(TableName, insert_dic)
    req1 = ReqResult()
    req1.code = 0
    req1.msg = "success"

    return json.dumps(req1.__dict__, ensure_ascii=False)


@realtimealarm.route('/DeleteVisitationPlan', methods=["post"])
def DeleteVisitationPlan():
    id = request.form.get("id")
    req = ReqResult()
    if id == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('DeleteVisitationPlan   id:{}'.format(id))

    sql = "delete from m_visitationplan where id={}".format(id)
    print("----DeleteVisitationPlan sql:", sql)
    db.execute_db(sql)
    print("----DeleteVisitationPlan sql over!")

    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
21.2 修改巡视计划
'''


@realtimealarm.route('/ModifyVisitationPlan', methods=["post"])
def ModifyVisitationPlan():
    print("taskplantype", request.form.get("taskplantype"))
    print("taskplanstate", request.form.get("taskplanstate"))
    print("taskpanh", request.form.get("taskpanh"))
    print("taskplanf", request.form.get("taskplanf"))
    print("devid", request.form.get("devid"))
    taskplantype = request.form.get("taskplantype")
    taskplanstate = request.form.get("taskplanstate")
    taskpanh = request.form.get("taskpanh")
    taskplanf = request.form.get("taskplanf")
    taskplanm = request.form.get("taskplanm")

    req = ReqResult()
    current_app.logger.info('ModifyVisitationPlan taskplantype:{}，taskplanstate:{}，taskpanh:{}，taskplanf:{}，taskplanm:{}'
                            .format(taskplantype,taskplanstate,taskpanh,taskplanf,taskplanm))

    sql = "update m_visitationplan set taskplantype='{}',taskplanstate='{}' ,taskpanh='{}',taskplanf='{}'," \
          "taskplanm='{}'  where id='{}'"\
        .format( taskplantype, taskplanstate, taskpanh, taskplanf,
                 taskplanm, 1)

    print("----ModifyVisitationPlan sql:", sql)
    db.execute_db(sql)
    print("----ModifyVisitationPlan sql over!")

    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)




@realtimealarm.route('/ModifyVisitationPlanState', methods=["post"])
def ModifyVisitationPlanState():
    id = request.form.get("id")
    taskplanstate = request.form.get("taskplanstate")
    req = ReqResult()
    if id == None or taskplanstate == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)

    current_app.logger.info('ModifyVisitationPlanState id:{}，taskplanstate:{}'
                            .format(id, taskplanstate))

    sql = "update m_visitationplan set taskplanstate={} where id={}" \
        .format(taskplanstate, id)

    print("----ModifyVisitationPlan sql:", sql)
    db.execute_db(sql)
    print("----ModifyVisitationPlan sql over!")

    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
21.4 获取历史巡视计划表
'''


@realtimealarm.route('/GetAllVisitationHistoryPlan', methods=["post"])
def GetAllVisitationHistoryPlan():
    pagesize = request.form.get("pagesize")
    pagenum = request.form.get("pagenum")
    req = ReqResult()
    if pagesize == None or pagenum == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)

    current_app.logger.info('GetVisitationHistoryPlan ')
    sqltotal = "select * from m_visitationplanhistory aa LEFT JOIN m_visitationplan bb " \
               "on aa.taskplanid = bb.id ORDER BY aa.id desc limit {},{}".format(
        str((int(pagenum) - 1) * int(pagesize)), str(pagesize))
    totaldata = db.select_db(sqltotal)

    for i in totaldata:
        if i["taskstarttime"] is not None:
            i["taskstarttime"] = i["taskstarttime"].strftime("%Y-%m-%d %H:%M:%S")
        if i["taskendtime"] is not None:
            i["taskendtime"] = i["taskendtime"].strftime("%Y-%m-%d %H:%M:%S")
        if i["predatetime"] is not None:
            i["predatetime"] = i["predatetime"].strftime("%Y-%m-%d %H:%M:%S")
        if i["createtime"] is not None:
            i["createtime"] = i["createtime"].strftime("%Y-%m-%d %H:%M:%S")

    sqltotalcnt = "select count(*) as cnt from m_visitationplanhistory"
    totaldatacnt = db.select_db(sqltotalcnt)
    dateInfo = {}
    dateInfo["datas"] = totaldata
    dateInfo["count"] = len(totaldata)
    dateInfo["total"] = totaldatacnt[0]["cnt"]
    #req.data = dateInfo
    #if len(listdata) == 0:
    if totaldata is None:
        req.code = 1
        req.msg = "获取数据失败"
    else:
        req.data = dateInfo
    return json.dumps(req.__dict__, ensure_ascii=False)




    print("GetVisitationPlan:", totaldata)
    req.code = 0
    req.msg = "读取成功"
    req.data = totaldata
    return json.dumps(req.__dict__, ensure_ascii=False)








'''
21.5 获取巡视计划详细列表
'''
@realtimealarm.route('/GetVisitationPlanInfoList', methods=["post"])
def GetVisitationPlanInfoList():
    id = request.form.get("id")
    pagesize = request.form.get("pagesize")
    pagenum = request.form.get("pagenum")
    req = ReqResult()
    if id == None or pagesize == None or pagenum == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)

    current_app.logger.info('GetVisitationHistoryPlan ')

    sqltotal = "SELECT *  FROM m_visitationplaninfo aa " \
               "LEFT JOIN m_visitationplan bb ON aa.taskplanid = bb.id " \
               "WHERE bb.id = {} ORDER BY aa.id DESC LIMIT {}, {}" \
        .format(id, str((int(pagenum) - 1) * int(pagesize)), str(pagesize))

    totaldata = db.select_db(sqltotal)

    for i in totaldata:
        if i["predatetime"] is not None:
            i["predatetime"] = i["predatetime"].strftime("%Y-%m-%d %H:%M:%S")
        if i["createtime"] is not None:
            i["createtime"] = i["createtime"].strftime("%Y-%m-%d %H:%M:%S")

    print("GetVisitationPlanInfoList:", totaldata)
    req.code = 0
    req.msg = "读取成功"
    req.data = totaldata
    return json.dumps(req.__dict__, ensure_ascii=False)


'''
21.6 添加巡视计划子项
'''
@realtimealarm.route('/AddVisitationPlanSubInfo', methods=["post"])
def AddVisitationPlanSubInfo():
    camid = request.form.get("camid")
    watchpoint = request.form.get("watchpoint")
    ctlopt = request.form.get("ctlopt")
    optipaddr = request.form.get("optipaddr")
    checktype = request.form.get("checktype")
    taskplanid = request.form.get("taskplanid")

    req = ReqResult()
    if camid == None or watchpoint == None or ctlopt == None \
            or optipaddr == None or checktype == None or taskplanid == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)

    TableName = "m_visitationplaninfo"
    select_maxid_sql = 'select max(id) as maxid from {}'.format(TableName)
    select_maxid_result = db.select_db(select_maxid_sql)
    id = 0
    if select_maxid_result[0]['maxid'] is None:
        id = 1
    else:
        id = int(select_maxid_result[0]['maxid']) + 1
    insert_dic = {
        'id': id,
        'camid': camid,
        'watchpoint': watchpoint,
        'ctlopt': ctlopt,
        'optipaddr': optipaddr,
        'checktype': checktype,
        'taskplanid': taskplanid,
        'yiqiid': 0,
    }
    db.insertData(TableName, insert_dic)
    req1 = ReqResult()
    req1.code = 0
    req1.msg = "success"

    return json.dumps(req1.__dict__, ensure_ascii=False)


'''
    21.7 删除巡视计划子项
'''
@realtimealarm.route('/DeleteVisitationPlanSubInfo', methods=["post"])
def DeleteVisitationPlanSubInfo():
    id = request.form.get("id")
    req = ReqResult()
    if id == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('DeleteStationInfo   id:{}'.format(id))

    sql = "delete from m_visitationplaninfo where id={}".format(id)
    print("----DeleteModelInfo sql:", sql)
    db.execute_db(sql)
    print("----DeleteModelInfo sql over!")

    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
   21.8. 修改巡视计划子项
'''
@realtimealarm.route('/UpdateVisitationPlanSubInfo', methods=["post"])
def UpdateVisitationPlanSubInfo():
    id = request.form.get("id")
    camid = request.form.get("camid")
    watchpoint = request.form.get("watchpoint")
    ctlopt = request.form.get("ctlopt")
    optipaddr = request.form.get("optipaddr")
    checktype = request.form.get("checktype")
    taskplanid = request.form.get("taskplanid")
    req = ReqResult()
    if id == None or camid == None or watchpoint == None or taskplanid == None \
            or ctlopt == None or optipaddr == None or checktype == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('UpdateModelUseFlag   id:{},flag:{}'.format(id, camid))
    sql = "update m_visitationplaninfo " \
          "set camid={},watchpoint={},ctlopt={},optipaddr='{}',checktype={},taskplanid={} where id={}" \
        .format(camid, watchpoint, ctlopt, optipaddr, checktype, taskplanid, id)
    print("UpdateVisitationPlanSubInfo：", sql)
    db.execute_db(sql)
    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)

'''
    21.9  获取巡视检测任务执行子项详情
'''
@realtimealarm.route('/GetVisitationPlanSubInfoById', methods=["post"])
def GetVisitationPlanSubInfoById():
    taskinfoid = request.form.get("taskinfoid")
    req = ReqResult()
    if taskinfoid == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)

    current_app.logger.info('GetVisitationHistoryPlan ')

    sqltotal = "select * from m_visitationplaninfo where id  = {}".format(taskinfoid)

    totaldata = db.select_db(sqltotal)
    print("GetVisitationPlanSubInfoById:", totaldata)
    req.code = 0
    req.msg = "读取成功"
    req.data = totaldata
    return json.dumps(req.__dict__, ensure_ascii=False)



'''
    22. 任务历史
    22.1 获取巡视检测任务执行历史列表
'''
@realtimealarm.route('/GetVisitationPlanHisList', methods=["post"])
def GetVisitationPlanHisList():
    taskid = request.form.get("taskid")
    pagesize = request.form.get("pagesize")
    pagenum = request.form.get("pagenum")
    req = ReqResult()
    if taskid == None or pagesize == None or pagenum == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)

    current_app.logger.info('GetVisitationHistoryPlan ')

    sqltotal = "SELECT *  FROM m_visitationplanhistory " \
               "WHERE taskplanid = {} ORDER BY id DESC LIMIT {}, {}" \
        .format(taskid, str((int(pagenum) - 1) * int(pagesize)), str(pagesize))

    totaldata = db.select_db(sqltotal)
    for i in totaldata:
        i["taskstarttime"] = i["taskstarttime"].strftime("%Y-%m-%d %H:%M:%S")
        i["taskendtime"] = i["taskendtime"].strftime("%Y-%m-%d %H:%M:%S")
    print("GetVisitationPlanHisList:", totaldata)
    sqltotal = "select count(*) as cnt from m_visitationplanhistory WHERE taskplanid = {}".format(taskid)

    cntdata = db.select_db(sqltotal)
    current_app.logger.info('GetVisitationPlanHisList cntdata:{}'.format(cntdata))
    # print(json_list)
    # ret1 = json.dumps(json_list)
    # print(ret1)

    dateInfo = {}
    dateInfo["datas"] = totaldata
    dateInfo["count"] = len(totaldata)
    dateInfo["total"] = cntdata[0]["cnt"]
    req.code = 0
    req.msg = "获取数据成功"
    req.data = dateInfo
    return json.dumps(req.__dict__, ensure_ascii=False)


'''
    22.2 获取巡视检测任务执行子项列表
'''
@realtimealarm.route('/GetVisitationPlanSubHisList', methods=["post"])
def GetVisitationPlanSubHisList():
    taskmagicserial = request.form.get("taskmagicserial")
    pagesize = request.form.get("pagesize")
    pagenum = request.form.get("pagenum")
    req = ReqResult()
    if taskmagicserial == None or pagesize == None or pagenum == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)

    current_app.logger.info('GetVisitationHistoryPlan ')

    sqltotal = "select * from m_visitationplaninfohistory where taskmagicserial " \
               " = '{}' ORDER BY id DESC LIMIT {}, {}" \
        .format(taskmagicserial, str((int(pagenum) - 1) * int(pagesize)), str(pagesize))

    totaldata = db.select_db(sqltotal)
    print("GetVisitationPlanSubHisList:", totaldata)
    req.code = 0
    req.msg = "读取成功"
    req.data = totaldata
    return json.dumps(req.__dict__, ensure_ascii=False)

'''
    23. 获取检修区域列表
'''
@realtimealarm.route('/GetJXRoomList', methods=["post"])
def GetJXRoomList():
    sqltotal = "select * from m_stationroom aa LEFT JOIN m_stationinfo bb on aa.stationid = bb.id where optflag=1"
    totaldata = db.select_db(sqltotal)
    print("GetMaintainList:", totaldata)

    req = ReqResult()
    req.code = 0
    req.msg = "读取成功"
    req.data = totaldata

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
   23.1 修改维护信息 
'''


@realtimealarm.route('/ModifyJXRoomState', methods=["post"])
def ModifyJXRoomState():
    req = ReqResult()
    roomid = request.form.get("roomid")
    flag = request.form.get("flag")
    if roomid == None or flag == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)

    TableName = "m_stationroom"

    sql = "update m_stationroom set optflag={} where id={}" \
        .format(flag, roomid)

    print("----ModifyVisitationPlan sql:", sql)
    db.execute_db(sql)
    print("----ModifyVisitationPlan sql over!")

    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
   24 修改URL信息 
'''


@realtimealarm.route('/ModifyURLInfo', methods=["post"])
def ModifyURLInfo():
    req = ReqResult()
    urlstr = request.form.get("urlstr")

    if urlstr == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)

    sql = "update m_systemsetting set urlstr='{}'" \
        .format(urlstr)

    print("----ModifyVisitationPlan sql:", sql)
    db.execute_db(sql)
    print("----ModifyVisitationPlan sql over!")

    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
    25. 获取告警等级 URL信息
'''


@realtimealarm.route('/GetSystemInfo', methods=["post"])
def GetSystemInfo():
    sqltotal = "select * from m_systemsetting"
    totaldata = db.select_db(sqltotal)
    print("GetSystemInfo:", totaldata)

    req = ReqResult()
    req.code = 0
    req.msg = "读取成功"
    req.data = totaldata

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
   26 修改告警等级接口
'''


@realtimealarm.route('/ModifyAlarmLevel', methods=["post"])
def ModifyAlarmLevel():
    req = ReqResult()
    level = request.form.get("level")

    if level == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)

    sql = "update m_systemsetting set curerrlevel={}" \
        .format(level)

    print("----ModifyAlarmLevel sql:", sql)
    db.execute_db(sql)
    print("----ModifyAlarmLevel sql over!")

    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)


'''



---------------------------------------------------------------------------------------
'''




def GetAlarmInfoFromDB(alarmid):
    sql = "select * from v_alarminfo where id={} ".format(alarmid)
    listdata = db.select_db(sql)

    json_list = []

    for i in listdata:
        i["updatetime"] = i["updatetime"].strftime("%Y-%m-%d %H:%M:%S")
        json_list.append(i)

    req = ReqResult()
    if len(listdata) == 0:
        req.code = 1
        req.msg = "获取数据失败"
    else:
        req.data = json_list[0]

        sql = "select filename from m_result where task_id = {}".format(alarmid)
        listdataimg = db.select_db(sql)

        imglist = []
        for im in listdataimg:
            imglist.append(im["filename"])
        req.data["imgs"] = imglist
    return json.dumps(req.__dict__, ensure_ascii=False)

'''
    3.获取告警详情
'''
@realtimealarm.route('/GetAlarmInfo', methods=["post"])
def GetAlarmInfo():
    print("token", request.form.get("token"))
    print("id", request.form.get("id"))
    alarmid = request.form.get("id")
    token = request.form.get("token")
    current_app.logger.info('GetAlarmInfo   token:{},alarmid:{}'.format(token,alarmid))
    return GetAlarmInfoFromDB(alarmid)

'''
    4.确定告警
'''
@realtimealarm.route('/AlarmInfoHandler', methods=["post"])
def AlarmInfoHandler():
    print("token", request.form.get("token"))
    print("id", request.form.get("id"))
    print("type", request.form.get("type"))
    alarmid = request.form.get("id")
    type = request.form.get("type")
    token = request.form.get("token")
    current_app.logger.info('AlarmInfoHandler   token:{},alarmid:{},type:{}'.format(token,alarmid,type))

    sql = "update m_task set opsts={},errortype={} where task_id={} ".format(20,type,alarmid)
    print("----AlarmInfoHandler sql:",sql)
    db.execute_db(sql)
    print("----AlarmInfoHandler sql over!")

    req = ReqResult()

    return json.dumps(req.__dict__)

'''
    4.1设置告警已读状态
'''
@realtimealarm.route('/AlarmInfoReadHandler', methods=["post"])
def AlarmInfoReadHandler():
    print("token", request.form.get("token"))
    print("id", request.form.get("id"))
    alarmid = request.form.get("id")
    token = request.form.get("token")
    current_app.logger.info('AlarmInfoReadHandler   token:{},alarmid:{}'.format(token,alarmid))
    sql = "update m_task set opsts={} where task_id={} ".format(15, alarmid)
    db.execute_db(sql)

    req = ReqResult()

    return json.dumps(req.__dict__)


'''
    4.2设置告警全部已读状态
'''
@realtimealarm.route('/AllAlarmInfoReadHandler', methods=["post"])
def AllAlarmInfoReadHandler():
    print("token", request.form.get("token"))
    token = request.form.get("token")
    current_app.logger.info('AllAlarmInfoReadHandler   token:{}'.format(token))
    sql = "update m_task set opsts={} where opsts=10 ".format(15)
    db.execute_db(sql)

    req = ReqResult()

    return json.dumps(req.__dict__)


'''
    5.确定全部告警
'''
@realtimealarm.route('/AllAlarmInfoHandler', methods=["post"])
def AllAlarmInfoHandler():
    print("token", request.form.get("token"))
    token=request.form.get("token")
    current_app.logger.info('AllAlarmInfoHandler   token:{}'.format(token))
    sql = "update m_task set opsts={} where opsts != 20 ".format(20)
    db.execute_db(sql)

    req = ReqResult()

    return json.dumps(req.__dict__)


def get_zip_file(input_path, result):
    files = os.listdir(input_path)
    for file in files:
        if os.path.isdir(input_path + '/' + file):
            get_zip_file(input_path + '/' + file, result)
        else:
            result.append(input_path + '/' + file)
def zip_file_path(input_path, output_path, output_name):
    f = zipfile.ZipFile(output_path + '/' + output_name, 'w', zipfile.ZIP_DEFLATED)
    filelists = []
    get_zip_file(input_path, filelists)
    for file in filelists:
        f.write(file)
    # 调用了close方法才会保证完成压缩
    f.close()
    return output_path + r"/" + output_name

'''
    6.告警导出
'''
@realtimealarm.route('/GetAlarmInfoFile', methods=["post"])
def GetAlarmInfoFile():
    print("token", request.form.get("token"))
    print("id", request.form.get("id"))
    alarmid = request.form.get("id")
    token = request.form.get("token")
    current_app.logger.info('GetAlarmInfoFile   token:{},alarmid:{}'.format(token,alarmid))
    strinfo = GetAlarmInfoFromDB(alarmid)
    print("strinfo:",strinfo)
    objinfo = json.loads(strinfo)
    tmpdir = '{}-{}-{}'.format(alarmid,time.strftime('%Y-%m-%d-%H-%M-%S'), token)
    tmppath = './tmpfiles/'+tmpdir
    print("--tmppath:",tmppath)
    os.mkdir(tmppath)
    f = None
    try:
        f = open('{}/info.txt'.format(tmppath), 'w')
        f.write(strinfo)
    finally:
        if f:
            f.close()

    imgcnt = 0
    print(objinfo, type(objinfo))
    for imgfile in objinfo["data"]["imgs"]:
        if os.path.isfile(imgfile) :
            shutil.copy(imgfile, tmppath+"/{}.bmp".format(imgcnt))
            imgcnt += 1

    hisvideo = objinfo["data"]["hisvideo"]
    if os.path.isfile(hisvideo):
        shutil.copy(hisvideo, tmppath + "/error.mp4")

    zipfilea = zip_file_path(tmppath, "./tmpfiles", tmpdir+".zip")
    req = ReqResult()
    req.data = "./tmpfiles"+"/"+tmpdir+".zip"

    shutil.rmtree(tmppath)

    return json.dumps(req.__dict__)


'''
    7.获取变电站列表
'''
@realtimealarm.route('/GetStationList11', methods=["post"])
def GetStationList11():
    print("token", request.form.get("token"))
    token=request.form.get("token")
    current_app.logger.info('GetStationList   token:{}'.format(token))

    sql = "select id, stationname as station from m_stationinfo"
    listdata = db.select_db(sql)
    print(listdata)
    req = ReqResult()
    if len(listdata) == 0:
        req.code = 1
        req.msg = "获取数据失败"
    else:
        req.data = listdata
        # print(listdata)

    return json.dumps(req.__dict__)

'''
    8.获取站内摄像头信息
'''
@realtimealarm.route('/GetStationCamList11', methods=["post"])
def GetStationCamList11():
    print("token", request.form.get("token"))
    print("stationid", request.form.get("stationid"))
    stationid = request.form.get("stationid")
    token = request.form.get("token")
    current_app.logger.info('GetStationCamList   token:{},stationid:{}'.format( token, stationid))

    sql = "select bb.camera_id as id, bb.camera_name as cam from m_stationroom aa LEFT JOIN m_camera  bb on aa.id = bb.roomid where aa.stationid={}".format(stationid)
    listdata = db.select_db(sql)
    print(listdata)
    req = ReqResult()
    if len(listdata) == 0:
        req.code = 1
        req.msg = "获取数据失败"
    else:
        req.data = listdata

    return json.dumps(req.__dict__)

'''
"token": "111111111111111",
“starttime”:”2020-06-06 06:06:06”,
“endtime”:”2020-06-06 06:10:06”,
“stationid”：“1”，
“camid”:”11”
'''
'''
    9.手动创建检测任务
'''
@realtimealarm.route('/CreateDetectTask', methods=["post"])
def CreateDetectTask():
    req = ReqResult()
    return json.dumps(req.__dict__)


#########################################################################################
#########################################################################################
#########################################################################################
'''

    10.获取异常分类列表

'''
@realtimealarm.route('/GetExceptClassList', methods=['post'])
def GetExceptClassList():

    print("token", request.form.get("token"))
    token = request.form.get("token")
    current_app.logger.info('GetExceptClassList   token:{},'.format(token))
    TableName = 'm_taskalarm'
    sql = "select id,alarmtype from {} ".format(TableName)
    listdata = db.select_db(sql)
    print(listdata)
    req = ReqResult()
    if len(listdata) == 0:
        req.code = 1
        req.msg = "获取数据失败"
    else:
        req.data = listdata

    return json.dumps(req.__dict__)

'''
    11.增加异常分类列表

'''

@realtimealarm.route('/AddExcept', methods=['post'])
def AddExcept():

    print("token", request.form.get("token"))
    print("alarmtype", request.form.get("alarmtype"))  # 新增的异常名称

    token = request.form.get("token")
    alarmtype = request.form.get('alarmtype')
    current_app.logger.info('AddExceptClassList   token:{}, alarmtype:{}'.format(token, alarmtype))

    TableName = 'm_taskalarm'
    select_alarmtype_sql = "select alarmtype from m_taskalarm where alarmtype='{}';".format(alarmtype)
    select_alarmtype_data = db.select_db(select_alarmtype_sql)

    req = ReqResult()
    # 如果存在已经插入的alarmtype字段，则直接返回插入失败
    if len(select_alarmtype_data) != 0:
        req.code = 1
        req.msg = "数据插入失败"
    else:
        # 获取最大id，然后再＋1
        max_id_sql = "select max(id) as id from {};".format(TableName)
        print(max_id_sql)
        max_id = db.select_db(max_id_sql)[0]["id"]  # 最大id
        print(max_id)

        alarmtype_dic = {}
        alarmtype_dic['id'] = max_id + 1
        alarmtype_dic['alarmtype'] = alarmtype   # 传递值的方式--->  {'id':max_id+1,'alarmtype':alarmtype}
        print(alarmtype_dic)
        # 插入
        insert_alarmtype = db.insertData(TableName, alarmtype_dic)
        print(insert_alarmtype)
        # # 返回全部alarmtype列表
        # select_alarmtype_list_sql = "select id,alarmtype from m_taskalarm "
        # select_alarmtype_list = db.select_db(select_alarmtype_list_sql)
        # req.data = select_alarmtype_list

    return json.dumps(req.__dict__)


'''
    12.异常分类列表修改
        AlterExceptClassList
'''

@realtimealarm.route('/AlterExceptClassList', methods=['post'])

def AlterExceptClassList():
    # print('token', request.form.get('token'))
    token = request.form.get('token')
    id = request.form.get('id')
    alarmtype = request.form.get('alarmtype')
    current_app.logger.info('AlterExceptClassList   token:{}, id:{},alarmtype:{}'.format(token,id,alarmtype))

    # 接收参数
    TableName = 'm_taskalarm'

    # 判断id是否存在,存在则执行

    select_id_sql = "select id from {} WHERE id='{}';".format(TableName, id)
    print(select_id_sql)
    select_id = db.select_db(select_id_sql)
    print(select_id)
    req = ReqResult()
    if len(select_id) == 0:
        req.code = 1
        req.msg = "数据修改失败"
    else:
        wheresql = 'id={};'.format(id)
        new_alarmtype_dic = {}  # 需要id和alarmtype组合成一个字典,最少两个key
        new_alarmtype_dic['id'] = id
        new_alarmtype_dic['alarmtype'] = alarmtype
        db.updateData(TableName, new_alarmtype_dic, wheresql)
    return json.dumps(req.__dict__)

'''以下的是传递报警信息'''
# def AlterExceptClassList():
#     # print('token', request.form.get('token'))
#     token = request.form.get('token')
#     current_app.logger.info('AlterExceptClassList   token:{}'.format(token))
#
#     # 接收参数
#     TableName = 'm_taskalarm'
#     old_alarmtype = request.form.get('old_alarmtype')
#     new_alarmtype = request.form.get('new_alarmtype')
#     # print('old-->{},new-->{}'.format(old_alarmtype,new_alarmtype))
#     select_old_alarmtype_sql = "select id,alarmtype from {} WHERE alarmtype='{}';".format(TableName, old_alarmtype)
#     # print(select_old_alarmtype_sql)
#     select_old_alarmtype = db.select_db(select_old_alarmtype_sql)
#     # print(select_old_alarmtype)
#     req = ReqResult()
#
#     # 校验参数
#     if len(select_old_alarmtype) == 0:  # 查询不到
#         req.code = 1
#         req.msg = "数据修改失败"
#     else:
#         # 获取 old_alarmtype id,并且把该id对应的alarmtype修改
#         new_alarmtype_dic = {}
#         new_alarmtype_dic['id'] = select_old_alarmtype[0]['id']
#         new_alarmtype_dic['alarmtype'] = new_alarmtype
#         print(new_alarmtype_dic)
#         wheresql = 'id={};'.format(select_old_alarmtype[0]['id'])
#         print(wheresql)
#         db.updateData(TableName, new_alarmtype_dic, wheresql)
#         req.code = 0
#         req.msg = "数据修改成功"
#         sql = "select id,alarmtype from m_taskalarm "
#         listdata = db.select_db(sql)
#         req.data = listdata
#     # 返回Json
#     return json.dumps(req.__dict__)


'''
    13. 设置异常警告分类
        SetExcepAlarmClass

'''

@realtimealarm.route('/SetExcepAlarmClass', methods=['post'])
def SetExcepAlarmClass():
    ''''
    任务id只能有一个，错误id和任务id一一对应,当遇到同一个task_id,则更新error_id;
    '''
    token = request.form.get('token')
    task_id = request.form.get('task_id')
    error_id = request.form.get('error_id')
    current_app.logger.info('SetExcepAlarmClass   token:{},task_id:{},error_id:{}'.format(token, task_id, error_id))
    req = ReqResult()


    TableName = 'm_taskalarmtype'

    nowTime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ''' 判断task_id是否存在,存在则更新errorid,不存在则insert '''
    select_taskid_sql = 'select task_id from {} WHERE task_id="{}"'.format(TableName, task_id)
    select_result = db.select_db(select_taskid_sql)
    select_maxid_sql = 'select max(id) as maxid from {} WHERE id'.format(TableName)
    select_maxid_result = db.select_db(select_maxid_sql)

    print(select_result)
    print(select_maxid_result)

    if len(select_result) == 0:  # 查不到,则插入
        if select_maxid_result[0]['maxid'] ==None:
            select_maxid_result[0]['maxid'] = 0

        insert_dic = {
            'id':select_maxid_result[0]['maxid']+1,
            'task_id': task_id,
            'errorid': error_id,
            'optoruid': '0',
            # 'updatetime': nowTime
        }
        db.insertData(TableName, insert_dic)
        req.code = 0
        req.msg = "插入成功!"
    else:
        up_dic = {
            # 'id': select_maxid_result[0]['maxid'] + 1,
            # 'task_id': task_id,
            'errorid': error_id,
            'optoruid': '0',
            # 'updatetime': nowTime
        }
        # 下面语句要用双引号,单引号报错
        wheresql = "task_id={};".format(task_id)
        db.updateData(TableName, up_dic, wheresql)
        req.code = 0
        req.msg = "更新成功!"
    # select_id_sql = "select count(id) as id_num from {} WHERE id".format(TableName)
    # select_id_num = db.select_db(select_id_sql)
    # print(select_id_num[0]['id_num'])
    # if select_id_num[0]['id_num'] == 0:
    #
    #     insert_dic = {
    #         'id': select_id_num[0]['id_num'],
    #         'task_id': task_id,
    #         'errorid': error_id,
    #         'optoruid': '0',
    #         'updatetime': upTime
    #     }
    #
    #     print(insert_dic)
    #     db.insertData(TableName,insert_dic)
    #
    # else:  # task_id 存在,则继续插入错误id
    #     select_repeat_taskid_sql = "select task_id  from {} WHERE task_id='{}'".format(TableName, task_id)
    #     # select_repeat_taskid = db.select_db(select_repeat_taskid_sql)[0]['task_id']
    #     select_repeat_taskid = db.select_db(select_repeat_taskid_sql)
    #     # 查不到则插入
    #     if len(select_repeat_taskid) == 0:
    #         print(select_repeat_taskid)
    #         insert_dic = {
    #             'id': select_id_num[0]['id_num'],
    #             'task_id': task_id,
    #             'errorid': error_id,
    #             'optoruid': '0',
    #             'updatetime': upTime
    #         }
    #
    #         db.insertData(TableName, insert_dic)
    #
    #         req.code = 0
    #         req.msg = "成功!"
    #
    #     else:
    #         wheresql = 'id={};'.format(select_id_num[0]['id_num'])
    #         up_dic = {
    #             'id': select_id_num[0]['id_num'],
    #             'task_id': task_id,
    #             'errorid': error_id,
    #             'optoruid': '0',
    #             'updatetime': upTime
    #         }
    #         db.updateData(TableName, up_dic, wheresql)
    #
    #         req.code = 0
    #         req.msg = "更新成功!"
    #
    # return json.dumps(req.__dict__)

    '''
    下面代码将会把摄像头异常的找到,之后把m_camera表的sts修改为0,0为该设备异常
    sql 中  m_taskalarmtype.errorid = 2   2默认为摄像头异常,字段可以在m_taskalarm表里查看
    '''
    # 查找出异常摄像头的camera_id和sts
    select_except_cameraId = 'select m_camera.camera_id, m_camera.sts from m_taskalarm left join m_taskalarmtype on m_taskalarm.id = m_taskalarmtype.errorid left join m_task on m_taskalarmtype.task_id = m_task.task_id left join m_camera on m_task.camera_id = m_camera.camera_id where m_taskalarmtype.errorid = 2 group by m_camera.camera_id, m_camera.sts'
    select_result2 = db.select_db(select_except_cameraId)
    # up_m_camera_sts = ''

    # 下面语句要用双引号,单引号报错
    TableName = 'm_camera'
    if all([select_result2, ]):
        for l in select_result2:
            wheresql = "camera_id={};".format(l['camera_id'])
            up_dic = {
                'camera_id': '{}'.format(l['camera_id']),
                'sts': '0',
            }
            db.updateData(TableName, up_dic, wheresql)


    return json.dumps(req.__dict__)

'''

    14.各种异常数据统计
    VariousExceptAlarmStatistics

'''

@realtimealarm.route('/VariousExceptAlarmStatistics', methods=['post'])
def VariousExceptAlarmStatistics():

    # print("token", request.form.get("token"))

    token = request.form.get("token")
    starttime = request.form.get("starttime")
    endtime = request.form.get("endtime")
    stationid = request.form.get("stationid")
    current_app.logger.info('VariousExceptAlarmStatistics   token:{},stationid:{}'.format(token, stationid))

    req = ReqResult()
    # 当没有开始时间时,直接获取失败
    if not all([starttime,]):
        req.code = 1
        req.msg = "数据为空"
    else:
        # 如果截止时间没有传递,默认当前时间
        if not all([endtime,]):
            nowTime = str(datetime.datetime.now())
            time_list = nowTime.split(' ')
            endtime = time_list[0]

        if all([stationid,]):
            # 执行sql
            select_sql1 = 'select m_taskalarm.id, m_taskalarm.alarmtype, IFNULL(!count(*),0) as alarmcount from m_taskalarm left join m_taskalarmtype on m_taskalarm.id = m_taskalarmtype.errorid left join m_task on m_taskalarmtype.task_id = m_task.task_id group by m_taskalarm.id, m_taskalarm.alarmtype;'

            select_result1 = db.select_db(select_sql1)
            select_sql2 = 'select m_taskalarm.id,m_taskalarm.alarmtype,count(*) as alarmcount from m_taskalarm left join m_taskalarmtype on m_taskalarm.id = m_taskalarmtype.errorid left join m_task on m_taskalarmtype.task_id = m_task.task_id left join m_camera on m_task.camera_id = m_camera.camera_id left join m_stationroom on m_stationroom.id = m_camera.roomid where  m_stationroom.stationid = {} and m_task.create_time between "{}" and "{}" group by m_taskalarm.id, m_taskalarm.alarmtype;'.format(stationid,starttime,endtime)
            select_result2 = db.select_db(select_sql2)

            for res2  in select_result2:
                for res1 in select_result2:
                    if res2['id'] == res1['id']:
                        select_result1[int(res2['id'])-1] = res2

            if len(select_result1) == 0:
                req.code = 1
                req.msg = "数据为空"
            else:
                req.data = select_result1
        else:
            select_sql1 = 'select m_taskalarm.id, m_taskalarm.alarmtype, IFNULL(!count(*),0) as alarmcount from m_taskalarm left join m_taskalarmtype on m_taskalarm.id = m_taskalarmtype.errorid left join m_task on m_taskalarmtype.task_id = m_task.task_id group by m_taskalarm.id, m_taskalarm.alarmtype;'
            select_result1 = db.select_db(select_sql1)
            select_sql2 = 'select m_taskalarm.id, m_taskalarm.alarmtype,count(*) as alarmcount from m_taskalarm left join m_taskalarmtype on m_taskalarm.id = m_taskalarmtype.errorid left join m_task on m_taskalarmtype.task_id = m_task.task_id where m_task.create_time  between "{}" and "{}" group by m_taskalarm.id, m_taskalarm.alarmtype;'.format(starttime,endtime)
            select_result2 = db.select_db(select_sql2)

            for res2  in select_result2:
                for res1 in select_result2:
                    if res2['id'] == res1['id']:
                        select_result1[int(res2['id'])-1] = res2

            if len(select_result1) == 0:
                req.code = 1
                req.msg = "数据为空"
            else:
                req.data = select_result1

    return json.dumps(req.__dict__)


'''
    15.设备异常统计
    DevFailure
'''


@realtimealarm.route('/DevAbnormal', methods=['post'])
def DevAbnormal():

    token = request.form.get("token")
    current_app.logger.info('DevAbnormal   token:{}'.format(token))

    select_camera_abnormal = 'select m_camera.camera_id,m_camera.camera_name,m_camera.dvr_id,m_camera.channel,m_camera.roomid,m_camera.sts,m_stationroom.stationid,m_stationroom.roomname,m_camera.create_time from m_taskalarm left join m_taskalarmtype on m_taskalarm.id = m_taskalarmtype.errorid left join m_task on m_taskalarmtype.task_id = m_task.task_id left join m_camera on m_task.camera_id = m_camera.camera_id left join m_stationroom on m_stationroom.id = m_camera.roomid where m_camera.sts = 0 group by m_camera.camera_id, m_camera.sts;'
    select_camera_abnormal_result = db.select_db(select_camera_abnormal)
    # title_list = list(select_camera_abnormal_to_excel_result[0].keys())
    cam_alarm_num = len(select_camera_abnormal_result)
    '''
    上面代码统计摄像头异常数量；
    下面代码统计设备一异常数量；
    '''
    dev_alarm_sql = 'select count(*) as error_num from m_devstate where now() >SUBDATE(updatetime,interval -60 minute);'
    dev_alarm = db.select_db(dev_alarm_sql)
    dev_alarm_num = dev_alarm[0]['error_num']

    req = ReqResult()

    req.code = 0
    req.msg = "成功"
    req.data = {
        'cam_alarm_num': cam_alarm_num,
        'dev_alarm_num': dev_alarm_num,
    }
    return json.dumps(req.__dict__)





'''

    17.导出异常设备明细


'''


@realtimealarm.route('/ExportData', methods=['post'])
# def ExportData():
#     token = request.form.get("token")
#     current_app.logger.info('ExportData   token:{}'.format(token))
#
#     select_camera_abnormal_to_excel = 'select m_camera.camera_id,m_camera.camera_name,m_camera.dvr_id,m_camera.channel,m_camera.roomid,m_camera.sts,m_stationroom.stationid,m_stationroom.roomname,m_camera.create_time from m_taskalarm left join m_taskalarmtype on m_taskalarm.id = m_taskalarmtype.errorid left join m_task on m_taskalarmtype.task_id = m_task.task_id left join m_camera on m_task.camera_id = m_camera.camera_id left join m_stationroom on m_stationroom.id = m_camera.roomid where m_camera.sts = 0 group by m_camera.camera_id, m_camera.sts;'
#     select_camera_abnormal_to_excel_result = db.select_db(select_camera_abnormal_to_excel)
#
#     if all([select_camera_abnormal_to_excel_result, ]):
#         title_list_camera = list(select_camera_abnormal_to_excel_result[0].keys())
#     # cam_alarm_num = len(select_camera_abnormal_to_excel_result)
#     # print(title_list_camera)
#
#     select_dev_abnormal_to_excel = 'select m_devstate.devid,m_devstate.updatetime,m_devinfo.address,m_devinfo.modelid from m_devstate left join m_devinfo on m_devstate.devid = m_devinfo.devid;'
#     select_dev_to_excel_result = db.select_db(select_dev_abnormal_to_excel)
#     if all([select_dev_to_excel_result, ]):
#         title_list_dev = list(select_dev_to_excel_result[0].keys())
#
#     req = ReqResult()
#     # 创建一个工作簿
#     xl = xlwt.Workbook(encoding='utf-8')
#     # 创建一个sheet对象,第二个参数是指单元格是否允许重设置，默认为False
#     sheet1 = xl.add_sheet('摄像头异常', cell_overwrite_ok=True)
#     sheet2 = xl.add_sheet('设备异常', cell_overwrite_ok=True)
#
#     # 初始化样式
#     style = xlwt.XFStyle()
#     font = xlwt.Font()
#     font.name = 'Times New Roman'
#     font.bold = True
#     style.alignment.horz = 2  # 字体居中
#     style.alignment.vert = 1
#     style.font = font
#
#
#     '''sheet1'''
#     try:
#         for i in range(len(title_list_camera)):
#             sheet1.write(0, i, title_list_camera[i], style)
#             sheet1.col(i).width = 4500  # Set the column width
#
#         list_results = []
#         for results in select_camera_abnormal_to_excel_result:
#             list_results.append(results.values())
#         # print(list_results)
#         j = 1
#         for results in list_results:
#             # print(list(results))
#
#             for i in range(len(title_list_camera)):
#                 sheet1.write(j, i, str(list(results)[i]))
#                 # print(list(results)[i])
#             j += 1
#
#         '''sheet2'''
#         for i in range(len(title_list_dev)):
#             sheet2.write(0, i, title_list_dev[i], style)
#             sheet2.col(i).width = 4500  # Set the column width
#
#         list_results = []
#         for results in select_dev_to_excel_result:
#             list_results.append(results.values())
#         # print(list_results)
#         j = 1
#         for results in list_results:
#             # print(list(results))
#
#             for i in range(len(title_list_dev)):
#                 sheet2.write(j, i, str(list(results)[i]))
#                 # print(list(results)[i])
#             j += 1
#
#
#         now_time = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
#         save_path = '/home/python/Desktop/{}_设备异常.xls'.format(now_time)
#
#         # 保存文件
#         xl.save(save_path)
#     except Exception as e:
#         req.code = 0
#         req.msg = e
#     else:
#
#         req.code = 0
#         req.data = save_path
#
#
#     # return json.dumps(req.__dict__)
def ExportData():
    token = request.form.get("token")
    current_app.logger.info('ExportData   token:{}'.format(token))

    select_camera_abnormal_to_excel = 'select m_camera.camera_id,m_camera.camera_name,m_camera.dvr_id,m_camera.channel,m_camera.roomid,m_camera.sts,m_stationroom.stationid,m_stationroom.roomname,m_camera.create_time from m_taskalarm left join m_taskalarmtype on m_taskalarm.id = m_taskalarmtype.errorid left join m_task on m_taskalarmtype.task_id = m_task.task_id left join m_camera on m_task.camera_id = m_camera.camera_id left join m_stationroom on m_stationroom.id = m_camera.roomid where m_camera.sts = 0 group by m_camera.camera_id, m_camera.sts;'
    select_camera_abnormal_to_excel_result = db.select_db(select_camera_abnormal_to_excel)
    print(select_camera_abnormal_to_excel_result)
    title_list_camera = []
    if all([select_camera_abnormal_to_excel_result, ]):
        title_list_camera = list(select_camera_abnormal_to_excel_result[0].keys())
    # cam_alarm_num = len(select_camera_abnormal_to_excel_result)
    # print(title_list_camera)

    select_dev_abnormal_to_excel = 'select m_devstate.devid,m_devstate.updatetime,m_devinfo.address,m_devinfo.modelid from m_devstate left join m_devinfo on m_devstate.devid = m_devinfo.devid;'
    select_dev_to_excel_result = db.select_db(select_dev_abnormal_to_excel)
    title_list_dev = []
    if all([select_dev_to_excel_result, ]):
        title_list_dev = list(select_dev_to_excel_result[0].keys())

    req = ReqResult()
    # 创建一个工作簿
    xl = xlwt.Workbook(encoding='utf-8')
    # 创建一个sheet对象,第二个参数是指单元格是否允许重设置，默认为False
    sheet1 = xl.add_sheet('摄像头异常', cell_overwrite_ok=True)
    sheet2 = xl.add_sheet('设备异常', cell_overwrite_ok=True)

    # 初始化样式
    style = xlwt.XFStyle()
    font = xlwt.Font()
    font.name = 'Times New Roman'
    font.bold = True
    style.alignment.horz = 2  # 字体居中
    style.alignment.vert = 1
    style.font = font


    '''sheet1'''
    save_path = None
    try:
        if len(title_list_camera) > 0:
            for i in range(len(title_list_camera)):
                sheet1.write(0, i, title_list_camera[i], style)
                sheet1.col(i).width = 4500  # Set the column width

            list_results = []
            for results in select_camera_abnormal_to_excel_result:
                list_results.append(results.values())
            # print(list_results)
            j = 1
            for results in list_results:
                # print(list(results))

                for i in range(len(title_list_camera)):
                    sheet1.write(j, i, str(list(results)[i]))
                    # print(list(results)[i])
                j += 1

        '''sheet2'''
        if len(title_list_dev)>0:
            for i in range(len(title_list_dev)):
                sheet2.write(0, i, title_list_dev[i], style)
                sheet2.col(i).width = 4500  # Set the column width

            list_results = []
            for results in select_dev_to_excel_result:
                list_results.append(results.values())
            # print(list_results)
            j = 1
            for results in list_results:
                # print(list(results))

                for i in range(len(title_list_dev)):
                    sheet2.write(j, i, str(list(results)[i]))
                    # print(list(results)[i])
                j += 1


        if len(title_list_dev)!=0 and len(title_list_camera)!=0:
        # 保存文件
            now_time = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
            #save_path = '/home/python/Desktop/{}_设备异常.xls'.format(now_time)
            save_path = '~/Desktop/DetectVideoServer/{}_设备异常.xls'.format(now_time)
            xl.save(save_path)

    except Exception as e:
        req.code = 0
        req.msg = e
    else:

        req.code = 0
        req.data = save_path
        # req.data = 'ok'


    return json.dumps(req.__dict__)



'''

    18.首页告警类型
    IndexAlarmType

'''
@realtimealarm.route('/IndexAlarmType', methods=['post'])
def IndexAlarmType():
    print("-------------IndexAlarmType------------")
    token = request.form.get("token")
    time_type = request.form.get("time_type")
    print("IndexAlarmType time_type:", str(time_type))
    sql = ""
    if int(time_type) == 0:
        sql = "select  aa.total as total,cc.cnt as huocnt,bb.cnt as rencnt,dd.cnt as othercnt ,ee.cnt as eleccnt ,ff.cnt as cameracnt ,gg.cnt as devstatcnt from  \
                (select count(*) as total from m_task where DATE_SUB(CURDATE(), INTERVAL 1 DAY) <= date(create_time)) aa , \
                ( select count(*) as cnt from m_task where errortype=1 and DATE_SUB(CURDATE(), INTERVAL 1 DAY) <= date(create_time)) bb , \
                ( select count(*) as cnt from m_task where errortype=2 and DATE_SUB(CURDATE(), INTERVAL 1 DAY) <= date(create_time)) cc , \
                ( select count(*) as cnt from m_task where errortype=3 and DATE_SUB(CURDATE(), INTERVAL 1 DAY) <= date(create_time)) dd , \
                ( select count(*) as cnt from m_task where errortype=4 and DATE_SUB(CURDATE(), INTERVAL 1 DAY) <= date(create_time)) ee , \
                ( select count(*) as cnt from m_task where errortype=5 and DATE_SUB(CURDATE(), INTERVAL 1 DAY) <= date(create_time)) ff , \
                ( select count(*) as cnt from m_task where errortype=6 and DATE_SUB(CURDATE(), INTERVAL 1 DAY) <= date(create_time)) gg "
    elif int(time_type) == 1:
        sql = "select  aa.total as total,cc.cnt as huocnt,bb.cnt as rencnt,dd.cnt as othercnt ,ee.cnt as eleccnt ,ff.cnt as cameracnt ,gg.cnt as devstatcnt from  \
                (select count(*) as total from m_task where DATE_SUB(CURDATE(), INTERVAL 7 DAY) <= date(create_time)) aa , \
                ( select count(*) as cnt from m_task where errortype=1 and DATE_SUB(CURDATE(), INTERVAL 7 DAY) <= date(create_time)) bb , \
                ( select count(*) as cnt from m_task where errortype=2 and DATE_SUB(CURDATE(), INTERVAL 7 DAY) <= date(create_time)) cc , \
                ( select count(*) as cnt from m_task where errortype=3 and DATE_SUB(CURDATE(), INTERVAL 7 DAY) <= date(create_time)) dd , \
                ( select count(*) as cnt from m_task where errortype=4 and DATE_SUB(CURDATE(), INTERVAL 7 DAY) <= date(create_time)) ee , \
                ( select count(*) as cnt from m_task where errortype=5 and DATE_SUB(CURDATE(), INTERVAL 7 DAY) <= date(create_time)) ff , \
                ( select count(*) as cnt from m_task where errortype=6 and DATE_SUB(CURDATE(), INTERVAL 7 DAY) <= date(create_time)) gg "
    else:
        sql = "select  aa.total as total,cc.cnt as huocnt,bb.cnt as rencnt,dd.cnt as othercnt ,ee.cnt as eleccnt ,ff.cnt as cameracnt ,gg.cnt as devstatcnt from  \
                (select count(*) as total from m_task where DATE_SUB(CURDATE(), INTERVAL 30 DAY) <= date(create_time)) aa , \
                ( select count(*) as cnt from m_task where errortype=1 and DATE_SUB(CURDATE(), INTERVAL 30 DAY) <= date(create_time)) bb , \
                ( select count(*) as cnt from m_task where errortype=2 and DATE_SUB(CURDATE(), INTERVAL 30 DAY) <= date(create_time)) cc , \
                ( select count(*) as cnt from m_task where errortype=3 and DATE_SUB(CURDATE(), INTERVAL 30 DAY) <= date(create_time)) dd , \
                ( select count(*) as cnt from m_task where errortype=4 and DATE_SUB(CURDATE(), INTERVAL 30 DAY) <= date(create_time)) ee , \
                ( select count(*) as cnt from m_task where errortype=5 and DATE_SUB(CURDATE(), INTERVAL 30 DAY) <= date(create_time)) ff , \
                ( select count(*) as cnt from m_task where errortype=6 and DATE_SUB(CURDATE(), INTERVAL 30 DAY) <= date(create_time)) gg "
    print("sql:",sql)

    listdata = db.select_db(sql)
    print(str(listdata))

    req = ReqResult()
    if len(listdata) == 0:
        req.code = 1
        req.msg = "获取数据失败"
    else:
        req.data = listdata

    return json.dumps(req.__dict__)





def IndexAlarmType1():
    token = request.form.get('token')
    time_type = request.form.get('time_type')
    current_app.logger.info('IndexAlarmType   token:{}'.format(token))

    now = datetime.datetime.now()
    now_time = datetime.datetime.now().strftime('%Y-%m-%d')
    req = ReqResult()

    # 获取告警列表

    # print(listdata[0:6])
    if all([time_type, ]):
        print(time_type)
        # 0 表示天
        if int(time_type) == 0:
            TableName = 'm_taskalarm'
            sql = "select id,alarmtype from {} ".format(TableName)
            listdata = db.select_db(sql)

            # 给字典附加count字段
            for day_res in listdata:
                day_res['alarmcount'] = 0

            delta = datetime.timedelta(days=-1)
            n_days = now + delta
            n_days = n_days.strftime('%Y-%m-%d')
            # print(n_days)

            day_alarm_count_sql = 'select m_taskalarm.id, m_taskalarm.alarmtype,count(*) as alarmcount from m_taskalarm left join m_taskalarmtype on m_taskalarm.id = m_taskalarmtype.errorid left join m_task on m_taskalarmtype.task_id = m_task.task_id where m_task.create_time  between "{}" and "{}" group by m_taskalarm.id, m_taskalarm.alarmtype;'.format(n_days, now_time)
            day_alarm_count = db.select_db(day_alarm_count_sql)

            day_alarm_list = []
            for listdata_day in listdata[0:6]:
                for day_alarm_count_day in day_alarm_count:
                    if str(listdata_day['alarmtype']) == str(day_alarm_count_day['alarmtype']):
                        listdata_day['alarmcount'] = day_alarm_count_day['alarmcount']

                day_alarm_list.append(listdata_day)
            print(day_alarm_list)
            req.data = day_alarm_list
        # 1表示周
        elif int(time_type) == 1:
            TableName = 'm_taskalarm'
            sql = "select id,alarmtype from {} ".format(TableName)
            listdata = db.select_db(sql)

            # 给字典附加count字段
            for day_res in listdata:
                day_res['alarmcount'] = 0
            delta = datetime.timedelta(days=-7)
            n_days = now + delta
            n_days = n_days.strftime('%Y-%m-%d')
            # print(n_days)

            day_alarm_count_sql = 'select m_taskalarm.id, m_taskalarm.alarmtype,count(*) as alarmcount from m_taskalarm left join m_taskalarmtype on m_taskalarm.id = m_taskalarmtype.errorid left join m_task on m_taskalarmtype.task_id = m_task.task_id where m_task.create_time  between "{}" and "{}" group by m_taskalarm.id, m_taskalarm.alarmtype;'.format(
                n_days, now_time)
            day_alarm_count = db.select_db(day_alarm_count_sql)

            day_alarm_list = []
            for listdata_day in listdata[0:6]:
                for day_alarm_count_day in day_alarm_count:
                    if str(listdata_day['alarmtype']) == str(day_alarm_count_day['alarmtype']):
                        listdata_day['alarmcount'] = day_alarm_count_day['alarmcount']

                day_alarm_list.append(listdata_day)
            # print(day_alarm_list)
            req.data = day_alarm_list

        # 2表示月
        elif int(time_type) == 2:
            TableName = 'm_taskalarm'
            sql = "select id,alarmtype from {} ".format(TableName)
            listdata = db.select_db(sql)

            # 给字典附加count字段
            for day_res in listdata:
                day_res['alarmcount'] = 0
                # ################   待优化
            # delta = datetime.timedelta(days=-30)
            # n_days = now + delta
            # n_days = n_days.strftime('%Y-%m-%d')

            #######################
            '''
            today = datetime.date.today()  # 1. 获取「今天」
            last_month = today.replace(month=today.month - 1)  # 2.获取前一个月
            last_month_date = last_month.strftime("%Y-%m-%d")

            '''

            # 上面代码不能解决跨年问题

            today = datetime.date.today()
            today_d = today.strftime('%d')
            first = today.replace(day=1)
            lastMonth = first - datetime.timedelta(days=1)
            lastMonth_y_m = lastMonth.strftime('%Y-%m')
            last_month_date = lastMonth_y_m + '-' + today_d

            day_alarm_count_sql = 'select m_taskalarm.id, m_taskalarm.alarmtype,count(*) as alarmcount from m_taskalarm left join m_taskalarmtype on m_taskalarm.id = m_taskalarmtype.errorid left join m_task on m_taskalarmtype.task_id = m_task.task_id where m_task.create_time  between "{}" and "{}" group by m_taskalarm.id, m_taskalarm.alarmtype;'.format(
                last_month_date, now_time)
            day_alarm_count = db.select_db(day_alarm_count_sql)

            day_alarm_list = []

            for listdata_day in listdata[0:6]:
                for day_alarm_count_day in day_alarm_count:
                    if str(listdata_day['alarmtype']) == str(day_alarm_count_day['alarmtype']):
                        listdata_day['alarmcount'] = day_alarm_count_day['alarmcount']

                day_alarm_list.append(listdata_day)
            print(day_alarm_list)
            req.data = day_alarm_list
        else:
            req.code = 1
            req.msg = '失败'
    else:
        req.code = 1
        req.msg = '失败'


    return  json.dumps(req.__dict__)



'''

    19.告警走势
    AlarmTrend

'''

@realtimealarm.route('/AlarmTrend', methods=['post'])
def AlarmTrend():
    print("---------AlarmTrend start--------")
    token = request.form.get("token")
    time_type = request.form.get("time_type")
    print("AlarmTrend time_type:", str(time_type))
    sql = ""
    if int(time_type) == 0:
        sql = "select DATE_FORMAT(create_time,'%m.%d') timeval,count(task_id) as cnt " \
              " from m_task where DATE_SUB(CURDATE(), INTERVAL 27 DAY)<= date(create_time)  group by timeval;  "
    elif int(time_type) == 1:
        sql = "select DATE_FORMAT(create_time,'%x.%v') as timeval,count(task_id) as cnt from m_task" \
              " where DATE_FORMAT(create_time,'%Y')=2021 group by timeval;"
    else:
        sql = "select DATE_FORMAT(create_time,'%x.%m') as timeval,count(task_id) as cnt from m_task" \
              " where DATE_FORMAT(create_time,'%Y')='2021' group by timeval;"

    print("AlarmTrend sql:", sql)
    listdata = db.select_db(sql)
    print(str(listdata))

    req = ReqResult()
    if len(listdata) == 0:
        req.code = 1
        req.msg = "获取数据失败"
    else:
        req.data = listdata

    return json.dumps(req.__dict__)

@realtimealarm.route('/AlarmTrend1', methods=['post'])
def AlarmTrend1():

    '''
    统计月/周/日告警
    :return:  14天的告警（每天总数），12周的告警（每周的总数），12月的告警（每月的总数）
    '''

    token = request.form.get("token")
    time_type = request.form.get("time_type")
    current_app.logger.info('ExportAbnormalDevInfo   token:{}'.format(token))
    now_time = datetime.datetime.now().strftime('%Y-%m-%d')
    req = ReqResult()


    # 日
    if int(time_type) == 0:
        now = datetime.datetime.now()
        delta = datetime.timedelta(days=-14+1)
        n_days = now + delta
        n_days = n_days.strftime('%Y-%m-%d')
        # n_days = '2020-11-11'
        # print(n_days)
        # 查询出告警的数量（每天的告警总数）
        day_alarm_count_sql = 'select date(m_task.create_time) as date,count(m_task.create_time) as count from m_taskalarm left join m_taskalarmtype on m_taskalarm.id = m_taskalarmtype.errorid left join m_task on m_taskalarmtype.task_id = m_task.task_id where m_task.create_time  between "{}" and "{}" group by date;'.format(n_days, now_time)
        day_alarm_counts = db.select_db(day_alarm_count_sql)
        # for day_alarm_count in day_alarm_counts:
        #     print(day_alarm_count)
        #     print(day_alarm_count['date'])
        #     print(day_alarm_count['count'])


        # 10天的日期
        day_select_sql_10 = 'SELECT @date := DATE_ADD(@date, INTERVAL - 1 DAY) days FROM ( SELECT @date := DATE_ADD("{}", INTERVAL + 1 DAY) FROM m_taskalarm LIMIT 10 ) time;'.format(now_time)
        day_res_10 = db.select_db(day_select_sql_10)
        # 4天的日期
        day_select_sql_4 = 'SELECT @date := DATE_ADD(@date, INTERVAL - 1 DAY) days FROM ( SELECT @date := DATE_ADD("{}", INTERVAL + 1 DAY) FROM m_taskalarm LIMIT 5 ) time;'.format(day_res_10[-1]['days'])
        day_res_4 = db.select_db(day_select_sql_4)
        # 14天的日期
        day_res_14 = day_res_10 + day_res_4[1:]

        # 给字典附加count字段
        for day_res in day_res_14:
            day_res['count'] = 0

        # 与数据库查询出的告警的日期与当前日期对比，有相同日期，直接修改count
        new_day_res_14 = []
        for day_res in day_res_14:
            for day_alarm_count in day_alarm_counts:
                if str(day_res['days']) == str(day_alarm_count['date']):
                    day_res['count'] = day_alarm_count['count']

            # 接下来 把数据append到new_day_res_14里
            new_day_res_14.append(day_res)
        req.code = 0
        req.data = new_day_res_14
    # print(new_day_res_14)

    # 月
    if int(time_type) == 2:

        now = datetime.datetime.now()
        month_select_sql_10 = 'SELECT DATE_FORMAT(@date := DATE_ADD(@date, INTERVAL - 1 MONTH),"%Y-%m") as month FROM ( SELECT @date := DATE_ADD("{}", INTERVAL + 1 MONTH) FROM  m_taskalarm  LIMIT 10 ) time;'.format(now)
        month_res_10 = db.select_db(month_select_sql_10)
        month_select_sql_2 = 'SELECT DATE_FORMAT(@date := DATE_ADD(@date, INTERVAL -1 MONTH),"%Y-%m") as month FROM ( SELECT @date := DATE_ADD("{}-01", INTERVAL +1 MONTH) FROM  m_taskalarm  LIMIT 3 ) time;'.format(month_res_10[-1]['month'])
        month_res_2 = db.select_db(month_select_sql_2)
        month_res_12 = month_res_10 + month_res_2[1:]

        month_alarm_count_sql = 'select date_format(m_task.create_time, "%Y-%m") as month,count(*) as count from m_taskalarm left join m_taskalarmtype on m_taskalarm.id = m_taskalarmtype.errorid left join m_task on m_taskalarmtype.task_id = m_task.task_id Where  m_task.create_time between date_sub(now(),interval 12 month) and now() group by month;'
        month_alarm_counts = db.select_db(month_alarm_count_sql)
        # print(month_alarm_counts)

        # print(month_res_12)

        # 给字典附加count字段
        for month_res in month_res_12:
            month_res['count'] = 0
            print(month_res)

        # 与数据库查询出的告警的日期与当前日期对比，有相同日期，直接修改count
        new_month_res_12 = []
        for month_res in month_res_12:
            for month_alarm_count in month_alarm_counts:
                if str(month_res['month']) == str(month_alarm_count['month']):
                    month_res['count'] = month_alarm_count['count']

            # 接下来 把数据append到new_month_res_12里
            new_month_res_12.append(month_res)
        req.code = 0
        req.data = new_month_res_12

    # 周
    if int(time_type) == 1:
        i = 1
        week_alarm_list = []
        while True:
            week_select_sql = 'SELECT date_format(m_task.create_time, "%Y-%m") as week,count(*) as count FROM m_taskalarm left join m_taskalarmtype on m_taskalarm.id = m_taskalarmtype.errorid left join m_task on m_taskalarmtype.task_id = m_task.task_id WHERE YEARWEEK(date_format(m_task.create_time,"%Y-%m-%d")) = YEARWEEK(now())-{} Group by  week;'.format(i)
            week_select = db.select_db(week_select_sql)

            i += 1
            if i >13:
                break
            count = 0
            for week in week_select:
                if len(week) == 0:
                    continue
                count += week['count']
            # print(count)
            week_alarm_list.append(count)
            # print(week_select)
            # print(week_alarm_list)
            # req.data = week_alarm_list[::-1]
        week_alarm_dict = {
            '0': week_alarm_list[0],
            '1': week_alarm_list[1],
            '2': week_alarm_list[2],
            '3': week_alarm_list[3],
            '4': week_alarm_list[4],
            '5': week_alarm_list[5],
            '6': week_alarm_list[6],
            '7': week_alarm_list[7],
            '8': week_alarm_list[8],
            '9': week_alarm_list[9],
            '10': week_alarm_list[10],
            '11': week_alarm_list[11],
        }

        print(week_alarm_dict)
        req.data = week_alarm_dict

    return json.dumps(req.__dict__)


'''

    20.设备总数
    DevCount

'''
@realtimealarm.route('/DevCount', methods=['post'])
def DevCount():
    token = request.form.get("token")

    current_app.logger.info('DevCount   token:{}'.format(token))

    req = ReqResult()
    devCount_sql = 'select count(devid) as devCount from m_devstate'
    devCount = db.select_db(devCount_sql)
    # print(devCount)

    # req.data = devCount[0]['devCount']

    dev_alarm_sql = 'select count(*) as error_num from m_devstate where now() >SUBDATE(updatetime,interval -60 minute);'
    dev_alarm = db.select_db(dev_alarm_sql)
    dev_alarm_num = dev_alarm[0]['error_num']



    req.code = 0
    req.msg = "成功"
    req.data = {
        'devCount': devCount[0]['devCount'],
        # 'devRuning': devCount[0]['devCount'],
        'devError': dev_alarm[0]['error_num'],
        'devRuning': int(devCount[0]['devCount'])-int(dev_alarm[0]['error_num']),

        'noInstallDev': 0,
    }


    return json.dumps(req.__dict__)


###########################################################################







# @realtimealarm.route('/GetCurAlarmList', methods=["post"])
# def GetCurAlarmList():
#     print("token", request.form.get("token"))
#     print("pagesize", request.form.get("pagesize"))
#     print("pagenum", request.form.get("pagenum"))
#
#     pagesize = request.form.get("pagesize")
#     pagenum = request.form.get("pagenum")
#     token = request.form.get("token")
#     req = ReqResult()
#     if pagesize == None or pagenum == None or token == None:
#         req.code = 1
#         req.msg= "参数不正确"
#         return json.dumps(req.__dict__)
#
#     current_app.logger.info('GetAlarmInfoFile   token:{},pagesize:{},pagenum:{}'.format(token,pagesize,pagenum))
#
#     sql = "select * ,CONCAT(stationname,'-',roomname) as station from v_curalert where opsts != 20 ORDER BY id desc limit {},{}".format( str((int(pagenum)-1)*int(pagesize)),str(pagesize))
#     listdata = db.select_db(sql)
#
#     json_list = []
#
#     for i in listdata:
#         i["updatetime"]=i["updatetime"].strftime("%Y-%m-%d %H:%M:%S")
#         json_list.append(i)
#
#     sqltotal = "select count(*) as cnt from v_curalert where opsts != 20"
#     totaldata = db.select_db(sqltotal)
#     current_app.logger.info('GetCurAlarmList totaldata:{}'.format(totaldata))
#     #print(json_list)
#     #ret1 = json.dumps(json_list)
#     #print(ret1)
#
#     dateInfo = {}
#     dateInfo["datas"] = json_list
#     dateInfo["count"] = len(json_list)
#     dateInfo["total"] = totaldata[0]["cnt"]
#
#     if len(listdata) == 0:
#         req.code = 1
#         req.msg = "获取数据失败"
#     else:
#         req.data = dateInfo
#
#     return json.dumps(req.__dict__)


########################################################################



'''

    21.获取全部的告警类型列表

'''

@realtimealarm.route('/GetAllAlarmList', methods=["post"])
def GetAllAlarmList():
    print("token", request.form.get("token"))
    print("pagesize", request.form.get("pagesize"))
    print("pagenum", request.form.get("pagenum"))

    pagesize = request.form.get("pagesize")
    pagenum = request.form.get("pagenum")
    token = request.form.get("token")
    req = ReqResult()

    if pagesize == None or pagenum == None or token == None:
        req.code = 1
        req.msg= "参数不正确"
        return json.dumps(req.__dict__)

    current_app.logger.info('GetAllAlarmList   token:{},pagesize:{},pagenum:{}'.format(token, pagesize, pagenum))

    # sql = "select * ,CONCAT(station,'-',roomname) as station from v_historyalarm where opsts != 20 ORDER BY id desc limit {},{}".format( str((int(pagenum)-1)*int(pagesize)),str(pagesize))
    # sql = "select m_task.task_id as id,m_task.sts,m_task.opsts,m_taskalarmtype.updatetime,m_camera.camera_name,m_stationinfo.stationname,CONCAT(m_stationinfo.stationname,'-',m_stationroom.roomname) as station,m_taskalarm.alarmtype from m_task left join m_taskalarmtype on m_taskalarmtype.task_id=m_task.task_id left join m_taskalarm on m_taskalarm.id=m_taskalarmtype.errorid left join m_camera on m_task.camera_id=m_camera.camera_id left join m_stationroom on m_stationroom.id = m_camera.roomid left join m_stationinfo on m_stationinfo.id=m_stationroom.stationid ORDER BY m_task.task_id desc limit {},{}".format( str((int(pagenum)-1)*int(pagesize)),str(pagesize))
    sql = "select m_task.task_id as id,m_sts.note as sts,m_task.opsts,m_stationroom.roomname as roomname,m_taskalarmtype.updatetime,m_camera.camera_name,m_stationinfo.stationname,CONCAT(m_stationinfo.stationname,'-',m_stationroom.roomname) as station,m_taskalarm.alarmtype from m_task left join m_taskalarmtype on m_taskalarmtype.task_id=m_task.task_id left join m_taskalarm on m_taskalarm.id=m_taskalarmtype.errorid left join m_camera on m_task.camera_id=m_camera.camera_id left join m_stationroom on m_stationroom.id = m_camera.roomid left join m_stationinfo on m_stationinfo.id=m_stationroom.stationid  left join m_sts on m_sts.sts=m_task.sts ORDER by id DESC limit {},{}".format( str((int(pagenum)-1)*int(pagesize)),str(pagesize))
    listdata = db.select_db(sql)

    # print(listdata)

    json_list = []
    #
    for i in listdata:
        if all([i["updatetime"],]):
            i["updatetime"]=i["updatetime"].strftime("%Y-%m-%d %H:%M:%S")    #
        else:
            i["updatetime"] = None
        json_list.append(i)
    print(json_list)

    sqltotal = "select count(*) as cnt from m_task"
    totaldata = db.select_db(sqltotal)
    current_app.logger.info('GetAllAlarmList totaldata:{}'.format(totaldata))

    dateInfo = {}
    dateInfo["datas"] = json_list
    dateInfo["count"] = len(json_list)
    dateInfo["total"] = totaldata[0]["cnt"]
    #
    if len(listdata) == 0:
        req.code = 1
        req.msg = "获取数据失败"
    else:
        req.data = dateInfo

    return json.dumps(req.__dict__)

    # return 'ok'


'''

    27.获取指定变电站内指定摄像头的点位

'''

@realtimealarm.route('/Camera_point', methods=["post"])
def GetCamera_pointsBycameraid():
    req = ReqResult()
    print("camera_id", request.form.get("camera_id"))
    camera_id = request.form.get("camera_id")
    if camera_id == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('GetCamera_pointsBycameraid   camera_id:{}'.format(camera_id))
    sqltotal = "select * from m_camera_point  where camera_id='{}'".format(camera_id)
    totaldata = db.select_db(sqltotal)
    json_list = []
    for i in totaldata:
        if i["create_time"] != None:
            i["create_time"] = i["create_time"].strftime("%Y-%m-%d %H:%M:%S")
        json_list.append(i)
    print("GetCamera_pointsBycameraid:", json_list)
    req.code = 0
    req.msg = "读取成功"
    req.data = totaldata
    return json.dumps(req.__dict__, ensure_ascii=False)



'''
   27.1 添加指定变电站内指定摄像头的点位
'''
@realtimealarm.route('/AddCamera_point', methods=["post"])
def AddCamera_point():
    camera_id = request.form.get("camera_id")
    point_info = request.form.get("point_info")
    point_type = request.form.get("point_type")
    camera_type = request.form.get("camera_type")


    req = ReqResult()
    if camera_id == None or point_info == None \
            or point_type == None :
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('AddCamera_point   camera_id:{},point_info:{},point_type:{},'
                            'camera_type:{}'
                            .format(0, camera_id, point_info, point_type, camera_type))

    select_maxid_sql = 'select max(point_id) as maxid from m_camera_point'
    select_maxid_result = db.select_db(select_maxid_sql)

    point_id = 0
    if select_maxid_result[0]['maxid'] is None:
        point_id = 1
    else:
        point_id = int(select_maxid_result[0]['maxid']) + 1
    nowTime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    insert_dic = {
       'point_id':point_id,
        'camera_id': camera_id,
        'point_info': point_info,
        'point_type': point_type,
        'camera_type': camera_type,
        'create_time': nowTime
    }
    print("----111111111-----", insert_dic)
    db.insertData("m_camera_point", insert_dic)
    print("---22222222222------")
    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
   27.2 修改指定变电站内指定摄像头的点位
'''
@realtimealarm.route('/ModifyCamera_point', methods=["post"])
def ModifyCamera_point():
    point_id = request.form.get("point_id")
    point_info = request.form.get("point_info")
    point_type = request.form.get("point_type")
    camera_type = request.form.get("camera_type")

    req = ReqResult()
    if point_id == None or point_info == None or point_type == None \
            or camera_type == None :
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('ModifyCamera_point   point_id:{},point_info:{},point_type:{},'
                            'camera_type:{}'
                            .format(point_id, point_info, point_type, camera_type))

    sql = "update m_camera_point set point_info='{}',point_type='{}',camera_type='{}' where point_id={}".format(
        point_info, point_type, camera_type, point_id)
    print("----ModifyStationRoomInfo sql:", sql)
    db.execute_db(sql)
    print("----ModifyStationRoomInfo sql over!")

    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
    27.3 删除指定变电站内指定摄像头的点位
'''
@realtimealarm.route('/DeleteCamera_point', methods=["post"])
def DeleteCamera_point():
    point_id = request.form.get("point_id")
    req = ReqResult()
    if point_id == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('DeleteCamera_point   point_id:{}'.format(point_id))

    sql = "delete from m_camera_point where point_id={}".format(point_id)
    print("----DeleteStationDVR sql:", sql)
    db.execute_db(sql)
    print("----DeleteStationDVR sql over!")

    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
28 获取指定站内房间roomID下的摄像头列表
'''

@realtimealarm.route('/GetStationRoomCamList', methods=["post"])
def GetStationRoomCamList():
    req = ReqResult()
    roomid = request.form.get("roomid")
    print("roomid:", roomid)
    if roomid == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('GetStationRoomCamList roomid:{}'.format(roomid))
    sqltotal = "select * from m_camera where roomid={}".format(roomid)
    totaldata = db.select_db(sqltotal)
    print(totaldata)
    json_list = []
    for i in totaldata:
        i["create_time"] = i["create_time"].strftime("%Y-%m-%d %H:%M:%S")
        json_list.append(i)

    print("GetStationRoomCamList:", json_list)
    req.code = 0
    req.msg = "读取成功"
    req.data = json_list

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
   29 增加检修区域，房间可多选   2025年8月8日
'''


@realtimealarm.route('/AddOverhaulAreaRooms', methods=["post"])
def AddOverhaulAreaRooms():
    roomids = request.form.get("roomids")
    starttime = request.form.get("starttime")
    endtime = request.form.get("endtime")
    # 去除时区部分
    starttime1 = starttime.split(" GMT")[0]
    endtime1=endtime.split(" GMT")[0]

    starttime1=datetime.datetime.strptime(starttime1, "%a %b %d %Y %H:%M:%S")
    endtime1 = datetime.datetime.strptime(endtime1, "%a %b %d %Y %H:%M:%S")
    starttime=starttime1.strftime("%Y-%m-%d %H:%M:%S")
    endtime=endtime1.strftime("%Y-%m-%d %H:%M:%S")
    stat = 1
    req = ReqResult()
    if roomids == None or starttime == None or endtime == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('AddOverhaulAreaRooms   roomids:{},c:{},endtime:{}'.format(roomids, roomids, endtime))

    select_maxid_sql = 'select max(id) as maxid from m_overhaularea'
    select_maxid_result = db.select_db(select_maxid_sql)

    id = 0
    if select_maxid_result[0]['maxid'] is None :
        id = 1
    else:
        # id = int(select_maxid_result[0]['maxid']) + 1
        id=1
    insert_dic = {
        'id': id,
        'roomids': roomids,
        'starttime': starttime,
        'endtime': endtime,
        'stat': stat
    }
    print("----111111111-----", insert_dic)
    db.insertData("m_overhaularea", insert_dic)
    print("---22222222222------")
    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
   29.1 查询检修区域，房间可多选   2025年8月8日
'''


@realtimealarm.route('/SelectOverhaulAreaRooms', methods=["post"])
def SelectOverhaulAreaRooms():
    req = ReqResult()
    select_sql = "select * from m_overhaularea"
    totaldata = db.select_db(select_sql)
    if len(totaldata) <= 0:
        req.code = 1
        req.msg = "未设置检修区域"
        return json.dumps(req.__dict__, ensure_ascii=False)
        print("未设置检修区域")
    else:
        current_app.logger.info('SelectOverhaulAreaRooms 查询检修区域{}'.format(totaldata))
        for index in range(len(totaldata)):
            id = totaldata[index]["id"]
            roomids = totaldata[index]["roomids"]
            starttime = totaldata[index]["starttime"]
            endtime = totaldata[index]["endtime"]
        json_list = []
        for i in totaldata:
            i["starttime"] = i["starttime"].strftime("%Y-%m-%d %H:%M:%S")
            i["endtime"] = i["endtime"].strftime("%Y-%m-%d %H:%M:%S")
            json_list.append(i)

        print("SelectOverhaulAreaRooms:", json_list)
        req.code = 0
        req.msg = "读取成功"
        req.data = json_list
        return json.dumps(req.__dict__, ensure_ascii=False)


'''
   29.2 删除清空检修区域，房间可多选   2025年8月12日
'''


@realtimealarm.route('/DeleteOverhaulAreaRooms', methods=["post"])
def DELETEOverhaulAreaRooms():
    id = request.form.get("id")
    req = ReqResult()
    if id == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    else:
        db.execute_db("DELETE FROM m_overhaularea WHERE id = {}".format(id))
        print("ID为1的数据已删除")
        current_app.logger.info('DELETEOverhaulAreaRooms 删除检修区域ID为{}'.format(id))
        req.code = 0
        req.msg = "成功"
        return json.dumps(req.__dict__, ensure_ascii=False)


'''
   29.3 修改检修区域，房间可多选时间修改   2025年8月12日
'''


@realtimealarm.route('/UpdateOverhaulAreaRooms', methods=["post"])
def UpdateOverhaulAreaRooms():
    id = request.form.get("id")
    roomids = request.form.get("roomids")
    starttime = request.form.get("starttime")
    endtime = request.form.get("endtime")
    stat = 1
    req = ReqResult()
    if id == None or id != '1':
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    else:
        current_app.logger.info(
            'UpdateOverhaulAreaRooms   id:{},roomids:{},starttime:{},endtime:{}'.format(id, roomids, starttime,
                                                                                        endtime))
        sql = "UPDATE m_overhaularea SET roomids='{}',starttime='{}',endtime='{}' WHERE id=1".format(str(roomids),
                                                                                                     starttime, endtime)
        db.execute_db(sql)
        req.code = 0
        req.msg = "success"

        return json.dumps(req.__dict__, ensure_ascii=False)



#参照："巡视任务子项 执行函数",此处单独处理下发流程
# params:
#   optipaddr: 机器人的IP地址
#   yiqiid:  发送的命令，可以是字符串或集合类型
def _sendOptInfoToDev(optipaddr,  yiqiid, port=8081, timeout=60):
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
    print("sendOptInfoToDev IP:{optipaddr},port:{port}, opt_cmd:{yiqiid}")
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
            #如果yiqiid是集合类型，则转换为字符串
            if isinstance(yiqiid, (set, list, tuple)):
                yiqiid = ' '.join(map(str, yiqiid))

            message_bytes = str(yiqiid).encode('utf-8')
            s.sendall(message_bytes)
            print(f"已发送消息: {str(message_bytes)}")
            # 发送命令
            # 记录开始时间
            start_time = time.time()
            try:
                # 接收响应
                response = s.recv(1024).decode().strip()
                print(f"收到响应: {response}")

                # 根据响应内容判断结果
                if response == "1":
                    return 0, "操作成功"
                else:  # 包括"0"和其他情况
                    return 4, "机器人服务响应内容错误"
            except socket.timeout:
                # 超时处理
                elapsed_time = time.time() - start_time
                print(f"超时({elapsed_time:.2f}秒): 未收到响应，视为成功")
                return 5, "通信超时，未收到响应"

    except Exception as e:
        print(f"通信异常: {e}")
        return 6, "通信异常: " + str(e)

'''
   30 获取全部机器人列表
'''
@realtimealarm.route('/GetAllRobotList', methods=["post"])
def GetAllRobotInfo():
    req = ReqResult()
    sqltotal = "select * from m_robot"
    totaldata = db.select_db(sqltotal)
    if len(totaldata) <= 0 or totaldata is None:
        req.code = 1
        req.msg = "未设置机器人信息"
        return json.dumps(req.__dict__, ensure_ascii=False)


# 输入为字符穿，内含十六进制数，需要将其转换成十进制，并按公式转换为单位为米的距离
def _robot_point_position_value_convert(data):

    for i in data:
        pos_x_hex = i['pos_x']
        pos_y_hex = i['pos_y']
        print(f"Converting pos_x: {pos_x_hex}, pos_y: {pos_y_hex}")

        #如果字符穿中有空格，先将空格去掉
        pos_x_hex = pos_x_hex.replace(" ", "")
        pos_y_hex = pos_y_hex.replace(" ", "")

        pos_x_dec = int(pos_x_hex, 16)
        pos_y_dec = int(pos_y_hex, 16)

        # //圈数=3995/400=9.9875
        # //距离=圈数*直径*3.1415926 (此处直径为4)
        # 小数点后保留2位
        pos_x_m = round((pos_x_dec / 400) * 4 * 3.1415926 / 100, 2)
        pos_y_m = round((pos_y_dec / 400) * 4 * 3.1415926 / 100, 2)

        i['pos_x'] = pos_x_m
        i['pos_y'] = pos_y_m
    return data

'''
   30.1 获取取指定变电站内指定机器人的全部点位信息
'''
@realtimealarm.route('/Robot_point', methods=["post"])
def GetCamera_pointsByrobotid():
    table_name = 'm_robot_point'
    req = ReqResult()
    robot_id = request.form.get("robot_id")
    print("robot_id:", robot_id)
  
    current_app.logger.info('GetAllRobotpointID:{}')
    sqltotal = "select id, point_type, pos_x, pos_y, create_time from {} where robot_id = {}".format(table_name, robot_id)
    totaldata = db.select_db(sqltotal)
    json_list = []
    for i in totaldata:
        if i["create_time"] != None and i["create_time"] != '':
            i["create_time"] = i["create_time"].strftime("%Y-%m-%d %H:%M:%S")
        json_list.append(i)
    print("GetCamera_pointsBycameraid:", json_list)

    _robot_point_position_value_convert(json_list)
    req.code = 0
    req.msg = "读取成功"
    req.data = json_list
    return json.dumps(req.__dict__, ensure_ascii=False)

'''
   30.2 发送机器人移动指令
'''
def _command_input_parese_print(opt_cmd, opt_pos):
    '''
    解析操作码，打印对应的操作信息
    :param opt_cmd: 操作码
    :return:
    '''
    opt_cmd_print_info = {
        0: '无效命令',
        1: '左行 ',
        2: '右行',
        3: '下降',
        4: '上升',
        5: '灯光',
        6: '高速',
        7: '调用预置点位',
        8: '查询位置',
        # 9: '设置预置点位'
    }
    opt_switch_print_info = {
        1: '开',
        0: '关'
    }

    # 参数校验
    if opt_cmd is None or opt_cmd == '' or opt_pos is None or opt_pos == '':
        print("opt_cmd/opt_pos is None or empty")
        return -1

    opt_cmd_int = int(opt_cmd)
    opt_pos_int = int(opt_pos)

    if opt_cmd_int in opt_cmd_print_info:
        if opt_cmd_int in [7]:  # 预置点命令
            if opt_pos is not None:
                print("Received command: {} - {}, preset point ID: {}".format(
                    opt_cmd_int,
                    opt_cmd_print_info[opt_cmd_int],
                    opt_pos
                ))
            else:
                print("Received command: {} - {}, preset point ID: Not provided".format(
                    opt_cmd_int,
                    opt_cmd_print_info[opt_cmd_int]
                ))
        elif opt_cmd_int in [1, 6]:   # 普通开关命令
            if opt_pos_int != 0 and opt_pos_int != 1:
                print("switch value invalid for command {}, must be 0[off] or 1[on]".format(opt_cmd_print_info[opt_cmd_int]))
                return -1
            print("Received command: {} - {}, switch:{} - {}".format(
                    opt_cmd_int,
                    opt_cmd_print_info[opt_cmd_int],
                    opt_pos_int,
                    opt_switch_print_info[opt_pos_int]
                ))
        else: #查询位置坐标
            print("Received command: {} - {}".format(
                    opt_cmd_int,
                    opt_cmd_print_info[opt_cmd_int]
                ))
        return 0    
    else:
        print("Received command: {} - Unknown command".format(opt_cmd_int))
        return -1

# 更新预置点位成功后,更新使能状态
def _set_enbale_status_by_presetID(robot_id, preset_id):
    code = 0
    msg = ''
    table_name = 'm_robot_point'

    try:
        sql = "UPDATE {} SET point_enable = 0;".format(table_name)
        db.select_db(sql)
        try:
            sql = "UPDATE {} SET point_enable = 1 WHERE id = {} and robot_id={};".format(table_name, preset_id, robot_id)
            db.select_db(sql)
            code = 0
            msg = '操作成功'
        except Exception as e:
            code = 3
            msg = "No robot found in database:{}".format(e)
    except Exception as e:
        code = 3
        msg = "No robot found in database:{}".format(e)

    return code, msg
    

# 发送机器人移动指令
# opt_cmd  : 操作码
# opt_param: 参数
@realtimealarm.route('/Robot_control', methods=["post"])
def RobotControl_command():

    '''
    发送机器人移动指令
    :param robot_id:  机器人的身份识别ID
    :param opt_cmd :  操作码
    :param opt_param: 参数
    :return:
    '''

    table_name = 'm_robot'
    req = ReqResult()
    robot_id = request.form.get("robot_id")
    opt_cmd = request.form.get("opt_cmd")
    opt_param = request.form.get("opt_param")
    print("rcv opt_cmd:{}, opt_pos:{}".format(opt_cmd, opt_param))

    command_dic = {
        'robot_id': robot_id,
        'opt_cmd': opt_cmd,
        'opt_param': opt_param
    }
    err_msg=[]

    command_json = json.dumps(command_dic)
    print("Sending robot move command:", command_json)
    # 这里添加实际发送命令的代码，例如通过消息队列或HTTP请求发送给机器人控制系统

    # 参数校验
    if robot_id is None or robot_id == '':
        req.code = 1
        req.msg = "robot_id is required"
        return json.dumps(req.__dict__, ensure_ascii=False)
    
    if (0 != _command_input_parese_print(opt_cmd, opt_param)):
        req.code = 2
        req.msg = "opt_cmd is invalid, opt_cmd:" + str(opt_cmd) + ", opt_pos:" + str(opt_param)
        return json.dumps(req.__dict__, ensure_ascii=False)

    #robot_id校验：根据robot_id获取对应的设备信息
    sql = "SELECT * FROM {} WHERE id = {}".format(table_name, robot_id)
    iitem = db.select_db(sql)
    if not iitem:
        req.code = 3
        req.msg = "No robot found in database:" + table_name + " with ID:" + robot_id
        return json.dumps(req.__dict__, ensure_ascii=False)

    robot_ip    = iitem[0]["robot_ip"]
    robot_port  = iitem[0]["robot_port"]

    # 拼接发送命令字符串
    str_cmd = str(opt_cmd) + ' ' + str(opt_param)
    req.code, req.msg = _sendOptInfoToDev(robot_ip, str_cmd, robot_port)

    # 确认预置点位在列表中的使能状态
    if 7 == int(opt_cmd):
        req.code, req.msg = _set_enbale_status_by_presetID(robot_id, opt_param)


    return json.dumps(req.__dict__, ensure_ascii=False)

def _get_value_from_request(value, type_needed):
    if value == None:
        if type_needed == string:
            return ''
        elif type_needed == int:
            return 0
        else:
            return value
    else:
        return value

'''
   31.1 新增一条表计的点位信息
'''
# 添加表计信息
# INPUT:
#            name       表计名称
#            #type       表计类型:1:LED_红,2:LED_绿;3:旋钮开关; 4:LED_黄; 5:LED_白;6:压板开关;7:表针;其他:待添加
#            pos_x      由用户输入的横坐标x
#            pos_y      由用户输入的横坐标y
#            pos_w      由用户输入的距离(x,y)的宽度
#            pos_h      由用户输入的距离(x,y)的高度
@realtimealarm.route('/AddMeterPresetInfo', methods=["post"])
def AddMeterPresetInfo():
    table_name = 'm_metername_point'
    req = ReqResult()
    name= request.form.get("name")
    pos_x = request.form.get("pos_x")
    pos_y = request.form.get("pos_y")
    pos_h = request.form.get("pos_h")
    pos_w = request.form.get("pos_w")

    if name == None or name == '':
        req.code = 1
        req.msg= "参数缺失:meter name is needed."
        return json.dumps(req.__dict__, ensure_ascii=False) 

    if pos_x == None or pos_x == '' or pos_y == None or pos_y == '' \
        or pos_h == None or pos_h == '' or pos_w == None or pos_w == '':
        req.code = 2
        req.msg= "参数缺失: postion info (x,y),(w,h) is needed."
        return json.dumps(req.__dict__, ensure_ascii=False) 

    current_app.logger.info("recv:name:{}, pos_x:{}, pos_y:{}, pos_h:{}, pos_w:{}".format(name, pos_x, pos_y, pos_h, pos_w))
  
    select_maxid_sql = 'select max(id) as maxid from {}'.format(table_name)
    select_maxid_result = db.select_db(select_maxid_sql)
    id = 0
    if select_maxid_result[0]['maxid'] is None:
        id = 1
    else:
        id = int(select_maxid_result[0]['maxid']) + 1

    insert_dic = {
        'id': id,
        'name':name,
        'type': 0,
        'pos_x':pos_x,
        'pos_y':pos_y,
        'pos_h':pos_h,
        'pos_w':pos_w,
        'create_time': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    try:
        db.insertData(table_name, insert_dic)
        current_app.logger.info("Inserted meter preset info: {}".format(insert_dic))
        req.code = 0
        req.msg = "操作成功"
    except Exception as e:
        req.code = 2
        req.msg = e

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
   31.2 修改/更新一条表计点位信息
'''
# 更新表计信息
#  INPUT    :
#  id           列表唯一识别号ID(必选项)
#  name         表计名称        (可选)前端写入
#  type         表计类别        (可选)暂不使用
#  pos_x        位置坐标x       (可选)前端写入
#  pos_y        位置坐标y       (可选)前端写入
#  pos_w        位置坐标w       (可选)前端写入
#  pos_h        位置坐标h       (可选)前端写入
@realtimealarm.route('/ModifyMeterPresetInfo', methods=["post"])
def ModifyMeterPresetInfoByID():
    table_name = 'm_metername_point'
    req = ReqResult()

    try:
        # 检查输参数合法性
        id = int(request.form.get("id"))
    except (TypeError, ValueError):
        req.code = 1
        req.msg = "参数不正确: id must be needed and type is integer."
        return json.dumps(req.__dict__, ensure_ascii=False)

    name  = request.form.get("name")
    pos_x = request.form.get("pos_x")
    pos_y = request.form.get("pos_y")
    pos_w = request.form.get("pos_w")
    pos_h = request.form.get("pos_h")
    meter_type = request.form.get("type")

    current_app.logger.info("Recv modify info:id:{}, name:{}, type:{}".format(id, name, meter_type))
    current_app.logger.info("                :pos_x:{}, pos_y:{}, pos_w:{}, pos_h:{}".format(pos_x, pos_y, pos_w,pos_h))
    

    if not db.checkIdExist(table_name, id):
        req.code = 2
        req.msg = 'ID:{} not found in table:{}'.format(id, table_name)
        return json.dumps(req.__dict__, ensure_ascii=False)
    
    try:
        new_meterinfo_dic = {}  #save all data you wanted as dict.

        if name != None and name != '':
            new_meterinfo_dic['name'] = name
        if meter_type != None and meter_type != '':
            new_meterinfo_dic['type'] = meter_type
        # mark position
        if pos_x != None and pos_x != '':
            new_meterinfo_dic['pos_x'] = pos_x
        if pos_y != None and pos_y != '':
            new_meterinfo_dic['pos_y'] = pos_y
        if pos_w != None and pos_w != '':
            new_meterinfo_dic['pos_w'] = pos_w
        if pos_h != None and pos_h != '':
            new_meterinfo_dic['pos_h'] = pos_h

        wheresql = 'id={};'.format(id)
        updateresult = db.updateData(table_name, new_meterinfo_dic, wheresql)

        # sqltatol += "where id = {}".format(id)
        # db.execute_db(sqltatol)
        req.code = 0
        req.msg = "success"

    except Exception as e:
        req.code = 3
        req.msg = "Modify failed:" + e

    return json.dumps(req.__dict__, ensure_ascii=False)

'''
   31.3 删除一条表计点位信息
'''
# 删除表计信息
#  INPUT    :
#  id           列表唯一识别号ID
@realtimealarm.route('/DeleteMeterPresetInfo', methods=["post"])
def DeleteMeterPresetInfoByID():
    table_name = 'm_metername_point'
    req = ReqResult()
    id = request.form.get("id")
  
    # 检查输参数合法性
    if id == None or id == '':
        req.code = 1
        req.msg= "参数不正确"
        return json.dumps(req.__dict__)
    
    if not db.checkIdExist(table_name, id):
        req.code = 2
        req.msg = 'ID:{} not found in table:{}'.format(id, table_name)
        return json.dumps(req.__dict__, ensure_ascii=False)

    try:
        sql = "delete from {} where id={}".format(table_name, id)
        print("----DeleteModelInfo sql:", sql)
        db.execute_db(sql)
        print("----DeleteModelInfo sql over!")
        req.code = 0
        req.msg = "success"

    except Exception as e:
        req.code = 3
        req.msg = "Delete ID:{} from {} failed:".format(id, table_name) + e

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
   31.4 根据ID查询对应表计的点位信息
'''
@realtimealarm.route('/GetMeterPresetInfoByID', methods=["post"])
def GetMeterPresetInfoByID():
    table_name = 'm_metername_point'
    req = ReqResult()
    id = request.form.get("id")
 
    # 检查输参数合法性
    if id == None or id == '':
        req.code = 1
        req.msg= "参数不正确"
        return json.dumps(req.__dict__)
    
    sql = "select * from {} where id={}".format(table_name, id)
    totaldata = db.select_db(sql)
    if len(totaldata) <= 0:
        req.code = 2
        req.msg = 'ID:{} not found in table:{}'.format(id, table_name)
        return json.dumps(req.__dict__, ensure_ascii=False) 
        
    json_list = []
    for i in totaldata:
        i["create_time"] = i["create_time"].strftime("%Y-%m-%d %H:%M:%S")
        json_list.append(i)

    req.code = 0
    req.msg = "读取成功"
    req.data = totaldata

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
   31.5 查询所有表计的点位信息
'''
@realtimealarm.route('/GetAllMeterPresetInfoList', methods=["post"])
def GetAllMeterPresetInfo():
    table_name = 'm_metername_point'
    req = ReqResult()

    sql = "select * from {}".format(table_name)
    totaldata = db.select_db(sql)
    if len(totaldata) <= 0:
        req.code = 1
        req.msg = 'Info not found in table:{}'.format(table_name)
        return json.dumps(req.__dict__, ensure_ascii=False) 
    
    json_list = []
    for i in totaldata:
        i["create_time"] = i["create_time"].strftime("%Y-%m-%d %H:%M:%S")
        json_list.append(i)

    req.code = 0
    req.msg = "读取成功"
    req.data = totaldata

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
   31.6  增加一条与任务ID和子任务ID相关连的表计信息(创建一个类型为表计的子任务时)
'''
@realtimealarm.route('/AddMeterInfo', methods=["post"])
def AddMeternameByPlanInfoID():
    table_name      = 'm_visitationplaninfo_meter'
    req             = ReqResult()

    try:
        # 新增接口至少应该包含任务ID/子任务ID和表计名称ID/点位ID/摄像头ID/变电站ID/机房ID
        planid          = int(request.form.get("planid"))
        planinfoid      = int(request.form.get("planinfoid"))
        station_id      = int(request.form.get("station_id"))
        stationroom_id  = int(request.form.get("stationroom_id"))
        camera_id       = int(request.form.get("camera_id"))
        metername_id    = int(request.form.get("metername_id"))
    except Exception as e:
        req.code = 1
        req.msg= "缺少参数: planid / planinfoid /  station_id / stationroom_id / camera_id / metername_id is needed."
        return json.dumps(req.__dict__, ensure_ascii=False)

    current_app.logger.info("recv:plan_id:{}, plan_info_id:{}, meternameid:{}".format(planid, planinfoid, metername_id))

    # 确认各ID在对应表中存在
    if not db.checkIdExist('m_stationinfo', station_id):
        req.code = 2
        req.msg = 'station_id:{} not found in table:{}'.format(station_id, 'm_stationinfo')
        return json.dumps(req.__dict__, ensure_ascii=False)
    
    if not db.checkIdExist('m_stationroom', stationroom_id):
        req.code = 2
        req.msg = 'stationroom_id:{} not found in table:{}'.format(stationroom_id, 'm_stationroom')
        return json.dumps(req.__dict__, ensure_ascii=False)

    if not db.checkIdExist('m_camera', camera_id, "camera_id"):
        req.code = 2
        req.msg = 'camera_id:{} not found in table:{}'.format(camera_id, 'm_camera')
        return json.dumps(req.__dict__, ensure_ascii=False)

    if not db.checkIdExist('m_metername_point', metername_id):
        req.code = 2
        req.msg = 'metername_id:{} not found in table:{}'.format(metername_id, 'm_metername_point')
        return json.dumps(req.__dict__, ensure_ascii=False)

    select_maxid_sql = 'select max(id) as maxid from {}'.format(table_name)
    select_maxid_result = db.select_db(select_maxid_sql)
    id = 0
    if select_maxid_result[0]['maxid'] is None:
        id = 1
    else:
        id = int(select_maxid_result[0]['maxid']) + 1

    insert_dic = {
        'id': id,
        'planid': planid,
        'planinfoid': planinfoid,
        'station_id':station_id,
        'stationroom_id':stationroom_id,
        'camera_id':camera_id,
        'metername_id':metername_id,
        'value_int': 0,
        'value_str': '',
        'imgname':'',
        'create_time': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    try:
        db.insertData(table_name, insert_dic)
        req.code = 0
        req.msg = "操作成功"
    except Exception as e:
        req.code = 2
        req.msg = e

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
31.7  删除一条与任务ID和子任务ID相关连的表计信息  (任务类型为表计的子任务)
'''
@realtimealarm.route('/DeleteMeterInfoByID', methods=["post"])
def DeleteMeterInfoByID():
    table_name = 'm_visitationplaninfo_meter'
    req = ReqResult()
    id = request.form.get("id")
  
    # 检查输参数合法性
    if id == None or id == '':
        req.code = 1
        req.msg= "参数不正确"
        return json.dumps(req.__dict__)
    
    if not db.checkIdExist(table_name, id):
        req.code = 2
        req.msg = 'metername_id:{} not found in table:{}'.format(id, 'm_metername_point')
        return json.dumps(req.__dict__, ensure_ascii=False)

    try:
        sql = "delete from {} where id={}".format(table_name, id)
        print("----DeleteModelInfo sql:", sql)
        db.execute_db(sql)
        print("----DeleteModelInfo sql over!")
        req.code = 0
        req.msg = "success"

    except Exception as e:
        req.code = 3
        req.msg = "Delete ID:{} from {} failed:".format(id, table_name) + e

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
   31.8  修改一条与任务ID和子任务ID相关连的表计信息
'''
@realtimealarm.route('/ModifyMeterInfo', methods=["post"])
def ModifyMeterInfoByID():
    table_name      = 'm_visitationplaninfo_meter'

    req             = ReqResult()
    id              = request.form.get("id")
    station_id      = request.form.get("station_id")
    stationroom_id  = request.form.get("stationroom_id")
    camera_id       = request.form.get("camera_id")
    metername_id    = request.form.get("metername_id")

    value_int   = request.form.get("value_int")
    value_str   = request.form.get("value_str")
    meter_type  = request.form.get("type")
    imgname     = request.form.get("imgname")

    current_app.logger.info("Recv modify info:id:{}, metername_id:{}, type:{}, value_int:{},value_str:{}".format(id, metername_id, meter_type,value_int,value_str))
    
    # 检查输参数合法性
    if id == None or id == '':
        req.code = 1
        req.msg= "缺少参数:id"
        return json.dumps(req.__dict__)
    
    if not db.checkIdExist(table_name, id):
        req.code = 2
        req.msg = 'ID:{} not found in table:{}'.format(id, table_name)
        return json.dumps(req.__dict__, ensure_ascii=False) 
    
    try:
        new_meterinfo_dic = {}  #save all data you wanted as dict.

        if station_id != None and station_id != '':
            new_meterinfo_dic['station_id'] = station_id
        if stationroom_id != None and stationroom_id != '':
            new_meterinfo_dic['stationroom_id'] = stationroom_id
        if camera_id != None and camera_id != '':
            new_meterinfo_dic['camera_id'] = camera_id
        if metername_id != None and metername_id != '':
            new_meterinfo_dic['metername_id'] = metername_id

        if value_int != None and value_int != '':
            new_meterinfo_dic['value_int'] = value_int
        if value_str != None and value_str != '':
            new_meterinfo_dic['value_str'] = value_str

        if imgname != None and imgname != '':
            new_meterinfo_dic['imgname'] = imgname

        wheresql = 'id={};'.format(id)
        db.updateData(table_name, new_meterinfo_dic, wheresql)

        req.code = 0
        req.msg = "success"

    except Exception as e:
        req.code = 3
        req.msg = "Modify failed:" + e

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
   31.9  根据ID号,获取一条与任务ID和子任务ID关联的表计信息
'''
@realtimealarm.route('/GetMeterInfoByID', methods=["post"])
def GetMeterInfoByID():
    table_name = 'm_visitationplaninfo_meter'
    req = ReqResult()
    id = request.form.get("id")
 
    # 检查输参数合法性
    if id == None or id == '':
        req.code = 1
        req.msg= "参数不正确"
        return json.dumps(req.__dict__)
    
    sql = "select * from {} where id={}".format(table_name, id)
    totaldata = db.select_db(sql)
    if len(totaldata) <= 0:
        req.code = 2
        req.msg = 'ID:{} not found in table:{}'.format(id, table_name)
        return json.dumps(req.__dict__, ensure_ascii=False) 
        
    json_list = []
    for i in totaldata:
        i["create_time"] = i["create_time"].strftime("%Y-%m-%d %H:%M:%S")
        json_list.append(i)

    req.code = 0
    req.msg = "读取成功"
    req.data = totaldata

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
   31.10 根据计划子任务ID,获取该子任务下的所有表计信息
    #  INPUT:
    #  planinfoid:子任务ID号
'''
@realtimealarm.route('/GetMeterInfoListByPlanInfoID', methods=["post"])
def GetMeterInfoByPlanInfoID():
    table_name = 'm_visitationplaninfo_meter'
    req = ReqResult()
    planinfoid = request.form.get("planinfoid")

    # 检查输参数合法性
    if planinfoid == None or planinfoid == '':
        req.code = 1
        req.msg= "参数缺失:planinfoid"
        return json.dumps(req.__dict__)
    
    sql = "select * from {} where planinfoid={}".format(table_name, planinfoid)
    totaldata = db.select_db(sql)
    if len(totaldata) <= 0:
        req.code = 2
        req.msg = 'planinfoid:{} not found in table:{}'.format(planinfoid, table_name)
        return json.dumps(req.__dict__, ensure_ascii=False) 
    
    json_list = []
    for i in totaldata:
        i["create_time"] = i["create_time"].strftime("%Y-%m-%d %H:%M:%S")
        json_list.append(i)

    req.code = 0
    req.msg = "读取成功"
    req.data = totaldata

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
   31.11 获取识别后的所有表记值列表集合
    #  INPUT:无
'''
@realtimealarm.route('/GetAllMeterInfoList', methods=["post"])
def GetAllMeterInfoList():
    table_name_meterinfo = 'm_visitationplaninfo_meter'
    table_name_meterpoint = 'm_metername_point'
    req = ReqResult()

    # 先根据表计名称ID，获取所有表计名称和对应的识别值
    # 两个关联的表：m_visitationplaninfo_meter , m_metername_point
    # 返回给前端数据时，应该包含：id, metername_id, metername, value_str
    # 目前只返回id, metername_id, value_str，前端根据metername_id再去m_metername_point表中获取名称
    # 再将id, metername_id, metername, value_str返回给前端
    sql = "SELECT t1.id, t2.name, t1.value_str FROM {} t1 \
            LEFT JOIN {} t2 ON t1.metername_id = t2.id ".format(table_name_meterinfo, table_name_meterpoint)
    try:
        totaldata = db.select_db(sql)
        if len(totaldata) <= 0:
            req.code = 1
            req.msg = 'Not found:' + table_name_meterinfo
            return json.dumps(req.__dict__, ensure_ascii=False)

    except Exception as e:
        req.code = 3
        req.msg = "Get failed:" + str(e)

    req.code = 0
    req.msg = "读取成功"
    req.data = totaldata

    return json.dumps(req.__dict__, ensure_ascii=False)