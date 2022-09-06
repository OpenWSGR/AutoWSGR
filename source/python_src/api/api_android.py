import threading as th
import time

import constants.settings as S
from airtest.core.api import shell, start_app
from airtest.core.helper import G
from airtest.core.settings import Settings as ST
from constants.other_constants import INFO1
from supports.logger import logit
from supports.run_timer import Timer

__all__ = ["ShellCmd", "click", "swipe", "long_tap", "UpdateScreen", \
    "start_app", "is_game_running"]

@logit()
def ShellCmd(timer: Timer, cmd, *args, **kwargs):
    """向链接的模拟器发送 shell 命令
    Args:
        cmd (str):命令字符串
    """
    return shell(cmd)

@logit()
def is_game_running(timer:Timer):
    apps = ShellCmd(timer, "ps")
    return "zhanjian2" in apps

@logit(level=INFO1)
def click(timer: Timer, x, y, times=1, delay=0.5, enable_subprocess=False, *args, **kwargs):
    if S.DEBUG:
        if 'print' in kwargs:
            is_print = kwargs.get('print')
        else:
            print("click:", time.time(), x, y)
    """点击模拟器相对坐标 (x,y).
    Args:
        x:相对横坐标  (相对 960x540 屏幕)
        y:相对纵坐标  (相对 960x540 屏幕)
        delay:点击后延时(单位为秒)
        enable_subprocess:是否启用多线程加速
        Note:
            if 'enable_subprocess' is True,arg 'times' must be 1 
    Returns:
        enable_subprocess == False:None
        enable_subprocess == True:
            A class threading.Thread refers to this click subprocess
    """
    if(times < 1):
        raise ValueError("invaild arg 'times' " + str(times))
    if(enable_subprocess and times != 1):
        raise ValueError("subprocess enabled but arg 'times' is not 1 but " + str(times))
    if(x >= 960 or x < 0 or y >= 540 or y <= 0):
        raise ValueError(
            "invaild args 'x' or 'y',x should be in [0,960),y should be in [0,540)\n,but x is " + str(x) + ",y is " + str(y))
    if(delay < 0):
        raise ValueError("arg 'delay' should be positive or 0")
    x, y = timer.covert_position(x, y)
    if(enable_subprocess == 1):
        p = th.Thread(target=lambda: ShellCmd(timer, "input tap "+str(x) + " " + str(y)))
        p.start()
        return p
    for _ in range(times):
        ShellCmd(timer, "input tap " + str(x) + " " + str(y))
        time.sleep(delay * S.DELAY)

@logit(level=INFO1)
def swipe(timer: Timer, x1, y1, x2, y2, duration=0.5, delay=0.5, *args, **kwargs):
    """匀速滑动模拟器相对坐标 (x1,y1) 到 (x2,y2).
    Args:
        x1,y1,x2,y2:相对坐标 (960x540 屏幕)
        duration:滑动总时间
        delay:滑动后延时(单位为秒)
    """
    if(delay < 0):
        raise ValueError("arg 'delay' should be positive or 0")
    if(x1 >= 960 or x1 < 0 or y1 >= 540 or y1 <= 0):
        raise ValueError(
            "invaild args 'x1' or 'y1',x1 should be in [0,960),y1 should be in [0,540)\n,but x1 is " + str(x1), +",y1 is " + str(y1))
    if(x2 >= 960 or x2 < 0 or y2 >= 540 or y2 <= 0):
        raise ValueError(
            "invaild args 'x2' or 'y2',x2 should be in [0,960),y2 should be in [0,540)\n,but x2 is " + str(x2), +",y2 is " + str(y2))
    x1, y1 = timer.covert_position(x1, y1)
    x2, y2 = timer.covert_position(x2, y2)
    duration = int(duration * 1000)
    input_str = f"input swipe {str(x1)} {str(y1)} {str(x2)} {str(y2)} {duration}"
    print("Time:", time.time(), input_str)
    ShellCmd(timer, f"input swipe {str(x1)} {str(y1)} {str(x2)} {str(y2)} {duration}")

    time.sleep(delay)

@logit(level=INFO1)
def long_tap(timer: Timer, x, y, duration=1, delay=0.5, *args, **kwargs):
    """长按相对坐标 (x,y)
    Args:
        x (_type_): 相对 (960x540 屏幕) 横坐标
        y (_type_): _description_
        duration (int, optional): 长按时间(秒). Defaults to 1.
        delay (float, optional): 操作后等待时间(秒). Defaults to 0.5.
    """
    if(x >= 960 or x < 0 or y >= 540 or y <= 0):
        raise ValueError(
            "invaild args 'x' or 'y',x should be in [0,960),y should be in [0,540)\n,but x is " + str(x), +",y is " + str(y))
    if(delay < 0):
        raise ValueError("arg 'delay' should be positive or 0")
    if(duration <= 0.2):
        raise ValueError("duration time too short,arg 'duration' should greater than 0.2")
    swipe(timer, x, y, x, y, duration=duration, delay=delay, *args, **kwargs)

@logit()
def UpdateScreen(timer: Timer, *args, **kwargs):
    """记录现在的屏幕信息,以 numpy.array 格式覆盖保存到 RD.screen
    """
    timer.screen = G.DEVICE.snapshot(filename=None, quality=ST.SNAPSHOT_QUALITY)
