"""跨页面导航 — 从任意页面到达目标页面。

提供游戏层的核心导航能力: ``goto_page(ctx, PageName.目标)``
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from autowsgr.infra.logger import get_logger
from autowsgr.ui.navigation import find_path
from autowsgr.ui.page import get_current_page
from autowsgr.ui.utils import NavigationError


if TYPE_CHECKING:
    from autowsgr.context import GameContext

_log = get_logger('ops')

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


def identify_current_page(ctx: GameContext) -> str | None:
    """截图并识别当前页面。

    尝试多次截图以应对动画或加载中的情况。

    Returns
    -------
    str | None
        当前页面名称，无法识别返回 ``None``。
    """
    ctrl = ctx.ctrl
    for attempt in range(MAX_IDENTIFY_ATTEMPTS):
        screen = ctrl.screenshot()
        page = get_current_page(screen)
        if page is not None:
            return page
        _log.debug(
            '[OPS] 页面识别失败 (第 {} 次尝试), 等待重试',
            attempt + 1,
        )
        time.sleep(IDENTIFY_INTERVAL)
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# 导航函数
# ═══════════════════════════════════════════════════════════════════════════════


def _goto_page(ctx: GameContext, target: str) -> None:
    """从当前页面导航到目标页面。

    采用逐步重规划策略 (Step-by-Step Re-planning):
    1. 识别当前页面
    2. BFS 查找路径
    3. 执行路径的第一步
    4. 循环回到 1，直到到达目标

    这允许处理不确定的导航动作 (如: build -> sidebar | main)。

    Raises
    ------
    NavigationError
        无法识别当前页面、找不到路径或步数超限。
    """
    MAX_STEPS = 20

    for step in range(MAX_STEPS):
        # 1. 识别
        current = identify_current_page(ctx)
        if current is None:
            raise NavigationError(
                f'无法识别当前页面，导航中止 (目标: {target})',
                screen=ctx.ctrl.screenshot(),
            )

        # 2. 检查
        if current == target:
            _log.info('[OPS] 已在目标页面: {}', target)
            return

        # 3. 寻路
        path = find_path(current, target)
        if path is None:
            raise NavigationError(
                f"无法找到从 '{current}' 到 '{target}' 的路径",
                screen=ctx.ctrl.screenshot(),
            )

        if not path:  # Should be covered by current == target, but safe check
            _log.info('[OPS] 已在目标页面: {}', target)
            return

        # 4. 执行一步
        edge = path[0]
        _log.debug(
            '[OPS] 步骤 {} (总限 {}): {} → {} ({})',
            step + 1,
            MAX_STEPS,
            edge.source,
            edge.target,
            edge.description,
        )
        edge.action(ctx)

    raise NavigationError(
        f'导航步数超限 ({MAX_STEPS})，目标: {target}',
        screen=ctx.ctrl.screenshot(),
    )


def goto_page(ctx: GameContext, target: str) -> None:
    """导航到目标页面，失败时自动重试一次。"""
    try:
        _goto_page(ctx, target)
    except NavigationError as e:
        _log.error('[OPS] 导航失败: {}', e)
        current_page = identify_current_page(ctx)
        _log.info('[OPS] 当前页面: {}, 执行一次重试', current_page)
        _goto_page(ctx, target)
