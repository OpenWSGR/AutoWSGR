"""地图页面高级操作 — 战役、决战、演习、远征。

从 ``map_page.py`` 中分离的 :class:`MapPage` 扩展方法，
以 Mixin 形式提供，保持主文件精简。
"""

from __future__ import annotations

import time

from loguru import logger

from autowsgr.ops.image_resources import Templates
from autowsgr.ui.map.data import (
    CAMPAIGN_POSITIONS,
    CLICK_CHALLENGE,
    CLICK_DIFFICULTY,
    DIFFICULTY_EASY_COLOR,
    DIFFICULTY_HARD_COLOR,
    CLICK_ENTER_DECISIVE,
    CLICK_REFRESH_RIVALS,
    CLICK_SCREEN_CENTER,
    EXPEDITION_READY_COLOR,
    EXPEDITION_SLOT_PROBES,
    EXPEDITION_SLOT_TOLERANCE,
    MapPanel,
    RIVAL_POSITIONS,
)
from autowsgr.ui.page import (
    click_and_wait_for_page,
    confirm_operation,
    wait_for_page,
)
from autowsgr.types import PageName
from autowsgr.vision import ImageChecker, PixelChecker
from autowsgr.emulator import AndroidController


class _MapPageOpsMixin:
    """Mixin: 地图页面的战役 / 决战 / 演习 / 远征操作。

    由 :class:`~autowsgr.ui.map.page.MapPage` 继承。
    """

    _ctrl: AndroidController

    # ── 动作 — 进入战役 (地图 → 出征准备) ───────────────────────────────
    def recognize_difficulty(self) -> str | None:
        """通过检测难度按钮颜色识别当前难度。
        切换图标为蓝色时，说明可以切换为 easy，当前为 hard；反之亦然。
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

        logger.warning(
            "[UI] 无法识别难度: 检测点颜色 {} 不匹配简单或困难",
        )
        raise
    
    def enter_campaign(
        self,
        map_index: int = 2,
        difficulty: str = "hard",
        campaign_name: str = "未知"
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

        logger.info(
            "[UI] 地图页面 → 进入战役 {} ({})",
            campaign_name,
            difficulty,
        )

        # 1. 切换到战役面板
        screen = self._ctrl.screenshot()
        if self.get_active_panel(screen) != MapPanel.BATTLE:  # type: ignore[attr-defined]
            self.switch_panel(MapPanel.BATTLE)  # type: ignore[attr-defined]

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
            target=PageName.DECISIVE_BATTLE,
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

    def click_screen_center(self) -> None:
        """点击屏幕中央 — 用于跳过动画/确认弹窗。"""
        self._ctrl.click(*CLICK_SCREEN_CENTER)

    # ── 动作 — 远征收取 ──

    def _find_ready_expedition_slot(self, screen) -> int | None:
        """检测 4 个远征槽位，返回第一个已完成 (黄色) 的槽位索引。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。

        Returns
        -------
        int | None
            就绪槽位索引 (0–3)，无就绪则返回 ``None``。
        """
        for i, (px, py) in enumerate(EXPEDITION_SLOT_PROBES):
            actual = PixelChecker.get_pixel(screen, px, py)
            if actual.near(EXPEDITION_READY_COLOR, EXPEDITION_SLOT_TOLERANCE):
                logger.debug(
                    "[UI] 远征槽位 {} 就绪: 实际颜色 {} ≈ 黄色",
                    i + 1,
                    actual.as_rgb_tuple(),
                )
                return i
        return None

    def collect_expedition(self) -> int:
        """在远征面板收取已完成的远征。

        Returns
        -------
        int
            收取的远征数量。

        Raises
        ------
        NavigationError
            远征通知仍在但 10s 内无法检测到就绪槽位。
        """
        from autowsgr.ui.map.page import MapPage

        collected = 0
        for _ in range(8):
            # ── 检测就绪槽位 (含等待逻辑) ──
            screen = self._ctrl.screenshot()
            slot_idx = self._find_ready_expedition_slot(
                screen
            )
            if slot_idx is None:
                # 无黄色槽位 — 检查上方探测点是否仍报告有远征
                if not MapPage.has_expedition_notification(
                    screen
                ):
                    logger.debug("[UI] 远征收取: 无就绪槽位且无通知，结束")
                    break

                # 上方探测点仍亮 — 等待槽位刷新 (最多 10s)
                logger.debug("[UI] 远征收取: 通知仍在，等待槽位刷新…")
                deadline = time.monotonic() + 10.0
                while time.monotonic() < deadline:
                    time.sleep(0.1)
                    screen = self._ctrl.screenshot()
                    slot_idx = self._find_ready_expedition_slot(screen)
                    if slot_idx is not None:
                        break
                    if not MapPage.has_expedition_notification(screen):
                        logger.debug(
                            "[UI] 远征收取: 通知消失，结束",
                        )
                        break
                else:
                    from autowsgr.ui.page import NavigationError
                    raise NavigationError(
                        "远征收取超时: 通知仍在但 10s 内未检测到就绪槽位"
                    )

                if slot_idx is None:
                    break

            slot_pos = EXPEDITION_SLOT_PROBES[slot_idx]
            logger.info("[UI] 远征收取: 点击槽位 {} ({:.4f}, {:.4f})",
                        slot_idx + 1, *slot_pos)

            # 1. 点击就绪槽位 (Legacy: timer.click(pos, delay=1))
            self._ctrl.click(*slot_pos)
            time.sleep(1.0)

            # 2. 等待远征结果画面 (Legacy: wait_image(fight_image[3]))
            _result_templates = [
                Templates.Symbol.CLICK_TO_CONTINUE,
            ]
            _wait_deadline = time.monotonic() + 5.0
            while time.monotonic() < _wait_deadline:
                screen = self._ctrl.screenshot()
                if ImageChecker.template_exists(screen, _result_templates):
                    break
            time.sleep(0.25)

            # 3. 点击屏幕中央跳过动画 (Legacy: timer.click(900, 500, delay=1))
            self.click_screen_center()
            time.sleep(1.0)

            # 4. 确认弹窗 (Legacy: confirm_operation(must_confirm=True))
            confirm_operation(
                self._ctrl,
                must_confirm=True,
                delay=0.5,
                confidence=0.9,
                timeout=5.0,
            )

            # 5. 等待回到地图页面
            wait_for_page(
                self._ctrl,
                checker=MapPage.is_current_page,
                source=f"远征收取",
                target=PageName.MAP,
            )

            collected += 1

        logger.info("[UI] 远征收取: {} 支", collected)
        return collected
