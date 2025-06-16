
from HomePage.HomePage import homepage
from RealtimeAlarm.RealtimeAlarm import realtimealarm
# from HistoryAlarm.HistoryAlarm import historyalarm
# from D5000System.D5000System import d5000system
#
# from TestErrorPage.TestErrorPage import testalarm

from flask import Flask, jsonify, request
import re, time
from config.setting import SERVER_PORT
import logging
from multiprocessing import Process, Queue,Lock
import socket
from common.mysqloptor import db
import time
import datetime
from flask_cors import *

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False  # jsonify返回的中文正常显示
app.json.ensure_ascii = False
CORS(app,supports_credentials=True)
app.register_blueprint(realtimealarm,url_prefix='/RealtimeAlarm')
app.register_blueprint(homepage,url_prefix='/HomePage')
# app.register_blueprint(historyalarm,url_prefix='/HistoryAlarm')
# app.register_blueprint(d5000system,url_prefix='/D5000System')
# app.register_blueprint(testalarm,url_prefix='/TestAlarm')
handler = logging.FileHandler("flask.log")
handler.setLevel(logging.INFO)

formatter= logging.Formatter("%(asctime)s - %(message)s")
handler.setFormatter(formatter)
app.logger.addHandler(handler)



if __name__ == '__main__':
    print("--flask--")
    # host为主机ip地址，port指定访问端口号，debug=True设置调试模式打开
    app.config['CHARSET'] = 'utf-8'
    app.run(host="0.0.0.0", port=SERVER_PORT, debug=True)




