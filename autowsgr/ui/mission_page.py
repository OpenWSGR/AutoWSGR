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
    name="任务页",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.1474, 0.0509, (15, 132, 228), tolerance=30.0),
        PixelRule.of(0.2203, 0.0537, (17, 128, 220), tolerance=30.0),
        PixelRule.of(0.1818, 0.0593, (21, 129, 227), tolerance=30.0),
        PixelRule.of(0.1703, 0.0491, (249, 255, 255), tolerance=30.0),
        PixelRule.of(0.1734, 0.0370, (242, 251, 255), tolerance=30.0),
        PixelRule.of(0.1984, 0.0370, (252, 250, 251), tolerance=30.0),
        PixelRule.of(0.1693, 0.0657, (255, 255, 250), tolerance=30.0),
        PixelRule.of(0.4339, 0.0509, (140, 146, 146), tolerance=30.0),
        PixelRule.of(0.3021, 0.0537, (123, 126, 141), tolerance=30.0),
    ],
)
"""任务页面像素签名。"""


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

        通过 9 个特征像素点全部匹配判定。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。
        """
        result = PixelChecker.check_signature(screen, PAGE_SIGNATURE)
        return result.matched

    # ── 回退 ──────────────────────────────────────────────────────────────

    def go_back(self) -> None:
        """点击回退按钮 (◁)，返回主页面。

        Raises
        ------
        NavigationError
            超时仍在任务页面。
        """
        from autowsgr.ui.main_page import MainPage

        logger.info("[UI] 任务页面 → 返回主页面")
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_BACK,
            checker=MainPage.is_current_page,
            source="任务页面",
            target="主页面",
        )
