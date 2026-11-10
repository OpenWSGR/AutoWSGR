"""资料不完整时按已有能力定位，不伪造节点类型或复用旧航行证据。"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import pytest

from autowsgr.combat.node_fusion import (
    FusionObservation,
    FusionProfile,
    FusionTracker,
    NodeEstimate,
)
from autowsgr.combat.node_fusion.enemy import EnemyObservation
from autowsgr.combat.node_fusion.map import TrackingMap


def _node(
    position: tuple[float, float],
    next_nodes: list[str] | None = None,
    node_type: str | None = None,
    detour: bool | None = None,
    ships: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    raw: dict[str, Any] = {'position': list(position)}
    if next_nodes is not None:
        raw['next'] = next_nodes
    if node_type is not None:
        raw['type'] = node_type
    if detour is not None:
        raw['detour'] = detour
    if ships is not None:
        raw['enemy_formations'] = [{'formation': 1, 'ships': list(ships)}] if ships else []
    return raw


def _tracker(raw: dict[str, Any]) -> FusionTracker:
    return FusionTracker(TrackingMap.from_dict(raw), FusionProfile(min_travel_seconds=None))


def _motion(tracker: FusionTracker, time: float, position: tuple[float, float]) -> NodeEstimate:
    return tracker.observe(
        FusionObservation('motion', time, frame_id=f'motion-{time}', position=position)
    )


def _phase(tracker: FusionTracker, time: float, phase: str = 'SPOT_ENEMY_SUCCESS') -> NodeEstimate:
    return tracker.observe(FusionObservation('phase', time, frame_id=f'phase-{time}', phase=phase))


def _proceed(tracker: FusionTracker, time: float) -> NodeEstimate:
    return tracker.observe(FusionObservation('action', time, action='proceed', clicked=True))


def _button_observation() -> EnemyObservation:
    return EnemyObservation(
        raw_slots=('NO',) * 6,
        ships=(None,) * 6,
        formation=None,
        formation_text='',
        formation_confidence=None,
        detour=True,
        detour_score=0.95,
    )


def test_real_classic_map_without_start_or_routes_can_locate_one_fresh_frame() -> None:
    metadata = TrackingMap.load_event('20220928', 'E', 1)
    assert metadata is not None
    assert '0' not in metadata.nodes
    assert not metadata.capabilities['topology']
    tracker = FusionTracker(metadata, FusionProfile(min_travel_seconds=None))
    moving = _motion(tracker, 1.0, metadata.nodes['D'].position)
    assert moving.current_node is None
    assert moving.diagnostics['ray']['available'] is False
    arrived = _phase(tracker, 2.0)
    assert arrived.anomaly is None
    assert arrived.current_node == 'D'


def test_many_coordinate_only_nodes_do_not_make_exact_position_permanently_ambiguous() -> None:
    raw = {
        f'N{row}{column}': _node((x, y))
        for row, y in enumerate((0.1, 0.5, 0.9))
        for column, x in enumerate((0.1, 0.35, 0.6, 0.85))
    }
    tracker = _tracker(raw)
    _motion(tracker, 1.0, (0.35, 0.5))
    arrived = _phase(tracker, 2.0, 'FORMATION')
    assert arrived.current_node == 'N11'


def test_unknown_types_can_cross_multiple_real_edges_without_inventing_silent_nodes() -> None:
    tracker = _tracker(
        {
            '0': _node((0.05, 0.1), ['B']),
            'B': _node((0.25, 0.1), ['C']),
            'C': _node((0.5, 0.1), ['D']),
            'D': _node((0.85, 0.1), []),
        }
    )
    _motion(tracker, 1.0, (0.85, 0.1))
    arrived = _phase(tracker, 2.0)
    assert arrived.current_node == 'D'
    assert all(node.node_type is None for node in tracker.map_data.nodes.values())
    for source, destination in zip(arrived.best_route, arrived.best_route[1:], strict=False):
        assert destination in tracker.map_data.nodes[source].next_nodes


def test_new_encounter_without_new_motion_does_not_reuse_previous_ship_position() -> None:
    tracker = _tracker(
        {
            '0': _node((0.05, 0.1), ['A']),
            'A': _node((0.2, 0.1), ['B']),
            'B': _node((0.8, 0.8), []),
        }
    )
    _motion(tracker, 1.0, (0.2, 0.1))
    assert _phase(tracker, 2.0).current_node == 'A'
    _proceed(tracker, 3.0)
    missing = _phase(tracker, 4.0)
    assert missing.current_node is None
    assert missing.diagnostics['distance']['available'] is False
    _motion(tracker, 5.0, (0.8, 0.8))
    recovered = _phase(tracker, 6.0)
    assert recovered.anomaly is None
    assert recovered.current_node == 'B'


def test_known_routes_exclude_disconnected_node_even_if_position_matches_it() -> None:
    tracker = _tracker(
        {
            '0': _node((0.05, 0.1), ['A']),
            'A': _node((0.2, 0.1), []),
            'X': _node((0.8, 0.8), []),
        }
    )
    _motion(tracker, 1.0, (0.8, 0.8))
    arrived = _phase(tracker, 2.0)
    assert arrived.current_node != 'X'
    assert arrived.node_weights.get('X', 0) == 0


def test_weak_early_winner_does_not_remove_other_legal_branch() -> None:
    tracker = _tracker(
        {
            '0': _node((0.05, 0.1), ['A', 'B']),
            'A': _node((0.2, 0.2), []),
            'B': _node((0.2, 0.25), ['C']),
            'C': _node((0.85, 0.9), []),
        }
    )
    _motion(tracker, 1.0, (0.2, 0.21))
    initial = _phase(tracker, 2.0)
    assert max(initial.node_weights, key=initial.node_weights.get) == 'A'
    assert initial.node_weights.get('B', 0) > 0
    _proceed(tracker, 3.0)
    _motion(tracker, 4.0, (0.85, 0.9))
    arrived = _phase(tracker, 5.0)
    assert arrived.current_node == 'C'
    corrected = next(row for row in arrived.history if row['event_id'] == initial.event_id)
    assert corrected['best_node'] == 'B'
    assert any(
        revision['event_id'] == initial.event_id
        and revision['before'][0] == 'A'
        and revision['after'][0] == 'B'
        for revision in arrived.revisions
    )


def test_coordinate_route_cycle_can_return_to_previous_encounter() -> None:
    tracker = _tracker(
        {
            '0': _node((0.05, 0.1), ['A']),
            'A': _node((0.2, 0.2), ['B']),
            'B': _node((0.8, 0.8), ['A']),
        }
    )
    for index, node in enumerate(('A', 'B', 'A')):
        start = 1.0 + index * 3
        _motion(tracker, start, tracker.map_data.nodes[node].position)
        arrived = _phase(tracker, start + 1)
        assert arrived.current_node == node
        if index < 2:
            _proceed(tracker, start + 2)


def test_duplicate_or_predeparture_frame_never_adds_fresh_geometry() -> None:
    tracker = _tracker({'A': _node((0.2, 0.2)), 'B': _node((0.8, 0.8))})
    first = FusionObservation('motion', 1.0, frame_id='source', position=(0.2, 0.2))
    saved = asdict(first)
    before = tracker.observe(first)
    repeated = tracker.observe(first)
    assert repeated.ignored is not None
    assert repeated.node_weights == pytest.approx(before.node_weights)
    assert repeated.diagnostics['distance']['available'] is False
    _phase(tracker, 2.0)
    _proceed(tracker, 3.0)
    stale = tracker.observe(FusionObservation('motion', 2.5, frame_id='stale', position=(0.8, 0.8)))
    assert stale.ignored is not None
    assert stale.diagnostics['distance']['available'] is False
    old = tracker.observe(FusionObservation('motion', 3.5, frame_id='source', position=(0.2, 0.2)))
    assert old.ignored is not None
    assert _phase(tracker, 4.0).current_node is None
    assert asdict(first) == saved


def test_missing_enemy_only_keeps_stage_and_route_history_without_motion() -> None:
    tracker = _tracker(
        {
            '0': _node((0.05, 0.1), ['A'], 'NULL', False),
            'A': _node((0.2, 0.2), ['B'], 'FIGHT', False),
            'B': _node((0.8, 0.8), [], 'FIGHT', False),
        }
    )
    assert tracker.map_data.capabilities['encounter_history']
    assert not tracker.map_data.capabilities['enemy']
    assert _phase(tracker, 1.0).current_node == 'A'
    _proceed(tracker, 2.0)
    arrived = _phase(tracker, 3.0)
    assert arrived.current_node == 'B'
    assert arrived.best_route == ('0', 'A', 'B')


def test_known_detour_is_evidence_even_when_enemy_variants_are_missing() -> None:
    tracker = _tracker(
        {
            '0': _node((0.05, 0.1), ['A', 'B'], 'NULL', False),
            'A': _node((0.2, 0.2), [], 'FIGHT', True),
            'B': _node((0.8, 0.8), [], 'FIGHT', False),
        }
    )
    arrived = tracker.observe(
        FusionObservation(
            'phase', 1.0, frame_id=1, phase='SPOT_ENEMY_SUCCESS', enemies=_button_observation()
        )
    )
    assert arrived.current_node == 'A'
    assert arrived.node_weights['B'] > 0


def test_unknown_detour_is_not_treated_as_a_negative_button_observation() -> None:
    tracker = _tracker(
        {
            '0': _node((0.05, 0.1), ['A', 'B'], 'NULL', False),
            'A': _node((0.2, 0.2), [], 'FIGHT', None, ('驱逐',) * 6),
            'B': _node((0.8, 0.8), [], 'FIGHT', False, ('驱逐',) * 6),
        }
    )
    arrived = tracker.observe(
        FusionObservation(
            'phase', 1.0, frame_id=1, phase='SPOT_ENEMY_SUCCESS', enemies=_button_observation()
        )
    )
    assert arrived.current_node == 'A'
    assert tracker.map_data.nodes['A'].detour is None


def test_nondiscriminating_enemy_keeps_existing_geometry_on_the_same_encounter() -> None:
    tracker = _tracker(
        {
            '0': _node((0.05, 0.1), ['A']),
            'A': _node((0.2, 0.2), ['B'], detour=True),
            'B': _node((0.8, 0.8), [], detour=True),
        }
    )
    moving = _motion(tracker, 1.0, (0.2, 0.2))
    arrived = tracker.observe(
        FusionObservation(
            'phase', 2.0, frame_id='spot', phase='SPOT_ENEMY_SUCCESS', enemies=_button_observation()
        )
    )
    assert arrived.current_node == 'A'
    assert arrived.node_weights == pytest.approx(moving.node_weights)
    assert arrived.diagnostics['distance']['available'] is False


def test_partial_enemy_templates_keep_unknown_fleet_neutral() -> None:
    tracker = _tracker(
        {
            'A': _node((0.2, 0.2)),
            'D': _node((0.9, 0.2)),
            'B': _node((0.5, 0.5), ships=('驱逐',) * 6),
            'C': _node((0.8, 0.8), ships=('战列',) * 6),
        }
    )
    enemy = EnemyObservation(
        raw_slots=('BB',) * 6,
        ships=('战列',) * 6,
        formation=1,
        formation_text='单纵阵',
        formation_confidence=0.99,
        detour=None,
        detour_score=None,
    )
    arrived = tracker.observe(
        FusionObservation('phase', 1.0, frame_id='spot', phase='SPOT_ENEMY_SUCCESS', enemies=enemy)
    )
    assert arrived.anomaly is None
    assert arrived.node_weights['C'] > arrived.node_weights['A'] > arrived.node_weights['B'] > 0
    assert arrived.current_node is None
    # A/D 均无变体：敌情证据对二者贡献相同（中性），不反向惩罚无资料节点。
    enemy_weights = arrived.diagnostics['enemy']['weights']
    assert enemy_weights['A'] == pytest.approx(enemy_weights['D'])


def test_matching_detour_supports_known_node_against_unknown_metadata() -> None:
    tracker = _tracker(
        {
            '0': _node((0.05, 0.1), ['A', 'B']),
            'A': _node((0.2, 0.2), [], detour=True),
            'B': _node((0.3, 0.2), []),
        }
    )
    moving = _motion(tracker, 1.0, (0.226, 0.2))
    arrived = tracker.observe(
        FusionObservation(
            'phase', 2.0, frame_id='spot', phase='SPOT_ENEMY_SUCCESS', enemies=_button_observation()
        )
    )
    assert arrived.node_weights['A'] > moving.node_weights['A']
    assert arrived.node_weights['B'] > 0
    # B 无变体也无迂回属性：敌情证据保持中性，只有 A 获得迂回正票。
    enemy_weights = arrived.diagnostics['enemy']['weights']
    assert enemy_weights['A'] > enemy_weights['B']


def test_temporary_destination_before_arrival_does_not_become_an_absorbing_state() -> None:
    tracker = _tracker(
        {
            '0': _node((0.05, 0.1), ['A']),
            'A': _node((0.2, 0.2), ['B']),
            'B': _node((0.8, 0.8), []),
        }
    )
    early = _motion(tracker, 1.0, (0.8, 0.8))
    assert early.node_weights['B'] > early.node_weights['A']
    assert early.current_node is None
    _motion(tracker, 2.0, (0.2, 0.2))
    arrived = _phase(tracker, 3.0)
    assert arrived.current_node == 'A'
    assert arrived.anomaly is None


def test_route_without_start_never_exports_internal_unknown_sentinel() -> None:
    tracker = _tracker(
        {
            'A': _node((0.2, 0.2), ['B']),
            'B': _node((0.8, 0.8), []),
        }
    )
    _motion(tracker, 1.0, (0.2, 0.2))
    first = _phase(tracker, 2.0)
    assert first.current_node == 'A'
    assert '0' not in first.best_route
    _proceed(tracker, 3.0)
    _motion(tracker, 4.0, (0.8, 0.8))
    arrived = _phase(tracker, 5.0)
    assert arrived.current_node == 'B'
    assert arrived.best_route == ('A', 'B')
