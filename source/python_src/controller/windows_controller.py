import os
import shutil
import time

import constants.settings as S
from airtest.core.api import auto_setup
from constants.custom_expections import CriticalErr
from constants.other_constants import INFO2

from utils.function_wrapper import try_for_times
from utils.logger import logit


# Win 和 Android 的通信
# Win 向系统写入数据

class WindowsController:
    def __init__(self, device_name) -> None:
        self.device_name = device_name

    def wait_network(self, timeout=1000):
        """等待到网络恢复

        Args:
            timer (_type_): _description_
            timeout (int, optional): _description_. Defaults to 1000.

        Returns:
            _type_: _description_
        """
        start_time = time.time()
        while (time.time() - start_time <= timeout):
            if self.CheckNetWork():
                return True
            time.sleep(10)

        return False

    def GetAndroidInfo(self):
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
            if (get == 0):
                get = 1
                continue
            if (len(x.split()) == 0):
                break
            a = x.split()[0]
            res.append(a)
        print("Devices list:", res)
        return res

    def CopyRequirements(self, path):
        """还没写好"""
        print(path)
        try:
            shutil.rmtree(path + "\\airtest")
        except:
            pass
        print(f"xcopy req {path} /E/H/C/I")
        os.system(f"xcopy req {path} /E/H/C/I")
        time.sleep(5)

    @try_for_times()
    def ConnectAndroid(self):
        """连接指定安卓设备
        Args:
        """

        if self.is_android_online(5) == False:
            self.RestartAndroid()

        from logging import ERROR, getLogger
        getLogger("airtest").setLevel(ERROR)
        auto_setup(__file__, devices=[
            f"android://127.0.0.1:5037//{self.device_name}?cap_method=MINICAP&&ori_method=MINICAPORI&&touch_method=MINITOUCH"])

        print("Hello,I am WSGR auto commanding system")

    def is_android_online(self, times=4):
        """判断 timer 给定的设备是否在线

        Args:
            timer (Timer): _description_

        Returns:
            bool: 在线返回 True,否则返回 False
        """
        while (times):
            times -= 1
            res = os.popen("adb devices -l")
            for x in res:
                print(x, end=' ')
                if (self.device_name in x and 'device' in x):
                    return True
        return False

    @logit(level=INFO2)
    def RestartAndroid(self):
        """重启安卓设备

        Args:
            times (int):重启次数
        """
        restart_time = time.time()
        print("Android Restaring")
        try:
            cwd = os.getcwd()
            try:
                os.system("taskkill -f -im dnplayer.exe")
            except:
                pass
            os.chdir(S.RESTART_PATH)
            os.popen(r".\dnplayer.exe")
            os.chdir(cwd)
            time.sleep(3)
            while self.is_android_online() == False:
                time.sleep(1)
                if (time.time() - restart_time > 120):
                    raise TimeoutError("can't start the emulator")
        except BaseException as E:
            print(E)
            raise CriticalErr("on Restart Android")

    def CheckNetWork(self):
        """检查网络状况

        Returns:
            bool:网络正常返回 True,否则返回 False
        """
        time.sleep(.5)
        return os.system("ping baidu.com") == False
