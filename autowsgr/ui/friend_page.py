"""好友页面 UI 控制器。

覆盖游戏 **好友** 页面的导航交互。

页面入口:
    主页面 → 侧边栏 → 好友

页面布局::

    ┌──────────────────────────────────────────────────────────────┐
    │ ◁  好友                                                     │
    ├──────────────────────────────────────────────────────────────┤
    │                                                              │
    │  好友 1 — Lv.XX                         [访问]              │
    │  好友 2 — Lv.XX                         [访问]              │
    │  好友 3 — Lv.XX                         [访问]              │
    │  ...                                                        │
    │                                                              │
    └──────────────────────────────────────────────────────────────┘

坐标体系:
    所有坐标为相对值 (0.0–1.0)。

.. note::
    页面像素签名暂未采集 (TODO)。当前仅声明拓扑关系和操作接口。

使用方式::

    from autowsgr.ui.friend_page import FriendPage

    page = FriendPage(ctrl)
    page.go_back()
"""

from __future__ import annotations

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
# 页面识别签名
# ═══════════════════════════════════════════════════════════════════════════════

PAGE_SIGNATURE = PixelSignature(
    name="好友页",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.1953, 0.0444, (255, 255, 255), tolerance=30.0),
        PixelRule.of(0.1641, 0.0574, (255, 252, 243), tolerance=30.0),
        PixelRule.of(0.2094, 0.0574, (14, 131, 226), tolerance=30.0),
        PixelRule.of(0.1521, 0.0361, (15, 132, 228), tolerance=30.0),
        PixelRule.of(0.1724, 0.0389, (32, 128, 205), tolerance=30.0),
        PixelRule.of(0.1651, 0.0370, (240, 255, 255), tolerance=30.0),
    ],
)
"""好友页面像素签名。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 点击坐标
# ═══════════════════════════════════════════════════════════════════════════════

CLICK_BACK: tuple[float, float] = (0.022, 0.058)
"""回退按钮 (◁)，返回侧边栏。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 页面控制器
# ═══════════════════════════════════════════════════════════════════════════════


class FriendPage:
    """好友页面控制器。

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
        """判断截图是否为好友页面。

        通过 6 个特征像素点全部匹配判定。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。
        """
        result = PixelChecker.check_signature(screen, PAGE_SIGNATURE)
        return result.matched

    # ── 回退 ──────────────────────────────────────────────────────────────

    def go_back(self) -> None:
        """点击回退按钮 (◁)，返回侧边栏。

        Raises
        ------
        NavigationError
            超时仍在好友页面。
        """
        from autowsgr.ui.sidebar_page import SidebarPage

        logger.info("[UI] 好友 → 返回侧边栏")
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_BACK,
            checker=SidebarPage.is_current_page,
            source="好友",
            target="侧边栏",
        )
