from typing import List, Dict, Any, Optional


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


# 使用示例
if __name__ == "__main__":
    # 创建状态对象
    status = CurrentProcessStatus(jobId="job_001")
    
    # 更新进度
    status.update_progress(unitFinish=3, total_count=40)
    
    # 添加巡检结果
    status.add_inspection_result(
        cabinetName="机柜A",
        unitName="巡检点1",
        unitResult="温度: 25°C",
        unitStatus="正常"
    )
    
    status.add_inspection_result(
        cabinetName="机柜A",
        unitName="巡检点2",
        unitResult="湿度: 60%",
        unitStatus="正常"
    )
    
    # 完成任务
    status.set_job_status(CurrentProcessStatus.JOB_STATUS_COMPLETED)
    status.update_progress(unitFinish=20, total_count=40)
    
    # 获取JSON数据
    json_data = status.to_dict()
    print("状态数据:", json_data)
    
    # 或者获取JSON字符串
    json_str = status.to_json()
    print("JSON字符串:", json_str)