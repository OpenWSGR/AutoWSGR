"""任务奖励收取。

导航到任务页面并委托 UI 层收取奖励。
"""

from __future__ import annotations

from autowsgr.emulator import AndroidController
from autowsgr.ops.navigate import goto_page
from autowsgr.ui.main_page import MainPage
from autowsgr.ui.mission_page import MissionPage


def collect_rewards(ctrl: AndroidController) -> bool:
    """检查并收取任务奖励。
    
    已完成，测试通过
    """
    goto_page(ctrl, "主页面")

    screen = ctrl.screenshot()
    if not MainPage.has_task_ready(screen):
        return False

    goto_page(ctrl, "任务页面")
    page = MissionPage(ctrl)
    result = page.collect_rewards()
    goto_page(ctrl, "主页面")
    return result
