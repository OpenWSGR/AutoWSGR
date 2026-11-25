"""决战恢复、确认起点及停止请求必须先于出征等有副作用的操作。"""

from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import cv2
import numpy as np
import pytest

from autowsgr.combat.node_fusion.map import TrackingMap
from autowsgr.combat.node_fusion.model import FusionTracker
from autowsgr.context import GameContext
from autowsgr.emulator.frame import CapturedFrame
from autowsgr.image_resources import Templates
from autowsgr.infra import DecisiveConfig, EmulatorConfig, UserConfig
from autowsgr.ops.decisive import handlers as handlers_module
from autowsgr.ops.decisive.config import MapData
from autowsgr.ops.decisive.controller import DecisiveController, DecisiveResult
from autowsgr.ops.decisive.logic import DecisiveLogic
from autowsgr.ops.decisive.repair import DecisiveRepairCoordinator
from autowsgr.ops.decisive.state import DecisiveState
from autowsgr.ops.decisive.tracking import DecisiveTrackingSession
from autowsgr.types import DecisiveEntryStatus, DecisivePhase, OSType, ShipDamageState
from autowsgr.ui.battle.fleet_change._detect import FleetSnapshot
from autowsgr.ui.decisive.battle_page import (
    CLICK_RESET_CHAPTER,
    DecisiveBattlePage,
    ResetConfirmationTimeoutError,
)
from autowsgr.vision import ImageChecker


def _chapter_overview(visible_nodes: int, *, chapter: int = 6) -> np.ndarray:
    """合成入口像素契约：亮起的节点包含当前小关，不代表已通过数量。"""
    image = np.full((720, 1280, 3), 40, dtype=np.uint8)
    template = Templates.Decisive.ENTRY_CHALLENGING
    patch = cv2.resize(
        template.image,
        (round(template.width * 1280 / 960), round(template.height * 720 / 540)),
    )
    height, width = patch.shape[:2]
    image[645 : 645 + height, 580 : 580 + width] = patch
    points = {
        1: ((0.4115, 0.4019), (0.6604, 0.4630), (0.8396, 0.7093)),
        6: ((0.606, 0.375), (0.532, 0.703), (0.862, 0.644)),
    }[chapter]
    for index, (x, y) in enumerate(points):
        px, py = int(x * 1280), int(y * 720)
        # 颜色取自首环已亮、0/30 的真实总览；这里只验证识别与消费契约。
        image[py - 2 : py + 3, px - 2 : px + 3] = (
            (254, 246, 251) if index < visible_nodes else (0, 81, 189)
        )
    assert DecisiveBattlePage.is_current_page(image).matched
    return image


@pytest.fixture
def controller(monkeypatch: pytest.MonkeyPatch) -> DecisiveController:
    metadata = TrackingMap.from_dict(
        {'A': {'next': ['B']}, 'B': {'next': []}},
    )
    monkeypatch.setattr(MapData, 'tracking_map', lambda *_: metadata)
    monkeypatch.setattr(handlers_module.time, 'sleep', lambda _: None)
    fleet = ['U1206', 'U2540', 'U1405', 'U47', 'U96', 'M296']
    ctrl = DecisiveController.__new__(DecisiveController)
    ctrl._ctrl = MagicMock()
    ctrl._ocr = MagicMock()
    ctrl._config = DecisiveConfig(chapter=6, level1=fleet, flagship_priority=[], useful_skill=False)
    ctrl._state = DecisiveState(chapter=6, stage=1, phase=DecisivePhase.PREPARE_COMBAT)
    ctrl._settings = UserConfig(
        emulator=EmulatorConfig(serial='local', path='/tmp/emulator'), os_type=OSType.linux
    )
    ctrl._ctx = GameContext(ctrl=ctrl._ctrl, ocr=ctrl._ocr, config=ctrl._settings)
    ctrl._repairs = DecisiveRepairCoordinator(ctrl._ctx, ctrl._config, user_config=ctrl._settings)
    ctrl._logic = DecisiveLogic(ctrl._config, ctrl._state, ctx=ctrl._ctx)
    ctrl._map = MagicMock()
    ctrl._map.try_leave_interrupted_sortie.return_value = False
    frame = CapturedFrame(np.zeros((2, 2, 3), dtype=np.uint8), 1, 1.0)
    ctrl._ctrl.screenshot.return_value = _chapter_overview(1)
    ctrl._map.wait_for_stable_map_frame.return_value = frame
    ctrl._map.detect_decisive_phase.return_value = DecisivePhase.PREPARE_COMBAT
    ctrl._map.recognize_node.return_value = None
    ctrl._map.is_skill_used.return_value = True
    ctrl._map.check_fleet.return_value = (
        fleet,
        dict.fromkeys(range(6), ShipDamageState.NORMAL),
        set(fleet),
    )
    ctrl._battle_page = MagicMock()
    ctrl._battle_page.detect_entry_status.return_value = DecisiveEntryStatus.CHALLENGING
    ctrl._battle_page.detect_stage.side_effect = DecisiveBattlePage.recognize_stage
    ctrl._tracking = DecisiveTrackingSession(6, 1)
    ctrl._known_start_stage = None
    ctrl._battle_encounter_id = None
    ctrl._inventory_refresh_required = True
    ctrl._has_chosen_fleet = True
    page = MagicMock()
    page.change_fleet.return_value = True
    page.detect_fleet_snapshot.return_value = FleetSnapshot(fleet[:], [True] * 6)
    page.detect_ship_damage.return_value = dict.fromkeys(range(6), ShipDamageState.NORMAL)
    page.read_repair_snapshot.return_value = (fleet[:], page.detect_ship_damage.return_value)
    monkeypatch.setattr(
        handlers_module, 'DecisiveBattlePreparationPage', MagicMock(return_value=page)
    )
    return ctrl


@pytest.mark.parametrize('letter', [None, 'A'])
def test_unknown_and_soft_a_recovery_scan_real_fleet(
    controller: DecisiveController, letter: str | None
) -> None:
    controller._map.recognize_node.return_value = letter
    controller._handle_prepare_combat()

    controller._map.check_fleet.assert_called_once()
    assert controller._tracking.tracker.initial is None
    assert controller.state.node == ('U' if letter is None else 'A')
    assert controller.state.ships == set(controller._config.level1)
    assert controller.state.fleet[1:] == controller._config.level1
    assert controller.state.phase == DecisivePhase.IN_COMBAT


def test_chapter_one_unknown_entry_preserves_recovery_scan(controller: DecisiveController) -> None:
    controller._config = controller._config.model_copy(update={'chapter': 1})
    controller._state.chapter = 1
    controller._ctrl.screenshot.return_value = _chapter_overview(1, chapter=1)
    controller._tracking = None
    controller._handle_enter_map()
    controller._handle_prepare_combat()

    controller._map.check_fleet.assert_called_once()
    assert controller._tracking.tracker.initial is None


def test_stop_during_repair_never_starts_another_battle(controller: DecisiveController) -> None:
    page = handlers_module.DecisiveBattlePreparationPage.return_value
    _, damage = page.read_repair_snapshot.return_value
    damage[5] = ShipDamageState.SEVERE
    page.repair_slots.side_effect = lambda *_args, **_kwargs: controller._ctx.stop_event.set()

    controller._handle_prepare_combat()

    page.repair_slots.assert_called_once()
    page.start_battle.assert_not_called()
    assert controller.state.phase == DecisivePhase.FINISHED
    assert not any(
        obs.action == 'encounter_complete' for obs in controller._tracking.tracker.observations
    )


@pytest.mark.parametrize(
    ('following_status', 'visible_nodes', 'valid'),
    [
        (DecisiveEntryStatus.REFRESHED, 1, True),
        (DecisiveEntryStatus.REFRESHED, 0, False),
        (DecisiveEntryStatus.REFRESHED, 2, False),
        (DecisiveEntryStatus.REFRESH, 1, False),
    ],
)
def test_reset_needs_verified_first_stage_before_certain_a(
    controller: DecisiveController,
    following_status: DecisiveEntryStatus,
    visible_nodes: int,
    valid: bool,
) -> None:
    controller._inventory_refresh_required = False
    controller._battle_page.detect_entry_status.side_effect = [
        DecisiveEntryStatus.REFRESH,
        following_status,
    ]
    controller._ctrl.screenshot.return_value = _chapter_overview(visible_nodes)
    controller._battle_page.reset_chapter.return_value = True
    if not valid:
        with pytest.raises(RuntimeError, match='拒绝假定 A 起点'):
            controller._handle_enter_map()
        controller._battle_page.click_enter_map.assert_not_called()
        assert controller._known_start_stage is None
        return

    controller._handle_enter_map()

    controller._battle_page.click_enter_map.assert_called_once()
    assert controller._known_start_stage == 1
    assert controller._inventory_refresh_required
    session = controller._ensure_tracking()
    assert session.tracker.initial == {'A': 1.0}
    assert session.current_node == 'A'
    assert not session.sample_node_label


@pytest.mark.parametrize('stage', [1, 2, 3])
def test_entry_preserves_current_stage_from_visible_nodes(
    controller: DecisiveController, stage: int
) -> None:
    screen = _chapter_overview(stage)
    assert DecisiveBattlePage.recognize_stage(screen, 6) == stage
    controller._ctrl.screenshot.return_value = screen

    controller._handle_enter_map()

    assert controller.state.stage == stage
    assert controller.state.phase == DecisivePhase.WAITING_FOR_MAP
    assert controller._ensure_tracking().stage == stage
    controller._battle_page.click_enter_map.assert_called_once()


def test_unlit_nodes_do_not_identify_first_stage() -> None:
    assert DecisiveBattlePage.recognize_stage(_chapter_overview(0), 6) == 0


def test_reset_timeout_retries_only_the_saved_first_stage(controller: DecisiveController) -> None:
    page = controller._battle_page
    controller._ctx.ctrl = controller._ctrl
    page.detect_entry_status.side_effect = [
        DecisiveEntryStatus.REFRESH,
        DecisiveEntryStatus.REFRESH,
        DecisiveEntryStatus.REFRESHED,
    ]
    page._read_chapter.return_value = 6
    page.reset_chapter.side_effect = ResetConfirmationTimeoutError('第一小关未亮')
    with pytest.raises(ResetConfirmationTimeoutError):
        controller._handle_enter_map()
    with pytest.raises(RuntimeError, match='无法继续'):
        controller._handle_enter_map()
    page.click_enter_map.assert_not_called()
    controller._handle_enter_map()
    page.reset_chapter.assert_called_once_with(6)
    page.click_enter_map.assert_called_once()


@pytest.mark.parametrize('delayed', [False, True])
def test_reset_waits_for_real_first_stage_without_repeating_clicks(
    monkeypatch: pytest.MonkeyPatch, delayed: bool
) -> None:
    ctx = SimpleNamespace(ctrl=MagicMock(), ocr=MagicMock(), stop_event=threading.Event())
    page = DecisiveBattlePage(ctx)
    dialog = _chapter_overview(0)
    wrong_chapter = _chapter_overview(1)
    transition = [_chapter_overview(0), _chapter_overview(2), wrong_chapter] if delayed else []
    ctx.ctrl.screenshot.side_effect = [dialog, *transition, _chapter_overview(1)]
    page._read_chapter = lambda screen: 5 if screen is wrong_chapter else 6
    wait = MagicMock()
    monkeypatch.setattr(ctx.stop_event, 'wait', wait)
    monkeypatch.setattr('autowsgr.ui.page.get_current_page', lambda *_args, **_kw: None)
    match = ImageChecker.find_any
    button = (0.6, 0.5)
    monkeypatch.setattr(
        ImageChecker,
        'find_any',
        lambda screen, *args, **kw: (
            SimpleNamespace(center=button) if screen is dialog else match(screen, *args, **kw)
        ),
    )
    monkeypatch.setattr(ImageChecker, 'template_exists', lambda *_args, **_kw: False)
    assert page.reset_chapter(6)
    assert ctx.ctrl.click.call_args_list == [call(*CLICK_RESET_CHAPTER), call(*button)]
    assert wait.call_count == len(transition)


@pytest.mark.parametrize(
    ('chapter', 'status', 'stage', 'expected'),
    [
        (6, DecisiveEntryStatus.CHALLENGING, 2, DecisiveResult.STOPPED),
        (6, DecisiveEntryStatus.REFRESHED, 3, DecisiveResult.STOPPED),
        (5, DecisiveEntryStatus.CHALLENGING, 2, DecisiveResult.ERROR),
        (None, DecisiveEntryStatus.CHALLENGING, 2, DecisiveResult.ERROR),
        (6, DecisiveEntryStatus.REFRESH, 1, DecisiveResult.ERROR),
        (6, DecisiveEntryStatus.CHALLENGING, 0, DecisiveResult.ERROR),
    ],
)
def test_cold_start_reenters_only_verified_saved_stage(
    controller: DecisiveController,
    chapter: int | None,
    status: DecisiveEntryStatus,
    stage: int,
    expected: DecisiveResult,
) -> None:
    controller._map.try_leave_interrupted_sortie.return_value = True
    controller._battle_page._read_chapter.return_value = chapter
    controller._battle_page.wait_for_entry_status.return_value = status, _chapter_overview(stage)
    controller._prepare_entry_state = MagicMock()
    controller._advance_until_repair = MagicMock(return_value=DecisiveResult.STOPPED)

    assert controller.run() is expected
    controller._map.try_leave_interrupted_sortie.assert_called_once()
    controller._prepare_entry_state.assert_not_called()
    controller._battle_page.reset_chapter.assert_not_called()
    if expected is DecisiveResult.STOPPED:
        controller._battle_page.click_enter_map.assert_called_once()
        assert controller.state.stage == stage
        assert controller.state.phase == DecisivePhase.WAITING_FOR_MAP
    else:
        controller._battle_page.click_enter_map.assert_not_called()


def test_unverified_retreat_does_not_create_a_start_prior(controller: DecisiveController) -> None:
    controller._known_start_stage = 1
    controller._inventory_refresh_required = False
    controller._execute_retreat()

    controller._map.confirm_retreat.assert_called_once()
    assert controller._known_start_stage is None
    assert controller._inventory_refresh_required
    assert controller._ensure_tracking().tracker.initial is None


def test_retreat_reenters_actual_stage_with_fresh_inventory(controller: DecisiveController) -> None:
    controller._state.phase = DecisivePhase.RETREAT
    controller._state.stage = 2
    controller._state.ships = {'旧舰'}
    controller._ctrl.screenshot.return_value = _chapter_overview(2)
    controller._map.wait_for_entry_phase.return_value = DecisivePhase.PREPARE_COMBAT

    def stop_on_prepare() -> None:
        controller._ctx.stop_event.set()

    controller._handle_prepare_combat = MagicMock(side_effect=stop_on_prepare)
    assert controller._main_loop() == DecisiveResult.STOPPED
    controller._map.confirm_retreat.assert_called_once()
    controller._battle_page.reset_chapter.assert_not_called()
    controller._battle_page.click_enter_map.assert_called_once()
    assert controller.state.stage == 2
    assert controller.state.ships == set()
    assert controller._inventory_refresh_required
    assert controller._known_start_stage is None


def test_metadata_reports_missing_facts_without_disabling_decisive_history() -> None:
    metadata = TrackingMap.from_dict({'A': {'next': ['B']}, 'B': {'next': []}})
    reasons = '；'.join(metadata.degradation_reasons)
    assert '缺少起始点 0 声明' in reasons
    assert '由场景策略决定' in reasons
    assert '不启用遭遇次数推进' not in reasons
    assert '停用' not in reasons
    tracker = FusionTracker(metadata, dynamics='decisive', initial={'A': 1.0})
    assert tracker.estimate.current_node == 'A'


@pytest.mark.parametrize('value', [-1, False, True, 1.5, '60'])
def test_repair_threshold_requires_a_nonnegative_integer(value: object) -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match='quick_repair_threshold_seconds'):
        UserConfig(
            emulator=EmulatorConfig(serial='local', path='/tmp/emulator'),
            os_type=OSType.linux,
            quick_repair_threshold_seconds=value,
        )


@pytest.mark.parametrize(
    ('failures', 'expected'), [(2, DecisiveResult.CHAPTER_CLEAR), (3, DecisiveResult.ERROR)]
)
def test_transient_failures_share_three_attempts(
    controller: DecisiveController, failures: int, expected: DecisiveResult
) -> None:
    controller._prepare_entry_state = MagicMock()
    controller._advance_until_repair = MagicMock(
        side_effect=[
            *[TimeoutError('识别超时') for _ in range(failures)],
            DecisiveResult.CHAPTER_CLEAR,
        ]
    )
    controller._battle_page.is_current_page.return_value = True
    assert controller.run() is expected
    assert controller._advance_until_repair.call_count == 3
    controller._prepare_entry_state.assert_called_once()


def test_waiting_can_stop_without_restarting_the_round(controller: DecisiveController) -> None:
    from autowsgr.ops.decisive.repair import RepairOutcome, RepairStatus

    controller._prepare_entry_state = MagicMock()

    def begin_wait() -> None:
        controller.state.phase = DecisivePhase.WAITING_FOR_REPAIR

    controller._handle_enter_map = MagicMock(side_effect=begin_wait)
    controller._repairs.poll = MagicMock(return_value=RepairOutcome(RepairStatus.WAITING, 4, 180))
    controller._ctx.stop_event.wait = MagicMock(
        side_effect=lambda _: controller._ctx.stop_event.set()
    )
    assert controller.run_for_times(2) == [DecisiveResult.STOPPED]
    controller._prepare_entry_state.assert_called_once()
    controller._handle_enter_map.assert_called_once()
    controller._map.confirm_retreat.assert_not_called()


@pytest.mark.parametrize('saved_chapter', [6, 5])
def test_run_resumes_saved_repair_only_after_fresh_health(
    controller: DecisiveController, monkeypatch: pytest.MonkeyPatch, saved_chapter: int
) -> None:
    """从本轮入口穿过保存、两次等待、重入库存核实，最后才允许首次出击。"""
    controller._ctx.ctrl = controller._ctrl
    controller._battle_page._read_chapter.return_value = saved_chapter
    controller._map.wait_for_entry_phase.return_value = DecisivePhase.PREPARE_COMBAT
    controller._map.is_map_page.side_effect = [False, True]
    navigate = MagicMock()
    monkeypatch.setattr('autowsgr.ops.navigate.goto_page', navigate)
    page = handlers_module.DecisiveBattlePreparationPage.return_value
    names, initial = page.read_repair_snapshot.return_value
    damage = dict(initial)
    damage[5] = ShipDamageState.REPAIRING
    now = 0.0
    controller._repairs._clock = lambda: now
    monkeypatch.setattr('autowsgr.scheduler.decisive.time.monotonic', lambda: now)

    def read_slots(*, fresh: bool = False) -> tuple[list[str], dict[int, ShipDamageState]]:
        if fresh:
            assert now == 180
            damage[5] = ShipDamageState.NORMAL
        return names, damage.copy()

    def wait(seconds: float) -> bool:
        nonlocal now
        expected = 180 - now
        assert seconds == expected
        page.start_battle.assert_not_called()
        controller._battle_page.click_enter_map.assert_called_once()
        now += min(seconds, 179)
        return False

    page.read_repair_snapshot.side_effect = read_slots
    controller._ctx.stop_event.wait = MagicMock(side_effect=wait)
    page.start_battle.side_effect = controller._ctx.stop_event.set
    result = controller.run()
    assert now == 180
    assert controller._ctx.stop_event.wait.call_count == 2
    controller._map.leave_to_overview.assert_called_once()
    controller._battle_page.reset_chapter.assert_not_called()
    controller._battle_page.navigate_to_chapter.assert_called_once_with(6)
    page.repair_slots.assert_not_called()
    if saved_chapter == 6:
        assert result is DecisiveResult.STOPPED
        page.read_repair_snapshot.assert_any_call(fresh=True)
        assert controller._map.check_fleet.call_count == 2
        assert controller._battle_page.click_enter_map.call_count == 2
        page.start_battle.assert_called_once()
    else:
        assert result is DecisiveResult.ERROR
        controller._battle_page.click_enter_map.assert_called_once()
        assert controller._repairs.saved
        page.start_battle.assert_not_called()


def test_full_dock_enters_destroy_directly_from_dialog(
    controller: DecisiveController, monkeypatch: pytest.MonkeyPatch
) -> None:
    destroy = MagicMock(return_value=True)
    monkeypatch.setattr('autowsgr.ops.destroy.destroy_ships_auto', destroy)
    controller._config = DecisiveConfig(full_destroy=True)
    controller._do_dock_full_destroy()
    destroy.assert_called_once_with(controller._ctx, from_dialog=True)
    controller._ctrl.click.assert_not_called()


def test_node_yields_after_overlays_before_next_formation(controller: DecisiveController) -> None:
    controller.state.node_completed = True
    controller.state.phase = DecisivePhase.CHOOSE_FLEET
    order = []

    def finish_purchase() -> None:
        order.append('购舰')
        controller.state.phase = DecisivePhase.PREPARE_COMBAT

    def stable_map() -> bool:
        order.append('确认下一节点地图')
        return True

    controller._handle_choose_fleet = finish_purchase
    controller._prepare_map_tracking = stable_map
    assert controller._advance_node() is DecisiveResult.NODE_COMPLETE
    assert order == ['购舰', '确认下一节点地图']
    assert controller.state.at_node_boundary
    controller._map.enter_formation.assert_not_called()
    controller._map.leave_to_overview.assert_not_called()

    # 只有外部任务真正拿到设备才暂离。同一小关保留定位和战斗历史。
    session = controller._tracking
    assert controller._park_for_daily()
    assert controller._park_for_daily()
    controller._map.leave_to_overview.assert_called_once()
    assert controller.state.expected_stage == 1
    assert controller._tracking is session
    assert controller.state.navigate_to_entry


def test_retry_after_reentry_recovers_inside_map(controller: DecisiveController) -> None:
    controller._repairs._saved = True
    controller.state.phase = DecisivePhase.WAITING_FOR_MAP
    controller._battle_page.is_current_page.return_value = False
    controller._map.is_fleet_preparation.return_value = False
    controller._map.detect_decisive_phase.return_value = DecisivePhase.PREPARE_COMBAT
    controller._advance_until_repair = MagicMock(
        side_effect=[TimeoutError(), DecisiveResult.NODE_COMPLETE]
    )
    controller._prepare_entry_state = MagicMock()

    assert controller._advance_node() is DecisiveResult.RETRY
    assert not controller._park_for_daily()
    assert controller._advance_node() is DecisiveResult.NODE_COMPLETE
    assert controller.state.phase is DecisivePhase.PREPARE_COMBAT
    controller._prepare_entry_state.assert_not_called()
    controller._battle_page.click_enter_map.assert_not_called()


def test_inventory_survives_temporary_leave_only_on_same_map(
    controller: DecisiveController,
) -> None:
    controller.state.ships = {'U-96'}
    controller.state.fleet[1] = 'U-96'
    controller._enter_verified_stage(1)
    assert controller.state.ships == {'U-96'}
    assert controller.state.fleet[1] == 'U-96'
    controller._enter_verified_stage(2)
    assert not controller.state.ships
    assert not any(controller.state.fleet)
