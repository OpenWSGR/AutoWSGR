"""解装舰船操作。

导航到建造页面(解体标签)并委托 UI 层执行。
"""

from __future__ import annotations

from autowsgr.emulator import AndroidController
from autowsgr.ops.navigate import goto_page
from autowsgr.types import PageName


def destroy_ships(
    ctrl: AndroidController,
    *,
    remove_equipment: bool = True,
) -> None:
    """解装舰船。"""
    from autowsgr.ui.build_page import BuildPage, BuildTab

    goto_page(ctrl, PageName.BUILD)

    page = BuildPage(ctrl)
    page.switch_tab(BuildTab.DESTROY)
    page.destroy_all(remove_equipment=remove_equipment)

    goto_page(ctrl, PageName.MAIN)
