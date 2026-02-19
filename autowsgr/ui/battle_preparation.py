"""出征准备页面 UI 控制器。

覆盖 **出征准备** 页面的全部界面交互。

页面布局::

    ┌──────────────────────────────────────────────────────────────┐
    │ ◁  出征准备                               🔧 修理舰船      │
    │                                                              │
    │  [1队]  2队   3队   4队    预  ⊕  ♛                        │
    │                                                              │
    │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐        │
    │  │ 舰1 │ │ 舰2 │ │ 舰3 │ │ 舰4 │ │ 舰5 │ │ 舰6 │        │
    │  └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘        │
    │                                                              │
    │  [综合战力]  快速补给  快速修理  装备预览                   │
    │                                                              │
    │  ☑ 自动补给                        [ 开始出征 ]            │
    └──────────────────────────────────────────────────────────────┘

    [ ] = 当前选中项

坐标体系:
    所有坐标为相对值 (0.0–1.0)，与分辨率无关。
    分为 **探测坐标** (采样颜色用于状态检测) 和 **点击坐标** (执行操作)。

使用方式::

    from autowsgr.ui.battle_preparation import BattlePreparationPage, Panel

    page = BattlePreparationPage(ctrl)

    # 状态查询 (静态方法，只需截图)
    screen = ctrl.screenshot()
    if BattlePreparationPage.is_current_page(screen):
        fleet = BattlePreparationPage.get_selected_fleet(screen)
        panel = BattlePreparationPage.get_active_panel(screen)

    # 执行动作
    page.select_fleet(2)
    page.quick_supply()
    page.start_battle()
"""

from __future__ import annotations

import enum

import numpy as np
from loguru import logger

from autowsgr.emulator.controller import AndroidController
from autowsgr.vision.matcher import Color, PixelChecker


# ═══════════════════════════════════════════════════════════════════════════════
# 枚举
# ═══════════════════════════════════════════════════════════════════════════════


class Panel(enum.Enum):
    """出征准备底部面板标签。"""

    STATS = "综合战力"
    QUICK_SUPPLY = "快速补给"
    QUICK_REPAIR = "快速修理"
    EQUIPMENT = "装备预览"


# ═══════════════════════════════════════════════════════════════════════════════
# 选中态参考颜色 (RGB)
# ═══════════════════════════════════════════════════════════════════════════════

_FLEET_ACTIVE = Color.of(16, 133, 228)
"""舰队标签选中态颜色 — 明亮蓝色。"""

_PANEL_ACTIVE = Color.of(30, 139, 240)
"""面板标签选中态颜色 — 明亮蓝色。"""

_AUTO_SUPPLY_ON = Color.of(13, 140, 233)
"""自动补给启用态颜色 — 蓝色勾选框。"""

_STATE_TOLERANCE = 30.0
"""状态检测颜色容差。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 探测坐标 — 采样颜色判断状态
# ═══════════════════════════════════════════════════════════════════════════════

FLEET_PROBE: dict[int, tuple[float, float]] = {
    1: (0.0750, 0.1731),
    2: (0.1974, 0.1778),
    3: (0.3271, 0.1694),
    4: (0.4479, 0.1713),
}
"""舰队标签探测点。选中项探测颜色 ≈ (16, 133, 228)。"""

PANEL_PROBE: dict[Panel, tuple[float, float]] = {
    Panel.STATS:        (0.1214, 0.7907),
    Panel.QUICK_SUPPLY: (0.2625, 0.7944),
    Panel.QUICK_REPAIR: (0.3932, 0.7926),
    Panel.EQUIPMENT:    (0.5250, 0.7926),
}
"""面板标签探测点。选中项探测颜色 ≈ (30, 139, 240)。"""

SUPPORT_PROBE: tuple[float, float] = (0.6521, 0.1843)
"""战役支援探测点。"""

AUTO_SUPPLY_PROBE: tuple[float, float] = (0.0552, 0.9343)
"""自动补给探测点。启用态探测颜色 ≈ (13, 140, 233)。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 点击坐标 — 执行操作
# ═══════════════════════════════════════════════════════════════════════════════

CLICK_BACK: tuple[float, float] = (0.022, 0.058)
"""回退按钮 (◁)。"""

CLICK_FLEET: dict[int, tuple[float, float]] = {
    1: (0.088, 0.170),
    2: (0.197, 0.170),
    3: (0.327, 0.170),
    4: (0.448, 0.170),
}
"""舰队标签点击位置。"""

CLICK_PANEL: dict[Panel, tuple[float, float]] = {
    Panel.STATS:        (0.155, 0.793),
    Panel.QUICK_SUPPLY: (0.286, 0.793),
    Panel.QUICK_REPAIR: (0.417, 0.793),
    Panel.EQUIPMENT:    (0.548, 0.793),
}
"""面板标签点击位置。"""

CLICK_SUPPORT: tuple[float, float] = (0.640, 0.180)
"""战役支援点击位置。"""

CLICK_AUTO_SUPPLY: tuple[float, float] = (0.095, 0.935)
"""自动补给复选框点击位置。"""

CLICK_START_BATTLE: tuple[float, float] = (0.850, 0.935)
"""「开始出征」按钮点击位置。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 页面控制器
# ═══════════════════════════════════════════════════════════════════════════════


class BattlePreparationPage:
    """出征准备页面控制器。

    **状态查询** 为 ``staticmethod``，只需截图即可调用。
    **操作动作** 为实例方法，通过注入的控制器执行。

    Parameters
    ----------
    ctrl:
        Android 设备控制器实例。
    """

    def __init__(self, ctrl: AndroidController) -> None:
        self._ctrl = ctrl

    # ── 页面识别 ──────────────────────────────────────────────────────────

    @staticmethod
    def is_current_page(screen: np.ndarray) -> bool:
        """判断截图是否为出征准备页面。

        检测逻辑:

        1. 舰队标签区 (4 个探测点) 恰好有 1 个为选中蓝色
        2. 面板标签区 (4 个探测点) 恰好有 1 个为选中蓝色

        此组合在其他页面中不会同时出现，能可靠识别本页面。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。
        """
        fleet_active = sum(
            1 for (x, y) in FLEET_PROBE.values()
            if PixelChecker.get_pixel(screen, x, y).near(
                _FLEET_ACTIVE, _STATE_TOLERANCE,
            )
        )
        if fleet_active != 1:
            return False

        panel_active = sum(
            1 for (x, y) in PANEL_PROBE.values()
            if PixelChecker.get_pixel(screen, x, y).near(
                _PANEL_ACTIVE, _STATE_TOLERANCE,
            )
        )
        return panel_active == 1

    # ── 状态查询 ──────────────────────────────────────────────────────────

    @staticmethod
    def get_selected_fleet(screen: np.ndarray) -> int | None:
        """获取当前选中的舰队编号。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。

        Returns
        -------
        int | None
            选中的舰队编号 (1–4)，无法确定时返回 ``None``。
        """
        for fleet_id, (x, y) in FLEET_PROBE.items():
            pixel = PixelChecker.get_pixel(screen, x, y)
            if pixel.near(_FLEET_ACTIVE, _STATE_TOLERANCE):
                return fleet_id
        return None

    @staticmethod
    def get_active_panel(screen: np.ndarray) -> Panel | None:
        """获取当前激活的底部面板。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。

        Returns
        -------
        Panel | None
            当前面板，或 ``None``。
        """
        for panel, (x, y) in PANEL_PROBE.items():
            pixel = PixelChecker.get_pixel(screen, x, y)
            if pixel.near(_PANEL_ACTIVE, _STATE_TOLERANCE):
                return panel
        return None

    @staticmethod
    def is_auto_supply_enabled(screen: np.ndarray) -> bool:
        """检测自动补给是否启用。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。
        """
        x, y = AUTO_SUPPLY_PROBE
        return PixelChecker.get_pixel(screen, x, y).near(
            _AUTO_SUPPLY_ON, _STATE_TOLERANCE,
        )

    # ── 动作 — 回退 / 出征 ───────────────────────────────────────────────

    def go_back(self) -> None:
        """点击回退按钮 (◁)，返回上一页。"""
        logger.info("[UI] 出征准备 → 回退")
        self._ctrl.click(*CLICK_BACK)

    def start_battle(self) -> None:
        """点击「开始出征」按钮。"""
        logger.info("[UI] 出征准备 → 开始出征")
        self._ctrl.click(*CLICK_START_BATTLE)

    # ── 动作 — 舰队选择 ──────────────────────────────────────────────────

    def select_fleet(self, fleet: int) -> None:
        """选择舰队。

        Parameters
        ----------
        fleet:
            舰队编号 (1–4)。

        Raises
        ------
        ValueError
            编号不在 1–4 范围内。
        """
        if fleet not in CLICK_FLEET:
            raise ValueError(f"舰队编号必须为 1–4，收到: {fleet}")
        logger.info("[UI] 出征准备 → 选择 {}队", fleet)
        self._ctrl.click(*CLICK_FLEET[fleet])

    # ── 动作 — 面板切换 ──────────────────────────────────────────────────

    def select_panel(self, panel: Panel) -> None:
        """切换底部面板标签。

        Parameters
        ----------
        panel:
            目标面板。
        """
        logger.info("[UI] 出征准备 → {}", panel.value)
        self._ctrl.click(*CLICK_PANEL[panel])

    def quick_supply(self) -> None:
        """点击「快速补给」标签。"""
        self.select_panel(Panel.QUICK_SUPPLY)

    def quick_repair(self) -> None:
        """点击「快速修理」标签。"""
        self.select_panel(Panel.QUICK_REPAIR)

    # ── 动作 — 开关 ──────────────────────────────────────────────────────

    def toggle_battle_support(self) -> None:
        """切换战役支援开关。

        .. note::
            此方法仅点击开关区域，不判断当前状态。
            需要配合截图 + 状态查询确认最终状态。
        """
        logger.info("[UI] 出征准备 → 切换战役支援")
        self._ctrl.click(*CLICK_SUPPORT)

    def toggle_auto_supply(self) -> None:
        """切换自动补给开关。

        .. note::
            此方法仅点击复选框，不判断当前状态。
            如需确保特定状态，先用 :meth:`is_auto_supply_enabled` 检查。
        """
        logger.info("[UI] 出征准备 → 切换自动补给")
        self._ctrl.click(*CLICK_AUTO_SUPPLY)
