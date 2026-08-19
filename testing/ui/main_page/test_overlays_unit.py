"""主页面每日浮层操作的无设备单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

import autowsgr.ui.utils as ui_utils
from autowsgr.ui.main_page import overlays
from autowsgr.ui.main_page.constants import DismissCoord
from autowsgr.vision import ImageChecker


@pytest.mark.parametrize('second_confirmed', [False, True])
def test_dismiss_sign_handles_optional_second_confirmation(
    monkeypatch: pytest.MonkeyPatch,
    *,
    second_confirmed: bool,
) -> None:
    """签到首次确认必须处理，第二段确认存在时继续点击。"""
    ctrl = MagicMock()
    confirm = MagicMock(side_effect=[True, second_confirmed])
    sleep = MagicMock()
    monkeypatch.setattr(ui_utils, 'confirm_operation', confirm)
    monkeypatch.setattr(overlays.time, 'sleep', sleep)

    overlays.dismiss_sign(ctrl)

    ctrl.click.assert_called_once_with(*DismissCoord.SIGN_CONFIRM.xy)
    assert confirm.call_args_list == [
        call(ctrl, must_confirm=True, timeout=overlays._SIGN_CONFIRM_TIMEOUT),
        call(ctrl, must_confirm=False, timeout=overlays._SIGN_CONFIRM_TIMEOUT),
    ]
    sleep.assert_called_once_with(overlays._SIGN_CONFIRM_WAIT)


@pytest.mark.parametrize(
    ('template_name', 'expected'),
    [
        ('overlay_news', overlays.OverlayKind.NEWS),
        ('overlay_sign', overlays.OverlayKind.SIGN),
        ('overlay_booking', overlays.OverlayKind.BOOKING),
        ('overlay_user_info', overlays.OverlayKind.USER_INFO),
    ],
)
def test_detect_overlay_uses_templates(
    monkeypatch: pytest.MonkeyPatch,
    *,
    template_name: str,
    expected: overlays.OverlayKind,
) -> None:
    """浮层检测改用图像模板匹配 (含 USER_INFO 新增分支)。"""
    monkeypatch.setattr(
        ImageChecker, 'template_exists', lambda _s, t, **_k: t.name == template_name
    )
    assert overlays.detect_overlay(MagicMock()) is expected


def test_detect_overlay_none_when_no_match(monkeypatch: pytest.MonkeyPatch) -> None:
    """无浮层命中时返回 None。"""
    monkeypatch.setattr(ImageChecker, 'template_exists', lambda *_a, **_k: False)
    assert overlays.detect_overlay(MagicMock()) is None
