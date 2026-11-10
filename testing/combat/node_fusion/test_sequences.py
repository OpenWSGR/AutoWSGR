"""基于真实地图拓扑和敌情配置的离线遭遇回放。

测试只输入观测，不创建模拟器或控制器，也不执行游戏操作；动作记录仅用于
描述历史中的操作意图。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
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


def _map(chapter: int, map_id: int) -> TrackingMap:
    metadata = TrackingMap.load(chapter, map_id)
    assert metadata is not None
    return metadata


def _enemy(metadata: TrackingMap, name: str, variant: int = 0) -> EnemyObservation:
    node = metadata.nodes[name]
    fleet = node.enemy_formations[variant]
    return EnemyObservation(
        raw_slots=(),
        ships=(*fleet.ships, *((None,) * (6 - len(fleet.ships)))),
        formation=fleet.formation,
        formation_text='',
        formation_confidence=None,
        detour=True if node.detour else None,
        detour_score=None,
        valid_slots=True,
    )


@dataclass
class Replay:
    tracker: FusionTracker
    timestamp: float = 0.0

    @classmethod
    def create(cls, metadata: TrackingMap) -> Replay:
        return cls(FusionTracker(metadata, FusionProfile(min_travel_seconds=1.0)))

    def phase(
        self,
        phase: str = 'SPOT_ENEMY_SUCCESS',
        enemy: EnemyObservation | None = None,
        decision_node: str | None = None,
    ) -> NodeEstimate:
        self.timestamp += 2.0
        estimate = self.tracker.observe(
            FusionObservation(
                kind='phase',
                timestamp=self.timestamp,
                frame_id=len(self.tracker.observations) + 1,
                phase=phase,
                enemies=enemy,
                decision_node=decision_node,
            )
        )
        assert estimate.anomaly is None
        return estimate

    def action(self, action: str, decision_node: str | None = None) -> NodeEstimate:
        self.timestamp += 2.0
        estimate = self.tracker.observe(
            FusionObservation(
                kind='action',
                timestamp=self.timestamp,
                action=action,
                clicked=True,
                decision_node=decision_node,
            )
        )
        assert estimate.anomaly is None
        return estimate

    def fight_and_proceed(self, decision_node: str | None = None) -> None:
        self.action('fight', decision_node)
        self.phase('FORMATION', decision_node=decision_node)
        self.action('formation', decision_node)
        self.phase('FIGHT_PERIOD', decision_node=decision_node)
        self.phase('RESULT', decision_node=decision_node)
        self.phase('PROCEED', decision_node=decision_node)
        self.action('proceed', decision_node)


@pytest.mark.parametrize(
    ('target', 'variant', 'expected_route'),
    [('C', 0, ('0', 'B', 'C')), ('F', 1, ('0', 'B', 'D', 'F'))],
)
def test_2_1_first_encounter_crosses_blank_nodes(
    target: str, variant: int, expected_route: tuple[str, ...]
) -> None:
    metadata = _map(2, 1)
    replay = Replay.create(metadata)
    estimate = replay.phase(enemy=_enemy(metadata, target, variant), decision_node='B')
    assert estimate.best_route == expected_route
    assert max(estimate.node_weights, key=estimate.node_weights.get) == target
    assert estimate.node_weights[target] > 0.9
    assert not {'0', 'B', 'D'} & estimate.node_weights.keys()


def test_2_5_b_c_g_uses_formation_to_separate_identical_fleets() -> None:
    metadata = _map(2, 5)
    replay = Replay.create(metadata)
    replay.phase(enemy=_enemy(metadata, 'A', 1), decision_node='A')
    replay.fight_and_proceed('A')
    at_b = replay.phase(enemy=_enemy(metadata, 'B'), decision_node='B')
    assert max(at_b.node_weights, key=at_b.node_weights.get) == 'B'
    replay.fight_and_proceed('B')
    # F 与 G 的六槽完全相同，阵型分别是 2 和 4。
    assert (
        metadata.nodes['F'].enemy_formations[0].ships
        == metadata.nodes['G'].enemy_formations[0].ships
    )
    estimate = replay.phase(enemy=_enemy(metadata, 'G'), decision_node='F')
    assert estimate.best_route == ('0', 'A', 'B', 'C', 'G')
    assert estimate.node_weights['G'] > 0.9
    assert estimate.node_weights['F'] > 0  # OCR 可能出错，仍保留其他解释。


def test_9_2_recovers_g_h_m_o_without_any_motion_frames() -> None:
    metadata = _map(9, 2)
    replay = Replay.create(metadata)
    for name in ('A', 'D', 'G', 'H', 'M', 'O'):
        estimate = replay.phase(enemy=_enemy(metadata, name), decision_node='M')
        assert max(estimate.node_weights, key=estimate.node_weights.get) == name
        assert estimate.node_weights[name] > 0.8
        if name != 'O':
            replay.action('detour', decision_node='M')
    assert estimate.best_route == ('0', 'A', 'D', 'G', 'H', 'M', 'O')
    assert not estimate.ambiguous
    best_state = max(estimate.state_weights, key=lambda state: state['weight'])
    assert (best_state['location'], best_state['stage']) == ('O', 'SPOT')
    assert any(
        state['location'] == 'M' and state['stage'] == 'DETOUR_PENDING' and state['weight'] > 0
        for state in estimate.state_weights
    )
    assert all(event.kind != 'motion' for event in replay.tracker.observations)
    assert all(event.decision_node == 'M' for event in replay.tracker.observations)


def _node(
    ships: tuple[str, ...],
    next_nodes: tuple[str, ...] = (),
    *,
    silent: bool = False,
) -> dict[str, Any]:
    return {
        'type': 'NULL' if silent else 'FIGHT',
        'detour': False,
        'position': [0.5, 0.5],
        'next': list(next_nodes),
        'enemy_formations': [] if silent else [{'formation': 1, 'ships': list(ships)}],
    }


def test_later_evidence_revises_earlier_node_without_rewriting_action_history() -> None:
    metadata = TrackingMap.from_dict(
        {
            '0': _node((), ('A', 'B'), silent=True),
            'A': _node(('战列',), ('C',)),
            'B': _node(('战巡',), ('D',)),
            'C': _node(('驱逐',) * 6),
            'D': _node(('航母',) * 6, ('E',)),
            'E': _node(('机场',) * 6),
        }
    )
    replay = Replay.create(metadata)
    initial = replay.phase(enemy=_enemy(metadata, 'A'), decision_node='A')
    assert initial.node_weights['A'] > 0.9
    assert initial.node_weights['B'] > 0
    initial_observation = replay.tracker.observations[0]
    replay.fight_and_proceed('A')
    at_d = replay.phase(enemy=_enemy(metadata, 'D'), decision_node='C')
    assert at_d.best_route == ('0', 'B', 'D')
    assert at_d.node_weights['D'] > at_d.node_weights['C'] > 0
    assert any(row['event_id'] == 0 and row['after'][0] == 'B' for row in at_d.revisions)
    executed_before = tuple(
        event for event in replay.tracker.observations if event.kind == 'action'
    )
    replay.fight_and_proceed('C')
    # A→C 已到终点，只有保留的 B→D 历史能够继续进入 E。
    final = replay.phase(enemy=_enemy(metadata, 'E'), decision_node='C')
    assert final.best_route == ('0', 'B', 'D', 'E')
    assert set(final.node_weights) == {'E'}
    assert final.node_weights['E'] > 0.99
    first = next(row for row in final.history if row['event_id'] == 0)
    assert first['best_node'] == first['viterbi_node'] == 'B'
    assert first['node_weights']['B'] > 0.99
    assert first['node_weights'].get('A', 0) == 0
    assert replay.tracker.observations[0] is initial_observation
    assert initial_observation.decision_node == 'A'
    actual_actions = tuple(event for event in replay.tracker.observations if event.kind == 'action')
    assert actual_actions[: len(executed_before)] == executed_before
    assert all(event.decision_node == 'A' for event in executed_before)
    assert first['decision_node'] == 'A'


def test_2_1_identical_e_f_enemy_signature_preserves_both_legal_histories() -> None:
    metadata = _map(2, 1)
    replay = Replay.create(metadata)
    replay.phase()  # 敌情缺失，首次遭遇可能在 A、C 或 F。
    replay.fight_and_proceed()
    replay.phase()  # 剩余历史为 0-A-C 和 0-B-C-E。
    replay.fight_and_proceed()
    assert metadata.nodes['E'].enemy_formations[1] == metadata.nodes['F'].enemy_formations[1]
    estimate = replay.phase(enemy=_enemy(metadata, 'E', 1))
    assert set(estimate.node_weights) == {'E', 'F'}
    assert estimate.node_weights['E'] == pytest.approx(2 / 3)
    assert estimate.node_weights['F'] == pytest.approx(1 / 3)
    assert estimate.ambiguous


def test_7_4_battle_loop_can_visit_b_again() -> None:
    metadata = _map(7, 4)
    replay = Replay.create(metadata)
    for name in ('B', 'E', 'D'):
        estimate = replay.phase(enemy=_enemy(metadata, name), decision_node=name)
        assert max(estimate.node_weights, key=estimate.node_weights.get) == name
        if name == 'D':
            replay.action('detour', 'D')
        else:
            replay.fight_and_proceed(name)
    estimate = replay.phase(enemy=_enemy(metadata, 'B'), decision_node='D')
    assert estimate.best_route == ('0', 'B', 'E', 'D', 'B')
    assert max(estimate.node_weights, key=estimate.node_weights.get) == 'B'
    assert estimate.node_weights['B'] > replay.tracker.profile.ambiguity_threshold
    assert not estimate.ambiguous


def test_7_2_loss_chain_can_finish_without_another_battle() -> None:
    metadata = _map(7, 2)
    replay = Replay.create(metadata)
    replay.phase(enemy=_enemy(metadata, 'A'))
    replay.fight_and_proceed('A')
    estimate = replay.phase('MAP_PAGE', decision_node='A')
    assert estimate.best_route == ('0', 'A', 'C', 'I')
    assert estimate.node_weights == {'I': pytest.approx(1)}
    assert all(state['stage'] == 'END' for state in estimate.state_weights)


@pytest.mark.parametrize('valid_slots', [True, False])
def test_unknown_ocr_and_no_slots_do_not_mean_empty_enemy_fleet(valid_slots: bool) -> None:
    metadata = _map(2, 1)
    unavailable = EnemyObservation(
        raw_slots=('NO',) * 6,
        ships=(None,) * 6,
        formation=None,
        formation_text='unreadable',
        formation_confidence=0.01,
        detour=None,
        detour_score=None,
        valid_slots=valid_slots,
    )
    missing = Replay.create(metadata).phase()
    observed = Replay.create(metadata).phase(enemy=unavailable)
    assert observed.node_weights == pytest.approx(missing.node_weights)
    assert set(observed.node_weights) == {'A', 'C', 'F'}
    assert observed.ambiguous
    assert observed.anomaly is None


def test_legacy_labels_cannot_filter_candidates_or_change_predictions() -> None:
    metadata = _map(2, 5)
    source = Replay.create(metadata)
    source.phase(enemy=_enemy(metadata, 'A'))
    source.fight_and_proceed()
    source.phase(enemy=_enemy(metadata, 'B'))
    source.fight_and_proceed()
    source.phase(enemy=_enemy(metadata, 'G'))
    reference = Replay.create(metadata).tracker
    incorrect = Replay.create(metadata).tracker
    for event in source.tracker.observations:
        expected = reference.observe(event)
        actual = incorrect.observe(replace(event, decision_node='NOT_A_MAP_NODE'))
        assert actual.node_weights == pytest.approx(expected.node_weights)
        assert actual.target_weights == pytest.approx(expected.target_weights)
        assert actual.best_route == expected.best_route
        assert actual.anomaly == expected.anomaly
    assert incorrect.estimate.best_route == ('0', 'A', 'B', 'C', 'G')
    assert all(event.decision_node == 'NOT_A_MAP_NODE' for event in incorrect.observations)


def test_sparse_motion_follows_bent_blank_route_instead_of_endpoint_chord() -> None:
    # C 与 D 的最终坐标和敌情相同，只能靠航迹区分：
    # C 必须沿 0→B→C 直角路线到达，D 则沿直线到达。
    nodes = {
        '0': _node((), ('B', 'D'), silent=True),
        'B': _node((), ('C',), silent=True),
        'C': _node(('驱逐',) * 6),
        'D': _node(('驱逐',) * 6),
    }
    for name, position in {
        '0': [0.1, 0.1],
        'B': [0.6, 0.1],
        'C': [0.6, 0.8],
        'D': [0.6, 0.8],
    }.items():
        nodes[name]['position'] = position
    tracker = FusionTracker(TrackingMap.from_dict(nodes))
    bend = tracker.observe(FusionObservation('motion', 1.0, frame_id=1, position=(0.6, 0.1)))
    assert bend.target_weights['C'] > bend.target_weights['D'] > 0
    assert set(bend.node_weights) == {'0->B', 'B->C', '0->D'}
    after_gap = tracker.observe(FusionObservation('motion', 4.0, frame_id=2, position=(0.6, 0.6)))
    assert max(after_gap.node_weights, key=after_gap.node_weights.get) == 'B->C'
    assert after_gap.target_weights['C'] > after_gap.target_weights['D'] > 0
    assert all(state['stage'] == 'NAVIGATING' for state in after_gap.state_weights)
    assert 'C' not in after_gap.node_weights  # 预测目的点不代表已经发生新遭遇。
    arrived = tracker.observe(FusionObservation('phase', 4.5, frame_id=3, phase='FORMATION'))
    assert arrived.node_weights['C'] > arrived.node_weights['D'] > 0
    assert arrived.best_route == ('0', 'B', 'C')
