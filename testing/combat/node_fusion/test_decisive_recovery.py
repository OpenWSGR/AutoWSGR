"""用合成顺序地图验证错误字母恢复，不依赖本地采集记录或随机掉落。"""

from __future__ import annotations

import pytest

from autowsgr.combat.node_fusion import (
    FusionObservation,
    FusionProfile,
    FusionTracker,
    NodeEstimate,
)
from autowsgr.combat.node_fusion.enemy import EnemyObservation
from autowsgr.combat.node_fusion.map import TrackingMap


def _enemy(ships: tuple[str | None, ...]) -> EnemyObservation:
    return EnemyObservation(
        raw_slots=(),
        ships=ships,
        formation=None,
        formation_text='',
        formation_confidence=None,
        detour=None,
        detour_score=None,
    )


def _phase(
    tracker: FusionTracker,
    encounter: str,
    phase: str = 'DECISIVE_MAP_READY',
    *,
    letter: str | None = None,
    enemy: EnemyObservation | None = None,
) -> NodeEstimate:
    event = len(tracker.observations) + 1
    estimate = tracker.observe(
        FusionObservation(
            'phase',
            float(event),
            frame_id=event,
            phase=phase,
            node_label=letter,
            enemies=enemy,
            encounter_id=encounter,
        )
    )
    assert estimate.anomaly is None
    assert estimate.ignored is None
    if phase != 'DECISIVE_STAGE_CLEAR':
        assert all(row['stage'] != 'END' for row in estimate.state_weights)
    return estimate


def _complete(tracker: FusionTracker, encounter: str) -> NodeEstimate:
    estimate = tracker.observe(
        FusionObservation(
            'action',
            float(len(tracker.observations) + 1),
            action='encounter_complete',
            encounter_id=encounter,
        )
    )
    assert estimate.anomaly is None
    assert estimate.ignored is None
    assert all(row['stage'] != 'END' for row in estimate.state_weights)
    return estimate


@pytest.mark.parametrize('letter_accuracy', [0.90, 0.96])
def test_later_enemy_resolves_partial_evidence_conflict_without_more_letters(
    letter_accuracy: float,
) -> None:
    names = 'ABCD'
    metadata = TrackingMap.from_dict(
        {
            name: {
                'next': [names[index + 1]] if index < 3 else [],
                'enemy_formations': [{'ships': [ship] * 6}],
            }
            for index, (name, ship) in enumerate(
                zip(names, ('驱逐', '轻巡', '机场', '战列'), strict=True)
            )
        }
    )
    tracker = FusionTracker(
        metadata,
        FusionProfile(node_label_accuracy=letter_accuracy),
        dynamics='decisive',
    )
    first = _phase(tracker, 'first', letter='C')
    assert first.current_node == 'C'
    assert first.node_weights['C'] == pytest.approx(letter_accuracy)
    assert set(first.node_weights) == set(names)

    # 第一个敌情只有一个有效槽，与错误字母冲突时保留歧义和完整候选。
    partial = _phase(
        tracker,
        'first',
        'SPOT_ENEMY_SUCCESS',
        enemy=_enemy(('驱逐', None, None, None, None, None)),
    )
    assert partial.ambiguous
    _phase(tracker, 'first', 'RESULT')
    _complete(tracker, 'first')
    assert _phase(tracker, 'second').ambiguous

    # 后续完全不读取字母；即便首次权重已超过停采阈值，新敌情仍能纠偏。
    corrected = _phase(tracker, 'second', 'SPOT_ENEMY_SUCCESS', enemy=_enemy(('轻巡',) * 6))
    assert corrected.current_node == 'B'
    assert corrected.node_weights['B'] > 0.90
    assert _phase(tracker, 'second', 'FORMATION').current_node == 'B'
    assert _phase(tracker, 'second', 'NIGHT_PROMPT').current_node == 'B'
    _phase(tracker, 'second', 'RESULT')
    _complete(tracker, 'second')

    for encounter in ('third', 'fourth'):
        _phase(tracker, encounter)
        _phase(tracker, encounter, 'RESULT')
        _complete(tracker, encounter)
    final = _phase(tracker, 'finished', 'DECISIVE_STAGE_CLEAR')
    assert final.best_route == tuple(names)
    assert final.history[0]['node_weights']['A'] == pytest.approx(1.0)
    assert all(row['stage'] == 'END' for row in final.state_weights)
    assert final.current_node is None


def test_next_page_eliminates_false_terminal_without_any_spotting() -> None:
    tracker = FusionTracker(
        TrackingMap.from_dict({'A': {'next': ['B']}, 'B': {'next': []}}),
        dynamics='decisive',
    )
    assert _phase(tracker, 'first', letter='B').current_node == 'B'
    _phase(tracker, 'first', 'RESULT')
    pending = _complete(tracker, 'first')
    assert pending.current_node is None
    assert any(row['stage'] == 'TERMINAL_PENDING' for row in pending.state_weights)

    following = _phase(tracker, 'second')
    assert following.node_weights == {'B': 1.0}
    assert not any(row['stage'] == 'TERMINAL_PENDING' for row in following.state_weights)
    assert following.history[0]['node_weights'].get('B', 0) == 0
    for phase in ('FORMATION', 'NIGHT_PROMPT', 'RESULT'):
        assert _phase(tracker, 'second', phase).current_node == 'B'
    _complete(tracker, 'second')
    final = _phase(tracker, 'finished', 'DECISIVE_STAGE_CLEAR')
    assert final.best_route == ('A', 'B')
    assert all(row['stage'] == 'END' for row in final.state_weights)
    assert all(observation.enemies is None for observation in tracker.observations)
