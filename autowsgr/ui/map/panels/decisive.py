"""决战面板 Mixin — 进入决战总览页。"""

from __future__ import annotations

import time

from loguru import logger

from autowsgr.ui.map.base import BaseMapPage
from autowsgr.ui.map.data import CLICK_ENTER_DECISIVE, MapPanel
from autowsgr.ui.page import click_and_wait_for_page
from autowsgr.types import PageName


class DecisivePanelMixin(BaseMapPage):
    """Mixin: 决战面板操作 — 进入决战。"""

    def enter_decisive(self) -> None:
        """从地图页进入决战总览页。

        Raises
        ------
        NavigationError
            超时未到达决战页面。
        """
        from autowsgr.ui.decisive.battle_page import DecisiveBattlePage

        logger.info("[UI] 地图页面 → 决战页面")

        # 1. 确保在决战面板
        self.ensure_panel(MapPanel.DECISIVE)
        time.sleep(0.5)

        # 2. 点击进入
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_ENTER_DECISIVE,
            checker=DecisiveBattlePage.is_current_page,
            source="地图-决战面板",
            target=PageName.DECISIVE_BATTLE,
        )
