"""全局枚举类型定义。

所有与游戏语义相关的枚举集中于此，供各层引用。
"""

from __future__ import annotations

import os
import sys
from enum import Enum
from dataclasses import dataclass


# ── 枚举基类 ──


class BaseEnum(Enum):
    """提供更友好的中文报错信息。"""

    @classmethod
    def _missing_(cls, value: object) -> None:
        supported = ", ".join(str(m.value) for m in cls)
        raise ValueError(f'"{value}" 不是合法的 {cls.__name__} 取值。 支持: [{supported}]')


class StrEnum(str, BaseEnum):
    """字符串枚举基类。"""


class IntEnum(int, BaseEnum):
    """整数枚举基类。"""


# ── 系统 / 环境 ──


class OSType(StrEnum):
    """操作系统类型。"""

    windows = "Windows"
    linux = "linux"
    macos = "macOS"

    @classmethod
    def auto(cls) -> OSType:
        """根据当前运行环境自动检测。"""
        if sys.platform.startswith("win"):
            return cls.windows
        if sys.platform == "darwin":
            return cls.macos
        if sys.platform.startswith("linux"):
            if cls._is_wsl():
                return cls.linux
            raise ValueError("暂不支持非 WSL 的 Linux 系统")
        raise ValueError(f"不支持的操作系统: {sys.platform}")

    @staticmethod
    def _is_wsl() -> bool:
        if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
            return True
        for path in ("/proc/sys/kernel/osrelease", "/proc/version"):
            try:
                with open(path, encoding="utf-8", errors="ignore") as fh:
                    if "microsoft" in fh.read().lower():
                        return True
            except OSError:
                continue
        return False


class EmulatorType(StrEnum):
    """模拟器类型。"""

    leidian = "雷电"
    bluestacks = "蓝叠"
    mumu = "MuMu"
    yunshouji = "云手机"
    others = "其他"

    # ── 自动检测辅助 ──

    def default_emulator_name(self, os_type: OSType) -> str:
        """返回对应操作系统下的默认 ADB serial。"""
        if os_type == OSType.windows:
            match self:
                case EmulatorType.leidian:
                    return "emulator-5554"
                case EmulatorType.bluestacks:
                    return "127.0.0.1:5555"
                case EmulatorType.mumu:
                    return "127.0.0.1:16384"
                case _:
                    raise ValueError(f"没有为 {self.value} 模拟器设置默认 emulator_name，请手动指定")
        elif os_type == OSType.macos:
            match self:
                case EmulatorType.bluestacks:
                    return "127.0.0.1:5555"
                case EmulatorType.mumu:
                    return "127.0.0.1:5555"
                case _:
                    raise ValueError(f"没有为 {self.value} 模拟器设置默认 emulator_name，请手动指定")
        raise ValueError(f"没有为 {os_type} 操作系统设置默认 emulator_name，请手动指定")

    def auto_emulator_path(self, os_type: OSType) -> str:
        """自动从系统中获取模拟器可执行文件路径。"""
        dispatch = {
            OSType.windows: self._windows_auto_emulator_path,
            OSType.macos: self._macos_auto_emulator_path,
        }
        func = dispatch.get(os_type)
        if func is None:
            raise ValueError(f"没有为 {os_type} 操作系统设置 emulator_path 查找方法，请手动指定")
        return func()

    def _windows_auto_emulator_path(self) -> str:
        """Windows 下从注册表中自动识别模拟器安装路径。"""
        import winreg

        try:
            match self:
                case EmulatorType.leidian:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\leidian") as key:
                        sub_key_name = winreg.EnumKey(key, 0)
                        with winreg.OpenKey(key, sub_key_name) as sub:
                            path, _ = winreg.QueryValueEx(sub, "InstallDir")
                            return os.path.join(path, "dnplayer.exe")
                case EmulatorType.bluestacks:
                    with winreg.OpenKey(
                        winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\BlueStacks_nxt_cn"
                    ) as key:
                        path, _ = winreg.QueryValueEx(key, "InstallDir")
                        return os.path.join(path, "HD-Player.exe")
                case EmulatorType.mumu:
                    try:
                        with winreg.OpenKey(
                            winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\MuMuPlayer-12.0",
                        ) as key:
                            path, _ = winreg.QueryValueEx(key, "UninstallString")
                            return os.path.join(
                                os.path.dirname(path), "shell", "MuMuPlayer.exe"
                            ).strip('"')
                    except FileNotFoundError:
                        with winreg.OpenKey(
                            winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\MuMuPlayer",
                        ) as key:
                            path, _ = winreg.QueryValueEx(key, "UninstallString")
                            return os.path.join(
                                os.path.dirname(path), "nx_main", "MuMuManager.exe"
                            ).strip('"')
                case _:
                    raise ValueError(
                        f"没有为 {self.value} 设置安装路径查找方法，请手动指定"
                    )
        except FileNotFoundError:
            raise FileNotFoundError(f"没有找到 {self.value} 的安装路径")

    def _macos_auto_emulator_path(self) -> str:
        """macOS 下自动识别模拟器安装路径。"""
        match self:
            case EmulatorType.mumu:
                path = "/Applications/MuMuPlayer.app"
            case EmulatorType.bluestacks:
                path = "/Applications/BlueStacks.app"
            case _:
                raise ValueError(f"没有为 {self.value} 设置安装路径查找方法，请手动指定")

        if os.path.exists(path):
            return path
        home_path = os.path.expanduser(f"~{path}")
        if os.path.exists(home_path):
            return home_path
        raise FileNotFoundError(f"没有找到 {self.value} 的安装路径")


class OcrBackend(StrEnum):
    """OCR 后端。"""

    easyocr = "easyocr"
    paddleocr = "paddleocr"


# ── 游戏概念 ──


class GameAPP(StrEnum):
    """游戏渠道服。"""

    official = "官服"
    xiaomi = "小米"
    tencent = "应用宝"

    @property
    def package_name(self) -> str:
        """返回 Android 包名。"""
        match self:
            case GameAPP.official:
                return "com.huanmeng.zhanjian2"
            case GameAPP.xiaomi:
                return "com.hoolai.zjsnr.mi"
            case GameAPP.tencent:
                return "com.tencent.tmgp.zhanjian2"
            case _:
                raise ValueError(f"没有为 {self} 设置包名，请手动指定")


class RepairMode(IntEnum):
    """修理策略。"""

    moderate_damage = 1
    """中破就修"""
    severe_damage = 2
    """大破才修"""
    repairing = 3
    """正在修理中"""


class FightCondition(IntEnum):
    """战况选择（出征前）。"""

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
        """对应的相对点击坐标 (x, y)。"""
        positions: dict[int, tuple[float, float]] = {
            1: (0.215, 0.409),
            2: (0.461, 0.531),
            3: (0.783, 0.362),
            4: (0.198, 0.764),
            5: (0.763, 0.740),
        }
        return positions[self.value]


class Formation(IntEnum):
    """阵型选择。"""

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
        """阵型按钮的相对坐标 (x, y)。"""
        return 0.597, self.value * 0.185 - 0.037


@dataclass
class FleetSelection:
    """战备舰队获取界面中单个可选项的信息。

    Attributes
    ----------
    name:
        舰船或技能名称。
    cost:
        购买所需分数。
    click_position:
        卡片点击位置 (相对坐标)。
    """

    name: str
    cost: int
    click_position: tuple[float, float]

class SearchEnemyAction(StrEnum):
    """索敌后可执行的动作。"""

    no_action = "no_action"
    retreat = "retreat"
    detour = "detour"
    refresh = "refresh"


class ShipType(StrEnum):
    """舰船类型。"""

    CV = "航母"
    CVL = "轻母"
    AV = "装母"
    BB = "战列"
    BBV = "航战"
    BC = "战巡"
    CA = "重巡"
    CAV = "航巡"
    CLT = "雷巡"
    CL = "轻巡"
    BM = "重炮"
    DD = "驱逐"
    SSG = "导潜"
    SS = "潜艇"
    SC = "炮潜"
    NAP = "补给"
    ASDG = "导驱"
    AADG = "防驱"
    KP = "导巡"
    CG = "防巡"
    CBG = "大巡"
    BG = "导战"
    Other = "其他"

    @property
    def relative_position_in_destroy(self) -> tuple[float, float]:
        """拆解界面中该舰种按钮的相对坐标。"""
        _map: dict[ShipType, tuple[float, float]] = {
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
        return _map[self]


class DestroyShipWorkMode(IntEnum):
    """拆解工作模式。"""

    disable = 0
    """不启用舰种分类"""
    include = 1
    """只拆指定舰种"""
    exclude = 2
    """拆除指定舰种以外的所有舰种"""


class ConditionFlag(StrEnum):
    """战斗流程状态标记。"""

    DOCK_FULL = "dock is full"
    """船坞已满且未设置自动解装"""
    FIGHT_END = "fight end"
    """战斗结束标志"""
    FIGHT_CONTINUE = "fight continue"
    """战斗继续"""
    OPERATION_SUCCESS = "success"
    """战斗流程正常结束"""
    BATTLE_TIMES_EXCEED = "out of times"
    """战斗次数用尽"""
    SKIP_FIGHT = "skip fight"
    """跳过战斗"""
    SL = "SL"
    """需要 / 进行了 SL 操作"""
    
class PageName(StrEnum):
    """游戏页面名称。"""

    MAIN = "主页面"
    """主页面"""
    MAP = "地图页面"
    """地图页面"""
    BATTLE_PREP = "出征准备"
    """出征准备"""
    SIDEBAR = "侧边栏"
    """侧边栏"""
    MISSION = "任务页面"
    """任务页面"""
    BACKYARD = "后院页面"
    """后院页面"""
    BATH = "浴室页面"
    """浴室页面"""
    CANTEEN = "食堂页面"
    """食堂页面"""
    CHOOSE_REPAIR = "选择修理页面"
    """选择修理页面"""
    BUILD = "建造页面"
    """建造页面"""
    INTENSIFY = "强化页面"
    """强化页面"""
    FRIEND = "好友页面"
    """好友页面"""
    DECISIVE_BATTLE = "决战页面"
    """决战页面"""


class MapEntrance(StrEnum):
    """地图入口。"""

    alpha = "alpha"
    beta = "beta"
