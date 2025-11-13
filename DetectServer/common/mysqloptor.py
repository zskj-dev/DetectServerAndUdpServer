
import pymysql
from config.setting import MYSQL_HOST ,MYSQL_PORT, MYSQL_USER, MYSQL_PWD ,MYSQL_DB
import time

class MysqlDB(object):
    def __init__(self, host, port, user, passwd, db):
        # 建立数据库连接
        self.conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            passwd=passwd,
            db=db,
            autocommit=True,
            charset='utf8'
        )
        # 通过 cursor() 创建游标对象，并让查询结果以字典格式输出
        self.cur = self.conn.cursor(cursor=pymysql.cursors.DictCursor)

    def __del__(self):
        #self.cur.close()
        #self.conn.close()
        pass
	
    def select_db(self ,sql):
        self.conn.ping(reconnect=True)
        self.cur.execute(sql)
        data = self.cur.fetchall()
        return data

    def execute_db(self, sql):
        try:
            self.conn.ping(reconnect=True)
            self.cur.execute(sql)
            self.conn.commit()
        except Exception as e:
            print("opt error:{}".format(e))
            self.conn.rellback()

    
      


    def insertData(self ,TableName ,dic):
        try:
            # conn=MySQLdb.connect(host='localhost',user='root',passwd='****',db='test',port=3306)  #链接数据库
            # cur=conn.cursor()
            # COLstr=''   #列的字段
            ROWstr =''  # 行字段

            # ColumnStyle=' VARCHAR(20)'
            for key in dic.keys():
                # COLstr=COLstr+' '+key+ColumnStyle+','
                ROWstr =(ROWstr +'"%s" ' +',' ) %(dic[key])


            # 推断表是否存在，存在运行try。不存在运行except新建表，再insert
            try:
                # cur.execute("SELECT * FROM  %s"%(TableName))
                # print("INSERT INTO %s VALUES (%s)" %(TableName ,ROWstr[:-1]))
                self.cur.execute("INSERT INTO %s VALUES (%s)" %(TableName ,ROWstr[:-1]))

            except Exception as e:
                print("opt error:{}".format(e))
                # cur.execute("CREATE TABLE %s (%s)"%(TableName,COLstr[:-1]))
                # cur.execute("INSERT INTO %s VALUES (%s)"%(TableName,ROWstr[:-1]))
            self.conn.commit()
            # self.cur.close()
            # self.conn.close()

        except Exception as e:
            print("opt error:{}".format(e))

    def updateData(self ,TableName ,dic ,wheresql):
        try:
            # conn=MySQLdb.connect(host='localhost',user='root',passwd='****',db='test',port=3306)  #链接数据库
            # cur=conn.cursor()
            # COLstr=''   #列的字段
            ROWstr =''  # 行字段

            # ColumnStyle=' VARCHAR(20)'
            for key in dic.keys():
                # COLstr=COLstr+' '+key+ColumnStyle+','
                ROWstr =(ROWstr +'%s="%s" ' +',' ) %(key ,dic[key])

            # 推断表是否存在，存在运行try。不存在运行except新建表，再insert
            try:
                # cur.execute("SELECT * FROM  %s"%(TableName))
                # 'alarmtype=new_alarmtype;'          alarmtype="奥特曼";
                print('update %s set %s where %s' %(TableName ,ROWstr[:-1], wheresql))
                # self.cur.execute("update %s set %s where {%s}" %(TableName ,ROWstr[:-1], wheresql))
                self.cur.execute('update %s set %s where %s' %(TableName ,ROWstr[:-1], wheresql))
                # self.conn.commit()
                # self.cur.close()
                # self.conn.close()

            except Exception as e:
                print("updateData 1 opt error:{}".format(e))
                # cur.execute("CREATE TABLE %s (%s)"%(TableName,COLstr[:-1]))
                # cur.execute("INSERT INTO %s VALUES (%s)"%(TableName,ROWstr[:-1]))
            self.conn.commit()
            # self.cur.close()
            # self.conn.close()

        except Exception as e:
            print("updateData 2 opt error:{}".format(e))

db = MysqlDB(MYSQL_HOST ,MYSQL_PORT, MYSQL_USER ,MYSQL_PWD ,MYSQL_DB)






