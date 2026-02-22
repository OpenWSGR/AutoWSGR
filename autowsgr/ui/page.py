"""UI 页面注册中心与导航工具。

提供三大功能:

1. **页面注册** — 每个页面控制器注册自己的识别函数，
   :func:`get_current_page` 遍历注册表识别当前截图。

2. **导航验证** — :func:`wait_for_page` / :func:`wait_leave_page`
   反复截图检查，内置浮层消除，确认导航生效。

3. **带重试的一步导航** — :func:`click_and_wait_for_page` /
   :func:`click_and_wait_leave_page`
   封装「点击 + 验证」，自动重试未响应的点击，保证到达或抛出异常。

典型使用::

    from autowsgr.ui.page import click_and_wait_leave_page, NavigationError

    # 点击，等待离开当前页 (带重试)
    click_and_wait_leave_page(
        ctrl,
        click_coord=(0.94, 0.90),
        checker=MainPage.is_current_page,
        source="主页面",
        target="地图页面",
    )

    # 自定义重试参数
    from autowsgr.ui.page import NavConfig
    cfg = NavConfig(max_retries=5, retry_delay=2.0, timeout=15.0)
    click_and_wait_for_page(ctrl, coord, checker, source="...", target="...", config=cfg)

错误层次::

    NavigationError  — 超时未到达目标，重试耗尽
    NetworkError     — 游戏进入登录/重连界面，需人工处理
        (来自 autowsgr.ui.overlay)
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

import numpy as np
from loguru import logger

from autowsgr.emulator import AndroidController
from autowsgr.ui.overlay import detect_overlay, dismiss_overlay  # noqa: F401
from autowsgr.vision import ImageChecker


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class NavigationError(Exception):
    """页面导航验证失败 — 超时未到达目标页面，或重试耗尽。"""


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
# 页面注册中心
# ---------------------------------------------------------------------------

_PAGE_REGISTRY: dict[str, Callable[[np.ndarray], bool]] = {}


def register_page(name: str, checker: Callable[[np.ndarray], bool]) -> None:
    """注册页面识别函数。"""
    if name in _PAGE_REGISTRY:
        logger.warning("[UI] 页面 '{}' 已注册，将覆盖", name)
    _PAGE_REGISTRY[name] = checker
    logger.debug("[UI] 注册页面: {}", name)


def get_current_page(screen: np.ndarray) -> str | None:
    """识别截图对应的页面名称，无匹配返回 ``None``。"""
    failed_checkers: list[str] = []
    for name, checker in _PAGE_REGISTRY.items():
        try:
            if checker(screen):
                logger.debug("[UI] 当前页面: {}", name)
                return name
        except Exception:
            logger.opt(exception=True).warning("[UI] 页面 '{}' 识别器异常", name)
            failed_checkers.append(name)
    if failed_checkers:
        logger.warning(
            "[UI] 无匹配页面，且以下识别器抛异常: {} (共 {} 个注册页面)",
            failed_checkers, len(_PAGE_REGISTRY),
        )
    else:
        logger.debug("[UI] 当前页面: 无匹配 (共 {} 个注册页面)", len(_PAGE_REGISTRY))
    return None


def get_registered_pages() -> list[str]:
    """返回所有已注册的页面名称列表。"""
    return list(_PAGE_REGISTRY.keys())


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _handle_overlay_if_present(
    ctrl: AndroidController,
    screen: np.ndarray,
) -> bool:
    """检测并尝试消除浮层。

    Returns True 表示执行了消除动作（调用方应跳过 sleep 立即重截图）。
    Raises NetworkError 表示遇到无法自动消除的浮层。
    """
    overlay = detect_overlay(screen)
    if overlay is None:
        return False
    dismiss_overlay(ctrl, overlay)   # NetworkError 向上抛
    return True


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
    source: str = "",
    target: str = "",
) -> np.ndarray:
    """反复截图，直到 ``checker`` 返回 ``True``。

    内置浮层消除。遇到可消除浮层时立即处理并继续轮询（不计入睡眠延迟）。

    Raises
    ------
    NavigationError
        超时仍未匹配。
    NetworkError
        遇到无法自动消除的浮层。
    """
    deadline = time.monotonic() + timeout
    attempt = 0
    logger.info("[UI] 等待到达: {} → {} (超时 {:.1f}s)", source or "?", target or "?", timeout)

    while True:
        attempt += 1
        screen = ctrl.screenshot()

        if handle_overlays and _handle_overlay_if_present(ctrl, screen):
            logger.debug("[UI] 等待 #{}: 消除浮层，立即重截图", attempt)
            continue

        if checker(screen):
            logger.info("[UI] 已到达: {} → {} (第 {} 次截图)", source or "?", target or "?", attempt)
            return screen

        current = get_current_page(screen)
        logger.debug("[UI] 等待 #{}: {} → {}, 当前={}", attempt, source or "?", target or "?", current or "未知")

        if time.monotonic() >= deadline:
            msg = (
                f"等待超时: {source or '?'} → {target or '?'}, "
                f"{attempt} 次截图后仍未到达, 当前: {current or '未知'}"
            )
            logger.error("[UI] {}", msg)
            raise NavigationError(msg)

        time.sleep(interval)


def wait_leave_page(
    ctrl: AndroidController,
    checker: Callable[[np.ndarray], bool],
    *,
    timeout: float = DEFAULT_NAV_CONFIG.timeout,
    interval: float = DEFAULT_NAV_CONFIG.interval,
    handle_overlays: bool = True,
    source: str = "",
    target: str = "",
) -> np.ndarray:
    """反复截图，直到 ``checker`` 返回 ``False`` (已离开)。

    目标页面签名未采集时的降级方案。优先使用 :func:`wait_for_page`。

    Raises
    ------
    NavigationError
        超时仍在原页面。
    NetworkError
        遇到无法自动消除的浮层。
    """
    deadline = time.monotonic() + timeout
    attempt = 0
    logger.info("[UI] 等待离开: {} → {} (超时 {:.1f}s)", source or "?", target or "?", timeout)

    while True:
        attempt += 1
        screen = ctrl.screenshot()

        if handle_overlays and _handle_overlay_if_present(ctrl, screen):
            logger.debug("[UI] 等待离开 #{}: 消除浮层，立即重截图", attempt)
            continue

        if not checker(screen):
            current = get_current_page(screen)
            logger.info("[UI] 已离开: {} → {} (第 {} 次截图, 到达={})", source or "?", target or "?", attempt, current or "未知")
            return screen

        logger.debug("[UI] 等待离开 #{}: 仍在 {}", attempt, source or "?")

        if time.monotonic() >= deadline:
            msg = (
                f"离开超时: {source or '?'} → {target or '?'}, "
                f"{attempt} 次截图后仍在 {source or '?'}"
            )
            logger.error("[UI] {}", msg)
            raise NavigationError(msg)

        time.sleep(interval)


# ---------------------------------------------------------------------------
# 带重试的一步导航 — 推荐 API
# ---------------------------------------------------------------------------


def click_and_wait_for_page(
    ctrl: AndroidController,
    click_coord: tuple[float, float],
    checker: Callable[[np.ndarray], bool],
    *,
    source: str = "",
    target: str = "",
    config: NavConfig = DEFAULT_NAV_CONFIG,
) -> np.ndarray:
    """点击 + 等待到达目标页面，内置重试。

    Raises
    ------
    NavigationError
        点击后未到达目标页面。
    NetworkError
        遇到无法自动消除的浮层。
    """
    ctrl.click(*click_coord)
    return wait_for_page(
        ctrl, checker,
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
        等待确认弹窗出现的最大时限 (秒); ≤0 仅检查当前帧。

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
            screen, confirm_templates, confidence=confidence,
        )
        if detail is not None:
            # 精确重定位 (Legacy 二次匹配风格)
            screen2 = ctrl.screenshot()
            detail2 = ImageChecker.find_any(
                screen2, confirm_templates, confidence=confidence,
            )
            if detail2 is not None:
                detail = detail2
            ctrl.click(*detail.center)
            logger.info(
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
        raise NavigationError("确认操作超时: 未找到确认按钮")
    return False


def click_and_wait_leave_page(
    ctrl: AndroidController,
    click_coord: tuple[float, float],
    checker: Callable[[np.ndarray], bool],
    *,
    source: str = "",
    target: str = "",
    config: NavConfig = DEFAULT_NAV_CONFIG,
) -> np.ndarray:
    """点击 + 等待离开当前页面，内置重试。

    目标页面签名未采集时的降级版本。
    优先使用 :func:`click_and_wait_for_page`。

    Raises
    ------
    NavigationError
        所有重试均超时。
    NetworkError
        遇到无法自动消除的浮层。
    """
    last_err: NavigationError | None = None

    for attempt in range(1, config.max_retries + 1):
        if attempt > 1:
            logger.warning(
                "[UI] 离开重试 {}/{}: {} → {} (等 {:.1f}s)",
                attempt, config.max_retries, source or "?", target or "?", config.retry_delay,
            )
            time.sleep(config.retry_delay)

        ctrl.click(*click_coord)

        try:
            return wait_leave_page(
                ctrl, checker,
                timeout=config.timeout,
                interval=config.interval,
                handle_overlays=config.handle_overlays,
                source=source,
                target=target,
            )
        except NavigationError as e:
            last_err = e
            logger.warning("[UI] 点击后离开超时 ({}/{}): {} → {}", attempt, config.max_retries, source or "?", target or "?")

    raise NavigationError(
        f"离开失败 (已重试 {config.max_retries} 次): {source or '?'} → {target or '?'}"
    ) from last_err
