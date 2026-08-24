"""游戏启动与初始化操作。

note. 已通过测试
TODO: 处理游戏更新提示

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
from datetime import date
from typing import TYPE_CHECKING

from autowsgr.infra.logger import get_logger
from autowsgr.ops.navigate import goto_page
from autowsgr.types import GameAPP, PageName
from autowsgr.ui.main_page import MainPage
from autowsgr.ui.start_screen_page import StartScreenPage
from autowsgr.ui.utils import NavigationError


if TYPE_CHECKING:
    from autowsgr.context import GameContext
    from autowsgr.emulator import AndroidController

_log = get_logger('ops.startup')

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

_OVERLAY_DISMISS_MAX: int = 5
"""每日浮层消除的最大尝试次数 (新闻 → 签到 → 确认 → 二次确认 → 兜底)。"""

_OVERLAY_DISMISS_WAIT: float = 1.5
"""消除每个浮层后的等待时间 (秒) — 弹窗按顺序逐个出现, 需要间隔等待。"""

_OVERLAY_CONFIRM_TIMEOUT: float = 3.0
"""确认弹窗兜底的最大等待时限 (秒) — 用于检测不到浮层签名但存在确认按钮的弹窗。"""

_RECOVERY_TO_MAIN_TIMEOUT: float = 20.0
"""页面异常恢复时，尝试回到主界面的超时 (秒)。"""


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
    _log.debug('[Startup] 游戏运行状态: {}', '运行中' if running else '未运行')
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
    _log.debug('[Startup] 主页面检测: {}', '是' if result else '否')
    return result


def wait_for_game_ui(
    ctrl: AndroidController,
    *,
    timeout: float = _STARTUP_TIMEOUT,
    interval: float = _STARTUP_POLL_INTERVAL,
) -> bool:
    # TODO: 游戏更新处理
    """等待游戏进入任意可识别的游戏页面或启动画面。

    通过反复截图，直到出现以下任一状态即视为 UI 就绪：
    启动画面、登录浮层、任意已注册页面 (如主页面)。

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
    # 延迟导入避免循环依赖 (ui 层反向引用 ops 的模块)
    from autowsgr.ui.main_page.overlays import detect_overlay
    from autowsgr.ui.page import get_current_page

    _log.info('[Startup] 等待游戏 UI 就绪 (超时 {:.0f}s)…', timeout)
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        screen = ctrl.screenshot()

        # 出现「点击进入」画面
        if StartScreenPage.is_current_page(screen):
            _log.info('[Startup] 检测到启动画面')
            return True

        # 出现登录后浮层（依然算 UI 就绪）
        if detect_overlay(screen) is not None:
            _log.info('[Startup] 检测到登录浮层，游戏已加载')
            return True

        # 已进入任意可识别页面 (如重启后直接恢复到主页面)
        page = get_current_page(screen)
        if page is not None:
            _log.info('[Startup] 检测到已进入页面: {}', page)
            return True

        _log.debug('[Startup] 游戏尚未就绪，等待 {:.1f}s…', interval)
        time.sleep(interval)

    _log.warning('[Startup] 等待游戏 UI 超时 ({:.0f}s)', timeout)
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
    _log.info('[Startup] 启动游戏 (package={})', package)
    ctrl.start_app(package)

    # 等待游戏 UI 就绪
    if not wait_for_game_ui(ctrl, timeout=startup_timeout):
        raise TimeoutError(f'游戏启动超时 ({startup_timeout}s)，未检测到任何已知页面')

    # 若在启动画面，点击进入，然后等待进入主流程（检测登录浮层）
    if StartScreenPage.is_current_page(ctrl.screenshot()):
        StartScreenPage(ctrl).click_enter()
        if not wait_for_game_ui(ctrl, timeout=30.0):
            raise TimeoutError('点击启动画面后超时，未进入游戏')

    _log.info('[Startup] 游戏加载完成')


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
    _log.info('[Startup] 强制重启游戏')
    ctrl.stop_app(package)
    time.sleep(2.0)
    start_game(ctrl, package, startup_timeout=startup_timeout)


def handle_daily_overlays(ctx: GameContext) -> None:
    """每日首次主页面浮层处理 (新闻公告 → 每日签到 → 活动预约)。

    时间戳 gate: 每天 0 点后第一次调用才真正截图检测并消除浮层,
    当天已处理过则直接返回 (零开销), 避免每次回主页都重复检测。

    触发时机 (启动 / 任务执行前 / 挂机等待) 均可安全调用:
    - 登录后弹出「新闻公告」→ 勾选「不再显示」+ 点左上角 X
    - 接着弹出「每日签到」→ 点领取 + 确认操作
    - 可能再弹出「活动预约」→ 点关闭 + 二次确认

    按弹窗出现顺序逐个消除, 最多尝试 :data:`_OVERLAY_DISMISS_MAX` 次,
    直到画面干净或无浮层可关为止。
    """
    today = date.today()  # noqa: DTZ011  # 本地墙上时钟 (游戏 0 点刷新)
    if ctx.daily_overlay_date == today:
        return
    # 先标记再执行: 即使本次消除中断, 当天也不会反复重试
    ctx.daily_overlay_date = today

    page = MainPage(ctx)
    for attempt in range(_OVERLAY_DISMISS_MAX):
        # ① 已知浮层 (新闻 / 签到 / 预约) 直接消除
        if page.dismiss_current_overlay():
            _log.info(
                '[Startup] 主页面浮层已消除 ({}/{})',
                attempt + 1,
                _OVERLAY_DISMISS_MAX,
            )
            time.sleep(_OVERLAY_DISMISS_WAIT)
            continue

        # ② 确认弹窗兜底: 检测不到浮层签名, 但可能有「确认」按钮
        #    (如签到奖励确认、二次确认) — 用确认模板轮子点掉
        from autowsgr.ui.utils import confirm_operation

        if confirm_operation(
            ctx.ctrl,
            must_confirm=False,
            timeout=_OVERLAY_CONFIRM_TIMEOUT,
        ):
            _log.info('[Startup] 确认弹窗兜底: 点击确认 ({}/{})', attempt + 1, _OVERLAY_DISMISS_MAX)
            time.sleep(_OVERLAY_DISMISS_WAIT)
            continue

        # ③ 既无浮层又无确认按钮 → 主页干净, 流程完成
        return


def go_main_page(ctx: GameContext, *, dismiss_overlays: bool = True) -> None:
    """确保当前处于游戏主页面。

    1. 调用 :func:`~autowsgr.ops.navigate.goto_page` 导航到主页面
    2. 若设置了 ``dismiss_overlays``，导航后消除登录浮层

    Parameters
    ----------
    ctx:
        游戏上下文。
    dismiss_overlays:
        是否消除登录浮层，默认 ``True``。
    """
    _log.info('[Startup] 导航到主页面')
    goto_page(ctx, PageName.MAIN)
    if dismiss_overlays:
        handle_daily_overlays(ctx)


def recover_to_main_or_restart(
    ctx: GameContext,
    app: GameAPP | str = GameAPP.official,
    *,
    timeout: float = _RECOVERY_TO_MAIN_TIMEOUT,
) -> None:
    """页面异常时优先回主页面，超时后强制重启游戏。"""
    ctrl = ctx.ctrl
    package = app.package_name if isinstance(app, GameAPP) else app

    from .navigate import identify_current_page

    page = identify_current_page(ctx)
    if page is not None:
        return

    _log.warning('[Startup] 当前页面无法识别，尝试恢复到主页面')
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        try:
            goto_page(ctx, PageName.MAIN)
            _log.info('[Startup] 页面恢复成功，已回到主页面')
        except NavigationError as exc:
            _log.debug('[Startup] 恢复主页面失败，继续重试: {}', exc)
            time.sleep(1.0)
        else:
            return

    _log.warning('[Startup] 页面恢复超时，执行强制重启游戏')
    restart_game(ctrl, package)


def ensure_game_ready(
    ctx: GameContext,
    app: GameAPP | str = GameAPP.official,
    *,
    startup_timeout: float = _STARTUP_TIMEOUT,
    dismiss_overlays: bool = True,
) -> None:
    """确保游戏已启动并处于可识别页面。

    这是最常用的顶层入口，适合脚本开头调用：

    - 游戏未运行 → 冷启动
    - 游戏已运行 → 直接消除浮层并导航到主页面

    Parameters
    ----------
    ctx:
        游戏上下文。
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

        from autowsgr.scheduler import launch

        ctx = launch("user_settings.yaml")
        # 游戏已在主页面
    """
    ctrl = ctx.ctrl
    package = app.package_name if isinstance(app, GameAPP) else app
    _log.info('[Startup] 确保游戏就绪 (package={})', package)

    if not is_game_running(ctrl, package):
        _log.info('[Startup] 游戏未运行，正在启动…')
        start_game(ctrl, package, startup_timeout=startup_timeout)
    else:
        recover_to_main_or_restart(ctx, package)
        _log.info('[Startup] 游戏已在运行')

    _log.info('[Startup] 游戏就绪')
    if dismiss_overlays:
        handle_daily_overlays(ctx)
