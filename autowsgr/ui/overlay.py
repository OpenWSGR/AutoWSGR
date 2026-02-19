"""游戏浮层检测与消除。

游戏在页面切换过程中可能弹出浮层（公告、签到等），
这些浮层会阻塞正常的页面识别和导航。

本模块提供:

1. **浮层检测** — :func:`detect_overlay` 识别当前截图是否存在浮层
2. **浮层消除** — :func:`dismiss_overlay` 自动关闭指定浮层
3. **专用关闭** — :func:`dismiss_news` / :func:`dismiss_sign` 针对性处理

浮层类型:

- **NEWS** (新闻公告): 登录后可能出现，带有「不再显示」复选框
- **SIGN** (每日签到): 登录后可能出现签到奖励弹窗

使用方式::

    from autowsgr.ui.overlay import detect_overlay, dismiss_overlay

    screen = ctrl.screenshot()
    overlay = detect_overlay(screen)
    if overlay is not None:
        dismiss_overlay(ctrl, overlay)

.. note::
    network error 的断线重连属于游戏层 (GameOps) 的职责范围，
    不在 UI 层 overlay 模块中处理。UI 层仅处理不影响游戏运行
    但会干扰页面识别的视觉浮层。
"""

from __future__ import annotations

import enum

import numpy as np
from loguru import logger

from autowsgr.emulator.controller import AndroidController
from autowsgr.vision.matcher import (
    MatchStrategy,
    PixelChecker,
    PixelRule,
    PixelSignature,
)


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class NetworkError(Exception):
    """游戏进入断线/重连/登录界面。

    此异常由 UI 层检测并抛出，由上层 (GameOps/Scheduler) 捕获处理。
    UI 层本身不负责网络恢复逻辑。
    """


# ---------------------------------------------------------------------------
# 浮层类型
# ---------------------------------------------------------------------------


class OverlayType(enum.Enum):
    """可自动消除的游戏浮层类型。"""

    NEWS = "新闻公告"
    SIGN = "每日签到"


# ---------------------------------------------------------------------------
# 像素签名
# ---------------------------------------------------------------------------

_SIG_NEWS = PixelSignature(
    name="news_page",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.1437, 0.9065, (254, 255, 255), tolerance=30.0),
        PixelRule.of(0.9411, 0.0685, (253, 254, 255), tolerance=30.0),
        PixelRule.of(0.9016, 0.0704, (254, 255, 255), tolerance=30.0),
        PixelRule.of(0.8599, 0.0685, (254, 255, 255), tolerance=30.0),
        PixelRule.of(0.2010, 0.9046, (254, 255, 255), tolerance=30.0),
        PixelRule.of(0.8849, 0.0574, (247, 249, 248), tolerance=30.0),
    ],
)
"""新闻公告浮层签名。"""

_SIG_NOT_SHOW_NEWS = PixelSignature(
    name="not_show_news",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.0714, 0.9065, (49, 130, 211), tolerance=30.0),
        PixelRule.of(0.0620, 0.9130, (52, 130, 205), tolerance=30.0),
    ],
)
"""「不再显示」复选框已勾选态签名 (蓝色)。"""

_SIG_SIGN = PixelSignature(
    name="sign_page",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.8766, 0.3046, (216, 218, 215), tolerance=30.0),
        PixelRule.of(0.1490, 0.3000, (255, 255, 255), tolerance=30.0),
        PixelRule.of(0.1786, 0.4019, (250, 255, 255), tolerance=30.0),
        PixelRule.of(0.4432, 0.4019, (254, 255, 255), tolerance=30.0),
    ],
)
"""每日签到浮层签名。"""

# ---------------------------------------------------------------------------
# 操作坐标 (相对值 0.0–1.0，基于 960×540)
# ---------------------------------------------------------------------------

_CLICK_NEWS_NOT_SHOW: tuple[float, float] = (0.0729, 0.8981)
"""新闻「不再显示」复选框。旧代码 (70, 485) ÷ (960, 540)。"""

_CLICK_NEWS_CLOSE: tuple[float, float] = (0.0313, 0.0556)
"""新闻关闭按钮 (左上角区域)。旧代码 (30, 30) ÷ (960, 540)。"""

_CLICK_SIGN_CONFIRM: tuple[float, float] = (0.4938, 0.6611)
"""签到领取/关闭按钮。旧代码 (474, 357) ÷ (960, 540)。"""


# ---------------------------------------------------------------------------
# 检测
# ---------------------------------------------------------------------------


def detect_overlay(screen: np.ndarray) -> OverlayType | None:
    """检测截图中是否存在可消除的浮层。

    按优先级依次检测: NEWS → SIGN。

    Parameters
    ----------
    screen:
        截图 (H×W×3, RGB)。

    Returns
    -------
    OverlayType | None
        检测到的浮层类型，无浮层返回 ``None``。
    """
    if PixelChecker.check_signature(screen, _SIG_NEWS).matched:
        logger.debug("[UI] 检测到浮层: 新闻公告")
        return OverlayType.NEWS

    if PixelChecker.check_signature(screen, _SIG_SIGN).matched:
        logger.debug("[UI] 检测到浮层: 每日签到")
        return OverlayType.SIGN

    return None


# ---------------------------------------------------------------------------
# 消除 — 专用函数
# ---------------------------------------------------------------------------


def dismiss_news(ctrl: AndroidController, screen: np.ndarray | None = None) -> None:
    """关闭新闻公告浮层。

    执行流程:

    1. 检查「不再显示」复选框 — 若未勾选则点击勾选
    2. 点击关闭按钮 (左上角)

    Parameters
    ----------
    ctrl:
        Android 控制器。
    screen:
        可选截图 (用于检查复选框状态)，省略时自动截取。
    """
    if screen is None:
        screen = ctrl.screenshot()

    # 若「不再显示」未勾选，先勾选
    not_show_checked = PixelChecker.check_signature(screen, _SIG_NOT_SHOW_NEWS).matched
    if not not_show_checked:
        logger.info("[UI] 新闻公告: 勾选「不再显示」")
        ctrl.click(*_CLICK_NEWS_NOT_SHOW)
        import time
        time.sleep(0.3)

    # 关闭新闻
    logger.info("[UI] 新闻公告: 关闭")
    ctrl.click(*_CLICK_NEWS_CLOSE)


def dismiss_sign(ctrl: AndroidController) -> None:
    """关闭每日签到浮层。

    点击签到确认/领取按钮。

    Parameters
    ----------
    ctrl:
        Android 控制器。
    """
    logger.info("[UI] 每日签到: 关闭")
    ctrl.click(*_CLICK_SIGN_CONFIRM)


# ---------------------------------------------------------------------------
# 消除 — 统一分发
# ---------------------------------------------------------------------------


def dismiss_overlay(ctrl: AndroidController, overlay: OverlayType) -> None:
    """消除指定类型的浮层。

    Parameters
    ----------
    ctrl:
        Android 控制器。
    overlay:
        浮层类型。

    Raises
    ------
    ValueError
        未知的浮层类型。
    """
    match overlay:
        case OverlayType.NEWS:
            dismiss_news(ctrl)
        case OverlayType.SIGN:
            dismiss_sign(ctrl)
        case _:
            raise ValueError(f"未知浮层类型: {overlay}")
