"""强化页面 UI 控制器。

覆盖游戏 **强化** 页面及其标签组 (强化/改修/技能) 的交互。

页面入口:
    主页面 → 侧边栏 → 强化

页面布局::

    ┌──────────────────────────────────────────────────────────────┐
    │ ◁   [强化]  改修   技能                                     │
    ├──────────────────────────────────────────────────────────────┤
    │                                                              │
    │                      强化内容区域                            │
    │                                                              │
    │  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐                  │
    │  │ 素材1 │  │ 素材2 │  │ 素材3 │  │ 素材4 │                  │
    │  └──────┘  └──────┘  └──────┘  └──────┘                  │
    │                                          [ 强化 ]           │
    └──────────────────────────────────────────────────────────────┘

    [ ] = 当前选中标签

标签组:
    强化/改修/技能 三个标签共享相同的顶部导航栏。

坐标体系:
    所有坐标为相对值 (0.0–1.0)。

.. note::
    页面像素签名暂未采集 (TODO)。当前仅声明拓扑关系和操作接口。

使用方式::

    from autowsgr.ui.intensify_page import IntensifyPage, IntensifyTab

    page = IntensifyPage(ctrl)
    page.switch_tab(IntensifyTab.REMAKE)
    page.go_back()
"""

from __future__ import annotations

import enum

import numpy as np
from loguru import logger

from autowsgr.emulator.controller import AndroidController
from autowsgr.ui.page import click_and_wait_for_page, wait_for_page
from autowsgr.vision.matcher import (
    MatchStrategy,
    PixelChecker,
    PixelRule,
    PixelSignature,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 枚举
# ═══════════════════════════════════════════════════════════════════════════════


class IntensifyTab(enum.Enum):
    """强化页面标签组。"""

    INTENSIFY = "强化"
    REMAKE = "改修"
    SKILL = "技能"


# ═══════════════════════════════════════════════════════════════════════════════
# 页面识别签名 — 每个标签各一组
# ═══════════════════════════════════════════════════════════════════════════════

TAB_SIGNATURES: dict[IntensifyTab, PixelSignature] = {
    IntensifyTab.INTENSIFY: PixelSignature(
        name="强化页-强化栏",
        strategy=MatchStrategy.ALL,
        rules=[
            PixelRule.of(0.1437, 0.0491, (15, 132, 228), tolerance=30.0),
            PixelRule.of(0.8141, 0.6926, (66, 66, 66), tolerance=30.0),
            PixelRule.of(0.8161, 0.8241, (33, 142, 245), tolerance=30.0),
            PixelRule.of(0.5526, 0.0444, (27, 41, 67), tolerance=30.0),
        ],
    ),
    IntensifyTab.REMAKE: PixelSignature(
        name="强化页-改造栏",
        strategy=MatchStrategy.ALL,
        rules=[
            PixelRule.of(0.8375, 0.8343, (33, 142, 243), tolerance=30.0),
            PixelRule.of(0.4609, 0.8324, (64, 64, 64), tolerance=30.0),
            PixelRule.of(0.2698, 0.0537, (15, 132, 228), tolerance=30.0),
            PixelRule.of(0.8281, 0.3685, (182, 213, 153), tolerance=30.0),
        ],
    ),
    IntensifyTab.SKILL: PixelSignature(
        name="强化页-技能栏",
        strategy=MatchStrategy.ALL,
        rules=[
            PixelRule.of(0.4052, 0.0472, (15, 132, 228), tolerance=30.0),
            PixelRule.of(0.2687, 0.3176, (28, 156, 247), tolerance=30.0),
            PixelRule.of(0.2745, 0.4204, (29, 157, 244), tolerance=30.0),
            PixelRule.of(0.2677, 0.5454, (24, 159, 251), tolerance=30.0),
            PixelRule.of(0.4219, 0.5194, (230, 230, 230), tolerance=30.0),
        ],
    ),
}
"""强化页面每个标签的像素签名。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 点击坐标
# ═══════════════════════════════════════════════════════════════════════════════

CLICK_BACK: tuple[float, float] = (0.022, 0.058)
"""回退按钮 (◁)。"""

CLICK_TAB: dict[IntensifyTab, tuple[float, float]] = {
    IntensifyTab.INTENSIFY: (0.1875, 0.0463),
    IntensifyTab.REMAKE:    (0.3125, 0.0463),
    IntensifyTab.SKILL:     (0.4375, 0.0463),
}
"""标签切换点击坐标。

.. note::
    坐标为估计值 (TODO: 待实际截图确认)。
"""


# ═══════════════════════════════════════════════════════════════════════════════
# 页面控制器
# ═══════════════════════════════════════════════════════════════════════════════


class IntensifyPage:
    """强化页面控制器 (含 改修/技能 标签组)。

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
        """判断截图是否为强化页面组 (含全部 3 个标签)。

        任一标签签名匹配即判定为强化页面。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。
        """
        return any(
            PixelChecker.check_signature(screen, sig).matched
            for sig in TAB_SIGNATURES.values()
        )

    @staticmethod
    def get_active_tab(screen: np.ndarray) -> IntensifyTab | None:
        """获取当前激活的标签。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。

        Returns
        -------
        IntensifyTab | None
            当前标签，无法确定时返回 ``None``。
        """
        for tab, sig in TAB_SIGNATURES.items():
            if PixelChecker.check_signature(screen, sig).matched:
                return tab
        return None

    # ── 标签切换 ──────────────────────────────────────────────────────────

    def switch_tab(self, tab: IntensifyTab) -> None:
        """切换到指定标签并验证到达。

        会先截图判断当前标签状态并记录日志，然后点击目标标签，
        最后验证目标标签签名匹配。

        Parameters
        ----------
        tab:
            目标标签。

        Raises
        ------
        NavigationError
            超时未到达目标标签。
        """
        current = self.get_active_tab(self._ctrl.screenshot())
        logger.info(
            "[UI] 强化页面: {} → {}",
            current.value if current else "未知",
            tab.value,
        )
        target_sig = TAB_SIGNATURES[tab]
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_TAB[tab],
            checker=lambda s, sig=target_sig: PixelChecker.check_signature(s, sig).matched,
            source=f"强化-{current.value if current else '?'}",
            target=f"强化-{tab.value}",
        )

    # ── 回退 ──────────────────────────────────────────────────────────────

    def go_back(self) -> None:
        """点击回退按钮 (◁)，返回侧边栏。

        Raises
        ------
        NavigationError
            超时仍在强化页面。
        """
        from autowsgr.ui.sidebar_page import SidebarPage

        logger.info("[UI] 强化页面 → 返回侧边栏")
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_BACK,
            checker=SidebarPage.is_current_page,
            source="强化页面",
            target="侧边栏",
        )
