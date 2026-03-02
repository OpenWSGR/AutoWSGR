"""解装舰船操作。

导航到建造页面（解体标签）并委托 UI 层执行。

``ship_types=None`` 表示不过滤舰种，全部解装；
传入舰种列表则只解装指定舰种。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.infra.logger import get_logger
from autowsgr.ops.navigate import goto_page
from autowsgr.types import PageName, ShipType


if TYPE_CHECKING:
    from autowsgr.context import GameContext

_log = get_logger('ops')


def destroy_ships(
    ctx: GameContext,
    *,
    ship_types: list[ShipType] | None = None,
    remove_equipment: bool = True,
) -> None:
    """解装舰船。

    Parameters
    ----------
    ctx:
        游戏上下文。
    ship_types:
        要解装的舰种列表。``None`` (默认) 表示不过滤，直接快速全选解装全部。
    remove_equipment:
        是否在解装前卸下装备。默认 ``True``。
    """
    from autowsgr.ui.build_page import BuildPage, BuildTab

    _log.info('[OPS] 开始解装')
    goto_page(ctx, PageName.BUILD)

    page = BuildPage(ctx)
    page.switch_tab(BuildTab.DESTROY)
    page.destroy_ships(ship_types, remove_equipment=remove_equipment)

    goto_page(ctx, PageName.MAIN)
    _log.info('[OPS] 解装完成')
