"""出征准备 — 修理操作。

提供快速修理槽位操作与按策略自动修理。
"""

from __future__ import annotations

import time

from autowsgr.infra import ActionFailedError
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

    def check_repair(
        self,
        strategy: RepairStrategy,
    ) -> list[int]:
        """根据策略执行快速修理检查（不实际修理）。

        Parameters
        ----------
        strategy:
            修理策略，默认 ``RepairStrategy.SEVERE``。

        Returns
        -------
        list[int]
            实际修理的槽位列表。
        """
        from autowsgr.ui.battle.base import RepairStrategy

        screen = self._ctrl.screenshot()
        damage = self.detect_ship_damage(screen)

        positions: list[int] = []
        for slot, dmg in damage.items():
            if dmg == ShipDamageState.NO_SHIP or dmg == ShipDamageState.NORMAL:
                continue
            if (
                (strategy is RepairStrategy.ALWAYS and dmg >= ShipDamageState.MODERATE)
                or (strategy is RepairStrategy.MODERATE and dmg >= ShipDamageState.MODERATE)
                or (strategy is RepairStrategy.SEVERE and dmg >= ShipDamageState.SEVERE)
            ):
                positions.append(slot)
        return positions

    def apply_repair(
        self,
        strategy: RepairStrategy | None = None,
        *,
        repair_manually: bool = False,
        retry_count: int = 3,
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
        if strategy is None:
            strategy = RepairStrategy.SEVERE

        if strategy is RepairStrategy.NEVER:
            return []

        repair_pos = []
        positions = self.check_repair(strategy)
        for i in range(retry_count):
            # 没有需要修理的舰船，直接返回
            if not positions:
                return []
            # 需要手动修理，退出程序
            if self._ctx.config.repair_manually or repair_manually:
                raise ActionFailedError('需要进行手动修理')
            self.repair_slots(positions)
            repair_pos.extend(positions)
            # 修理完成再检查一遍
            positions = self.check_repair(strategy)
            if not positions:
                _log.info('[UI] 修理位置: {} (策略: {})', repair_pos, strategy.value)
                return repair_pos
            _log.info(f'[UI] 有舰船修理失败: {positions}, 重试第 {i} 次')
        # 经过重试仍修理失败
        _log.error('[UI] 舰船修理异常(策略: {})', strategy.value)
        raise ActionFailedError('舰船修理异常')
