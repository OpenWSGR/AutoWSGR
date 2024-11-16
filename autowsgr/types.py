import os
import sys


if sys.platform == 'win32':
    import winreg

from enum import Enum


class StrEnum(str, Enum):
    pass


class OcrBackend(StrEnum):
    easyocr = 'easyocr'
    paddleocr = 'paddleocr'


def windows_auto_emulator_path(self):
    """自动识别模拟器路径"""
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


def mac_auto_emulator_path() -> str:
    # 开始查找mac上的mumu模拟器，这里只适配了mumu模拟器
    # 全局安装目录-不存在的时候再去当前用户应用目录
    path = '/Applications/MuMuPlayer.app/Contents/MacOS'
    if os.path.exists(path):
        return path
    return f'~/{path}'


class EmulatorType(StrEnum):
    leidian = '雷电'
    bluestacks = '蓝叠 Hyper-V'
    mumu = 'MuMu'
    yunshouji = '云手机'
    others = '其他'

    @property
    def default_emulator_name(self) -> str:
        match self.value:
            case EmulatorType.leidian:
                return 'emulator-5554'
            case EmulatorType.mumu:
                return '127.0.0.1:16384'
            case _:
                raise ValueError(f'没有为 {self.value} 设置默认连接名称，请手动指定')

    @property
    def auto_emulator_path(self) -> str:
        adapter_fun = {
            'win32': lambda: windows_auto_emulator_path(self),
            'linux': lambda: '',
            'darwin': lambda: mac_auto_emulator_path(),
        }
        return adapter_fun[sys.platform]()


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
