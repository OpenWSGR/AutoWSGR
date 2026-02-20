"""食堂做菜操作。

导航到食堂页面并委托 UI 层执行做菜。
"""

from __future__ import annotations

from autowsgr.emulator import AndroidController
from autowsgr.ops.navigate import goto_page
from autowsgr.ui.canteen_page import CanteenPage


def cook(
    ctrl: AndroidController,
    *,
    position: int = 1,
    force_cook: bool = False,
) -> bool:
    """在食堂做菜。

    Parameters
    ----------
    position:
        菜谱编号 (1-3)。
    force_cook:
        当有菜正在生效时是否继续做菜。
    """
    goto_page(ctrl, "食堂页面")
    page = CanteenPage(ctrl)
    return page.cook(position, force_cook=force_cook)
