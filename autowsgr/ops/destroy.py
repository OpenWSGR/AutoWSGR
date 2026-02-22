"""解装舰船操作。

导航到建造页面（解体标签）并委托 UI 层执行。

``ship_types=None`` 表示不过滤舰种，全部解装；
传入舰种列表则只解装指定舰种。
"""

from __future__ import annotations

from autowsgr.emulator import AndroidController
from autowsgr.ops.navigate import goto_page
from autowsgr.types import PageName, ShipType


def destroy_ships(
    ctrl: AndroidController,
    *,
    ship_types: list[ShipType] | None = None,
    remove_equipment: bool = True,
) -> None:
    """解装舰船。

    Parameters
    ----------
    ctrl:
        设备控制器。
    ship_types:
        要解装的舰种列表。``None`` (默认) 表示不过滤，直接快速全选解装全部。
    remove_equipment:
        是否在解装前卸下装备。默认 ``True``。
    """
    from autowsgr.ui.build_page import BuildPage, BuildTab

    goto_page(ctrl, PageName.BUILD)

    page = BuildPage(ctrl)
    page.switch_tab(BuildTab.DESTROY)
    page.destroy_ships(ship_types, remove_equipment=remove_equipment)

    goto_page(ctrl, PageName.MAIN)
