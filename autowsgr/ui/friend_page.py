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
from autowsgr.ui.page import wait_leave_page


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

        .. warning::
            签名暂未采集，当前始终返回 ``False``。
            TODO: 采集好友页面像素签名。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。
        """
        # TODO: 实现像素签名检测
        return False

    # ── 回退 ──────────────────────────────────────────────────────────────

    def go_back(self) -> None:
        """点击回退按钮 (◁)，返回侧边栏。"""
        logger.info("[UI] 好友 → 返回侧边栏")
        self._ctrl.click(*CLICK_BACK)
        # TODO: 签名采集后启用导航验证
