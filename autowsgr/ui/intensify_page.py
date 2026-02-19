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
from autowsgr.ui.page import wait_leave_page


# ═══════════════════════════════════════════════════════════════════════════════
# 枚举
# ═══════════════════════════════════════════════════════════════════════════════


class IntensifyTab(enum.Enum):
    """强化页面标签组。"""

    INTENSIFY = "强化"
    REMAKE = "改修"
    SKILL = "技能"


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

        .. warning::
            签名暂未采集，当前始终返回 ``False``。
            TODO: 采集强化页面像素签名。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。
        """
        # TODO: 实现像素签名检测
        return False

    # ── 标签切换 ──────────────────────────────────────────────────────────

    def switch_tab(self, tab: IntensifyTab) -> None:
        """切换到指定标签。

        Parameters
        ----------
        tab:
            目标标签。
        """
        logger.info("[UI] 强化页面 → {}", tab.value)
        self._ctrl.click(*CLICK_TAB[tab])

    # ── 回退 ──────────────────────────────────────────────────────────────

    def go_back(self) -> None:
        """点击回退按钮 (◁)，返回侧边栏。

        .. note::
            回退验证依赖 ``is_current_page()``，签名未采集时无法验证。
            当前实现仅执行点击。
        """
        logger.info("[UI] 强化页面 → 返回侧边栏")
        self._ctrl.click(*CLICK_BACK)
        # TODO: 签名采集后启用导航验证
        # wait_leave_page(
        #     self._ctrl,
        #     IntensifyPage.is_current_page,
        #     source="强化页面",
        #     target="侧边栏",
        # )
