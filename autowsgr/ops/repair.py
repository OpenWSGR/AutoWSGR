"""浴室修理操作。

涉及跨页面操作: 任意页面 → 后院 → 浴室 → 选择修理 (overlay)。

选择修理是浴室页面上的一个 overlay，打开后仍识别为浴室页面。
点击某个舰船进行修理后 overlay 自动关闭。

旧代码参考: ``game_operation.repair_by_bath``
"""

from __future__ import annotations

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
    page.click_first_repair_ship()

    # 点击舰船后 overlay 自动关闭，已回到浴室页面
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
