import json
import subprocess
import time

import airtest.core.android
import requests
from airtest.core.api import connect_device

from autowsgr.constants.custom_exceptions import CriticalErr
from autowsgr.utils.logger import Logger


class MacController:
    def __init__(self, config, logger: Logger) -> None:
        self.logger = logger
        self.emulator_name = config.emulator_name
        self.device = None
        self.path = config.emulator_start_cmd  #
        self.prot = self.emulator_name.split(':')[-1]

    def check_network(self):
        """检查网络状况

        Returns:
            bool:网络正常返回 True,否则返回 False
        """
        response = requests.get('https://www.moefantasy.com', timeout=5)

        return response.status_code == 200

    def wait_network(self, timeout=1000):
        """等待到网络恢复"""
        start_time = time.time()
        while time.time() - start_time <= timeout:
            if self.check_network():
                return True
            time.sleep(10)

        return False

    def connect_android(self) -> airtest.core.android.Android:
        android = f'Android:///{self.emulator_name}'
        try:
            self.device = connect_device(android)
            return self.device
        except Exception:
            self.logger.error('连接模拟器失败！')
            raise CriticalErr('连接模拟器失败！')

    def is_android_online(self):
        marsh = self.__get_info_all()
        return any(self.prot == v.get('adb_port') for v in marsh['return']['results'])

    def restart_android(self):
        self.__start_android()

    def __kill_android(self):
        marsh = self.__get_info_all()
        for k, v in enumerate(marsh['return']['results']):
            if self.prot == v.get('adb_port'):
                cmd = f'.{self.path}/mumutool close {k}'
                subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=True,
                )

        return True

    def __start_android(self):
        marsh = self.__get_info_all()

        for k, v in enumerate(marsh['return']['results']):
            if self.prot == v.get('adb_port'):
                cmd = f'{self.path}/mumutool restart {k}'
                subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=True,
                )
        return True

    def __get_info_all(self):
        cmd = f'{self.path}/mumutool info all'
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
