"""跨页面导航 — 从任意页面到达目标页面。

本模块提供游戏层的核心导航能力:

1. **goto_page** — 从当前页面导航到目标页面（利用导航图 BFS）

.. deprecated::
    ``go_main_page`` 已弃用，统一改用 ``goto_page(ctrl, "主页面")``。
    函数暂时保留以兼容旧调用方，后续将删除。

这些函数属于 GameOps 层，因为它们跨越多个 UIController，
需要识别当前页面、规划路径、逐步执行导航。

Usage::

    from autowsgr.ops.navigate import goto_page

    # 从当前页面导航到建造页面
    goto_page(ctrl, "建造页面")

    # 回到主页面
    goto_page(ctrl, "主页面")
"""

from __future__ import annotations

import time

from loguru import logger

from autowsgr.emulator.controller import AndroidController
from autowsgr.ui.navigation import find_path
from autowsgr.ui.page import (
    NavigationError,
    click_and_wait_for_page,
    get_current_page,
    get_registered_pages,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════════════════════════════════════

MAX_IDENTIFY_ATTEMPTS: int = 5
"""页面识别最大尝试次数。"""

IDENTIFY_INTERVAL: float = 1.0
"""页面识别重试间隔 (秒)。"""

BACK_BUTTON: tuple[float, float] = (0.022, 0.058)
"""通用左上角回退按钮坐标。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 页面识别
# ═══════════════════════════════════════════════════════════════════════════════


def identify_current_page(ctrl: AndroidController) -> str | None:
    """截图并识别当前页面。

    尝试多次截图以应对动画或加载中的情况。

    Parameters
    ----------
    ctrl:
        Android 设备控制器实例。

    Returns
    -------
    str | None
        当前页面名称，无法识别返回 ``None``。
    """
    for attempt in range(MAX_IDENTIFY_ATTEMPTS):
        screen = ctrl.screenshot()
        page = get_current_page(screen)
        if page is not None:
            return page
        logger.debug(
            "[OPS] 页面识别失败 (第 {} 次尝试), 等待重试",
            attempt + 1,
        )
        time.sleep(IDENTIFY_INTERVAL)
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# 页面 checker 映射
# ═══════════════════════════════════════════════════════════════════════════════


def _get_page_checker(page_name: str):
    """获取指定页面的 is_current_page 检测器。

    通过延迟导入避免循环依赖。
    """
    from autowsgr.ui.backyard_page import BackyardPage
    from autowsgr.ui.bath_page import BathPage
    from autowsgr.ui.battle_preparation import BattlePreparationPage
    from autowsgr.ui.build_page import BuildPage
    from autowsgr.ui.canteen_page import CanteenPage
    from autowsgr.ui.friend_page import FriendPage
    from autowsgr.ui.intensify_page import IntensifyPage
    from autowsgr.ui.main_page import MainPage
    from autowsgr.ui.map_page import MapPage
    from autowsgr.ui.mission_page import MissionPage
    from autowsgr.ui.sidebar_page import SidebarPage

    _CHECKERS = {
        "主页面": MainPage.is_current_page,
        "地图页面": MapPage.is_current_page,
        "出征准备": BattlePreparationPage.is_current_page,
        "侧边栏": SidebarPage.is_current_page,
        "任务页面": MissionPage.is_current_page,
        "后院页面": BackyardPage.is_current_page,
        "浴室页面": BathPage.is_current_page,
        "食堂页面": CanteenPage.is_current_page,
        "建造页面": BuildPage.is_current_page,
        "强化页面": IntensifyPage.is_current_page,
        "好友页面": FriendPage.is_current_page,
    }
    return _CHECKERS.get(page_name)


# ═══════════════════════════════════════════════════════════════════════════════
# 导航函数
# ═══════════════════════════════════════════════════════════════════════════════


def goto_page(ctrl: AndroidController, target: str) -> None:
    """从当前页面导航到目标页面。

    利用导航图 BFS 查找最短路径，逐步执行:

    1. 识别当前页面
    2. BFS 查找路径
    3. 逐边执行: 点击 + 等待到达

    Parameters
    ----------
    ctrl:
        Android 设备控制器实例。
    target:
        目标页面名称 (如 ``"主页面"``、``"建造页面"``)。

    Raises
    ------
    NavigationError
        无法识别当前页面、找不到路径、或导航过程中超时。
    """
    # 1. 识别当前页面
    current = identify_current_page(ctrl)
    if current is None:
        raise NavigationError(
            f"无法识别当前页面，无法导航到 '{target}'"
        )

    if current == target:
        logger.info("[OPS] 已在目标页面: {}", target)
        return

    # 2. BFS 查找路径
    path = find_path(current, target)
    if path is None:
        raise NavigationError(
            f"无法找到从 '{current}' 到 '{target}' 的路径"
        )

    logger.info(
        "[OPS] 导航: {} → {} (共 {} 步)",
        current, target, len(path),
    )

    # 3. 逐边执行
    for i, edge in enumerate(path):
        checker = _get_page_checker(edge.target)
        if checker is None:
            raise NavigationError(
                f"目标页面 '{edge.target}' 无识别器"
            )
        logger.info(
            "[OPS]   步骤 {}/{}: {} → {} (点击 {:.3f}, {:.3f})",
            i + 1, len(path), edge.source, edge.target,
            edge.click[0], edge.click[1],
        )
        click_and_wait_for_page(
            ctrl,
            click_coord=edge.click,
            checker=checker,
            source=edge.source,
            target=edge.target,
        )

    logger.info("[OPS] 已到达: {}", target)


def go_main_page(ctrl: AndroidController) -> None:  # noqa: D401
    """**[已弃用]** 从任意页面回到主页面。

    .. deprecated::
        请改用 ``goto_page(ctrl, "主页面")``。
        本函数保留仅供过渡期兼容，后续将删除。

    内部先尝试 ``goto_page``；若失败，退化为反复点击左上角回退按钮。

    Parameters
    ----------
    ctrl:
        Android 设备控制器实例。

    Raises
    ------
    NavigationError
        回退多次后仍未到达主页面。
    """
    from autowsgr.ui.main_page import MainPage

    # 快速检查
    screen = ctrl.screenshot()
    if MainPage.is_current_page(screen):
        logger.info("[OPS] 已在主页面")
        return

    # 尝试智能导航
    goto_page(ctrl, "主页面")
        
