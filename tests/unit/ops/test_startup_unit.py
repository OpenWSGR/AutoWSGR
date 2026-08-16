"""游戏启动阶段每日浮层处理的无设备单元测试。"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest

import autowsgr.ui.utils as ui_utils
from autowsgr.ops import startup
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

    startup.handle_daily_overlays(_make_ctx())

    assert page.dismiss_current_overlay.call_count == startup._OVERLAY_DISMISS_MAX
    assert sleep.call_count == startup._OVERLAY_DISMISS_MAX


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
    ctx = _make_ctx()

    startup.go_main_page(ctx, dismiss_overlays=dismiss_overlays)

    goto.assert_called_once_with(ctx, PageName.MAIN)
    assert handle.call_count == expected_calls


def test_ensure_game_ready_handles_overlays_for_running_game(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """游戏已运行并恢复页面后，仍会从顶层启动入口检查每日浮层。"""
    monkeypatch.setattr(startup, 'is_game_running', MagicMock(return_value=True))
    recover = MagicMock()
    handle = MagicMock()
    monkeypatch.setattr(startup, 'recover_to_main_or_restart', recover)
    monkeypatch.setattr(startup, 'handle_daily_overlays', handle)
    ctx = _make_ctx()

    startup.ensure_game_ready(ctx, app='test.package')

    recover.assert_called_once_with(ctx, 'test.package')
    handle.assert_called_once_with(ctx)
