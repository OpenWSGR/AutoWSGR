"""识别统计只借助去除敌情后的定位核对，不用识别结果自证正确。"""

from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any

import pytest
from autowsgr_native.vessel_type import VesselType

from autowsgr.combat.node_fusion.calibration import (
    CalibrationTotals,
    RecognitionCount,
    RecognitionStats,
    recognition_stats,
)
from autowsgr.combat.node_fusion.enemy import EnemyObservation
from autowsgr.combat.node_fusion.map import TrackingMap
from autowsgr.combat.node_fusion.model import FusionObservation, FusionProfile, FusionTracker


def _node(
    next_nodes: tuple[str, ...],
    *,
    ship: str = '驱逐',
    position: tuple[float, float] = (0.5, 0.5),
    silent: bool = False,
) -> dict[str, Any]:
    return {
        'position': list(position),
        'next': list(next_nodes),
        'type': 'NULL' if silent else 'FIGTH',
        'detour': False,
        'enemy_formations': [] if silent else [{'formation': 1, 'ships': [ship] * 6}],
    }


def _tracker(raw: dict[str, Any] | None = None) -> FusionTracker:
    return FusionTracker(
        TrackingMap.from_dict(raw or {'0': _node(('A',), silent=True), 'A': _node(())}),
        FusionProfile(min_travel_seconds=None),
    )


def _enemy(ship: str = '驱逐', formation: int | None = 1) -> EnemyObservation:
    code = next(
        value.as_english()
        for name in dir(VesselType)
        if isinstance(value := getattr(VesselType, name), VesselType) and value.as_chinese() == ship
    )
    return EnemyObservation(
        raw_slots=(code,) * 6,
        ships=(ship,) * 6,
        formation=formation,
        formation_text='' if formation is None else str(formation),
        formation_confidence=None,
        detour=None,
        detour_score=None,
    )


def _spot(tracker: FusionTracker, time: float, enemy: EnemyObservation | None) -> None:
    estimate = tracker.observe(
        FusionObservation(
            'phase', time, frame_id=f'spot-{time}', phase='SPOT_ENEMY_SUCCESS', enemies=enemy
        )
    )
    assert estimate.anomaly is None


def _motion(tracker: FusionTracker, time: float, position: tuple[float, float]) -> None:
    estimate = tracker.observe(
        FusionObservation('motion', time, frame_id=f'motion-{time}', position=position)
    )
    assert estimate.anomaly is None


def _proceed(tracker: FusionTracker, time: float) -> None:
    tracker.observe(FusionObservation('phase', time, phase='RESULT'))
    tracker.observe(FusionObservation('action', time + 0.1, action='proceed', clicked=True))


@pytest.mark.parametrize(
    ('value', 'expected', 'attempted', 'bucket'),
    [
        ('驱逐', {'驱逐'}, True, 'correct'),
        ('战列', {'驱逐'}, True, 'errors'),
        (None, {'驱逐'}, True, 'missing'),
        ('驱逐', {'驱逐', '战列'}, True, 'ambiguous'),
        (None, {'驱逐', '战列'}, True, 'ambiguous'),
        ('驱逐', None, True, 'no_reference'),
        (None, set(), True, 'no_reference'),
        (None, {1}, False, 'not_attempted'),
        (None, None, False, 'not_attempted'),
        (None, {None}, True, 'empty'),
        ('驱逐', {None}, True, 'empty'),
    ],
)
def test_recognition_buckets_are_mutually_exclusive(
    value: object, expected: set[object] | None, attempted: bool, bucket: str
) -> None:
    count = RecognitionCount()
    count.observe(value, expected, attempted=attempted)
    fields = asdict(count)
    assert fields.pop('total') == 1
    assert fields[bucket] == 1
    assert sum(fields.values()) == 1


def test_unique_node_counts_native_slot_error_and_missing_no() -> None:
    tracker = _tracker()
    enemy = replace(
        _enemy(formation=2),
        raw_slots=('BB', 'NO', 'DD', 'DD', 'DD', 'DD'),
        ships=('战列', None, '驱逐', '驱逐', '驱逐', '驱逐'),
    )
    _spot(tracker, 1.0, enemy)
    stats = recognition_stats(tracker)
    assert stats.samples == stats.located == 1
    assert stats.ships == RecognitionCount(total=6, correct=4, errors=1, missing=1)
    assert stats.ship_slots['1'] == RecognitionCount(total=1, errors=1)
    assert stats.ship_slots['2'] == RecognitionCount(total=1, missing=1)
    assert stats.ship_slots['3'] == RecognitionCount(total=1, correct=1)
    assert stats.ship_confusion == {'驱逐': {'BB': 1, 'NO': 1, 'DD': 4}}
    assert stats.ship_slot_confusion['1'] == {'驱逐': {'BB': 1}}
    assert stats.ship_slot_confusion['2'] == {'驱逐': {'NO': 1}}
    assert stats.ship_slot_confusion['3'] == {'驱逐': {'DD': 1}}


def test_multiple_variants_use_consensus_instead_of_matching_observed_variant() -> None:
    raw = {'0': _node(('A',), silent=True), 'A': _node(())}
    raw['A']['enemy_formations'].append(
        {'formation': 2, 'ships': ['战列', '驱逐', '驱逐', '驱逐', '驱逐', '驱逐']}
    )
    tracker = _tracker(raw)
    _spot(tracker, 1.0, _enemy())
    stats = recognition_stats(tracker)
    assert stats.located == 1
    assert stats.ships == RecognitionCount(total=6, correct=5, ambiguous=1)
    assert stats.ship_confusion == {'驱逐': {'DD': 5}}
    assert stats.ship_slots['1'] == RecognitionCount(total=1, ambiguous=1)
    assert stats.ship_slot_confusion['1'] == {}


def test_enemy_based_location_cannot_be_its_own_recognition_reference() -> None:
    tracker = _tracker(
        {
            '0': _node(('A', 'B'), silent=True),
            'A': _node(()),
            'B': _node((), ship='战列'),
        }
    )
    _spot(tracker, 1.0, _enemy())
    assert tracker.estimate.current_node == 'A'
    stats = recognition_stats(tracker)
    assert stats.samples == 1
    assert stats.located == 0
    assert stats.ships == RecognitionCount(total=6, no_reference=6)
    assert stats.ship_confusion == {}
    assert all(not matrix for matrix in stats.ship_slot_confusion.values())


@pytest.mark.parametrize('first_failed', [False, True])
def test_repeated_page_keeps_first_read_even_when_later_read_succeeds(first_failed: bool) -> None:
    tracker = _tracker()
    first = None if first_failed else _enemy(ship='战列')
    _spot(tracker, 1.0, first)
    _spot(tracker, 2.0, _enemy())
    _spot(tracker, 3.0, _enemy())
    stats = recognition_stats(tracker)
    assert stats.samples == stats.located == 1
    assert stats.repeated == 2
    assert stats.ships == (
        RecognitionCount(total=6, missing=6)
        if first_failed
        else RecognitionCount(total=6, errors=6)
    )
    assert stats.ship_confusion == {'驱逐': {'MISSING' if first_failed else 'BB': 6}}


@pytest.mark.parametrize('failed_proceed', [False, True])
@pytest.mark.parametrize('first_failed', [False, True])
def test_recovered_location_keeps_unlocated_first_sample_in_same_encounter(
    failed_proceed: bool, first_failed: bool
) -> None:
    tracker = _tracker(
        {
            name: {
                'position': list(position),
                'enemy_formations': [{'formation': 1, 'ships': [ship] * 6}],
            }
            for name, position, ship in (
                ('A', (0.1, 0.1), '驱逐'),
                ('B', (0.9, 0.9), '战列'),
            )
        }
    )
    first = None if first_failed else _enemy(ship='战列')
    # 首次索敌缺少独立定位证据；后来识别成功不能替换这份未定位样本。
    tracker.observe(FusionObservation('phase', 1.0, phase='SPOT_ENEMY_SUCCESS', enemies=first))
    if failed_proceed:
        tracker.observe(FusionObservation('action', 1.5, action='proceed', clicked=False))
    _motion(tracker, 2.0, (0.1, 0.1))
    _spot(tracker, 3.0, _enemy())
    stats = recognition_stats(tracker)
    assert stats.samples == 1
    assert stats.repeated == 1
    assert stats.located == stats.ignored == 0
    assert stats.ships == RecognitionCount(total=6, no_reference=6)
    assert stats.ship_confusion == {}
    assert tracker.observations[0].enemies is first


def test_formation_and_detour_are_excluded_from_native_recognition_statistics() -> None:
    reports = []
    for enemy in (
        _enemy(),
        _enemy(formation=None),
        replace(_enemy(formation=5), detour=True),
    ):
        tracker = _tracker()
        _spot(tracker, 1.0, enemy)
        reports.append(asdict(recognition_stats(tracker)))
    assert reports[0] == reports[1] == reports[2]
    assert 'formation' not in reports[0]
    assert 'detour' not in reports[0]


def test_native_raw_code_controls_counts_even_when_converted_ships_disagree() -> None:
    tracker = _tracker()
    _spot(tracker, 1.0, replace(_enemy(), raw_slots=('BB',) * 6))
    stats = recognition_stats(tracker)
    assert stats.ships == RecognitionCount(total=6, errors=6)
    assert stats.ship_confusion == {'驱逐': {'BB': 6}}


@pytest.mark.parametrize(
    ('raw_slots', 'valid_slots', 'column'),
    [
        (('NO',) * 6, True, 'NO'),
        (('UNRECOGNIZED_CODE',) * 6, True, 'UNKNOWN'),
        (('DD',) * 5, True, 'INVALID_SLOTS'),
        (('DD',) * 7, True, 'INVALID_SLOTS'),
        (('DD',) * 6, False, 'INVALID_SLOTS'),
    ],
)
def test_invalid_native_result_is_missing_even_if_converted_ships_look_correct(
    raw_slots: tuple[str, ...], valid_slots: bool, column: str
) -> None:
    tracker = _tracker()
    _spot(tracker, 1.0, replace(_enemy(), raw_slots=raw_slots, valid_slots=valid_slots))
    stats = recognition_stats(tracker)
    assert stats.ships == RecognitionCount(total=6, missing=6)
    assert stats.ship_confusion == {'驱逐': {column: 6}}
    for slot in map(str, range(1, 7)):
        assert stats.ship_slots[slot] == RecognitionCount(total=1, missing=1)
        assert stats.ship_slot_confusion[slot] == {'驱逐': {column: 1}}


def test_unknown_native_codes_share_one_bounded_column() -> None:
    tracker = _tracker()
    _spot(tracker, 1.0, replace(_enemy(), raw_slots=tuple(f'unknown-{i}' for i in range(6))))
    stats = recognition_stats(tracker)
    assert stats.ships.missing == 6
    assert stats.ship_confusion == {'驱逐': {'UNKNOWN': 6}}


def test_empty_reference_slots_are_not_native_correct_samples_or_confusion_rows() -> None:
    raw = {'0': _node(('A',), silent=True), 'A': _node(())}
    raw['A']['enemy_formations'][0]['ships'] = ['驱逐'] * 4
    tracker = _tracker(raw)
    _spot(tracker, 1.0, replace(_enemy(), raw_slots=('DD',) * 4 + ('NO',) * 2))
    stats = recognition_stats(tracker)
    assert stats.ships == RecognitionCount(total=6, correct=4, empty=2)
    assert stats.ship_confusion == {'驱逐': {'DD': 4}}
    assert stats.ship_slot_confusion['5'] == stats.ship_slot_confusion['6'] == {}


def test_native_chinese_reference_mapping_follows_installed_enum() -> None:
    for name in dir(VesselType):
        value = getattr(VesselType, name)
        if not isinstance(value, VesselType) or value.as_english() == 'NO':
            continue
        chinese, code = value.as_chinese(), value.as_english()
        tracker = _tracker({'0': _node(('A',), silent=True), 'A': _node((), ship=chinese)})
        _spot(tracker, 1.0, replace(_enemy(), raw_slots=(code,) * 6))
        stats = recognition_stats(tracker)
        assert stats.ships == RecognitionCount(total=6, correct=6)
        assert stats.ship_confusion == {chinese: {code: 6}}


def test_later_geometry_revises_reference_for_earlier_recognition() -> None:
    tracker = _tracker(
        {
            '0': _node(('A', 'B'), position=(0.05, 0.1), silent=True),
            'A': _node((), position=(0.2, 0.2)),
            'B': _node(('C',), position=(0.2, 0.8), ship='战列'),
            'C': _node((), position=(0.85, 0.8), ship='战列'),
        }
    )
    _motion(tracker, 1.0, (0.2, 0.2))
    _motion(tracker, 1.2, (0.205, 0.2))
    _spot(tracker, 2.0, _enemy(ship='战列'))
    earlier = recognition_stats(tracker)
    assert earlier.located == 1
    assert earlier.ships.errors == 6
    _proceed(tracker, 3.0)
    _motion(tracker, 4.0, (0.85, 0.8))
    _spot(tracker, 5.0, _enemy(ship='战列'))
    revised = recognition_stats(tracker)
    assert revised.samples == revised.located == 2
    assert revised.ships == RecognitionCount(total=12, correct=12)
    assert earlier.ships.errors == 6


def test_returning_to_same_node_in_a_cycle_creates_another_sample() -> None:
    tracker = _tracker(
        {
            '0': _node(('A',), silent=True),
            'A': _node(('B',)),
            'B': _node(('A',), ship='战列'),
        }
    )
    _spot(tracker, 1.0, _enemy())
    _proceed(tracker, 2.0)
    _spot(tracker, 3.0, _enemy(ship='战列'))
    _proceed(tracker, 4.0)
    _spot(tracker, 5.0, _enemy())
    stats = recognition_stats(tracker)
    assert stats.samples == stats.located == 3
    assert stats.repeated == 0
    assert stats.ships == RecognitionCount(total=18, correct=18)


def test_totals_use_unique_sortie_deltas_and_independent_snapshots() -> None:
    totals = CalibrationTotals()
    first = RecognitionStats(samples=1, located=1, ships=RecognitionCount(total=6, correct=6))
    second = RecognitionStats(samples=1, ships=RecognitionCount(total=6, no_reference=6))
    first_payload = totals.add('first-sortie', first)
    assert first_payload is not None
    first_copy = asdict(first)
    assert first_payload['delta'] == first_payload['cumulative'] == first_copy
    assert first_payload['completed_sorties'] == 1
    assert totals.add('first-sortie', second) is None
    first.ships.correct = 0
    second_payload = totals.add('second-sortie', second)
    assert second_payload is not None
    assert first_payload['delta'] == first_payload['cumulative'] == first_copy
    assert second_payload['delta'] == asdict(second)
    assert second_payload['completed_sorties'] == 2
    assert second_payload['run_id'] == first_payload['run_id']
    assert second_payload['cumulative']['samples'] == 2
    assert second_payload['cumulative']['located'] == 1
    assert second_payload['cumulative']['ships'] == asdict(
        RecognitionCount(total=12, correct=6, no_reference=6)
    )
    first_payload['cumulative']['ships']['correct'] = 999
    third_payload = totals.add('third-sortie', RecognitionStats())
    assert third_payload is not None
    assert third_payload['cumulative']['ships']['correct'] == 6


def test_totals_recursively_accumulate_confusion_and_freeze_nested_snapshots() -> None:
    totals = CalibrationTotals()
    node = _tracker().map_data.nodes['A']
    first, second, third = RecognitionStats(), RecognitionStats(), RecognitionStats()
    first.observe(_enemy(), node)
    second.observe(_enemy(ship='战列'), node)
    third.observe(
        _enemy(),
        _tracker({'0': _node(('A',), silent=True), 'A': _node((), ship='战列')}).map_data.nodes[
            'A'
        ],
    )
    first_payload = totals.add('first', first)
    assert first_payload is not None
    first.ship_confusion['驱逐']['DD'] = 999
    first.ship_slot_confusion['1']['驱逐']['DD'] = 999
    second_payload = totals.add('second', second)
    assert second_payload is not None
    assert first_payload['delta']['ship_confusion'] == {'驱逐': {'DD': 6}}
    assert first_payload['cumulative']['ship_confusion'] == {'驱逐': {'DD': 6}}
    assert first_payload['cumulative']['ship_slot_confusion']['1'] == {'驱逐': {'DD': 1}}
    assert second_payload['delta']['ship_confusion'] == {'驱逐': {'BB': 6}}
    assert second_payload['cumulative']['ship_confusion'] == {'驱逐': {'DD': 6, 'BB': 6}}
    assert second_payload['cumulative']['ship_slots']['1'] == asdict(
        RecognitionCount(total=2, correct=1, errors=1)
    )
    first_payload['cumulative']['ship_slot_confusion']['1']['驱逐']['DD'] = 999
    second_payload['delta']['ship_confusion']['驱逐']['BB'] = 999
    third_payload = totals.add('third', third)
    assert third_payload is not None
    assert third_payload['schema_version'] == 2
    assert third_payload['cumulative']['ship_confusion'] == {
        '驱逐': {'DD': 6, 'BB': 6},
        '战列': {'DD': 6},
    }
    assert third_payload['cumulative']['ship_slot_confusion']['1'] == {
        '驱逐': {'DD': 1, 'BB': 1},
        '战列': {'DD': 1},
    }
