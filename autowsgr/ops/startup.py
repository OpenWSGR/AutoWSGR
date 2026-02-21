"""游戏启动与初始化操作。

提供从零开始到稳定运行于主页面的完整启动流程：

1. 检测游戏是否在前台运行
2. 冷启动游戏并等待加载完成
3. 关闭登录后弹出的浮层（新闻公告、每日签到）
4. 导航到主页面

主要入口::

    from autowsgr.ops.startup import ensure_game_ready
    from autowsgr.types import GameAPP

    # 确保游戏已启动并位于主页面
    ensure_game_ready(ctrl, GameAPP.official)

旧代码参考:
    ``autowsgr_legacy/timer/timer.py`` — ``init`` / ``start_game`` / ``go_main_page``
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from loguru import logger

from autowsgr.ops.navigate import goto_page
from autowsgr.types import GameAPP, PageName
from autowsgr.ui.main_page import MainPage
from autowsgr.ui.overlay import OverlayType, detect_overlay, dismiss_overlay
from autowsgr.vision import MatchStrategy, PixelChecker, PixelRule, PixelSignature

if TYPE_CHECKING:
    from autowsgr.emulator import AndroidController


# ═══════════════════════════════════════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════════════════════════════════════

_GAME_PACKAGE_OFFICIAL = GameAPP.official.package_name
"""官服包名，作为默认值使用。"""

_STARTUP_TIMEOUT: float = 120.0
"""等待游戏加载完成的最大时间 (秒)。"""

_STARTUP_POLL_INTERVAL: float = 1.0
"""加载等待轮询间隔 (秒)。"""

_OVERLAY_DISMISS_TIMEOUT: float = 10.0
"""等待浮层出现并消除的超时 (秒)。"""

_OVERLAY_DISMISS_DELAY: float = 1.0
"""消除浮层后的等待时间 (秒)。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 启动画面签名
# ═══════════════════════════════════════════════════════════════════════════════

# 游戏加载完成后会出现「点击进入」画面，特征为底部横幅区域偏暖黄色调。
# TODO 这个特征不对

SIG_START_SCREEN = PixelSignature(
    name="game_start_screen",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.7531, 0.5403, (237, 223, 101), tolerance=30.0),
        PixelRule.of(0.7539, 0.5514, (236, 220, 107), tolerance=30.0),
        PixelRule.of(0.8320, 0.5444, (244, 232, 114), tolerance=30.0),
        PixelRule.of(0.8320, 0.5528, (245, 230, 113), tolerance=30.0),
        PixelRule.of(0.7828, 0.5403, (241, 215, 96), tolerance=30.0),
        PixelRule.of(0.7844, 0.5556, (239, 227, 119), tolerance=30.0),
        PixelRule.of(0.8016, 0.5403, (243, 230, 115), tolerance=30.0),
        PixelRule.of(0.8039, 0.5556, (237, 229, 122), tolerance=30.0),
        PixelRule.of(0.8195, 0.5389, (244, 231, 116), tolerance=30.0),
        PixelRule.of(0.8219, 0.5528, (239, 222, 108), tolerance=30.0),
        PixelRule.of(0.7719, 0.5403, (239, 219, 98), tolerance=30.0),
        PixelRule.of(0.7719, 0.5500, (236, 222, 100), tolerance=30.0),
    ],
)
"""游戏「点击进入」启动画面像素签名。

#: 「点击进入」画面点击目标（屏幕中央）
_CLICK_START_SCREEN: tuple[float, float] = (0.5, 0.5)


# ═══════════════════════════════════════════════════════════════════════════════
# 游戏状态检测
# ═══════════════════════════════════════════════════════════════════════════════


def is_game_running(ctrl: AndroidController, package: str = _GAME_PACKAGE_OFFICIAL) -> bool:
    """检查游戏是否在前台运行。

    Parameters
    ----------
    ctrl:
        Android 设备控制器。
    package:
        游戏包名，默认为官服 ``com.huanmeng.zhanjian2``。

    Returns
    -------
    bool
        ``True`` 表示游戏进程存在（但不保证处于可操作的页面状态）。
    """
    running = ctrl.is_app_running(package)
    logger.debug("[Startup] 游戏运行状态: {}", "运行中" if running else "未运行")
    return running


def is_on_main_page(ctrl: AndroidController) -> bool:
    """截图并检测当前是否在主页面。

    Parameters
    ----------
    ctrl:
        Android 设备控制器。

    Returns
    -------
    bool
        ``True`` 表示当前在主页面。
    """
    screen = ctrl.screenshot()
    result = MainPage.is_current_page(screen)
    logger.debug("[Startup] 主页面检测: {}", "是" if result else "否")
    return result


def is_on_start_screen(ctrl: AndroidController) -> bool:
    """截图并检测当前是否在游戏「点击进入」启动画面。

    .. note::
        依赖 :data:`SIG_START_SCREEN` 签名，需先校准。

    Parameters
    ----------
    ctrl:
        Android 设备控制器。

    Returns
    -------
    bool
        ``True`` 表示当前在启动画面。
    """
    screen = ctrl.screenshot()
    return PixelChecker.check_signature(screen, SIG_START_SCREEN).matched


# ═══════════════════════════════════════════════════════════════════════════════
# 浮层处理
# ═══════════════════════════════════════════════════════════════════════════════


def dismiss_login_overlays(
    ctrl: AndroidController,
    *,
    timeout: float = _OVERLAY_DISMISS_TIMEOUT,
    delay: float = _OVERLAY_DISMISS_DELAY,
) -> None:
    """消除游戏登录后弹出的浮层（新闻公告、每日签到）。

    轮询截图，发现浮层即消除，直到连续两次截图均无浮层为止。

    Parameters
    ----------
    ctrl:
        Android 设备控制器。
    timeout:
        最长等待时间 (秒)；超时后不抛出异常，记录警告。
    delay:
        消除浮层后的稳定等待时间 (秒)。
    """
    logger.info("[Startup] 检测并消除登录浮层")
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        screen = ctrl.screenshot()
        overlay = detect_overlay(screen)

        if overlay is None:
            logger.debug("[Startup] 无浮层，跳过")
            return

        logger.info("[Startup] 检测到浮层: {}，正在消除", overlay.value)
        dismiss_overlay(ctrl, overlay)
        time.sleep(delay)

    logger.warning("[Startup] 浮层消除超时 ({:.0f}s)，继续执行", timeout)


# ═══════════════════════════════════════════════════════════════════════════════
# 启动画面处理
# ═══════════════════════════════════════════════════════════════════════════════


def click_start_screen(ctrl: AndroidController) -> None:
    """点击「点击进入」启动画面，进入游戏。

    Parameters
    ----------
    ctrl:
        Android 设备控制器。
    """
    logger.info("[Startup] 点击启动画面，进入游戏")
    ctrl.click(*_CLICK_START_SCREEN)
    time.sleep(2.0)


def wait_for_game_ui(
    ctrl: AndroidController,
    *,
    timeout: float = _STARTUP_TIMEOUT,
    interval: float = _STARTUP_POLL_INTERVAL,
) -> bool:
    """等待游戏进入任意可识别的游戏页面或启动画面。

    通过反复截图，直到出现主页面或启动画面任意一种状态。

    Parameters
    ----------
    ctrl:
        Android 设备控制器。
    timeout:
        等待超时 (秒)。
    interval:
        轮询间隔 (秒)。

    Returns
    -------
    bool
        超时前成功检测到返回 ``True``，超时返回 ``False``。
    """
    from autowsgr.ui.page import get_current_page

    logger.info("[Startup] 等待游戏 UI 就绪 (超时 {:.0f}s)…", timeout)
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        screen = ctrl.screenshot()

        # 已到达某个游戏页面
        if get_current_page(screen) is not None:
            logger.info("[Startup] 已识别到游戏页面")
            return True

        # 出现「点击进入」画面
        if PixelChecker.check_signature(screen, SIG_START_SCREEN).matched:
            logger.info("[Startup] 检测到启动画面")
            return True

        # 出现登录后浮层（依然算 UI 就绪）
        if detect_overlay(screen) is not None:
            logger.info("[Startup] 检测到登录浮层，游戏已加载")
            return True

        logger.debug("[Startup] 游戏尚未就绪，等待 {:.1f}s…", interval)
        time.sleep(interval)

    logger.warning("[Startup] 等待游戏 UI 超时 ({:.0f}s)", timeout)
    return False


# ═══════════════════════════════════════════════════════════════════════════════
# 启动流程
# ═══════════════════════════════════════════════════════════════════════════════


def start_game(
    ctrl: AndroidController,
    package: str = _GAME_PACKAGE_OFFICIAL,
    *,
    startup_timeout: float = _STARTUP_TIMEOUT,
) -> None:
    """冷启动游戏，直到进入主页面为止。

    流程::

        启动 App → 等待加载 → 若在启动画面则点击进入
            → 消除登录浮层 → 导航到主页面

    Parameters
    ----------
    ctrl:
        Android 设备控制器。
    package:
        游戏包名，默认官服。
    startup_timeout:
        等待启动画面出现的超时 (秒)。

    Raises
    ------
    TimeoutError
        超时后游戏未进入可识别状态。
    """
    logger.info("[Startup] 启动游戏 (package={})", package)
    ctrl.start_app(package)

    # 等待游戏 UI 就绪
    if not wait_for_game_ui(ctrl, timeout=startup_timeout):
        raise TimeoutError(f"游戏启动超时 ({startup_timeout}s)，未检测到任何已知页面")

    # 若在启动画面，点击进入
    if is_on_start_screen(ctrl):
        click_start_screen(ctrl)
        # 再等待一次，进入游戏主流程
        if not wait_for_game_ui(ctrl, timeout=30.0):
            raise TimeoutError("点击启动画面后超时，未进入游戏")

    logger.info("[Startup] 游戏加载完成")


def restart_game(
    ctrl: AndroidController,
    package: str = _GAME_PACKAGE_OFFICIAL,
    *,
    startup_timeout: float = _STARTUP_TIMEOUT,
) -> None:
    """强制重启游戏（先 force-stop，再冷启动）。

    Parameters
    ----------
    ctrl:
        Android 设备控制器。
    package:
        游戏包名。
    startup_timeout:
        冷启动等待超时 (秒)。
    """
    logger.info("[Startup] 强制重启游戏")
    ctrl.stop_app(package)
    time.sleep(2.0)
    start_game(ctrl, package, startup_timeout=startup_timeout)


def go_main_page(ctrl: AndroidController, *, dismiss_overlays: bool = True) -> None:
    """确保当前处于游戏主页面。

    1. 若设置了 ``dismiss_overlays``，先消除登录浮层
    2. 调用 :func:`~autowsgr.ops.navigate.goto_page` 导航到主页面

    Parameters
    ----------
    ctrl:
        Android 设备控制器。
    dismiss_overlays:
        是否先消除登录浮层，默认 ``True``。
    """
    if dismiss_overlays:
        dismiss_login_overlays(ctrl)

    logger.info("[Startup] 导航到主页面")
    goto_page(ctrl, PageName.MAIN)


def ensure_game_ready(
    ctrl: AndroidController,
    app: GameAPP | str = GameAPP.official,
    *,
    startup_timeout: float = _STARTUP_TIMEOUT,
    dismiss_overlays: bool = True,
) -> None:
    """确保游戏已启动并处于主页面。

    这是最常用的顶层入口，适合脚本开头调用：

    - 游戏未运行 → 冷启动
    - 游戏已运行 → 直接消除浮层并导航到主页面

    Parameters
    ----------
    ctrl:
        Android 设备控制器。
    app:
        游戏渠道服 (``GameAPP`` 枚举) 或 Android 包名字符串。
        默认官服。
    startup_timeout:
        冷启动等待超时 (秒)。
    dismiss_overlays:
        是否消除登录浮层，默认 ``True``。

    Examples
    --------
    ::

        from autowsgr.emulator import ADBController
        from autowsgr.ops.startup import ensure_game_ready
        from autowsgr.types import GameAPP

        ctrl = ADBController()
        ctrl.connect()

        ensure_game_ready(ctrl, GameAPP.official)
        # 现在游戏已在主页面，可以开始操作
    """
    package = app.package_name if isinstance(app, GameAPP) else app
    logger.info("[Startup] 确保游戏就绪 (package={})", package)

    if not is_game_running(ctrl, package):
        logger.info("[Startup] 游戏未运行，正在启动…")
        start_game(ctrl, package, startup_timeout=startup_timeout)
    else:
        logger.info("[Startup] 游戏已在运行")

    go_main_page(ctrl, dismiss_overlays=dismiss_overlays)
    logger.info("[Startup] 游戏就绪，当前位于主页面")
