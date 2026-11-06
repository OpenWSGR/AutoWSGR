"""融合接管决策、帧来源、异常隔离和阶段归属的集成回归。"""

from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import numpy as np
import pytest

from autowsgr.combat import actions as actions_module
from autowsgr.combat import engine as engine_module
from autowsgr.combat import handlers as handlers_module
from autowsgr.combat.engine import CombatEngine
from autowsgr.combat.node_fusion import FusionObservation, NodeEstimate
from autowsgr.combat.node_fusion import integration as integration_module
from autowsgr.combat.node_fusion.calibration import CalibrationTotals
from autowsgr.combat.node_fusion.enemy import EnemyObservation
from autowsgr.combat.node_fusion.integration import TrackingSession
from autowsgr.combat.node_fusion.map import TrackingMap
from autowsgr.combat.node_fusion.replay import replay
from autowsgr.combat.plan import CombatMode, CombatPlan, NodeDecision
from autowsgr.combat.recognizer import CombatRecognizer
from autowsgr.combat.state import CombatPhase
from autowsgr.emulator.frame import CapturedFrame
from autowsgr.types import ConditionFlag, Formation


if TYPE_CHECKING:
    from pathlib import Path

    from autowsgr.emulator import AndroidController


def estimate(
    node: str = 'Z',
    *,
    stage: str = 'SPOT',
    ambiguous: bool = False,
    transition: str = 'same_encounter',
) -> NodeEstimate:
    return NodeEstimate(
        event_id=0,
        node_weights={node: 1.0},
        target_weights={},
        state_weights=({'location': node, 'stage': stage, 'variant': 0, 'weight': 1.0},),
        best_route=('0', node),
        history=({'event_id': 0, 'transition': transition},),
        revisions=(),
        contributions={},
        ambiguous=ambiguous,
        diagnostics={
            name: {'weights': {node: 1.0}}
            for name in ('distance', 'ray', 'history_prior', 'geometry', 'enemy', 'fusion')
        },
    )


class RecordingFusion:
    def __init__(self) -> None:
        self.observations = []
        self.result = estimate()

    def observe(self, observation: FusionObservation) -> NodeEstimate:
        self.observations.append(observation)
        event_id = len(self.observations) - 1
        history = ({'event_id': event_id, 'transition': self.result.history[0]['transition']},)
        return replace(self.result, event_id=event_id, history=history)


@pytest.fixture
def frame() -> CapturedFrame:
    return CapturedFrame(np.zeros((540, 960, 3), dtype=np.uint8), 73, 12.5)


@pytest.fixture
def evidence() -> EnemyObservation:
    return EnemyObservation(
        raw_slots=('DD',) * 6,
        ships=('驱逐',) * 6,
        formation=2,
        formation_text='复纵阵',
        formation_confidence=0.95,
        detour=None,
        detour_score=None,
    )


@pytest.fixture
def calibration_session(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TrackingSession:
    metadata = TrackingMap.from_dict(
        {
            '0': {
                'position': [0.1, 0.2],
                'next': ['A'],
                'type': 'NULL',
                'detour': False,
                'enemy_formations': [],
            },
            'A': {
                'position': [0.5, 0.2],
                'next': [],
                'type': 'FIGTH',
                'detour': False,
                'enemy_formations': [{'formation': 2, 'ships': ['驱逐'] * 6}],
            },
        }
    )
    monkeypatch.setattr(TrackingMap, 'load', lambda *_: metadata)
    monkeypatch.setattr(integration_module, 'CALIBRATION_TOTALS', CalibrationTotals())
    session = TrackingSession.start(CombatPlan(chapter=2, map_id=1), tmp_path)
    assert session is not None
    assert session.tracker is not None
    return session


def make_engine(
    frame: CapturedFrame,
    tmp_path: Path,
    *,
    single: bool = False,
    detour: bool = False,
    record_replay: bool = False,
) -> CombatEngine:
    context = SimpleNamespace(
        ctrl=MagicMock(),
        ocr=MagicMock(),
        config=SimpleNamespace(log=SimpleNamespace(dir=tmp_path, node_fusion_replay=record_replay)),
    )
    engine = CombatEngine(context)
    engine._plan = CombatPlan(
        mode=CombatMode.BATTLE if single else CombatMode.NORMAL,
        chapter=2,
        map_id=1,
        selected_nodes=['Z'],
        default_node=NodeDecision(formation=Formation.double_column),
        nodes={'Z': NodeDecision(formation=Formation.wedge, detour=detour)},
    )
    engine._node = 'A'
    engine._recognizer = SimpleNamespace(last_match=frame, last_frame=frame)
    if not single:
        engine._tracking = TrackingSession()
        engine._tracking.tracker = RecordingFusion()
        if record_replay:
            engine._tracking.log_path = tmp_path / 'tracking.jsonl'
        engine._tracking.detector = MagicMock(detection_status='no_cluster')
        engine._tracking.detector.detect.return_value = None
    return engine


def test_fused_node_controls_selection_and_formation_from_same_frame(
    monkeypatch: pytest.MonkeyPatch,
    frame: CapturedFrame,
    evidence: EnemyObservation,
    tmp_path: Path,
) -> None:
    engine = make_engine(frame, tmp_path, record_replay=True)
    observe, enter, formation = MagicMock(return_value=evidence), MagicMock(), MagicMock()
    monkeypatch.setattr(integration_module, 'observe_enemy', observe)
    monkeypatch.setattr(handlers_module, 'click_enter_fight', enter)
    monkeypatch.setattr(handlers_module, 'click_formation', formation)
    monkeypatch.setattr(handlers_module, 'get_enemy_info', MagicMock(side_effect=AssertionError))
    monkeypatch.setattr(
        handlers_module, 'get_enemy_formation', MagicMock(side_effect=AssertionError)
    )
    engine._phase = CombatPhase.SPOT_ENEMY_SUCCESS
    assert engine._make_decision(engine._phase) == ConditionFlag.FIGHT_CONTINUE
    observe.assert_called_once_with(frame.image, engine._ocr, mode='fight')
    first = engine._tracking.tracker.observations[0]
    assert (first.kind, first.phase, first.frame_id, first.timestamp) == (
        'phase',
        'SPOT_ENEMY_SUCCESS',
        73,
        12.5,
    )
    assert first.enemies is evidence
    assert first.decision_node == 'A'
    assert engine.current_node == 'Z'
    enter.assert_called_once()
    engine._phase = CombatPhase.FORMATION
    assert engine._make_decision(engine._phase) == ConditionFlag.FIGHT_CONTINUE
    formation.assert_called_once_with(engine._device, Formation.wedge)
    records = [
        json.loads(line) for line in engine._tracking.log_path.read_text('utf-8').splitlines()
    ]
    assert records[0]['estimate']['node_weights'] == {'Z': 1.0}
    assert set(records[0]['estimate']['diagnostics']) == {
        'distance',
        'ray',
        'history_prior',
        'geometry',
        'enemy',
        'fusion',
    }
    assert records[0]['observation']['decision_node'] == 'A'
    assert records[1]['observation']['decision_node'] == 'Z'
    assert 'image' not in records[0]['observation']


def test_single_battle_does_not_start_map_tracking(
    monkeypatch: pytest.MonkeyPatch, frame: CapturedFrame, tmp_path: Path
) -> None:
    engine = make_engine(frame, tmp_path, single=True)
    engine._plan.selected_nodes = ['A']
    enemies, formation = MagicMock(return_value={'DD': 6}), MagicMock(return_value='复纵阵')
    monkeypatch.setattr(handlers_module, 'get_enemy_info', enemies)
    monkeypatch.setattr(handlers_module, 'get_enemy_formation', formation)
    monkeypatch.setattr(handlers_module, 'image_exist', lambda *_: False)
    monkeypatch.setattr(handlers_module, 'click_enter_fight', MagicMock())
    engine._start_tracking()
    assert engine._tracking is None
    engine._make_decision(CombatPhase.SPOT_ENEMY_SUCCESS)
    enemies.assert_called_once()
    formation.assert_called_once()
    assert not list(tmp_path.iterdir())


def test_missing_spot_uses_formation_without_invented_enemy(
    monkeypatch: pytest.MonkeyPatch, frame: CapturedFrame, tmp_path: Path
) -> None:
    engine = make_engine(frame, tmp_path)
    engine._last_action = 'yes'
    clicked = MagicMock()
    monkeypatch.setattr(handlers_module, 'click_formation', clicked)
    engine._make_decision(CombatPhase.FORMATION)
    first = engine._tracking.tracker.observations[0]
    assert first.phase == 'FORMATION'
    assert first.enemies is None
    assert engine.current_node == 'Z'
    clicked.assert_called_once_with(engine._device, Formation.wedge)


@pytest.mark.parametrize('clicked', [False, True])
def test_detour_records_actual_dispatch_time(
    monkeypatch: pytest.MonkeyPatch,
    frame: CapturedFrame,
    evidence: EnemyObservation,
    tmp_path: Path,
    clicked: bool,
) -> None:
    engine = make_engine(frame, tmp_path, detour=True)
    monkeypatch.setattr(
        integration_module, 'observe_enemy', lambda *_a, **_k: replace(evidence, detour=True)
    )
    monkeypatch.setattr(integration_module.time, 'monotonic', lambda: 17.0)

    def click(device: AndroidController, *_args: object) -> bool:
        if clicked:
            device.click(0.5, 0.5)
        return clicked

    monkeypatch.setattr(handlers_module, 'click_image', click)
    leave = MagicMock(return_value=frame.image)
    monkeypatch.setattr(handlers_module, 'wait_leave_page', leave)
    engine._make_decision(CombatPhase.SPOT_ENEMY_SUCCESS)
    action = engine._tracking.tracker.observations[-1]
    assert (action.action, action.clicked, action.page_left) == (
        'detour',
        clicked,
        True if clicked else None,
    )
    assert action.timestamp == 17.0
    assert leave.call_count == int(clicked)
    assert engine._tracking.current_node == ('0' if clicked else 'Z')


def test_click_time_proxy_keeps_shared_click_interface(
    monkeypatch: pytest.MonkeyPatch, frame: CapturedFrame
) -> None:
    events, device = [], MagicMock()
    device.screenshot.return_value = frame.image
    device.click.side_effect = lambda *_args: events.append('click')

    def monotonic() -> float:
        events.append('timestamp')
        return 17.0

    monkeypatch.setattr(integration_module.time, 'monotonic', monotonic)
    monkeypatch.setattr(
        actions_module.ImageChecker,
        'find_any',
        lambda *_a, **_k: SimpleNamespace(center=(0.5, 0.5)),
    )
    clicked, timestamp = TrackingSession.time_click(
        device,
        lambda proxy: actions_module.click_image(proxy, handlers_module.TemplateKey.BYPASS, 2.5),
    )
    assert clicked
    assert timestamp == 17.0
    assert events == ['timestamp', 'click']
    device.click.assert_called_once_with(0.5, 0.5)


def test_motion_never_reuses_missing_position_or_applies_target(
    monkeypatch: pytest.MonkeyPatch, frame: CapturedFrame, tmp_path: Path
) -> None:
    engine = make_engine(frame, tmp_path)
    engine._tracking.tracker.result = replace(
        estimate('0->Z', stage='NAVIGATING'),
        target_weights={'Z': 1.0},
    )
    monkeypatch.setattr(engine_module, 'click_speed_up', lambda *_: None)
    monkeypatch.setattr(engine_module, 'dismiss_resource_confirm', lambda *_: None)
    poll = engine._get_poll_action(CombatPhase.PROCEED)
    poll(frame.image)
    poll(frame.image)
    assert len(engine._tracking.tracker.observations) == 1
    observation = engine._tracking.tracker.observations[0]
    assert observation.position is None
    assert (observation.timestamp, observation.frame_id, observation.detector_status) == (
        frame.captured_at,
        frame.sequence,
        'no_cluster',
    )
    assert engine.current_node == 'A'
    assert engine._tracking.current_node == '0'


def test_recognizer_preserves_matched_frame(
    monkeypatch: pytest.MonkeyPatch, frame: CapturedFrame
) -> None:
    context = SimpleNamespace(ctrl=MagicMock(), stop_event=SimpleNamespace(is_set=lambda: False))
    context.ctrl.capture_frame.return_value = frame
    recognizer = CombatRecognizer(context)
    monkeypatch.setattr(recognizer, '_match_phase', lambda *_: True)
    observed = []
    result = recognizer.wait_for_phase([CombatPhase.FORMATION], poll_action=observed.append)
    assert result is CombatPhase.FORMATION
    assert recognizer.last_match is frame
    assert recognizer.last_frame is frame
    assert observed[0] is frame.image
    context.ctrl.screenshot.assert_not_called()


def test_real_model_and_compact_multichannel_log(
    frame: CapturedFrame, evidence: EnemyObservation, tmp_path: Path
) -> None:
    engine = make_engine(frame, tmp_path, record_replay=True)
    engine._start_tracking()
    assert engine._tracking.tracker is not None
    assert engine.current_node == '0'
    engine._tracking_phase(CombatPhase.SPOT_ENEMY_SUCCESS, frame=frame, enemies=evidence)
    assert engine.current_node == 'A'
    records = [
        json.loads(line) for line in engine._tracking.log_path.read_text('utf-8').splitlines()
    ]
    assert records[0]['mode'] == 'fusion'
    assert 'history' not in records[-1]['estimate']
    assert 'state_weights' in records[-1]['estimate']
    assert 'diagnostics' in records[-1]['estimate']
    engine._tracking_action('fight', clicked=True, timestamp=13.0)
    records = [
        json.loads(line) for line in engine._tracking.log_path.read_text('utf-8').splitlines()
    ]
    assert 'state_weights' not in records[-1]['estimate']
    assert records[-1]['estimate']['state_count'] > 0


def test_default_session_keeps_debug_without_replay_serialization(
    monkeypatch: pytest.MonkeyPatch, frame: CapturedFrame, tmp_path: Path
) -> None:
    opened = MagicMock(side_effect=AssertionError('默认不创建回放目录'))
    snapshot = MagicMock(side_effect=AssertionError('默认不复制地图'))
    monkeypatch.setattr(TrackingSession, '_open_log', opened)
    monkeypatch.setattr(TrackingMap, 'to_dict', snapshot)
    session = TrackingSession.start(CombatPlan(chapter=2, map_id=1), tmp_path)
    assert session is not None
    assert session.tracker is not None
    assert session.log_path is None

    # 日常推断及 DEBUG 继续运行，但不产生回放所需的观测和估计副本。
    serializer = MagicMock(side_effect=AssertionError('不应序列化回放观测'))
    estimate_copy = MagicMock(side_effect=AssertionError('不应序列化回放估计'))
    debug = MagicMock()
    monkeypatch.setattr(integration_module, 'asdict', serializer)
    monkeypatch.setattr(NodeEstimate, 'as_dict', estimate_copy)
    monkeypatch.setattr(integration_module._log, 'debug', debug)
    session.phase(CombatPhase.FORMATION, frame, '0')
    assert session.tracker is not None
    assert session.estimate is not None
    opened.assert_not_called()
    snapshot.assert_not_called()
    serializer.assert_not_called()
    estimate_copy.assert_not_called()
    debug.assert_called_once()
    assert all(
        channel in debug.call_args.args[0]
        for channel in ('距离=', '射线=', '历史=', '几何=', '敌情=', '融合=')
    )
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('record_replay', [False, True])
def test_engine_applies_replay_setting(
    frame: CapturedFrame, tmp_path: Path, record_replay: bool
) -> None:
    engine = make_engine(frame, tmp_path, record_replay=record_replay)
    engine._start_tracking()
    assert engine._tracking.tracker is not None
    assert (engine._tracking.log_path is not None) is record_replay
    assert (tmp_path / 'node-fusion').exists() is record_replay


def test_end_reports_recognition_statistics_once_without_replay(
    monkeypatch: pytest.MonkeyPatch,
    calibration_session: TrackingSession,
    frame: CapturedFrame,
    evidence: EnemyObservation,
    tmp_path: Path,
) -> None:
    session = calibration_session
    info = MagicMock()
    monkeypatch.setattr(integration_module._log, 'info', info)
    session.phase(CombatPhase.SPOT_ENEMY_SUCCESS, frame, '0', evidence)
    assert session.current_node == 'A'
    session.action('end', CombatPhase.RESULT, 'A', timestamp=13.0)
    session.finish()
    session.finish()

    info.assert_called_once()
    assert '[NodeFusion统计]' in info.call_args.args[0]
    payload = json.loads(info.call_args.args[-1])
    assert payload['completed_sorties'] == 1
    assert payload['delta'] == payload['cumulative']
    assert payload['delta']['samples'] == 1
    assert payload['delta']['located'] == 1
    assert payload['delta']['ships']['correct'] == 6
    assert payload['delta']['ships']['errors'] == 0
    assert 'formation' not in payload['delta']
    assert 'detour' not in payload['delta']
    assert session.log_path is None
    assert not list(tmp_path.iterdir())


def test_statistics_failure_warns_without_disabling_node_control(
    monkeypatch: pytest.MonkeyPatch,
    calibration_session: TrackingSession,
    frame: CapturedFrame,
    evidence: EnemyObservation,
    tmp_path: Path,
) -> None:
    engine = make_engine(frame, tmp_path)
    session = calibration_session
    tracker = session.tracker
    engine._tracking = session
    engine._plan.selected_nodes = ['A']
    engine._plan.nodes = {'A': NodeDecision(formation=Formation.wedge)}
    session.phase(CombatPhase.SPOT_ENEMY_SUCCESS, frame, '0', evidence)
    engine._apply_tracking_node()
    assert engine.current_node == 'A'
    calculate = MagicMock(side_effect=RuntimeError('统计失败'))
    warning, info, formation = MagicMock(), MagicMock(), MagicMock()
    monkeypatch.setattr(integration_module, 'recognition_stats', calculate)
    monkeypatch.setattr(integration_module._log, 'warning', warning)
    monkeypatch.setattr(integration_module._log, 'info', info)
    monkeypatch.setattr(handlers_module, 'click_formation', formation)

    session.finish()
    session.finish()
    calculate.assert_called_once_with(tracker)
    warning.assert_called_once()
    assert '[NodeFusion统计]' in warning.call_args.args[0]
    info.assert_not_called()
    assert session.tracker is tracker
    assert engine.current_node == 'A'
    assert engine._make_decision(CombatPhase.FORMATION) is ConditionFlag.FIGHT_CONTINUE
    formation.assert_called_once_with(engine._device, Formation.wedge)
    assert session.tracker is tracker
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('invalid_metadata', [False, True])
def test_missing_metadata_leaves_unknown_without_old_fallback(
    monkeypatch: pytest.MonkeyPatch,
    frame: CapturedFrame,
    tmp_path: Path,
    invalid_metadata: bool,
) -> None:
    engine = make_engine(frame, tmp_path, record_replay=True)
    loader = MagicMock(return_value=None)
    if invalid_metadata:
        loader.side_effect = ValueError('地图元数据无效')
    monkeypatch.setattr(TrackingMap, 'load', loader)
    engine._start_tracking()
    assert engine._tracking.tracker is None
    assert engine.current_node == '0'
    records = [
        json.loads(line) for line in engine._tracking.log_path.read_text('utf-8').splitlines()
    ]
    assert records[-1]['kind'] == 'disabled'


def test_model_failure_prevents_formation_at_previous_node(
    monkeypatch: pytest.MonkeyPatch, frame: CapturedFrame, tmp_path: Path
) -> None:
    engine = make_engine(frame, tmp_path)
    engine._tracking.tracker = MagicMock()
    engine._tracking.tracker.observe.side_effect = RuntimeError('推断失败')
    clicked = MagicMock()
    monkeypatch.setattr(handlers_module, 'click_formation', clicked)
    assert engine._make_decision(CombatPhase.FORMATION) is ConditionFlag.SL
    assert engine._tracking.tracker is None
    assert engine.current_node == '0'
    clicked.assert_not_called()


def test_ambiguous_result_cannot_control_formation(
    monkeypatch: pytest.MonkeyPatch, frame: CapturedFrame, tmp_path: Path
) -> None:
    engine = make_engine(frame, tmp_path)
    engine._tracking.tracker.result = estimate(ambiguous=True)
    clicked = MagicMock()
    monkeypatch.setattr(handlers_module, 'click_formation', clicked)
    assert engine._make_decision(CombatPhase.FORMATION) is ConditionFlag.SL
    assert engine.current_node == '0'
    clicked.assert_not_called()


def test_each_sortie_starts_with_new_history(frame: CapturedFrame, tmp_path: Path) -> None:
    engine = make_engine(frame, tmp_path)
    previous = engine._tracking
    engine._reset()
    assert engine._tracking is None
    engine._start_tracking()
    assert engine._tracking is not previous
    assert engine._tracking.tracker.observations == []


def test_motion_requires_matching_capture_provenance(frame: CapturedFrame, tmp_path: Path) -> None:
    engine = make_engine(frame, tmp_path)
    engine._tracking_motion(frame.image.copy())
    engine._recognizer.last_frame = None
    engine._tracking_motion(frame.image)
    assert engine._tracking.tracker.observations == []


def test_proceed_timestamp_excludes_click_wait(
    monkeypatch: pytest.MonkeyPatch, frame: CapturedFrame, tmp_path: Path
) -> None:
    engine = make_engine(frame, tmp_path)
    engine._node = 'Z'
    engine._plan.nodes['Z'].proceed = True
    engine._phase = CombatPhase.PROCEED
    clock = [17.0]
    monkeypatch.setattr(handlers_module.time, 'monotonic', lambda: clock[0])

    def click(_device: AndroidController, *, go_forward: bool) -> None:
        assert go_forward
        clock[0] += 3.0

    monkeypatch.setattr(handlers_module, 'click_proceed', click)
    engine._handle_proceed()
    observation = engine._tracking.tracker.observations[-1]
    assert observation.action == 'proceed'
    assert observation.timestamp == 17.0
    assert clock[0] == 20.0


def test_log_failure_does_not_disable_only_tracker(
    monkeypatch: pytest.MonkeyPatch, frame: CapturedFrame, tmp_path: Path
) -> None:
    engine = make_engine(frame, tmp_path, record_replay=True)
    tracker = engine._tracking.tracker
    monkeypatch.setattr(engine._tracking, '_write', MagicMock(side_effect=OSError('磁盘已满')))
    clicked = MagicMock()
    monkeypatch.setattr(handlers_module, 'click_formation', clicked)
    assert engine._make_decision(CombatPhase.FORMATION) is ConditionFlag.FIGHT_CONTINUE
    assert engine._tracking.tracker is tracker
    assert engine._tracking.log_path is None
    assert engine.current_node == 'Z'
    clicked.assert_called_once_with(engine._device, Formation.wedge)


def test_detour_success_then_failed_spot_uses_next_node_rules(
    monkeypatch: pytest.MonkeyPatch, frame: CapturedFrame, tmp_path: Path
) -> None:
    engine = make_engine(frame, tmp_path)
    engine._last_action = 'detour'
    engine._formation_by_rule = Formation.single_column
    engine._plan.nodes['Z'].SL_when_detour_fails = True
    engine._plan.nodes['Z'].formation_when_spot_enemy_fails = Formation.single_horizontal
    engine._tracking.tracker.result = estimate('Z', stage='COMBAT', transition='new_encounter')
    clicked = MagicMock()
    monkeypatch.setattr(handlers_module, 'click_formation', clicked)
    assert engine._make_decision(CombatPhase.FORMATION) is ConditionFlag.FIGHT_CONTINUE
    clicked.assert_called_once_with(engine._device, Formation.single_horizontal)


def test_detour_failure_still_obeys_failure_sl(
    monkeypatch: pytest.MonkeyPatch, frame: CapturedFrame, tmp_path: Path
) -> None:
    engine = make_engine(frame, tmp_path)
    engine._last_action = 'detour'
    engine._plan.nodes['Z'].SL_when_detour_fails = True
    engine._tracking.tracker.result = estimate('Z', stage='COMBAT')
    clicked = MagicMock()
    monkeypatch.setattr(handlers_module, 'click_formation', clicked)
    assert engine._make_decision(CombatPhase.FORMATION) is ConditionFlag.SL
    clicked.assert_not_called()


def test_action_then_old_frame_cannot_restore_previous_confirmed_node(
    frame: CapturedFrame, tmp_path: Path
) -> None:
    engine = make_engine(frame, tmp_path)
    engine._tracking_phase(CombatPhase.SPOT_ENEMY_SUCCESS, frame=frame)
    assert engine.current_node == 'Z'
    engine._tracking_action('proceed', clicked=True, timestamp=13.0)
    engine._tracking.tracker.result = replace(estimate('Z'), ignored='frame predates last action')
    engine._tracking_phase(CombatPhase.FORMATION, frame=frame)
    assert engine.current_node == '0'


def test_event_map_uses_same_model_without_unverified_time_bound(tmp_path: Path) -> None:
    plan = CombatPlan(mode=CombatMode.EVENT, event_name='20260930', chapter='E', map_id=1)
    session = TrackingSession.start(plan, tmp_path)
    assert session is not None
    assert session.tracker is not None
    assert session.tracker.profile.min_travel_seconds is None


def test_enemy_reader_failure_still_uses_phase_history(
    monkeypatch: pytest.MonkeyPatch, frame: CapturedFrame, tmp_path: Path
) -> None:
    engine = make_engine(frame, tmp_path)
    monkeypatch.setattr(
        integration_module, 'observe_enemy', MagicMock(side_effect=ValueError('识别失败'))
    )
    assert engine._tracking_enemy_observation('fight') is None
    assert engine.current_node == 'Z'
    assert engine._tracking.tracker.observations[-1].enemies is None


def test_partial_map_warns_once_and_records_available_capabilities(
    monkeypatch: pytest.MonkeyPatch, frame: CapturedFrame, tmp_path: Path
) -> None:
    metadata = TrackingMap.from_dict(
        {
            '0': {'position': [0.1, 0.2], 'next': ['A']},
            'A': {'position': [0.5, 0.2], 'next': []},
        },
        source='旧地图.yaml',
    )
    tracker = RecordingFusion()
    tracker.result = estimate('A', stage='COMBAT')
    monkeypatch.setattr(TrackingMap, 'load', lambda *_: metadata)
    monkeypatch.setattr(integration_module, 'FusionTracker', lambda *_: tracker)
    warning = MagicMock()
    monkeypatch.setattr(integration_module._log, 'warning', warning)

    session = TrackingSession.start(CombatPlan(chapter=2, map_id=1), tmp_path, record_replay=True)
    assert session is not None
    assert session.tracker is tracker
    session.phase(CombatPhase.FORMATION, frame, '0')
    session.phase(CombatPhase.FIGHT_PERIOD, replace(frame, sequence=74, captured_at=13.0), 'A')

    warning.assert_called_once()
    message = warning.call_args.args[0].format(*warning.call_args.args[1:])
    assert all(text in message for text in ('自动降级', '旧地图.yaml', '节点类型', '敌情', '迂回'))
    assert '船位距离' in message
    assert '运动射线' in message
    assert '地图路由约束' in message
    records = [json.loads(line) for line in session.log_path.read_text('utf-8').splitlines()]
    start = records[0]
    assert start['capabilities']['distance']
    assert start['capabilities']['topology']
    assert not start['capabilities']['encounter_history']
    assert start['metadata_source'] == '旧地图.yaml'
    assert start['metadata_snapshot']['A']['type'] is None
    assert start['metadata_snapshot']['A']['enemy_formations'] is None
    assert start['degradation_reasons'] == list(metadata.degradation_reasons)
    assert not any(record['kind'] == 'disabled' for record in records)


def test_complete_map_does_not_emit_degradation_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    warning = MagicMock()
    monkeypatch.setattr(integration_module._log, 'warning', warning)
    session = TrackingSession.start(CombatPlan(chapter=2, map_id=1), tmp_path, record_replay=True)
    assert session is not None
    assert session.tracker is not None
    warning.assert_not_called()
    records = [json.loads(line) for line in session.log_path.read_text('utf-8').splitlines()]
    assert records[0]['degradation_reasons'] == []
    assert all(records[0]['capabilities'].values())


def test_legacy_event_map_tracks_and_replays_frozen_coordinates(
    monkeypatch: pytest.MonkeyPatch, frame: CapturedFrame, tmp_path: Path
) -> None:
    plan = CombatPlan(
        mode=CombatMode.EVENT,
        event_name='20260730',
        chapter='H',
        map_id=1,
        entrance='a',
    )
    warning = MagicMock()
    monkeypatch.setattr(integration_module._log, 'warning', warning)
    session = TrackingSession.start(plan, tmp_path, record_replay=True)
    assert session is not None
    assert session.tracker is not None
    metadata = session.tracker.map_data
    assert metadata.source.endswith('.yaml')
    assert not metadata.capabilities['encounter_history']
    assert session.tracker.profile.min_travel_seconds is None
    session.publish(
        FusionObservation('motion', 12.0, frame_id=72, position=metadata.nodes['A'].position)
    )
    session.phase(CombatPhase.FORMATION, frame, '0')
    assert session.current_node == 'A'
    warning.assert_called_once()

    # 回放必须使用当次记录的旧地图快照，不能改用后来生成的地图。
    monkeypatch.setattr(
        TrackingMap, 'load_event', MagicMock(side_effect=AssertionError('不应重新加载地图'))
    )
    summary = replay(session.log_path)
    assert summary['metadata_snapshot_used']
    assert summary['metadata_source'] == metadata.source
    assert summary['capabilities'] == metadata.capabilities
    assert summary['degradation_reasons'] == metadata.degradation_reasons
    assert summary['online_comparison'] == {'compared': 2, 'matches': 2, 'mismatches': []}
