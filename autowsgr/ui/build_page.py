"""建造页面 UI 控制器。

覆盖游戏 **建造** 页面及其标签组 (建造/解体/开发/废弃) 的交互。

页面入口:
    主页面 → 侧边栏 → 建造

页面布局::

    ┌──────────────────────────────────────────────────────────────┐
    │ ◁   [建造]  解体   开发   废弃                              │
    ├──────────────────────────────────────────────────────────────┤
    │                                                              │
    │                     建造内容区域                              │
    │                                                              │
    │  空闲  │  空闲  │  空闲  │  空闲                             │
    │                                                              │
    └──────────────────────────────────────────────────────────────┘

    [ ] = 当前选中标签

标签组:
    建造/解体/开发/废弃 四个标签共享相同的顶部导航栏。
    切换标签不会离开此页面组，只是改变内容区域。

坐标体系:
    所有坐标为相对值 (0.0–1.0)。

.. note::
    页面像素签名暂未采集 (TODO)。当前仅声明拓扑关系和操作接口。

使用方式::

    from autowsgr.ui.build_page import BuildPage, BuildTab

    page = BuildPage(ctrl)
    page.switch_tab(BuildTab.DEVELOP)
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


class BuildTab(enum.Enum):
    """建造页面标签组。"""

    BUILD = "建造"
    DESTROY = "解体"
    DEVELOP = "开发"
    DISCARD = "废弃"


# ═══════════════════════════════════════════════════════════════════════════════
# 页面识别签名 — 每个标签各一组
# ═══════════════════════════════════════════════════════════════════════════════

TAB_SIGNATURES: dict[BuildTab, PixelSignature] = {
    BuildTab.BUILD: PixelSignature(
        name="建造页-建造栏",
        strategy=MatchStrategy.ALL,
        rules=[
            PixelRule.of(0.6724, 0.1278, (105, 203, 255), tolerance=30.0),
            PixelRule.of(0.7792, 0.1417, (220, 86, 87), tolerance=30.0),
            PixelRule.of(0.2250, 0.0556, (15, 124, 215), tolerance=30.0),
            PixelRule.of(0.8922, 0.1380, (51, 164, 240), tolerance=30.0),
        ],
    ),
    BuildTab.DESTROY: PixelSignature(
        name="建造页-解装栏",
        strategy=MatchStrategy.ALL,
        rules=[
            PixelRule.of(0.2708, 0.0472, (15, 132, 228), tolerance=30.0),
            PixelRule.of(0.8391, 0.9000, (29, 124, 214), tolerance=30.0),
            PixelRule.of(0.8307, 0.7778, (56, 56, 56), tolerance=30.0),
            PixelRule.of(0.8948, 0.2861, (12, 140, 227), tolerance=30.0),
            PixelRule.of(0.9396, 0.2880, (237, 237, 237), tolerance=30.0),
        ],
    ),
    BuildTab.DEVELOP: PixelSignature(
        name="建造页-开发栏",
        strategy=MatchStrategy.ALL,
        rules=[
            PixelRule.of(0.6656, 0.1278, (115, 205, 255), tolerance=30.0),
            PixelRule.of(0.7792, 0.1398, (220, 88, 86), tolerance=30.0),
            PixelRule.of(0.4802, 0.0537, (18, 125, 219), tolerance=30.0),
            PixelRule.of(0.2203, 0.0491, (20, 32, 56), tolerance=30.0),
        ],
    ),
    BuildTab.DISCARD: PixelSignature(
        name="建造页-废弃栏",
        strategy=MatchStrategy.ALL,
        rules=[
            PixelRule.of(0.5240, 0.0519, (15, 132, 228), tolerance=30.0),
            PixelRule.of(0.3484, 0.0676, (21, 37, 63), tolerance=30.0),
            PixelRule.of(0.8854, 0.1500, (25, 121, 208), tolerance=30.0),
            PixelRule.of(0.4526, 0.9741, (25, 120, 210), tolerance=30.0),
            PixelRule.of(0.7370, 0.9657, (54, 54, 54), tolerance=30.0),
            PixelRule.of(0.8495, 0.9713, (26, 121, 211), tolerance=30.0),
        ],
    ),
}
"""建造页面每个标签的像素签名。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 点击坐标
# ═══════════════════════════════════════════════════════════════════════════════

CLICK_BACK: tuple[float, float] = (0.022, 0.058)
"""回退按钮 (◁)。"""

CLICK_TAB: dict[BuildTab, tuple[float, float]] = {
    BuildTab.BUILD:   (0.1875, 0.0463),
    BuildTab.DESTROY: (0.3125, 0.0463),
    BuildTab.DEVELOP: (0.4375, 0.0463),
    BuildTab.DISCARD: (0.5625, 0.0463),
}
"""标签切换点击坐标。

.. note::
    坐标为估计值 (TODO: 待实际截图确认)。
"""


# ═══════════════════════════════════════════════════════════════════════════════
# 页面控制器
# ═══════════════════════════════════════════════════════════════════════════════


class BuildPage:
    """建造页面控制器 (含 解体/开发/废弃 标签组)。

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
        """判断截图是否为建造页面组 (含全部 4 个标签)。

        任一标签签名匹配即判定为建造页面。

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
    def get_active_tab(screen: np.ndarray) -> BuildTab | None:
        """获取当前激活的标签。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。

        Returns
        -------
        BuildTab | None
            当前标签，无法确定时返回 ``None``。
        """
        for tab, sig in TAB_SIGNATURES.items():
            if PixelChecker.check_signature(screen, sig).matched:
                return tab
        return None

    # ── 标签切换 ──────────────────────────────────────────────────────────

    def switch_tab(self, tab: BuildTab) -> None:
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
            "[UI] 建造页面: {} → {}",
            current.value if current else "未知",
            tab.value,
        )
        target_sig = TAB_SIGNATURES[tab]
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_TAB[tab],
            checker=lambda s, sig=target_sig: PixelChecker.check_signature(s, sig).matched,
            source=f"建造-{current.value if current else '?'}",
            target=f"建造-{tab.value}",
        )

    # ── 回退 ──────────────────────────────────────────────────────────────

    def go_back(self) -> None:
        """点击回退按钮 (◁)，返回侧边栏。

        Raises
        ------
        NavigationError
            超时仍在建造页面。
        """
        from autowsgr.ui.sidebar_page import SidebarPage

        logger.info("[UI] 建造页面 → 返回侧边栏")
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_BACK,
            checker=SidebarPage.is_current_page,
            source="建造页面",
            target="侧边栏",
        )
        # wait_leave_page(
        #     self._ctrl,
        #     BuildPage.is_current_page,
        #     source="建造页面",
        #     target="侧边栏",
        # )
