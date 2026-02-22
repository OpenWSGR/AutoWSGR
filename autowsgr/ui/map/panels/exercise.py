"""演习面板 Mixin — 对手检测 / 选择 / 战斗 / 刷新 / 阵容识别。

参考 legacy ``get_exercise_stats()`` 和 ``NormalExerciseInfo._make_decision()``
重构为新架构下的独立 Mixin。

演习面板共有 **5 个对手**，屏幕一次显示 4 个:
- 上滑至顶部 (``up``): 显示对手 1–4，对手 5 需要下滑才可见。
- 下滑至底部 (``down``): 显示对手 2–5，对手 1 需要上滑才可见。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
from loguru import logger

from autowsgr.ui.map.base import BaseMapPage
from autowsgr.ui.map.data import (
    EXERCISE_ARROW_DOWN_PROBE,
    EXERCISE_ARROW_GRAY,
    EXERCISE_ARROW_TOLERANCE,
    EXERCISE_ARROW_UP_PROBE,
    EXERCISE_CHALLENGE_COLOR,
    EXERCISE_CHALLENGE_PROBES,
    EXERCISE_CHALLENGE_TOLERANCE,
    EXERCISE_CLICK_RIVAL_INFO,
    EXERCISE_CLICK_START_BATTLE,
    EXERCISE_SWIPE_DELAY,
    EXERCISE_SWIPE_TO_BOTTOM,
    EXERCISE_SWIPE_TO_TOP,
)
from autowsgr.types import PageName
from autowsgr.ui.page import click_and_wait_for_page
from autowsgr.vision import PixelChecker


# ═══════════════════════════════════════════════════════════════════════════════
# 数据结构
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class ExerciseRivalStatus:
    """五个演习对手的挑战状态。

    Attributes
    ----------
    rivals:
        长度为 5 的列表, ``True`` = 可挑战 (蓝色按钮), ``False`` = 已挑战。
        索引 0–4 对应对手 1–5。
    """

    rivals: list[bool] = field(default_factory=lambda: [False] * 5)

    @property
    def challengeable_count(self) -> int:
        """可挑战的对手数量。"""
        return sum(self.rivals)

    def first_challengeable(self) -> int | None:
        """返回第一个可挑战对手的序号 (1-based)，无则返回 ``None``。"""
        for i, ok in enumerate(self.rivals):
            if ok:
                return i + 1
        return None

    def __repr__(self) -> str:
        tags = ["✓" if ok else "✗" for ok in self.rivals]
        return f"ExerciseRivalStatus([{', '.join(tags)}])"


# ═══════════════════════════════════════════════════════════════════════════════
# Mixin
# ═══════════════════════════════════════════════════════════════════════════════


class ExercisePanelMixin(BaseMapPage):
    """Mixin: 演习面板操作 — 对手状态检测 / 选择 / 战斗入口 / 刷新 / 阵容识别。

    所有方法假设调用前已处于演习面板 (:attr:`MapPanel.EXERCISE`)。
    """

    # ═══════════════════════════════════════════════════════════════════════
    # 内部辅助 — 列表滚动
    # ═══════════════════════════════════════════════════════════════════════

    def _exercise_is_at_top(self, screen: np.ndarray) -> bool:
        """检测演习列表是否已在顶部 (上箭头变灰)。"""
        return PixelChecker.check_pixel(
            screen,
            *EXERCISE_ARROW_UP_PROBE,
            EXERCISE_ARROW_GRAY,
            EXERCISE_ARROW_TOLERANCE,
        )

    def _exercise_is_at_bottom(self, screen: np.ndarray) -> bool:
        """检测演习列表是否已在底部 (下箭头变灰)。"""
        return PixelChecker.check_pixel(
            screen,
            *EXERCISE_ARROW_DOWN_PROBE,
            EXERCISE_ARROW_GRAY,
            EXERCISE_ARROW_TOLERANCE,
        )

    def _exercise_swipe_to_top(self) -> None:
        """将演习列表滑动到顶部。"""
        self._ctrl.swipe(*EXERCISE_SWIPE_TO_TOP)
        time.sleep(EXERCISE_SWIPE_DELAY)

    def _exercise_swipe_to_bottom(self) -> None:
        """将演习列表滑动到底部。"""
        self._ctrl.swipe(*EXERCISE_SWIPE_TO_BOTTOM)
        time.sleep(EXERCISE_SWIPE_DELAY)

    def _check_challenge_at(self, screen: np.ndarray, slot: int) -> bool:
        """检测屏幕上第 ``slot`` (0–3) 个可见位置的挑战按钮颜色。

        Returns
        -------
        bool
            ``True`` — 蓝色挑战按钮可见 (可挑战)，``False`` — 已挑战。
        """
        x, y = EXERCISE_CHALLENGE_PROBES[slot]
        return PixelChecker.check_pixel(
            screen, x, y,
            EXERCISE_CHALLENGE_COLOR,
            EXERCISE_CHALLENGE_TOLERANCE,
        )

    # ═══════════════════════════════════════════════════════════════════════
    # 查询 — 对手挑战状态
    # ═══════════════════════════════════════════════════════════════════════

    def get_exercise_rival_status(self) -> ExerciseRivalStatus:
        """检测所有 5 个演习对手的挑战状态。

        **流程** (参考 legacy ``get_exercise_stats``):
        1. 上滑确保列表在顶部。
        2. 截图，检测屏幕 4 个位置 (对手 1–4)。
        3. 下滑到底部。
        4. 截图，检测屏幕第 4 个位置 (此时为对手 5)。

        Returns
        -------
        ExerciseRivalStatus
            5 个对手的可挑战状态。
        """
        status = ExerciseRivalStatus()

        # 1. 确保在顶部
        screen = self._ctrl.screenshot()
        if not self._exercise_is_at_top(screen):
            self._exercise_swipe_to_top()
            screen = self._ctrl.screenshot()

        # 2. 读取对手 1–4
        for i in range(4):
            status.rivals[i] = self._check_challenge_at(screen, i)

        logger.debug(
            "[UI] 演习对手 1–4 状态: {}",
            ["✓" if s else "✗" for s in status.rivals[:4]],
        )

        # 3. 下滑到底部
        self._exercise_swipe_to_bottom()
        screen = self._ctrl.screenshot()

        # 4. 读取对手 5 (此时在第 4 个可见位置)
        status.rivals[4] = self._check_challenge_at(screen, 3)

        logger.info("[UI] 演习对手状态: {}", status)
        return status

    # ═══════════════════════════════════════════════════════════════════════
    # 操作 — 选择指定对手
    # ═══════════════════════════════════════════════════════════════════════

    def select_exercise_rival(self, rival_index: int) -> None:
        """在演习面板中点击选择指定对手。

        **滚动逻辑**:
        - 对手 1–4: 上滑到顶部后，点击对应可见位置 (0–3)。
        - 对手 5: 下滑到底部后，点击第 4 个可见位置 (3)。

        选择后会进入「对手信息」页面，可查看阵容或开始战斗。

        Parameters
        ----------
        rival_index:
            对手序号 (1–5, 1-based)。

        Raises
        ------
        ValueError
            对手序号不在 1–5 范围内。
        """
        if not 1 <= rival_index <= 5:
            raise ValueError(f"对手序号必须为 1–5，收到: {rival_index}")

        logger.info("[UI] 演习 → 选择第 {} 个对手", rival_index)

        if rival_index <= 4:
            # 对手 1–4: 确保在顶部
            screen = self._ctrl.screenshot()
            if not self._exercise_is_at_top(screen):
                self._exercise_swipe_to_top()

            slot = rival_index - 1  # 可见位置 0–3
            x, y = EXERCISE_CHALLENGE_PROBES[slot]
            self._ctrl.click(x, y)
        else:
            # 对手 5: 确保在底部
            screen = self._ctrl.screenshot()
            if not self._exercise_is_at_bottom(screen):
                self._exercise_swipe_to_bottom()

            x, y = EXERCISE_CHALLENGE_PROBES[3]  # 第 4 个可见位置
            self._ctrl.click(x, y)

        time.sleep(0.5)

    # ═══════════════════════════════════════════════════════════════════════
    # 操作 — 选择对手后进入战斗
    # ═══════════════════════════════════════════════════════════════════════

    def enter_exercise_battle(self) -> None:
        """在「对手信息」页面点击开始战斗，进入出征准备页。

        在调用此方法前，应先通过 :meth:`select_exercise_rival` 选择对手。

        Raises
        ------
        NavigationError
            超时未到达出征准备页面。
        """
        from autowsgr.ui.battle.preparation import BattlePreparationPage

        logger.info("[UI] 演习 → 开始战斗 (对手信息页 → 出征准备)")
        click_and_wait_for_page(
            self._ctrl,
            click_coord=EXERCISE_CLICK_START_BATTLE,
            checker=BattlePreparationPage.is_current_page,
            source="演习-对手信息",
            target=PageName.BATTLE_PREP,
        )

    # ═══════════════════════════════════════════════════════════════════════
    # 操作 — 在对手信息页刷新阵容
    # ═══════════════════════════════════════════════════════════════════════

    def refresh_rival_in_info_page(self) -> None:
        """在「对手信息」页面点击刷新按钮，更换当前对手的阵容。

        参考 legacy: ``timer.click(665, 400, delay=0.75)``。
        """
        logger.info("[UI] 演习 → 刷新对手阵容 (对手信息页)")
        self._ctrl.click(*EXERCISE_CLICK_RIVAL_INFO)
        time.sleep(0.75)

    # ═══════════════════════════════════════════════════════════════════════
    # 查询 — 识别对手阵容 (预留接口)
    # ═══════════════════════════════════════════════════════════════════════

    def recognize_rival_formation(self) -> list[str] | None:
        """识别当前「对手信息」页面的对手阵容。

        .. note::
            此接口为预留，实际 OCR 识别逻辑将在后续版本实现。
            目前仅截图并返回 ``None``。

        Returns
        -------
        list[str] | None
            对手舰船类型列表 (如 ``["DD", "CL", "CA", "BB", "CV", "SS"]``)，
            识别失败返回 ``None``。
        """
        screen = self._ctrl.screenshot()
        logger.debug("[UI] 演习 → 识别对手阵容 (预留接口, 尚未实现)")
        # TODO: 实现 OCR 识别对手阵容
        # 参考 legacy get_enemy_condition() — 裁切 TYPE_SCAN_AREA[0] 区域进行文字识别
        _ = screen
        return None

    # ═══════════════════════════════════════════════════════════════════════
    # 组合操作 — 选择并进入战斗
    # ═══════════════════════════════════════════════════════════════════════

    def challenge_rival(self, rival_index: int) -> None:
        """选择指定对手并直接进入出征准备页。

        这是 :meth:`select_exercise_rival` + :meth:`enter_exercise_battle`
        的组合快捷方法。

        Parameters
        ----------
        rival_index:
            对手序号 (1–5)。
        """
        self.select_exercise_rival(rival_index)
        time.sleep(0.5)
        self.enter_exercise_battle()
