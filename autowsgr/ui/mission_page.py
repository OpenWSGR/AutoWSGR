"""任务页面 UI 控制器。

已完成，需测试

使用方式::

    from autowsgr.ui.mission_page import MissionPage

    page = MissionPage(ctrl)
    page.go_back()
"""

from __future__ import annotations

import time

import numpy as np
from loguru import logger

from autowsgr.emulator import AndroidController
from autowsgr.image_resources import Templates
from autowsgr.types import PageName
from autowsgr.ui.page import click_and_wait_for_page
from autowsgr.ui.tabbed_page import TabbedPageType, identify_page_type
from autowsgr.vision import ImageChecker


# ═══════════════════════════════════════════════════════════════════════════════
# 点击坐标
# ═══════════════════════════════════════════════════════════════════════════════

CLICK_BACK: tuple[float, float] = (0.022, 0.058)
"""回退按钮 (◁)。"""

CLICK_CONFIRM_CENTER: tuple[float, float] = (0.5, 0.5)
"""领取奖励后弹窗确认 — 点击屏幕中央关闭。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 页面控制器
# ═══════════════════════════════════════════════════════════════════════════════


class MissionPage:
    """任务页面控制器。

    Parameters
    ----------
    ctrl:
        Android 设备控制器实例。
    """

    def __init__(self, ctrl: AndroidController) -> None:
        self._ctrl = ctrl

    # ── 页面识别 ──────────────────────────────────────────────────────────

    @staticmethod
    def is_current_page(screen: np.ndarray) -> bool:
        """判断截图是否为任务页面。

        通过统一标签页检测层 (:mod:`~autowsgr.ui.tabbed_page`) 识别。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。
        """
        return identify_page_type(screen) == TabbedPageType.MISSION

    # ── 回退 ──────────────────────────────────────────────────────────────

    def go_back(self) -> None:
        """点击回退按钮 (◁)，返回主页面。

        Raises
        ------
        NavigationError
            超时仍在任务页面。
        """
        from autowsgr.ui.main_page import MainPage

        logger.info("[UI] 任务页面 → 返回主页面")
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_BACK,
            checker=MainPage.is_current_page,
            source=PageName.MISSION,
            target=PageName.MAIN,
        )

    # ── 操作 ──────────────────────────────────────────────────────────────

    def dismiss_reward_popup(self) -> None:
        """点击屏幕中央，关闭领取奖励后的弹窗。"""
        logger.info("[UI] 任务页面 → 关闭奖励弹窗")
        self._ctrl.click(*CLICK_CONFIRM_CENTER)

    # ── 组合动作 — 奖励收取 ──

    def _try_confirm(self, *, timeout: float = 5.0) -> bool:
        """等待并点击确认弹窗。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            screen = self._ctrl.screenshot()
            detail = ImageChecker.find_any(screen, Templates.Confirm.all())
            if detail is not None:
                self._ctrl.click(*detail.center)
                time.sleep(0.5)
                return True
            time.sleep(0.3)
        return False

    def collect_rewards(self) -> bool:
        """在任务页面收取奖励。

        必须已在任务页面。依次尝试一键领取和单个领取。

        Returns
        -------
        bool
            是否成功领取了奖励。
        """
        # 尝试 "一键领取"
        screen = self._ctrl.screenshot()
        detail = ImageChecker.find_template(screen, Templates.GameUI.REWARD_COLLECT_ALL)
        if detail is not None:
            self._ctrl.click(*detail.center)
            time.sleep(0.5)
            self.dismiss_reward_popup()
            time.sleep(0.3)
            self._try_confirm(timeout=5.0)
            return True

        # 尝试 "单个领取"
        screen = self._ctrl.screenshot()
        detail = ImageChecker.find_template(screen, Templates.GameUI.REWARD_COLLECT)
        if detail is not None:
            self._ctrl.click(*detail.center)
            time.sleep(0.5)
            self._try_confirm(timeout=5.0)
            return True

        return False
