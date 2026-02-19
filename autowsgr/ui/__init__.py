"""UI 控制层 — 页面识别与交互操作。

每个游戏页面对应一个控制器类，封装：

1. **页面识别** — 通过像素特征检测当前是否在该页面
2. **状态查询** — 读取页面内动态状态（选中标签、开关等）
3. **操作动作** — 点击按钮、切换标签等

状态查询为 ``staticmethod``，只需截图数组即可调用；
操作动作需要 :class:`~autowsgr.emulator.controller.AndroidController` 实例。

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

__all__ = [
    "BattlePreparationPage",
    "MainPage",
    "MainPageTarget",
    "MapIdentity",
    "MapPage",
    "MapPanel",
    "Panel",
]
