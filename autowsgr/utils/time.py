import datetime


def get_eta(time_str):
    # time_str: 时间字符串 "10:30:00" 格式

    # 将时间字符串转换为datetime对象
    time_obj = datetime.datetime.strptime(time_str, "%H:%M:%S")

    # 获取当前时间
    now = datetime.datetime.now()

    # 计算当前时间加上time_obj表示的时间
    return now + datetime.timedelta(hours=time_obj.hour, minutes=time_obj.minute, seconds=time_obj.second)
