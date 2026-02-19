"""侧边栏页面 UI 控制器。

覆盖游戏 **侧边栏** (左下角 ≡ 菜单) 的导航交互。

页面布局::

    ┌───────────┬────────────────────────────────────────────────┐
    │  司令室    │                                                │
    │  好 友     │           (主界面内容，被侧边栏遮挡部分)         │
    │  建 造     │                                                │
    │  强 化     │                                                │
    │  战 况     │                                                │
    │  任 务     │                                                │
    │  ≡        │                                                │
    └───────────┴────────────────────────────────────────────────┘

导航目标:

- **建造** (第3项): 进入建造页面 (含 解体/开发/废弃 标签)
- **强化** (第4项): 进入强化页面 (含 改修/技能 标签)
- **好友** (第2项): 进入好友页面

坐标体系:
    所有坐标为相对值 (0.0–1.0)，由 960×540 绝对坐标换算。
    侧边栏像素签名来自 sig.py 采样数据。

使用方式::

    from autowsgr.ui.sidebar_page import SidebarPage, SidebarTarget

    page = SidebarPage(ctrl)

    # 页面识别
    screen = ctrl.screenshot()
    if SidebarPage.is_current_page(screen):
        page.navigate_to(SidebarTarget.BUILD)

    # 关闭侧边栏
    page.close()
"""

from __future__ import annotations

import enum

import numpy as np
from loguru import logger

from autowsgr.emulator.controller import AndroidController
from autowsgr.ui.page import click_and_wait_for_page
from autowsgr.vision.matcher import (
    MatchStrategy,
    PixelChecker,
    PixelRule,
    PixelSignature,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 枚举
# ═══════════════════════════════════════════════════════════════════════════════


class SidebarTarget(enum.Enum):
    """侧边栏可导航的目标。"""

    BUILD = "建造"
    INTENSIFY = "强化"
    FRIEND = "好友"


# ═══════════════════════════════════════════════════════════════════════════════
# 页面识别签名
# ═══════════════════════════════════════════════════════════════════════════════

PAGE_SIGNATURE = PixelSignature(
    name="sidebar_page",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.0406, 0.0787, (59, 59, 59), tolerance=30.0),
        PixelRule.of(0.0443, 0.2074, (51, 51, 51), tolerance=30.0),
        PixelRule.of(0.0417, 0.3426, (56, 56, 56), tolerance=30.0),
        PixelRule.of(0.0422, 0.4583, (60, 62, 61), tolerance=30.0),
        PixelRule.of(0.0417, 0.5935, (53, 53, 53), tolerance=30.0),
        PixelRule.of(0.0422, 0.7231, (59, 59, 59), tolerance=30.0),
    ],
)
"""侧边栏像素签名 — 检测左侧深色菜单栏的 6 个采样点。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 导航按钮点击坐标
# ═══════════════════════════════════════════════════════════════════════════════

CLICK_NAV: dict[SidebarTarget, tuple[float, float]] = {
    SidebarTarget.BUILD:     (0.1563, 0.3704),
    SidebarTarget.INTENSIFY: (0.1563, 0.5000),
    SidebarTarget.FRIEND:    (0.1563, 0.7593),
}
"""侧边栏菜单项点击坐标。

坐标换算: 旧代码 (150, 200) / (150, 270) / (150, 410) ÷ (960, 540)。
"""

CLICK_CLOSE: tuple[float, float] = (0.0438, 0.8963)
"""关闭侧边栏 (左下角 ≡ 同一切换按钮)。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 页面控制器
# ═══════════════════════════════════════════════════════════════════════════════


class SidebarPage:
    """侧边栏页面控制器。

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
        """判断截图是否为侧边栏页面。

        通过 6 个深色菜单栏采样点全部匹配判定。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。
        """
        result = PixelChecker.check_signature(screen, PAGE_SIGNATURE)
        return result.matched

    # ── 导航 ──────────────────────────────────────────────────────────────

    def navigate_to(self, target: SidebarTarget) -> None:
        """点击菜单项，进入指定子页面。

        利用目标页面的签名进行正向验证。

        Parameters
        ----------
        target:
            导航目标。

        Raises
        ------
        NavigationError
            超时未到达目标页面。
        """
        from autowsgr.ui.build_page import BuildPage
        from autowsgr.ui.friend_page import FriendPage
        from autowsgr.ui.intensify_page import IntensifyPage

        target_checker = {
            SidebarTarget.BUILD: BuildPage.is_current_page,
            SidebarTarget.INTENSIFY: IntensifyPage.is_current_page,
            SidebarTarget.FRIEND: FriendPage.is_current_page,
        }
        logger.info("[UI] 侧边栏 → {}", target.value)
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_NAV[target],
            checker=target_checker[target],
            source="侧边栏",
            target=target.value,
        )

    def go_to_build(self) -> None:
        """点击「建造」— 进入建造页面。"""
        self.navigate_to(SidebarTarget.BUILD)

    def go_to_intensify(self) -> None:
        """点击「强化」— 进入强化页面。"""
        self.navigate_to(SidebarTarget.INTENSIFY)

    def go_to_friend(self) -> None:
        """点击「好友」— 进入好友页面。"""
        self.navigate_to(SidebarTarget.FRIEND)

    # ── 关闭 ──────────────────────────────────────────────────────────────

    def close(self) -> None:
        """关闭侧边栏，返回主页面。

        点击后反复截图验证，确认已到达主页面。

        Raises
        ------
        NavigationError
            超时未关闭侧边栏。
        """
        from autowsgr.ui.main_page import MainPage

        logger.info("[UI] 侧边栏 → 关闭 (返回主页面)")
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_CLOSE,
            checker=MainPage.is_current_page,
            source="侧边栏",
            target="主页面",
        )
