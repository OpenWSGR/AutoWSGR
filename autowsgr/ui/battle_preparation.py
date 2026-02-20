"""出征准备页面 UI 控制器。

覆盖 **出征准备** 页面的全部界面交互。
坐标与颜色常量见 :mod:`autowsgr.ui.battle_constants`。
"""

from __future__ import annotations

import enum
import time

import numpy as np
from loguru import logger

from autowsgr.emulator.controller import AndroidController
from autowsgr.ui.battle_constants import (
    AUTO_SUPPLY_ON,
    AUTO_SUPPLY_PROBE,
    BLOOD_BAR_PROBE,
    BLOOD_BLACK,
    BLOOD_EMPTY,
    BLOOD_GREEN,
    BLOOD_RED,
    BLOOD_TOLERANCE,
    BLOOD_YELLOW,
    CLICK_AUTO_SUPPLY,
    CLICK_BACK,
    CLICK_FLEET,
    CLICK_SHIP_SLOT,
    CLICK_START_BATTLE,
    CLICK_SUPPORT,
    FLEET_ACTIVE,
    FLEET_PROBE,
    PANEL_ACTIVE,
    STATE_TOLERANCE,
    SUPPORT_DISABLE,
    SUPPORT_ENABLE,
    SUPPORT_EXHAUSTED,
    SUPPORT_PROBE,
)
from autowsgr.ui.page import click_and_wait_for_page
from autowsgr.vision.matcher import PixelChecker


# ═══════════════════════════════════════════════════════════════════════════════
# 枚举
# ═══════════════════════════════════════════════════════════════════════════════


class Panel(enum.Enum):
    """出征准备底部面板标签。"""

    STATS = "综合战力"
    QUICK_SUPPLY = "快速补给"
    QUICK_REPAIR = "快速修理"
    EQUIPMENT = "装备预览"


PANEL_PROBE: dict[Panel, tuple[float, float]] = {
    Panel.STATS:        (0.1214, 0.7907),
    Panel.QUICK_SUPPLY: (0.2625, 0.7944),
    Panel.QUICK_REPAIR: (0.3932, 0.7926),
    Panel.EQUIPMENT:    (0.5250, 0.7926),
}
"""面板标签探测点。选中项探测颜色 ≈ (30, 139, 240)。"""

CLICK_PANEL: dict[Panel, tuple[float, float]] = {
    Panel.STATS:        (0.155, 0.793),
    Panel.QUICK_SUPPLY: (0.286, 0.793),
    Panel.QUICK_REPAIR: (0.417, 0.793),
    Panel.EQUIPMENT:    (0.548, 0.793),
}
"""面板标签点击位置。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 页面控制器
# ═══════════════════════════════════════════════════════════════════════════════


class BattlePreparationPage:
    """出征准备页面控制器。

    **状态查询** 为 ``staticmethod``，只需截图即可调用。
    **操作动作** 为实例方法，通过注入的控制器执行。
    """

    def __init__(self, ctrl: AndroidController) -> None:
        self._ctrl = ctrl

    # ── 页面识别 ──

    @staticmethod
    def is_current_page(screen: np.ndarray) -> bool:
        """判断截图是否为出征准备页面。"""
        fleet_active = sum(
            1
            for (x, y) in FLEET_PROBE.values()
            if PixelChecker.get_pixel(screen, x, y).near(
                FLEET_ACTIVE, STATE_TOLERANCE
            )
        )
        if fleet_active != 1:
            return False

        panel_active = sum(
            1
            for (x, y) in PANEL_PROBE.values()
            if PixelChecker.get_pixel(screen, x, y).near(
                PANEL_ACTIVE, STATE_TOLERANCE
            )
        )
        return panel_active == 1

    # ── 状态查询 ──

    @staticmethod
    def get_selected_fleet(screen: np.ndarray) -> int | None:
        """获取当前选中的舰队编号 (1–4)。"""
        for fleet_id, (x, y) in FLEET_PROBE.items():
            pixel = PixelChecker.get_pixel(screen, x, y)
            if pixel.near(FLEET_ACTIVE, STATE_TOLERANCE):
                return fleet_id
        return None

    @staticmethod
    def get_active_panel(screen: np.ndarray) -> Panel | None:
        """获取当前激活的底部面板。"""
        for panel, (x, y) in PANEL_PROBE.items():
            pixel = PixelChecker.get_pixel(screen, x, y)
            if pixel.near(PANEL_ACTIVE, STATE_TOLERANCE):
                return panel
        return None

    @staticmethod
    def is_auto_supply_enabled(screen: np.ndarray) -> bool:
        """检测自动补给是否启用。"""
        x, y = AUTO_SUPPLY_PROBE
        return PixelChecker.get_pixel(screen, x, y).near(
            AUTO_SUPPLY_ON, STATE_TOLERANCE
        )

    # ── 动作 — 回退 / 出征 ──

    def go_back(self) -> None:
        """点击回退按钮 (◁)，返回地图页面。"""
        from autowsgr.ui.map_page import MapPage

        logger.info("[UI] 出征准备 → 回退")
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_BACK,
            checker=MapPage.is_current_page,
            source="出征准备",
            target="地图页面",
        )

    def start_battle(self) -> None:
        """点击「开始出征」按钮。"""
        logger.info("[UI] 出征准备 → 开始出征")
        self._ctrl.click(*CLICK_START_BATTLE)

    # ── 动作 — 舰队/面板选择 ──

    def select_fleet(self, fleet: int) -> None:
        """选择舰队 (1–4)。"""
        if fleet not in CLICK_FLEET:
            raise ValueError(f"舰队编号必须为 1–4，收到: {fleet}")
        logger.info("[UI] 出征准备 → 选择 {}队", fleet)
        self._ctrl.click(*CLICK_FLEET[fleet])

    def select_panel(self, panel: Panel) -> None:
        """切换底部面板标签。"""
        logger.info("[UI] 出征准备 → {}", panel.value)
        self._ctrl.click(*CLICK_PANEL[panel])

    def quick_supply(self) -> None:
        """点击「快速补给」标签。"""
        self.select_panel(Panel.QUICK_SUPPLY)

    def quick_repair(self) -> None:
        """点击「快速修理」标签。"""
        self.select_panel(Panel.QUICK_REPAIR)

    # ── 动作 — 开关 ──

    def toggle_battle_support(self) -> None:
        """切换战役支援开关。"""
        logger.info("[UI] 出征准备 → 切换战役支援")
        self._ctrl.click(*CLICK_SUPPORT)

    def toggle_auto_supply(self) -> None:
        """切换自动补给开关。"""
        logger.info("[UI] 出征准备 → 切换自动补给")
        self._ctrl.click(*CLICK_AUTO_SUPPLY)

    # ── 状态查询 — 舰船血量 ──

    @staticmethod
    def detect_ship_damage(screen: np.ndarray) -> dict[int, int]:
        """检测 6 个舰船槽位的血量状态。

        Returns
        -------
        dict[int, int]
            槽位号 (1–6) → 血量状态:
            ``0``: 绿血, ``1``: 黄血, ``2``: 红血, ``3``: 维修中, ``-1``: 无舰船
        """
        result: dict[int, int] = {}
        for slot, (x, y) in BLOOD_BAR_PROBE.items():
            pixel = PixelChecker.get_pixel(screen, x, y)
            if pixel.near(BLOOD_EMPTY, BLOOD_TOLERANCE):
                result[slot] = -1
            elif pixel.near(BLOOD_GREEN, BLOOD_TOLERANCE):
                result[slot] = 0
            elif pixel.near(BLOOD_YELLOW, BLOOD_TOLERANCE):
                result[slot] = 1
            elif pixel.near(BLOOD_RED, BLOOD_TOLERANCE):
                result[slot] = 2
            elif pixel.near(BLOOD_BLACK, BLOOD_TOLERANCE):
                result[slot] = 3
            else:
                logger.debug("[UI] 舰船 {} 血量颜色未匹配: {}", slot, pixel)
                result[slot] = 0
        return result

    # ── 状态查询 — 战役支援 ──

    @staticmethod
    def is_support_enabled(screen: np.ndarray) -> bool:
        """检测战役支援是否启用。灰色 (次数用尽) 也视为已启用。"""
        x, y = SUPPORT_PROBE
        pixel = PixelChecker.get_pixel(screen, x, y)
        d_enable = pixel.distance(SUPPORT_ENABLE)
        d_disable = pixel.distance(SUPPORT_DISABLE)
        d_exhausted = pixel.distance(SUPPORT_EXHAUSTED)
        if d_enable > d_exhausted and d_disable > d_exhausted:
            return True
        return d_enable < d_disable

    # ── 动作 — 补给/修理 ──

    def supply(self, ship_ids: list[int] | None = None) -> None:
        """切换到补给面板并补给指定舰船。"""
        if ship_ids is None:
            ship_ids = [1, 2, 3, 4, 5, 6]
        self.select_panel(Panel.QUICK_SUPPLY)
        time.sleep(0.5)
        for sid in ship_ids:
            if sid not in CLICK_SHIP_SLOT:
                logger.warning("[UI] 无效槽位: {}", sid)
                continue
            self._ctrl.click(*CLICK_SHIP_SLOT[sid])
            time.sleep(0.3)
        logger.info("[UI] 出征准备 → 补给 {}", ship_ids)

    def repair_slots(self, positions: list[int]) -> None:
        """切换到快速修理面板并修理指定位置的舰船。"""
        if not positions:
            return
        self.select_panel(Panel.QUICK_REPAIR)
        time.sleep(0.8)
        for pos in positions:
            if pos not in BLOOD_BAR_PROBE:
                logger.warning("[UI] 无效修理位置: {}", pos)
                continue
            self._ctrl.click(*BLOOD_BAR_PROBE[pos])
            time.sleep(1.5)
            logger.info("[UI] 出征准备 → 修理位置 {}", pos)

    def click_ship_slot(self, slot: int) -> None:
        """点击指定舰船槽位 (1–6)。"""
        if slot not in CLICK_SHIP_SLOT:
            raise ValueError(f"舰船槽位必须为 1–6，收到: {slot}")
        logger.info("[UI] 出征准备 → 点击舰船位 {}", slot)
        self._ctrl.click(*CLICK_SHIP_SLOT[slot])
