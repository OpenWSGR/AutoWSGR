import os
import sys
from enum import Enum
from typing_extensions import Self


class StrEnum(str, Enum):
    """提供更友好的中文报错信息"""

    @classmethod
    def _missing_(cls, value: str) -> None:
        supported_values = ', '.join(cls.__members__.values())
        raise ValueError(f'"{value}" 不是合法的{cls.__name__}取值. 支持的有: [{supported_values}]')


"""如果有一些功能在主程序中尚未支持（比如linux系统），请在本模块中对其进行raise
   主程序中将不考虑对这些异常的处理
"""


class OcrBackend(StrEnum):
    easyocr = 'easyocr'
    paddleocr = 'paddleocr'


class OSType(StrEnum):
    windows = 'Windows'
    linux = 'Linux'
    macos = 'macOS'

    @classmethod
    def auto(cls) -> Self:
        if sys.platform.startswith('win'):
            return OSType.windows
        if sys.platform == 'darwin':
            return OSType.macos
        raise ValueError(f'不支持的操作系统 {sys.platform}')


class EmulatorType(StrEnum):
    leidian = '雷电'
    bluestacks = '蓝叠'
    mumu = 'MuMu'
    yunshouji = '云手机'
    others = '其他'

    def default_emulator_name(self, os: OSType) -> str:
        """自动获取默认模拟器连接名称"""
        if os == OSType.windows:
            match self.value:
                case EmulatorType.leidian:
                    return 'emulator-5554'
                case EmulatorType.mumu:
                    return '127.0.0.1:16384'
                case _:
                    raise ValueError(f'没有为 {self.value} 模拟器设置默认emulator_name，请手动指定')
        elif os == OSType.macos:
            match self.value:
                case EmulatorType.bluestacks:
                    return '127.0.0.1:5555'
                case EmulatorType.mumu:
                    return '127.0.0.1:5555'
                case _:
                    raise ValueError(f'没有为 {self.value} 模拟器设置默认emulator_name，请手动指定')
        else:
            raise ValueError(f'没有为 {os} 操作系统设置默认emulator_name，请手动指定')

    def auto_emulator_path(self, os: OSType) -> str:
        """自动获取模拟器路径"""
        adapter_fun = {
            OSType.windows: self.windows_auto_emulator_path,
            OSType.macos: self.macos_auto_emulator_path,
        }
        if os in adapter_fun:
            return adapter_fun[os]()
        raise ValueError(f'没有为 {os} 操作系统设置emulator_path查找方法，请手动指定')

    def windows_auto_emulator_path(self) -> str:
        """Windows自动识别模拟器路径"""
        import winreg

        try:
            match self.value:
                case EmulatorType.leidian:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\leidian') as key:
                        sub_key = winreg.EnumKey(key, 0)
                        with winreg.OpenKey(key, sub_key) as sub_key:
                            path, _ = winreg.QueryValueEx(sub_key, 'InstallDir')
                            return os.path.join(path, 'dnplayer.exe')
                case EmulatorType.bluestacks:
                    with winreg.OpenKey(
                        winreg.HKEY_LOCAL_MACHINE,
                        r'SOFTWARE\BlueStacks_nxt_cn',
                    ) as key:
                        path, _ = winreg.QueryValueEx(key, 'InstallDir')
                        return os.path.join(path, 'HD-Player.exe')
                case EmulatorType.mumu:
                    with winreg.OpenKey(
                        winreg.HKEY_LOCAL_MACHINE,
                        r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\MuMuPlayer-12.0',
                    ) as key:
                        path, _ = winreg.QueryValueEx(key, 'UninstallString')
                        return os.path.join(os.path.dirname(path), 'shell', 'MuMuPlayer.exe')
                case _:
                    raise ValueError(f'没有为 {self.value} 设置安装路径查找方法，请手动指定')
        except FileNotFoundError:
            raise FileNotFoundError(f'没有找到 {self.value} 的安装路径')

    def macos_auto_emulator_path(self) -> str:
        """macOS自动识别模拟器路径"""
        match self.value:
            case EmulatorType.mumu:
                path = '/Applications/MuMuPlayer.app'
            case EmulatorType.bluestacks:
                path = '/Applications/BlueStacks.app'
            case _:
                raise ValueError(f'没有为 {self.value} 设置安装路径查找方法，请手动指定')

        if os.path.exists(path):
            return path
        if os.path.exists(f'~/{path}'):
            # 全局安装目录-不存在的时候再去当前用户应用目录
            return f'~/{path}'
        raise FileNotFoundError(f'没有找到 {self.value} 的安装路径')


class GameAPP(StrEnum):
    official = '官服'
    xiaomi = '小米'
    tencent = '应用宝'

    @property
    def app_name(self) -> str:
        match self.value:
            case GameAPP.official:
                return 'com.huanmeng.zhanjian2'
            case GameAPP.xiaomi:
                return 'com.hoolai.zjsnr.mi'
            case GameAPP.tencent:
                return 'com.tencent.tmgp.zhanjian2'
            case _:
                raise ValueError(f'没有为 {self.value} 设置包名，请手动指定')
