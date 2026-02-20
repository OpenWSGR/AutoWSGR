"""选船页面 UI 控制器。

已完成，需测试

使用方式::

    from autowsgr.ui.choose_ship_page import ChooseShipPage

    page = ChooseShipPage(ctrl)
    page.click_search_box()
    page.click_first_result()
"""

from __future__ import annotations

import numpy as np
from loguru import logger

from autowsgr.emulator import AndroidController

from autowsgr.vision import (
    MatchStrategy,
    PixelChecker,
    PixelRule,
    PixelSignature,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 点击坐标 (960×540 基准)
# ═══════════════════════════════════════════════════════════════════════════════

CLICK_SEARCH_BOX: tuple[float, float] = (700 / 960, 30 / 540)
"""搜索框。"""

CLICK_DISMISS_KEYBOARD: tuple[float, float] = (50 / 960, 50 / 540)
"""点击空白区域关闭键盘。"""

CLICK_REMOVE_SHIP: tuple[float, float] = (83 / 960, 167 / 540)
"""「移除」按钮 — 将当前槽位舰船移除。"""

CLICK_FIRST_RESULT: tuple[float, float] = (183 / 960, 167 / 540)
"""搜索结果列表中的第一个结果。"""

PAGE_SIGNATURE = PixelSignature(
    name="舰船选择页面",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.8602, 0.9069, (27, 121, 211), tolerance=30.0),
        PixelRule.of(0.9656, 0.9083, (26, 120, 210), tolerance=30.0),
        PixelRule.of(0.8578, 0.5556, (54, 54, 54), tolerance=30.0),
        PixelRule.of(0.8594, 0.6750, (54, 54, 54), tolerance=30.0),
        PixelRule.of(0.9656, 0.5583, (54, 54, 54), tolerance=30.0),
        PixelRule.of(0.9688, 0.6833, (54, 54, 54), tolerance=30.0),
        PixelRule.of(0.6406, 0.0569, (23, 37, 64), tolerance=30.0),
    ],
)


# ═══════════════════════════════════════════════════════════════════════════════
# 页面控制器
# ═══════════════════════════════════════════════════════════════════════════════


class ChooseShipPage:
    """选船页面控制器。

    从出征准备页面点击舰船槽位后进入此页面。
    提供搜索、选择、移除舰船等原子操作。

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
        """判断截图是否为选船页面。

        .. warning::
            尚未实现像素签名采集，当前始终返回 False。
            选船页面识别由 ops 层通过图像模板匹配完成。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。
        """
        result = PixelChecker.check_signature(screen, PAGE_SIGNATURE)
        return result.matched

    # ── 操作 ──────────────────────────────────────────────────────────────

    def click_search_box(self) -> None:
        """点击搜索框，准备输入舰船名。"""
        logger.info("[UI] 选船 → 打开搜索框")
        self._ctrl.click(*CLICK_SEARCH_BOX)

    def input_ship_name(self, name: str) -> None:
        """在搜索框中输入舰船名。

        调用前应先 :meth:`click_search_box`。

        Parameters
        ----------
        name:
            舰船名 (中文)。
        """
        logger.info("[UI] 选船 → 输入舰船名 '{}'", name)
        self._ctrl.text(name)

    def dismiss_keyboard(self) -> None:
        """点击空白区域关闭软键盘。"""
        logger.info("[UI] 选船 → 关闭键盘")
        self._ctrl.click(*CLICK_DISMISS_KEYBOARD)

    def click_first_result(self) -> None:
        """点击搜索结果中的第一个舰船。"""
        logger.info("[UI] 选船 → 点击第一个结果")
        self._ctrl.click(*CLICK_FIRST_RESULT)

    def click_remove(self) -> None:
        """点击「移除」按钮，移除当前槽位的舰船。"""
        logger.info("[UI] 选船 → 移除舰船")
        self._ctrl.click(*CLICK_REMOVE_SHIP)
