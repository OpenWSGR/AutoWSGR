"""主页面 UI 控制器。

已完成

使用方式::

    from autowsgr.ui.main_page import MainPage, MainPageTarget

    page = MainPage(ctrl)

    # 页面识别
    screen = ctrl.screenshot()
    if MainPage.is_current_page(screen):
        page.navigate_to(MainPageTarget.SORTIE)
"""

from __future__ import annotations

import enum

import numpy as np
from loguru import logger

from autowsgr.emulator import AndroidController
from autowsgr.ui.page import click_and_wait_for_page
from autowsgr.vision import (
    Color,
    MatchStrategy,
    PixelChecker,
    PixelRule,
    PixelSignature,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 枚举
# ═══════════════════════════════════════════════════════════════════════════════


class MainPageTarget(enum.Enum):
    """主页面可导航的目标。"""

    SORTIE = "出征"
    TASK = "任务"
    SIDEBAR = "侧边栏"
    HOME = "主页"


# ═══════════════════════════════════════════════════════════════════════════════
# 页面识别签名
# ═══════════════════════════════════════════════════════════════════════════════

PAGE_SIGNATURE = PixelSignature(
    name="主页面",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.6453, 0.9375, (52, 115, 168), tolerance=30.0),
        PixelRule.of(0.8126, 0.8681, (213, 206, 180), tolerance=30.0),
        PixelRule.of(0.9696, 0.8903, (121, 130, 135), tolerance=30.0),
        PixelRule.of(0.0570, 0.8847, (251, 252, 255), tolerance=30.0),
    ],
)
"""主页面像素签名 — 检测资源栏 + 角落特征。"""

EXPEDITION_READY_PROBE: tuple[float, float] = (0.9719, 0.8407)
"""远征完成探测点 — 主页面右下角远征通知。

换算自旧代码 (933, 454) ÷ (960, 540)。
远征完成时显示红色 ≈ (255, 89, 45)。
"""

_EXPEDITION_READY_COLOR = Color.of(255, 89, 45)
"""远征完成通知颜色 (RGB)。"""

_EXPEDITION_READY_TOLERANCE = 40.0
"""远征通知检测容差。"""

TASK_READY_PROBE: tuple[float, float] = (0.7229, 0.8463)
"""任务可领取探测点 — 主页面任务按钮上方。

换算自旧代码 (694, 457) ÷ (960, 540)。
有可领取任务时显示红色 ≈ (255, 89, 45)。
"""


# ═══════════════════════════════════════════════════════════════════════════════
# 导航按钮点击坐标
# ═══════════════════════════════════════════════════════════════════════════════

CLICK_NAV: dict[MainPageTarget, tuple[float, float]] = {
    MainPageTarget.SORTIE:  (0.9375, 0.8981),
    MainPageTarget.TASK:    (0.6823, 0.9037),
    MainPageTarget.SIDEBAR: (0.0490, 0.8981),
    MainPageTarget.HOME:    (0.0531, 0.1519),
}
"""4 个导航控件的点击坐标。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 页面控制器
# ═══════════════════════════════════════════════════════════════════════════════


class MainPage:
    """主页面 (母港界面) 控制器。

    **状态查询** 为 ``staticmethod``，只需截图即可调用。
    **操作动作** 为实例方法，通过注入的控制器执行。

    Parameters
    ----------
    ctrl:
        Android 设备控制器实例。
    """

    def __init__(self, ctrl: AndroidController) -> None:
        self._ctrl = ctrl

    # ── 页面识别 ──────────────────────────────────────────────────────────

    @staticmethod
    def is_current_page(screen: np.ndarray) -> bool:
        """判断截图是否为主页面。

        通过 8 个特征像素点 (资源栏 + 角落) 全部匹配判定。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。
        """
        result = PixelChecker.check_signature(screen, PAGE_SIGNATURE)
        return result.matched

    # ── 状态查询 ──────────────────────────────────────────────────────────

    @staticmethod
    def has_expedition_ready(screen: np.ndarray) -> bool:
        """检测是否有远征完成可收取。

        主页面右下角出现红色通知点时返回 ``True``。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。
        """
        x, y = EXPEDITION_READY_PROBE
        return PixelChecker.get_pixel(screen, x, y).near(
            _EXPEDITION_READY_COLOR, _EXPEDITION_READY_TOLERANCE,
        )

    @staticmethod
    def has_task_ready(screen: np.ndarray) -> bool:
        """检测是否有任务奖励可领取。

        主页面任务按钮上方出现红色通知点时返回 ``True``。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。
        """
        x, y = TASK_READY_PROBE
        return PixelChecker.get_pixel(screen, x, y).near(
            _EXPEDITION_READY_COLOR, _EXPEDITION_READY_TOLERANCE,
        )

    # ── 导航 ──────────────────────────────────────────────────────────────

    def navigate_to(self, target: MainPageTarget) -> None:
        """点击导航控件，进入指定子页面。

        点击后反复截图验证，确认已到达目标页面。
        利用导航图中的目标页面签名进行正向验证。

        Parameters
        ----------
        target:
            导航目标。

        Raises
        ------
        NavigationError
            超时未到达目标页面。
        """
        from autowsgr.ui.backyard_page import BackyardPage
        from autowsgr.ui.map.page import MapPage
        from autowsgr.ui.mission_page import MissionPage
        from autowsgr.ui.sidebar_page import SidebarPage

        target_checker = {
            MainPageTarget.SORTIE: MapPage.is_current_page,
            MainPageTarget.TASK: MissionPage.is_current_page,
            MainPageTarget.SIDEBAR: SidebarPage.is_current_page,
            MainPageTarget.HOME: BackyardPage.is_current_page,
        }
        logger.info("[UI] 主页面 → {}", target.value)
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_NAV[target],
            checker=target_checker[target],
            source="主页面",
            target=target.value,
        )

    def go_to_sortie(self) -> None:
        """点击「出征」— 进入地图选择页面。"""
        self.navigate_to(MainPageTarget.SORTIE)

    def go_to_task(self) -> None:
        """点击「任务」— 进入任务页面。"""
        self.navigate_to(MainPageTarget.TASK)

    def open_sidebar(self) -> None:
        """点击「≡」— 打开侧边栏。"""
        self.navigate_to(MainPageTarget.SIDEBAR)

    def go_home(self) -> None:
        """点击主页图标 — 进入主页页面。"""
        self.navigate_to(MainPageTarget.HOME)
