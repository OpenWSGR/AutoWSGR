"""出征面板 Mixin — 章节选择与进入出征准备。"""

from __future__ import annotations

import time

from loguru import logger

from autowsgr.ui.map.base import BaseMapPage
from autowsgr.ui.map.data import (
    CHAPTER_MAP_COUNTS,
    CLICK_ENTER_SORTIE,
    CLICK_MAP_NEXT,
    CLICK_MAP_PREV,
    MapPanel,
)
from autowsgr.ui.page import click_and_wait_for_page, wait_for_page
from autowsgr.types import PageName


class SortiePanelMixin(BaseMapPage):
    """Mixin: 出征面板操作 — 选择章节 / 地图节点 / 进入出征准备。"""

    def enter_sortie(self, chapter: int | str, map_num: int | str) -> None:
        """进入出征: 选择指定章节和地图节点，直接到达出征准备页面。

        Parameters
        ----------
        chapter:
            目标章节编号 (1–9) 或事件地图标识字符串。
        map_num:
            目标地图节点编号 (1–6) 或事件地图标识字符串。

        Raises
        ------
        ValueError
            章节或地图编号无效 (仅数字模式)。
        NavigationError
            导航超时。
        """
        from autowsgr.ui.battle.preparation import BattlePreparationPage

        logger.info("[UI] 地图页面 → 进入出征 {}-{}", chapter, map_num)

        # 1. 确保在出征面板
        self.ensure_panel(MapPanel.SORTIE)
        time.sleep(0.5)

        # 2. 导航到指定章节
        if isinstance(chapter, int):
            max_maps = CHAPTER_MAP_COUNTS.get(chapter, 0)
            if max_maps == 0:
                raise ValueError(f"章节 {chapter} 不在已知地图数据中")
            if isinstance(map_num, int) and not 1 <= map_num <= max_maps:
                raise ValueError(
                    f"章节 {chapter} 的地图编号必须为 1–{max_maps}，收到: {map_num}"
                )
            result = self.navigate_to_chapter(chapter)
            if result is None:
                from autowsgr.ui.page import NavigationError

                raise NavigationError(f"无法导航到第 {chapter} 章")

        # 3. 切换到指定地图节点
        if isinstance(map_num, int) and self._ocr is not None:
            screen = self._ctrl.screenshot()
            info = self.recognize_map(screen, self._ocr)
            if info is not None:
                current_map = info.map_num
                if current_map != map_num:
                    delta = map_num - current_map
                    if delta > 0:
                        for _ in range(delta):
                            self._ctrl.click(*CLICK_MAP_NEXT)
                            time.sleep(0.3)
                    else:
                        for _ in range(-delta):
                            self._ctrl.click(*CLICK_MAP_PREV)
                            time.sleep(0.3)
                    time.sleep(0.5)

        # 4. 点击进入出征准备
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_ENTER_SORTIE,
            checker=BattlePreparationPage.is_current_page,
            source=f"地图-出征 {chapter}-{map_num}",
            target=PageName.BATTLE_PREP,
        )
