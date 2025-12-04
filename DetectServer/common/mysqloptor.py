
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
        '''
                with self.pool.connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, params)
                    return cursor.fetchall()
        '''

    def select_db(self, sql):
        # self.conn.ping(reconnect=True)
        # self.cur.execute(sql)
        # data = self.cur.fetchall()
        # return data
        with self.pool.connection() as conn:
            with conn.cursor(cursor=pymysql.cursors.DictCursor) as cursor:
                # 打印驱动和游标类型
                # print(f"驱动模块: {conn.__class__.__module__}")
                # print(f"游标类型: {cursor.__class__.__name__}")
                cursor.execute(sql)
                result = cursor.fetchall()
                # assert isinstance(result, list), "select_db查询结果不是list类型"
                return result

    def execute_db(self, sql):
        try:
            with self.pool.connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(sql)
                    conn.commit()
        except Exception as e:
            print("execute_db error: {}".format(e))
            # 如果有错误，回滚事务
            with self.pool.connection() as conn:
                conn.rollback()
        # try:
        #     self.conn.ping(reconnect=True)
        #     self.cur.execute(sql)
        #     self.conn.commit()
        # except Exception as e:
        #     print("opt error:{}".format(e))
        #     self.conn.rellback()


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

    def checkIdExist(self, TableName, id, key='id'):
        """
        检查指定表中是否存在给定ID的记录

        参数:
            TableName (str): 数据库表名
            id (int): 要检查的记录ID

        返回:
            bool: 如果记录存在返回True,否则返回False
        """
        try:
            id = int(id)
            table_name = str(TableName)
            # self.conn.ping(reconnect=True)
            # 添加调试信息
            # print(f"DEBUG: table_name={table_name}, key={key}, id={id}")
            sql = "SELECT * FROM {} WHERE {} = {}".format(table_name, key, id)
            print(f"DEBUG: SQL={sql}")  # 打印生成的SQL
            self.cur.execute(sql)
            result = self.cur.fetchone()
            return result is not None
        except Exception as e:
            print("check_id_exist opt error:{}".format(e))
            return False

    def getTalbeMaxID(self, TableName):
        """
        获取指定表中的最大ID值

        参数:
            TableName (str): 数据库表名

        返回:
            int: 表中的最大ID值，如果表为空则返回0
        """
        try:
            table_name = str(TableName)
            self.conn.ping(reconnect=True)
            sql = "SELECT MAX(id) AS max_id FROM {}".format(table_name)
            self.cur.execute(sql)
            result = self.cur.fetchone()
            if result and result['max_id'] is not None:
                return result['max_id']
            else:
                return 0
        except Exception as e:
            print("get_table_max_id opt error:{}".format(e))
            return 0    

db = MysqlDB(MYSQL_HOST ,MYSQL_PORT, MYSQL_USER ,MYSQL_PWD ,MYSQL_DB)






