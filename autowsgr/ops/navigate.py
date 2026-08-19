"""跨页面导航 — 从任意页面到达目标页面。

提供游戏层的核心导航能力: ``goto_page(ctx, PageName.目标)``
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from autowsgr.infra.logger import get_logger
from autowsgr.types import PageName
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


def identify_current_page(
    ctx: GameContext,
    candidates: set[str] | None = None,
) -> str | None:
    """截图并识别当前页面。

    尝试多次截图以应对动画或加载中的情况。候选集识别重试耗尽后
    追加一轮全量识别兜底 —— 栈漂移可能把真实页面排除在候选之外。

    Parameters
    ----------
    candidates:
        候选页面名集合。``None`` 时评估全部注册页;导航过程中由
        :func:`_goto_page` 从 :attr:`GameContext.ui_stack` 计算并传入,
        以收缩搜索空间。

    Returns
    -------
    str | None
        当前页面名称，无法识别返回 ``None``。
    """
    ctrl = ctx.ctrl
    for attempt in range(MAX_IDENTIFY_ATTEMPTS):
        screen = ctrl.screenshot()
        page = get_current_page(screen, candidates=candidates)
        if page is not None:
            return page
        _log.debug(
            '[OPS] 页面识别失败 (第 {} 次尝试), 等待重试',
            attempt + 1,
        )
        time.sleep(IDENTIFY_INTERVAL)

    if candidates is not None:
        # 候选耗尽:降级全量识别一轮(候选集可能因栈漂移漏掉真实页面)
        screen = ctrl.screenshot()
        page = get_current_page(screen)
        if page is not None:
            _log.warning('[OPS] 候选识别失败, 全量兜底命中: {}', page)
            return page
    return None


def _sync_ctx_page(ctx: GameContext, name: str) -> None:
    """把识别结果同步到 ``ctx.current_page`` (deprecated 字段, server 上报用)。"""
    try:
        ctx.current_page = PageName(name)
    except ValueError:
        ctx.current_page = None


# ═══════════════════════════════════════════════════════════════════════════════
# 导航函数
# ═══════════════════════════════════════════════════════════════════════════════


def _goto_page(ctx: GameContext, target: str) -> None:
    """从当前页面导航到目标页面。

    采用逐步重规划策略 (Step-by-Step Re-planning):
    1. 识别当前页面, 并用 ``ctx.ui_stack.observe`` 对账
    2. BFS 查找路径
    3. 声明意图 (``ui_stack.push``) 后执行路径的第一步
    4. 循环回到 1，直到到达目标

    这允许处理不确定的导航动作 (如: build -> sidebar | main)。

    Raises
    ------
    NavigationError
        无法识别当前页面、找不到路径或步数超限。
    """
    max_steps = 20
    stack = ctx.ui_stack
    # 候选集:首轮全表扫描(真不知在哪);每步由栈给出
    # {current} + neighbors(current) + {parent} + {target} + neighbors(target),
    # 相比纯邻域机制多纳入 parent, 覆盖回退时序与无入边叶子页 (CHOOSE_SHIP 等)。
    candidates: set[str] | None = None

    for step in range(max_steps):
        # 1. 识别 + 对账
        current = identify_current_page(ctx, candidates=candidates)
        if current is None:
            raise NavigationError(
                f'无法识别当前页面，导航中止 (目标: {target})',
                screen=ctx.ctrl.screenshot(),
            )
        stack.observe(current)
        _sync_ctx_page(ctx, current)

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

        # 4. 执行一步:先声明意图(下一轮识别的 observe 会纠正),
        #    动作失败未到达时, 识别到 parent 会被 pop 回收
        edge = path[0]
        _log.debug(
            '[OPS] 步骤 {} (总限 {}): {} → {} ({})',
            step + 1,
            max_steps,
            edge.source,
            edge.target,
            edge.description,
        )
        stack.push(edge.target)
        edge.action(ctx)
        candidates = stack.candidates(target) or None

    raise NavigationError(
        f'导航步数超限 ({max_steps})，目标: {target}',
        screen=ctx.ctrl.screenshot(),
    )


def goto_page(ctx: GameContext, target: str) -> None:
    """导航到目标页面，失败时自动重试一次。

    首次失败时先用 ``ui_stack.resync`` 全量识别重建栈 (漂移后的栈
    会把真实页面排除在候选外, 直接重试大概率再失败), 再重试导航。
    """
    try:
        _goto_page(ctx, target)
    except NavigationError as e:
        _log.error('[OPS] 导航失败: {}', e)
        resynced = ctx.ui_stack.resync(ctx.ctrl.screenshot())
        _log.info('[OPS] 栈重建 (resync): {}, 执行一次重试', resynced or '识别失败')
        current_page = identify_current_page(ctx)
        _log.info('[OPS] 当前页面: {}, 执行一次重试', current_page)
        _goto_page(ctx, target)
