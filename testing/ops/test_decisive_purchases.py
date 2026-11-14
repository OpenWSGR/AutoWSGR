"""库存必须完整核实，技能筛选和目标编队消费实际快照。"""

from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from autowsgr.infra import DecisiveConfig, EmulatorConfig, UserConfig
from autowsgr.ops.decisive.controller import DecisiveController
from autowsgr.types import DecisivePhase, FleetSelection, OSType, ShipDamageState
from autowsgr.ui.battle.fleet_change._detect import FleetSnapshot
from autowsgr.ui.decisive.fleet_ocr import recognize_fleet_options


def _controller(*, strict: bool = False) -> DecisiveController:
    config = DecisiveConfig(
        level1=['U-2540', 'U-96', 'U-1206', 'M-296', 'U-47', '351'],
        level2=[],
        flagship_priority=['U-2540', 'U-1206'],
        useful_skill=strict,
        useful_skill_strict=strict,
    )
    ctx = SimpleNamespace(
        ctrl=MagicMock(),
        ocr=MagicMock(),
        # 显式固定环境, 避免 os_type/emulator 默认值依赖宿主平台 (非 WSL Linux CI 会抛错)
        config=UserConfig(
            emulator=EmulatorConfig(serial='127.0.0.1:5555', path='/tmp/emulator'),
            os_type=OSType.linux,
            decisive_battle=config,
        ),
        stop_event=threading.Event(),
        update_ship_damage=MagicMock(),
        is_ship_available=lambda _name: True,
    )
    controller = DecisiveController(ctx, config)
    controller.state.stage = 1
    controller.state.node = 'B'
    controller.state.score = 3
    controller.state.ships = {'U-1206', 'M-296'}
    controller.state.fleet = ['', 'U-1206', 'M-296', '', '', '', '']
    controller.state.ship_stats = [ShipDamageState.NORMAL] * 2 + [ShipDamageState.NO_SHIP] * 4
    controller._map = MagicMock()
    controller._map.close_fleet_overlay.return_value = True
    controller._map.is_skill_used.return_value = True
    controller._inventory_refresh_required = False
    controller._has_chosen_fleet = True
    controller._prepare_map_tracking = MagicMock(return_value=True)
    return controller


def _page(monkeypatch: pytest.MonkeyPatch, names: list[str | None]) -> MagicMock:
    page = MagicMock()
    page.change_fleet.return_value = True
    page.detect_fleet_snapshot.return_value = FleetSnapshot(
        names=names[:], occupied=[name is not None for name in names]
    )
    page.detect_ship_damage.return_value = {
        slot: ShipDamageState.NORMAL if name else ShipDamageState.NO_SHIP
        for slot, name in enumerate(names)
    }
    monkeypatch.setattr(
        'autowsgr.ops.decisive.handlers.DecisiveBattlePreparationPage', lambda *_: page
    )
    monkeypatch.setattr('autowsgr.ops.decisive.handlers.time.sleep', lambda _: None)
    return page


@pytest.mark.parametrize(('name', 'cost'), [('U-2540', 3), ('长跑训练', 0)])
def test_purchase_click_requires_inventory_confirmation(name: str, cost: int) -> None:
    controller = _controller()
    if name == '长跑训练':
        controller.state.fleet = ['', *controller._config.level1]
        controller.state.ships = set(controller._config.level1)
    before = controller.state.ships.copy()
    screen = np.zeros((54, 96, 3), dtype=np.uint8)
    selections = {name: FleetSelection(name=name, cost=cost, click_position=(0.25, 0.5))}
    controller._recognize_fleet_options_with_retry = MagicMock(return_value=(screen, 3, selections))
    controller._handle_choose_fleet()
    controller._map.buy_fleet_option.assert_called_once_with((0.25, 0.5))
    assert controller.state.ships == before
    assert controller._inventory_refresh_required
    assert controller.state.phase == DecisivePhase.PREPARE_COMBAT


@pytest.mark.parametrize('after_refresh', [False, True])
def test_zero_budget_replaces_previous_budget(after_refresh: bool) -> None:
    controller = _controller()
    screen = np.zeros((54, 96, 3), dtype=np.uint8)
    offer = {'not_a_configured_ship': FleetSelection('not_a_configured_ship', 3, (0.25, 0.5))}
    controller._map.wait_for_fleet_overlay_stable.return_value = screen
    controller._map.is_fleet_overlay_open.return_value = True
    controller._map.recognize_fleet_options.side_effect = (
        [(3, offer)] if after_refresh else []
    ) + [(0, {})] * 3
    controller._handle_choose_fleet()
    assert controller.state.score == 0
    controller._map.buy_fleet_option.assert_not_called()
    assert not controller._inventory_refresh_required
    assert controller._map.refresh_fleet.call_count == int(after_refresh)


def test_zero_budget_survives_later_ocr_failure_during_retry() -> None:
    controller = _controller()
    screen = np.zeros((720, 1280, 3), dtype=np.uint8)
    ocr = MagicMock()
    ocr.recognize_number.side_effect = [0, None, None]
    ocr.recognize.return_value = []
    controller._map.wait_for_fleet_overlay_stable.return_value = screen
    controller._map.is_fleet_overlay_open.return_value = True
    controller._map.recognize_fleet_options.side_effect = lambda image, **kwargs: (
        recognize_fleet_options(ocr, image, **kwargs)
    )
    _, score, selections = controller._recognize_fleet_options_with_retry(fallback_score=9)
    assert score == 0
    assert selections == {}
    assert ocr.recognize_number.call_count == 3


@pytest.mark.parametrize('actually_owned', [False, True])
def test_preparation_uses_scanned_inventory_after_purchase(
    monkeypatch: pytest.MonkeyPatch, actually_owned: bool
) -> None:
    controller = _controller()
    controller._inventory_refresh_required = True
    available = {'U-1206', 'M-296'} | ({'U-2540'} if actually_owned else set())
    controller._map.check_fleet.return_value = (
        ['U-1206', 'M-296', None, None, None, None],
        {},
        available,
    )
    expected = (
        ['U-2540', 'U-1206', 'M-296', None, None, None]
        if actually_owned
        else ['U-1206', 'M-296', None, None, None, None]
    )
    page = _page(monkeypatch, expected)
    controller._handle_prepare_combat()
    controller._map.check_fleet.assert_called_once()
    assert controller.state.ships == available
    assert controller.state.fleet == ['', *[name or '' for name in expected]]
    assert not controller._inventory_refresh_required
    page.start_battle.assert_called_once()


@pytest.mark.parametrize('gained', [[], ['U-2540']])
def test_skill_ocr_also_requires_real_inventory(
    monkeypatch: pytest.MonkeyPatch, gained: list[str]
) -> None:
    controller = _controller()
    controller._map.is_skill_used.return_value = False
    controller._map.use_skill.return_value = gained
    available = {'U-1206', 'M-296', 'U-81'}
    controller._map.check_fleet.return_value = (
        ['U-1206', 'M-296', None, None, None, None],
        {},
        available,
    )
    page = _page(monkeypatch, ['U-1206', 'M-296', None, None, None, None])
    controller._handle_prepare_combat()
    controller._map.check_fleet.assert_called_once()
    assert controller.state.ships == available
    assert 'U-2540' not in controller.state.ships
    page.start_battle.assert_called_once()


@pytest.mark.parametrize('failure', ['scan', 'short_slots', 'missing_member', 'stop', 'sync'])
def test_inventory_refresh_failure_preserves_previous_snapshot(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    controller = _controller()
    controller._inventory_refresh_required = True
    old = (controller.state.ships, controller.state.fleet, controller.state.ship_stats)
    page = _page(monkeypatch, ['U-1206', 'M-296', None, None, None, None])
    fleet = ['U-1206', None, None, None, None, None]
    if failure == 'scan':
        controller._map.check_fleet.side_effect = RuntimeError('incomplete scan')
    elif failure == 'short_slots':
        controller._map.check_fleet.return_value = (fleet[:1], {}, {'U-1206'})
    elif failure == 'missing_member':
        controller._map.check_fleet.return_value = (fleet, {}, set())
    elif failure == 'sync':
        controller._map.check_fleet.return_value = (fleet, {}, {'U-1206'})
        controller._ctx.update_ship_damage.side_effect = RuntimeError('registry unavailable')
    else:

        def stopped_scan() -> tuple:
            controller._ctx.stop_event.set()
            return fleet, {}, {'U-1206'}

        controller._map.check_fleet.side_effect = stopped_scan
    with pytest.raises((RuntimeError, ValueError, InterruptedError)):
        controller._handle_prepare_combat()
    assert (controller.state.ships, controller.state.fleet, controller.state.ship_stats) == old
    assert controller.state.ships is old[0]
    assert controller.state.fleet is old[1]
    assert controller.state.ship_stats is old[2]
    assert controller._inventory_refresh_required
    page.change_fleet.assert_not_called()
    page.apply_repair.assert_not_called()
    page.start_battle.assert_not_called()


@pytest.mark.parametrize('fallback', [False, True])
def test_purchase_uncertainty_marks_inventory_before_click(fallback: bool) -> None:
    controller = _controller()
    name = 'not_a_configured_ship' if fallback else 'U-2540'
    selections = {name: FleetSelection(name, 0, (0.25, 0.5))}
    controller._recognize_fleet_options_with_retry = MagicMock(
        return_value=(np.zeros((54, 96, 3), dtype=np.uint8), 3, selections)
    )
    controller._map.close_fleet_overlay.return_value = not fallback

    def uncertain_click(_position: tuple[float, float]) -> None:
        assert controller._inventory_refresh_required
        raise RuntimeError('click uncertain')

    controller._map.buy_fleet_option.side_effect = uncertain_click
    with pytest.raises(RuntimeError, match='click uncertain'):
        controller._handle_choose_fleet()
    assert controller._inventory_refresh_required
    assert controller.state.ships == {'U-1206', 'M-296'}


def test_skill_uncertainty_marks_inventory_before_action() -> None:
    controller = _controller()
    controller._map.is_skill_used.return_value = False

    def uncertain_skill() -> list[str]:
        assert controller._inventory_refresh_required
        raise RuntimeError('skill uncertain')

    controller._map.use_skill.side_effect = uncertain_skill
    with pytest.raises(RuntimeError, match='skill uncertain'):
        controller._handle_prepare_combat()
    assert controller._inventory_refresh_required
    assert controller.state.ships == {'U-1206', 'M-296'}
    controller._map.check_fleet.assert_not_called()


def test_verified_inventory_without_changes_skips_scan_but_checks_actual_fleet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _controller()
    page = _page(monkeypatch, ['U-1206', 'M-296', None, None, None, None])
    controller._handle_prepare_combat()
    controller._map.check_fleet.assert_not_called()
    page.change_fleet.assert_not_called()
    page.detect_fleet_snapshot.assert_called_once_with()
    assert not controller._inventory_refresh_required
    page.start_battle.assert_called_once()


def test_refresh_copies_complete_snapshot_and_clears_old_tail() -> None:
    controller = _controller()
    controller._inventory_refresh_required = True
    fleet = ['U-1206', None, None, None, None, None]
    inventory = {'U-1206', 'U-96'}
    controller._map.check_fleet.return_value = (fleet, {}, inventory)
    controller._refresh_inventory()
    assert controller.state.fleet == ['', 'U-1206', '', '', '', '', '']
    assert controller.state.ship_stats == [ShipDamageState.NORMAL] + [ShipDamageState.NO_SHIP] * 5
    fleet[0] = 'U-2540'
    inventory.clear()
    assert controller.state.fleet[1] == 'U-1206'
    assert controller.state.ships == {'U-1206', 'U-96'}
    assert not controller._inventory_refresh_required


def test_refresh_publishes_three_in_team_ships_without_reserve_inventory() -> None:
    """UI 已合并空候选与在队成员；这里只验证完整三元组的业务发布。"""
    controller = _controller()
    controller._inventory_refresh_required = True
    controller.state.ships = set(controller._config.level1)
    controller.state.fleet = ['', *controller._config.level1]
    controller.state.ship_stats = [ShipDamageState.NORMAL] * 6
    fleet = ['U-1206', 'M-296', '351', None, None, None]
    stats = [ShipDamageState.NORMAL, ShipDamageState.MODERATE, ShipDamageState.SEVERE] + [
        ShipDamageState.NO_SHIP
    ] * 3
    controller._map.check_fleet.return_value = (
        fleet,
        dict(enumerate(stats)),
        {'U-1206', 'M-296', '351'},
    )

    controller._refresh_inventory()

    controller._map.check_fleet.assert_called_once_with()
    assert controller.state.ships == {'U-1206', 'M-296', '351'}
    assert controller.state.fleet == ['', 'U-1206', 'M-296', '351', '', '', '']
    assert controller.state.ship_stats == stats
    assert not controller._inventory_refresh_required
    assert [event.args for event in controller._ctx.update_ship_damage.call_args_list] == [
        ('U-1206', ShipDamageState.NORMAL),
        ('M-296', ShipDamageState.MODERATE),
        ('351', ShipDamageState.SEVERE),
    ]


def test_strict_skill_refreshes_full_pre_skill_inventory_before_duplicate_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _controller(strict=True)
    controller._inventory_refresh_required = True
    controller._map.is_skill_used.return_value = False
    all_ships = set(controller._config.level1) | {f'other-{index}' for index in range(9)}
    trace = []
    controller._map.check_fleet.side_effect = lambda: (
        trace.append('scan') or ([None] * 6, {}, all_ships)
    )
    controller._map.use_skill.side_effect = lambda: trace.append('skill') or ['U-96']
    page = _page(monkeypatch, [None] * 6)
    controller._handle_prepare_combat()
    assert trace == ['scan', 'skill']
    assert controller.state.ships == all_ships
    assert controller.state.phase == DecisivePhase.RETREAT
    assert controller._inventory_refresh_required
    page.change_fleet.assert_not_called()
    page.apply_repair.assert_not_called()
    page.start_battle.assert_not_called()


@pytest.mark.parametrize('strict', [False, True])
def test_skill_and_purchase_refreshes_merge_unless_strict_needs_pre_skill_snapshot(
    monkeypatch: pytest.MonkeyPatch, strict: bool
) -> None:
    controller = _controller(strict=strict)
    controller._inventory_refresh_required = True
    controller._map.is_skill_used.return_value = False
    trace = []
    before = {'U-1206', 'M-296'}
    after = before | {'U-96'}

    def scan() -> tuple:
        trace.append('scan')
        return (
            ['U-1206', 'M-296', None, None, None, None],
            {},
            before if trace == ['scan'] else after,
        )

    controller._map.check_fleet.side_effect = scan
    controller._map.use_skill.side_effect = lambda: trace.append('skill') or ['U-96']
    page = _page(monkeypatch, ['U-1206', 'U-96', 'M-296', None, None, None])
    controller._handle_prepare_combat()
    assert trace == (['scan', 'skill', 'scan'] if strict else ['skill', 'scan'])
    assert controller.state.ships == after
    assert not controller._inventory_refresh_required
    page.start_battle.assert_called_once()


@pytest.mark.parametrize(
    'failure', ['false_return', 'wrong_name', 'unknown', 'extra_ship', 'wrong_occupancy']
)
def test_unverified_fleet_change_never_repairs_or_starts(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    controller = _controller()
    controller.state.ships.add('U-2540')
    old_fleet = controller.state.fleet[:]
    page = _page(monkeypatch, ['U-2540', 'U-1206', 'M-296', None, None, None])
    if failure == 'false_return':
        page.change_fleet.return_value = False
    elif failure == 'wrong_name':
        page.detect_fleet_snapshot.return_value.names[0] = 'U-96'
    elif failure == 'unknown':
        page.detect_fleet_snapshot.return_value.names[0] = None
    elif failure == 'wrong_occupancy':
        page.detect_fleet_snapshot.return_value.occupied[0] = False
    else:
        page.detect_fleet_snapshot.return_value.names[5] = 'U-96'
        page.detect_fleet_snapshot.return_value.occupied[5] = True
    with pytest.raises(RuntimeError, match='编队'):
        controller._handle_prepare_combat()
    assert controller.state.fleet == old_fleet
    assert controller._inventory_refresh_required
    page.apply_repair.assert_not_called()
    page.start_battle.assert_not_called()
