import json
import os
import re
import subprocess
import time
from typing import Protocol

import airtest.core.android
import requests
from airtest.core.api import connect_device
from airtest.core.error import AdbError

from autowsgr.constants.custom_exceptions import CriticalErr
from autowsgr.types import EmulatorType
from autowsgr.user_config import UserConfig
from autowsgr.utils.logger import Logger


class OSController(Protocol):
    logger: Logger
    emulator_type: EmulatorType
    emulator_name: str
    emulator_start_cmd: str
    emulator_process_name: str
    dev_name: str  # emulator_name 添加类似 Android:/// 前缀, 自动设置

    def check_network(self) -> bool:
        """检查网络状况

        Returns:
            bool:网络正常返回 True,否则返回 False
        """
        response = requests.get('https://www.moefantasy.com', timeout=5)

        return response.status_code == 200

    def wait_network(self, timeout=1000) -> bool:
        """等待到网络恢复"""
        start_time = time.time()
        while time.time() - start_time <= timeout:
            if self.check_network():
                return True
            time.sleep(10)

        return False

    def is_android_online(self) -> bool: ...

    def connect_android(self) -> airtest.core.android.Android:
        """连接指定安卓设备
        Returns:
            dev: airtest.
        """
        if not self.is_android_online():
            self.restart_android()
            time.sleep(15)
        start_time = time.time()
        while time.time() - start_time <= 30:
            try:
                dev = connect_device(self.dev_name)
                dev.snapshot()
                self.logger.info('Android Connected!')
                return dev
            except AdbError:
                self.logger.error('Adb 连接模拟器失败, 正在清除原有连接并重试')
                from airtest.core.android.adb import ADB

                adb = ADB().get_adb_path()
                subprocess.run([adb, 'kill-server'])

        self.logger.error('连接模拟器失败！')
        raise CriticalErr('连接模拟器失败！')

    def kill_android(self) -> None: ...

    def start_android(self) -> None: ...

    def restart_android(self) -> None:
        self.kill_android()
        self.start_android()


class WindowsController(OSController):
    def __init__(
        self,
        config: UserConfig,
        logger: Logger,
    ) -> None:
        self.logger = logger

        self.emulator_type = config.emulator_type
        self.emulator_name = config.emulator_name
        self.emulator_start_cmd = config.emulator_start_cmd
        self.emulator_process_name = config.emulator_process_name

        match self.emulator_type:
            case EmulatorType.leidian | EmulatorType.bluestacks:
                self.dev_name = f'Android:///{self.emulator_name}'
            case _:
                self.dev_name = f'Android:///{self.emulator_name}'

    def is_android_online(self) -> bool:
        """判断 timer 给定的设备是否在线
        Returns:
            bool: 在线返回 True, 否则返回 False
        """
        match self.emulator_type:
            case EmulatorType.leidian:
                raw_res = self.__ldconsole('isrunning')
                self.logger.debug('EmulatorType status: ' + raw_res)
                return raw_res == 'running'
            case EmulatorType.yunshouji:
                return True
            case _:
                # TODO: 检查是否所有windows版本返回都是中文
                raw_res = subprocess.check_output(
                    f'tasklist /fi "ImageName eq {self.emulator_process_name}',
                ).decode('gbk')
                return 'PID' in raw_res

    def kill_android(self) -> None:
        try:
            match self.emulator_type:
                case EmulatorType.leidian:
                    self.__ldconsole('quit')
                case EmulatorType.yunshouji:
                    self.logger.info('云手机无需关闭')
                case _:
                    subprocess.run(['taskkill', '-f', '-im', self.emulator_process_name])
        except Exception as e:
            raise CriticalErr(f'停止模拟器失败: {e}')

    def start_android(self) -> None:
        try:
            match self.emulator_type:
                case EmulatorType.leidian:
                    self.__ldconsole('launch')
                case EmulatorType.yunshouji:
                    self.logger.info('云手机无需启动')
                case _:
                    os.popen(self.emulator_start_cmd)

            start_time = time.time()
            while not self.is_android_online():
                time.sleep(1)
                if time.time() - start_time > 120:
                    raise TimeoutError('模拟器启动超时！')
        except Exception as e:
            raise CriticalErr(f'模拟器启动失败: {e}')

    def __ldconsole(self, command, command_arg='', global_command=False) -> str:
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
        console_dir = os.path.join(os.path.dirname(self.emulator_start_cmd), 'ldconsole.exe')
        emulator_index = (int(re.search(r'\d+', self.emulator_name).group()) - 5554) / 2

        if not global_command:
            cmd = [
                console_dir,
                command,
                '--index',
                str(emulator_index),
                command_arg,
            ]
        else:
            cmd = [console_dir, command_arg]

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True,
        )
        output, error = process.communicate()

        return (
            output.decode('utf-8', errors='replace')
            if output
            else error.decode('utf-8', errors='replace')
        )


class MacController(OSController):
    def __init__(self, config: UserConfig, logger: Logger) -> None:
        self.logger = logger

        self.emulator_type = config.emulator_type
        self.emulator_name = config.emulator_name
        self.emulator_start_cmd = config.emulator_start_cmd
        self.emulator_process_name = config.emulator_process_name

        self.dev_name = f'Android:///{self.emulator_name}'
        if self.emulator_type == EmulatorType.mumu:
            self.mumu_tool = os.path.join(config.emulator_start_cmd, 'Contents/MacOS/mumutool')
            self.prot = self.emulator_name.split(':')[-1]

    def is_android_online(self) -> bool:
        try:
            subprocess.check_output(f'pgrep -f {self.emulator_process_name}', shell=True)
            if self.emulator_type == EmulatorType.mumu:
                marsh = self.__get_mumu_info()
                return any(self.prot == v.get('adb_port') for v in marsh['return']['results'])
            return True
        except subprocess.CalledProcessError:
            return False

    def kill_android(self) -> None:
        if self.emulator_type == EmulatorType.mumu:
            return
        subprocess.Popen(f'pkill -9 -f {self.emulator_process_name}', shell=True)

    def start_android(self) -> None:
        subprocess.Popen(f'open -a {self.emulator_start_cmd}', shell=True)
        if self.emulator_type == EmulatorType.mumu:
            marsh = self.__get_mumu_info()
            for k, v in enumerate(marsh['return']['results']):
                if self.prot == v.get('adb_port'):
                    cmd = f'{self.mumu_tool} restart {k}'
                    subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        shell=True,
                    )

    def __get_mumu_info(self) -> dict:
        cmd = f'{self.mumu_tool} info all'
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True,
        )
        output, error = process.communicate()
        tempStr = output.decode()
        try:
            return json.loads(tempStr)
        except Exception as e:
            self.logger.error(f'{cmd} {e}')
        return {}
