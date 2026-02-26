"""出征准备 — 修理操作。

提供快速修理槽位操作与按策略自动修理。
"""

from __future__ import annotations

import time

from autowsgr.infra.logger import get_logger
from autowsgr.types import ShipDamageState
from autowsgr.ui.battle.base import BaseBattlePreparation, RepairStrategy
from autowsgr.ui.battle.constants import BLOOD_BAR_PROBE


_log = get_logger('ui.preparation')


class RepairMixin(BaseBattlePreparation):
    """修理操作 Mixin。

    依赖 :class:`~autowsgr.ui.battle.base.BaseBattlePreparation` 提供的
    ``_ctrl``, ``select_panel``，以及
    :class:`~autowsgr.ui.battle.detection.DetectionMixin` 提供的
    ``detect_ship_damage``。
    """

    def repair_slots(self, positions: list[int]) -> None:
        """切换到快速修理面板并修理指定位置的舰船。"""
        from autowsgr.ui.battle.base import Panel

        if not positions:
            return
        self.select_panel(Panel.QUICK_REPAIR)
        time.sleep(0.8)
        for pos in positions:
            if pos not in BLOOD_BAR_PROBE:
                _log.warning('[UI] 无效修理位置: {}', pos)
                continue
            self._ctrl.click(*BLOOD_BAR_PROBE[pos])
            time.sleep(1.5)
            _log.info('[UI] 出征准备 → 修理位置 {}', pos)

    def apply_repair(
        self,
        strategy: RepairStrategy | None = None,
    ) -> list[int]:
        """根据策略执行快速修理。

        Parameters
        ----------
        strategy:
            修理策略，默认 ``RepairStrategy.SEVERE``。

        Returns
        -------
        list[int]
            实际修理的槽位列表。
        """
        from autowsgr.ui.battle.base import RepairStrategy as RS

        if strategy is None:
            strategy = RS.SEVERE

        if strategy is RS.NEVER:
            return []

        screen = self._ctrl.screenshot()
        damage = self.detect_ship_damage(screen)

        positions: list[int] = []
        for slot, dmg in damage.items():
            if dmg == ShipDamageState.NO_SHIP or dmg == ShipDamageState.NORMAL:
                continue
            if (
                (strategy is RS.ALWAYS and dmg >= ShipDamageState.MODERATE)
                or (strategy is RS.MODERATE and dmg >= ShipDamageState.MODERATE)
                or (strategy is RS.SEVERE and dmg >= ShipDamageState.SEVERE)
            ):
                positions.append(slot)

        if positions:
            self.repair_slots(positions)
            _log.info('[UI] 修理位置: {} (策略: {})', positions, strategy.value)
        return positions
