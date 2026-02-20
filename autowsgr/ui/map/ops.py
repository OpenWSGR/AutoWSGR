"""地图页面高级操作 — 战役、决战、演习、远征。

从 ``map_page.py`` 中分离的 :class:`MapPage` 扩展方法，
以 Mixin 形式提供，保持主文件精简。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from loguru import logger

from autowsgr.ops.image_resources import Templates
from autowsgr.ui.map.data import (
    CAMPAIGN_NAMES,
    CAMPAIGN_POSITIONS,
    CLICK_CHALLENGE,
    CLICK_DIFFICULTY_EASY,
    CLICK_DIFFICULTY_HARD,
    CLICK_ENTER_CAMPAIGN,
    CLICK_ENTER_DECISIVE,
    CLICK_REFRESH_RIVALS,
    CLICK_SCREEN_CENTER,
    MAP_NODE_POSITIONS,
    MapPanel,
    RIVAL_POSITIONS,
)
from autowsgr.ui.page import click_and_wait_for_page, wait_for_page
from autowsgr.vision.image_matcher import ImageChecker

if TYPE_CHECKING:
    from autowsgr.emulator import AndroidController


class _MapPageOpsMixin:
    """Mixin: 地图页面的战役 / 决战 / 演习 / 远征操作。

    由 :class:`~autowsgr.ui.map.page.MapPage` 继承。
    """

    _ctrl: AndroidController

    # ── 动作 — 进入战役 (地图 → 出征准备) ───────────────────────────────

    def enter_campaign(
        self,
        map_index: int = 2,
        difficulty: str = "hard",
    ) -> None:
        """进入战役: 选择难度和战役类型，直接到达出征准备页面。

        Parameters
        ----------
        map_index:
            战役编号 (1–5: 航母/潜艇/驱逐/巡洋/战列)。
        difficulty:
            难度 ``"easy"`` 或 ``"hard"``。

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

        battle_name = CAMPAIGN_NAMES.get(map_index, "未知")
        logger.info(
            "[UI] 地图页面 → 进入战役 {} ({})",
            battle_name,
            difficulty,
        )

        # 1. 切换到战役面板
        screen = self._ctrl.screenshot()
        if self.get_active_panel(screen) != MapPanel.BATTLE:  # type: ignore[attr-defined]
            self.switch_panel(MapPanel.BATTLE)  # type: ignore[attr-defined]
            time.sleep(1.0)

        # 2. 选择难度
        if difficulty == "easy":
            self._ctrl.click(*CLICK_DIFFICULTY_EASY)
        else:
            self._ctrl.click(*CLICK_DIFFICULTY_HARD)
        time.sleep(0.5)

        # 3. 选择战役
        self._ctrl.click(*CAMPAIGN_POSITIONS[map_index])
        time.sleep(0.5)

        # 4. 点击进入 (双击确保)
        self._ctrl.click(*CLICK_ENTER_CAMPAIGN)
        self._ctrl.click(*CLICK_ENTER_CAMPAIGN)
        time.sleep(1.5)

        # 等待到达出征准备
        wait_for_page(
            self._ctrl,
            checker=BattlePreparationPage.is_current_page,
            source=f"地图-战役 {battle_name}",
            target="出征准备",
        )

    # ── 动作 — 进入决战 (地图 → 决战页面) ────────────────────────────────

    def enter_decisive(self) -> None:
        """从地图页进入决战总览页。

        Raises
        ------
        NavigationError
            超时未到达决战页面。
        """
        from autowsgr.ui.decisive_battle_page import DecisiveBattlePage

        logger.info("[UI] 地图页面 → 决战页面")

        # 1. 确保在决战面板
        screen = self._ctrl.screenshot()
        if self.get_active_panel(screen) != MapPanel.DECISIVE:  # type: ignore[attr-defined]
            self.switch_panel(MapPanel.DECISIVE)  # type: ignore[attr-defined]
            time.sleep(0.5)

        # 2. 点击进入
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_ENTER_DECISIVE,
            checker=DecisiveBattlePage.is_current_page,
            source="地图-决战面板",
            target="决战页面",
        )

    # ── 动作 — 演习面板操作 ──────────────────────────────────────────────

    def click_rival(self, index: int) -> None:
        """演习面板 → 点击指定对手的挑战按钮 (1–4)。"""
        if not 1 <= index <= len(RIVAL_POSITIONS):
            raise ValueError(f"对手序号必须为 1–4，收到: {index}")
        logger.info("[UI] 地图 (演习) → 点击第 {} 个对手", index)
        self._ctrl.click(*RIVAL_POSITIONS[index - 1])

    def click_refresh_rivals(self) -> None:
        """演习面板 → 点击「刷新对手」按钮。"""
        logger.info("[UI] 地图 (演习) → 刷新对手")
        self._ctrl.click(*CLICK_REFRESH_RIVALS)

    def click_challenge(self) -> None:
        """演习面板 → 点击「挑战」确认按钮。"""
        logger.info("[UI] 地图 (演习) → 挑战")
        self._ctrl.click(*CLICK_CHALLENGE)

    # ── 动作 — 地图节点操作 ──────────────────────────────────────────────

    def click_map_node(self, node: int) -> None:
        """出征面板 → 点击指定地图节点 (1–5)。"""
        if node not in MAP_NODE_POSITIONS:
            raise ValueError(f"地图节点必须为 1–5，收到: {node}")
        logger.info("[UI] 地图 (出征) → 点击节点 {}", node)
        self._ctrl.click(*MAP_NODE_POSITIONS[node])

    def click_screen_center(self) -> None:
        """点击屏幕中央 — 用于跳过动画/确认弹窗。"""
        self._ctrl.click(*CLICK_SCREEN_CENTER)

    # ── 动作 — 远征收取 ──

    def collect_expedition(self) -> int:
        """在远征面板收取已完成的远征 (循环确认弹窗)。

        Returns
        -------
        int
            收取的远征数量。
        """
        collected = 0
        for _ in range(6):
            screen = self._ctrl.screenshot()
            has_notif = self.has_expedition_notification(screen)  # type: ignore[attr-defined]
            if not has_notif and collected > 0:
                break

            detail = ImageChecker.find_any(screen, Templates.Confirm.all())
            if detail is not None:
                self._ctrl.click(*detail.center)
                time.sleep(1.0)
                collected += 1
                continue

            if has_notif:
                self.click_screen_center()
                time.sleep(1.0)
            else:
                break

        logger.info("[UI] 远征收取: {} 支", collected)
        return collected
