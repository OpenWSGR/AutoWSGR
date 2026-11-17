"""游戏启动、登录等待和每日浮层处理的无设备单元测试。"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest

import autowsgr.ui.utils as ui_utils
from autowsgr.ops import navigate, startup
from autowsgr.types import PageName


_TODAY = date(2026, 8, 8)


def _make_ctx(*, handled_on: date | None = None) -> SimpleNamespace:
    """构造浮层处理所需的最小游戏上下文。"""
    return SimpleNamespace(ctrl=MagicMock(), daily_overlay_date=handled_on)


def _freeze_today(monkeypatch: pytest.MonkeyPatch) -> None:
    """固定游戏使用的本地日期，避免测试受真实日期变化影响。"""
    date_type = MagicMock()
    date_type.today.return_value = _TODAY
    monkeypatch.setattr(startup, 'date', date_type)


@pytest.fixture
def startup_clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """让轮询只推进虚拟时间，不执行真实等待。"""
    now = [0.0]
    monkeypatch.setattr(startup.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(startup.time, 'sleep', lambda seconds: now.__setitem__(0, now[0] + seconds))
    return now


def _mock_pages(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """用可读状态替代像素图，保留启动函数本身的状态转换与轮询。"""
    title = MagicMock()
    title.is_current_page.side_effect = lambda screen: screen == 'title'
    monkeypatch.setattr(startup, 'StartScreenPage', title)
    monkeypatch.setattr(
        startup,
        'get_current_page',
        {'main': PageName.MAIN, 'news': PageName.MAIN, 'map': PageName.MAP}.get,
    )
    return title


@pytest.mark.parametrize('screen', ['title', 'main', 'news', 'map'])
def test_wait_for_game_ui_accepts_title_and_known_game_pages(
    monkeypatch: pytest.MonkeyPatch,
    screen: str,
) -> None:
    """主页面、主页面浮层和其他已注册页面都可结束初始加载等待。"""
    _mock_pages(monkeypatch)
    ctrl = MagicMock()
    ctrl.screenshot.return_value = screen

    assert startup.wait_for_game_ui(ctrl)
    ctrl.screenshot.assert_called_once()


@pytest.mark.usefixtures('startup_clock')
def test_wait_after_enter_does_not_accept_title_or_try_game_page_signatures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """点击后仍停留在标题页时，即使其他识别器宽松命中也不能报登录成功。"""
    _mock_pages(monkeypatch)
    registered_page = MagicMock(return_value=PageName.MAP)
    monkeypatch.setattr(startup, 'get_current_page', registered_page)
    ctrl = MagicMock()
    ctrl.screenshot.return_value = 'title'

    assert not startup.wait_for_game_ui(ctrl, timeout=2.0, interval=1.0, allow_start_screen=False)
    assert ctrl.screenshot.call_count == 2
    registered_page.assert_not_called()


@pytest.mark.usefixtures('startup_clock')
def test_start_game_waits_through_title_and_loading_after_enter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """一次点击后需要等到游戏页面，标题页和加载背景都不能提前结束。"""
    title = _mock_pages(monkeypatch)
    ctrl = MagicMock()
    ctrl.screenshot.side_effect = ['title', 'title', 'title', 'loading', 'news']

    startup.start_game(ctrl, 'test.package')

    ctrl.start_app.assert_called_once_with('test.package')
    title.return_value.click_enter.assert_called_once_with()
    assert ctrl.screenshot.call_count == 5


@pytest.mark.usefixtures('startup_clock')
def test_start_game_times_out_when_enter_does_not_leave_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """进入按钮无效时必须抛出超时，而不是把原来的标题页当成成功。"""
    title = _mock_pages(monkeypatch)
    ctrl = MagicMock()
    ctrl.screenshot.return_value = 'title'

    with pytest.raises(TimeoutError, match='点击启动画面后超时'):
        startup.start_game(ctrl)

    title.return_value.click_enter.assert_called_once_with()


@pytest.mark.parametrize('already_running', [False, True])
def test_login_can_take_more_than_thirty_seconds(
    monkeypatch: pytest.MonkeyPatch,
    startup_clock: list[float],
    *,
    already_running: bool,
) -> None:
    """正常登录加载耗时超过 30 秒时，冷启动和运行中登录均使用现有启动预算。"""
    title = _mock_pages(monkeypatch)
    title.return_value.click_enter.side_effect = lambda: startup.time.sleep(2.0)
    ctrl = MagicMock()

    def screenshot() -> str:
        if not title.return_value.click_enter.called:
            return 'title'
        return 'main' if startup_clock[0] >= 45.0 else 'loading'

    ctrl.screenshot.side_effect = screenshot
    if already_running:
        monkeypatch.setattr(startup, 'go_main_page', MagicMock())
        ctx = _make_ctx()
        ctx.ctrl = ctrl
        startup.recover_to_main_or_restart(ctx)
    else:
        startup.start_game(ctrl, startup_timeout=60.0)

    title.return_value.click_enter.assert_called_once_with()
    assert startup_clock[0] == 45.0


def test_cold_start_shares_total_timeout_between_loading_and_entering(
    monkeypatch: pytest.MonkeyPatch,
    startup_clock: list[float],
) -> None:
    """启动画面加载和点击后等待共用预算，点击后的稳定等待也计入总时长。"""
    title = _mock_pages(monkeypatch)
    title.return_value.click_enter.side_effect = lambda: startup.time.sleep(2.0)
    ctrl = MagicMock()

    def screenshot() -> str:
        if startup_clock[0] < 10.0 or title.return_value.click_enter.called:
            return 'loading'
        return 'title'

    ctrl.screenshot.side_effect = screenshot

    with pytest.raises(TimeoutError, match='点击启动画面后超时'):
        startup.start_game(ctrl, startup_timeout=20.0)

    title.return_value.click_enter.assert_called_once_with()
    assert startup_clock[0] == 20.0


def test_start_game_accepts_existing_game_page_without_clicking_enter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """应用直接恢复游戏页面时不点标题页坐标。"""
    title = _mock_pages(monkeypatch)
    ctrl = MagicMock()
    ctrl.screenshot.return_value = 'main'

    startup.start_game(ctrl)

    title.return_value.click_enter.assert_not_called()


@pytest.mark.usefixtures('startup_clock')
def test_restart_game_stops_then_enters_and_waits_for_game_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """异常恢复使用的强制重启走同一套登录等待，仍需离开启动页才完成。"""
    title = _mock_pages(monkeypatch)
    ctrl = MagicMock()
    ctrl.screenshot.side_effect = ['title', 'title', 'title', 'main']

    startup.restart_game(ctrl, 'test.package')

    assert ctrl.method_calls[:2] == [call.stop_app('test.package'), call.start_app('test.package')]
    title.return_value.click_enter.assert_called_once_with()
    assert ctrl.screenshot.call_count == 4


def test_handle_daily_overlays_skips_after_today_is_handled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """当天已经处理过时，不再创建页面控制器或截图。"""
    _freeze_today(monkeypatch)
    page_type = MagicMock()
    monkeypatch.setattr(startup, 'MainPage', page_type)
    ctx = _make_ctx(handled_on=_TODAY)

    startup.handle_daily_overlays(ctx)

    page_type.assert_not_called()


def test_startup_can_handle_overlays_again_on_same_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """游戏重新登录后仍会处理浮层，不受调度器当天已经处理过的标记影响。"""
    _freeze_today(monkeypatch)
    page = MagicMock()
    page.dismiss_current_overlay.return_value = False
    monkeypatch.setattr(startup, 'MainPage', MagicMock(return_value=page))
    monkeypatch.setattr(ui_utils, 'confirm_operation', MagicMock(return_value=False))
    ctx = _make_ctx(handled_on=_TODAY)

    startup.handle_daily_overlays(ctx, force=True)

    page.dismiss_current_overlay.assert_called_once_with()


def test_handle_daily_overlays_processes_overlay_and_confirm_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """已知浮层和无签名确认框按出现顺序处理，画面干净后结束。"""
    _freeze_today(monkeypatch)
    page = MagicMock()
    page.dismiss_current_overlay.side_effect = [True, False, False]
    monkeypatch.setattr(startup, 'MainPage', MagicMock(return_value=page))

    confirm = MagicMock(side_effect=[True, False])
    monkeypatch.setattr(ui_utils, 'confirm_operation', confirm)
    sleep = MagicMock()
    monkeypatch.setattr(startup.time, 'sleep', sleep)
    ctx = _make_ctx()

    startup.handle_daily_overlays(ctx)

    assert ctx.daily_overlay_date == _TODAY
    assert page.dismiss_current_overlay.call_count == 3
    assert confirm.call_args_list == [
        call(ctx.ctrl, must_confirm=False, timeout=startup._OVERLAY_CONFIRM_TIMEOUT),
        call(ctx.ctrl, must_confirm=False, timeout=startup._OVERLAY_CONFIRM_TIMEOUT),
    ]
    assert sleep.call_args_list == [
        call(startup._OVERLAY_DISMISS_WAIT),
        call(startup._OVERLAY_DISMISS_WAIT),
    ]


def test_handle_daily_overlays_stops_at_attempt_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """浮层持续出现时最多处理固定次数，防止异常画面导致死循环。"""
    _freeze_today(monkeypatch)
    page = MagicMock()
    page.dismiss_current_overlay.return_value = True
    monkeypatch.setattr(startup, 'MainPage', MagicMock(return_value=page))
    sleep = MagicMock()
    monkeypatch.setattr(startup.time, 'sleep', sleep)

    ctx = _make_ctx()
    startup.handle_daily_overlays(ctx)

    assert page.dismiss_current_overlay.call_count == startup._OVERLAY_DISMISS_MAX
    assert sleep.call_count == startup._OVERLAY_DISMISS_MAX
    assert ctx.daily_overlay_date is None


@pytest.mark.parametrize(
    ('dismiss_overlays', 'expected_calls'),
    [(True, 1), (False, 0)],
)
def test_go_main_page_handles_overlays_after_navigation(
    monkeypatch: pytest.MonkeyPatch,
    *,
    dismiss_overlays: bool,
    expected_calls: int,
) -> None:
    """主页面导航完成后按开关决定是否执行每日浮层处理。"""
    goto = MagicMock()
    handle = MagicMock()
    monkeypatch.setattr(startup, 'goto_page', goto)
    monkeypatch.setattr(startup, 'handle_daily_overlays', handle)
    wait = MagicMock()
    monkeypatch.setattr(startup, 'wait_for_page', wait)
    ctx = _make_ctx()

    startup.go_main_page(ctx, dismiss_overlays=dismiss_overlays)

    goto.assert_called_once_with(ctx, PageName.MAIN)
    assert handle.call_count == expected_calls
    assert wait.call_count == expected_calls
    if dismiss_overlays:
        handle.assert_called_once_with(ctx, force=True)


@pytest.mark.usefixtures('startup_clock')
def test_go_main_page_verifies_clean_base_after_overlay_dismissal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """导航认为已在主页面时仍须等到基础界面，不能把尚未消失的浮层当成就绪。"""
    monkeypatch.setattr(startup, 'goto_page', MagicMock())
    monkeypatch.setattr(startup, 'handle_daily_overlays', MagicMock())
    monkeypatch.setattr(startup.MainPage, 'is_base_page', lambda screen: screen != 'loading')
    monkeypatch.setattr(
        startup.MainPage, 'detect_overlay', lambda screen: 'news' if screen == 'news' else None
    )
    monkeypatch.setattr(
        'autowsgr.ui.page.get_current_page', lambda _screen, **_kwargs: PageName.MAIN
    )
    ctx = _make_ctx()
    ctx.ctrl.screenshot.side_effect = ['news', 'loading', 'main']

    startup.go_main_page(ctx)

    assert ctx.ctrl.screenshot.call_count == 3


@pytest.mark.usefixtures('startup_clock')
def test_go_main_page_rejects_overlay_that_did_not_dismiss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """处理浮层后若仍未到干净主页，启动失败且不会交付可运行任务的假就绪状态。"""
    monkeypatch.setattr(startup, 'goto_page', MagicMock())
    monkeypatch.setattr(startup, 'handle_daily_overlays', MagicMock())
    monkeypatch.setattr(startup.MainPage, 'is_base_page', lambda _screen: True)
    monkeypatch.setattr(startup.MainPage, 'detect_overlay', lambda _screen: 'news')
    monkeypatch.setattr(
        'autowsgr.ui.page.get_current_page', lambda _screen, **_kwargs: PageName.MAIN
    )
    monkeypatch.setattr('autowsgr.infra.logger.save_image', MagicMock())
    ctx = _make_ctx()
    ctx.ctrl.screenshot.return_value = 'news'

    with pytest.raises(ui_utils.NavigationError, match='等待超时'):
        startup.go_main_page(ctx)


def test_ensure_game_ready_handles_overlays_for_running_game(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """游戏已运行并恢复页面后，仍会从顶层启动入口检查每日浮层。"""
    monkeypatch.setattr(startup, 'is_game_running', MagicMock(return_value=True))
    recover = MagicMock()
    main = MagicMock()
    monkeypatch.setattr(startup, 'recover_to_main_or_restart', recover)
    monkeypatch.setattr(startup, 'go_main_page', main)
    ctx = _make_ctx()

    startup.ensure_game_ready(ctx, app='test.package')

    recover.assert_called_once_with(ctx, 'test.package', dismiss_overlays=True)
    main.assert_called_once_with(ctx, dismiss_overlays=True)


def test_ensure_game_ready_navigates_to_main_after_cold_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """冷启动结束后统一执行主页面导航和浮层校验。"""
    monkeypatch.setattr(startup, 'is_game_running', MagicMock(return_value=False))
    start = MagicMock()
    main = MagicMock()
    monkeypatch.setattr(startup, 'start_game', start)
    monkeypatch.setattr(startup, 'go_main_page', main)
    ctx = _make_ctx()

    startup.ensure_game_ready(ctx, 'test.package', startup_timeout=45.0)

    start.assert_called_once_with(ctx.ctrl, 'test.package', startup_timeout=45.0)
    main.assert_called_once_with(ctx, dismiss_overlays=True)


@pytest.mark.parametrize('dismiss_overlays', [True, False])
@pytest.mark.usefixtures('startup_clock')
def test_recover_running_game_on_title_enters_without_restarting(
    monkeypatch: pytest.MonkeyPatch,
    *,
    dismiss_overlays: bool,
) -> None:
    """运行中的游戏停留在点击进入页时直接登录，不交给无路径的页面导航恢复。"""
    title = _mock_pages(monkeypatch)
    identify = MagicMock()
    restart = MagicMock()
    main = MagicMock()
    monkeypatch.setattr(navigate, 'identify_current_page', identify)
    monkeypatch.setattr(startup, 'restart_game', restart)
    monkeypatch.setattr(startup, 'go_main_page', main)
    ctx = _make_ctx()
    ctx.ctrl.screenshot.side_effect = ['title', 'title', 'main']

    startup.recover_to_main_or_restart(ctx, 'test.package', dismiss_overlays=dismiss_overlays)

    title.return_value.click_enter.assert_called_once_with()
    identify.assert_not_called()
    restart.assert_not_called()
    main.assert_called_once_with(ctx, dismiss_overlays=dismiss_overlays)


def test_recovery_restart_finishes_on_clean_main(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """页面恢复超时重启后仍需完成主页面和浮层处理。"""
    _mock_pages(monkeypatch)
    monkeypatch.setattr(navigate, 'identify_current_page', MagicMock(return_value=None))
    restart = MagicMock()
    main = MagicMock()
    monkeypatch.setattr(startup, 'restart_game', restart)
    monkeypatch.setattr(startup, 'go_main_page', main)
    ctx = _make_ctx()
    ctx.ctrl.screenshot.return_value = 'unknown'

    startup.recover_to_main_or_restart(ctx, 'test.package', timeout=0.0)

    restart.assert_called_once_with(ctx.ctrl, 'test.package')
    main.assert_called_once_with(ctx, dismiss_overlays=True)


@pytest.mark.usefixtures('startup_clock')
def test_recovery_enters_title_that_appears_after_initial_loading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """运行中的应用稍后才显示标题页时，恢复轮询重新检查并登录，避免无谓重启。"""
    title = _mock_pages(monkeypatch)
    monkeypatch.setattr(navigate, 'identify_current_page', MagicMock(return_value=None))
    restart = MagicMock()
    main = MagicMock()
    monkeypatch.setattr(startup, 'restart_game', restart)
    monkeypatch.setattr(startup, 'go_main_page', main)
    ctx = _make_ctx()
    ctx.ctrl.screenshot.side_effect = ['loading', 'title', 'title', 'main']

    startup.recover_to_main_or_restart(ctx, 'test.package', dismiss_overlays=False)

    title.return_value.click_enter.assert_called_once_with()
    restart.assert_not_called()
    main.assert_called_once_with(ctx, dismiss_overlays=False)
