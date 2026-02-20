"""强化页面 UI 控制器。

已完成

页面入口:
    主页面 → 侧边栏 → 强化

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

from autowsgr.emulator import AndroidController
from autowsgr.ui.page import click_and_wait_for_page, wait_for_page
from autowsgr.ui.tabbed_page import (
    TabbedPageType,
    get_active_tab_index,
    identify_page_type,
    make_tab_checker,
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
# 标签索引映射
# ═══════════════════════════════════════════════════════════════════════════════

_TAB_LIST: list[IntensifyTab] = list(IntensifyTab)
"""标签枚举值列表 — 索引与标签栏探测位置一一对应。"""

_TAB_TO_INDEX: dict[IntensifyTab, int] = {
    tab: i for i, tab in enumerate(_TAB_LIST)
}
"""标签 → 标签索引映射。"""


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

        通过统一标签页检测层识别。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。
        """
        return identify_page_type(screen) == TabbedPageType.INTENSIFY

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
            当前标签，索引越界或无法确定时返回 ``None``。
        """
        idx = get_active_tab_index(screen)
        if idx is None or idx >= len(_TAB_LIST):
            return None
        return _TAB_LIST[idx]

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
        target_idx = _TAB_TO_INDEX[tab]
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_TAB[tab],
            checker=make_tab_checker(TabbedPageType.INTENSIFY, target_idx),
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
