"""活动导航 — 主页面 → 活动地图的专用导航流程。

逻辑: 清除浮层 → 等待活动图标模板出现 → 点击并等待活动页面。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from autowsgr.infra.logger import get_logger
from autowsgr.vision import ImageChecker

from .constants import NavCoord, Sig, Target
from .overlays import detect_overlay, dismiss_overlay


if TYPE_CHECKING:
    from collections.abc import Callable

    import numpy as np

    from autowsgr.emulator import AndroidController
    from autowsgr.vision import ImageTemplate

_log = get_logger('ui')

# ── 活动图标模板 (延迟加载) ──────────────────────────────────────────────

_event_icon_templates: list[ImageTemplate] | None = None


def _get_event_icon_templates() -> list[ImageTemplate]:
    """延迟加载活动入口图标模板。"""
    global _event_icon_templates
    if _event_icon_templates is None:
        from autowsgr.image_resources._lazy import load_template

        _event_icon_templates = [
            load_template(
                'event/event_icon_20260212_720p.png',
                name='event_icon',
                source_resolution=(1280, 720),
            ),
        ]
    return _event_icon_templates


# ── 内部: 单次导航尝试 ──────────────────────────────────────────────────


def _try_navigate_to_event(
    ctrl: AndroidController,
    event_checker: Callable[[np.ndarray], bool],
    *,
    icon_wait: float = 3.0,
    nav_wait: float = 5.0,
) -> bool:
    """执行一次活动导航尝试。

    流程:
        1. 确保无浮层覆盖
        2. 等待活动图标模板出现 (图像模板匹配)
        3. 点击图标并等待活动页面签名

    Returns
    -------
    bool
        ``True`` — 成功到达活动页面；``False`` — 本次失败。
    """
    from autowsgr.vision import PixelChecker

    # ① 清除浮层
    screen = ctrl.screenshot()
    overlay = detect_overlay(screen)
    if overlay is not None:
        _log.debug('[UI] 活动导航: 先消除浮层 {}', overlay.value)
        dismiss_overlay(ctrl, overlay)
        time.sleep(0.5)
        screen = ctrl.screenshot()

    # 确认仍在主页面
    if not PixelChecker.check_signature(screen, Sig.PAGE.ps).matched:
        _log.warning('[UI] 活动导航: 当前不在主页面基础态')
        return False

    # ② 等待活动图标模板出现
    templates = _get_event_icon_templates()
    deadline = time.time() + icon_wait
    detail = None
    while time.time() < deadline:
        screen = ctrl.screenshot()
        detail = ImageChecker.find_any(screen, templates, confidence=0.8)
        if detail is not None:
            break
        time.sleep(0.3)

    if detail is None:
        _log.warning('[UI] 活动导航: 等待 {:.1f}s 后仍未检测到活动图标', icon_wait)
        return False

    # ③ 点击活动图标并等待活动页面
    coord = NavCoord.EVENT.xy
    _log.debug('[UI] 主页面 → 活动')
    ctrl.click(*coord)
    time.sleep(1.0)

    deadline = time.time() + nav_wait
    while time.time() < deadline:
        screen = ctrl.screenshot()
        if event_checker(screen):
            _log.info('[UI] 已到达活动地图页面')
            return True
        # 点击后可能触发的浮层 (如预约页) 由 overlay 机制统一处理
        overlay = detect_overlay(screen)
        if overlay is not None:
            _log.debug('[UI] 活动导航: 点击后出现浮层 {}, 消除', overlay.value)
            dismiss_overlay(ctrl, overlay)
        time.sleep(0.5)

    _log.warning('[UI] 活动导航: 点击后 {:.1f}s 内未到达活动页面', nav_wait)
    return False


# ── 公开: 带重试的导航入口 ──────────────────────────────────────────────


def navigate_to_event(
    ctrl: AndroidController,
    *,
    is_base_page: type,  # MainPage class (保留兼容签名)
    max_retries: int = 3,
) -> None:
    """导航到活动地图 — 带自动重试。

    Raises
    ------
    NavigationError
        超过最大重试次数仍未到达活动地图页面。
    """
    from autowsgr.ui.page import NavigationError

    from .controller import _get_target_checker

    event_checker = _get_target_checker(Target.EVENT)

    for attempt in range(1, max_retries + 1):
        _log.debug('[UI] 活动导航: 尝试 {}/{}', attempt, max_retries)
        if _try_navigate_to_event(ctrl, event_checker):
            return
        time.sleep(1.0)

    raise NavigationError(
        f'活动导航失败: {max_retries} 次尝试后仍未进入活动地图页面',
    )
