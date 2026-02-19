"""UI 页面注册中心与导航验证工具。

提供两类功能:

1. **页面注册** — 每个页面控制器注册自己的识别函数，
   :func:`get_current_page` 遍历注册表识别当前截图对应的页面。

2. **导航验证** — :func:`wait_for_page` / :func:`wait_leave_page`
   反复截图检查，确认导航操作确实生效。

典型使用::

    from autowsgr.ui.page import get_current_page, wait_for_page

    # 识别当前页面
    screen = ctrl.screenshot()
    page_name = get_current_page(screen)

    # 导航后等待到达目标
    ctrl.click(0.9, 0.9)
    wait_for_page(ctrl, target_checker, source="主页面", target="出征")
"""

from __future__ import annotations

import time
from typing import Callable

import numpy as np
from loguru import logger

from autowsgr.emulator.controller import AndroidController


# ═══════════════════════════════════════════════════════════════════════════════
# 异常
# ═══════════════════════════════════════════════════════════════════════════════


class NavigationError(Exception):
    """页面导航验证失败 — 超时未到达目标页面。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 页面注册中心
# ═══════════════════════════════════════════════════════════════════════════════

_PAGE_REGISTRY: dict[str, Callable[[np.ndarray], bool]] = {}


def register_page(name: str, checker: Callable[[np.ndarray], bool]) -> None:
    """注册页面识别函数。

    Parameters
    ----------
    name:
        页面名称 (如 ``"主页面"``、``"地图页面"``)。
    checker:
        接收截图 (H×W×3, RGB) 返回 ``bool`` 的识别函数。
    """
    if name in _PAGE_REGISTRY:
        logger.warning("[UI] 页面 '{}' 已注册，将覆盖", name)
    _PAGE_REGISTRY[name] = checker
    logger.debug("[UI] 注册页面: {}", name)


def get_current_page(screen: np.ndarray) -> str | None:
    """识别截图对应的页面名称。

    遍历所有已注册的页面识别函数，返回第一个匹配的页面名称。

    Parameters
    ----------
    screen:
        截图 (H×W×3, RGB)。

    Returns
    -------
    str | None
        页面名称，全部未匹配时返回 ``None``。
    """
    for name, checker in _PAGE_REGISTRY.items():
        try:
            if checker(screen):
                logger.debug("[UI] 当前页面: {}", name)
                return name
        except Exception:
            logger.opt(exception=True).warning(
                "[UI] 页面 '{}' 识别器异常", name,
            )
    logger.debug(
        "[UI] 当前页面: 无匹配 (共 {} 个注册页面)", len(_PAGE_REGISTRY),
    )
    return None


def get_registered_pages() -> list[str]:
    """返回所有已注册的页面名称列表。"""
    return list(_PAGE_REGISTRY.keys())


# ═══════════════════════════════════════════════════════════════════════════════
# 导航验证
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULT_TIMEOUT: float = 10.0
"""默认导航验证超时 (秒)。"""

DEFAULT_INTERVAL: float = 0.5
"""默认截图间隔 (秒)。"""


def wait_for_page(
    ctrl: AndroidController,
    checker: Callable[[np.ndarray], bool],
    *,
    timeout: float = DEFAULT_TIMEOUT,
    interval: float = DEFAULT_INTERVAL,
    source: str = "",
    target: str = "",
) -> np.ndarray:
    """反复截图验证，直到 ``checker`` 返回 ``True``。

    用于导航后确认已到达目标页面。

    Parameters
    ----------
    ctrl:
        设备控制器。
    checker:
        页面识别函数 — 接收截图返回是否到达。
    timeout:
        超时 (秒)。
    interval:
        两次截图间的等待 (秒)。
    source:
        来源页面名称 (仅日志)。
    target:
        目标页面名称 (仅日志)。

    Returns
    -------
    np.ndarray
        验证成功时的截图。

    Raises
    ------
    NavigationError
        超时未到达目标页面。
    """
    deadline = time.monotonic() + timeout
    attempt = 0
    logger.info(
        "[UI] 导航验证开始: {} → {} (超时 {:.1f}s)",
        source, target, timeout,
    )

    while True:
        attempt += 1
        screen = ctrl.screenshot()
        result = checker(screen)

        if result:
            logger.info(
                "[UI] 导航验证成功: {} → {} (第 {} 次截图)",
                source, target, attempt,
            )
            return screen

        current = get_current_page(screen)
        logger.debug(
            "[UI] 导航验证 #{}: {} → {}, 当前={}, 结果=✗",
            attempt, source, target, current or "未知",
        )

        if time.monotonic() >= deadline:
            msg = (
                f"导航验证超时: {source} → {target}, "
                f"{attempt} 次截图验证后仍未到达, "
                f"当前页面: {current or '未知'}"
            )
            logger.error("[UI] {}", msg)
            raise NavigationError(msg)

        time.sleep(interval)


def wait_leave_page(
    ctrl: AndroidController,
    checker: Callable[[np.ndarray], bool],
    *,
    timeout: float = DEFAULT_TIMEOUT,
    interval: float = DEFAULT_INTERVAL,
    source: str = "",
    target: str = "",
) -> np.ndarray:
    """反复截图验证，直到 ``checker`` 返回 ``False`` (已离开)。

    用于导航后确认已离开当前页面 (目标页面无签名时的降级方案)。

    Parameters
    ----------
    ctrl:
        设备控制器。
    checker:
        当前页面识别函数 — 返回 ``True`` 表示仍在原页面。
    timeout:
        超时 (秒)。
    interval:
        两次截图间的等待 (秒)。
    source:
        来源页面名称 (仅日志)。
    target:
        目标页面名称 (仅日志)。

    Returns
    -------
    np.ndarray
        确认离开时的截图。

    Raises
    ------
    NavigationError
        超时仍在原页面。
    """
    deadline = time.monotonic() + timeout
    attempt = 0
    logger.info(
        "[UI] 离开验证开始: {} → {} (超时 {:.1f}s)",
        source, target, timeout,
    )

    while True:
        attempt += 1
        screen = ctrl.screenshot()
        still_here = checker(screen)

        if not still_here:
            current = get_current_page(screen)
            logger.info(
                "[UI] 离开验证成功: {} → {} (第 {} 次截图, 到达={})",
                source, target, attempt, current or "未知",
            )
            return screen

        logger.debug(
            "[UI] 离开验证 #{}: {} → {}, 仍在 {}",
            attempt, source, target, source,
        )

        if time.monotonic() >= deadline:
            msg = (
                f"离开验证超时: {source} → {target}, "
                f"{attempt} 次截图验证后仍在 {source}"
            )
            logger.error("[UI] {}", msg)
            raise NavigationError(msg)

        time.sleep(interval)
