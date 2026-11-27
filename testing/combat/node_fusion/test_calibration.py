"""识别校验只借助去除敌情后的定位核对，不符槽位告警，其余保持静默。"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from autowsgr_native.vessel_type import VesselType

from autowsgr.combat.node_fusion.calibration import recognition_mismatches
from autowsgr.combat.node_fusion.enemy import EnemyObservation
from autowsgr.combat.node_fusion.map import TrackingMap
from autowsgr.combat.node_fusion.model import FusionObservation, FusionProfile, FusionTracker
from autowsgr.combat.plan import CombatMode
from autowsgr.ops.decisive.config import MapData


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
        'type': 'NULL' if silent else 'FIGHT',
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


def test_wrong_slot_reports_expected_and_recognized_code() -> None:
    tracker = _tracker()
    _spot(
        tracker,
        1.0,
        replace(
            _enemy(formation=2),
            raw_slots=('BB', 'NO', 'DD', 'DD', 'DD', 'DD'),
            ships=('战列', None, '驱逐', '驱逐', '驱逐', '驱逐'),
        ),
    )
    (mismatch,) = recognition_mismatches(tracker)
    assert mismatch.node == 'A'
    assert mismatch.slot == 1
    assert mismatch.expected == '驱逐'
    assert mismatch.code == 'BB'
    assert mismatch.recognized == '战列'


def test_variant_split_slots_are_not_comparable_and_stay_silent() -> None:
    raw = {'0': _node(('A',), silent=True), 'A': _node(())}
    raw['A']['enemy_formations'].append(
        {'formation': 2, 'ships': ['战列', '驱逐', '驱逐', '驱逐', '驱逐', '驱逐']}
    )
    tracker = _tracker(raw)
    _spot(tracker, 1.0, _enemy())
    assert recognition_mismatches(tracker) == []


def test_enemy_based_location_cannot_be_its_own_reference() -> None:
    tracker = _tracker(
        {
            '0': _node(('A', 'B'), silent=True),
            'A': _node(()),
            'B': _node((), ship='战列'),
        }
    )
    _spot(tracker, 1.0, _enemy())
    assert recognition_mismatches(tracker) == []


@pytest.mark.parametrize('first_failed', [False, True])
def test_repeated_page_keeps_first_read_even_when_later_read_succeeds(
    first_failed: bool,
) -> None:
    tracker = _tracker()
    first = None if first_failed else _enemy(ship='战列')
    _spot(tracker, 1.0, first)
    _spot(tracker, 2.0, _enemy())
    _spot(tracker, 3.0, _enemy())
    mismatches = recognition_mismatches(tracker)
    if first_failed:
        # 首读缺失没有"错成了什么"，不构成反馈内容。
        assert mismatches == []
    else:
        assert [item.slot for item in mismatches] == [1, 2, 3, 4, 5, 6]
        assert {item.code for item in mismatches} == {'BB'}


def test_recovered_location_keeps_unlocated_first_sample() -> None:
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
    tracker.observe(FusionObservation('phase', 1.0, phase='SPOT_ENEMY_SUCCESS', enemies=None))
    _motion(tracker, 2.0, (0.1, 0.1))
    _spot(tracker, 3.0, _enemy())
    assert recognition_mismatches(tracker) == []


def test_native_raw_code_is_the_comparison_basis() -> None:
    tracker = _tracker()
    _spot(tracker, 1.0, replace(_enemy(), raw_slots=('BB',) * 6))
    assert len(recognition_mismatches(tracker)) == 6


@pytest.mark.parametrize(
    ('raw_slots', 'valid_slots'),
    [
        (('NO',) * 6, True),
        (('UNRECOGNIZED_CODE',) * 6, True),
        (('DD',) * 5, True),
        (('DD',) * 7, True),
        (('DD',) * 6, False),
    ],
)
def test_invalid_native_results_are_not_reported(
    raw_slots: tuple[str, ...], valid_slots: bool
) -> None:
    tracker = _tracker()
    _spot(tracker, 1.0, replace(_enemy(), raw_slots=raw_slots, valid_slots=valid_slots))
    assert recognition_mismatches(tracker) == []


def test_empty_reference_slots_are_not_reported() -> None:
    raw = {'0': _node(('A',), silent=True), 'A': _node(())}
    raw['A']['enemy_formations'][0]['ships'] = ['驱逐'] * 4
    tracker = _tracker(raw)
    _spot(tracker, 1.0, replace(_enemy(), raw_slots=('DD',) * 4 + ('NO',) * 2))
    assert recognition_mismatches(tracker) == []


@pytest.mark.parametrize('combat_mode', [CombatMode.NORMAL, CombatMode.EVENT, CombatMode.DECISIVE])
@pytest.mark.parametrize('slot', range(6))
def test_loot_ap_exemption_is_only_normal_third_slot(combat_mode: CombatMode, slot: int) -> None:
    tracker = _tracker({'0': _node(('A',), silent=True), 'A': _node((), ship='轻母')})
    raw_slots = ['CVL'] * 6
    raw_slots[slot] = 'AP'
    _spot(
        tracker,
        1.0,
        replace(_enemy(ship='轻母'), raw_slots=tuple(raw_slots)),
    )
    mismatches = recognition_mismatches(tracker, combat_mode=combat_mode)
    if combat_mode == CombatMode.NORMAL and slot == 2:
        assert mismatches == []
    else:
        assert [(item.slot, item.code, item.expected) for item in mismatches] == [
            (slot + 1, 'AP', '轻母')
        ]


@pytest.mark.parametrize('combat_mode', [CombatMode.NORMAL, CombatMode.EVENT, CombatMode.DECISIVE])
def test_ap_signature_node_is_excluded_whether_or_not_observation_matches(
    combat_mode: CombatMode,
) -> None:
    for raw_slots in (('AP',) * 6, ('DD',) * 6):
        tracker = _tracker({'0': _node(('A',), silent=True), 'A': _node((), ship='补给')})
        _spot(tracker, 1.0, replace(_enemy(ship='补给'), raw_slots=raw_slots))
        assert recognition_mismatches(tracker, combat_mode=combat_mode) == []


@pytest.mark.parametrize('combat_mode', [CombatMode.NORMAL, CombatMode.EVENT, CombatMode.DECISIVE])
def test_matching_supply_ship_in_mixed_fleet_is_silent(combat_mode: str) -> None:
    raw = {'0': _node(('A',), silent=True), 'A': _node(())}
    raw['A']['enemy_formations'][0]['ships'][2] = '补给'
    tracker = _tracker(raw)
    _spot(tracker, 1.0, replace(_enemy(), raw_slots=('DD', 'DD', 'AP', 'DD', 'DD', 'DD')))
    assert recognition_mismatches(tracker, combat_mode=combat_mode) == []


def test_all_supply_signature_exemption_preserves_empty_slots() -> None:
    raw = {'0': _node(('A',), silent=True), 'A': _node(())}
    raw['A']['enemy_formations'][0]['ships'] = ['补给', '补给', None, None, None, None]
    tracker = _tracker(raw)
    _spot(tracker, 1.0, _enemy())
    assert recognition_mismatches(tracker, combat_mode=CombatMode.DECISIVE) == []


def test_all_native_types_recognized_correctly_stay_silent() -> None:
    for name in dir(VesselType):
        value = getattr(VesselType, name)
        if not isinstance(value, VesselType) or value.as_english() == 'NO':
            continue
        chinese, code = value.as_chinese(), value.as_english()
        if chinese == VesselType.AP.as_chinese():
            continue
        tracker = _tracker({'0': _node(('A',), silent=True), 'A': _node((), ship=chinese)})
        _spot(tracker, 1.0, replace(_enemy(), raw_slots=(code,) * 6))
        assert recognition_mismatches(tracker) == []


def test_later_geometry_revises_reference_and_clears_mismatch() -> None:
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
    _proceed(tracker, 3.0)
    _motion(tracker, 4.0, (0.85, 0.8))
    _spot(tracker, 5.0, _enemy(ship='战列'))
    assert recognition_mismatches(tracker) == []


def test_returning_to_same_node_in_a_cycle_reports_each_encounter() -> None:
    tracker = _tracker(
        {
            '0': _node(('A',), silent=True),
            'A': _node(('B',)),
            'B': _node(('A',), ship='战列'),
        }
    )
    _spot(tracker, 1.0, _enemy())
    _proceed(tracker, 2.0)
    _spot(tracker, 3.0, replace(_enemy(ship='战列'), raw_slots=('DD',) * 6))
    _proceed(tracker, 4.0)
    # 环回 A 点：观测与签名一致，不产生新的告警。
    _spot(tracker, 5.0, _enemy())
    mismatches = recognition_mismatches(tracker)
    assert [item.slot for item in mismatches] == list(range(1, 7))
    assert mismatches[0].node == 'B'


def _decisive_spot(
    tracker: FusionTracker, time: float, encounter_id: str, raw_slots: tuple[str, ...]
) -> None:
    tracker.observe(
        FusionObservation(
            'phase',
            time,
            frame_id=f'spot-{time}',
            phase='SPOT_ENEMY_SUCCESS',
            encounter_id=encounter_id,
            enemies=replace(_enemy(), raw_slots=raw_slots),
        )
    )


def test_decisive_reference_preserves_known_start_and_verified_progress() -> None:
    tracker = FusionTracker(MapData.tracking_map(6, 1), dynamics='decisive', initial={'A': 1.0})
    _decisive_spot(tracker, 1.0, 'first', ('BB', 'CL', 'NO', 'NO', 'NO', 'NO'))
    tracker.observe(
        FusionObservation('action', 2.0, action='encounter_complete', encounter_id='first')
    )
    tracker.observe(FusionObservation('phase', 3.0, phase='DECISIVE_MAP_READY'))
    _decisive_spot(tracker, 4.0, 'second', ('DD', 'SS', 'SS', 'NO', 'NO', 'NO'))
    _decisive_spot(tracker, 5.0, 'second', ('CLT', 'SS', 'SS', 'NO', 'NO', 'NO'))
    mismatches = recognition_mismatches(tracker, combat_mode=CombatMode.DECISIVE)
    assert [(item.node, item.slot, item.code, item.encounter_id) for item in mismatches] == [
        ('A', 1, 'BB', 'first'),
        ('B', 1, 'DD', 'second'),
    ]
    assert [item.event_id for item in mismatches] == [0, 3]


def test_decisive_unknown_resume_does_not_use_enemy_to_label_native_feedback() -> None:
    tracker = FusionTracker(MapData.tracking_map(6, 1), dynamics='decisive')
    _decisive_spot(tracker, 1.0, 'resume', ('BB', 'CL', 'NO', 'NO', 'NO', 'NO'))
    assert recognition_mismatches(tracker, combat_mode=CombatMode.DECISIVE) == []


def test_airfield_code_and_supply_code_remain_distinct() -> None:
    tracker = FusionTracker(MapData.tracking_map(6, 1), dynamics='decisive', initial={'J': 1.0})
    slots = ('AP', 'BB', 'DD', 'BB', 'BC', 'AV')
    _decisive_spot(tracker, 1.0, 'airport', slots)
    (mismatch,) = recognition_mismatches(tracker, combat_mode=CombatMode.DECISIVE)
    assert (mismatch.slot, mismatch.expected, mismatch.code, mismatch.recognized) == (
        1,
        '机场',
        'AP',
        '补给',
    )
    matching = FusionTracker(MapData.tracking_map(6, 1), dynamics='decisive', initial={'J': 1.0})
    _decisive_spot(matching, 1.0, 'airport', (VesselType.Airfield.as_english(), *slots[1:]))
    assert recognition_mismatches(matching, combat_mode=CombatMode.DECISIVE) == []
