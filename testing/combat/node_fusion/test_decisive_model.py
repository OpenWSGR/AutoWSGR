"""决战真实页面、确定推进与不确定观测共用同一历史推断内核。"""

from __future__ import annotations

from dataclasses import replace

import pytest

from autowsgr.combat.node_fusion import (
    FusionObservation,
    FusionProfile,
    FusionTracker,
    NodeEstimate,
)
from autowsgr.combat.node_fusion.enemy import EnemyObservation
from autowsgr.combat.node_fusion.map import TrackingMap


def _map() -> TrackingMap:
    return TrackingMap.from_dict(
        {
            name: {
                'next': [following] if following else [],
                'enemy_formations': [{'ships': [ship] * 6}],
            }
            for name, following, ship in (
                ('A', 'B', '驱逐'),
                ('B', 'C', '轻巡'),
                ('C', None, '机场'),
            )
        }
    )


def _enemy(name: str) -> EnemyObservation:
    return EnemyObservation(
        raw_slots=(),
        ships=_map().nodes[name].enemy_formations[0].ships,
        formation=None,
        formation_text='',
        formation_confidence=None,
        detour=None,
        detour_score=None,
    )


def _phase(tracker: FusionTracker, phase: str = 'DECISIVE_MAP_READY', **kwargs) -> NodeEstimate:
    event = len(tracker.observations) + 1
    return tracker.observe(
        FusionObservation('phase', float(event), frame_id=event, phase=phase, **kwargs)
    )


def _complete(tracker: FusionTracker, encounter: str) -> NodeEstimate:
    return tracker.observe(
        FusionObservation(
            'action',
            float(len(tracker.observations) + 1),
            action='encounter_complete',
            encounter_id=encounter,
        )
    )


def test_known_start_is_certain_without_fake_entry_or_geometry() -> None:
    tracker = FusionTracker(_map(), dynamics='decisive', initial={'A': 1.0})
    assert tracker.estimate.current_node == 'A'
    assert tracker.estimate.node_weights == {'A': 1.0}
    assert tracker.estimate.best_route == ('A',)
    assert not tracker.map_data.capabilities['distance']
    assert all(node.position is None for node in tracker.map_data.nodes.values())
    assert TrackingMap.from_dict(tracker.map_data.to_dict()) == tracker.map_data
    _phase(tracker, encounter_id='first', node_label='C')
    assert tracker.estimate.current_node == 'A'


def test_resume_preserves_all_candidates_and_can_correct_initial_wrong_label() -> None:
    tracker = FusionTracker(_map(), dynamics='decisive')
    assert tracker.estimate.node_weights == pytest.approx(dict.fromkeys('ABC', 1 / 3))
    first = _phase(tracker, node_label='A', encounter_id='first')
    assert first.current_node == 'A'
    assert first.node_weights['B'] > 0
    estimate = _phase(tracker, 'SPOT_ENEMY_SUCCESS', enemies=_enemy('B'), encounter_id='first')
    assert max(estimate.node_weights, key=estimate.node_weights.get) == 'B'
    assert estimate.revisions
    _complete(tracker, 'first')
    estimate = _phase(tracker, encounter_id='second')
    assert estimate.node_weights['C'] > estimate.node_weights['B']
    assert estimate.best_route == ('B', 'C')


def test_stopping_letter_sampling_keeps_enemy_correction_and_missing_spot_is_neutral() -> None:
    tracker = FusionTracker(_map(), FusionProfile(node_label_accuracy=0.96), dynamics='decisive')
    initial = _phase(tracker, node_label='A', encounter_id='one')
    assert initial.node_weights['A'] >= 0.95
    absent = _phase(tracker, 'SPOT_ENEMY_SUCCESS', encounter_id='one')
    assert absent.node_weights == pytest.approx(initial.node_weights)
    # Stop active map letters; later encounters still constrain the entire retained history.
    _complete(tracker, 'one')
    _phase(tracker, encounter_id='two')
    corrected = _phase(tracker, 'SPOT_ENEMY_SUCCESS', enemies=_enemy('C'), encounter_id='two')
    assert corrected.node_weights['C'] > initial.node_weights['B']
    _complete(tracker, 'two')
    final = _phase(tracker, 'DECISIVE_STAGE_CLEAR')
    assert final.best_route == ('B', 'C')
    assert final.history[0]['best_node'] == 'B'


def test_same_encounter_reads_and_battle_pages_never_advance() -> None:
    tracker = FusionTracker(_map(), dynamics='decisive', initial={'A': 1.0})
    for phase in ('DECISIVE_MAP_READY', 'SPOT_ENEMY_SUCCESS', 'FORMATION', 'RESULT', 'RESULT'):
        estimate = _phase(tracker, phase, encounter_id='one')
        assert estimate.node_weights == {'A': 1.0}
    for action in ('formation', 'night', 'end', 'retreat'):
        tracker.observe(FusionObservation('action', len(tracker.observations) + 1, action=action))
        assert tracker.estimate.node_weights == {'A': 1.0}
    assert _complete(tracker, 'one').current_node == 'B'
    duplicate = _complete(tracker, 'one')
    assert duplicate.ignored == 'duplicate encounter completion'
    assert tracker.estimate.current_node == 'B'
    _phase(tracker, 'FORMATION', encounter_id='two')
    assert _complete(tracker, 'two').current_node == 'C'


def test_failed_completion_and_wrong_encounter_do_not_advance() -> None:
    tracker = FusionTracker(_map(), dynamics='decisive', initial={'A': 1.0})
    _phase(tracker, encounter_id='one')
    tracker.observe(
        FusionObservation(
            'action',
            2.0,
            action='encounter_complete',
            encounter_id='one',
            clicked=False,
        )
    )
    assert tracker.estimate.current_node == 'A'
    assert _complete(tracker, 'wrong').anomaly
    assert tracker.estimate.node_weights == {'A': 1.0}
    assert _complete(tracker, 'one').current_node == 'B'


def test_completed_encounter_returns_first_accepted_observation() -> None:
    tracker = FusionTracker(_map(), dynamics='decisive', initial={'A': 1.0})
    _phase(tracker, encounter_id='one')
    assert tracker.completed_encounter('one') is None
    completion = FusionObservation(
        'action', 2.0, action='encounter_complete', encounter_id='one', clicked=True
    )
    tracker.observe(completion)
    accepted_estimate = tracker.estimate.as_dict()

    duplicate = _complete(tracker, 'one')

    assert duplicate.ignored == 'duplicate encounter completion'
    assert tracker.completed_encounter('one') is completion
    assert tracker.completed_encounter('missing') is None
    assert tracker.estimate.as_dict() == accepted_estimate


@pytest.mark.parametrize(
    ('timestamp', 'encounter_id', 'clicked'),
    [(2.0, 'one', False), (2.0, 'wrong', True), (0.5, 'one', True)],
)
def test_rejected_completion_is_not_exposed_as_accepted(
    timestamp: float, encounter_id: str, clicked: bool
) -> None:
    tracker = FusionTracker(_map(), dynamics='decisive', initial={'A': 1.0})
    _phase(tracker, encounter_id='one')
    tracker.observe(
        FusionObservation(
            'action',
            timestamp,
            action='encounter_complete',
            encounter_id=encounter_id,
            clicked=clicked,
        )
    )
    assert tracker.completed_encounter(encounter_id) is None
    assert tracker.completed_encounter('one') is None

    _complete(tracker, 'one')

    assert tracker.completed_encounter('one') is tracker.observations[-1]


def test_next_map_page_rejects_premature_terminal_and_revises_history() -> None:
    tracker = FusionTracker(_map(), dynamics='decisive')
    _phase(tracker, node_label='C', encounter_id='one')
    prediction = _complete(tracker, 'one')
    assert prediction.current_node is None
    assert any(row['stage'] == 'TERMINAL_PENDING' for row in prediction.state_weights)
    next_map = _phase(tracker, encounter_id='two')
    assert not next_map.anomaly
    assert not any(row['stage'] == 'TERMINAL_PENDING' for row in next_map.state_weights)
    assert next_map.history[0]['node_weights'].get('C', 0) == 0


def test_actual_clear_covers_lagging_estimate_without_prediction_triggering_clear() -> None:
    tracker = FusionTracker(_map(), dynamics='decisive', initial={'A': 1.0})
    _phase(tracker, encounter_id='one')
    _complete(tracker, 'one')
    assert tracker.estimate.current_node == 'B'
    clear = _phase(tracker, 'DECISIVE_STAGE_CLEAR')
    assert clear.node_weights == {'C': 1.0}
    assert clear.current_node is None
    assert clear.diagnostics['page_correction']
    assert all(row['stage'] == 'END' for row in clear.state_weights)


def test_duplicate_label_does_not_accumulate_confidence() -> None:
    tracker = FusionTracker(_map(), dynamics='decisive')
    first = _phase(tracker, node_label='B', encounter_id='one')
    for _ in range(3):
        observed = _phase(tracker, node_label='B', encounter_id='one')
        assert observed.node_weights == first.node_weights
    tracker.observe(FusionObservation('action', 5.0, action='fight'))
    again = _phase(tracker, node_label='B', encounter_id='one')
    assert again.node_weights == pytest.approx(first.node_weights)


def test_clone_excludes_enemy_but_retains_scenario_and_initial_constraints() -> None:
    tracker = FusionTracker(_map(), dynamics='decisive', initial={'A': 0.2, 'B': 0.8})
    _phase(tracker, node_label='A', encounter_id='one')
    _phase(tracker, 'SPOT_ENEMY_SUCCESS', enemies=_enemy('B'), encounter_id='one')
    _complete(tracker, 'one')
    reference = tracker.clone_without_enemy()
    assert reference.initial == tracker.initial
    assert reference.dynamics == 'decisive'
    assert reference.observations == []
    assert not reference.map_data.capabilities['enemy']
    for obs in tracker.observations:
        reference.observe(replace(obs, enemies=None))
    repeated = FusionTracker(
        reference.map_data, reference.profile, dynamics='decisive', initial=tracker.initial
    )
    for obs in reference.observations:
        repeated.observe(obs)
    assert repeated.estimate.as_dict() == reference.estimate.as_dict()


def test_unknown_expected_formation_is_not_a_mismatch() -> None:
    metadata = _map()
    tracker = FusionTracker(metadata, dynamics='decisive')
    for name in metadata.nodes:
        assert metadata.nodes[name].enemy_formations[0].formation is None
    only_formation = replace(_enemy('A'), ships=(None,) * 6, formation=3)
    result = _phase(tracker, 'SPOT_ENEMY_SUCCESS', enemies=only_formation)
    assert result.node_weights == pytest.approx(dict.fromkeys('ABC', 1 / 3))


@pytest.mark.parametrize('initial', [{}, {'Z': 1.0}, {'A': -1.0}, {'A': 0.0}, {'A': True}])
def test_invalid_initial_distribution_rejected(initial: dict) -> None:
    with pytest.raises(ValueError, match=r'[Ii]nitial'):
        FusionTracker(_map(), dynamics='decisive', initial=initial)
