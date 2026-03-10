"""任务页面 UI 控制器。

使用方式::

    from autowsgr.ui.mission_page import MissionPage, MissionPanel

    page = MissionPage(ctx)
    page.go_back()

    # 切换到周常标签
    page.switch_panel(MissionPanel.WEEKLY)

    # 任务识别
    missions = page.recognize_missions(screen)
    for m in missions:
        print(m.name, m.progress, m.claimable)
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from autowsgr.image_resources import Templates
from autowsgr.infra.logger import get_logger
from autowsgr.types import PageName
from autowsgr.ui.mission_page.data import (
    CLICK_BACK,
    CLICK_CONFIRM_CENTER,
    CLICK_PANEL,
    PANEL_SWITCH_DELAY,
    MissionPanel,
)
from autowsgr.ui.mission_page.recognition import find_button_rows, recognize_row
from autowsgr.ui.tabbed_page import TabbedPageType, identify_page_type
from autowsgr.ui.utils import click_and_wait_for_page
from autowsgr.vision import ImageChecker


if TYPE_CHECKING:
    import numpy as np

    from autowsgr.context import GameContext
    from autowsgr.ui.mission_page.data import MissionInfo


_log = get_logger('ui')


class MissionPage:
    """任务页面控制器。

    Parameters
    ----------
    ctx:
        游戏上下文实例。
    """

    def __init__(self, ctx: GameContext) -> None:
        self._ctx = ctx
        self._ctrl = ctx.ctrl

    # ── 页面识别 ──────────────────────────────────────────────────────────

    @staticmethod
    def is_current_page(screen: np.ndarray) -> bool:
        """判断截图是否为任务页面。"""
        return identify_page_type(screen) == TabbedPageType.MISSION

    # ── 面板切换 ──────────────────────────────────────────────────────────

    def switch_panel(self, panel: MissionPanel) -> None:
        """切换到指定子标签 (日常/周常)。

        Parameters
        ----------
        panel:
            目标面板。
        """
        _log.info('[UI] 任务页面: 切换到 {}', panel.value)
        self._ctrl.click(*CLICK_PANEL[panel])
        time.sleep(PANEL_SWITCH_DELAY)

    # ── 回退 ──────────────────────────────────────────────────────────────

    def go_back(self) -> None:
        """点击回退按钮, 返回主页面。

        Raises
        ------
        NavigationError
            超时仍在任务页面。
        """
        from autowsgr.ui.main_page import MainPage

        _log.info('[UI] 任务页面 -> 返回主页面')
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_BACK,
            checker=MainPage.is_current_page,
            source=PageName.MISSION,
            target=PageName.MAIN,
        )

    # ── 奖励收取 ─────────────────────────────────────────────────────────

    def dismiss_reward_popup(self) -> None:
        """点击屏幕中央, 关闭领取奖励后的弹窗。"""
        _log.info('[UI] 任务页面 -> 关闭奖励弹窗')
        self._ctrl.click(*CLICK_CONFIRM_CENTER)

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

    # ── 任务识别 ──────────────────────────────────────────────────────────

    def recognize_missions(self, screen: np.ndarray) -> list[MissionInfo]:
        """识别截图中可见的任务列表 (单帧, 不滚动)。

        Parameters
        ----------
        screen:
            任务页面截图 (HxWx3, RGB)。

        Returns
        -------
        list[MissionInfo]
            可见任务列表, 按从上到下排列。
        """
        from autowsgr.ui.mission_page.data import get_all_mission_names

        rows = find_button_rows(screen)
        if not rows:
            _log.debug('[UI] 任务页面: 未检测到按钮行')
            return []

        candidates = get_all_mission_names()
        missions: list[MissionInfo] = []
        for anchor_y, btn_type in rows:
            info = recognize_row(screen, anchor_y, btn_type, self._ctx.ocr, candidates)
            if info is None:
                _log.debug('[UI] 任务识别: 跳过无效行 (anchor_y={:.3f})', anchor_y)
                continue
            _log.debug(
                '[UI] 任务识别: {} (raw={!r}, progress={}%, claimable={})',
                info.name,
                info.raw_text,
                info.progress,
                info.claimable,
            )
            missions.append(info)
        return missions

    def recognize_all_missions(
        self,
        panel: MissionPanel = MissionPanel.DAILY,
        max_scrolls: int = 6,
    ) -> list[MissionInfo]:
        """识别指定子标签下的全部任务 (含自动滚动)。

        Parameters
        ----------
        panel:
            子标签: ``MissionPanel.DAILY`` 或 ``MissionPanel.WEEKLY``。
        max_scrolls:
            最大滚动次数。

        Returns
        -------
        list[MissionInfo]
            全部任务列表。
        """
        self.switch_panel(panel)

        all_missions: list[MissionInfo] = []
        seen_names: set[str] = set()

        for _scroll in range(max_scrolls + 1):
            screen = self._ctrl.screenshot()
            visible = self.recognize_missions(screen)
            new_count = 0
            for m in visible:
                if m.name not in seen_names:
                    seen_names.add(m.name)
                    all_missions.append(m)
                    new_count += 1
            if new_count == 0:
                _log.debug('[UI] 任务识别: 无新任务, 停止滚动 (第 {} 次)', _scroll)
                break
            # 向下滑动
            self._ctrl.swipe(0.5, 0.7, 0.5, 0.45, duration=0.75)
            time.sleep(0.5)

        _log.info('[UI] 任务识别完成: {} 条 (panel={})', len(all_missions), panel.value)
        return all_missions
