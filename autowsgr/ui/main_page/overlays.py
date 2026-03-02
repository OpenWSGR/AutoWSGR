"""主页面浮层检测与消除。

浮层类型:

- **NEWS** (新闻公告): 登录后可能出现，带「不再显示」复选框
- **SIGN** (每日签到): 登录后可能出现签到奖励弹窗

使用方式::

    from autowsgr.ui.main_page.overlays import detect_overlay, dismiss_overlay

    overlay = detect_overlay(screen)
    if overlay is not None:
        dismiss_overlay(ctrl, overlay)
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from autowsgr.infra.logger import get_logger
from autowsgr.vision import PixelChecker

from .constants import DismissCoord, OverlayKind, Sig


if TYPE_CHECKING:
    import numpy as np

    from autowsgr.emulator import AndroidController


_log = get_logger('ui')


# ─────────────────────────────────────────────────────────────────────────────
# 检测
# ─────────────────────────────────────────────────────────────────────────────


def detect_overlay(screen: np.ndarray) -> OverlayKind | None:
    """检测截图中是否存在主页面浮层。

    按优先级依次检测: NEWS → SIGN → BOOKING。

    Returns
    -------
    OverlayKind | None
        检测到的浮层类型，无浮层返回 ``None``。
    """
    if PixelChecker.check_signature(screen, Sig.NEWS.ps).matched:
        _log.debug('[UI] 检测到浮层: 新闻公告')
        return OverlayKind.NEWS
    if PixelChecker.check_signature(screen, Sig.SIGN.ps).matched:
        _log.debug('[UI] 检测到浮层: 每日签到')
        return OverlayKind.SIGN
    if PixelChecker.check_signature(screen, Sig.BOOKING.ps).matched:
        _log.debug('[UI] 检测到浮层: 活动预约')
        return OverlayKind.BOOKING
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 消除 — 专用函数
# ─────────────────────────────────────────────────────────────────────────────


def dismiss_news(ctrl: AndroidController, screen: np.ndarray | None = None) -> None:
    """关闭新闻公告浮层。"""
    if screen is None:
        screen = ctrl.screenshot()

    not_show = PixelChecker.check_signature(screen, Sig.NEWS_NOT_SHOW.ps).matched
    if not not_show:
        _log.info('[UI] 新闻公告: 勾选「不再显示」')
        ctrl.click(*DismissCoord.NEWS_NOT_SHOW.xy)
        time.sleep(0.3)

    _log.info('[UI] 新闻公告: 关闭')
    ctrl.click(*DismissCoord.NEWS_CLOSE.xy)


def dismiss_sign(ctrl: AndroidController) -> None:
    """关闭每日签到浮层。"""
    from autowsgr.ui.page import confirm_operation

    _log.info('[UI] 每日签到: 关闭')
    ctrl.click(*DismissCoord.SIGN_CONFIRM.xy)
    confirm_operation(ctrl, must_confirm=True, timeout=5.0)


def dismiss_booking(ctrl: AndroidController) -> None:
    """关闭活动预约浮层。"""
    _log.info('[UI] 活动预约: 关闭')
    ctrl.click(*DismissCoord.BOOKING.xy)
    time.sleep(1.0)
    # 二次确认 — 若仍未返回主页面则再点一次
    from autowsgr.ui.main_page.constants import Sig as _Sig

    screen = ctrl.screenshot()
    if not PixelChecker.check_signature(screen, _Sig.PAGE.ps).matched:
        _log.warning('[UI] 活动预约: 首次关闭未生效，重试')
        ctrl.click(*DismissCoord.BOOKING.xy)
        time.sleep(1.0)


# ─────────────────────────────────────────────────────────────────────────────
# 消除 — 统一分发
# ─────────────────────────────────────────────────────────────────────────────


def dismiss_overlay(ctrl: AndroidController, overlay: OverlayKind) -> None:
    """消除指定类型的浮层。"""
    match overlay:
        case OverlayKind.NEWS:
            dismiss_news(ctrl)
        case OverlayKind.SIGN:
            dismiss_sign(ctrl)
        case OverlayKind.BOOKING:
            dismiss_booking(ctrl)
        case _:
            raise ValueError(f'未知浮层类型: {overlay}')
