"""UI 控制层 — 页面识别与交互操作。

每个游戏页面对应一个控制器类，封装：

1. **页面识别** — 通过像素特征检测当前是否在该页面
2. **状态查询** — 读取页面内动态状态（选中标签、开关等）
3. **操作动作** — 点击按钮、切换标签等

状态查询为 ``staticmethod``，只需截图数组即可调用；
操作动作需要 :class:`~autowsgr.emulator.controller.AndroidController` 实例。

导航操作 (``go_back``、``navigate_to`` 等) 内置截图验证，
点击后反复截图确认页面已切换，超时抛出 :class:`NavigationError`。
所有导航均使用 **正向验证** (目标页面签名匹配)，不再使用离开判定。

浮层处理:
    导航过程中自动检测并消除游戏浮层 (新闻公告、每日签到)。
    浮层模块: :mod:`autowsgr.ui.overlay`

自动导航 / 兜底回主页:
    ``goto_page()``、``go_main_page()`` 等跨页面路由属于 **游戏层**
    (GameOps) 的职责，不在 UI 控制层中实现。
    UI 层只提供：页面识别、导航验证、单步操作。

页面导航树::

    主页面 (MainPage)
    ├── 地图页面 (MapPage)                  ← 出征
    │   ├── [面板] 出征/演习/远征/战役/决战
    │   └── 出征准备 (BattlePreparationPage)
    │       └── → 浴室 (BathPage)           ← 跨级快捷通道
    ├── 任务页面 (MissionPage)              ← 任务
    ├── 后院页面 (BackyardPage)             ← 主页图标
    │   ├── 浴室 (BathPage)
    │   │   └── 选择修理 (ChooseRepairPage)
    │   └── 食堂 (CanteenPage)
    └── 侧边栏 (SidebarPage)               ← ≡ 按钮
        ├── 建造 (BuildPage)
        │   └── [标签] 建造/解体/开发/废弃
        ├── 强化 (IntensifyPage)
        │   └── [标签] 强化/改修/技能
        └── 好友 (FriendPage)

页面识别注册中心::

    from autowsgr.ui import get_current_page

    screen = ctrl.screenshot()
    page_name = get_current_page(screen)  # "主页面" / "地图页面" / ...

导航路径查找::

    from autowsgr.ui.navigation import find_path

    path = find_path("主页面", "建造页面")
    for edge in path:
        ctrl.click(*edge.click)

使用方式::

    from autowsgr.ui import BattlePreparationPage, Panel

    page = BattlePreparationPage(ctrl)
    screen = ctrl.screenshot()
    if BattlePreparationPage.is_current_page(screen):
        fleet = BattlePreparationPage.get_selected_fleet(screen)
        page.start_battle()
"""

# ── 控制器 ─────────────────────────────────────────────────────────────
from autowsgr.ui.backyard_page import BackyardPage, BackyardTarget
from autowsgr.ui.bath_page import BathPage
from autowsgr.ui.battle.preparation import BattlePreparationPage, Panel
from autowsgr.ui.build_page import BuildPage, BuildTab
from autowsgr.ui.canteen_page import CanteenPage
from autowsgr.ui.choose_ship_page import ChooseShipPage
from autowsgr.ui.decisive_battle_page import DecisiveBattlePage
from autowsgr.ui.friend_page import FriendPage
from autowsgr.ui.intensify_page import IntensifyPage, IntensifyTab
from autowsgr.ui.main_page import MainPage, MainPageTarget
from autowsgr.ui.map.data import MAP_DATABASE, MapIdentity
from autowsgr.ui.map.page import MapPage
from autowsgr.ui.map.data import MapPanel
from autowsgr.ui.mission_page import MissionPage
from autowsgr.ui.sidebar_page import SidebarPage, SidebarTarget

# ── 标签页统一检测层 ──────────────────────────────────────────────
from autowsgr.ui.tabbed_page import (
    TAB_BLUE,
    TAB_PROBES,
    TabbedPageType,
    get_active_tab_index,
    identify_page_type,
    is_tabbed_page,
    make_page_checker,
    make_tab_checker,
)

# ── 浮层处理 ───────────────────────────────────────────────────────────
from autowsgr.ui.overlay import (
    NetworkError,
    OverlayType,
    detect_overlay,
    dismiss_news,
    dismiss_overlay,
    dismiss_sign,
)

# ── 导航基础设施 ───────────────────────────────────────────────────────
from autowsgr.ui.page import (
    NavConfig,
    NavigationError,
    click_and_wait_for_page,
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
register_page("侧边栏", SidebarPage.is_current_page)
register_page("任务页面", MissionPage.is_current_page)
register_page("后院页面", BackyardPage.is_current_page)
register_page("浴室页面", BathPage.is_current_page)
register_page("食堂页面", CanteenPage.is_current_page)
register_page("建造页面", BuildPage.is_current_page)
register_page("强化页面", IntensifyPage.is_current_page)
register_page("好友页面", FriendPage.is_current_page)
register_page("决战页面", DecisiveBattlePage.is_current_page)

__all__ = [
    # ── 控制器 ──
    "BackyardPage",
    "BackyardTarget",
    "BathPage",
    "BattlePreparationPage",
    "BuildPage",
    "BuildTab",
    "CanteenPage",
    "ChooseShipPage",
    "DecisiveBattlePage",
    "FriendPage",
    "IntensifyPage",
    "IntensifyTab",
    "MainPage",
    "MainPageTarget",
    "MapIdentity",
    "MapPage",
    "MapPanel",
    "MissionPage",
    "Panel",
    "SidebarPage",
    "SidebarTarget",
    # ── 标签页统一检测 ──
    "TAB_BLUE",
    "TAB_PROBES",
    "TabbedPageType",
    "get_active_tab_index",
    "identify_page_type",
    "is_tabbed_page",
    "make_page_checker",
    "make_tab_checker",
    # ── 浮层 ──
    "NetworkError",
    "OverlayType",
    "detect_overlay",
    "dismiss_news",
    "dismiss_overlay",
    "dismiss_sign",
    # ── 导航基础设施 ──
    "NavConfig",
    "NavigationError",
    "click_and_wait_for_page",
    "get_current_page",
    "get_registered_pages",
    "register_page",
    "wait_for_page",
    "wait_leave_page",
    # ── 数据 ──
    "MAP_DATABASE",
]
