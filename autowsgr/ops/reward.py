"""任务奖励收取。

导航到任务页面并委托 UI 层收取奖励。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.infra.logger import get_logger
from autowsgr.ops.navigate import goto_page
from autowsgr.types import PageName
from autowsgr.ui.main_page import MainPage
from autowsgr.ui.mission_page import MissionPage


if TYPE_CHECKING:
    from autowsgr.context import GameContext

_log = get_logger('ops')


def collect_rewards(ctx: GameContext) -> bool:
    """检查并收取任务奖励。

    已完成，测试通过
    """
    _log.info('[OPS] 检查任务奖励')
    goto_page(ctx, PageName.MAIN)

    screen = ctx.ctrl.screenshot()
    if not MainPage.has_task_ready(screen):
        return False

    goto_page(ctx, PageName.MISSION)
    page = MissionPage(ctx)
    result = page.collect_rewards()
    goto_page(ctx, PageName.MAIN)
    _log.info('[OPS] 任务奖励收取完成')
    return result
