"""跨页面导航 — 从任意页面到达目标页面。

提供游戏层的核心导航能力: ``goto_page(ctrl, PageName.目标)``
"""

from __future__ import annotations

import time

from loguru import logger

from autowsgr.emulator import AndroidController
from autowsgr.types import PageName
from autowsgr.ui.navigation import find_path
from autowsgr.ui.page import NavigationError, get_current_page


# ═══════════════════════════════════════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════════════════════════════════════

MAX_IDENTIFY_ATTEMPTS: int = 5
"""页面识别最大尝试次数。"""

IDENTIFY_INTERVAL: float = 1.0
"""页面识别重试间隔 (秒)。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 页面识别
# ═══════════════════════════════════════════════════════════════════════════════


def identify_current_page(ctrl: AndroidController) -> str | None:
    """截图并识别当前页面。

    尝试多次截图以应对动画或加载中的情况。

    Returns
    -------
    str | None
        当前页面名称，无法识别返回 ``None``。
    """
    for attempt in range(MAX_IDENTIFY_ATTEMPTS):
        screen = ctrl.screenshot()
        page = get_current_page(screen)
        if page is not None:
            return page
        logger.debug(
            "[OPS] 页面识别失败 (第 {} 次尝试), 等待重试",
            attempt + 1,
        )
        time.sleep(IDENTIFY_INTERVAL)
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# 导航函数
# ═══════════════════════════════════════════════════════════════════════════════


def _goto_page(ctrl: AndroidController, target: str) -> None:
    """从当前页面导航到目标页面。

    1. 识别当前页面
    2. BFS 查找路径
    3. 逐边调用 ``edge.action(ctrl)``（截图验证由页面控制器内部完成）

    Raises
    ------
    NavigationError
        无法识别当前页面或找不到路径。
    """
    current = identify_current_page(ctrl)
    if current is None:
        raise NavigationError(
            f"无法识别当前页面，无法导航到 '{target}'"
        )

    if current == target:
        logger.info("[OPS] 已在目标页面: {}", target)
        return

    path = find_path(current, target)
    if path is None:
        raise NavigationError(
            f"无法找到从 '{current}' 到 '{target}' 的路径"
        )

    logger.info("[OPS] 导航: {} → {} (共 {} 步)", current, target, len(path))

    for i, edge in enumerate(path):
        logger.info(
            "[OPS]   步骤 {}/{}: {} → {} ({})",
            i + 1, len(path), edge.source, edge.target, edge.description,
        )
        edge.action(ctrl)

    logger.info("[OPS] 已到达: {}", target)


def goto_page(ctrl: AndroidController, target: str) -> None:
    """导航到目标页面，失败时自动重试一次。"""
    try:
        _goto_page(ctrl, target)
    except NavigationError as e:
        logger.error("[OPS] 导航失败: {}", e)
        current_page = identify_current_page(ctrl)
        logger.info("[OPS] 当前页面: {}, 执行一次重试", current_page)
        _goto_page(ctrl, target)