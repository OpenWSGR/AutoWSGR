"""UI 控制层 — 页面识别与交互操作。

每个游戏页面对应一个控制器类，封装：

1. **页面识别** — 通过像素特征检测当前是否在该页面
2. **状态查询** — 读取页面内动态状态（选中标签、开关等）
3. **操作动作** — 点击按钮、切换标签等

状态查询为 ``staticmethod``，只需截图数组即可调用；
操作动作需要 :class:`~autowsgr.emulator.controller.AndroidController` 实例。

导航操作 (``go_back``、``navigate_to`` 等) 内置截图验证，
点击后反复截图确认页面已切换，超时抛出 :class:`NavigationError`。

页面识别注册中心::

    from autowsgr.ui import get_current_page

    screen = ctrl.screenshot()
    page_name = get_current_page(screen)  # "主页面" / "地图页面" / ...

使用方式::

    from autowsgr.ui import BattlePreparationPage, Panel

    page = BattlePreparationPage(ctrl)
    screen = ctrl.screenshot()
    if BattlePreparationPage.is_current_page(screen):
        fleet = BattlePreparationPage.get_selected_fleet(screen)
        page.start_battle()
"""

from autowsgr.ui.battle_preparation import BattlePreparationPage, Panel
from autowsgr.ui.main_page import MainPage, MainPageTarget
from autowsgr.ui.map_page import MAP_DATABASE, MapIdentity, MapPage, MapPanel
from autowsgr.ui.page import (
    NavigationError,
    get_current_page,
    get_registered_pages,
    register_page,
    wait_for_page,
    wait_leave_page,
)

# ── 注册所有页面识别器 ──
register_page("主页面", MainPage.is_current_page)
register_page("地图页面", MapPage.is_current_page)
register_page("出征准备", BattlePreparationPage.is_current_page)

__all__ = [
    "BattlePreparationPage",
    "MainPage",
    "MainPageTarget",
    "MapIdentity",
    "MapPage",
    "MapPanel",
    "NavigationError",
    "Panel",
    "get_current_page",
    "get_registered_pages",
    "register_page",
    "wait_for_page",
    "wait_leave_page",
]
