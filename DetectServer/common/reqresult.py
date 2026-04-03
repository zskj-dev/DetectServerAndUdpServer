from typing import List, Dict, Any, Optional
from common.mysqloptor import db

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
    
############ 定义接口数据结构: 当前计划的执行情况 ############
class InspectionResult:
    """巡检结果项"""
    def __init__(self, cabinetName: str = "", unitName: str = "", 
                 unitResult: str = "", unitStatus: str = ""):
        self.cabinetName= cabinetName
        self.unitName   = unitName
        self.unitResult = unitResult
        self.unitStatus = unitStatus

    def to_dict(self) -> Dict[str, str]:
        return {
            "cabinetName": self.cabinetName,
            "unitName": self.unitName,
            "unitResult": self.unitResult,
            "unitStatus": self.unitStatus
        }

# 当前计划的执行情况
class CurrentProcessStatus:
    """当前处理状态"""

    # 状态常量（根据接口文档）
    JOB_STATUS_COMPLETED = "0"      # 已完成
    JOB_STATUS_EXECUTING = "1"      # 正在执行
    JOB_STATUS_CANCELLED = "2"      # 已取消
    # 巡检状态
    UNIT_STATUS_DONE     = "已检查"  # 已完成
    UNIT_STATUS_DOING    = "检测中"  # 检测中
    UNIT_STATUS_PENDING  = "待检查"  # 待检查

    def __init__(self, jobId: str = ""):
        # 根据接口文档，所有字段都是String类型
        self.jobId: str     = jobId
        self.jobStatus: str = self.JOB_STATUS_EXECUTING  # 默认正在执行
        self.unitCount: str = "0"   # 任务巡检点总数
        self.unitFinish: str= "0"  # 已完成的巡检点个数
        # result应该是List类型，包含多个巡检结果
        self.result: List[InspectionResult] = []

    def add_inspection_result(self, cabinetName: str, unitName: str, 
                              unitResult: str, unitStatus: str) -> None:
        """添加巡检结果"""
        inspection = InspectionResult(
            cabinetName=cabinetName,
            unitName=unitName,
            unitResult=unitResult,
            unitStatus=unitStatus
        )
        self.result.append(inspection)

    def update_progress(self, unitFinish: int, total_count: Optional[int] = None) -> None:
        """更新进度"""
        self.unitFinish = str(unitFinish)
        if total_count is not None:
            self.unitCount = str(total_count)
    
    def set_job_status(self, status: str) -> None:
        """设置作业状态"""
        if status in [self.JOB_STATUS_COMPLETED, 
                     self.JOB_STATUS_EXECUTING, 
                     self.JOB_STATUS_CANCELLED]:
            self.jobStatus = status

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于JSON序列化）"""
        return {
            "jobId": self.jobId,
            "jobStatus": self.jobStatus,
            "unitCount": self.unitCount,
            "unitFinish": self.unitFinish,
            "result": [item.to_dict() for item in self.result]
        }

    def to_json(self) -> str:
        """转换为JSON字符串（如果需要的话）"""
        import json
        return json.dumps(self.to_dict(), ensure_ascii=False)


from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime


@dataclass
class UnitResult:
    """巡检点结果详情"""
    unitName: str  # 巡检点名称
    unitId: str  # 巡检点Id
    unitType: str  # 巡检点类型
    cabinetId: str  # 机柜Id
    cabinetName: str  # 机柜名称
    unitResult: str  # 巡检结果数据
    unitThreshold: str  # 巡检点阈值
    unitStatus: str  # 巡检点状态
    unitPhoto: str  # 巡检点图片
    unitTime: str  # 巡检点检测时间


@dataclass
class InspectionReport:
    """巡检报告数据格式"""
    scheduleName: str  # 计划名称
    unitCount: str  # 巡检点总数
    unitFinish: str  # 完成巡检点个数
    unitWrong: str  # 异常巡检点个数
    unitCancel: str  # 取消巡检点个数
    startTime: str  # 任务开始时间
    stopTime: str  # 任务结束时间
    conclusion: List[str]  # 巡检结论
    result: List[UnitResult]  # 巡检结果列表


def get_inspection_data_from_db() :
    sql_select = "SELECT  t2.name as unitName, \
            t1.id as unitId,  \
            (       \
                case                        \
                WHEN ( t2.type = '1')          \
            THEN                        \
            '状态灯'           \
            WHEN(t2.type = '2' ) THEN       \
            '状态灯' \
            WHEN(t2.type = '4') THEN \
            '状态灯'   \
            WHEN(t2.type = '5') THEN  \
            '状态灯'  \
            WHEN(t2.type = '3' ) THEN  \
            '开关'  \
            END  \
            ) AS   \
            `unitType`,  \
        t1.id as cabinetId,  \
        ca_p.point_info as cabinetName, \
        t1.value_str as unitResult \
        FROM m_visitationplaninfo_meter \
        t1 LEFT JOIN m_metername_point t2 ON t1.metername_id = t2.id LEFT JOIN  m_camera_point ca_p \
        ON t2.watchpoint = ca_p.point_id;"

    unit_results = db.select_db(sql_select)
    return unit_results

# 使用示例
def create_sample_inspection_report():
    """创建示例巡检报告数据"""

    # 创建巡检点结果示例
    unit_results = [
        UnitResult(
            unitName="温度传感器-01",
            unitId="TEMP001",
            unitType="温度传感器",
            cabinetId="CAB001",
            cabinetName="服务器机柜A",
            unitResult="23.5°C",
            unitThreshold="20-25°C",
            unitStatus="正常",
            unitPhoto="/images/cab001_temp001.jpg",
            unitTime="2024-01-15 10:30:25"
        ),
        UnitResult(
            unitName="湿度传感器-01",
            unitId="HUM001",
            unitType="湿度传感器",
            cabinetId="CAB001",
            cabinetName="服务器机柜A",
            unitResult="45%",
            unitThreshold="40-60%",
            unitStatus="正常",
            unitPhoto="/images/cab001_hum001.jpg",
            unitTime="2024-01-15 10:31:15"
        )
    ]

    # 创建巡检报告示例
    report = InspectionReport(
        scheduleName="数据中心日常巡检-20240115",
        unitCount="50",
        unitFinish="48",
        unitWrong="1",
        unitCancel="1",
        startTime="2024-01-15 09:00:00",
        stopTime="2024-01-15 11:30:00",
        conclusion=["巡检完成", "发现1处异常", "1处已取消"],
        result=unit_results
    )

    return report


# 转换为字典的方法
def inspection_report_to_dict(report: InspectionReport) -> dict:
    """将InspectionReport对象转换为字典"""
    return {
        "scheduleName": report.scheduleName,
        "unitCount": report.unitCount,
        "unitFinish": report.unitFinish,
        "unitWrong": report.unitWrong,
        "unitCancel": report.unitCancel,
        "startTime": report.startTime,
        "stopTime": report.stopTime,
        "conclusion": report.conclusion,
        "result": [
            {
                "unitName": u.unitName,
                "unitId": u.unitId,
                "unitType": u.unitType,
                "cabinetId": u.cabinetId,
                "cabinetName": u.cabinetName,
                "unitResult": u.unitResult,
                "unitThreshold": u.unitThreshold,
                "unitStatus": u.unitStatus,
                "unitPhoto": u.unitPhoto,
                "unitTime": u.unitTime
            }
            for u in report.result
        ]
    }


# 从字典创建对象的方法
def dict_to_inspection_report(data: dict) -> InspectionReport:
    """将字典转换为InspectionReport对象"""
    unit_results = [
        UnitResult(
            unitName=u["unitName"],
            unitId=u["unitId"],
            unitType=u["unitType"],
            cabinetId=u["cabinetId"],
            cabinetName=u["cabinetName"],
            unitResult=u["unitResult"],
            unitThreshold=u["unitThreshold"],
            unitStatus=u["unitStatus"],
            unitPhoto=u["unitPhoto"],
            unitTime=u["unitTime"]
        )
        for u in data["result"]
    ]

    return InspectionReport(
        scheduleName=data["scheduleName"],
        unitCount=data["unitCount"],
        unitFinish=data["unitFinish"],
        unitWrong=data["unitWrong"],
        unitCancel=data["unitCancel"],
        startTime=data["startTime"],
        stopTime=data["stopTime"],
        conclusion=data["conclusion"],
        result=unit_results
    )


# 如果需要JSON序列化，可以添加这个方法
def to_json(report: InspectionReport) -> str:
    """将巡检报告转换为JSON字符串"""
    import json
    return json.dumps(inspection_report_to_dict(report), ensure_ascii=False, indent=2)


# 测试代码
if __name__ == "__main__":
    # 创建示例数据
    sample_report = create_sample_inspection_report()

    # 打印对象信息
    print("=== 巡检报告对象 ===")
    print(f"计划名称: {sample_report.scheduleName}")
    print(f"巡检点总数: {sample_report.unitCount}")
    print(f"完成数: {sample_report.unitFinish}")
    print(f"异常数: {sample_report.unitWrong}")
    print(f"取消数: {sample_report.unitCancel}")
    print(f"开始时间: {sample_report.startTime}")
    print(f"结束时间: {sample_report.stopTime}")
    print(f"结论: {sample_report.conclusion}")
    print(f"巡检结果数量: {len(sample_report.result)}")

    print("\n=== 第一个巡检点详情 ===")
    first_result = sample_report.result[0]
    print(f"巡检点名称: {first_result.unitName}")
    print(f"巡检点ID: {first_result.unitId}")
    print(f"巡检结果: {first_result.unitResult}")
    print(f"巡检状态: {first_result.unitStatus}")

    # 转换为字典
    print("\n=== 转换为字典 ===")
    report_dict = inspection_report_to_dict(sample_report)
    print(report_dict)

    # 转换为JSON
    print("\n=== 转换为JSON ===")
    print(to_json(sample_report))

#
# # 使用示例
# if __name__ == "__main__":
#     # 创建状态对象
#     status = CurrentProcessStatus(jobId="job_001")
#
#     # 更新进度
#     status.update_progress(unitFinish=3, total_count=40)
#
#     # 添加巡检结果
#     status.add_inspection_result(
#         cabinetName="机柜A",
#         unitName="巡检点1",
#         unitResult="温度: 25°C",
#         unitStatus="正常"
#     )
#
#     status.add_inspection_result(
#         cabinetName="机柜A",
#         unitName="巡检点2",
#         unitResult="湿度: 60%",
#         unitStatus="正常"
#     )
#
#     # 完成任务
#     status.set_job_status(CurrentProcessStatus.JOB_STATUS_COMPLETED)
#     status.update_progress(unitFinish=20, total_count=40)
#
#     # 获取JSON数据
#     json_data = status.to_dict()
#     print("状态数据:", json_data)
#
#     # 或者获取JSON字符串
#     json_str = status.to_json()
#     print("JSON字符串:", json_str)