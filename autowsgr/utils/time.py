from datetime import datetime, time, timedelta


def str2time(time_str: str, format="%H:%M:%S"):
    return datetime.strptime(time_str, format).time()


def time2timedelta(time_obj: time):
    return timedelta(hours=time_obj.hour, minutes=time_obj.minute, seconds=time_obj.second)


def get_eta(time_obj: time):
    now = datetime.now()
    return now + time2timedelta(time_obj)
