"""浴室修理操作。

涉及跨页面操作: 任意页面 → 后院 → 浴室 → 选择修理 (overlay)。

选择修理是浴室页面上的一个 overlay，打开后仍识别为浴室页面。
点击某个舰船进行修理后 overlay 自动关闭。

旧代码参考: ``game_operation.repair_by_bath``
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from autowsgr.infra.logger import get_logger
from autowsgr.ops.navigate import goto_page
from autowsgr.types import PageName
from autowsgr.ui.bath_page import BathPage


if TYPE_CHECKING:
    from autowsgr.context import GameContext

_log = get_logger('ops')

# ═══════════════════════════════════════════════════════════════════════════════
# 公开函数
# ═══════════════════════════════════════════════════════════════════════════════


def repair_in_bath(ctx: GameContext) -> None:
    """使用浴室修理修理时间最长的舰船。

    流程: 导航到浴室 → 打开选择修理 overlay → 点击第一个待修理舰船
    (overlay 自动关闭)。

    旧代码参考: ``repair_by_bath(timer)``
    """
    goto_page(ctx, PageName.BATH)

    page = BathPage(ctx)
    page.go_to_choose_repair()
    page.click_repair_all()

    # 点击全部修理后 overlay 已关闭，先回到浴室页面，再返回主界面
    time.sleep(1.0)
    try:
        goto_page(ctx, PageName.MAIN)
    except Exception:
        _log.warning('[OPS] 浴室修理后返回主界面失败，可能仍在过渡动画中')
    _log.info('[OPS] 浴室修理操作完成')


def repair_ship_by_name(ctx: GameContext, ship_name: str) -> int:
    """使用浴室修理指定名称的舰船。

    Parameters
    ----------
    ctx:
        游戏上下文。
    ship_name:
        要修理的舰船名称 (中文)。

    Returns
    -------
    int
        修理时间 (秒)。若浴场已满则返回 ``-1``。
    """
    goto_page(ctx, PageName.BATH)

    page = BathPage(ctx)
    page.go_to_choose_repair()
    repair_secs = page.repair_ship(ship_name)

    if repair_secs >= 0:
        ship = ctx.get_ship(ship_name)
        ship.set_repair(repair_secs)
        _log.info('[OPS] 浴室修理操作完成: {} ({}s)', ship_name, repair_secs)
    else:
        _log.warning('[OPS] 浴场已满, 无法修理 {}', ship_name)

    return repair_secs


def repair_one_available(
    ctx: GameContext,
    *,
    blacklist: list[str] | None = None,
) -> bool:
    """有空闲修理槽时, 派修修理时间最长的非黑名单舰船 (调度入口)。

    由 ``BathRepairTrigger`` 周期调用。流程:

    1. ``ctx.bathroom`` 无空闲槽 → 直接返回 (省一次开 overlay)。
    2. 导航浴室 → 开选择修理 overlay → 修最长非黑名单船。
    3. 成功 → ``ctx.bathroom.occupy`` 记录释放时间, 返回 ``True``。
       浴场满 → ``mark_unknown`` 退避, 返回 ``False``。

    Parameters
    ----------
    ctx:
        游戏上下文。
    blacklist:
        不修理的舰船名列表 (来自 ``daily_automation.bath_repair_blacklist``)。

    Returns
    -------
    bool
        ``True`` 成功派出一艘修理; ``False`` 无空位 / 无可修船 / 浴场满。
    """
    bath = ctx.bathroom
    bath.slot_count = ctx.config.bathroom_count
    if not bath.is_available():
        _log.debug('[OPS] 浴室无空闲槽, 跳过修理')
        return False

    goto_page(ctx, PageName.BATH)
    page = BathPage(ctx)
    page.go_to_choose_repair()
    secs = page.repair_longest(blacklist=set(blacklist or []))

    if secs > 0:
        bath.occupy(secs)
        _log.info('[OPS] 浴室修理派单成功 ({}s)', secs)
        result = True
    elif secs == -2:
        # 浴场满: 状态不可靠, 标记未知下次重试
        bath.mark_unknown()
        _log.warning('[OPS] 浴场已满, 稍后重试')
        result = False
    else:
        # secs == -1: 无可修候选, 状态不变
        result = False

    time.sleep(1.0)
    try:
        goto_page(ctx, PageName.MAIN)
    except Exception:
        _log.warning('[OPS] 浴室修理后返回主界面失败')
    return result
