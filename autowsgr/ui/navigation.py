"""UI 导航图 — 基于页面控制器函数的声明式路径查找。

每条边存储一个 **动作函数** ``action(ctrl)``，内部调用对应页面控制器的
``navigate_to`` / ``go_back`` 等方法完成导航。
坐标、重试、截图验证均由页面控制器自行处理，本模块仅描述拓扑。

Usage::

    from autowsgr.ui.navigation import find_path

    path = find_path(PageName.MAIN, PageName.BUILD)
    for edge in path:
        edge.action(ctrl)
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from autowsgr.types import PageName

if TYPE_CHECKING:
    from collections.abc import Callable

    from autowsgr.emulator import AndroidController


# ═══════════════════════════════════════════════════════════════════════════════
# 导航边
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class NavEdge:
    """导航图中的一条有向边。

    Attributes
    ----------
    source:
        出发页面。
    target:
        到达页面。
    action:
        执行导航的函数 ``(ctrl) -> None``，内部调用页面控制器方法。
    description:
        人类可读描述。
    """

    source: PageName
    target: PageName
    action: Callable[[AndroidController], None] = field(repr=False)
    description: str = ""


# ═══════════════════════════════════════════════════════════════════════════════
# 动作函数 — 延迟导入避免循环依赖
# ═══════════════════════════════════════════════════════════════════════════════


def _main_to_map(ctrl: AndroidController) -> None:
    from autowsgr.ui.main_page import MainPage, MainPageTarget
    MainPage(ctrl).navigate_to(MainPageTarget.SORTIE)


def _main_to_mission(ctrl: AndroidController) -> None:
    from autowsgr.ui.main_page import MainPage, MainPageTarget
    MainPage(ctrl).navigate_to(MainPageTarget.TASK)


def _main_to_backyard(ctrl: AndroidController) -> None:
    from autowsgr.ui.main_page import MainPage, MainPageTarget
    MainPage(ctrl).navigate_to(MainPageTarget.HOME)


def _main_to_sidebar(ctrl: AndroidController) -> None:
    from autowsgr.ui.main_page import MainPage, MainPageTarget
    MainPage(ctrl).navigate_to(MainPageTarget.SIDEBAR)


def _map_to_main(ctrl: AndroidController) -> None:
    from autowsgr.ui.map.page import MapPage
    MapPage(ctrl).go_back()


def _mission_to_main(ctrl: AndroidController) -> None:
    from autowsgr.ui.mission_page import MissionPage
    MissionPage(ctrl).go_back()


def _backyard_to_main(ctrl: AndroidController) -> None:
    from autowsgr.ui.backyard_page import BackyardPage
    BackyardPage(ctrl).go_back()


def _sidebar_to_main(ctrl: AndroidController) -> None:
    from autowsgr.ui.sidebar_page import SidebarPage
    SidebarPage(ctrl).close()


def _map_to_decisive(ctrl: AndroidController) -> None:
    from autowsgr.ui.map.page import MapPage
    MapPage(ctrl).enter_decisive()


def _battle_prep_to_map(ctrl: AndroidController) -> None:
    from autowsgr.ui.battle.preparation import BattlePreparationPage
    BattlePreparationPage(ctrl).go_back()


def _backyard_to_bath(ctrl: AndroidController) -> None:
    from autowsgr.ui.backyard_page import BackyardPage, BackyardTarget
    BackyardPage(ctrl).navigate_to(BackyardTarget.BATH)


def _backyard_to_canteen(ctrl: AndroidController) -> None:
    from autowsgr.ui.backyard_page import BackyardPage, BackyardTarget
    BackyardPage(ctrl).navigate_to(BackyardTarget.CANTEEN)


def _bath_to_backyard(ctrl: AndroidController) -> None:
    from autowsgr.ui.bath_page import BathPage
    BathPage(ctrl).go_back()


def _canteen_to_backyard(ctrl: AndroidController) -> None:
    from autowsgr.ui.canteen_page import CanteenPage
    CanteenPage(ctrl).go_back()


def _sidebar_to_build(ctrl: AndroidController) -> None:
    from autowsgr.ui.sidebar_page import SidebarPage, SidebarTarget
    SidebarPage(ctrl).navigate_to(SidebarTarget.BUILD)


def _sidebar_to_intensify(ctrl: AndroidController) -> None:
    from autowsgr.ui.sidebar_page import SidebarPage, SidebarTarget
    SidebarPage(ctrl).navigate_to(SidebarTarget.INTENSIFY)


def _sidebar_to_friend(ctrl: AndroidController) -> None:
    from autowsgr.ui.sidebar_page import SidebarPage, SidebarTarget
    SidebarPage(ctrl).navigate_to(SidebarTarget.FRIEND)


def _build_to_sidebar(ctrl: AndroidController) -> None:
    from autowsgr.ui.build_page import BuildPage
    BuildPage(ctrl).go_back()


def _intensify_to_sidebar(ctrl: AndroidController) -> None:
    from autowsgr.ui.intensify_page import IntensifyPage
    IntensifyPage(ctrl).go_back()


def _friend_to_sidebar(ctrl: AndroidController) -> None:
    from autowsgr.ui.friend_page import FriendPage
    FriendPage(ctrl).go_back()


def _decisive_to_main(ctrl: AndroidController) -> None:
    from autowsgr.ui.decisive import DecisiveBattlePage
    DecisiveBattlePage(ctrl).go_back()


# ═══════════════════════════════════════════════════════════════════════════════
# 导航图
# ═══════════════════════════════════════════════════════════════════════════════

NAV_GRAPH: list[NavEdge] = [
    # ── 主页面 ↔ 一级页面 ──
    NavEdge(PageName.MAIN, PageName.MAP, _main_to_map, "主页面 → 地图"),
    NavEdge(PageName.MAIN, PageName.MISSION, _main_to_mission, "主页面 → 任务"),
    NavEdge(PageName.MAIN, PageName.BACKYARD, _main_to_backyard, "主页面 → 后院"),
    NavEdge(PageName.MAIN, PageName.SIDEBAR, _main_to_sidebar, "主页面 → 侧边栏"),
    NavEdge(PageName.MAP, PageName.MAIN, _map_to_main, "地图 → 主页面"),
    NavEdge(PageName.MISSION, PageName.MAIN, _mission_to_main, "任务 → 主页面"),
    NavEdge(PageName.BACKYARD, PageName.MAIN, _backyard_to_main, "后院 → 主页面"),
    NavEdge(PageName.SIDEBAR, PageName.MAIN, _sidebar_to_main, "侧边栏 → 主页面"),
    # ── 地图 → 子页面 ──
    NavEdge(PageName.MAP, PageName.DECISIVE_BATTLE, _map_to_decisive, "地图 → 决战"),
    # ── 出征准备 → 地图 ──
    NavEdge(PageName.BATTLE_PREP, PageName.MAP, _battle_prep_to_map, "出征准备 → 地图"),
    # ── 后院 ↔ 子页面 ──
    NavEdge(PageName.BACKYARD, PageName.BATH, _backyard_to_bath, "后院 → 浴室"),
    NavEdge(PageName.BACKYARD, PageName.CANTEEN, _backyard_to_canteen, "后院 → 食堂"),
    NavEdge(PageName.BATH, PageName.BACKYARD, _bath_to_backyard, "浴室 → 后院"),
    NavEdge(PageName.CANTEEN, PageName.BACKYARD, _canteen_to_backyard, "食堂 → 后院"),
    # ── 侧边栏 ↔ 子页面 ──
    NavEdge(PageName.SIDEBAR, PageName.BUILD, _sidebar_to_build, "侧边栏 → 建造"),
    NavEdge(PageName.SIDEBAR, PageName.INTENSIFY, _sidebar_to_intensify, "侧边栏 → 强化"),
    NavEdge(PageName.SIDEBAR, PageName.FRIEND, _sidebar_to_friend, "侧边栏 → 好友"),
    NavEdge(PageName.BUILD, PageName.SIDEBAR, _build_to_sidebar, "建造 → 侧边栏"),
    NavEdge(PageName.INTENSIFY, PageName.SIDEBAR, _intensify_to_sidebar, "强化 → 侧边栏"),
    NavEdge(PageName.FRIEND, PageName.SIDEBAR, _friend_to_sidebar, "好友 → 侧边栏"),
    # ── 决战 → 主页面 (跨级) ──
    NavEdge(PageName.DECISIVE_BATTLE, PageName.MAIN, _decisive_to_main, "决战 → 主页面"),
]


# ═══════════════════════════════════════════════════════════════════════════════
# 路径查找
# ═══════════════════════════════════════════════════════════════════════════════

_adjacency: dict[PageName, list[NavEdge]] = {}
for _e in NAV_GRAPH:
    _adjacency.setdefault(_e.source, []).append(_e)


def find_path(source: str, target: str) -> list[NavEdge] | None:
    """BFS 查找从 *source* 到 *target* 的最短路径。

    Parameters
    ----------
    source, target:
        页面名称，可以是 :class:`PageName` 或等价字符串。

    Returns
    -------
    list[NavEdge] | None
        路径上的边列表；``source == target`` 时返回空列表；不可达返回 ``None``。
    """
    if source == target:
        return []

    visited: set[str] = {source}
    queue: deque[tuple[str, list[NavEdge]]] = deque([(source, [])])

    while queue:
        current, path = queue.popleft()
        for edge in _adjacency.get(current, []):
            if edge.target in visited:
                continue
            new_path = [*path, edge]
            if edge.target == target:
                return new_path
            visited.add(edge.target)
            queue.append((edge.target, new_path))

    return None
