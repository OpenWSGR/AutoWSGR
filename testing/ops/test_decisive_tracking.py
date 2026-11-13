"""小关会话、敌情纠偏和当场决策的集成约束。"""

from __future__ import annotations

import threading
from dataclasses import replace
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import numpy as np
import pytest

from autowsgr.combat.engine import CombatEngine
from autowsgr.combat.node_fusion.enemy import EnemyObservation
from autowsgr.combat.node_fusion.map import TrackingMap
from autowsgr.combat.node_fusion.model import FusionObservation
from autowsgr.combat.node_fusion.replay import replay
from autowsgr.combat.plan import CombatMode, CombatPlan, NodeDecision
from autowsgr.combat.state import CombatPhase
from autowsgr.emulator.frame import CapturedFrame
from autowsgr.ops.decisive import tracking as tracking_module
from autowsgr.ops.decisive.config import MapData
from autowsgr.ops.decisive.controller import DecisiveController
from autowsgr.ops.decisive.state import DecisiveState
from autowsgr.ops.decisive.tracking import DecisiveTrackingSession
from autowsgr.types import ConditionFlag, DecisivePhase, Formation


if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def metadata(monkeypatch: pytest.MonkeyPatch) -> TrackingMap:
    data = TrackingMap.from_dict(
        {
            name: {
                'next': [chr(ord(name) + 1)] if name != 'C' else [],
                'type': 'FIGHT',
                'enemy_formations': [{'ships': [ship] * 6}],
            }
            for name, ship in zip('ABC', ('驱逐', '机场', '战列'), strict=True)
        }
    )
    monkeypatch.setattr(MapData, 'tracking_map', lambda *_: data)
    return data


def frame(sequence: int) -> CapturedFrame:
    return CapturedFrame(np.zeros((2, 2, 3), dtype=np.uint8), sequence, float(sequence))


def test_known_a_skips_sampling_advances_once_and_replays(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session = DecisiveTrackingSession(6, 1, known_start=True, log_dir=tmp_path, record_replay=True)
    assert session.current_node == 'A'
    assert not session.sample_node_label
    session.map_ready(frame(1))
    encounter = session.encounter_id
    session.phase(CombatPhase.RESULT, frame(2), 'A')
    monkeypatch.setattr(tracking_module.time, 'monotonic', lambda: 3.0)
    assert session.complete_encounter(encounter)
    assert not session.complete_encounter(encounter)
    assert session.current_node == 'B'
    session.map_ready(frame(4))
    assert session.encounter_id != encounter
    result = replay(session.log_path)
    assert result['phases'][-1]['node_weights'] == session.estimate.node_weights
    assert result['online_comparison']['mismatches'] == []


def test_completion_query_and_duplicate_survive_disabled_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = DecisiveTrackingSession(6, 1, known_start=True)
    session.phase(CombatPhase.RESULT, frame(1), 'A')
    encounter = session.encounter_id
    monkeypatch.setattr(tracking_module.time, 'monotonic', lambda: 2.0)
    assert session.complete_encounter(encounter)
    model = session.tracker
    completion = model.observations[-1]
    session.publish(replace(completion, timestamp=3.0))
    assert session.estimate.ignored == 'duplicate encounter completion'
    assert session.completed_encounter(encounter) is completion

    session.fail('synthetic device failure after completion')

    assert session.tracker is None
    assert session.completed_encounter(encounter) is completion
    count = len(model.observations)
    assert not session.complete_encounter(encounter)
    assert len(model.observations) == count


def test_decisive_ignored_observation_does_not_restore_action_cleared_node() -> None:
    session = DecisiveTrackingSession(6, 1, known_start=True)
    session.phase(CombatPhase.RESULT, frame(1), 'A')
    session.action('retreat', CombatPhase.RESULT, 'A', clicked=True, timestamp=2.0)
    assert session.current_node == '0'
    assert session.estimate.current_node == 'A'

    session.publish(
        FusionObservation('action', 2.0, action='retreat', clicked=True, phase='RESULT')
    )

    assert session.estimate.ignored == 'duplicate action event'
    assert session.current_node == '0'
    session.phase(CombatPhase.FORMATION, frame(3), '0')
    assert session.current_node == 'A'


def test_unknown_resume_enemy_corrects_bad_initial_label(monkeypatch: pytest.MonkeyPatch) -> None:
    session = DecisiveTrackingSession(6, 1)
    assert session.sample_node_label
    assert set(session.estimate.node_weights) == set('ABC')
    session.map_ready(frame(1), 'A')
    evidence = EnemyObservation(
        raw_slots=('AF',) * 6,
        ships=('机场',) * 6,
        formation=None,
        formation_text='',
        formation_confidence=None,
        detour=None,
        detour_score=None,
    )
    session.phase(CombatPhase.SPOT_ENEMY_SUCCESS, frame(2), session.current_node, evidence)
    assert max(session.estimate.node_weights, key=session.estimate.node_weights.get) == 'B'
    assert session.current_node == '0'  # 冲突时保留歧义，不冒充确定定位。
    monkeypatch.setattr(tracking_module.time, 'monotonic', lambda: 3.0)
    session.complete_encounter(session.encounter_id)
    session.map_ready(frame(4))
    session.phase(
        CombatPhase.SPOT_ENEMY_SUCCESS,
        frame(5),
        session.current_node,
        replace(evidence, raw_slots=('BB',) * 6, ships=('战列',) * 6),
    )
    assert session.current_node == 'C'
    assert not session.sample_node_label
    # 停采只控制主动地图字母识别，融合器仍接受阵型页及新敌情。
    session.phase(CombatPhase.FORMATION, frame(6), 'C')
    assert session.current_node == 'C'
    session.request_node_sample('页面冲突')
    assert session.sample_node_label
    session.phase(CombatPhase.NIGHT_PROMPT, frame(7), 'C')
    assert session.sample_node_label


def test_sampling_hysteresis_preserves_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    session = DecisiveTrackingSession(6, 1)
    original = session.tracker.observe
    for confidence, expected in ((0.96, False), (0.9, False), (0.79, True), (0.9, True)):
        value = replace(
            session.estimate,
            node_weights={'A': confidence, 'B': 1 - confidence},
            ambiguous=False,
        )
        monkeypatch.setattr(session.tracker, 'observe', lambda _, value=value: value)
        session.map_ready(frame(1))
        assert session.sample_node_label is expected
        assert len(session.estimate.node_weights) == 2
    monkeypatch.setattr(session.tracker, 'observe', original)


def test_engine_borrows_session_and_does_not_close_it(monkeypatch: pytest.MonkeyPatch) -> None:
    session = DecisiveTrackingSession(6, 1, known_start=True)
    session.finish = MagicMock()
    engine = CombatEngine(SimpleNamespace(ctrl=MagicMock(), ocr=MagicMock()))
    monkeypatch.setattr(engine, '_step', lambda: ConditionFlag.FIGHT_END)
    result = engine.fight(CombatPlan(mode=CombatMode.DECISIVE), [], tracking_session=session)
    assert result.flag == ConditionFlag.OPERATION_SUCCESS
    assert engine._tracking is session
    session.finish.assert_not_called()
    assert session.current_node == 'A'


def test_ambiguous_tactics_use_fallback_and_same_tactics_can_proceed() -> None:
    session = DecisiveTrackingSession(6, 1)
    engine = CombatEngine(SimpleNamespace(ctrl=MagicMock(), ocr=MagicMock()))
    fallback = NodeDecision(formation=Formation.double_column, night=True)
    selected = NodeDecision(formation=Formation.single_column, night=False)
    engine._plan = CombatPlan(
        mode=CombatMode.DECISIVE,
        default_node=fallback,
        nodes={'A': selected, 'B': selected, 'C': fallback},
    )
    engine._tracking = session
    engine._node = '0'
    assert engine._get_current_decision() == fallback
    engine._plan.nodes['C'] = selected
    assert engine._get_current_decision() == selected
    session.map_ready(frame(1), 'C')
    engine._apply_tracking_node()
    assert engine._get_current_decision() == selected


def test_ignored_completion_keeps_local_encounter(monkeypatch: pytest.MonkeyPatch) -> None:
    session = DecisiveTrackingSession(6, 1, known_start=True)
    session.map_ready(frame(10))
    encounter = session.encounter_id
    monkeypatch.setattr(tracking_module.time, 'monotonic', lambda: 3.0)
    with pytest.raises(RuntimeError, match='completed decisive encounter'):
        session.complete_encounter(encounter)
    assert session.encounter_id == encounter
    assert session.current_node == 'A'


@pytest.mark.parametrize('real_clear', [False, True])
def test_controller_waits_for_page_and_submits_one_step(
    monkeypatch: pytest.MonkeyPatch, real_clear: bool
) -> None:
    session = DecisiveTrackingSession(6, 1, known_start=real_clear)
    session.map_ready(frame(1), None if real_clear else 'C')
    session.phase(CombatPhase.RESULT, frame(2), session.current_node)
    monkeypatch.setattr(tracking_module.time, 'monotonic', lambda: 3.0)
    controller = DecisiveController.__new__(DecisiveController)
    controller._ctx = SimpleNamespace(stop_event=threading.Event())
    controller._ctrl = MagicMock()
    controller._ctrl.capture_frame.return_value = frame(4)
    controller._state = DecisiveState(chapter=6, stage=1, node=session.current_node)
    controller._tracking = session
    controller._battle_encounter_id = session.encounter_id
    controller._map = MagicMock()
    controller._map.is_stage_clear.return_value = real_clear
    controller._map.detect_decisive_phase.return_value = DecisivePhase.CHOOSE_FLEET
    controller._POST_COMBAT_INTERVAL = 0
    controller._handle_node_result()
    expected = DecisivePhase.STAGE_CLEAR if real_clear else DecisivePhase.CHOOSE_FLEET
    assert controller.state.phase == expected
    assert sum(obs.action == 'encounter_complete' for obs in session.tracker.observations) == 1
    if real_clear:
        assert session.estimate.node_weights == {'C': 1.0}
        controller._map.confirm_stage_clear.return_value = []
        controller._handle_stage_clear()
        assert controller._tracking is None
        assert controller._known_start_stage == 2
        assert controller.state.node == 'A'
    else:
        assert session.estimate.node_weights['B'] > 0
        assert not any(row['stage'] == 'TERMINAL_PENDING' for row in session.estimate.state_weights)
