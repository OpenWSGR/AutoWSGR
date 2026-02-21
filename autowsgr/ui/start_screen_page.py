"""游戏「点击进入」启动画面 UI 控制器。

游戏冷启动后、进入主流程前会停在此画面，需要点击右下角按钮才能继续。

使用方式::

    from autowsgr.ui.start_screen_page import StartScreenPage

    screen = ctrl.screenshot()
    if StartScreenPage.is_current_page(screen):
        StartScreenPage(ctrl).click_enter()
        # 之后开始检测登录浮层
"""

from __future__ import annotations

import time

import numpy as np
from loguru import logger

from autowsgr.emulator import AndroidController
from autowsgr.vision import MatchStrategy, PixelChecker, PixelRule, PixelSignature


# ═══════════════════════════════════════════════════════════════════════════════
# 页面识别签名
# ═══════════════════════════════════════════════════════════════════════════════

PAGE_SIGNATURE = PixelSignature(
    name="启动画面",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.0508, 0.8722, (204, 210, 208), tolerance=30.0),
        PixelRule.of(0.8125, 0.8569, (224, 183, 41), tolerance=30.0),
        PixelRule.of(0.8695, 0.9028, (222, 198, 40), tolerance=30.0),
        PixelRule.of(0.9641, 0.8681, (222, 197, 43), tolerance=30.0),
        PixelRule.of(0.7914, 0.7333, (237, 237, 237), tolerance=30.0),
    ],
)
"""启动画面像素签名 — 底部横幅暖黄色调特征。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════════════════════════════════════

#: 「点击进入」按钮坐标（右下角）
CLICK_ENTER: tuple[float, float] = (0.9, 0.85)

#: 点击后等待画面稳定的时间（秒）
_CLICK_SETTLE: float = 2.0


# ═══════════════════════════════════════════════════════════════════════════════
# 页面控制器
# ═══════════════════════════════════════════════════════════════════════════════


class StartScreenPage:
    """游戏「点击进入」启动画面控制器。

    **状态查询** 为 ``staticmethod``，只需截图即可调用。
    **操作动作** 为实例方法，通过注入的控制器执行。

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
        """判断截图是否为启动画面。

        通过底部横幅暖黄色调像素签名匹配判定。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。
        """
        return PixelChecker.check_signature(screen, PAGE_SIGNATURE).matched

    # ── 操作动作 ──────────────────────────────────────────────────────────

    def click_enter(self) -> None:
        """点击右下角「点击进入」按钮，进入游戏主流程。

        点击坐标为 :data:`CLICK_ENTER` ``(0.9, 0.85)``，点击后等待
        :data:`_CLICK_SETTLE` 秒让画面稳定，之后可开始检测登录浮层。
        """
        logger.info("[StartScreen] 点击「点击进入」按钮 {}", CLICK_ENTER)
        self._ctrl.click(*CLICK_ENTER)
        time.sleep(_CLICK_SETTLE)
