"""UI 截图-判断-等待 工具函数。

从 ``autowsgr.ui.page`` 迁移而来，提供:

- **NavigationError** — 导航验证失败异常
- **NavConfig / DEFAULT_NAV_CONFIG** — 导航操作参数
- **wait_for_page / wait_leave_page** — 底层截图轮询
- **click_and_wait_for_page / click_and_wait_leave_page** — 带重试的一步导航
- **confirm_operation** — 确认弹窗点击
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from autowsgr.infra.logger import get_logger
from autowsgr.vision import ImageChecker


if TYPE_CHECKING:
    from collections.abc import Callable

    import numpy as np

    from autowsgr.emulator import AndroidController


_log = get_logger('ui')

# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class NavigationError(Exception):
    """页面导航验证失败 - 超时未到达目标页面，或重试耗尽。"""

    def __init__(self, msg: str = '', screen: np.ndarray | None = None) -> None:
        if screen is not None:
            from autowsgr.infra.logger import save_image

            save_image(screen, tag='NavError')
        super().__init__(msg)


# ---------------------------------------------------------------------------
# 导航配置
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class NavConfig:
    """导航操作参数配置。

    Attributes
    ----------
    max_retries:
        点击重试最大次数 (含首次)。
    retry_delay:
        两次点击之间的等待 (秒)。
    timeout:
        每轮验证的超时 (秒)。
    interval:
        验证循环中两次截图的间隔 (秒)。
    handle_overlays:
        是否自动处理游戏浮层 (新闻公告等)。
    """

    max_retries: int = 2
    retry_delay: float = 1.0
    timeout: float = 5.0
    interval: float = 0.5
    handle_overlays: bool = True


DEFAULT_NAV_CONFIG = NavConfig()


# ---------------------------------------------------------------------------
# 底层验证
# ---------------------------------------------------------------------------


def wait_for_page(
    ctrl: AndroidController,
    checker: Callable[[np.ndarray], bool],
    *,
    timeout: float = DEFAULT_NAV_CONFIG.timeout,
    interval: float = DEFAULT_NAV_CONFIG.interval,
    handle_overlays: bool = True,
    source: str = '',
    target: str = '',
) -> np.ndarray:
    """反复截图，直到 ``checker`` 返回 ``True``。

    内置浮层消除。遇到可消除浮层时立即处理并继续轮询（不计入睡眠延迟）。

    Raises
    ------
    NavigationError
        超时仍未匹配。
    """
    from autowsgr.ui.page import get_current_page

    deadline = time.monotonic() + timeout
    attempt = 0
    _log.debug('[UI] 等待到达: {} -> {} (超时 {:.1f}s)', source or '?', target or '?', timeout)

    while True:
        attempt += 1
        screen = ctrl.screenshot()

        if checker(screen):
            _log.debug(
                '[UI] 已到达: {} -> {} (第 {} 次截图)', source or '?', target or '?', attempt
            )
            return screen

        current = get_current_page(screen)
        _log.debug(
            '[UI] 等待 #{}: {} -> {}, 当前={}',
            attempt,
            source or '?',
            target or '?',
            current or '未知',
        )

        if time.monotonic() >= deadline:
            msg = (
                f'等待超时: {source or "?"} -> {target or "?"}, '
                f'{attempt} 次截图后仍未到达, 当前: {current or "未知"}'
            )
            _log.error('[UI] {}', msg)
            raise NavigationError(msg, screen=screen)

        time.sleep(interval)


def wait_leave_page(
    ctrl: AndroidController,
    checker: Callable[[np.ndarray], bool],
    *,
    timeout: float = DEFAULT_NAV_CONFIG.timeout,
    interval: float = DEFAULT_NAV_CONFIG.interval,
    handle_overlays: bool = True,
    source: str = '',
    target: str = '',
) -> np.ndarray:
    """反复截图，直到 ``checker`` 返回 ``False`` (已离开)。

    目标页面签名未采集时的降级方案。优先使用 :func:`wait_for_page`。

    Raises
    ------
    NavigationError
        超时仍在原页面。
    """
    from autowsgr.ui.page import get_current_page

    deadline = time.monotonic() + timeout
    attempt = 0
    _log.debug('[UI] 等待离开: {} -> {} (超时 {:.1f}s)', source or '?', target or '?', timeout)

    while True:
        attempt += 1
        screen = ctrl.screenshot()

        if not checker(screen):
            current = get_current_page(screen)
            _log.debug(
                '[UI] 已离开: {} -> {} (第 {} 次截图, 到达={})',
                source or '?',
                target or '?',
                attempt,
                current or '未知',
            )
            return screen

        _log.debug('[UI] 等待离开 #{}: 仍在 {}', attempt, source or '?')

        if time.monotonic() >= deadline:
            msg = (
                f'离开超时: {source or "?"} -> {target or "?"}, '
                f'{attempt} 次截图后仍在 {source or "?"}'
            )
            _log.error('[UI] {}', msg)
            raise NavigationError(msg, screen=screen)

        time.sleep(interval)


# ---------------------------------------------------------------------------
# 带重试的一步导航 - 推荐 API
# ---------------------------------------------------------------------------


def click_and_wait_for_page(
    ctrl: AndroidController,
    click_coord: tuple[float, float],
    checker: Callable[[np.ndarray], bool],
    *,
    source: str = '',
    target: str = '',
    config: NavConfig = DEFAULT_NAV_CONFIG,
) -> np.ndarray:
    """点击 + 等待到达目标页面，内置重试。

    Raises
    ------
    NavigationError
        点击后未到达目标页面。

    """
    ctrl.click(*click_coord)
    return wait_for_page(
        ctrl,
        checker,
        timeout=config.timeout,
        interval=config.interval,
        handle_overlays=config.handle_overlays,
        source=source,
        target=target,
    )


# ---------------------------------------------------------------------------
# 确认弹窗操作 (Legacy confirm_operation 风格)
# ---------------------------------------------------------------------------


def confirm_operation(
    ctrl: AndroidController,
    *,
    must_confirm: bool = False,
    delay: float = 0.5,
    confidence: float = 0.9,
    timeout: float = 0.0,
) -> bool:
    """等待并点击弹出在屏幕中央的各种确认按钮。

    与 Legacy ``Timer.confirm_operation`` 行为一致:
    在 *timeout* 时限内反复截图寻找任意确认按钮模板，
    找到后精确重定位并点击。

    Parameters
    ----------
    ctrl:
        Android 设备控制器实例。
    must_confirm:
        为 ``True`` 时，超时未找到确认按钮则抛出异常。
    delay:
        点击确认按钮后的睡眠延时 (秒)。
    confidence:
        模板匹配置信度阈值。
    timeout:
        等待确认弹窗出现的最大时限 (秒); <=0 仅检查当前帧。

    Returns
    -------
    bool
        ``True`` 为找到并点击了确认按钮，``False`` 为未找到。

    Raises
    ------
    NavigationError
        *must_confirm* 为 ``True`` 且超时仍未找到确认按钮。
    """
    from autowsgr.image_resources import Templates

    confirm_templates = Templates.Confirm.all()
    deadline = time.monotonic() + max(timeout, 0)

    while True:
        screen = ctrl.screenshot()
        detail = ImageChecker.find_any(
            screen,
            confirm_templates,
            confidence=confidence,
        )
        if detail is not None:
            # 精确重定位 (Legacy 二次匹配风格)
            screen2 = ctrl.screenshot()
            detail2 = ImageChecker.find_any(
                screen2,
                confirm_templates,
                confidence=confidence,
            )
            if detail2 is not None:
                detail = detail2
            ctrl.click(*detail.center)
            _log.info(
                "[UI] 确认操作: 点击 '{}' ({:.4f}, {:.4f})",
                detail.template_name,
                *detail.center,
            )
            time.sleep(delay)
            return True

        if time.monotonic() >= deadline:
            break
        time.sleep(0.3)

    if must_confirm:
        raise NavigationError('确认操作超时: 未找到确认按钮', screen=ctrl.screenshot())
    return False


def click_and_wait_leave_page(
    ctrl: AndroidController,
    click_coord: tuple[float, float],
    checker: Callable[[np.ndarray], bool],
    *,
    source: str = '',
    target: str = '',
    config: NavConfig = DEFAULT_NAV_CONFIG,
) -> np.ndarray:
    """点击 + 等待离开当前页面，内置重试。

    目标页面签名未采集时的降级版本。
    优先使用 :func:`click_and_wait_for_page`。

    Raises
    ------
    NavigationError
        所有重试均超时。
    """
    last_err: NavigationError | None = None

    for attempt in range(1, config.max_retries + 1):
        if attempt > 1:
            _log.warning(
                '[UI] 离开重试 {}/{}: {} -> {} (等 {:.1f}s)',
                attempt,
                config.max_retries,
                source or '?',
                target or '?',
                config.retry_delay,
            )
            time.sleep(config.retry_delay)

        ctrl.click(*click_coord)

        try:
            return wait_leave_page(
                ctrl,
                checker,
                timeout=config.timeout,
                interval=config.interval,
                handle_overlays=config.handle_overlays,
                source=source,
                target=target,
            )
        except NavigationError as e:
            last_err = e
            _log.warning(
                '[UI] 点击后离开超时 ({}/{}): {} -> {}',
                attempt,
                config.max_retries,
                source or '?',
                target or '?',
            )

    raise NavigationError(
        f'离开失败 (已重试 {config.max_retries} 次): {source or "?"} -> {target or "?"}',
        screen=ctrl.screenshot(),
    ) from last_err
