"""任务页面 UI 控制器。

覆盖游戏 **任务** 页面的导航交互。

页面入口:
    主页面 → 点击「任务」

页面布局::

    ┌──────────────────────────────────────────────────────────────┐
    │ ◁  任务                                                     │
    ├──────────────────────────────────────────────────────────────┤
    │                                                              │
    │  ☑ 出击任务 1 — 完成第一章      [领取]                       │
    │  ☐ 出击任务 2 — 完成第二章                                   │
    │  ☑ 日常任务   — 出击 3 次       [领取]                       │
    │  ☐ 周常任务   — 出击 15 次                                   │
    │  ...                                                        │
    │                                                              │
    └──────────────────────────────────────────────────────────────┘

坐标体系:
    所有坐标为相对值 (0.0–1.0)。

.. note::
    页面像素签名暂未采集 (TODO)。当前仅声明拓扑关系和操作接口。

使用方式::

    from autowsgr.ui.mission_page import MissionPage

    page = MissionPage(ctrl)
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
"""回退按钮 (◁)。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 页面控制器
# ═══════════════════════════════════════════════════════════════════════════════


class MissionPage:
    """任务页面控制器。

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
        """判断截图是否为任务页面。

        .. warning::
            签名暂未采集，当前始终返回 ``False``。
            TODO: 采集任务页面像素签名。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。
        """
        # TODO: 实现像素签名检测
        return False

    # ── 回退 ──────────────────────────────────────────────────────────────

    def go_back(self) -> None:
        """点击回退按钮 (◁)，返回主页面。

        .. note::
            回退验证依赖 ``is_current_page()``，签名未采集时无法验证。
            当前实现仅执行点击。
        """
        logger.info("[UI] 任务页面 → 返回主页面")
        self._ctrl.click(*CLICK_BACK)
        # TODO: 签名采集后启用导航验证
        # wait_leave_page(
        #     self._ctrl,
        #     MissionPage.is_current_page,
        #     source="任务页面",
        #     target="主页面",
        # )
