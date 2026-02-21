"""出征准备页面 UI 控制器。

覆盖 **出征准备** 页面的全部界面交互。
坐标与颜色常量见 :mod:`autowsgr.ui.battle.constants`。
"""

from __future__ import annotations

import enum
import time
from collections.abc import Sequence

import numpy as np
from loguru import logger

from autowsgr.emulator import AndroidController
from autowsgr.ui.battle.blood import classify_blood
from autowsgr.ui.battle.constants import (
    AUTO_SUPPLY_ON,
    AUTO_SUPPLY_PROBE,
    BLOOD_BAR_PROBE,
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
from autowsgr.types import PageName, ShipDamageState
from autowsgr.vision import PixelChecker, PixelSignature, PixelRule, MatchStrategy, OCREngine


# ═══════════════════════════════════════════════════════════════════════════════
# 枚举
# ═══════════════════════════════════════════════════════════════════════════════


class RepairStrategy(enum.Enum):
    """修理策略。"""

    MODERATE = "moderate"
    """修中破及以上 (damage >= 1)。"""

    SEVERE = "severe"
    """仅修大破 (damage >= 2)。"""

    ALWAYS = "always"
    """有损伤即修 (damage >= 1, 含黄血)。"""

    NEVER = "never"
    """不修理。"""


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

PAGE_SIGNATURE = PixelSignature(
    name=PageName.BATTLE_PREP,
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.0758, 0.7806, (46, 61, 80), tolerance=30.0),
        PixelRule.of(0.8758, 0.0500, (216, 223, 229), tolerance=30.0),
        PixelRule.of(0.9422, 0.9389, (255, 219, 47), tolerance=30.0),
        PixelRule.of(0.8070, 0.9417, (255, 219, 47), tolerance=30.0),
    ],
)
"""面板标签点击位置。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 页面控制器
# ═══════════════════════════════════════════════════════════════════════════════


class BattlePreparationPage:
    """出征准备页面控制器。

    **状态查询** 为 ``staticmethod``，只需截图即可调用。
    **操作动作** 为实例方法，通过注入的控制器执行。
    """

    def __init__(self, ctrl: AndroidController, ocr: OCREngine | None = None) -> None:
        self._ctrl = ctrl
        self._ocr = ocr

    # ── 页面识别 ──

    @staticmethod
    def is_current_page(screen: np.ndarray) -> bool:
        """判断截图是否为出征准备页面。"""
        result = PixelChecker.check_signature(screen, PAGE_SIGNATURE)
        return result.matched

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
        from autowsgr.ui.map.page import MapPage

        logger.info("[UI] 出征准备 → 回退")
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_BACK,
            checker=MapPage.is_current_page,
            source=PageName.BATTLE_PREP,
            target=PageName.MAP,
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
    def detect_ship_damage(screen: np.ndarray) -> dict[int, ShipDamageState]:
        """检测 6 个舰船槽位的血量状态。

        Returns
        -------
        dict[int, ShipDamageState]
            槽位号 (0–5) → 血量状态。
        """
        result: dict[int, ShipDamageState] = {}
        for slot, (x, y) in BLOOD_BAR_PROBE.items():
            pixel = PixelChecker.get_pixel(screen, x, y)
            result[slot] = classify_blood(pixel)
        logger.debug(
            "[准备页] 血量检测: {}",
            " | ".join(f"槽{i}={result[i].name}" for i in range(len(result))),
        )
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
            ship_ids = [0, 1, 2, 3, 4, 5]
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
        """点击指定舰船槽位 (0–5)。"""
        if slot not in CLICK_SHIP_SLOT:
            raise ValueError(f"舰船槽位必须为 0–5，收到: {slot}")
        logger.info("[UI] 出征准备 → 点击舰船位 {}", slot)
        self._ctrl.click(*CLICK_SHIP_SLOT[slot])

    # ── 组合动作 — 修理 / 补给 / 换船 ──

    def apply_repair(
        self,
        strategy: RepairStrategy = RepairStrategy.SEVERE,
    ) -> list[int]:
        """根据策略执行快速修理。

        Returns
        -------
        list[int]
            实际修理的槽位列表。
        """
        if strategy is RepairStrategy.NEVER:
            return []

        screen = self._ctrl.screenshot()
        damage = self.detect_ship_damage(screen)

        positions: list[int] = []
        for slot, dmg in damage.items():
            if dmg == ShipDamageState.NO_SHIP or dmg == ShipDamageState.NORMAL:
                continue
            if strategy is RepairStrategy.ALWAYS and dmg >= ShipDamageState.MODERATE:
                positions.append(slot)
            elif strategy is RepairStrategy.MODERATE and dmg >= ShipDamageState.MODERATE:
                positions.append(slot)
            elif strategy is RepairStrategy.SEVERE and dmg >= ShipDamageState.SEVERE:
                positions.append(slot)

        if positions:
            self.repair_slots(positions)
            logger.info("[UI] 修理位置: {} (策略: {})", positions, strategy.value)
        return positions

    def apply_supply(self) -> None:
        """确保舰队已补给 (自动补给未开启则手动补给)。"""
        screen = self._ctrl.screenshot()
        if self.is_auto_supply_enabled(screen):
            return
        self.supply()

    def change_fleet(
        self,
        fleet_id: int,
        ship_names: Sequence[str | None],
    ) -> None:
        """更换编队全部舰船。
        TODO: 需测试
        Parameters
        ----------
        fleet_id:
            舰队编号 (2–4)。1 队不支持更换。
        ship_names:
            舰船名列表 (按槽位 0–5)。``None`` 或 ``""`` 表示该位留空。
        """

        if fleet_id == 1:
            raise ValueError("不支持更换 1 队舰船编成")

        logger.info("[UI] 更换 {} 队编成: {}", fleet_id, ship_names)

        names = list(ship_names) + [None] * 6
        names = [n if n else None for n in names[:6]]

        # 检测当前各槽位状态
        screen = self._ctrl.screenshot()
        damage = self.detect_ship_damage(screen)

        # 先移除所有已有舰船
        for slot in range(6):
            if damage.get(slot, ShipDamageState.NO_SHIP) != ShipDamageState.NO_SHIP:
                self._change_single_ship(0, None, slot_occupied=True)
                time.sleep(0.3)

        # 检测移除后状态
        screen = self._ctrl.screenshot()
        damage = self.detect_ship_damage(screen)

        # 逐个放入目标舰船
        for slot in range(6):
            name = names[slot]
            occupied = damage.get(slot, ShipDamageState.NO_SHIP) != ShipDamageState.NO_SHIP
            self._change_single_ship(slot, name, slot_occupied=occupied)
            time.sleep(0.3)

        logger.info("[UI] {} 队编成更换完成", fleet_id)

    def _change_single_ship(
        self,
        slot: int,
        name: str | None,
        *,
        slot_occupied: bool = True,
    ) -> None:
        """更换/移除指定位置的单艘舰船。"""
        from autowsgr.ui.choose_ship_page import ChooseShipPage

        if name is None and not slot_occupied:
            return

        self.click_ship_slot(slot)
        time.sleep(1.0)

        choose_page = ChooseShipPage(self._ctrl)

        if name is None:
            choose_page.click_remove()
            time.sleep(0.8)
            return

        choose_page.click_search_box()
        time.sleep(0.5)
        choose_page.input_ship_name(name)
        time.sleep(0.3)
        choose_page.dismiss_keyboard()
        time.sleep(0.8)

        screen = self._ctrl.screenshot()
        if self._ocr is None:
            logger.warning("[UI] 未提供 OCR 引擎，无法验证舰船名称")
        else:
            ship_name = self._ocr.recognize_ship_name(screen, [name])
            if ship_name != name:
                logger.warning("[UI] 未精确匹配 '{}', OCR 识别: '{}'", name, ship_name)

        choose_page.click_first_result()
        time.sleep(1.0)
