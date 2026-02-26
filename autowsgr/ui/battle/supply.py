"""出征准备 — 补给与战役支援。

提供补给 / 支援状态查询与切换操作。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from autowsgr.infra.logger import get_logger
from autowsgr.ui.battle.base import BaseBattlePreparation
from autowsgr.ui.battle.constants import (
    CLICK_SHIP_SLOT,
    CLICK_SUPPORT,
    SUPPORT_DISABLE,
    SUPPORT_ENABLE,
    SUPPORT_EXHAUSTED,
    SUPPORT_PROBE,
)
from autowsgr.vision import PixelChecker


if TYPE_CHECKING:
    import numpy as np


_log = get_logger('ui.preparation')


class SupplyMixin(BaseBattlePreparation):
    """补给与战役支援 Mixin。

    依赖 :class:`~autowsgr.ui.battle.base.BaseBattlePreparation` 提供的
    ``_ctrl``, ``select_panel``, ``is_auto_supply_enabled``。
    """

    # ── 状态查询 — 战役支援 ──────────────────────────────────────────────

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

    # ── 动作 — 开关 ──────────────────────────────────────────────────────

    def toggle_battle_support(self) -> None:
        """切换战役支援开关。"""
        _log.debug('[UI] 出征准备 → 切换战役支援')
        self._ctrl.click(*CLICK_SUPPORT)

    # ── 动作 — 补给 ──────────────────────────────────────────────────────

    def supply(self, ship_ids: list[int] | None = None) -> None:
        """切换到补给面板并补给指定舰船。"""
        from autowsgr.ui.battle.base import Panel

        if ship_ids is None:
            ship_ids = [0, 1, 2, 3, 4, 5]
        self.select_panel(Panel.QUICK_SUPPLY)
        time.sleep(0.5)
        for sid in ship_ids:
            if sid not in CLICK_SHIP_SLOT:
                _log.warning('[UI] 无效槽位: {}', sid)
                continue
            self._ctrl.click(*CLICK_SHIP_SLOT[sid])
            time.sleep(0.3)
        _log.debug('[UI] 出征准备 → 补给 {}', ship_ids)

    def apply_supply(self) -> None:
        """确保舰队已补给 (自动补给未开启则手动补给)。"""
        screen = self._ctrl.screenshot()
        if self.is_auto_supply_enabled(screen):
            return
        self.supply()
