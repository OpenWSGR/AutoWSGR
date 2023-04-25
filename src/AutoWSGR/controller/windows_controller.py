import os
import shutil
import time
import subprocess

from subprocess import check_output

from airtest.core.api import auto_setup
from AutoWSGR.constants.custom_exceptions import CriticalErr
from AutoWSGR.constants.data_roots import ADB_ROOT
from AutoWSGR.utils.function_wrapper import try_for_times

# Win 和 Android 的通信
# Win 向系统写入数据


class WindowsController:
    def __init__(self, config, logger) -> None:
        self.logger = logger

        self.emulator = config["type"]  # 模拟器类型
        self.start_cmd = config["start_cmd"]  # 模拟器启动命令
        if self.emulator == "蓝叠 Hyper-V":
            assert config["config_file"], "Bluestacks 需要提供配置文件"
            self.emulator_config_file = config["config_file"]

        self.exe_name = os.path.basename(self.start_cmd)  # 自动获得模拟器的进程名

    # ======================== 网络 ========================
    def check_network(self):
        """检查网络状况

        Returns:
            bool:网络正常返回 True,否则返回 False
        """
        return os.system("ping www.moefantasy.com") == 0

    def wait_network(self, timeout=1000):
        """等待到网络恢复
        """
        start_time = time.time()
        while (time.time() - start_time <= timeout):
            if self.check_network():
                return True
            time.sleep(10)

        return False

    # ======================== 模拟器 ========================
    def GetAndroidInfo(self):
        """还没写好"""
        """返回所有在线设备的编号

        Returns:
            list:一个包含所有设备信息的列表
        """
        info = os.popen(f"{ADB_ROOT}/adb.exe devices -l")
        time.sleep(1)
        info = os.popen(f"{ADB_ROOT}/adb.exe devices -l")
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
        self.logger.debug(f"Devices list: {res}")
        return res

    # @try_for_times()
    def connect_android(self):
        """连接指定安卓设备
        Args:
        """
        if not self.is_android_online():
            self.restart_android()
            time.sleep(15)

        if self.emulator == "雷电":
            dev_name = "emulator-5554"
            cap_method = "MINICAP"
        elif self.emulator == "蓝叠 Hyper-V":
            with open(self.emulator_config_file, 'r') as f:
                lines = f.readlines()
            for line in lines:
                if line.startswith("bst.instance.Pie64.status.adb_port="):
                    port = line.split("=")[-1].strip()[1:-1]
                    dev_name = f"127.0.0.1:{port}"
            cap_method = "JAVACAP"

        from logging import ERROR, getLogger
        getLogger("airtest").setLevel(ERROR)
        
        start_time = time.time()
        while time.time() - start_time <= 30:
            try:
                auto_setup(__file__, devices=[
                    f"android://127.0.0.1:5037/{dev_name}?cap_method={cap_method}&&ori_method=MINICAPORI&&touch_methoda"])
                self.logger.info("Hello,I am WSGR auto commanding system")
                return
            except:
                pass
        
        self.logger.error("连接模拟器失败！")
        raise CriticalErr("连接模拟器失败！")

    def is_android_online(self):
        """判断 timer 给定的设备是否在线
        Returns:
            bool: 在线返回 True,否则返回 False
        """
        raw_res = check_output(f'tasklist /fi "ImageName eq {self.exe_name}').decode('gbk')  # TODO: 检查是否所有windows版本返回都是中文
        return "PID" in raw_res

    def kill_android(self):
        try:
            subprocess.run(["taskkill", "-f", "-im", self.exe_name])
        except:
            pass

    def start_android(self):
        try:
            os.popen(self.start_cmd)
            start_time = time.time()
            while not self.is_android_online():
                time.sleep(1)
                if time.time() - start_time > 120:
                    raise TimeoutError("模拟器启动超时！")
        except Exception as e:
            self.logger.error(f"{e} 请检查模拟器路径!")
            raise CriticalErr("on Restart Android")

    def restart_android(self):
        self.kill_android()
        self.start_android()
