"""跨页面导航 — 从任意页面到达目标页面。

提供游戏层的核心导航能力: ``goto_page(ctrl, "目标页面")``
"""

from __future__ import annotations

import time

from loguru import logger

from autowsgr.emulator import AndroidController
from autowsgr.types import PageName
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
    from autowsgr.ui.battle.preparation import BattlePreparationPage
    from autowsgr.ui.build_page import BuildPage
    from autowsgr.ui.canteen_page import CanteenPage
    from autowsgr.ui.friend_page import FriendPage
    from autowsgr.ui.intensify_page import IntensifyPage
    from autowsgr.ui.main_page import MainPage
    from autowsgr.ui.map.page import MapPage
    from autowsgr.ui.mission_page import MissionPage
    from autowsgr.ui.sidebar_page import SidebarPage

    _CHECKERS = {
        PageName.MAIN: MainPage.is_current_page,
        PageName.MAP: MapPage.is_current_page,
        PageName.BATTLE_PREP: BattlePreparationPage.is_current_page,
        PageName.SIDEBAR: SidebarPage.is_current_page,
        PageName.MISSION: MissionPage.is_current_page,
        PageName.BACKYARD: BackyardPage.is_current_page,
        PageName.BATH: BathPage.is_current_page,
        PageName.CANTEEN: CanteenPage.is_current_page,
        PageName.BUILD: BuildPage.is_current_page,
        PageName.INTENSIFY: IntensifyPage.is_current_page,
        PageName.FRIEND: FriendPage.is_current_page,
    }
    return _CHECKERS.get(page_name)


# ═══════════════════════════════════════════════════════════════════════════════
# 导航函数
# ═══════════════════════════════════════════════════════════════════════════════


def _goto_page(ctrl: AndroidController, target: str) -> None:
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

def goto_page(ctrl: AndroidController, target: str) -> None:
    try:
        _goto_page(ctrl, target)
    except NavigationError as e:
        logger.error("[OPS] 导航失败: {}", e)
        current_page = identify_current_page(ctrl)
        logger.info("[OPS] 当前页面: {}, 执行一次重试", current_page)
        _goto_page(ctrl, target)