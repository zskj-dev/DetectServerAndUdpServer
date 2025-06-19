from flask import Blueprint, render_template, redirect, request, current_app, send_file
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
from PIL import Image, ImageDraw
import io

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
    "severe_alert": (255, 0, 0),  # 鲜艳的红色，用于严重告警
    "high_warning": (255, 69, 0),  # 橙红色，用于高优先级警告
    "medium_warning": (255, 140, 0),  # 亮橙色（偏红），用于中等优先级警告
    "low_notice": (255, 192, 203),  # 浅粉红色，用于低优先级通知
    "critical_error": (139, 0, 0),  # 深红色，用于关键错误
    "minor_issue": (255, 20, 147),  # 紫红色，用于次要问题
    "emergency_alert": (255, 99, 71),  # 鲜亮的番茄红，用于紧急告警
    "resolved_alert": (188, 143, 143),  # 淡玫瑰红色，用于已解决的告警（可选）
}
realtimealarm = Blueprint('RealtimeAlarm', __name__)


def getModelFileNameAndCurErrLevel():
    systemsetting = {}
    sqltotal = "select a.filename,a.id from m_model a where a.flag = 1"
    totaldata = db.select_db(sqltotal)
    # print("getSystemConfig:", totaldata[0]["filename"])
    systemsetting["filename"] = totaldata[0]["filename"]
    systemsetting["fileid"] = totaldata[0]["id"]
    sqltotal = "select curerrlevel from m_systemsetting"
    totaldata = db.select_db(sqltotal)
    # print("getSystemConfig:",totaldata[0]["curerrlevel"])
    systemsetting["curerrlevel"] = totaldata[0]["curerrlevel"]
    return systemsetting


def getModelFileTypeErrLevel(modelid, syslevel):
    li = {}
    sqltotal = "select modelid, errtypeindex, errtypename, errtypelevel from m_modelinfo where modelid = {}".format(
        modelid)
    totaldata = db.select_db(sqltotal)

    for item in totaldata:
        if item['errtypelevel'] >= syslevel:
            li[str(item['errtypeindex'])] = 1
        else:
            li[str(item['errtypeindex'])] = 0
    # print("getModelFileTypeErrLevel:",li)

    return li


'''
    2.图片下载预览
'''


@realtimealarm.route('/download/<filename>', methods=["post", "get"])
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
        return send_file(file_path, as_attachment=False)
    else:
        # 如果文件不存在，返回404错误
        return "File not found", 404


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1] in ALLOWED_EXTENSIONS


'''
    1.检测
'''


@realtimealarm.route('/detection', methods=["post", "get"])
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
                # 文件上传目录地址
                random_str = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
                filenamea = secure_filename(random_str + f.filename)
                upload_path = os.path.join(outputpath, filenamea)
                rgb_img.save(upload_path)
                # img.save(processed_bytes, format="PNG")

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
            "clsname": model.names[int(most_common_type)]
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
    print("token", request.form.get("token"))
    token = request.form.get("token")
    current_app.logger.info('GetCurAlarmMaxID   token:{}'.format(token))

    sql = "select max(id) as id from v_errlist where state != 3"
    maxid = db.select_db(sql)
    print(maxid)
    req = ReqResult()
    if len(maxid) == 0:
        req.code = 1
        req.msg = "获取数据失败"
    else:
        #req.data = maxid[0]["id"]
        req.data = maxid[0][0]
    return json.dumps(req.__dict__, ensure_ascii=False)


'''
    3.1获取告警最大ID
'''


@realtimealarm.route('/GetCurAlarmMaxID', methods=["post"])
def GetCurAlarmMaxID():
    print("token", request.form.get("token"))
    token = request.form.get("token")
    current_app.logger.info('GetCurAlarmMaxID   token:{}'.format(token))

    sql = "select max(id) as id from v_errlist where state = 3"
    maxid = db.select_db(sql)
    req = ReqResult()
    if len(maxid) == 0:
        req.code = 1
        req.msg = "获取数据失败"
    else:
        #req.data = maxid[0]["id"]
        req.data = maxid[0][0]
    return json.dumps(req.__dict__, ensure_ascii=False)


'''
    4.获取实时告警列表
'''


@realtimealarm.route('/GetCurAlarmList', methods=["post"])
def GetCurAlarmList():
    print("pagesize", request.form.get("pagesize"))
    print("pagenum", request.form.get("pagenum"))

    pagesize = request.form.get("pagesize")
    pagenum = request.form.get("pagenum")
    token = request.form.get("token")
    req = ReqResult()
    if pagesize == None or pagenum == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('GetCurAlarmList   token:{},pagesize:{},pagenum:{}'.format(token, pagesize, pagenum))
    return getlist(0, pagesize, pagenum)


'''
    4.1获取全部终端上报信息列表
'''


@realtimealarm.route('/GetAllAlarmMsgList', methods=["post"])
def GetAllAlarmMsgList():
    print("pagesize", request.form.get("pagesize"))
    print("pagenum", request.form.get("pagenum"))

    pagesize = request.form.get("pagesize")
    pagenum = request.form.get("pagenum")
    token = request.form.get("token")
    req = ReqResult()
    if pagesize == None or pagenum == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('GetCurAlarmList   token:{},pagesize:{},pagenum:{}'.format(token, pagesize, pagenum))
    return getlist(1, pagesize, pagenum)


'''
    4.2获取标记误报告警列表
'''


@realtimealarm.route('/GetAllMsgMistakeList', methods=["post"])
def GetAllMsgMistakeList():
    print("pagesize", request.form.get("pagesize"))
    print("pagenum", request.form.get("pagenum"))

    pagesize = request.form.get("pagesize")
    pagenum = request.form.get("pagenum")
    token = request.form.get("token")
    req = ReqResult()
    if pagesize == None or pagenum == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('GetCurAlarmList   token:{},pagesize:{},pagenum:{}'.format(token, pagesize, pagenum))
    return getlist(2, pagesize, pagenum)


'''
    4.3获取所有告警数据信息
'''


@realtimealarm.route('/GetAllMsgList', methods=["post"])
def GetAllMsgList():
    print("pagesize", request.form.get("pagesize"))
    print("pagenum", request.form.get("pagenum"))

    pagesize = request.form.get("pagesize")
    pagenum = request.form.get("pagenum")
    token = request.form.get("token")
    req = ReqResult()
    if pagesize == None or pagenum == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('GetAllMsgList   token:{},pagesize:{},pagenum:{}'.format(token, pagesize, pagenum))
    return getlist(3, pagesize, pagenum)


'''
    4.4 获取加标记的信息数据数据
'''


@realtimealarm.route('/GetAllMsgFlagList', methods=["post"])
def GetAllMsgFlagList():
    pagesize = request.form.get("pagesize")
    pagenum = request.form.get("pagenum")
    token = request.form.get("token")
    req = ReqResult()
    if pagesize == None or pagenum == None:
        req.code = 1
        req.msg = "参数不正确"
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


def getlist(type, pagesize, pagenum):
    req = ReqResult()
    sql = ""
    if type == 0:
        sql = "select * from v_errlist where optflag1 =0 and confirm =0 and state = 3 ORDER BY id desc limit {},{}".format(
            str((int(pagenum) - 1) * int(pagesize)), str(pagesize))
    elif type == 1:
        sql = "select * from v_errlist where state != 3 ORDER BY id desc limit {},{}".format(
            str((int(pagenum) - 1) * int(pagesize)), str(pagesize))
    elif type == 2:
        sql = "select * from v_errlist where optflag1 =1 and confirm =1 and state = 3 ORDER BY id desc limit {},{}".format(
            str((int(pagenum) - 1) * int(pagesize)), str(pagesize))
    elif type == 3:
        sql = "select * from v_errlist  ORDER BY id desc limit {},{}".format(
            str((int(pagenum) - 1) * int(pagesize)), str(pagesize))
    elif type == 4:
        sql = "select * from v_errlist where flag=1 ORDER BY id desc limit {},{}".format(
            str((int(pagenum) - 1) * int(pagesize)), str(pagesize))
    else:
        sql = "select * from v_errlist ORDER BY id desc limit {},{}".format(
            str((int(pagenum) - 1) * int(pagesize)), str(pagesize))

    print("--------getlist sql:", sql)
    listdata = db.select_db(sql)
    print("--------getlist listdatalen:", len(listdata))

    if len(listdata) == 0:
        req.code = 1
        req.msg = "获取数据失败,listdata为空"
    else:
        json_list = []

        for i in listdata:
            i["updatetime"] = i["updatetime"].strftime("%Y-%m-%d %H:%M:%S")
            json_list.append(i)

        sqltotal = ""  # "select count(*) as cnt from v_errlist where opsts != 20"
        if type == 0:
            sqltotal = "select count(*) as cnt from v_errlist where optflag1 =0 and confirm =0 and state = 3"
        elif type == 1:
            sqltotal = "select count(*) as cnt from v_errlist where state != 3"
        elif type == 2:
            sqltotal = "select count(*) as cnt from v_errlist where optflag1 =1 and confirm =1 and state = 3 "
        elif type == 3:
            sqltotal = "select count(*) as cnt from v_errlist"
        elif type == 4:
            sqltotal = "select count(*) as cnt from v_errlist where flag=1"
        else:
            sqltotal = "select count(*) as cnt from v_errlist"

        totaldata = db.select_db(sqltotal)
        current_app.logger.info('getlist totaldata:{}'.format(totaldata))
        # print(json_list)
        # ret1 = json.dumps(json_list)
        # print(ret1)

        dateInfo = {}
        dateInfo["datas"] = json_list
        dateInfo["count"] = len(json_list)
        dateInfo["total"] = totaldata[0]["cnt"]
        if len(json_list) == 0:
            req.code = 1
            req.msg = "获取数据失败,json_list为空"
        else:
            req.code = 0
            req.msg = "success"
        req.data = dateInfo
    return json.dumps(req.__dict__, ensure_ascii=False)
    # return json.dumps(req.__dict__)


'''
    4.5. 标记信息
'''


@realtimealarm.route('/UpdateMsgFlag', methods=["post"])
def UpdateMsgFlag():
    id = request.form.get("id")
    flag = request.form.get("flag")
    req = ReqResult()
    if id == None or flag == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('UpdateMsgFlag   id:{},flag:{}'.format(id, flag))
    sql = "update m_errorinfo set flag={} where id={}".format(flag, id)
    db.execute_db(sql)
    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
    4.6. 标记误报信息
'''


@realtimealarm.route('/UpdateMsgMistakeFlag', methods=["post"])
def UpdateMsgMistakeFlag():
    id = request.form.get("id")
    flag = request.form.get("flag")
    req = ReqResult()
    if id == None or flag == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('UpdateMsgFlag   id:{},flag:{}'.format(id, flag))
    sql = "update m_errorinfo set flag={},confirm =1  where id={}".format(flag, id)
    db.execute_db(sql)
    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
    4.7. 确定消息
'''


@realtimealarm.route('/UpdateMsgConfirmState', methods=["post"])
def UpdateMsgConfirmState():
    id = request.form.get("id")
    req = ReqResult()
    if id == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('UpdateMsgFlag   id:{}'.format(id))
    sql = "update m_errorinfo set confirm =1  where id={}".format(id)
    db.execute_db(sql)
    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
    4.8. 确定多个消息
'''


@realtimealarm.route('/UpdateMsgsConfirmState', methods=["post"])
def UpdateMsgsConfirmState():
    print("ids", request.form.get("ids"))
    ids = request.form.get("ids")
    req = ReqResult()
    if ids == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('UpdateMsgFlag   id:{}'.format(ids))
    sql = "update m_errorinfo set confirm = 1  where id in ({})".format(ids)
    db.execute_db(sql)
    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
    4.9. 标记多个误报信息
'''
@realtimealarm.route('/UpdateMsgsMistakeFlag', methods=["post"])
def UpdateMsgsMistakeFlag():
    ids = request.form.get("ids")
    flag = request.form.get("flag")
    req = ReqResult()
    if ids == None or flag == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('UpdateMsgFlag   ids:{},flag:{}'.format(ids, flag))
    sql = "update m_errorinfo set flag={},confirm = 1  where id in ({})".format(flag, ids)
    db.execute_db(sql)
    req.code = 0
    req.msg = "success"
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
    id = request.form.get("modelid")
    pagesize = request.form.get("pagesize")
    pagenum = request.form.get("pagenum")
    token = request.form.get("token")
    req = ReqResult()
    if pagesize == None or pagenum == None or id == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('GetCurAlarmList   token:{},pagesize:{},pagenum:{}'.format(token, pagesize, pagenum))

    sql = "select * from m_modelinfo  where modelid={} ORDER BY errtypeindex desc limit {},{}".format(id,
                                                                                                      str((
                                                                                                                      int(pagenum) - 1) * int(
                                                                                                          pagesize)),
                                                                                                      str(pagesize))

    print("--------GetErrorTypeList sql:", sql)
    listdata = db.select_db(sql)
    print("--------GetErrorTypeList listdatalen:", len(listdata))
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
    sql = "update m_modelinfo set errtypeindex={}, errtypename='{}',  errtypelevel={},tips='{}'  where id={}".format(
        errtypeindex, errtypename, errtypelevel, tips, id)
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
    current_app.logger.info(
        'AddErrorTypeAlarm  modelid:{}  errortype:{},errorname:{},alarmtype:{},tips:{}'.format(modelid, errtypeindex,
                                                                                               errtypename,
                                                                                               errtypelevel, tips))

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
        'tips': tips
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
    id = request.form.get("id")
    req = ReqResult()
    if id == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('DeleteErrorTypeAlarm   errortype:{}'.format(id))

    sql = "delete from m_modelinfo where id={}".format(id)
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
    print("GetStationList:", totaldata)

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
    print("GetCamListByStation:", totaldata)

    req = ReqResult()
    req.code = 0
    req.msg = "读取成功"
    req.data = totaldata

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
    9. 告警数据下载（get）
'''
@realtimealarm.route('/GetAllMsgInfoFile/<msgtype>', methods=["post", "get"])
def GetAllMsgInfoFile(msgtype):
    # msgtype = request.form.get("msgtype")
    msgtype = int(msgtype)
    sqltotal = ""
    if msgtype == 0:
        sqltotal = """select * from v_errlist  where state = 3 ORDER BY id; """
    elif msgtype == 1:
        sqltotal = """select * from v_errlist  where state != 3 ORDER BY id; """
    elif msgtype == 2:
        sqltotal = """select * from v_errlist  where flag = 1 ORDER BY id; """
    else:
        sqltotal = """select * from v_errlist  ORDER BY id; """
    print("GetCamListByStation sqltotal:", sqltotal)
    totaldata = db.select_db(sqltotal)
    print("GetCamListByStation:", totaldata)
    random_str = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
    filename = random_str + '_output.csv'
    fipath = os.path.join("./files", filename)
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
    stationname = request.form.get("stationname")
    type = request.form.get("type")
    position = request.form.get("position")
    req = ReqResult()
    if type == None or position == None or stationname == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('AddStationInfo   stationname:{},type:{},position:{}'.format(stationname, type, position))

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
        'type': type,
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
    id = request.form.get("id")
    stationname = request.form.get("stationname")
    type = request.form.get("type")
    position = request.form.get("position")
    req = ReqResult()
    if type == None or position == None or stationname == None or id == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info(
        'ModifyStationInfo   id:{}, stationname:{},type:{},position:{}'.format(id, stationname, type, position))

    sql = "update m_stationinfo set stationname='{}',type='{}',position='{}' where id={}".format(
        stationname, type, position, id)
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
    id = request.form.get("id")
    req = ReqResult()
    if id == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('DeleteStationInfo   id:{}'.format(id))

    sql = "delete from m_stationinfo where id={}".format(id)
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
    stationid = request.form.get("stationid")
    if stationid == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    sqltotal = "select * from m_stationroom  where stationid={}".format(stationid)
    totaldata = db.select_db(sqltotal)
    print("GetStationList:", totaldata)
    req.code = 0
    req.msg = "读取成功"
    req.data = totaldata

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
   10.1 添加变电站房间
'''
@realtimealarm.route('/AddStationRoom', methods=["post"])
def AddStationRoom():
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
        'roomname': roomname
    }
    print("----111111111-----", insert_dic)
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
    id = request.form.get("id")
    req = ReqResult()
    if id == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('DeleteStationRoom   id:{}'.format(id))

    sql = "delete from m_stationroom where id={}".format(id)
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
    stationid = request.form.get("stationid")
    if stationid == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('GetStationDVRList   stationid:{}'.format(stationid))
    sqltotal = "select * from m_dvr  where stationid={}".format(stationid)
    totaldata = db.select_db(sqltotal)
    json_list = []
    for i in totaldata:
        i["create_time"] = i["create_time"].strftime("%Y-%m-%d %H:%M:%S")
        json_list.append(i)

    print("GetStationDVRList:", json_list)
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
    if dvr_name == None or ip == None \
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
    print("----111111111-----", insert_dic)
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
    if dvr_id == None or dvr_name == None or ip == None \
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
    dvr_id = request.form.get("dvr_id")
    req = ReqResult()
    if id == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('DeleteStationRoom   dvr_id:{}'.format(dvr_id))

    sql = "delete from m_dvr where dvr_id={}".format(dvr_id)
    print("----DeleteStationDVR sql:", sql)
    db.execute_db(sql)
    print("----DeleteStationDVR sql over!")

    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
12.DVR/NVR 摄像头信息列表
'''
@realtimealarm.route('/GetStationDVRCamList', methods=["post"])
def GetStationDVRCamList():
    req = ReqResult()
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

    print("GetStationDVRList:", json_list)
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
    if camera_name == None or dvr_id == None \
            or channel == None or roomid == None or realserialnum == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('AddStationDVRCam   camera_name:{},dvr_id:{},channel:{},'
                            'roomid:{},realserialnum:{}'
                            .format(camera_name, dvr_id, channel, roomid, realserialnum))

    select_maxid_sql = 'select max(camera_id) as maxid from m_camera'
    select_maxid_result = db.select_db(select_maxid_sql)

    dvr_id = 0
    if select_maxid_result[0]['maxid'] is None:
        dvr_id = 1
    else:
        dvr_id = int(select_maxid_result[0]['maxid']) + 1
    nowTime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    insert_dic = {
        'camera_id': dvr_id,
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
    print("----111111111-----", insert_dic)
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
    if camera_id == None or camera_name == None or dvr_id == None \
            or channel == None or roomid == None or realserialnum == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('AddStationDVRCam   camera_id:{},camera_name:{},dvr_id:{},channel:{},'
                            'roomid:{},realserialnum:{}'
                            .format(camera_id, camera_name, dvr_id, channel, roomid, realserialnum))

    sql = "update m_camera set camera_name='{}',dvr_id='{}' ,channel='{}',roomid='{}',realserialnum='{}',optipaddr='{}',optserial='{}' where camera_id={}".format(
        camera_name, dvr_id, channel, roomid, realserialnum, optipaddr, optserial, camera_id)
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
    camera_id = request.form.get("camera_id")
    req = ReqResult()
    if camera_id == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('DeleteStationDVRCam   camera_id:{}'.format(camera_id))

    sql = "delete from m_camera where camera_id={}".format(camera_id)
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

    print("GetStationDVRList:", totaldata)
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
    if devmodel == None or cpu == None \
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
    print("----111111111-----", insert_dic)
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
    if devmodel == None or cpu == None or id == None \
            or mem == None or length == None or width == None \
            or high == None or lannum == None or videotype == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('ModifyStationDevType   id:{},devmodel:{},cpu:{},mem:{},'
                            'length:{},width:{} high:{},lannum:{},videotype:{},'
                            .format(id, devmodel, cpu, mem, length, width,
                                    high, lannum, videotype))

    sql = "update m_devbaseinfo set devmodel='{}',cpu='{}' ,mem='{}',length='{}',width='{}',high='{}',lannum='{}',videotype='{}' where id={}".format(
        devmodel, cpu, mem, length, width, high, lannum, videotype, id)
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

    sql = "delete from m_devbaseinfo where id={}".format(id)
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

    print("GetStationDetectDevList:", totaldata)
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
               " on aa.dvrinfoid = bb.dvr_id where bb.stationid = {}".format(id)
    # sql = "delete from m_camera where camera_id={}".format(camera_id)
    totaldata = db.select_db(sqltotal)
    print("GetStationDetectDevListByStationId:", totaldata)
    req.code = 0
    req.msg = "读取成功"
    req.data = totaldata
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
    print("----111111111-----", insert_dic)
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
    if id == None or devid == None or address == None \
            or modelid == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('ModifyStationDetectDev   id:{},devid:{},address:{},modelid:{},'
                            .format(id, devid, address, modelid))

    sql = "update m_devinfo set devid='{}',address='{}' ,modelid='{}' where id={}".format(
        devid, address, modelid, id)
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
    devid = request.form.get("devid")
    if devid == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('GetDetectDevChParamsList   devid:{}'.format(devid))
    sqltotal = "select * from m_devrunconfig  where devid='{}' order by devchannel".format(devid)
    totaldata = db.select_db(sqltotal)
    print("GetDetectDevChParamsList:", totaldata)
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
    if devid == None or devchannel == None or dvrinfoid == None or dvrchannel == None \
            or state == None or ThredMultiple == None or SelThredMultipleEnable == None \
            or LearnValOne == None or ThredMultipleOne == None or LearnValTwo == None \
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
    print("----111111111-----", insert_dic)
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
    if id == None or devid == None or devchannel == None or dvrinfoid == None or dvrchannel == None \
            or state == None or ThredMultiple == None or SelThredMultipleEnable == None \
            or LearnValOne == None or ThredMultipleOne == None or LearnValTwo == None \
            or ThredMultipleTwo == None or LearnValThree == None or ThredMultipleThree == None or runenable == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('ModifyDetectDevChParams   id:{},devid:{},devchannel:{},dvrinfoid:{},dvrchannel:{},'
                            'state:{},ThredMultiple:{},SelThredMultipleEnable:{},LearnValOne:{},'
                            'ThredMultipleOne:{},LearnValTwo:{},ThredMultipleTwo:{},LearnValThree:{},'
                            'ThredMultipleThree:{},runenable:{}'
                            .format(id, devid, devchannel, dvrinfoid, dvrchannel, state,
                                    ThredMultiple, SelThredMultipleEnable, LearnValOne, ThredMultipleOne, LearnValTwo,
                                    ThredMultipleTwo, LearnValThree, ThredMultipleThree, runenable))

    sql = "update m_devrunconfig set devid='{}',devchannel='{}' ,dvrinfoid='{}',dvrchannel='{}'," \
          "state='{}',ThredMultiple='{}',SelThredMultipleEnable='{}',LearnValOne='{}',ThredMultipleOne='{}' ," \
          "LearnValTwo='{}',ThredMultipleTwo='{}',LearnValThree='{}' ,ThredMultipleThree='{}' ,runenable='{}'" \
          " where id='{}'" \
        .format(devid, devchannel, dvrinfoid, dvrchannel,
                state, ThredMultiple, SelThredMultipleEnable, LearnValOne, ThredMultipleOne,
                LearnValTwo, ThredMultipleTwo, LearnValThree, ThredMultipleThree, runenable, id)

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

    sql = "delete from m_devrunconfig where id={}".format(id)
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
    print("GetDetectDevTempList:", json_list)
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

    print("GetDetectDevTempBydevid:", json_list)
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
    for i in totaldata:
        i["updatetime"] = i["updatetime"].strftime("%Y-%m-%d %H:%M:%S")

    print("GetDetectDevStateList:", totaldata)
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
    print("GetDetectDevStateBydevid:", json_list)
    req.code = 0
    req.msg = "读取成功"
    req.data = totaldata
    return json.dumps(req.__dict__, ensure_ascii=False)


'''
    20. 获取维护信息列表  
'''


@realtimealarm.route('/GetMaintainList', methods=["post"])
def GetMaintainList():
    sqltotal = "select * from m_maintain aa  LEFT JOIN  m_stationinfo bb on aa.stationid =  bb.id"
    totaldata = db.select_db(sqltotal)
    for i in totaldata:
        i["updatetime"] = i["updatetime"].strftime("%Y-%m-%d %H:%M:%S")

    print("GetMaintainList:", totaldata)

    req = ReqResult()
    req.code = 0
    req.msg = "读取成功"
    req.data = totaldata

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
   20.1 添加维护信息 
'''


@realtimealarm.route('/AddMaintainInfo', methods=["post"])
def AddMaintainInfo():
    req = ReqResult()
    stationid = request.form.get("stationid")
    info = request.form.get("info")
    if stationid == None or info == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)

    TableName = "m_maintain"
    select_maxid_sql = 'select max(id) as maxid from {}'.format(TableName)
    select_maxid_result = db.select_db(select_maxid_sql)
    id = 0
    if select_maxid_result[0]['maxid'] is None:
        id = 1
    else:
        id = int(select_maxid_result[0]['maxid']) + 1
    insert_dic = {
        'id': id,
        'stationid': stationid,
        'info': info,
        'updatetime': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    db.insertData(TableName, insert_dic)
    req1 = ReqResult()
    req1.code = 0
    req1.msg = "success"

    return json.dumps(req1.__dict__, ensure_ascii=False)


'''
    20.2 删除维护信息 
'''


@realtimealarm.route('/DelMaintainInfo', methods=["post"])
def DelMaintainInfo():
    id = request.form.get("id")
    req = ReqResult()
    if id == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    current_app.logger.info('DeleteStationInfo   id:{}'.format(id))

    sql = "delete from m_maintain where id={}".format(id)
    print("----DeleteModelInfo sql:", sql)
    db.execute_db(sql)
    print("----DeleteModelInfo sql over!")

    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
   20.3. 修改维护信息
'''


@realtimealarm.route('/UpdateMaintainInfo', methods=["post"])
def UpdateMaintainInfo():
    req = ReqResult()
    id = request.form.get("id")
    stationid = request.form.get("stationid")
    info = request.form.get("info")
    if stationid == None or info == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)
    datestr = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    current_app.logger.info('UpdateMsgFlag   id:{},stationid:{},info:{}'.format(id, stationid, info))
    sql = "update m_maintain set stationid={},info='{}',updatetime='{}' where id={}".format(stationid, info, datestr,
                                                                                            id)
    db.execute_db(sql)
    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
21.获取巡视计划表
'''


@realtimealarm.route('/GetVisitationPlan', methods=["post"])
def GetVisitationPlan():
    req = ReqResult()
    current_app.logger.info('GetVisitationPlan ')
    sqltotal = "select * from m_visitationplan"
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
21.获取摄像头巡视任务计划
'''


@realtimealarm.route('/GetViewVisitationPlan', methods=["post"])
def GetViewVisitationPlan():
    req = ReqResult()
    current_app.logger.info('GetVisitationPlan ')
    sqltotal = "select * from m_visitationplan where taskplanclass=1"
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
        'predatetime': None,
        'createtime': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    db.insertData(TableName, insert_dic)
    req1 = ReqResult()
    req1.code = 0
    req1.msg = "success"

    return json.dumps(req1.__dict__, ensure_ascii=False)


'''
21.2 修改巡视计划
'''


@realtimealarm.route('/ModifyVisitationPlan', methods=["post"])
def ModifyVisitationPlan():
    id = request.form.get("id")
    taskplanname = request.form.get("taskplanname")
    taskplanclass = request.form.get("taskplanclass")
    taskplantype = request.form.get("taskplantype")
    taskplanstate = request.form.get("taskplanstate")
    taskpanh = request.form.get("taskpanh")
    taskplanf = request.form.get("taskplanf")
    taskplanm = request.form.get("taskplanm")
    req = ReqResult()

    if id == None or taskplanname == None or taskplanclass == None or \
            taskplantype == None or taskplanstate == None or taskpanh == None \
            or taskplanf == None or taskplanm == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__, ensure_ascii=False)

    current_app.logger.info(
        'ModifyVisitationPlan taskplantype:{}，taskplanstate:{}，taskpanh:{}，taskplanf:{}，taskplanm:{}'
        .format(taskplantype, taskplanstate, taskpanh, taskplanf, taskplanm))

    sql = "update m_visitationplan set taskplanname='{}',taskplanclass='{}'," \
          "taskplantype='{}',taskplanstate='{}' ,taskpanh='{}',taskplanf='{}'," \
          "taskplanm='{}'  where id={}" \
        .format(taskplanname, taskplanclass, taskplantype, taskplanstate, taskpanh, taskplanf,
                taskplanm, id)

    print("----ModifyVisitationPlan sql:", sql)
    db.execute_db(sql)
    print("----ModifyVisitationPlan sql over!")

    req.code = 0
    req.msg = "success"

    return json.dumps(req.__dict__, ensure_ascii=False)


'''
21.3 修改计划状态
'''


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
               "on aa.taskplanid = bb.id ORDER BY id desc limit {},{}".format(
        str((int(pagenum) - 1) * int(pagesize)), str(pagesize))
    totaldata = db.select_db(sqltotal)
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
          "set camid={},watchpoint={},ctlopt={},optipaddr={},checktype={},taskplanid={} where id={}" \
        .format(camid, watchpoint, ctlopt, optipaddr, checktype, taskplanid, id)
    db.execute_db(sql)
    req.code = 0
    req.msg = "success"

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
    print("id", request.form.get("id"))
    alarmid = request.form.get("id")
    token = request.form.get("token")
    current_app.logger.info('GetAlarmInfo   token:{},alarmid:{}'.format(token, alarmid))
    return GetAlarmInfoFromDB(alarmid)


'''
    4.确定告警
'''


@realtimealarm.route('/AlarmInfoHandler', methods=["post"])
def AlarmInfoHandler():
    print("id", request.form.get("id"))
    print("type", request.form.get("type"))
    alarmid = request.form.get("id")
    type = request.form.get("type")
    token = request.form.get("token")
    current_app.logger.info('AlarmInfoHandler   token:{},alarmid:{},type:{}'.format(token, alarmid, type))

    sql = "update m_task set opsts={},errortype={} where task_id={} ".format(20, type, alarmid)
    print("----AlarmInfoHandler sql:", sql)
    db.execute_db(sql)
    print("----AlarmInfoHandler sql over!")

    req = ReqResult()

    return json.dumps(req.__dict__)


'''
    4.1设置告警已读状态
'''


@realtimealarm.route('/AlarmInfoReadHandler', methods=["post"])
def AlarmInfoReadHandler():
    print("id", request.form.get("id"))
    alarmid = request.form.get("id")
    token = request.form.get("token")
    current_app.logger.info('AlarmInfoReadHandler   token:{},alarmid:{}'.format(token, alarmid))
    sql = "update m_task set opsts={} where task_id={} ".format(15, alarmid)
    db.execute_db(sql)

    req = ReqResult()

    return json.dumps(req.__dict__)


'''
    4.2设置告警全部已读状态
'''


@realtimealarm.route('/AllAlarmInfoReadHandler', methods=["post"])
def AllAlarmInfoReadHandler():
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
    token = request.form.get("token")
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
    print("id", request.form.get("id"))
    alarmid = request.form.get("id")
    token = request.form.get("token")
    current_app.logger.info('GetAlarmInfoFile   token:{},alarmid:{}'.format(token, alarmid))
    strinfo = GetAlarmInfoFromDB(alarmid)
    print("strinfo:", strinfo)
    objinfo = json.loads(strinfo)
    tmpdir = '{}-{}-{}'.format(alarmid, time.strftime('%Y-%m-%d-%H-%M-%S'), token)
    tmppath = './tmpfiles/' + tmpdir
    print("--tmppath:", tmppath)
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
        if os.path.isfile(imgfile):
            shutil.copy(imgfile, tmppath + "/{}.bmp".format(imgcnt))
            imgcnt += 1

    hisvideo = objinfo["data"]["hisvideo"]
    if os.path.isfile(hisvideo):
        shutil.copy(hisvideo, tmppath + "/error.mp4")

    zipfilea = zip_file_path(tmppath, "./tmpfiles", tmpdir + ".zip")
    req = ReqResult()
    req.data = "./tmpfiles" + "/" + tmpdir + ".zip"

    shutil.rmtree(tmppath)

    return json.dumps(req.__dict__)


'''
    7.获取变电站列表
'''


@realtimealarm.route('/GetStationList11', methods=["post"])
def GetStationList11():
    token = request.form.get("token")
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
    print("stationid", request.form.get("stationid"))
    stationid = request.form.get("stationid")
    token = request.form.get("token")
    current_app.logger.info('GetStationCamList   token:{},stationid:{}'.format(token, stationid))

    sql = "select bb.camera_id as id, bb.camera_name as cam from m_stationroom aa LEFT JOIN m_camera  bb on aa.id = bb.roomid where aa.stationid={}".format(
        stationid)
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
        alarmtype_dic['alarmtype'] = alarmtype  # 传递值的方式--->  {'id':max_id+1,'alarmtype':alarmtype}
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
    current_app.logger.info('AlterExceptClassList   token:{}, id:{},alarmtype:{}'.format(token, id, alarmtype))

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
        if select_maxid_result[0]['maxid'] == None:
            select_maxid_result[0]['maxid'] = 0

        insert_dic = {
            'id': select_maxid_result[0]['maxid'] + 1,
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
    #

    token = request.form.get("token")
    starttime = request.form.get("starttime")
    endtime = request.form.get("endtime")
    stationid = request.form.get("stationid")
    current_app.logger.info('VariousExceptAlarmStatistics   token:{},stationid:{}'.format(token, stationid))

    req = ReqResult()
    # 当没有开始时间时,直接获取失败
    if not all([starttime, ]):
        req.code = 1
        req.msg = "数据为空"
    else:
        # 如果截止时间没有传递,默认当前时间
        if not all([endtime, ]):
            nowTime = str(datetime.datetime.now())
            time_list = nowTime.split(' ')
            endtime = time_list[0]

        if all([stationid, ]):
            # 执行sql
            select_sql1 = 'select m_taskalarm.id, m_taskalarm.alarmtype, IFNULL(!count(*),0) as alarmcount from m_taskalarm left join m_taskalarmtype on m_taskalarm.id = m_taskalarmtype.errorid left join m_task on m_taskalarmtype.task_id = m_task.task_id group by m_taskalarm.id, m_taskalarm.alarmtype;'

            select_result1 = db.select_db(select_sql1)
            select_sql2 = 'select m_taskalarm.id,m_taskalarm.alarmtype,count(*) as alarmcount from m_taskalarm left join m_taskalarmtype on m_taskalarm.id = m_taskalarmtype.errorid left join m_task on m_taskalarmtype.task_id = m_task.task_id left join m_camera on m_task.camera_id = m_camera.camera_id left join m_stationroom on m_stationroom.id = m_camera.roomid where  m_stationroom.stationid = {} and m_task.create_time between "{}" and "{}" group by m_taskalarm.id, m_taskalarm.alarmtype;'.format(
                stationid, starttime, endtime)
            select_result2 = db.select_db(select_sql2)

            for res2 in select_result2:
                for res1 in select_result2:
                    if res2['id'] == res1['id']:
                        select_result1[int(res2['id']) - 1] = res2

            if len(select_result1) == 0:
                req.code = 1
                req.msg = "数据为空"
            else:
                req.data = select_result1
        else:
            select_sql1 = 'select m_taskalarm.id, m_taskalarm.alarmtype, IFNULL(!count(*),0) as alarmcount from m_taskalarm left join m_taskalarmtype on m_taskalarm.id = m_taskalarmtype.errorid left join m_task on m_taskalarmtype.task_id = m_task.task_id group by m_taskalarm.id, m_taskalarm.alarmtype;'
            select_result1 = db.select_db(select_sql1)
            select_sql2 = 'select m_taskalarm.id, m_taskalarm.alarmtype,count(*) as alarmcount from m_taskalarm left join m_taskalarmtype on m_taskalarm.id = m_taskalarmtype.errorid left join m_task on m_taskalarmtype.task_id = m_task.task_id where m_task.create_time  between "{}" and "{}" group by m_taskalarm.id, m_taskalarm.alarmtype;'.format(
                starttime, endtime)
            select_result2 = db.select_db(select_sql2)

            for res2 in select_result2:
                for res1 in select_result2:
                    if res2['id'] == res1['id']:
                        select_result1[int(res2['id']) - 1] = res2

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
        if len(title_list_dev) > 0:
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

        if len(title_list_dev) != 0 and len(title_list_camera) != 0:
            # 保存文件
            now_time = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
            # save_path = '/home/python/Desktop/{}_设备异常.xls'.format(now_time)
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
    print("sql:", sql)

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

            day_alarm_count_sql = 'select m_taskalarm.id, m_taskalarm.alarmtype,count(*) as alarmcount from m_taskalarm left join m_taskalarmtype on m_taskalarm.id = m_taskalarmtype.errorid left join m_task on m_taskalarmtype.task_id = m_task.task_id where m_task.create_time  between "{}" and "{}" group by m_taskalarm.id, m_taskalarm.alarmtype;'.format(
                n_days, now_time)
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

    return json.dumps(req.__dict__)


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
        delta = datetime.timedelta(days=-14 + 1)
        n_days = now + delta
        n_days = n_days.strftime('%Y-%m-%d')
        # n_days = '2020-11-11'
        # print(n_days)
        # 查询出告警的数量（每天的告警总数）
        day_alarm_count_sql = 'select date(m_task.create_time) as date,count(m_task.create_time) as count from m_taskalarm left join m_taskalarmtype on m_taskalarm.id = m_taskalarmtype.errorid left join m_task on m_taskalarmtype.task_id = m_task.task_id where m_task.create_time  between "{}" and "{}" group by date;'.format(
            n_days, now_time)
        day_alarm_counts = db.select_db(day_alarm_count_sql)
        # for day_alarm_count in day_alarm_counts:
        #     print(day_alarm_count)
        #     print(day_alarm_count['date'])
        #     print(day_alarm_count['count'])

        # 10天的日期
        day_select_sql_10 = 'SELECT @date := DATE_ADD(@date, INTERVAL - 1 DAY) days FROM ( SELECT @date := DATE_ADD("{}", INTERVAL + 1 DAY) FROM m_taskalarm LIMIT 10 ) time;'.format(
            now_time)
        day_res_10 = db.select_db(day_select_sql_10)
        # 4天的日期
        day_select_sql_4 = 'SELECT @date := DATE_ADD(@date, INTERVAL - 1 DAY) days FROM ( SELECT @date := DATE_ADD("{}", INTERVAL + 1 DAY) FROM m_taskalarm LIMIT 5 ) time;'.format(
            day_res_10[-1]['days'])
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
        month_select_sql_10 = 'SELECT DATE_FORMAT(@date := DATE_ADD(@date, INTERVAL - 1 MONTH),"%Y-%m") as month FROM ( SELECT @date := DATE_ADD("{}", INTERVAL + 1 MONTH) FROM  m_taskalarm  LIMIT 10 ) time;'.format(
            now)
        month_res_10 = db.select_db(month_select_sql_10)
        month_select_sql_2 = 'SELECT DATE_FORMAT(@date := DATE_ADD(@date, INTERVAL -1 MONTH),"%Y-%m") as month FROM ( SELECT @date := DATE_ADD("{}-01", INTERVAL +1 MONTH) FROM  m_taskalarm  LIMIT 3 ) time;'.format(
            month_res_10[-1]['month'])
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
            week_select_sql = 'SELECT date_format(m_task.create_time, "%Y-%m") as week,count(*) as count FROM m_taskalarm left join m_taskalarmtype on m_taskalarm.id = m_taskalarmtype.errorid left join m_task on m_taskalarmtype.task_id = m_task.task_id WHERE YEARWEEK(date_format(m_task.create_time,"%Y-%m-%d")) = YEARWEEK(now())-{} Group by  week;'.format(
                i)
            week_select = db.select_db(week_select_sql)

            i += 1
            if i > 13:
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
        'devRuning': int(devCount[0]['devCount']) - int(dev_alarm[0]['error_num']),

        'noInstallDev': 0,
    }

    return json.dumps(req.__dict__)


###########################################################################


# @realtimealarm.route('/GetCurAlarmList', methods=["post"])
# def GetCurAlarmList():
#
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
    print("pagesize", request.form.get("pagesize"))
    print("pagenum", request.form.get("pagenum"))

    pagesize = request.form.get("pagesize")
    pagenum = request.form.get("pagenum")
    token = request.form.get("token")
    req = ReqResult()

    if pagesize == None or pagenum == None or token == None:
        req.code = 1
        req.msg = "参数不正确"
        return json.dumps(req.__dict__)

    current_app.logger.info('GetAllAlarmList   token:{},pagesize:{},pagenum:{}'.format(token, pagesize, pagenum))

    # sql = "select * ,CONCAT(station,'-',roomname) as station from v_historyalarm where opsts != 20 ORDER BY id desc limit {},{}".format( str((int(pagenum)-1)*int(pagesize)),str(pagesize))
    # sql = "select m_task.task_id as id,m_task.sts,m_task.opsts,m_taskalarmtype.updatetime,m_camera.camera_name,m_stationinfo.stationname,CONCAT(m_stationinfo.stationname,'-',m_stationroom.roomname) as station,m_taskalarm.alarmtype from m_task left join m_taskalarmtype on m_taskalarmtype.task_id=m_task.task_id left join m_taskalarm on m_taskalarm.id=m_taskalarmtype.errorid left join m_camera on m_task.camera_id=m_camera.camera_id left join m_stationroom on m_stationroom.id = m_camera.roomid left join m_stationinfo on m_stationinfo.id=m_stationroom.stationid ORDER BY m_task.task_id desc limit {},{}".format( str((int(pagenum)-1)*int(pagesize)),str(pagesize))
    sql = "select m_task.task_id as id,m_sts.note as sts,m_task.opsts,m_stationroom.roomname as roomname,m_taskalarmtype.updatetime,m_camera.camera_name,m_stationinfo.stationname,CONCAT(m_stationinfo.stationname,'-',m_stationroom.roomname) as station,m_taskalarm.alarmtype from m_task left join m_taskalarmtype on m_taskalarmtype.task_id=m_task.task_id left join m_taskalarm on m_taskalarm.id=m_taskalarmtype.errorid left join m_camera on m_task.camera_id=m_camera.camera_id left join m_stationroom on m_stationroom.id = m_camera.roomid left join m_stationinfo on m_stationinfo.id=m_stationroom.stationid  left join m_sts on m_sts.sts=m_task.sts ORDER by id DESC limit {},{}".format(
        str((int(pagenum) - 1) * int(pagesize)), str(pagesize))
    listdata = db.select_db(sql)

    # print(listdata)

    json_list = []
    #
    for i in listdata:
        if all([i["updatetime"], ]):
            i["updatetime"] = i["updatetime"].strftime("%Y-%m-%d %H:%M:%S")  #
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













