"""远征操作。

检查主页面远征通知, 导航到地图页面委托 UI 层收取。
"""

from __future__ import annotations

from loguru import logger

from autowsgr.emulator import AndroidController
from autowsgr.ops.navigate import goto_page
from autowsgr.types import PageName
from autowsgr.ui.main_page import MainPage
from autowsgr.ui.map.page import MapPage
from autowsgr.ui.map.data import MapPanel


def collect_expedition(ctrl: AndroidController) -> bool:
    """收取已完成的远征。
    
    已完成，测试通过

    Returns
    -------
    bool
        是否执行了收取操作。
    """
    goto_page(ctrl, PageName.MAIN)
    screen = ctrl.screenshot()
    if not MainPage.has_expedition_ready(screen):
        return False

    goto_page(ctrl, PageName.MAP)
    page = MapPage(ctrl)

    screen = ctrl.screenshot()
    if not MapPage.has_expedition_notification(screen):
        goto_page(ctrl, PageName.MAIN)
        return False

    page.switch_panel(MapPanel.EXPEDITION)

    collected = page.collect_expedition()

    goto_page(ctrl, PageName.MAIN)
    return collected > 0
