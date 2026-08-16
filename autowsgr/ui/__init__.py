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
    from autowsgr.types import PageName

    path = find_path(PageName.MAIN, PageName.BUILD)
    for edge in path:
        edge.action(ctrl)

使用方式::

    from autowsgr.ui import BattlePreparationPage, Panel

    page = BattlePreparationPage(ctrl)
    screen = ctrl.screenshot()
    if BattlePreparationPage.is_current_page(screen):
        fleet = BattlePreparationPage.get_selected_fleet(screen)
        page.start_battle()
"""

# ── 控制器 ─────────────────────────────────────────────────────────────
from autowsgr.types import PageName
from autowsgr.ui.main_page.constants import OverlayKind
from autowsgr.ui.page import (
    get_current_page,
    get_registered_pages,
    register_page,
)

# ── 标签页统一检测层 ──────────────────────────────────────────────
from autowsgr.ui.tabbed_page import (
    TabbedPageType,
)
from autowsgr.ui.utils import (
    NavConfig,
    NavigationError,
    click_and_wait_for_page,
    wait_for_page,
    wait_leave_page,
)

from .backyard_page import BackyardPage, BackyardTarget
from .bath_page import BathPage
from .battle import BattlePreparationPage, Panel, RepairStrategy
from .build_page import BuildPage, BuildTab
from .canteen_page import CanteenPage
from .choose_ship_page import ChooseShipPage
from .decisive import DecisiveBattlePage, DecisiveMapController
from .event.event_page import BaseEventPage
from .friend_page import FriendPage
from .intensify_page import IntensifyPage, IntensifyTab
from .main_page import MainPage
from .map.data import MAP_DATABASE, MapIdentity, MapPanel
from .map.page import MapPage
from .mission_page import MissionInfo, MissionPage, MissionPanel
from .sidebar_page import SidebarPage, SidebarTarget


# ── 兼容别名 ─────────────────────────────────────────────────────
MainPageTarget = MainPage.Target
OverlayType = OverlayKind

# ── 注册所有页面识别器 ──


register_page(PageName.MAIN, MainPage.is_current_page)
register_page(PageName.MAP, MapPage.is_current_page)
# BATTLE_PREP 不注册: 出征准备页在游戏流转中是单向中转 (战斗结束跳过它直接回
# 准备页之前的 UI —— 演习/战役/决战/活动皆然), 不属于 UI 导航域。它是战斗
# 流程的锚点: start_fight / wait_leave_page 等直接引用
# BattlePreparationPage.is_current_page 签名 (不经过注册中心)。
# 侧边栏是左侧抽屉, 不遮挡主页面右侧识别元素 — 双命中时主页面分数更高
# (0.988 vs ~0.86), 注册为覆盖型: 命中时优先判侧边栏。否则导航会在
# "已到达侧边栏"与"当前是主页面"间震荡, 反复点切换按钮把侧边栏开了又关
# (实机 2026-08-16: 船坞满自动解装的 MAIN→SIDEBAR 死循环 → NavError)。
register_page(PageName.SIDEBAR, SidebarPage.is_current_page, overlay=True)
register_page(PageName.MISSION, MissionPage.is_current_page)
register_page(PageName.BACKYARD, BackyardPage.is_current_page)
register_page(PageName.BATH, BathPage.is_current_page)
register_page(PageName.CANTEEN, CanteenPage.is_current_page)
register_page(PageName.BUILD, BuildPage.is_current_page)
register_page(PageName.INTENSIFY, IntensifyPage.is_current_page)
register_page(PageName.FRIEND, FriendPage.is_current_page)
# EVENT_MAP 必须在 DECISIVE_BATTLE 之前注册。get_current_page 按注册顺序 first-match-wins,
# 而决战签名是 4 个深色背景像素点 (不特异), 在深色主题活动页面 (如 20260730 激斗漩涡) 上
# 会误命中 → 活动页被冒认为决战页 → 导航误判"进活动后立刻退出"。活动页改用标题图模板
# 识别 (高度特异), 排在决战前即可优先正确识别。参见 event_page._get_event_title_templates。
register_page(PageName.EVENT_MAP, BaseEventPage.is_current_page)
register_page(PageName.DECISIVE_BATTLE, DecisiveBattlePage.is_current_page)
register_page(PageName.CHOOSE_SHIP, ChooseShipPage.is_current_page)

__all__ = [
    # ── 数据 ──
    'MAP_DATABASE',
    # ── 控制器 ──
    'BackyardPage',
    'BackyardTarget',
    'BaseEventPage',
    'BathPage',
    'BattlePreparationPage',
    'BuildPage',
    'BuildTab',
    'CanteenPage',
    'ChooseShipPage',
    'DecisiveBattlePage',
    'DecisiveMapController',
    'FriendPage',
    'IntensifyPage',
    'IntensifyTab',
    'MainPage',
    'MainPageTarget',
    'MapIdentity',
    'MapPage',
    'MapPanel',
    'MissionInfo',
    'MissionPage',
    'MissionPanel',
    # ── 导航基础设施 ──
    'NavConfig',
    'NavigationError',
    # ── 浮层 ──
    'OverlayKind',
    'OverlayType',
    'Panel',
    'RepairStrategy',
    'SidebarPage',
    'SidebarTarget',
    # ── 标签页统一检测 ──
    'TabbedPageType',
    'click_and_wait_for_page',
    'get_current_page',
    'get_registered_pages',
    'register_page',
    'wait_for_page',
    'wait_leave_page',
]
