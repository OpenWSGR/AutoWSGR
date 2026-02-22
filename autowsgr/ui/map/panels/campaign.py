"""战役面板 Mixin — 难度选择与进入战役出征准备。"""

from __future__ import annotations

import time

from loguru import logger

from autowsgr.ui.map.base import BaseMapPage
from autowsgr.ui.map.data import (
    CAMPAIGN_POSITIONS,
    CLICK_DIFFICULTY,
    DIFFICULTY_EASY_COLOR,
    DIFFICULTY_HARD_COLOR,
    MapPanel,
)
from autowsgr.ui.page import wait_for_page
from autowsgr.types import PageName
from autowsgr.vision import PixelChecker


class CampaignPanelMixin(BaseMapPage):
    """Mixin: 战役面板操作 — 难度识别 / 切换 / 进入战役。"""

    # ── 查询 ─────────────────────────────────────────────────────────────

    def recognize_difficulty(self) -> str | None:
        """通过检测难度按钮颜色识别当前难度。

        切换图标为蓝色时，说明可以切换为 easy，当前为 hard；反之亦然。

        Returns
        -------
        str | None
            ``"easy"`` / ``"hard"``，识别失败返回 ``None``。

        Raises
        ------
        RuntimeError
            超过重试次数仍无法识别。
        """
        retry = 0
        while retry < 10:
            screen = self._ctrl.screenshot()
            px = PixelChecker.get_pixel(screen, *CLICK_DIFFICULTY)
            if px.near(DIFFICULTY_EASY_COLOR, tolerance=50):
                return "hard"
            elif px.near(DIFFICULTY_HARD_COLOR, tolerance=50):
                return "easy"
            time.sleep(0.25)
            retry += 1

        logger.warning("[UI] 无法识别难度: 检测点颜色不匹配简单或困难")
        raise RuntimeError("无法识别战役难度")

    # ── 操作 ─────────────────────────────────────────────────────────────

    def enter_campaign(
        self,
        map_index: int = 2,
        difficulty: str = "hard",
        campaign_name: str = "未知",
    ) -> None:
        """进入战役: 选择难度和战役类型，直接到达出征准备页面。

        Parameters
        ----------
        map_index:
            战役编号 (1–5: 航母/潜艇/驱逐/巡洋/战列)。
        difficulty:
            难度 ``"easy"`` 或 ``"hard"``。
        campaign_name:
            战役名称 (仅用于日志)。

        Raises
        ------
        ValueError
            战役编号或难度无效。
        NavigationError
            导航超时。
        """
        from autowsgr.ui.battle.preparation import BattlePreparationPage

        if map_index not in CAMPAIGN_POSITIONS:
            raise ValueError(f"战役编号必须为 1–5，收到: {map_index}")
        if difficulty not in ("easy", "hard"):
            raise ValueError(f"难度必须为 easy 或 hard，收到: {difficulty}")

        logger.info(
            "[UI] 地图页面 → 进入战役 {} ({})",
            campaign_name,
            difficulty,
        )

        # 1. 切换到战役面板
        self.ensure_panel(MapPanel.BATTLE)

        # 2. 选择难度
        if self.recognize_difficulty() != difficulty:
            self._ctrl.click(*CLICK_DIFFICULTY)
        while self.recognize_difficulty() != difficulty:
            logger.debug("[UI] 等待难度切换到 {}…", difficulty)
            time.sleep(0.25)
        time.sleep(0.75)

        # 3. 选择战役
        self._ctrl.click(*CAMPAIGN_POSITIONS[map_index])
        time.sleep(0.5)

        # 等待到达出征准备
        wait_for_page(
            self._ctrl,
            checker=BattlePreparationPage.is_current_page,
            source=f"地图-战役 {campaign_name}",
            target=PageName.BATTLE_PREP,
        )
