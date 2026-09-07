"""测试普通出征与决战进入澡堂的显式导航路线。"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from autowsgr.ops import navigate
from autowsgr.types import PageName


def test_normal_sortie_returns_to_map_before_bath(monkeypatch: pytest.MonkeyPatch) -> None:
    page = MagicMock()
    monkeypatch.setattr('autowsgr.ui.battle.preparation.BattlePreparationPage', lambda _ctx: page)
    goto_page = MagicMock()
    monkeypatch.setattr(navigate, 'goto_page', goto_page)
    ctx = object()

    navigate.goto_bath_from_normal_sortie(ctx)

    page.go_back.assert_called_once_with()
    goto_page.assert_called_once_with(ctx, PageName.BATH)


def test_decisive_sortie_leaves_saved_map_before_bath(monkeypatch: pytest.MonkeyPatch) -> None:
    controller = MagicMock()
    decisive_config = object()
    ctx = SimpleNamespace(
        config=SimpleNamespace(decisive_battle=decisive_config),
        ctrl=object(),
    )
    monkeypatch.setattr(
        'autowsgr.ui.decisive.DecisiveMapController',
        lambda _ctx, _config: controller,
    )
    goto_page = MagicMock()
    monkeypatch.setattr(navigate, 'goto_page', goto_page)
    wait_for_page = MagicMock()
    monkeypatch.setattr('autowsgr.ui.utils.wait_for_page', wait_for_page)

    navigate.goto_bath_from_decisive_sortie(ctx)

    controller.go_to_map_page.assert_called_once_with()
    controller.open_retreat_dialog.assert_called_once_with()
    controller.confirm_leave.assert_called_once_with()
    wait_for_page.assert_called_once()
    assert wait_for_page.call_args.args[0] is ctx.ctrl
    assert wait_for_page.call_args.kwargs['target'] is PageName.DECISIVE_BATTLE
    goto_page.assert_called_once_with(ctx, PageName.BATH)
