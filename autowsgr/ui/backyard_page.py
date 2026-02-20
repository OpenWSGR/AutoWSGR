"""后院页面 UI 控制器。

已完成

使用方式::

    from autowsgr.ui.backyard_page import BackyardPage, BackyardTarget

    page = BackyardPage(ctrl)
    page.go_to_bath()
    page.go_back()
"""

from __future__ import annotations

import enum

import numpy as np
from loguru import logger

from autowsgr.emulator import AndroidController
from autowsgr.ui.page import click_and_wait_for_page
from autowsgr.vision import (
    MatchStrategy,
    PixelChecker,
    PixelRule,
    PixelSignature,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 枚举
# ═══════════════════════════════════════════════════════════════════════════════


class BackyardTarget(enum.Enum):
    """后院页面可导航的目标。"""

    BATH = "浴室"
    CANTEEN = "食堂"


# ═══════════════════════════════════════════════════════════════════════════════
# 页面识别签名
# ═══════════════════════════════════════════════════════════════════════════════

PAGE_SIGNATURE = PixelSignature(
    name="后院",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.6990, 0.8389, (193, 98, 66), tolerance=30.0),
        PixelRule.of(0.2583, 0.7750, (240, 222, 146), tolerance=30.0),
        PixelRule.of(0.3344, 0.5222, (246, 119, 76), tolerance=30.0),
        PixelRule.of(0.5880, 0.2861, (255, 254, 250), tolerance=30.0),
        PixelRule.of(0.9031, 0.4380, (255, 254, 250), tolerance=30.0),
    ],
)
"""后院页面像素签名 — 检测后院背景及装饰特征。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 点击坐标
# ═══════════════════════════════════════════════════════════════════════════════

CLICK_BACK: tuple[float, float] = (0.022, 0.058)
"""回退按钮 (◁)，返回主页面。"""

CLICK_NAV: dict[BackyardTarget, tuple[float, float]] = {
    BackyardTarget.BATH:    (0.3125, 0.3704),
    BackyardTarget.CANTEEN: (0.7292, 0.7407),
}
"""导航按钮点击坐标。

坐标换算: 旧代码 (300, 200) / (700, 400) ÷ (960, 540)。
"""


# ═══════════════════════════════════════════════════════════════════════════════
# 页面控制器
# ═══════════════════════════════════════════════════════════════════════════════


class BackyardPage:
    """后院页面控制器。

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
        """判断截图是否为后院页面。

        通过 5 个特征像素点 (背景及装饰) 全部匹配判定。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。
        """
        result = PixelChecker.check_signature(screen, PAGE_SIGNATURE)
        return result.matched

    # ── 导航 ──────────────────────────────────────────────────────────────

    def navigate_to(self, target: BackyardTarget) -> None:
        """点击导航按钮，进入指定子页面。

        Parameters
        ----------
        target:
            导航目标。

        Raises
        ------
        NavigationError
            超时未到达目标页面。
        """
        from autowsgr.ui.bath_page import BathPage
        from autowsgr.ui.canteen_page import CanteenPage

        target_checker = {
            BackyardTarget.BATH: BathPage.is_current_page,
            BackyardTarget.CANTEEN: CanteenPage.is_current_page,
        }
        logger.info("[UI] 后院 → {}", target.value)
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_NAV[target],
            checker=target_checker[target],
            source="后院",
            target=target.value,
        )

    def go_to_bath(self) -> None:
        """进入浴室 (修理舰船)。"""
        self.navigate_to(BackyardTarget.BATH)

    def go_to_canteen(self) -> None:
        """进入食堂。"""
        self.navigate_to(BackyardTarget.CANTEEN)

    # ── 回退 ──────────────────────────────────────────────────────────────

    def go_back(self) -> None:
        """点击回退按钮 (◁)，返回主页面。

        Raises
        ------
        NavigationError
            超时仍在后院页面。
        """
        from autowsgr.ui.main_page import MainPage

        logger.info("[UI] 后院 → 返回主页面")
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_BACK,
            checker=MainPage.is_current_page,
            source="后院",
            target="主页面",
        )
