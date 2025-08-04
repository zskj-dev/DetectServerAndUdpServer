from datetime import datetime


def compare_time_parts_with_tolerance(time_a, time_b, tolerance=2):
    # 比较小时和分钟
    if time_a.hour != time_b.hour or time_a.minute != time_b.minute:
        return False

        # 比较秒数，允许有tolerance秒的偏差
    diff = abs(time_a.second - time_b.second)
    return diff <= tolerance


# 创建两个datetime对象
time1 = datetime(2023, 4, 1, 12, 30, 45)  # 2023年4月1日 12:30:45
time2 = datetime(2023, 4, 1, 12, 30, 47)  # 2023年4月1日 12:30:47

# 调用函数并打印结果
if compare_time_parts_with_tolerance(time1, time2):
    print("时分秒（相差2秒内）相等")
else:
    print("时分秒（相差2秒内）不相等")

# 另一个示例，相差3秒，应该不相等
time3 = datetime(2023, 4, 1, 12, 30, 48)
if compare_time_parts_with_tolerance(time1, time3):
    print("time1和time3的时分秒（相差2秒内）相等")
else:
    print("time1和time3的时分秒（相差2秒内）不相等")