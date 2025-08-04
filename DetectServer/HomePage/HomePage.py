from flask import Blueprint, render_template, redirect,request,current_app
from common.mysqloptor import db
from common.reqresult import ReqResult
import xlwt
import json
import shutil
import time
import datetime
import os
import zipfile
import os.path



homepage = Blueprint('HomePage',__name__)

'''
1. 首页
获取设备数量和状态
'''

@homepage.route('/GetDevicesState', methods=["post"])
def GetDevicesState():
    print("token",request.form.get("token"))
    token=request.form.get("token")
    current_app.logger.info('GetDevicesState   token:{}'.format(token))

    sql = "select count(id) as cnt, address from m_devinfo GROUP BY address"
    listdata = db.select_db(sql)
    if listdata == None:
        listdata = []
    totalval = 0
    for i in listdata:
        totalval += i["cnt"]

    sql = '''select  count(id) as cnt  from m_devrunconfig where state = 0'''
    errcnt = db.select_db(sql)
    if len(errcnt) != 0:
        errcnt = errcnt[0]["cnt"]
    else:
        errcnt = 0
    req = ReqResult()
    dateInfo = {}
    dateInfo["datas"] = listdata
    dateInfo["total"] = totalval
    dateInfo['error'] = errcnt

    if len(listdata) == 0:
        req.code = 1
        req.msg = "获取数据失败"
    else:
        req.data = dateInfo

    return json.dumps(req.__dict__, ensure_ascii=False).encode('utf-8')


@homepage.route('/test', methods=["post"])
def test():
    req = ReqResult()
    req.code = 1
    req.msg = "获取数据失败"

    return json.dumps(req.__dict__, ensure_ascii=False).encode('utf-8')