if(__name__ == '__main__'):
    path = './source/python/rewrite'
    import os
    import sys
    print(os.path.abspath(path))
    sys.path.append(os.path.abspath(path))


from supports import *
from api.api_android import click
from airtest.core.api import auto_setup

__all__ = ["GetAndroidInfo", "CopyRequirements",
           "ConnectAndroid", "RestartAndroid", "CheckNetWork", "is_android_online"
           ]

# Win 和 Android 的通信
# Win 向系统写入数据


def GetAndroidInfo():
    """还没写好"""
    """返回所有在线设备的编号

    Returns:
        list:一个包含所有设备信息的列表 
    """
    info = os.popen("adb devices -l")
    time.sleep(2)
    info = os.popen("adb devices -l")
    res = []
    get = 0
    for x in info:
        if(get == 0):
            get = 1
            continue
        if(len(x.split()) == 0):
            break
        a = x.split()[0]
        res.append(a)
    print("Devices list:", res)
    return res

def CopyRequirements(timer: Timer, path):
    """还没写好"""
    print(path)
    try:
        shutil.rmtree(path + "\\airtest")
    except:
        pass
    print(f"xcopy req {path} /E/H/C/I")
    os.system(f"xcopy req {path} /E/H/C/I")
    time.sleep(5)

@try_for_times
def ConnectAndroid(timer: Timer):
    """连接指定安卓设备
    Args:
    """
    
    if(not any((is_android_online(timer), is_android_online(timer), is_android_online(timer)))):
        RestartAndroid(timer)
        
    from logging import getLogger, ERROR
    getLogger("airtest").setLevel(ERROR)
    auto_setup(__file__, devices=[
        f"android://127.0.0.1:5037//{timer.device_name}?cap_method=MINICAP&&ori_method=MINICAPORI&&touch_method=MINITOUCH"])

    print("Hello,I am WSGR auto commanding system")

def is_android_online(timer:Timer):
    """判断 timer 给定的设备是否在线

    Args:
        timer (Timer): _description_

    Returns:
        bool: 在线返回 True,否则返回 False
    """
    res = os.popen("adb devices -l")
    for x in res:
        print(x, end=' ')
        if(timer.device_name in x and 'device' in x):
            return True
    return False

@logit(level=INFO2)
def RestartAndroid(timer: Timer):
    """重启安卓设备

    Args:
        times (int):重启次数
    """
    restart_time = time.time()
    print("Android Restaring")
    try:
        dir = os.getcwd()
        try:
            os.system("taskkill -f -im dnplayer.exe")
        except:
            pass
        os.chdir(S.RESTART_PATH)
        os.popen(r".\dnplayer.exe")
        os.chdir(dir)
        while(is_android_online(timer) == False):
            time.sleep(1)
            if(time.time() - restart_time > 120):
                raise TimeoutError("can't start the emulator")
    except:
        raise CriticalErr("on Restart Android")

def CheckNetWork():
    """检查网络状况

    Returns:
        bool:网络正常返回 True,否则返回 False
    """
    time.sleep(.5)
    return os.system("ping baidu.com") == False

if(__name__ == '__main__'):
    timer = Timer()
    devices = GetAndroidInfo()
    timer.device_name = devices[-1]

    ConnectAndroid(timer, 0, device=timer.device_name)
    click(timer, 400, 120)
    # print(get_all_files('./source/python/rewrite'))
