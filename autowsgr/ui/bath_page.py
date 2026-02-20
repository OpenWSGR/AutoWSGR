"""浴室页面 UI 控制器。

覆盖游戏 **浴室** (修理舰船) 页面的导航交互。

页面入口:
    - 主页面 → 后院 → 浴室
    - 出征准备 → 右上角 🔧 → 浴室 (跨级快捷通道)

页面布局::

    ┌──────────────────────────────────────────────────────────────┐
    │ ◁  浴室                                       [选择修理] ⊕ │
    ├──────────────────────────────────────────────────────────────┤
    │                                                              │
    │  修理位 1:  ■■■■□□  修理中  剩余 03:42                     │
    │  修理位 2:  空闲                                            │
    │  修理位 3:  空闲                                            │
    │  修理位 4:  空闲        (可能需要扩建)                       │
    │                                                              │
    └──────────────────────────────────────────────────────────────┘

导航目标:

- **选择修理**: 右上角按钮，进入选择要修理的舰船

跨级通道:

- 从出征准备页面可直接进入浴室 (旧代码的 cross-edge)
- 浴室可直接返回主页面 (跨级跳过后院)

坐标体系:
    所有坐标为相对值 (0.0–1.0)，由 960×540 绝对坐标换算。

.. note::
    页面像素签名暂未采集 (TODO)。当前仅声明拓扑关系和操作接口。

使用方式::

    from autowsgr.ui.bath_page import BathPage

    page = BathPage(ctrl)
    page.go_to_choose_repair()
    page.go_back()
"""

from __future__ import annotations

import numpy as np
from loguru import logger

from autowsgr.emulator import AndroidController
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
    name="浴场页",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.8458, 0.1102, (74, 132, 178), tolerance=30.0),
        PixelRule.of(0.8604, 0.0889, (253, 254, 255), tolerance=30.0),
        PixelRule.of(0.8734, 0.0454, (52, 146, 198), tolerance=30.0),
        PixelRule.of(0.9875, 0.1019, (69, 133, 181), tolerance=30.0),
    ],
)
"""浴室页面像素签名。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 点击坐标
# ═══════════════════════════════════════════════════════════════════════════════

CLICK_BACK: tuple[float, float] = (0.022, 0.058)
"""回退按钮 (◁)。

.. note::
    回退目标取决于入口路径:
    - 从后院进入 → 返回后院
    - 从出征准备跨级进入 → 返回主页面 (旧代码行为)
    当前实现统一使用 ◁ 按钮。
"""

CLICK_CHOOSE_REPAIR: tuple[float, float] = (0.9375, 0.0556)
"""选择修理按钮 (右上角)。

坐标换算: 旧代码 (900, 30) ÷ (960, 540)。
"""

CLICK_FIRST_REPAIR_SHIP: tuple[float, float] = (0.1198, 0.4315)
"""选择修理页面中第一个舰船的位置。

旧代码: timer.click(115, 233) → (115/960, 233/540)。
"""


# ═══════════════════════════════════════════════════════════════════════════════
# 页面控制器
# ═══════════════════════════════════════════════════════════════════════════════


class BathPage:
    """浴室页面控制器。

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
        """判断截图是否为浴室页面。

        通过 4 个特征像素点全部匹配判定。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。
        """
        result = PixelChecker.check_signature(screen, PAGE_SIGNATURE)
        return result.matched

    # ── 导航 ──────────────────────────────────────────────────────────────

    def go_to_choose_repair(self) -> None:
        """点击右上角按钮，进入选择修理。

        Raises
        ------
        NavigationError
            超时仍在浴室页面。
        """
        logger.info("[UI] 浴室 → 选择修理")
        # 选择修理页面暂无签名，使用 leave 降级
        from autowsgr.ui.page import wait_leave_page

        self._ctrl.click(*CLICK_CHOOSE_REPAIR)
        wait_leave_page(
            self._ctrl,
            BathPage.is_current_page,
            source="浴室",
            target="选择修理",
        )

    # ── 回退 ──────────────────────────────────────────────────────────────

    def go_back(self) -> None:
        """点击回退按钮 (◁)。

        回退目标取决于入口路径:

        - 从后院进入 → 返回后院
        - 从出征准备跨级进入 → 可能返回主页面

        使用后院签名验证。若返回主页面也能通过 (已离开浴室) 判定。

        Raises
        ------
        NavigationError
            超时仍在浴室页面。
        """
        from autowsgr.ui.page import wait_leave_page

        logger.info("[UI] 浴室 → 返回")
        self._ctrl.click(*CLICK_BACK)
        wait_leave_page(
            self._ctrl,
            BathPage.is_current_page,
            source="浴室",
            target="后院/主页面",
        )

    # ── 选择修理子页面操作 ────────────────────────────────────────────────

    def click_first_repair_ship(self) -> None:
        """选择修理页面 → 点击第一个舰船 (修理时间最长的排在首位)。"""
        logger.info("[UI] 浴室 (选择修理) → 点击第一个舰船")
        self._ctrl.click(*CLICK_FIRST_REPAIR_SHIP)
