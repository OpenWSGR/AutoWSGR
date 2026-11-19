"""验证在浴室读不出维修时长时，决战能否换上候补或等其他舰船修好。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from autowsgr.constants import ship_name_identity
from autowsgr.ops.decisive.controller import DecisiveResult
from autowsgr.types import DecisivePhase
from autowsgr.types import ShipDamageState as Damage
from autowsgr.ui.bath_page.page import RepairShipInfo
from testing.ops.test_decisive_repair import _bath, _controller, _snapshot


@pytest.mark.parametrize(
    ('count', 'waiting_ship', 'expected_waits', 'expected'),
    [
        (7, False, [], DecisiveResult.CHAPTER_CLEAR),
        (7, True, [7], DecisiveResult.CHAPTER_CLEAR),
        (1, False, [], DecisiveResult.ERROR),
        (2, True, [], DecisiveResult.ERROR),
        (7, True, [7], DecisiveResult.STOPPED),
    ],
    ids=['reserve', 'repair-can-fill', 'only-ship', 'repair-cannot-fill', 'stop-during-wait'],
)
def test_failed_quote_through_scheduler(
    monkeypatch: pytest.MonkeyPatch,
    count: int,
    waiting_ship: bool,
    expected_waits: list[int],
    expected: DecisiveResult,
) -> None:
    ctrl, clock = _controller(count=count)
    monkeypatch.setattr('autowsgr.scheduler.decisive.time.monotonic', clock)
    ctrl.state.chapter = ctrl.state.stage = 1
    ships = ctrl._config.level1
    ctrl.state.ships = set(ships)
    ctrl.state.fleet = ['', *ships[:6], *([''] * max(0, 6 - count))]
    health = dict.fromkeys(ships, Damage.NORMAL)
    health[ships[0]] = Damage.SEVERE
    if waiting_ship:
        health[ships[1]] = Damage.REPAIRING
        ctrl._ctx.get_ship(ships[1]).repair_end_time = clock() + 7
    ctrl._map = MagicMock()
    page = MagicMock()
    bath = _bath(monkeypatch, ctrl, [RepairShipInfo(ships[0], (0.1, 0.5), '')])
    monkeypatch.setattr('autowsgr.ops.decisive.repair.goto_page', MagicMock())
    monkeypatch.setattr(ctrl, '_prepare_entry_state', MagicMock())
    observed_waits = []

    def wait(seconds: float) -> None:
        observed_waits.append(seconds)
        if expected is DecisiveResult.STOPPED:
            ctrl._ctx.stop_event.set()
        else:
            clock.return_value += seconds

    monkeypatch.setattr(ctrl._ctx.stop_event, 'wait', wait)

    def snapshot(**_kwargs: object) -> tuple[list[str | None], dict[int, Damage]]:
        return _snapshot({name: health[name] for name in ctrl.state.fleet[1:] if name})

    page.read_repair_snapshot.side_effect = snapshot

    def change(_page: object, fleet: list[str]) -> tuple[list[str | None], dict[int, Damage]]:
        ctrl.state.fleet = fleet.copy()
        return snapshot()

    monkeypatch.setattr(ctrl, '_verify_prepared_fleet', change)

    def reenter() -> None:
        for name in ships:
            end = ctrl._ctx.get_ship(name).repair_end_time
            if end and clock() >= end:
                health[name] = Damage.NORMAL
        if ctrl._prepare_available_fleet(page):
            page.start_battle()
            ctrl.state.phase = DecisivePhase.CHAPTER_CLEAR

    monkeypatch.setattr(ctrl, '_handle_enter_map', reenter)
    assert not ctrl._prepare_available_fleet(page)
    assert ctrl._main_loop() is expected
    if expected is DecisiveResult.ERROR:
        assert '保留存档：U-0' in ctrl._repairs.poll().detail
        assert ctrl._repairs.saved
    assert observed_waits == expected_waits
    bath.go_to_choose_repair.assert_called_once()
    ctrl._ctx.ctrl.click.assert_not_called()
    page.repair_slots.assert_not_called()
    assert page.start_battle.call_count == int(expected is DecisiveResult.CHAPTER_CLEAR)
    assert ctrl._ctx.get_ship(ships[0]).repair_end_time == 0
    if expected is DecisiveResult.CHAPTER_CLEAR:
        assert ship_name_identity(ships[0]) in ctrl._repairs.blocked_identities
        assert ships[0] not in ctrl.state.fleet
    ctrl._map.leave_to_overview.assert_called_once()
