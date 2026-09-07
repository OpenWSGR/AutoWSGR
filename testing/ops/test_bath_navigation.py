"""测试普通出征与决战进入澡堂的显式导航路线。"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import autowsgr.ops.repair as repair_module
from autowsgr.context import GameContext
from autowsgr.infra import ActionFailedError
from autowsgr.ops import navigate
from autowsgr.types import PageName
from autowsgr.ui.battle.base import RepairStrategy
from autowsgr.ui.battle.preparation import BattlePreparationPage
from autowsgr.ui.utils import NavigationError


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


def test_manual_repair_action_runs_before_manual_repair_error() -> None:
    ctx = GameContext(
        ctrl=MagicMock(),
        config=SimpleNamespace(repair_manually=True),
        ocr=None,
    )
    page = BattlePreparationPage(ctx)
    page.check_repair = MagicMock(return_value=[0])
    manual_repair_action = MagicMock()

    with pytest.raises(ActionFailedError, match='需要进行手动修理'):
        page.apply_repair(
            RepairStrategy.MODERATE,
            manual_repair_action=manual_repair_action,
        )

    manual_repair_action.assert_called_once_with([0])


def test_manual_bath_repair_records_success_and_stops_on_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = MagicMock()
    page.repair_ship.side_effect = [120, -1]
    ship = MagicMock()
    ctx = SimpleNamespace(
        bathroom=MagicMock(),
        config=SimpleNamespace(bathroom_count=2),
        get_ship=lambda _name: ship,
        update_ship_damage=MagicMock(),
    )
    goto_page = MagicMock()
    monkeypatch.setattr(repair_module, 'BathPage', lambda _ctx: page)
    monkeypatch.setattr(repair_module, 'goto_page', goto_page)

    repair_module.repair_manual_targets_in_bath(ctx, ['舰一', '舰二'])

    assert page.go_to_choose_repair.call_count == 2
    assert page.repair_ship.call_args_list[0].args == ('舰一',)
    ship.set_repair.assert_called_once_with(120)
    ctx.update_ship_damage.assert_called_once_with('舰一', 0)
    ctx.bathroom.occupy.assert_called_once_with(120)
    goto_page.assert_called_once_with(ctx, PageName.MAIN)


def test_manual_bath_repair_logs_missing_target_and_returns_home(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = MagicMock()
    page.repair_ship.side_effect = NavigationError('target not listed')
    ctx = SimpleNamespace()
    goto_page = MagicMock()
    monkeypatch.setattr(repair_module, 'BathPage', lambda _ctx: page)
    monkeypatch.setattr(repair_module, 'goto_page', goto_page)

    repair_module.repair_manual_targets_in_bath(ctx, ['舰一'])

    page.go_to_choose_repair.assert_called_once_with()
    page.repair_ship.assert_called_once_with('舰一')
    goto_page.assert_called_once_with(ctx, PageName.MAIN)
