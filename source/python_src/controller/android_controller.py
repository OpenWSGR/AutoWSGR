import threading as th
import time

import constants.settings as S
from airtest.core.api import shell, start_app
from constants.other_constants import INFO1

from utils.api_image import convert_position
from utils.logger import logit


class AndroidController:
    def __init__(self, resolution) -> None:
        self.resolution = resolution

    @logit()
    def ShellCmd(self, cmd, *args, **kwargs):
        """向链接的模拟器发送 shell 命令
        Args:
            cmd (str):命令字符串
        """
        return shell(cmd)

    @logit()
    def is_game_running(self):
        apps = self.ShellCmd("ps")
        return "zhanjian2" in apps

    @logit(level=INFO1)
    def click(self, x, y, times=1, delay=0.5, enable_subprocess=False, *args, **kwargs):
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
        if (times < 1):
            raise ValueError("invaild arg 'times' " + str(times))
        if (enable_subprocess and times != 1):
            raise ValueError("subprocess enabled but arg 'times' is not 1 but " + str(times))
        if (x >= 960 or x < 0 or y >= 540 or y <= 0):
            raise ValueError(
                "invaild args 'x' or 'y',x should be in [0,960),y should be in [0,540)\n,but x is " + str(x) + ",y is " + str(y))
        if (delay < 0):
            raise ValueError("arg 'delay' should be positive or 0")
        x, y = convert_position(x, y, self.resolution)
        if (enable_subprocess == 1):
            p = th.Thread(target=lambda: self.ShellCmd("input tap "+str(x) + " " + str(y)))
            p.start()
            return p
        for _ in range(times):
            self.ShellCmd("input tap " + str(x) + " " + str(y))
            time.sleep(delay * S.DELAY)

    @logit(level=INFO1)
    def swipe(self, x1, y1, x2, y2, duration=0.5, delay=0.5, *args, **kwargs):
        """匀速滑动模拟器相对坐标 (x1,y1) 到 (x2,y2).
        Args:
            x1,y1,x2,y2:相对坐标 (960x540 屏幕)
            duration:滑动总时间
            delay:滑动后延时(单位为秒)
        """
        if (delay < 0):
            raise ValueError("arg 'delay' should be positive or 0")
        if (x1 >= 960 or x1 < 0 or y1 >= 540 or y1 <= 0):
            raise ValueError(
                "invaild args 'x1' or 'y1',x1 should be in [0,960),y1 should be in [0,540)\n,but x1 is " + str(x1), +",y1 is " + str(y1))
        if (x2 >= 960 or x2 < 0 or y2 >= 540 or y2 <= 0):
            raise ValueError(
                "invaild args 'x2' or 'y2',x2 should be in [0,960),y2 should be in [0,540)\n,but x2 is " + str(x2), +",y2 is " + str(y2))
        x1, y1 = convert_position(x1, y1, self.resolution)
        x2, y2 = convert_position(x2, y2, self.resolution)
        duration = int(duration * 1000)
        input_str = f"input swipe {str(x1)} {str(y1)} {str(x2)} {str(y2)} {duration}"
        if S.DEBUG:
            print("Time:", time.time(), input_str)
        self.ShellCmd(input_str)

        time.sleep(delay)

    @logit(level=INFO1)
    def long_tap(self, x, y, duration=1, delay=0.5, *args, **kwargs):
        """长按相对坐标 (x,y)
        Args:
            x (_type_): 相对 (960x540 屏幕) 横坐标
            y (_type_): _description_
            duration (int, optional): 长按时间(秒). Defaults to 1.
            delay (float, optional): 操作后等待时间(秒). Defaults to 0.5.
        """
        if (x >= 960 or x < 0 or y >= 540 or y <= 0):
            raise ValueError(
                "invaild args 'x' or 'y',x should be in [0,960),y should be in [0,540)\n,but x is " + str(x), +",y is " + str(y))
        if (delay < 0):
            raise ValueError("arg 'delay' should be positive or 0")
        if (duration <= 0.2):
            raise ValueError("duration time too short,arg 'duration' should greater than 0.2")
        self.swipe(x, y, x, y, duration=duration, delay=delay, *args, **kwargs)
        
    
