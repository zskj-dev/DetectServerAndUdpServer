


class ReqResult:
    def __init__(self):
        self.code = 0
        self.msg = "成功"
        self.data = None

    def toJson(self):
        return {
            "code": self.code,
            "msg": self.msg,
            "data": self.data
        }