import os
import sys
from enum import Enum

from autowsgr.utils.operator import unzip_element


class BaseEnum(Enum):
    """提供更友好的中文报错信息"""

    @classmethod
    def _missing_(cls, value: str) -> None:
        supported_values = ', '.join(
            [enum_object.value.__str__() for enum_object in cls.__members__.values()],
        )
        raise ValueError(f'"{value}" 不是合法的{cls.__name__}取值. 支持的有: [{supported_values}]')

    @classmethod
    def enum(cls) -> list:
        return list(cls.__members__.values())


class StrEnum(str, BaseEnum):
    @classmethod
    def get_all_chars(cls) -> list:
        char_list = []
        for name in unzip_element(cls.enum()):
            for char in name:
                char_list = list({*char_list, char})
        return char_list


class IntEnum(int, BaseEnum):
    pass


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
    def auto(cls) -> 'OSType':
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
            match self:
                case EmulatorType.leidian:
                    return 'emulator-5554'
                case EmulatorType.bluestacks:
                    return '127.0.0.1:5555'
                case EmulatorType.mumu:
                    return '127.0.0.1:16384'
                case _:
                    raise ValueError(f'没有为 {self.value} 模拟器设置默认emulator_name，请手动指定')
        elif os == OSType.macos:
            match self:
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
            match self:
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
        match self:
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
        match self:
            case GameAPP.official:
                return 'com.huanmeng.zhanjian2'
            case GameAPP.xiaomi:
                return 'com.hoolai.zjsnr.mi'
            case GameAPP.tencent:
                return 'com.tencent.tmgp.zhanjian2'
            case _:
                raise ValueError(f'没有为 {self} 设置包名，请手动指定')


class RepairMode(IntEnum):
    moderate_damage = 1
    """中破就修"""
    severe_damage = 2
    """大破才修"""
    repairing = 3
    """正在修理中的"""


class FightCondition(IntEnum):
    steady_advance = 1
    """稳步前进"""
    firepower_forever = 2
    """火力万岁"""
    caution = 3
    """小心翼翼"""
    aim = 4
    """瞄准"""
    search_formation = 5
    """搜索阵型"""

    @property
    def relative_click_position(self) -> tuple[float, float]:
        return [
            None,
            [0.215, 0.409],
            [0.461, 0.531],
            [0.783, 0.362],
            [0.198, 0.764],
            [0.763, 0.74],
        ][self.value]


class Formation(IntEnum):
    single_column = 1
    """单纵阵"""
    double_column = 2
    """复纵阵"""
    circular = 3
    """轮型阵"""
    wedge = 4
    """梯形阵"""
    single_horizontal = 5
    """单横阵"""

    @property
    def relative_position(self) -> tuple[float, float]:
        return 0.597, self.value * 0.185 - 0.037


class SearchEnemyAction(StrEnum):
    no_action = 'no_action'
    retreat = 'retreat'
    detour = 'detour'
    refresh = 'refresh'


class ShipType(StrEnum):
    CV = '航母'
    CVL = '轻母'
    AV = '装母'
    BB = '战列'
    BBV = '航战'
    BC = '战巡'
    CA = '重巡'
    CAV = '航巡'
    CLT = '雷巡'
    CL = '轻巡'
    BM = '重炮'
    DD = '驱逐'
    SSG = '导潜'
    SS = '潜艇'
    SC = '炮潜'
    NAP = '补给'
    ASDG = '导驱'
    AADG = '防驱'
    KP = '导巡'
    CG = '防巡'
    CBG = '大巡'
    BG = '导战'
    Other = '其他'

    @property
    def relative_position_in_destroy(self) -> tuple[float, float]:
        dict = {
            ShipType.CV: (0.555, 0.197),
            ShipType.CVL: (0.646, 0.197),
            ShipType.AV: (0.738, 0.197),
            ShipType.BB: (0.830, 0.197),
            ShipType.BBV: (0.922, 0.197),
            ShipType.BC: (0.556, 0.288),
            ShipType.CA: (0.646, 0.288),
            ShipType.CAV: (0.738, 0.288),
            ShipType.CLT: (0.830, 0.288),
            ShipType.CL: (0.922, 0.288),
            ShipType.BM: (0.556, 0.379),
            ShipType.DD: (0.646, 0.379),
            ShipType.SSG: (0.738, 0.379),
            ShipType.SS: (0.830, 0.379),
            ShipType.SC: (0.922, 0.379),
            ShipType.NAP: (0.555, 0.470),
            ShipType.ASDG: (0.646, 0.470),
            ShipType.AADG: (0.738, 0.470),
            ShipType.KP: (0.830, 0.470),
            ShipType.CG: (0.922, 0.470),
            ShipType.CBG: (0.555, 0.561),
            ShipType.BG: (0.646, 0.561),
            ShipType.Other: (0.738, 0.561),
        }
        return dict[self]


class DestroyShipWorkMode(IntEnum):
    """拆解工作模式"""

    disable = 0
    """不启用舰种分类"""
    include = 1
    """拆哪些船"""
    exclude = 2
    """不拆哪些船"""


class ConditionFlag(StrEnum):
    DOCK_FULL = 'dock is full'
    """船坞已满并且没有设置自动解装"""
    FIGHT_END = 'fight end'
    """战斗结束标志, 一般不返回这个, 和 success 相同"""
    FIGHT_CONTINUE = 'fight continue'
    """战斗继续"""
    OPERATION_SUCCESS = 'success'
    """战斗流程正常结束 (到达了某个结束点或者选择了回港)"""
    BATTLE_TIMES_EXCEED = 'out of times'
    """战斗超时"""
    SKIP_FIGHT = 'skip fight'
    """跳过战斗"""
    SL = 'SL'
    """需要 / 进行了 SL 操作"""


class FormationName(StrEnum):
    single_column = '单纵'
    double_column = '复纵'
    circular = '轮型'
    wedge = '梯形'
    single_horizontal = '单横'
