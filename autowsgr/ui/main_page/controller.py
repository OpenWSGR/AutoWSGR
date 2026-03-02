"""主页面 (母港界面) 控制器。
TODO: 从 sidebar_page 打开的浮层暂时无法正常关闭, 但可以走错误恢复流程恢复
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from autowsgr.infra.logger import get_logger
from autowsgr.types import PageName
from autowsgr.vision import PixelChecker

from .constants import (
    NavCoord,
    OverlayKind,
    ProbePoint,
    Sig,
    Target,
    ThemeColor,
)
from .overlays import detect_overlay, dismiss_overlay


if TYPE_CHECKING:
    from collections.abc import Callable

    import numpy as np

    from autowsgr.context import GameContext

_log = get_logger('ui')


# ─────────────────────────────────────────────────────────────────────────────
# 目标页面检测器 (延迟导入)
# ─────────────────────────────────────────────────────────────────────────────


def _get_target_checker(target: Target) -> Callable[[np.ndarray], bool]:
    """延迟导入并返回目标页面的 ``is_current_page``。"""
    if target is Target.SORTIE:
        from autowsgr.ui.map.page import MapPage

        return MapPage.is_current_page
    if target is Target.TASK:
        from autowsgr.ui.mission_page import MissionPage

        return MissionPage.is_current_page
    if target is Target.SIDEBAR:
        from autowsgr.ui.sidebar_page import SidebarPage

        return SidebarPage.is_current_page
    if target is Target.HOME:
        from autowsgr.ui.backyard_page import BackyardPage

        return BackyardPage.is_current_page
    if target is Target.EVENT:
        from autowsgr.ui.event.event_page import BaseEventPage

        return BaseEventPage.is_current_page
    raise ValueError(f'未知的导航目标: {target}')


# ═══════════════════════════════════════════════════════════════════════════════
# 主页面控制器
# ═══════════════════════════════════════════════════════════════════════════════


class MainPage:
    """主页面 (母港界面) 控制器。

    集成页面识别、浮层处理与导航:

    - **页面识别** — :meth:`is_current_page` 同时检测基础页面与浮层
    - **浮层处理** — :meth:`detect_overlay` / :meth:`dismiss_current_overlay`
    - **常规导航** — 走「点击 + 等待目标页面签名」流程
    - **活动导航** — 专用流程，处理侧边栏图标识别与预约页误入

    使用方式::

        page = MainPage(ctrl)
        page.navigate_to(MainPage.Target.SORTIE)
    """

    Target = Target

    def __init__(self, ctx: GameContext) -> None:
        self._ctx = ctx
        self._ctrl = ctx.ctrl

    # ── 页面识别 ──────────────────────────────────────────────────────────

    @staticmethod
    def is_current_page(screen: np.ndarray) -> bool:
        """判断截图是否为主页面 (含浮层覆盖)。

        参考 :class:`~autowsgr.ui.event.event_page.BaseEventPage` 模式，
        将浮层 (新闻公告 / 每日签到 / 活动预约) 也识别为主页面。
        """
        if PixelChecker.check_signature(screen, Sig.PAGE.ps).matched:
            return True
        if PixelChecker.check_signature(screen, Sig.NEWS.ps).matched:
            return True
        if PixelChecker.check_signature(screen, Sig.SIGN.ps).matched:
            return True
        return PixelChecker.check_signature(screen, Sig.BOOKING.ps).matched

    @staticmethod
    def is_base_page(screen: np.ndarray) -> bool:
        """判断截图是否为主页面基础状态 (不含浮层)。"""
        return PixelChecker.check_signature(screen, Sig.PAGE.ps).matched

    @staticmethod
    def detect_overlay(screen: np.ndarray) -> OverlayKind | None:
        """检测当前截图的浮层类型。"""
        return detect_overlay(screen)

    # ── 状态查询 ──────────────────────────────────────────────────────────

    @staticmethod
    def has_expedition_ready(screen: np.ndarray) -> bool:
        """检测是否有远征完成可收取 (右下角红点)。"""
        tc = ThemeColor.NOTIFICATION_RED
        return PixelChecker.get_pixel(
            screen,
            *ProbePoint.EXPEDITION_READY.xy,
        ).near(tc.color, tc.tolerance)

    @staticmethod
    def has_task_ready(screen: np.ndarray) -> bool:
        """检测是否有任务奖励可领取 (任务按钮红点)。"""
        tc = ThemeColor.NOTIFICATION_RED
        return PixelChecker.get_pixel(
            screen,
            *ProbePoint.TASK_READY.xy,
        ).near(tc.color, tc.tolerance)

    # ── 浮层处理 ──────────────────────────────────────────────────────────

    def dismiss_current_overlay(self) -> bool:
        """检测并消除当前浮层。返回 ``True`` 表示已处理。"""
        screen = self._ctrl.screenshot()
        overlay = detect_overlay(screen)
        if overlay is None:
            return False
        dismiss_overlay(self._ctrl, overlay)
        return True

    # ── 导航入口 ──────────────────────────────────────────────────────────

    def navigate_to(self, target: Target) -> None:
        """导航到指定子页面。

        自动处理浮层后再执行导航。活动目标走专用流程。

        Raises
        ------
        NavigationError
            超时未到达目标页面。
        """
        self._ensure_clean_page()
        if target is Target.EVENT:
            self._navigate_to_event()
        else:
            self._navigate_standard(target)

    def _ensure_clean_page(self, *, max_attempts: int = 3) -> None:
        """确保当前在干净的主页面 (无浮层覆盖)。"""
        for i in range(max_attempts):
            screen = self._ctrl.screenshot()
            overlay = detect_overlay(screen)
            if overlay is None:
                return
            _log.info(
                '[UI] 主页面: 导航前消除浮层 {} ({}/{})',
                overlay.value,
                i + 1,
                max_attempts,
            )
            dismiss_overlay(self._ctrl, overlay)
            time.sleep(0.5)

    def _navigate_standard(self, target: Target) -> None:
        """通用单步导航 — 点击坐标 + 等待目标页面签名。"""
        from autowsgr.ui.page import click_and_wait_for_page

        coord = NavCoord[target.name]
        _log.info('[UI] 主页面 → {}', target.value)
        click_and_wait_for_page(
            self._ctrl,
            click_coord=coord.xy,
            checker=_get_target_checker(target),
            source=PageName.MAIN,
            target=target.page_name,
        )

    # ── 活动导航 (委托 event_nav) ────────────────────────────────────────

    def _navigate_to_event(self, *, max_retries: int = 3) -> None:
        """导航到活动地图 — 含侧边栏图标检测与预约页处理。"""
        from .event_nav import navigate_to_event

        navigate_to_event(self._ctrl, is_base_page=MainPage, max_retries=max_retries)

    # ── 便捷方法 ──────────────────────────────────────────────────────────

    def go_to_sortie(self) -> None:
        """进入地图选择页面。"""
        self.navigate_to(Target.SORTIE)

    def go_to_task(self) -> None:
        """进入任务页面。"""
        self.navigate_to(Target.TASK)

    def open_sidebar(self) -> None:
        """打开侧边栏。"""
        self.navigate_to(Target.SIDEBAR)

    def go_home(self) -> None:
        """进入后院页面。"""
        self.navigate_to(Target.HOME)

    def go_to_event(self) -> None:
        """进入活动页面。"""
        self.navigate_to(Target.EVENT)
