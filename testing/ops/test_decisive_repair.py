"""决战修理按同帧舰名确认，到期后必须重新观察。"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from autowsgr.constants import ship_name_identity
from autowsgr.context import GameContext
from autowsgr.emulator.frame import CapturedFrame
from autowsgr.infra import ActionFailedError, DecisiveConfig, EmulatorConfig, UserConfig
from autowsgr.ops.decisive.controller import DecisiveController
from autowsgr.ops.decisive.repair import RepairOutcome, RepairStatus
from autowsgr.types import OSType
from autowsgr.types import ShipDamageState as Damage
from autowsgr.ui.bath_page.page import RepairShipInfo
from autowsgr.ui.bath_page.recognition import _ocr_card
from autowsgr.ui.battle.blood import BLOOD_GREEN, classify_blood
from autowsgr.ui.battle.constants import BLOOD_BAR_PROBE
from autowsgr.ui.decisive.preparation import (
    _REPAIR_MARKER,
    _REPAIR_SLOT_OFFSETS,
    DecisiveBattlePreparationPage,
)
from autowsgr.ui.utils.navigation import NavigationError
from autowsgr.vision import Color
from autowsgr.vision.ocr import OCRResult


def _controller(threshold: int | None = 60, count: int = 4) -> tuple[DecisiveController, MagicMock]:
    settings = UserConfig(
        emulator=EmulatorConfig(serial='127.0.0.1:5555', path='/tmp/emulator'),
        os_type=OSType.linux,
        repair_manually=False,
    )
    config = DecisiveConfig(level1=[f'U-{i}' for i in range(count)], level2=[])
    ctx = GameContext(ctrl=MagicMock(), config=settings, ocr=MagicMock())
    ctrl = DecisiveController(
        ctx,
        config,
        user_config=settings.model_copy(update={'quick_repair_threshold_seconds': threshold}),
    )
    clock = MagicMock(return_value=1000)
    ctrl._repairs._clock = clock
    return ctrl, clock


def _snapshot(states: dict[str, Damage]) -> tuple[list[str | None], dict[int, Damage]]:
    names = list(states)
    names.extend([None] * (6 - len(names)))
    return names, {i: states[name] if name else Damage.NO_SHIP for i, name in enumerate(names)}


def _prepare(
    controller: DecisiveController, states: dict[str, Damage], page: MagicMock | None = None
) -> RepairOutcome:
    names, damage = _snapshot(states)
    return controller._repairs.prepare(
        page or MagicMock(),
        fleet=names,
        damage=damage,
        acquired=controller._config.level1,
        chapter=1,
        stage=1,
    )


def _save(controller: DecisiveController, monkeypatch: pytest.MonkeyPatch) -> RepairOutcome:
    monkeypatch.setattr('autowsgr.ops.decisive.repair.goto_page', MagicMock())
    controller._repairs.save_progress(MagicMock(), MagicMock())
    return controller._repairs.dispatch_pending()


def test_marker_precedes_green_blood_and_reads_names_on_same_frame() -> None:
    frame = np.zeros((540, 960, 3), dtype=np.uint8)
    for slot, offset in enumerate(_REPAIR_SLOT_OFFSETS):
        for x, y, color in _REPAIR_MARKER:
            frame[y, x + offset] = color.as_rgb_tuple()
        bx, by = BLOOD_BAR_PROBE[slot]
        frame[int(by * 540), int(bx * 960)] = BLOOD_GREEN.as_rgb_tuple()

    page = object.__new__(DecisiveBattlePreparationPage)
    page._ctrl = MagicMock()
    page._ctrl.screenshot.return_value = frame
    page.detect_fleet = MagicMock(return_value=[f'U-{i}' for i in range(6)])
    names, damage = page.read_repair_snapshot()
    assert len(names) == 6
    assert list(damage.values()) == [Damage.REPAIRING] * 6
    page.detect_fleet.assert_called_once_with(frame)
    page._ctrl.screenshot.assert_called_once()
    frame[220, 49] = 0
    assert page.detect_repair_damage(frame)[0] is Damage.NORMAL
    frame[int(BLOOD_BAR_PROBE[0][1] * 540), int(BLOOD_BAR_PROBE[0][0] * 960)] = 255
    assert page.detect_repair_damage(frame)[0] is classify_blood(Color.of(255, 255, 255))


def test_missing_flagship_and_reserve_names_require_one_complete_frame() -> None:
    ctrl, _ = _controller()
    fleet = ['U-47', 'U-1206', '351', '鲃鱼', 'U-96', 'M-296']
    ctrl._state.ships = set(fleet)
    ctrl._repairs.observe_inventory = MagicMock()
    damage = dict.fromkeys(range(6), Damage.NORMAL)
    page = MagicMock()
    # 实机首槽「147」、第四槽「鱼」均与舰名库的多个名字并列，各自留下空名。
    page.read_repair_snapshot.side_effect = [
        ([None, *fleet[1:]], {**damage, 1: Damage.SEVERE}),
        ([*fleet[:3], None, *fleet[4:]], {**damage, 2: Damage.SEVERE}),
        (fleet, damage),
    ]
    assert ctrl._observe_repairs(page) == (fleet, damage)
    calls = page.read_repair_snapshot.call_args_list
    assert len(calls) == 3
    assert not calls[0].kwargs
    assert all(c.kwargs['fresh'] and 0 < c.kwargs['timeout'] <= 2 for c in calls[1:])
    assert ctrl._state.fleet[1:] == fleet
    ctrl._repairs.observe_inventory.assert_called_once_with(
        set(fleet),
        chapter=ctrl._state.chapter,
        stage=ctrl._state.stage,
        damage=dict.fromkeys(fleet, Damage.NORMAL),
    )


@pytest.mark.parametrize('stale', [False, True])
def test_unresolved_slot_keeps_original_failure_and_inventory(stale: bool) -> None:
    ctrl, _ = _controller()
    ctrl._repairs.observe_inventory = MagicMock()
    page = MagicMock()
    # 第三次实机失败时，末槽的 U-96 被读作「496」，但血条仍在。
    partial = (
        ['U-2540', 'U-1206', '351', '鲃鱼', 'U-47', None],
        dict.fromkeys(range(6), Damage.NORMAL),
    )
    if stale:
        page.read_repair_snapshot.side_effect = [partial, ActionFailedError('未取得新帧')]
    else:
        page.read_repair_snapshot.return_value = partial
    with pytest.raises(RuntimeError, match='决战准备页未能确认全部舰船的名称和伤情'):
        ctrl._observe_repairs(page)
    assert page.read_repair_snapshot.call_count == (2 if stale else 6)
    ctrl._repairs.observe_inventory.assert_not_called()
    page.repair_slots.assert_not_called()


def test_blind_recheck_uses_actual_identity_and_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl, clock = _controller()
    repairs = ctrl._repairs
    states = dict.fromkeys(ctrl._config.level1, Damage.NORMAL)
    states['U-0'] = Damage.REPAIRING
    assert _prepare(ctrl, states).status is RepairStatus.NEEDS_BATH
    outcome = _save(ctrl, monkeypatch)
    assert (outcome.status, outcome.wait_seconds, outcome.target_size) == (
        RepairStatus.WAITING,
        180,
        4,
    )
    clock.return_value += 179
    _prepare(ctrl, states)
    assert repairs.poll().wait_seconds == 1
    clock.return_value += 1
    assert repairs.poll().status is RepairStatus.REENTER
    # 另一艘舰的绿血不能证明 U-0 已修好。
    repairs.observe_inventory(states, chapter=1, stage=1, damage={'U-1': Damage.NORMAL})
    assert repairs.due_identities == {ship_name_identity('U-0')}
    assert repairs.blocked_identities
    _prepare(ctrl, states)
    assert repairs.poll().wait_seconds == 180
    clock.return_value += 180
    states['U-0'] = Damage.NORMAL
    assert _prepare(ctrl, states).status is RepairStatus.READY
    assert not repairs.blocked_identities


def test_known_end_time_honored_then_rechecked(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl, clock = _controller(count=1)
    ctrl._ctx.get_ship('U-0').repair_end_time = clock() + 12
    _prepare(ctrl, {'U-0': Damage.REPAIRING})
    assert _save(ctrl, monkeypatch).wait_seconds == 12
    clock.return_value += 12
    assert ctrl._repairs.poll().status is RepairStatus.REENTER
    _prepare(ctrl, {'U-0': Damage.REPAIRING})
    assert ctrl._repairs.poll().wait_seconds == 180


def test_inventory_only_reserve_wakes_at_its_registered_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctrl, clock = _controller(count=2)
    reserve = ctrl._ctx.get_ship('U-1')
    reserve.repair_end_time = clock() + 738
    assert _prepare(ctrl, {'U-0': Damage.NORMAL}).status is RepairStatus.NEEDS_BATH
    waiting = _save(ctrl, monkeypatch)
    assert (waiting.status, waiting.wait_seconds, waiting.target_size) == (
        RepairStatus.WAITING,
        738,
        2,
    )
    clock.return_value += 738
    assert ctrl._repairs.poll().status is RepairStatus.REENTER
    assert ship_name_identity('U-1') in ctrl._repairs.blocked_identities
    assert _prepare(ctrl, {'U-0': Damage.NORMAL, 'U-1': Damage.NORMAL}).status is RepairStatus.READY
    assert reserve.repair_end_time == 0


def test_blind_recheck_survives_stage_change_without_transferring_ownership() -> None:
    ctrl, clock = _controller(count=2)
    repairs = ctrl._repairs
    repairs.observe_inventory(['U-0'], chapter=1, stage=1, damage={'U-0': Damage.REPAIRING})
    assert ctrl._ctx.get_ship('U-0').repair_recheck_at == clock() + 180
    clock.return_value += 120
    repairs.reset_stage()
    repairs.observe_inventory(['U-1'], chapter=1, stage=2)
    assert repairs.acquired == ('U-1',)
    assert repairs.target_size == 1
    assert not repairs.blocked_identities
    repairs.observe_inventory(['U-0'], chapter=1, stage=2)
    assert repairs.target_size == 2
    assert ship_name_identity('U-0') in repairs.blocked_identities
    clock.return_value += 60
    assert repairs.due_identities == {ship_name_identity('U-0')}
    repairs.observe_inventory(['U-1'], chapter=1, stage=2, damage={'U-1': Damage.NORMAL})
    assert repairs.due_identities == {ship_name_identity('U-0')}
    repairs.observe_inventory(['U-0'], chapter=1, stage=2, damage={'U-0': Damage.NORMAL})
    assert not repairs.due_identities


def test_registered_aliases_share_the_same_repair_record() -> None:
    ctrl, clock = _controller()
    canonical = ctrl._ctx.get_ship('赛尔弗里吉')
    canonical.record_bath(clock() + 17)
    alias = ctrl._ctx.get_ship('塞尔弗里奇')
    assert alias is canonical
    ctrl._repairs.observe_inventory([alias.name, '塞尔弗里奇'], chapter=1, stage=1)
    assert ctrl._repairs.acquired == (canonical.name,)
    clock.return_value += 17
    assert ctrl._repairs.due_identities == {ship_name_identity('塞尔弗里奇')}


def test_six_healthy_reserves_release_eight_ship_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl, _ = _controller(count=8)
    states = dict.fromkeys(ctrl._config.level1[:6], Damage.NORMAL)
    states['U-0'] = states['U-1'] = Damage.REPAIRING
    _prepare(ctrl, states)
    assert _save(ctrl, monkeypatch).target_size == 6
    ctrl._repairs.observe_inventory(
        ctrl._config.level1, chapter=1, stage=1, damage={'U-6': Damage.NORMAL, 'U-7': Damage.NORMAL}
    )
    assert ctrl._repairs.poll().status is RepairStatus.REENTER
    healthy = dict.fromkeys(ctrl._config.level1[2:], Damage.NORMAL)
    assert _prepare(ctrl, healthy).status is RepairStatus.READY


def _bath(
    monkeypatch: pytest.MonkeyPatch, ctrl: DecisiveController, cards: list[RepairShipInfo]
) -> MagicMock:
    bath = MagicMock()
    bath.has_choose_repair_overlay.return_value = False
    bath.is_current_page.return_value = True
    bath.wait_repair_accepted.return_value = True
    bath.recognize_repair_ships.return_value = cards
    monkeypatch.setattr('autowsgr.ops.decisive.repair.BathPage', lambda _ctx: bath)
    monkeypatch.setattr(ctrl._ctx.stop_event, 'wait', lambda _: None)
    return bath


@pytest.mark.parametrize('duration', ['', '00:99:00'])
def test_unreadable_duration_fails_without_dispatch(
    monkeypatch: pytest.MonkeyPatch, duration: str
) -> None:
    ctrl, _ = _controller(threshold=0, count=1)
    card = RepairShipInfo('U-0', (0.1, 0.5), duration)
    bath = _bath(monkeypatch, ctrl, [card])
    _prepare(ctrl, {'U-0': Damage.SEVERE})
    outcome = _save(ctrl, monkeypatch)
    assert outcome.status is RepairStatus.RECHECK
    assert outcome.targets == ('U-0',)
    assert outcome.wait_seconds is None
    assert 'U-0' in outcome.detail
    bath._swipe_left.assert_not_called()
    bath.recognize_repair_ships.assert_called_once()
    ctrl._ctx.ctrl.click.assert_not_called()
    assert not ctrl._repairs.due_identities
    assert ctrl._ctx.get_ship('U-0').repair_end_time == 0


@pytest.mark.parametrize(('duration', 'seconds'), [('00:00:00', 0), ('00:00:59', 59)])
def test_valid_short_quote_dispatched_once(
    monkeypatch: pytest.MonkeyPatch, duration: str, seconds: int
) -> None:
    ctrl, clock = _controller(count=1)
    card = RepairShipInfo('U-0', (0.1, 0.5), duration)
    _bath(monkeypatch, ctrl, [card])
    _prepare(ctrl, {'U-0': Damage.SEVERE})
    outcome = _save(ctrl, monkeypatch)
    assert outcome.status is (RepairStatus.REENTER if seconds == 0 else RepairStatus.WAITING)
    ctrl._repairs.dispatch_pending()
    ctrl._ctx.ctrl.click.assert_called_once_with(*card.position)
    assert ctrl._ctx.get_ship('U-0').repair_end_time == clock() + seconds


@pytest.mark.parametrize('threshold', [0, 60])
def test_equal_threshold_authorizes_bucket_only_for_matching_name(
    monkeypatch: pytest.MonkeyPatch, threshold: int | None
) -> None:
    ctrl, _ = _controller(threshold=threshold, count=1)
    damaged = {'U-0': Damage.SEVERE}
    duration = '00:01:00' if threshold else '00:00:00'
    card = RepairShipInfo('U-0', (0.1, 0.5), duration)
    _bath(monkeypatch, ctrl, [card])
    _prepare(ctrl, damaged)
    assert _save(ctrl, monkeypatch).status is RepairStatus.REENTER
    ctrl._ctx.ctrl.click.assert_not_called()
    page = MagicMock()
    page.read_repair_snapshot.side_effect = [_snapshot(damaged), _snapshot({'U-0': Damage.NORMAL})]
    assert _prepare(ctrl, damaged, page).status is RepairStatus.READY
    page.repair_slots.assert_called_once_with([0])
    assert all(call.kwargs == {'fresh': True} for call in page.read_repair_snapshot.call_args_list)


def test_default_repair_needs_no_quote() -> None:
    ctrl, _ = _controller(threshold=None, count=1)
    page = MagicMock()
    state = {'U-0': Damage.SEVERE}
    page.read_repair_snapshot.side_effect = [_snapshot(state), _snapshot({'U-0': Damage.NORMAL})]
    outcome = _prepare(ctrl, state, page)
    assert outcome.status is RepairStatus.READY
    assert outcome.snapshot == _snapshot({'U-0': Damage.NORMAL})
    assert page.read_repair_snapshot.call_count == 2
    page.repair_slots.assert_called_once_with([0])
    assert all(call.kwargs == {'fresh': True} for call in page.read_repair_snapshot.call_args_list)


def test_full_bath_retains_name_and_stops_before_next_click(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctrl, clock = _controller(count=1)
    ctrl._ctx.bathroom = MagicMock()
    ctrl._ctx.bathroom.is_available.return_value = False
    ctrl._ctx.bathroom.get_waiting_time.return_value = 25
    card = RepairShipInfo('U-0', (0.1, 0.5), '00:00:15')
    _bath(monkeypatch, ctrl, [card])
    _prepare(ctrl, {'U-0': Damage.SEVERE})
    outcome = _save(ctrl, monkeypatch)
    assert (outcome.targets, outcome.wait_seconds) == (('U-0',), 25)
    clock.return_value += 25
    assert ctrl._repairs.poll().status is RepairStatus.NEEDS_BATH
    ctrl._ctx.stop_event.set()
    assert ctrl._repairs.dispatch_pending().status is RepairStatus.STOPPED
    ctrl._ctx.ctrl.click.assert_not_called()


def test_stop_after_opening_quick_repair_panel_spends_no_bucket() -> None:
    ctrl, _ = _controller(threshold=None, count=1)
    page = DecisiveBattlePreparationPage(ctrl._ctx, ctrl._config, MagicMock())
    page.select_panel = MagicMock(side_effect=lambda _panel: ctrl._ctx.stop_event.set())
    page.repair_slots([0])
    ctrl._ctx.ctrl.click.assert_not_called()


def test_fresh_snapshot_skips_cached_decoded_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl, _clock = _controller(count=1)
    page = DecisiveBattlePreparationPage(ctrl._ctx, ctrl._config, MagicMock())
    stale = np.zeros((540, 960, 3), dtype=np.uint8)
    new = np.zeros_like(stale)
    page._ctrl.capture_frame.side_effect = [
        CapturedFrame(stale, 42, 120),
        CapturedFrame(new, 43, 181),
    ]
    monkeypatch.setattr('autowsgr.ui.decisive.preparation.time.monotonic', lambda: 180.0)
    page.detect_fleet = MagicMock(return_value=['胡德', *([None] * 5)])
    page.detect_repair_damage = MagicMock(return_value={0: Damage.NORMAL})
    page.read_repair_snapshot(fresh=True)
    assert page.detect_fleet.call_args.args[0] is new
    assert page.detect_repair_damage.call_args.args[0] is new


@pytest.mark.parametrize('raw', ['', '00:00:00'])
def test_real_bath_card_preserves_missing_time(raw: str) -> None:
    ocr = MagicMock()
    name = OCRResult('胡德', 1, (10, 125, 60, 140))
    ocr.recognize.side_effect = [[name], [OCRResult(raw, 1, (0, 0, 60, 10))]]
    card = _ocr_card(np.zeros((480, 160, 3), np.uint8), ocr, 100, 160, 1280)
    assert card is not None
    assert (card.name, card.repair_time) == ('胡德', raw)


def test_bath_refuses_to_open_keeps_pending_and_backs_off(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl, clock = _controller(count=1)
    bath = _bath(monkeypatch, ctrl, [])
    bath.go_to_choose_repair.side_effect = NavigationError('overlay unavailable')
    _prepare(ctrl, {'U-0': Damage.SEVERE})
    result = _save(ctrl, monkeypatch)
    assert (result.status, result.wait_seconds, result.targets) == (
        RepairStatus.WAITING,
        5,
        ('U-0',),
    )
    clock.return_value += 5
    assert ctrl._repairs.poll().status is RepairStatus.NEEDS_BATH
    ctrl._ctx.ctrl.click.assert_not_called()


def test_controller_requests_a_fresh_frame_only_after_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctrl, clock = _controller(count=1)
    ctrl._state.chapter = ctrl._state.stage = 1
    ctrl._state.ships = {'U-0'}
    states = {'U-0': Damage.REPAIRING}
    page = MagicMock()
    page.read_repair_snapshot.return_value = _snapshot(states)
    ctrl._observe_repairs(page)
    _prepare(ctrl, states)
    assert _save(ctrl, monkeypatch).wait_seconds == 180
    clock.return_value += 179
    ctrl._observe_repairs(page)
    page.read_repair_snapshot.assert_called_with()
    assert ctrl._repairs.poll().wait_seconds == 1
    clock.return_value += 1
    page.read_repair_snapshot.return_value = _snapshot({'U-0': Damage.NORMAL})
    ctrl._observe_repairs(page)
    page.read_repair_snapshot.assert_called_with(fresh=True)
    assert not ctrl._repairs.blocked_identities
    assert ctrl._repairs.poll().status is RepairStatus.REENTER


def test_bucket_retry_requires_a_fresh_frame_after_first_click() -> None:
    ctrl, _ = _controller(threshold=None, count=1)
    page = MagicMock()
    states = {'U-0': Damage.SEVERE}
    page.read_repair_snapshot.side_effect = [_snapshot(states), ActionFailedError('没有新帧')]
    with pytest.raises(ActionFailedError, match='没有新帧'):
        _prepare(ctrl, states, page)
    page.read_repair_snapshot.assert_called_with(fresh=True)
    page.repair_slots.assert_called_once_with([0])


@pytest.mark.parametrize('after_click', [False, True])
def test_other_slots_must_match_before_and_after_each_bucket(after_click: bool) -> None:
    ctrl, _ = _controller(threshold=None, count=3)
    states = {'U-0': Damage.SEVERE, 'U-1': Damage.NORMAL, 'U-2': Damage.NORMAL}
    names, damage = _snapshot(states)
    ctrl.state.fleet = ['', *(name or '' for name in names)]
    ctrl.state.ships = set(states)
    changed = (['U-0', 'U-2', 'U-1', None, None, None], {**damage, 0: Damage.NORMAL})
    recovered = (names, {**damage, 0: Damage.NORMAL})
    corrected = recovered if after_click else (names, damage)
    page = MagicMock()
    ctrl._verify_prepared_fleet = MagicMock()
    frames = [(names, damage)]  # 准备页入口
    if after_click:
        frames.append((names, damage))
    frames.extend([changed, corrected])
    if not after_click:
        frames.append(recovered)
    page.read_repair_snapshot.side_effect = [*frames, recovered]

    def verify(*_args, **_kwargs) -> None:
        assert page.repair_slots.call_count == int(after_click)
        assert ctrl._ctx.quick_repair_used == 0

    ctrl._verify_prepared_fleet.side_effect = verify
    assert ctrl._prepare_repairs(page)
    ctrl._verify_prepared_fleet.assert_called_once_with(page, ctrl.state.fleet, force_change=True)
    page.repair_slots.assert_called_once_with([0])
    assert ctrl._ctx.quick_repair_used == 1


@pytest.mark.parametrize('after_click', [False, True])
def test_missing_other_name_never_partially_updates_or_repeats_bucket(after_click: bool) -> None:
    ctrl, _ = _controller(threshold=None, count=2)
    states = {'U-0': Damage.SEVERE, 'U-1': Damage.NORMAL}
    names, damage = _snapshot(states)
    unreadable = (['U-0', *([None] * 5)], {**damage, 0: Damage.NORMAL})
    page = MagicMock()
    page.read_repair_snapshot.side_effect = ([(names, damage)] if after_click else []) + [
        unreadable,
        unreadable,
        ActionFailedError('未取得新帧'),
    ]
    with pytest.raises(RuntimeError, match='未能确认全部舰船'):
        _prepare(ctrl, states, page)
    assert page.repair_slots.call_count == int(after_click)
    assert ctrl._ctx.quick_repair_used == 0
    assert ctrl._repairs.damaged_identities == {ship_name_identity('U-0')}


@pytest.mark.parametrize(('threshold', 'clicks'), [(60, 1), (None, 3)])
def test_unconfirmed_bucket_rechecks_identity_before_any_next_click(
    threshold: int | None, clicks: int
) -> None:
    ctrl, _ = _controller(threshold=threshold, count=2)
    states = {'U-0': Damage.SEVERE, 'U-1': Damage.SEVERE}
    names, damage = _snapshot(states)
    repairs = ctrl._repairs
    repairs.observe_inventory(states, chapter=1, stage=1, damage=states)
    if threshold is not None:
        repairs._long_repairs.update(ship_name_identity(name) for name in states)
    page = MagicMock()
    page.read_repair_snapshot.return_value = (names, damage)
    for _ in range(2):
        with pytest.raises(ActionFailedError, match='未确认 U-0 恢复'):
            _prepare(ctrl, states, page)
        assert [c.args[0] for c in page.repair_slots.call_args_list] == [[0]] * clicks
        assert ctrl._ctx.quick_repair_used == 0
    partially_recovered = (names, {**damage, 0: Damage.NORMAL})
    page.read_repair_snapshot.side_effect = [
        partially_recovered,
        partially_recovered,
        (names, {**damage, 0: Damage.NORMAL, 1: Damage.NORMAL}),
    ]
    assert _prepare(ctrl, states, page).status is RepairStatus.READY
    assert [c.args[0] for c in page.repair_slots.call_args_list] == [[0]] * clicks + [[1]]
    assert ctrl._ctx.quick_repair_used == 2
    assert all(c.kwargs == {'fresh': True} for c in page.read_repair_snapshot.call_args_list)


def test_no_frame_sequence_requires_changed_pixels_to_prove_redraw() -> None:
    ctrl, _ = _controller(count=1)
    page = DecisiveBattlePreparationPage(ctrl._ctx, ctrl._config, MagicMock())
    stale = np.zeros((1, 1, 3), np.uint8)
    new = np.ones_like(stale)
    page._ctrl.capture_frame.side_effect = [
        CapturedFrame(stale, None, 0),
        CapturedFrame(stale.copy(), None, 10),
        CapturedFrame(new, None, 20),
    ]
    page.detect_fleet = MagicMock(return_value=['胡德', *([None] * 5)])
    page.detect_repair_damage = MagicMock(return_value={0: Damage.NORMAL})
    page.read_repair_snapshot(fresh=True)
    assert page.detect_fleet.call_args.args[0] is new
    assert page.detect_repair_damage.call_args.args[0] is new


@pytest.mark.parametrize(('count', 'buckets'), [(8, 1), (9, 0)])
def test_short_bath_precedes_lineup_and_buckets_cover_only_shortfall(
    monkeypatch: pytest.MonkeyPatch, count: int, buckets: int
) -> None:
    # 三艘受伤，一艘短修，两艘长修；健康替补数决定要不要用桶。
    ctrl, _ = _controller(threshold=1800, count=count)
    ctrl.state.chapter = ctrl.state.stage = 1
    ships = ctrl._config.level1
    ctrl.state.ships = set(ships)
    ctrl.state.fleet = ['', *ships[:6]]
    health = dict.fromkeys(ships, Damage.NORMAL)
    health.update(dict.fromkeys(ships[:3], Damage.SEVERE))
    events = []
    page = MagicMock()

    def snapshot(**_kwargs: bool) -> tuple[list[str | None], dict[int, Damage]]:
        return _snapshot({name: health[name] for name in ctrl.state.fleet[1:] if name})

    def change(_page: object, target: list[str]) -> tuple[list[str | None], dict[int, Damage]]:
        events.append('编队')
        ctrl.state.fleet = target.copy()
        return snapshot()

    def bucket(slots: list[int]) -> None:
        [slot] = slots
        name = ctrl.state.fleet[slot + 1]
        events.append(name)
        health[name] = Damage.NORMAL

    page.read_repair_snapshot.side_effect = snapshot
    page.repair_slots.side_effect = bucket
    monkeypatch.setattr(ctrl, '_verify_prepared_fleet', change)
    ctrl._map = MagicMock()
    ctrl._route_repair = MagicMock()
    monkeypatch.setattr('autowsgr.ops.decisive.repair.goto_page', MagicMock())
    _bath(
        monkeypatch,
        ctrl,
        [
            RepairShipInfo(ships[0], (0.1, 0.5), '00:29:59'),
            RepairShipInfo(ships[1], (0.3, 0.5), '00:30:00'),
            RepairShipInfo(ships[2], (0.5, 0.5), '00:30:01'),
        ],
    )
    ctrl._ctx.ctrl.click.side_effect = lambda *_pos: events.append('入浴')
    assert not ctrl._prepare_available_fleet(page)
    assert events == []
    assert ctrl._repairs.dispatch_pending().status is RepairStatus.REENTER
    assert events == ['入浴']
    ctrl._ctx.ctrl.click.assert_called_once_with(0.1, 0.5)
    assert ctrl._prepare_available_fleet(page)
    assert page.repair_slots.call_count == buckets
    if buckets:
        assert events[-1] == ships[1]
    assert ships[0] not in ctrl.state.fleet
    assert all(health[name] is Damage.NORMAL for name in ctrl.state.fleet[1:])


def test_short_repairs_rejoin_only_after_verified_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctrl, clock = _controller(threshold=1800, count=2)
    states = {'U-0': Damage.NORMAL, 'U-1': Damage.SEVERE}
    _bath(monkeypatch, ctrl, [RepairShipInfo('U-1', (0.1, 0.5), '00:29:59')])
    page = MagicMock()
    assert _prepare(ctrl, states, page).status is RepairStatus.NEEDS_BATH
    result = _save(ctrl, monkeypatch)
    assert (result.status, result.wait_seconds) == (RepairStatus.WAITING, 1799)
    clock.return_value += 1799
    assert ctrl._repairs.poll().status is RepairStatus.REENTER
    states['U-1'] = Damage.REPAIRING
    assert _prepare(ctrl, states, page).status is RepairStatus.NEEDS_BATH
    assert ctrl._repairs.poll().wait_seconds == 180
    clock.return_value += 180
    states['U-1'] = Damage.NORMAL
    assert _prepare(ctrl, states, page).status is RepairStatus.READY
    page.repair_slots.assert_not_called()


def test_final_battle_damage_is_dispatched_from_overview(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl, _ = _controller(threshold=1800)
    names = ctrl._config.level1
    ctrl._repairs.observe_inventory(
        names, chapter=6, stage=3, damage={names[0]: Damage.SEVERE, names[1]: Damage.SEVERE}
    )
    _bath(
        monkeypatch,
        ctrl,
        [
            RepairShipInfo(names[0], (0.1, 0.5), '00:01:00'),
            RepairShipInfo(names[1], (0.5, 0.5), '01:00:00'),
        ],
    )
    monkeypatch.setattr('autowsgr.ops.decisive.repair.goto_page', MagicMock())
    assert ctrl._repairs.park_after_settlement()
    assert ctrl._repairs.dispatch_pending().status is RepairStatus.REENTER
    ctrl._ctx.ctrl.click.assert_called_once_with(0.1, 0.5)


def test_bath_deadline_counts_from_dispatch_click(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl, clock = _controller(threshold=1800, count=1)
    bath = _bath(monkeypatch, ctrl, [RepairShipInfo('U-0', (0.1, 0.5), '00:00:30')])

    def confirm() -> bool:
        clock.return_value += 2
        return True

    bath.wait_repair_accepted.side_effect = confirm
    _prepare(ctrl, {'U-0': Damage.MODERATE})
    assert _save(ctrl, monkeypatch).wait_seconds == 28
