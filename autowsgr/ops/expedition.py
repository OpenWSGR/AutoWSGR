"""远征操作。

检查主页面远征通知, 导航到地图页面委托 UI 层收取。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.infra.logger import get_logger
from autowsgr.ops.navigate import goto_page
from autowsgr.types import PageName
from autowsgr.ui.main_page import MainPage
from autowsgr.ui.map.data import MapPanel
from autowsgr.ui.map.page import MapPage


if TYPE_CHECKING:
    from autowsgr.context import GameContext

_log = get_logger('ops')


def collect_expedition(ctx: GameContext) -> bool:
    """收取已完成的远征。

    已完成，测试通过

    Returns
    -------
    bool
        是否执行了收取操作。
    """
    _log.info('[OPS] 开始检查远征收取')
    goto_page(ctx, PageName.MAIN)
    screen = ctx.ctrl.screenshot()
    if not MainPage.has_expedition_ready(screen):
        _log.debug('[OPS] 无远征可收取')
        return False

    goto_page(ctx, PageName.MAP)
    page = MapPage(ctx)

    screen = ctx.ctrl.screenshot()
    if not MapPage.has_expedition_notification(screen):
        goto_page(ctx, PageName.MAIN)
        return False

    page.switch_panel(MapPanel.EXPEDITION)

    collected = page.collect_expedition()

    goto_page(ctx, PageName.MAIN)
    _log.info('[OPS] 远征收取完成')
    return collected > 0
