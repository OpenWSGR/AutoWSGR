import os
import re
import subprocess
import time
from subprocess import check_output

import airtest.core.android.android
from airtest.core.api import connect_device

from autowsgr.constants.custom_exceptions import CriticalErr
from autowsgr.constants.data_roots import ADB_ROOT
from autowsgr.utils.function_wrapper import try_for_times

# Win 和 Android 的通信
# Win 向系统写入数据


class WindowsController:
    def __init__(self, config, logger) -> None:
        self.logger = logger

        self.emulator = config["type"]  # 模拟器类型
        self.emulator_name = config["emulator_name"]
        self.start_cmd = config["start_cmd"]  # 模拟器启动命令
        if self.emulator == "蓝叠 Hyper-V":
            assert config["config_file"], "Bluestacks 需要提供配置文件"
            self.emulator_config_file = config["config_file"]

        self.exe_name = os.path.basename(self.start_cmd)  # 自动获得模拟器的进程名
        self.emulator_index = (int(re.search(r'\d+', self.emulator_name).group()) - 5554) / 2

    # ======================== 网络 ========================
    def check_network(self):
        """检查网络状况

        Returns:
            bool:网络正常返回 True,否则返回 False
        """
        return os.system("ping www.moefantasy.com") == 0

    def wait_network(self, timeout=1000):
        """等待到网络恢复"""
        start_time = time.time()
        while time.time() - start_time <= timeout:
            if self.check_network():
                return True
            time.sleep(10)

        return False

    # ======================== 模拟器 ========================
    def ldconsole(self, command, command_arg="", global_command=False):
        """
        使用雷电命令行控制模拟器。

        :param command: 要执行的ldconsole命令。
        :type command: str

        :param command_arg: 命令的附加参数（可选）。
        :type command_arg: str, 可选

        :param global_command: 指示命令是否是全局的（不特定于模拟器实例）。
        :type global_command: bool, 可选

        :return: 雷电命令行执行的输出。
        :rtype: str
        """
        console_dir = os.path.join(os.path.dirname(self.start_cmd), "ldconsole.exe")
        if not global_command:
            ret = os.popen(console_dir + " " + command + " --index " + str(self.emulator_index) + " " + command_arg)
        else:
            ret = os.popen(console_dir + " " + command_arg)
        return ret.read()

    # @try_for_times()
    def connect_android(self) -> airtest.core.android.android.Android:
        """连接指定安卓设备
        Returns:
            dev: airtest.
        """
        if not self.is_android_online():
            self.restart_android()
            time.sleep(15)

        if self.emulator == "雷电":
            dev_name = f"ANDROID:///{self.emulator_name}"
        elif self.emulator == "蓝叠 Hyper-V":
            with open(self.emulator_config_file, "r") as f:
                lines = f.readlines()
            for line in lines:
                if line.startswith("bst.instance.Pie64.status.adb_port="):
                    port = line.split("=")[-1].strip()[1:-1]
                    dev_name = f"ANDROID:///127.0.0.1:{port}"

        from logging import ERROR, getLogger

        getLogger("airtest").setLevel(ERROR)

        start_time = time.time()
        while time.time() - start_time <= 30:
            try:
                dev = connect_device(dev_name)
                self.logger.info("Android Connected!")
                return dev
            except:
                pass

        self.logger.error("连接模拟器失败！")
        raise CriticalErr("连接模拟器失败！")

    def is_android_online(self):
        """判断 timer 给定的设备是否在线
        Returns:
            bool: 在线返回 True, 否则返回 False
        """
        raw_res = self.ldconsole("isrunning")
        self.logger.info("Emulator status: " + raw_res)
        return raw_res == 'running'

    def kill_android(self):
        self.ldconsole("quit")

    def start_android(self):
        try:
            self.ldconsole("launch")
            self.logger.info("Emulator launched")
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
