"""食堂页面 UI 控制器。

已完成 需测试

覆盖游戏 **食堂** (料理/食堂) 页面的导航交互。

使用方式::

    from autowsgr.ui.canteen_page import CanteenPage

    page = CanteenPage(ctrl)
    page.go_back()
"""

from __future__ import annotations

import time

import numpy as np
from loguru import logger

from autowsgr.emulator import AndroidController
from autowsgr.image_resources import Templates
from autowsgr.ui.page import click_and_wait_for_page
from autowsgr.vision import (
    ImageChecker,
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

# ── 做菜弹窗坐标 ──────────────────────────────────────────────────────

CLICK_FORCE_COOK: tuple[float, float] = (0.414, 0.628)
"""「效果正在生效」弹窗中选择继续做菜按钮。

旧代码: timer.relative_click(0.414, 0.628)
"""

CLICK_CANCEL_COOK: tuple[float, float] = (0.650, 0.628)
"""「效果正在生效」弹窗中取消做菜按钮。

旧代码: timer.relative_click(0.65, 0.628)
"""

CLICK_DISMISS_POPUP: tuple[float, float] = (0.788, 0.207)
"""关闭弹窗通用按钮。

旧代码: timer.relative_click(0.788, 0.207)
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

    def confirm_force_cook(self) -> None:
        """「效果正在生效」弹窗 → 点击继续做菜。"""
        logger.info("[UI] 食堂 → 确认继续做菜 (覆盖生效中的菜)")
        self._ctrl.click(*CLICK_FORCE_COOK)

    def cancel_force_cook(self) -> None:
        """「效果正在生效」弹窗 → 取消做菜。"""
        logger.info("[UI] 食堂 → 取消做菜 (保留生效中的菜)")
        self._ctrl.click(*CLICK_CANCEL_COOK)

    def dismiss_popup(self) -> None:
        """关闭弹窗 (通用关闭按钮)。"""
        logger.info("[UI] 食堂 → 关闭弹窗")
        self._ctrl.click(*CLICK_DISMISS_POPUP)

    def click_to_skip_animation(self) -> None:
        """点击屏幕任意位置跳过动画。

        目前仅在做菜过程中使用，点击坐标为屏幕右下角。
        """
        logger.info("[UI] 食堂 → 点击跳过动画")
        self._ctrl.click(0.9, 0.9)
    # ── 组合动作 — 做菜 ──

    _COOK_BUTTON_TIMEOUT: float = 7.5

    def cook(self, position: int = 1, *, force_cook: bool = False) -> bool:
        """选择菜谱并做菜。

        必须已在食堂页面。

        Parameters
        ----------
        position:
            菜谱编号 (1–3)。
        force_cook:
            当有菜正在生效时是否继续做菜。

        Returns
        -------
        bool
            做菜是否成功。
        """
        self.select_recipe(position)

        # 等待做菜按钮出现
        deadline = time.monotonic() + self._COOK_BUTTON_TIMEOUT
        while time.monotonic() < deadline:
            screen = self._ctrl.screenshot()
            detail = ImageChecker.find_template(screen, Templates.Cook.COOK_BUTTON)
            if detail is not None:
                self._ctrl.click(*detail.center)
                break
            time.sleep(0.3)
        else:
            raise TimeoutError(f"做菜按钮未出现 ({self._COOK_BUTTON_TIMEOUT}s)")

        time.sleep(0.5)

        # 检测 "效果正在生效" 弹窗
        screen = self._ctrl.screenshot()
        if ImageChecker.template_exists(screen, Templates.Cook.HAVE_COOK):
            if force_cook:
                self.confirm_force_cook()
                time.sleep(0.5)
                screen = self._ctrl.screenshot()
                if ImageChecker.template_exists(screen, Templates.Cook.NO_TIMES):
                    self.dismiss_popup()
                    return False
            else:
                self.cancel_force_cook()
                time.sleep(0.3)
                self.dismiss_popup()
                return False

        self.click_to_skip_animation()
        logger.info("[UI] 做菜完成 (菜谱 {})", position)
    
        return True
