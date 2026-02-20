"""食堂页面 UI 控制器。

覆盖游戏 **食堂** (料理/食堂) 页面的导航交互。

页面入口:
    主页面 → 后院 → 食堂

页面布局::

    ┌──────────────────────────────────────────────────────────────┐
    │ ◁  食堂                                                     │
    ├──────────────────────────────────────────────────────────────┤
    │                                                              │
    │  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐                  │
    │  │ 菜品1 │  │ 菜品2 │  │ 菜品3 │  │ 菜品4 │                  │
    │  └──────┘  └──────┘  └──────┘  └──────┘                  │
    │                                                              │
    │                                        [ 料理 ]             │
    └──────────────────────────────────────────────────────────────┘

跨级通道:

- 旧代码中食堂可直接返回主页面 (跨级跳过后院)

坐标体系:
    所有坐标为相对值 (0.0–1.0)。

.. note::
    页面像素签名暂未采集 (TODO)。当前仅声明拓扑关系和操作接口。

使用方式::

    from autowsgr.ui.canteen_page import CanteenPage

    page = CanteenPage(ctrl)
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
    name="餐厅页",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.7667, 0.0454, (27, 134, 228), tolerance=30.0),
        PixelRule.of(0.8734, 0.1611, (29, 119, 205), tolerance=30.0),
        PixelRule.of(0.8745, 0.2750, (29, 115, 198), tolerance=30.0),
        PixelRule.of(0.8734, 0.3806, (27, 116, 198), tolerance=30.0),
        PixelRule.of(0.7734, 0.0602, (254, 255, 255), tolerance=30.0),
    ],
)
"""食堂页面像素签名 (来自 sig.py 重新采集)。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 点击坐标
# ═══════════════════════════════════════════════════════════════════════════════

CLICK_BACK: tuple[float, float] = (0.022, 0.058)
"""回退按钮 (◁)，返回后院。

.. note::
    旧代码中食堂 ◁ 按钮可能直接返回主页面 (跨级)，
    具体行为待实际确认。
"""

CLICK_RECIPE: dict[int, tuple[float, float]] = {
    1: (0.3313, 0.5111),
    2: (0.4375, 0.2593),
    3: (0.5792, 0.4019),
}
"""菜谱点击坐标 (1–3)。

换算自旧代码: (318, 276), (420, 140), (556, 217) ÷ (960, 540)。
"""


# ═══════════════════════════════════════════════════════════════════════════════
# 页面控制器
# ═══════════════════════════════════════════════════════════════════════════════


class CanteenPage:
    """食堂页面控制器。

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
        """判断截图是否为食堂页面。

        通过 5 个特征像素点全部匹配判定。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。
        """
        result = PixelChecker.check_signature(screen, PAGE_SIGNATURE)
        return result.matched

    # ── 回退 ──────────────────────────────────────────────────────────────

    def go_back(self) -> None:
        """点击回退按钮 (◁)，返回后院。

        Raises
        ------
        NavigationError
            超时仍在食堂页面。
        """
        from autowsgr.ui.backyard_page import BackyardPage

        logger.info("[UI] 食堂 → 返回后院")
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_BACK,
            checker=BackyardPage.is_current_page,
            source="食堂",
            target="后院",
        )

    # ── 操作 ──────────────────────────────────────────────────────────────

    def select_recipe(self, position: int) -> None:
        """点击选择菜谱。

        Parameters
        ----------
        position:
            菜谱编号 (1–3)。

        Raises
        ------
        ValueError
            编号不在 1–3 范围内。
        """
        if position not in CLICK_RECIPE:
            raise ValueError(f"菜谱编号必须为 1–3，收到: {position}")
        logger.info("[UI] 食堂 → 选择菜谱 {}", position)
        self._ctrl.click(*CLICK_RECIPE[position])
