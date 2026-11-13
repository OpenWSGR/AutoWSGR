"""采集不能改变实战识别次数，也不能把中止当作推进。"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, replace
from itertools import count
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from autowsgr.combat.engine import CombatEngine
from autowsgr.combat.history import CombatResult
from autowsgr.combat.node_fusion.enemy import EnemyObservation
from autowsgr.combat.node_fusion.model import FusionObservation
from autowsgr.combat.plan import CombatMode, CombatPlan
from autowsgr.combat.state import CombatPhase
from autowsgr.emulator.frame import CapturedFrame
from autowsgr.image_resources import Templates
from autowsgr.infra import DecisiveConfig, UserConfig
from autowsgr.ops.decisive.controller import DecisiveController, DecisiveResult
from autowsgr.ops.decisive.logic import DecisiveLogic
from autowsgr.ops.decisive.state import DecisiveState
from autowsgr.ops.decisive.tracking import DecisiveTrackingSession
from autowsgr.types import ConditionFlag, DecisiveEntryStatus, DecisivePhase, Formation
from autowsgr.ui.decisive.map_controller import DecisiveMapController

from tools.decisive.collect import CollectionController, RecordingCombatEngine, main, parse_args
from tools.decisive.recording import FileStopEvent, RecordingDevice, SampleArchive
from tools.decisive.replay_collection import convert_collection


def _map_pixels() -> np.ndarray:
    pixels = np.zeros((720, 1280, 3), dtype=np.uint8)
    pixels[200:240, 480:520] = (230, 207, 95)
    pixels[640:699, 1050:1210] = cv2.resize(Templates.Decisive.MAP_PAGE.image, (160, 59))
    return pixels


@pytest.mark.parametrize(
    ('flag', 'stopped', 'expected'),
    [
        (ConditionFlag.OPERATION_SUCCESS, False, DecisivePhase.NODE_RESULT),
        (ConditionFlag.OPERATION_SUCCESS, True, DecisivePhase.FINISHED),
        (ConditionFlag.FIGHT_END, False, DecisivePhase.FINISHED),
        (ConditionFlag.SL, False, DecisivePhase.FINISHED),
        (ConditionFlag.DOCK_FULL, False, DecisivePhase.DOCK_FULL),
    ],
)
def test_only_completed_combat_reaches_node_result(
    flag: ConditionFlag, stopped: bool, expected: DecisivePhase
) -> None:
    controller = DecisiveController.__new__(DecisiveController)
    controller._ctx = SimpleNamespace(stop_event=threading.Event())
    if stopped:
        controller._ctx.stop_event.set()
    controller._state = DecisiveState(stage=1, node='J', phase=DecisivePhase.IN_COMBAT)
    controller._tracking = DecisiveTrackingSession(6, 1)
    controller._tracking.map_ready(CapturedFrame(np.zeros((2, 2, 3), dtype=np.uint8), 1, 1.0), 'J')
    controller._ensure_tracking = MagicMock(return_value=controller._tracking)
    controller._logic = SimpleNamespace(
        get_formation=lambda _node: Formation.double_column, is_key_point=lambda _node: True
    )
    controller._run_combat = MagicMock(return_value=CombatResult(flag=flag))
    controller._sync_ship_states = MagicMock()
    controller._handle_combat()
    assert controller.state.phase == expected
    assert controller.state.node == 'J'


def test_stop_before_node_result_does_not_increment() -> None:
    controller = DecisiveController.__new__(DecisiveController)
    controller._ctx = SimpleNamespace(stop_event=threading.Event())
    controller._ctx.stop_event.set()
    controller._state = DecisiveState(stage=1, node='J', phase=DecisivePhase.NODE_RESULT)
    controller._tracking = None
    controller._handle_node_result()
    assert controller.state.node == 'J'
    assert controller._main_loop() == DecisiveResult.STOPPED


def test_finished_without_clear_is_not_success() -> None:
    controller = DecisiveController.__new__(DecisiveController)
    controller._ctx = SimpleNamespace(stop_event=threading.Event())
    controller._state = DecisiveState(phase=DecisivePhase.FINISHED)
    controller._tracking = None
    assert controller._main_loop() == DecisiveResult.ERROR


def test_enemy_uses_matched_frame_and_reuses_native_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    archive = SampleArchive(tmp_path)
    ctx = SimpleNamespace(ctrl=MagicMock(), ocr=None)
    engine = RecordingCombatEngine(ctx, archive)
    frame = CapturedFrame(np.zeros((54, 96, 3), dtype=np.uint8), 41, 12.5)
    engine._recognizer = SimpleNamespace(last_match=frame, capture_frame=MagicMock())
    evidence = EnemyObservation(
        raw_slots=('Airfield', 'BB', 'DD', 'BB', 'BC', 'AV'),
        ships=('机场', '战列', '驱逐', '战列', '战巡', '航战'),
        formation=2,
        formation_text='复纵阵',
        formation_confidence=0.97,
        detour=None,
        detour_score=None,
    )
    observe = MagicMock(return_value=evidence)
    monkeypatch.setattr('tools.decisive.collect.observe_enemy', observe)
    counts, formation, returned = engine._collect_spot_evidence()
    observe.assert_called_once()
    assert observe.call_args.args[0] is frame.image
    assert returned is evidence
    assert counts['Airfield'] == 1
    assert formation == '复纵阵'
    engine._recognizer.capture_frame.assert_not_called()
    ctx.ctrl.screenshot.assert_not_called()
    row = json.loads((tmp_path / 'observations.jsonl').read_text(encoding='utf-8'))
    assert row['frame_sequence'] == 41
    assert row['observation']['ships'][0] == '机场'


def _collection_controller() -> CollectionController:
    controller = CollectionController.__new__(CollectionController)
    controller._state = DecisiveState(stage=1, node='A')
    controller._ctx = SimpleNamespace(stop_event=threading.Event())
    controller._ctrl = MagicMock()
    controller._config = DecisiveConfig()
    controller._ocr = None
    controller._map = MagicMock()
    controller._battle_page = MagicMock()
    controller.archive = SimpleNamespace(context={}, record=MagicMock())
    controller.round_number = 1
    controller._tracking = None
    controller._known_start_stage = None
    controller._battle_encounter_id = None
    controller._labelled_completions = set()
    controller._sampled_encounters = set()
    controller._sampled_frames = set()
    controller._first_entry = None
    controller._allow_reset = False
    controller._inventory_refresh_required = True
    controller._set_label(None, 1, None)
    return controller


def test_stop_file_prevents_click_and_preserves_snapshot(tmp_path: Path) -> None:
    archive = SampleArchive(tmp_path)
    stop = FileStopEvent(tmp_path / 'STOP')
    real = MagicMock()
    frame = CapturedFrame(np.zeros((10, 10, 3), dtype=np.uint8), 3, 1.0)
    real.capture_frame.return_value = frame
    device = RecordingDevice(real, archive, stop)
    stop.path.touch()
    with pytest.raises(InterruptedError):
        device.click(0.1, 0.2)
    real.click.assert_not_called()
    assert device.capture_frame() is frame


def test_existing_archive_is_rejected_without_overwriting_samples(tmp_path: Path) -> None:
    archive = SampleArchive(tmp_path)
    archive.record('map', CapturedFrame(np.zeros((10, 10, 3), dtype=np.uint8), 1, 1.0))
    saved = {path.name: path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()}
    with pytest.raises(FileExistsError, match='采集目录'):
        SampleArchive(tmp_path)
    assert {path.name: path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()} == saved


@pytest.fixture
def collector_after_battle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> CollectionController:
    """由真实采集器和会话生成战后事件；只替换设备与页面识别边界。"""
    sequences = count(1)

    def capture() -> CapturedFrame:
        return CapturedFrame(_map_pixels(), next(sequences), time.monotonic())

    config = DecisiveConfig(chapter=6)
    ctx = SimpleNamespace(
        ctrl=SimpleNamespace(capture_frame=capture, screenshot=lambda: capture().image),
        ocr=None,
        config=UserConfig(decisive_battle=config),
        stop_event=threading.Event(),
    )
    archive = SampleArchive(tmp_path / 'collection')
    controller = CollectionController(ctx, config, archive)
    controller.state.stage = 1
    start_node = getattr(request, 'param', 'A')
    native = SimpleNamespace(recognize_map=MagicMock(side_effect=[start_node, 'B']))
    monkeypatch.setattr('autowsgr.ui.decisive.map_controller.get_api_dll', lambda: native)
    monkeypatch.setattr('autowsgr.ops.decisive.handlers.time.sleep', lambda _seconds: None)
    controller._known_start_stage = 1 if start_node == 'A' else None
    controller._set_label(start_node, 1, 'user_confirmed_start')
    controller._observe_map_ready(capture())
    controller._record('combat_start', snapshot=False)
    frame = capture()
    session = controller._tracking
    session.publish(
        FusionObservation(
            'phase',
            frame.captured_at,
            frame_id=frame.sequence,
            phase='RESULT',
            encounter_id=session.encounter_id,
        )
    )
    archive.record('result', frame)
    controller._record('combat_end', snapshot=False, result=ConditionFlag.OPERATION_SUCCESS.value)
    controller._battle_encounter_id = session.encounter_id
    controller._state.phase = DecisivePhase.NODE_RESULT
    return controller


@pytest.fixture
def recorded_map_transition(collector_after_battle: CollectionController) -> Path:
    controller = collector_after_battle
    controller._handle_node_result()
    assert controller.state.node == 'B'
    return controller.archive.output / 'observations.jsonl'


@pytest.mark.parametrize('legacy', [False, True])
def test_recorded_next_map_is_replayed_after_real_completion(
    recorded_map_transition: Path, tmp_path: Path, legacy: bool
) -> None:
    rows = [
        json.loads(line)
        for line in recorded_map_transition.read_text(encoding='utf-8').splitlines()
    ]
    if legacy:
        rows = [row for row in rows if row['kind'] != 'encounter_complete']
    else:
        kinds = [row['kind'] for row in rows]
        assert kinds.index('node_result_before') < kinds.index('encounter_complete')
        assert kinds.index('encounter_complete') < len(kinds) - 1 - kinds[::-1].index('map')
    source = tmp_path / 'snapshot.jsonl'
    source.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
    report = convert_collection(source, tmp_path / 'replay')
    stage = report['stages'][0]
    summary = json.loads(
        Path(stage['replay_log'])
        .with_suffix('')
        .with_suffix('.summary.json')
        .read_text(encoding='utf-8')
    )
    next_map = [row for row in summary['phases'] if row['phase'] == 'DECISIVE_MAP_READY'][-1]
    assert next_map['anomaly'] is None
    assert next_map['node_weights'] == {'B': 1.0}
    assert stage['labels']['top1_accuracy'] == 1.0
    assert report['completed_encounters'] == 1
    assert stage['duplicate_completions_ignored'] == 0
    assert stage['completion_sources'] == {
        'legacy_before_timestamp' if legacy else 'recorded_observation': 1
    }


@pytest.mark.parametrize('legacy', [False, True])
def test_recorded_completion_tail_requires_evidence(
    recorded_map_transition: Path, tmp_path: Path, legacy: bool
) -> None:
    rows = [
        json.loads(line)
        for line in recorded_map_transition.read_text(encoding='utf-8').splitlines()
    ]
    rows = [row for row in rows if row['kind'] != 'node_result_after']
    if legacy:
        rows = [row for row in rows if row['kind'] != 'encounter_complete']
    source = tmp_path / 'tail.jsonl'
    source.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
    report = convert_collection(source, tmp_path / 'replay')
    assert report['completed_encounters'] == (0 if legacy else 1)


@pytest.mark.parametrize('interruption', ['before', 'after', 'timeout'])
def test_recording_preserves_committed_completion_on_interruption(
    collector_after_battle: CollectionController, tmp_path: Path, interruption: str
) -> None:
    controller = collector_after_battle
    if interruption == 'before':
        controller._ctx.stop_event.set()
    elif interruption == 'after':
        capture = controller._ctrl.capture_frame
        reads = count(1)

        def capture_and_stop() -> CapturedFrame:
            frame = capture()
            if next(reads) == 2:
                controller._ctx.stop_event.set()
            return frame

        controller._ctrl.capture_frame = capture_and_stop
        controller._map.detect_decisive_phase = lambda _image: None
    else:
        controller._POST_COMBAT_TIMEOUT = 0.0
    if interruption == 'timeout':
        with pytest.raises(TimeoutError):
            controller._handle_node_result()
    else:
        controller._handle_node_result()
    report = convert_collection(
        controller.archive.output / 'observations.jsonl', tmp_path / 'replay'
    )
    assert report['completed_encounters'] == (0 if interruption == 'before' else 1)


@pytest.mark.parametrize('collector_after_battle', ['J'], indirect=True)
def test_recorded_terminal_completion_has_no_false_label_conflict(
    collector_after_battle: CollectionController,
) -> None:
    controller = collector_after_battle
    controller._map.is_stage_clear = lambda _image: True
    controller._handle_node_result()
    assert controller.state.phase == DecisivePhase.STAGE_CLEAR
    rows = [
        json.loads(line)
        for line in (controller.archive.output / 'observations.jsonl')
        .read_text(encoding='utf-8')
        .splitlines()
    ]
    assert sum(row['kind'] == 'encounter_complete' for row in rows) == 1
    assert not any(row['kind'] == 'label_conflict' for row in rows)
    assert rows[-1]['label_node'] == 'J'


def test_current_map_start_does_not_navigate_or_reset() -> None:
    controller = _collection_controller()
    controller._record = MagicMock()
    controller._map.detect_decisive_phase.return_value = DecisivePhase.PREPARE_COMBAT
    controller._main_loop = MagicMock(return_value=DecisiveResult.CHAPTER_CLEAR)
    controller._prepare_entry_state = MagicMock()
    assert controller.run_current_map(1, 'A') == DecisiveResult.CHAPTER_CLEAR
    assert controller.state.stage == 1
    assert controller.state.node == 'A'
    assert controller.label_source == 'user_confirmed_start'
    assert controller._label_node == 'A'
    assert controller._known_start_stage == 1
    controller._prepare_entry_state.assert_not_called()


@pytest.mark.parametrize('node', [None, 'B'])
def test_current_map_only_confirmed_a_sets_known_start(node: str | None) -> None:
    controller = _collection_controller()
    controller._record = MagicMock()
    controller._main_loop = MagicMock(return_value=DecisiveResult.STOPPED)
    controller._map.detect_decisive_phase.return_value = DecisivePhase.PREPARE_COMBAT
    controller.run_current_map(1, node)
    assert controller._known_start_stage is None
    assert controller._label_node == node


def test_first_round_navigates_from_home_without_claiming_map_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _collection_controller()
    controller._record = MagicMock()
    controller._map.detect_decisive_phase.return_value = None
    controller._main_loop = MagicMock(return_value=DecisiveResult.STOPPED)
    controller._prepare_entry_state = MagicMock()
    monkeypatch.setattr(
        'tools.decisive.collect.BattlePreparationPage.is_current_page', lambda _screen: False
    )
    controller.run_current_map(1, 'A')
    controller._prepare_entry_state.assert_called_once()
    assert controller.state.phase == DecisivePhase.ENTER_MAP
    assert controller.label_source is None
    assert controller._first_entry == (1, 'A')
    assert controller._known_start_stage is None


def test_recovery_from_preparation_returns_to_existing_map_without_reset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _collection_controller()
    controller._record = MagicMock()
    controller._main_loop = MagicMock(return_value=DecisiveResult.STOPPED)
    controller._prepare_entry_state = MagicMock()
    controller._map.detect_decisive_phase.side_effect = [None, DecisivePhase.PREPARE_COMBAT]
    monkeypatch.setattr(
        'tools.decisive.collect.BattlePreparationPage.is_current_page', lambda _screen: True
    )
    page = MagicMock()
    monkeypatch.setattr(
        'tools.decisive.collect.DecisiveBattlePreparationPage', MagicMock(return_value=page)
    )
    controller.run_current_map(1, 'B')
    page.go_back.assert_called_once()
    controller._prepare_entry_state.assert_not_called()
    controller._battle_page.reset_chapter.assert_not_called()
    assert (controller.state.stage, controller.state.node) == (1, 'B')
    assert controller._label_node == 'B'
    assert controller._known_start_stage is None


def test_preparation_recovery_failure_does_not_fall_back_to_global_navigation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _collection_controller()
    controller._record = MagicMock()
    controller._prepare_entry_state = MagicMock()
    controller._map.detect_decisive_phase.return_value = None
    monkeypatch.setattr(
        'tools.decisive.collect.BattlePreparationPage.is_current_page', lambda _screen: True
    )
    page = MagicMock()
    monkeypatch.setattr(
        'tools.decisive.collect.DecisiveBattlePreparationPage', MagicMock(return_value=page)
    )
    with pytest.raises(RuntimeError, match='保留现场停止'):
        controller.run_current_map(1, 'B')
    page.go_back.assert_called_once()
    controller._prepare_entry_state.assert_not_called()
    controller._battle_page.reset_chapter.assert_not_called()


def test_stop_before_preparation_recovery_prevents_back_click(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _collection_controller()
    controller._record = MagicMock()
    controller._map.detect_decisive_phase.return_value = None

    def matched_and_stopped(_screen: object) -> bool:
        controller._ctx.stop_event.set()
        return True

    monkeypatch.setattr(
        'tools.decisive.collect.BattlePreparationPage.is_current_page', matched_and_stopped
    )
    page = MagicMock()
    monkeypatch.setattr(
        'tools.decisive.collect.DecisiveBattlePreparationPage', MagicMock(return_value=page)
    )
    with pytest.raises(InterruptedError):
        controller.run_current_map(1, 'B')
    page.go_back.assert_not_called()


def test_first_round_refuses_reset_before_any_click() -> None:
    controller = _collection_controller()
    controller._record = MagicMock()
    controller._battle_page.detect_entry_status.return_value = DecisiveEntryStatus.REFRESH
    with pytest.raises(RuntimeError, match='首轮入口要求重置'):
        controller._handle_enter_map()
    controller._battle_page.reset_chapter.assert_not_called()
    controller._battle_page.click_enter_map.assert_not_called()


def test_entry_stage_mismatch_does_not_apply_user_label() -> None:
    controller = _collection_controller()
    controller._record = MagicMock()
    controller._first_entry = (1, 'A')
    controller._battle_page.detect_entry_status.return_value = DecisiveEntryStatus.CHALLENGING
    controller._battle_page.detect_stage.return_value = 1
    with pytest.raises(RuntimeError, match='停止复核标签'):
        controller._handle_enter_map()
    assert controller._label_node is None
    assert controller._known_start_stage is None
    controller._battle_page.click_enter_map.assert_not_called()


def test_prediction_changes_never_overwrite_independent_label() -> None:
    controller = _collection_controller()
    controller._set_label('A', 1, 'user_confirmed_start')
    controller._state.node = 'J'
    controller._record('map', snapshot=False)
    assert controller.archive.context['predicted_node'] == 'J'
    assert controller.archive.context['label_node'] == 'A'


def test_controller_archive_uses_live_session_prediction() -> None:
    controller = _collection_controller()
    controller._set_label('A', 1, 'user_confirmed_start')
    controller._state.node = 'J'
    controller._tracking = SimpleNamespace(current_node='B', encounter_id='first', log_path=None)
    controller._record('combat_end', snapshot=False)
    assert controller.archive.context['predicted_node'] == 'B'
    assert controller.archive.context['label_node'] == 'A'


@pytest.mark.parametrize('known_start', [False, True])
def test_collector_does_not_duplicate_production_fleet_scan(
    known_start: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    controller = _collection_controller()
    controller._record = MagicMock()
    controller._inventory_refresh_required = True
    controller._has_chosen_fleet = True
    controller._tracking = DecisiveTrackingSession(6, 1, known_start=known_start)
    controller._ensure_tracking = MagicMock(return_value=controller._tracking)
    controller._observe_map_ready = MagicMock()
    controller._sync_ship_states = MagicMock()
    controller._map.detect_decisive_phase.return_value = DecisivePhase.PREPARE_COMBAT
    controller._map.is_skill_used.return_value = True
    controller._map.check_fleet.return_value = (
        ['芝加哥', None, None, None, None, None],
        {},
        {'芝加哥'},
    )
    controller._logic = DecisiveLogic(controller._config, controller._state)
    monkeypatch.setattr('autowsgr.ops.decisive.handlers.time.sleep', lambda _seconds: None)
    controller._handle_prepare_combat()
    controller._map.check_fleet.assert_called_once()
    assert not controller._inventory_refresh_required


def test_reset_then_next_stage_preserves_confirmed_a_and_new_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _collection_controller()
    controller.round_number = 2
    controller._ctx.config = SimpleNamespace(
        log=SimpleNamespace(dir=None, node_fusion_replay=False)
    )
    controller._record = MagicMock()
    controller._allow_reset = True
    controller._inventory_refresh_required = True
    controller._battle_page.detect_entry_status.side_effect = [
        DecisiveEntryStatus.REFRESH,
        DecisiveEntryStatus.REFRESH,
        DecisiveEntryStatus.REFRESHED,
    ]
    controller._battle_page.reset_chapter.return_value = True
    controller._battle_page.detect_stage.return_value = 0
    controller._handle_enter_map()
    assert controller._known_start_stage == 1
    assert controller._label_node == 'A'
    assert controller.label_source == 'confirmed_chapter_reset'
    assert controller._inventory_refresh_required
    first = controller._ensure_tracking()
    assert first.tracker.initial == {'A': 1.0}
    controller._sampled_encounters.add(first.encounter_id)
    controller._map.confirm_stage_clear.return_value = []
    monkeypatch.setattr(
        'tools.decisive.collect.ImageChecker.find_any', lambda *_args, **_kwargs: object()
    )
    controller._handle_stage_clear()
    assert controller._tracking is None
    assert first._statistics_finished
    assert controller._label_stage == 2
    assert controller._inventory_refresh_required
    controller._battle_page.detect_entry_status.side_effect = None
    controller._battle_page.detect_entry_status.return_value = DecisiveEntryStatus.CHALLENGING
    controller._battle_page.detect_stage.return_value = 1
    controller._handle_enter_map()
    assert controller.label_source == 'confirmed_stage_clear'
    assert controller._label_node == 'A'
    second = controller._ensure_tracking()
    assert second.tracker.initial == {'A': 1.0}
    assert second.encounter_id != first.encounter_id
    assert second.encounter_id not in controller._sampled_encounters


def test_phase_archive_overrides_stale_controller_prediction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = SampleArchive(tmp_path)
    archive.context.update(predicted_node='J', encounter_id='old')
    engine = RecordingCombatEngine(SimpleNamespace(ctrl=MagicMock(), ocr=None), archive)
    engine._node = 'B'
    engine._tracking = SimpleNamespace(encounter_id='active')
    engine._recognizer = SimpleNamespace(last_match=None)
    monkeypatch.setattr(
        CombatEngine, '_make_decision', lambda _self, _phase: ConditionFlag.FIGHT_CONTINUE
    )
    engine._make_decision(CombatPhase.RESULT)
    row = json.loads((tmp_path / 'observations.jsonl').read_text(encoding='utf-8'))
    assert row['predicted_node'] == 'B'
    assert row['encounter_id'] == 'active'


@pytest.mark.parametrize('label', [None, 'A'])
def test_labels_advance_once_only_after_session_commits(label: str | None) -> None:
    controller = _collection_controller()
    controller._set_label(label, 1, 'user_confirmed_start')
    controller._tracking = DecisiveTrackingSession(6, 1, known_start=True)
    controller._battle_encounter_id = controller._tracking.encounter_id
    controller._state.node = 'J'
    controller._sync_completed_label()
    assert controller._label_node == label
    controller._tracking.complete_encounter(controller._battle_encounter_id)
    controller._sync_completed_label()
    controller._sync_completed_label()
    assert controller._label_node == ('B' if label else None)
    assert controller._state.node == 'J'


def test_stop_preserves_already_committed_completion_label() -> None:
    controller = _collection_controller()
    controller._set_label('A', 1, 'user_confirmed_start')
    controller._tracking = DecisiveTrackingSession(6, 1, known_start=True)
    controller._battle_encounter_id = controller._tracking.encounter_id
    controller._tracking.complete_encounter(controller._battle_encounter_id)
    controller._ctx.stop_event.set()
    controller._sync_completed_label()
    assert controller._label_node == 'B'
    assert controller._labelled_completions == {controller._battle_encounter_id}


@pytest.mark.parametrize('disabled', [False, True])
def test_completion_archive_uses_accepted_event_before_later_ignored_attempt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, disabled: bool
) -> None:
    controller = _collection_controller()
    controller.archive = SampleArchive(tmp_path)
    controller._set_label('A', 1, 'user_confirmed_start')
    session = DecisiveTrackingSession(6, 1, known_start=True)
    controller._tracking = session
    controller._battle_encounter_id = session.encounter_id
    session.phase(
        CombatPhase.RESULT,
        CapturedFrame(np.zeros((2, 2, 3), dtype=np.uint8), 1, 1.0),
        'A',
    )
    monkeypatch.setattr(time, 'monotonic', lambda: 2.0)
    session.complete_encounter(controller._battle_encounter_id)
    completion = session.tracker.observations[-1]
    session.publish(replace(completion, timestamp=3.0))
    if disabled:
        session.fail('synthetic failure after accepted completion')
    controller._ctx.stop_event.set()

    controller._sync_completed_label()
    controller._sync_completed_label()

    records = [
        json.loads(line)
        for line in (tmp_path / 'observations.jsonl').read_text(encoding='utf-8').splitlines()
    ]
    assert len(records) == 1
    assert records[0]['observation'] == asdict(completion)
    assert controller._label_node == 'B'


def test_recording_engine_publishes_same_enemy_object_before_decision(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    archive = SampleArchive(tmp_path)
    engine = RecordingCombatEngine(SimpleNamespace(ctrl=MagicMock(), ocr=None), archive)
    engine._tracking = DecisiveTrackingSession(6, 1, known_start=True)
    frame = CapturedFrame(np.zeros((54, 96, 3), dtype=np.uint8), 41, 12.5)
    engine._recognizer = SimpleNamespace(last_match=frame, capture_frame=MagicMock())
    evidence = EnemyObservation(
        raw_slots=('CL', 'CL', 'NO', 'NO', 'NO', 'NO'),
        ships=('轻巡', '轻巡', None, None, None, None),
        formation=None,
        formation_text='',
        formation_confidence=None,
        detour=None,
        detour_score=None,
    )
    observe = MagicMock(return_value=evidence)
    monkeypatch.setattr('tools.decisive.collect.observe_enemy', observe)
    engine._collect_spot_evidence()
    observe.assert_called_once()
    assert engine._tracking.tracker.observations[-1].enemies is evidence
    assert engine._node == 'A'
    engine._recognizer.capture_frame.assert_not_called()
    row = json.loads((tmp_path / 'observations.jsonl').read_text(encoding='utf-8'))
    assert row['encounter_id'] == engine._tracking.encounter_id
    assert row['fusion_event_id'] == 0


def test_collector_injects_owned_tracking_session(monkeypatch: pytest.MonkeyPatch) -> None:
    controller = _collection_controller()
    controller._record = MagicMock()
    controller._tracking = DecisiveTrackingSession(6, 1, known_start=True)
    engine = MagicMock()
    engine.saw_enemy = False
    engine.fight.return_value = CombatResult(flag=ConditionFlag.OPERATION_SUCCESS)
    monkeypatch.setattr(
        'tools.decisive.collect.RecordingCombatEngine', MagicMock(return_value=engine)
    )
    plan = CombatPlan(mode=CombatMode.DECISIVE)
    controller._run_combat(plan)
    assert engine.fight.call_args.kwargs['tracking_session'] is controller._tracking
    assert controller._record.call_args.kwargs['saw_enemy'] is False


@pytest.mark.parametrize('known_start', [False, True])
@pytest.mark.parametrize('sequence', [51, None])
def test_map_sampling_uses_supplied_frame_once_per_encounter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, known_start: bool, sequence: int | None
) -> None:
    controller = _collection_controller()
    controller.archive = SampleArchive(tmp_path)
    controller._tracking = DecisiveTrackingSession(6, 1, known_start=known_start)
    controller._set_label('A', 1, 'user_confirmed_start')
    controller._ctx.ctrl = controller._ctrl
    controller._ctx.ocr = None
    controller._map = DecisiveMapController(controller._ctx, controller._config)
    native = MagicMock()
    native.recognize_map.return_value = 'J'
    monkeypatch.setattr('autowsgr.ui.decisive.map_controller.get_api_dll', lambda: native)
    frame = CapturedFrame(_map_pixels(), sequence, 20.0)
    controller._observe_map_ready(frame)
    # 即使预测被外部暂时修订，也仍是同一遭遇，不额外识别或重贴标签。
    controller._state.node = 'D'
    controller._observe_map_ready(frame)
    native.recognize_map.assert_called_once()
    controller._ctrl.capture_frame.assert_not_called()
    controller._ctrl.screenshot.assert_not_called()
    rows = [
        json.loads(line)
        for line in (tmp_path / 'observations.jsonl').read_text(encoding='utf-8').splitlines()
    ]
    (sample,) = [row for row in rows if row['kind'] == 'map']
    assert sample['frame_sequence'] == sequence
    assert sample['label_node'] == 'A'
    assert sample['raw_node'] == 'J'
    assert sample['used_for_tracking'] == (not known_start)
    assert sample['crop_bounds'] == [461, 0, 514, 720]
    crop = cv2.cvtColor(cv2.imread(str(tmp_path / sample['crop'])), cv2.COLOR_BGR2RGB)
    np.testing.assert_array_equal(crop, native.recognize_map.call_args.args[0])
    assert controller._tracking.tracker.observations[0].node_label == (None if known_start else 'J')


@pytest.mark.parametrize('overlay', [None, 'FLEET_ACQUISITION', 'CONFIRM_EXIT', 'ADVANCE_CHOICE'])
def test_collection_does_not_recognize_non_map_or_overlay_frames(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, overlay: str | None
) -> None:
    controller = _collection_controller()
    controller.archive = SampleArchive(tmp_path)
    controller._ctx.ctrl = controller._ctrl
    controller._ctx.ocr = None
    controller._map = DecisiveMapController(controller._ctx, controller._config)
    pixels = _map_pixels() if overlay else np.zeros((720, 1280, 3), dtype=np.uint8)
    if overlay:
        patch = getattr(Templates.Decisive, overlay).image
        height, width = patch.shape[:2]
        pixels[50 : 50 + height, 700 : 700 + width] = patch
    native = MagicMock()
    monkeypatch.setattr('autowsgr.ui.decisive.map_controller.get_api_dll', lambda: native)
    assert (
        controller._sample_map(CapturedFrame(pixels, 1, 1.0), 'one', used_for_tracking=True) is None
    )
    native.recognize_map.assert_not_called()
    assert not controller._sampled_frames
    assert not controller._sampled_encounters


def test_collection_archives_native_error_before_stopping(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    controller = _collection_controller()
    controller.archive = SampleArchive(tmp_path)
    controller._ctx.ctrl = controller._ctrl
    controller._ctx.ocr = None
    controller._map = DecisiveMapController(controller._ctx, controller._config)
    native = MagicMock()
    native.recognize_map.side_effect = RuntimeError('native unavailable')
    monkeypatch.setattr('autowsgr.ui.decisive.map_controller.get_api_dll', lambda: native)
    frame = CapturedFrame(_map_pixels(), 51, 20.0)
    with pytest.raises(RuntimeError, match='native unavailable'):
        controller._sample_map(frame, 'one', used_for_tracking=True)
    rows = [
        json.loads(line)
        for line in (tmp_path / 'observations.jsonl').read_text(encoding='utf-8').splitlines()
    ]
    assert rows[-1]['kind'] == 'map_error'
    assert rows[-1]['failure'] == 'native_error'
    assert 'native unavailable' in rows[-1]['error']
    assert rows[-1]['frame_sequence'] == 51
    assert rows[-1]['timings']['map_native_seconds'] >= 0
    native.recognize_map.assert_called_once()
    assert not controller._sampled_frames


def test_collection_samples_again_only_for_requested_new_frame_or_new_encounter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    controller = _collection_controller()
    controller.archive = SampleArchive(tmp_path)
    controller._ctx.ctrl = controller._ctrl
    controller._ctx.ocr = None
    controller._map = DecisiveMapController(controller._ctx, controller._config)
    controller._tracking = DecisiveTrackingSession(6, 1, known_start=True)
    session = controller._tracking
    native = MagicMock()
    native.recognize_map.side_effect = ['A', 'A', 'B']
    monkeypatch.setattr('autowsgr.ui.decisive.map_controller.get_api_dll', lambda: native)
    first = CapturedFrame(_map_pixels(), None, 20.0)
    second = CapturedFrame(_map_pixels(), None, 20.1)
    controller._observe_map_ready(first)
    controller._observe_map_ready(second)
    assert native.recognize_map.call_count == 1
    session.request_node_sample('test explicit request')
    controller._observe_map_ready(first)
    assert native.recognize_map.call_count == 1
    controller._observe_map_ready(second)
    assert native.recognize_map.call_count == 2
    old_encounter = session.encounter_id
    session.complete_encounter(old_encounter)
    controller._observe_map_ready(CapturedFrame(_map_pixels(), None, time.monotonic()))
    assert native.recognize_map.call_count == 3
    rows = [
        json.loads(line)
        for line in (tmp_path / 'observations.jsonl').read_text(encoding='utf-8').splitlines()
    ]
    assert controller.archive.counter == len(rows) == 8
    assert sum(row['kind'] == 'map' for row in rows) == 3
    assert controller._sampled_encounters == {old_encounter, session.encounter_id}


def test_shared_observation_leaves_stage_membership_validation_to_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    controller = _collection_controller()
    controller.archive = SampleArchive(tmp_path)
    controller._ctx.ctrl = controller._ctrl
    controller._ctx.ocr = None
    controller._map = DecisiveMapController(controller._ctx, controller._config)
    controller._tracking = DecisiveTrackingSession(6, 1)
    native = MagicMock()
    native.recognize_map.return_value = 'Z-extra'
    monkeypatch.setattr('autowsgr.ui.decisive.map_controller.get_api_dll', lambda: native)
    controller._observe_map_ready(CapturedFrame(_map_pixels(), 51, 20.0))
    observation = controller._tracking.tracker.observations[-1]
    assert observation.node_label is None
    rows = [
        json.loads(line)
        for line in (tmp_path / 'observations.jsonl').read_text(encoding='utf-8').splitlines()
    ]
    sample = next(row for row in rows if row['kind'] == 'map')
    assert sample['raw_node'] == 'Z-extra'
    assert sample['failure'] is None
    assert controller._map.recognize_node(CapturedFrame(_map_pixels(), 52, 20.1)) == 'Z'


def test_unknown_start_does_not_invent_confirmed_a() -> None:
    args = parse_args(['--output', 'samples'])
    assert args.start_node is None


@pytest.mark.parametrize(
    'extra', [[], ['--round-offset', '0'], ['--round-offset', '1', '--start-node', 'A']]
)
def test_next_round_entry_rejects_missing_progress_or_conflicting_map_label(
    extra: list[str],
) -> None:
    with pytest.raises(SystemExit):
        parse_args(['--output', 'samples', '--start-at-entry', *extra])


def test_next_round_entry_parses_only_remaining_rounds() -> None:
    args = parse_args(
        ['--output', 'samples', '--start-at-entry', '--round-offset', '1', '--rounds', '2']
    )
    assert args.start_at_entry
    assert args.round_offset + args.rounds == 3


@pytest.mark.parametrize('conflicting', [['--start-at-entry'], ['--start-node', 'J']])
def test_reward_resume_is_exclusive_with_map_or_new_round_entry(conflicting: list[str]) -> None:
    with pytest.raises(SystemExit):
        parse_args(
            ['--output', 'samples', '--resume-stage-clear', '--round-offset', '1', *conflicting]
        )


def test_reward_resume_does_not_initialize_or_replay_completed_battle() -> None:
    controller = _collection_controller()
    controller._record = MagicMock()
    controller._handle_stage_clear = MagicMock()
    controller._main_loop = MagicMock(return_value=DecisiveResult.CHAPTER_CLEAR)
    controller._ensure_tracking = MagicMock()
    controller._prepare_entry_state = MagicMock()
    controller._handle_combat = MagicMock()
    assert controller.run_stage_clear(1) == DecisiveResult.CHAPTER_CLEAR
    controller._handle_stage_clear.assert_called_once_with(resume_rewards=True)
    controller._ensure_tracking.assert_not_called()
    controller._handle_combat.assert_not_called()
    controller._prepare_entry_state.assert_not_called()
    controller._battle_page.reset_chapter.assert_not_called()
    assert controller._tracking is None
    assert controller._state.stage == 1
    assert controller._state.node == 'J'
    assert controller._state.phase == DecisivePhase.STAGE_CLEAR


def test_reward_resume_keeps_production_clear_contract_and_next_a(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _collection_controller()
    controller._record = MagicMock()
    controller._ctx.config = SimpleNamespace(
        log=SimpleNamespace(dir=None, node_fusion_replay=False)
    )
    controller._map.confirm_stage_clear.return_value = []
    controller._main_loop = MagicMock(return_value=DecisiveResult.STOPPED)
    confirmation = MagicMock(return_value=object())
    monkeypatch.setattr('tools.decisive.collect.ImageChecker.find_any', confirmation)
    controller.run_stage_clear(1)
    controller._map.confirm_stage_clear.assert_called_once_with(resume_rewards=True)
    # 恢复奖励时不等待初始通关确认按钮，唯一模板检查是结算后入口。
    confirmation.assert_called_once()
    assert controller._known_start_stage == 2
    assert controller._label_stage == 2
    assert controller._label_node == 'A'
    assert controller._tracking is None
    controller._state.stage = 2
    session = controller._ensure_tracking()
    assert session.tracker.initial == {'A': 1.0}


def test_stop_before_reward_resume_never_calls_settlement() -> None:
    controller = _collection_controller()
    controller._ctx.stop_event.set()
    controller._handle_stage_clear = MagicMock()
    assert controller.run_stage_clear(1) == DecisiveResult.STOPPED
    controller._handle_stage_clear.assert_not_called()


def test_reward_resume_dispatches_fifty_remaining_battles_without_extra_round(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ctx = SimpleNamespace(
        ctrl=MagicMock(), config=UserConfig(decisive_battle=DecisiveConfig(chapter=6))
    )
    controller = MagicMock()
    controller.run_stage_clear.return_value = DecisiveResult.CHAPTER_CLEAR
    controller.run.return_value = DecisiveResult.CHAPTER_CLEAR
    monkeypatch.setattr('tools.decisive.collect.launch', MagicMock(return_value=ctx))
    monkeypatch.setattr(
        'tools.decisive.collect.CollectionController', MagicMock(return_value=controller)
    )
    monkeypatch.setattr(
        'tools.decisive.collect.subprocess.check_output', lambda *_args, **_kwargs: 'fixed-commit'
    )
    assert (
        main(
            [
                '--output',
                str(tmp_path),
                '--round-offset',
                '1',
                '--rounds',
                '2',
                '--start-stage',
                '1',
                '--resume-stage-clear',
            ]
        )
        == 0
    )
    controller.run_stage_clear.assert_called_once_with(1)
    controller.run.assert_called_once()
    controller.run_current_map.assert_not_called()
    assert controller.round_number == 3


@pytest.mark.parametrize('from_entry', [False, True])
def test_first_round_dispatch_respects_explicit_entry_resume(
    from_entry: bool, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = UserConfig(decisive_battle=DecisiveConfig(chapter=6))
    ctx = SimpleNamespace(ctrl=MagicMock(), config=config)
    controller = MagicMock()
    controller.run.return_value = DecisiveResult.CHAPTER_CLEAR
    controller.run_current_map.return_value = DecisiveResult.CHAPTER_CLEAR
    monkeypatch.setattr('tools.decisive.collect.launch', MagicMock(return_value=ctx))
    monkeypatch.setattr(
        'tools.decisive.collect.CollectionController', MagicMock(return_value=controller)
    )
    monkeypatch.setattr(
        'tools.decisive.collect.subprocess.check_output', lambda *_args, **_kwargs: 'fixed-commit'
    )
    args = ['--output', str(tmp_path), '--rounds', '2']
    if from_entry:
        args += ['--round-offset', '1', '--start-at-entry']
    assert main(args) == 0
    assert controller.run.call_count == (2 if from_entry else 1)
    assert controller.run_current_map.call_count == (0 if from_entry else 1)
    assert controller.round_number == (3 if from_entry else 2)
    assert config.log.node_fusion_replay is False
    assert ctx.config.log.node_fusion_replay is True
