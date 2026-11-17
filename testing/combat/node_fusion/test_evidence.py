"""节点融合的独立证据与操作历史回归测试。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict, replace
from typing import Any

import pytest

from autowsgr.combat.node_fusion import FusionObservation, FusionProfile, FusionTracker
from autowsgr.combat.node_fusion.enemy import EnemyObservation
from autowsgr.combat.node_fusion.map import TrackingMap


def _node(
    next_nodes: list[str],
    variants: list[tuple[int, str]],
    *,
    detour: bool = False,
) -> dict[str, Any]:
    return {
        'type': 'FIGHT' if variants else 'NULL',
        'position': [0.5, 0.5],
        'next': next_nodes,
        'detour': detour,
        'enemy_formations': [
            {'formation': formation, 'ships': [ship] * 6} for formation, ship in variants
        ],
    }


def _enemy(ship: str | None = '驱逐', formation: int | None = 1) -> EnemyObservation:
    return EnemyObservation(
        raw_slots=('NO' if ship is None else 'DD',) * 6,
        ships=(ship,) * 6,
        formation=formation,
        formation_text='' if formation is None else str(formation),
        formation_confidence=None if formation is None else 0.95,
        detour=None,
        detour_score=None,
    )


def _branches() -> FusionTracker:
    return FusionTracker(
        TrackingMap.from_dict(
            {
                '0': _node(['A', 'B'], []),
                'A': _node([], [(1, '驱逐')]),
                'B': _node([], [(2, '战列')]),
            }
        )
    )


def _chain(profile: FusionProfile | None = None) -> FusionTracker:
    tracker = FusionTracker(
        TrackingMap.from_dict(
            {
                '0': _node(['A'], []),
                'A': _node(['B'], [(1, '驱逐')], detour=True),
                'B': _node([], [(2, '战列')]),
            }
        ),
        profile,
    )
    tracker.observe(
        FusionObservation(
            'phase',
            1.0,
            frame_id=10,
            phase='SPOT_ENEMY_SUCCESS',
            enemies=_enemy(),
        )
    )
    return tracker


def _geometry_tracker() -> FusionTracker:
    raw = {
        '0': _node(['A', 'B'], []),
        'A': _node([], [(1, '驱逐')]),
        'B': _node([], [(2, '战列')]),
    }
    raw['0']['position'] = [0.0, 0.0]
    raw['A']['position'] = [1.0, 0.0]
    raw['B']['position'] = [0.0, 1.0]
    return FusionTracker(TrackingMap.from_dict(raw))


def test_diagnostics_expose_different_geometry_outputs_without_extra_votes() -> None:
    tracker = _geometry_tracker()
    first = tracker.observe(FusionObservation('motion', 1.0, 1, position=(0.1, 0.0)))
    assert first.diagnostics['distance']['available']
    assert first.diagnostics['ray']['available'] is False
    assert first.diagnostics['ray']['mixture_weight'] == 0

    moving = tracker.observe(FusionObservation('motion', 1.2, 2, position=(0.2, 0.0)))
    channels = moving.diagnostics
    assert max(channels['distance']['weights'], key=channels['distance']['weights'].get) == 'B'
    assert max(channels['ray']['weights'], key=channels['ray']['weights'].get) == 'A'
    assert max(channels['geometry']['weights'], key=channels['geometry']['weights'].get) == '0->A'
    assert channels['ray']['frame_gap_seconds'] == pytest.approx(0.2)
    assert 0 < channels['ray']['mixture_weight'] <= 0.5
    assert channels['fusion']['weights'] == moving.node_weights
    assert channels['fusion']['target_weights'] == moving.target_weights
    assert moving.current_node is None

    arrived = tracker.observe(
        FusionObservation('phase', 2.5, 3, phase='SPOT_ENEMY_SUCCESS', enemies=_enemy())
    )
    assert arrived.current_node == 'A'
    assert arrived.diagnostics['enemy']['available']
    assert not arrived.diagnostics['distance']['available']
    assert not arrived.diagnostics['ray']['available']
    assert not arrived.diagnostics['geometry']['available']


def test_ray_diagnostics_expose_frame_gap_decay() -> None:
    ray_weights = []
    for elapsed in (0.2, 2.0):
        tracker = _geometry_tracker()
        tracker.observe(FusionObservation('motion', 1.0, 1, position=(0.1, 0.0)))
        result = tracker.observe(FusionObservation('motion', 1.0 + elapsed, 2, position=(0.2, 0.0)))
        ray = result.diagnostics['ray']
        assert ray['available']
        assert ray['frame_gap_seconds'] == pytest.approx(elapsed)
        ray_weights.append(ray['mixture_weight'])
    assert ray_weights[1] < ray_weights[0] / 10


def test_diagnostic_collection_does_not_change_inference(monkeypatch: pytest.MonkeyPatch) -> None:
    tracked, without_diagnostics = _geometry_tracker(), _geometry_tracker()
    monkeypatch.setattr(without_diagnostics, '_diagnostics', lambda _event_id: {})
    observations = [
        FusionObservation('motion', 1.0, 1, position=(0.1, 0.0)),
        FusionObservation('motion', 1.2, 2, position=(0.2, 0.0)),
        FusionObservation('phase', 2.5, 3, phase='SPOT_ENEMY_SUCCESS', enemies=_enemy()),
        FusionObservation('phase', 2.8, 4, phase='FORMATION'),
    ]
    for observation in observations:
        actual, expected = tracked.observe(observation), without_diagnostics.observe(observation)
        assert actual.node_weights == pytest.approx(expected.node_weights)
        assert actual.target_weights == pytest.approx(expected.target_weights)
        assert actual.best_route == expected.best_route
        assert actual.revisions == expected.revisions


def test_ignored_observation_diagnostics_do_not_reuse_old_visual_evidence() -> None:
    tracker = _geometry_tracker()
    observation = FusionObservation('motion', 1.0, 1, position=(0.1, 0.0))
    initial = tracker.observe(observation)
    duplicate = tracker.observe(observation)
    assert duplicate.diagnostics['observation_accepted'] is False
    assert duplicate.diagnostics['source_event_id'] == initial.event_id
    for channel in ('distance', 'ray', 'geometry', 'enemy'):
        assert duplicate.diagnostics[channel]['available'] is False
        assert duplicate.diagnostics[channel]['weights'] == {}
    assert duplicate.diagnostics['fusion']['weights'] == initial.node_weights


def test_current_node_requires_an_arrival_and_excludes_departure_intent() -> None:
    tracker = _chain()
    assert tracker.estimate.current_node == 'A'
    departing = tracker.observe(FusionObservation('action', 2.0, action='proceed', clicked=True))
    assert departing.current_node is None
    assert departing.node_weights['A'] == pytest.approx(1.0)
    pending_detour = _chain().observe(
        FusionObservation('action', 2.0, action='detour', clicked=True)
    )
    assert pending_detour.current_node == 'A'
    assert replace(pending_detour, ambiguous=True).current_node is None
    assert replace(pending_detour, anomaly='无法解释').current_node is None


def test_enemy_diagnostics_summarize_support_and_separate_history_prior() -> None:
    tracker = FusionTracker(
        TrackingMap.from_dict(
            {
                '0': _node(['A', 'B'], []),
                'A': _node([], [(1, '驱逐'), (2, '战列')]),
                'B': _node([], [(2, '驱逐')]),
            }
        )
    )
    result = tracker.observe(
        FusionObservation('phase', 1.0, 1, phase='SPOT_ENEMY_SUCCESS', enemies=_enemy('驱逐', 2))
    )
    channels = result.diagnostics
    assert channels['history_prior']['weights'] == pytest.approx({'A': 0.5, 'B': 0.5})
    enemy = channels['enemy']
    # 诊断只保留节点级汇总；逐变体明细由重放同一观测流复得。
    assert enemy['weights']['B'] > enemy['weights']['A']
    assert enemy['robust_top']['node'] == 'B'
    assert enemy['robust_top']['lead_nats'] > 0
    assert 'variants' not in enemy
    assert 'joint_log_likelihood' not in enemy
    assert result.node_weights['B'] > result.node_weights['A']


def test_repeated_six_slot_read_is_not_six_more_votes_per_frame() -> None:
    tracker = _branches()
    first = FusionObservation(
        'phase',
        1.0,
        frame_id=10,
        phase='SPOT_ENEMY_SUCCESS',
        enemies=_enemy(),
    )
    initial = tracker.observe(first)
    duplicate = tracker.observe(first)
    assert duplicate.ignored is not None
    for frame_id in range(11, 31):
        repeated = tracker.observe(
            FusionObservation(
                'phase',
                float(frame_id),
                frame_id=frame_id,
                phase='SPOT_ENEMY_SUCCESS',
                enemies=_enemy(),
            )
        )
        assert repeated.node_weights == pytest.approx(initial.node_weights)
    assert 0 < initial.node_weights['B'] < initial.node_weights['A'] < 1


def test_formation_and_six_ships_must_fit_one_joint_variant() -> None:
    tracker = FusionTracker(
        TrackingMap.from_dict(
            {
                '0': _node(['A', 'B'], []),
                'A': _node([], [(1, '驱逐'), (2, '战列')]),
                'B': _node([], [(2, '驱逐')]),
            }
        )
    )
    result = tracker.observe(
        FusionObservation(
            'phase',
            1.0,
            frame_id=1,
            phase='SPOT_ENEMY_SUCCESS',
            enemies=_enemy(formation=2),
        )
    )
    assert result.node_weights['B'] > 0.9
    assert 0 < result.node_weights['A'] < 0.1


def test_wholly_missing_enemy_read_does_not_erase_earlier_evidence() -> None:
    tracker = _branches()
    first = tracker.observe(
        FusionObservation(
            'phase',
            1.0,
            frame_id=1,
            phase='SPOT_ENEMY_SUCCESS',
            enemies=_enemy(),
        )
    )
    missing = tracker.observe(
        FusionObservation(
            'phase',
            2.0,
            frame_id=2,
            phase='SPOT_ENEMY_SUCCESS',
            enemies=_enemy(None, None),
        )
    )
    assert missing.node_weights == pytest.approx(first.node_weights)


@pytest.mark.parametrize(
    'partial',
    [
        _enemy(None, 1),
        _enemy('驱逐', None),
        replace(_enemy(None, None), ships=('驱逐', None, None, None, None, None)),
    ],
)
def test_partial_missing_read_preserves_previously_observed_components(
    partial: EnemyObservation,
) -> None:
    tracker = _branches()
    first = tracker.observe(
        FusionObservation(
            'phase',
            1.0,
            frame_id=1,
            phase='SPOT_ENEMY_SUCCESS',
            enemies=_enemy(),
        )
    )
    result = tracker.observe(
        FusionObservation(
            'phase',
            2.0,
            frame_id=2,
            phase='SPOT_ENEMY_SUCCESS',
            enemies=partial,
        )
    )
    assert result.node_weights == pytest.approx(first.node_weights)


def test_changed_formation_with_missing_ships_does_not_remove_ship_evidence() -> None:
    full, partial = _branches(), _branches()
    first = FusionObservation(
        'phase',
        1.0,
        frame_id=1,
        phase='SPOT_ENEMY_SUCCESS',
        enemies=_enemy(),
    )
    full.observe(first)
    partial.observe(first)
    full_result = full.observe(
        FusionObservation(
            'phase',
            2.0,
            frame_id=2,
            phase='SPOT_ENEMY_SUCCESS',
            enemies=_enemy('驱逐', 2),
        )
    )
    partial_result = partial.observe(
        FusionObservation(
            'phase',
            2.0,
            frame_id=2,
            phase='SPOT_ENEMY_SUCCESS',
            enemies=_enemy(None, 2),
        )
    )
    assert partial_result.node_weights == pytest.approx(full_result.node_weights)


def test_late_detour_formation_keeps_same_and_next_node_hypotheses() -> None:
    tracker = _chain()
    tracker.observe(FusionObservation('action', 2.0, action='detour', clicked=True))
    result = tracker.observe(FusionObservation('phase', 3.5, frame_id=11, phase='FORMATION'))
    assert set(result.node_weights) == {'A', 'B'}
    assert all(0 < weight < 1 for weight in result.node_weights.values())


def test_spot_page_remaining_after_detour_does_not_cancel_pending_departure() -> None:
    tracker = _chain()
    tracker.observe(FusionObservation('action', 2.0, action='detour', clicked=True))
    waiting = tracker.observe(
        FusionObservation(
            'phase',
            2.2,
            frame_id=11,
            phase='SPOT_ENEMY_SUCCESS',
            enemies=_enemy(),
        )
    )
    assert waiting.node_weights == pytest.approx({'A': 1.0})
    arrived = tracker.observe(
        FusionObservation(
            'phase',
            3.5,
            frame_id=12,
            phase='SPOT_ENEMY_SUCCESS',
            enemies=_enemy('战列', 2),
        )
    )
    assert 'B' in arrived.node_weights
    assert arrived.node_weights['B'] > 0


@pytest.mark.parametrize('elapsed', [0.0, 0.2, 0.949])
def test_formation_before_minimum_travel_is_still_at_detour_node(elapsed: float) -> None:
    tracker = _chain()
    tracker.observe(FusionObservation('action', 2.0, action='detour', clicked=True))
    result = tracker.observe(
        FusionObservation(
            'phase',
            2.0 + elapsed,
            frame_id=11,
            phase='FORMATION',
        )
    )
    assert result.node_weights == pytest.approx({'A': 1.0})


@pytest.mark.parametrize('elapsed', [0.95, 1.0, 4.0])
def test_at_or_after_travel_boundary_does_not_prove_detour_success(elapsed: float) -> None:
    tracker = _chain()
    tracker.observe(FusionObservation('action', 2.0, action='detour', clicked=True))
    result = tracker.observe(
        FusionObservation(
            'phase',
            2.0 + elapsed,
            frame_id=11,
            phase='FORMATION',
        )
    )
    assert set(result.node_weights) == {'A', 'B'}
    assert result.node_weights['A'] > 0


def test_failed_detour_click_cannot_create_a_new_encounter() -> None:
    tracker = _chain()
    tracker.observe(FusionObservation('action', 2.0, action='detour', clicked=False))
    result = tracker.observe(FusionObservation('phase', 4.0, frame_id=11, phase='FORMATION'))
    assert result.node_weights == pytest.approx({'A': 1.0})


def test_old_frame_cannot_be_reused_as_another_kind_after_action() -> None:
    tracker = _chain()
    pending = tracker.observe(FusionObservation('action', 2.0, action='detour', clicked=True))
    # 即使调用者传入新时间戳，也不能改变同一解码帧的身份。
    stale = tracker.observe(
        FusionObservation(
            'motion',
            2.2,
            frame_id=10,
            position=(0.5, 0.5),
        )
    )
    assert stale.ignored is not None
    assert stale.node_weights == pytest.approx(pending.node_weights)


def test_combat_phase_sequence_without_departure_never_increments_node() -> None:
    tracker = _chain()
    phases = ['FORMATION', 'FIGHT_PERIOD', 'RESULT', 'EXP_SETTLEMENT', 'PROCEED', 'RESULT']
    for frame_id, phase in enumerate(phases, 11):
        result = tracker.observe(FusionObservation('phase', float(frame_id), frame_id, phase))
        assert result.node_weights == pytest.approx({'A': 1.0})


def test_smoothing_never_rewrites_raw_observations() -> None:
    tracker = _branches()
    first = FusionObservation(
        'phase',
        1.0,
        frame_id=10,
        phase='SPOT_ENEMY_SUCCESS',
        enemies=_enemy(),
        decision_node='B',
    )
    original = asdict(first)
    tracker.observe(first)
    tracker.observe(
        FusionObservation(
            'phase',
            2.0,
            frame_id=11,
            phase='SPOT_ENEMY_SUCCESS',
            enemies=_enemy('战列', 2),
        )
    )
    assert tracker.observations[0] is first
    assert asdict(first) == original
    assert asdict(tracker.observations[0]) == original
    with pytest.raises(FrozenInstanceError):
        first.decision_node = 'A'


def test_travel_timing_can_be_disabled_for_unverified_modes() -> None:
    tracker = _chain(FusionProfile(min_travel_seconds=None))
    tracker.observe(FusionObservation('action', 2.0, action='detour', clicked=True))
    result = tracker.observe(FusionObservation('phase', 2.2, frame_id=11, phase='FORMATION'))
    assert set(result.node_weights) == {'A', 'B'}


def test_identical_spot_polling_does_not_manufacture_detour_success() -> None:
    tracker = _chain()
    tracker.observe(FusionObservation('action', 2.0, action='detour', clicked=True))
    initial = tracker.observe(
        FusionObservation('phase', 3.5, frame_id=11, phase='SPOT_ENEMY_SUCCESS')
    )
    for frame_id in range(12, 30):
        repeated = tracker.observe(
            FusionObservation(
                'phase', float(frame_id), frame_id=frame_id, phase='SPOT_ENEMY_SUCCESS'
            )
        )
        assert repeated.node_weights == pytest.approx(initial.node_weights)
        assert repeated.ignored is not None


def test_identical_spot_after_timing_boundary_keeps_both_explanations() -> None:
    tracker = _chain()
    tracker.observe(FusionObservation('action', 2.0, action='detour', clicked=True))
    early = tracker.observe(
        FusionObservation('phase', 2.2, frame_id=11, phase='SPOT_ENEMY_SUCCESS')
    )
    assert early.node_weights == pytest.approx({'A': 1.0})
    late = tracker.observe(FusionObservation('phase', 3.5, frame_id=12, phase='SPOT_ENEMY_SUCCESS'))
    assert late.ignored is None
    assert set(late.node_weights) == {'A', 'B'}
    repeated = tracker.observe(
        FusionObservation('phase', 3.6, frame_id=13, phase='SPOT_ENEMY_SUCCESS')
    )
    assert repeated.node_weights == pytest.approx(late.node_weights)


def test_missing_enemy_fields_cannot_repeatedly_split_pending_detour_prior() -> None:
    # 两个节点故意使用相同敌情；丢弃已经识别的槽位不能支持任一种新遭遇解释。
    metadata = TrackingMap.from_dict(
        {
            '0': _node(['A'], []),
            'A': _node(['B'], [(1, '驱逐')], detour=True),
            'B': _node([], [(1, '驱逐')], detour=True),
        }
    )
    tracker = FusionTracker(metadata)
    tracker.observe(
        FusionObservation('phase', 1.0, frame_id=1, phase='SPOT_ENEMY_SUCCESS', enemies=_enemy())
    )
    tracker.observe(FusionObservation('action', 2.0, action='detour', clicked=True))
    initial = tracker.observe(
        FusionObservation('phase', 3.5, frame_id=2, phase='SPOT_ENEMY_SUCCESS', enemies=_enemy())
    )
    for index in range(6):
        partial = replace(_enemy(), ships=tuple(None if i == index else '驱逐' for i in range(6)))
        repeated = tracker.observe(
            FusionObservation(
                'phase',
                3.6 + index * 0.1,
                frame_id=3 + index,
                phase='SPOT_ENEMY_SUCCESS',
                enemies=partial,
            )
        )
        assert repeated.node_weights == pytest.approx(initial.node_weights)


@pytest.mark.parametrize('wrong_slots', [1, 2])
def test_one_or_two_wrong_slots_keep_true_fleet_candidate(wrong_slots: int) -> None:
    tracker = _branches()
    corrupted = replace(_enemy(), ships=('战列',) * wrong_slots + ('驱逐',) * (6 - wrong_slots))
    estimate = tracker.observe(
        FusionObservation('phase', 1.0, frame_id=1, phase='SPOT_ENEMY_SUCCESS', enemies=corrupted)
    )
    assert 0 < estimate.node_weights['B'] < estimate.node_weights['A'] < 1


def test_wrong_formation_does_not_eliminate_matching_six_slots() -> None:
    tracker = _branches()
    estimate = tracker.observe(
        FusionObservation(
            'phase', 1.0, frame_id=1, phase='SPOT_ENEMY_SUCCESS', enemies=_enemy(formation=2)
        )
    )
    assert 0 < estimate.node_weights['B'] < estimate.node_weights['A'] < 1


def test_new_detour_click_can_recover_a_previous_click_with_no_effect() -> None:
    metadata = TrackingMap.from_dict(
        {
            '0': _node(['A'], []),
            'A': _node(['B'], [(1, '驱逐')], detour=True),
            'B': _node([], [(1, '驱逐')]),
        }
    )
    tracker = FusionTracker(metadata)
    tracker.observe(FusionObservation('phase', 1.0, frame_id=1, phase='SPOT_ENEMY_SUCCESS'))
    tracker.observe(FusionObservation('action', 2.0, action='detour', clicked=True))
    first_attempt = tracker.observe(
        FusionObservation('phase', 3.5, frame_id=2, phase='SPOT_ENEMY_SUCCESS')
    )
    assert set(first_attempt.node_weights) == {'A', 'B'}
    # 此处确实执行了第二次点击，不是重复记录第一次操作。
    tracker.observe(FusionObservation('action', 4.0, action='detour', clicked=True))
    second_attempt = tracker.observe(
        FusionObservation('phase', 5.5, frame_id=3, phase='SPOT_ENEMY_SUCCESS')
    )
    assert second_attempt.node_weights['B'] > first_attempt.node_weights['B']
    assert second_attempt.node_weights['A'] > 0


def test_late_delivered_position_cannot_be_scored_as_current_combat_position() -> None:
    nodes = {
        '0': _node(['A'], []),
        'A': _node(['B'], [(1, '驱逐')], detour=True),
        'B': _node([], [(2, '战列')]),
    }
    nodes['A']['position'] = [0.25, 0.5]
    nodes['B']['position'] = [0.75, 0.5]
    tracker = FusionTracker(TrackingMap.from_dict(nodes))
    tracker.observe(FusionObservation('phase', 1.0, frame_id=1, phase='SPOT_ENEMY_SUCCESS'))
    tracker.observe(FusionObservation('action', 2.0, action='detour', clicked=True))
    formation = tracker.observe(FusionObservation('phase', 4.0, frame_id=20, phase='FORMATION'))
    late_motion = FusionObservation('motion', 2.2, frame_id=12, position=(0.25, 0.5))
    result = tracker.observe(late_motion)
    assert result.ignored is not None
    assert result.node_weights == pytest.approx(formation.node_weights)
    assert tracker.observations[-1] is late_motion


def test_silent_terminal_arrival_also_respects_travel_lower_bound() -> None:
    nodes = {
        '0': _node(['A'], []),
        'A': _node(['T'], [(1, '驱逐')], detour=True),
        'T': _node([], []),
    }
    nodes['T']['type'] = 'LOSS'
    tracker = FusionTracker(TrackingMap.from_dict(nodes))
    tracker.observe(FusionObservation('phase', 1.0, frame_id=1, phase='SPOT_ENEMY_SUCCESS'))
    tracker.observe(FusionObservation('action', 2.0, action='detour', clicked=True))
    early = tracker.observe(FusionObservation('phase', 2.2, frame_id=2, phase='MAP_PAGE'))
    assert early.anomaly is not None
    assert 'T' not in early.node_weights
    late = tracker.observe(FusionObservation('phase', 4.0, frame_id=3, phase='MAP_PAGE'))
    assert late.anomaly is None
    assert late.node_weights == pytest.approx({'T': 1.0})
    assert late.best_route == ('0', 'A', 'T')


def test_explicit_return_does_not_need_a_sailing_interval() -> None:
    tracker = _chain()
    tracker.observe(FusionObservation('action', 2.0, action='retreat', clicked=True))
    result = tracker.observe(FusionObservation('phase', 2.2, frame_id=11, phase='MAP_PAGE'))
    assert result.anomaly is None
    assert result.node_weights == pytest.approx({'A': 1.0})
    assert all(state['stage'] == 'END' for state in result.state_weights)
