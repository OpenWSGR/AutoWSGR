"""决战恢复、确认起点及停止请求必须先于出征等有副作用的操作。"""

from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from autowsgr.combat.node_fusion.map import TrackingMap
from autowsgr.combat.node_fusion.model import FusionTracker
from autowsgr.emulator.frame import CapturedFrame
from autowsgr.image_resources import Templates
from autowsgr.infra import DecisiveConfig
from autowsgr.ops.decisive import handlers as handlers_module
from autowsgr.ops.decisive.config import MapData
from autowsgr.ops.decisive.controller import DecisiveController
from autowsgr.ops.decisive.logic import DecisiveLogic
from autowsgr.ops.decisive.state import DecisiveState
from autowsgr.ops.decisive.tracking import DecisiveTrackingSession
from autowsgr.types import DecisiveEntryStatus, DecisivePhase, ShipDamageState
from autowsgr.ui.battle.fleet_change._detect import FleetSnapshot
from autowsgr.ui.decisive.battle_page import DecisiveBattlePage


def _chapter_overview(completed: int) -> np.ndarray:
    """构造真实入口模板和明确完成标记；验证页面进度到领域小关的边界。"""
    image = np.full((720, 1280, 3), 40, dtype=np.uint8)
    template = Templates.Decisive.ENTRY_CHALLENGING
    patch = cv2.resize(
        template.image,
        (round(template.width * 1280 / 960), round(template.height * 720 / 540)),
    )
    height, width = patch.shape[:2]
    image[600 : 600 + height, 500 : 500 + width] = patch
    for index, (x, y) in enumerate(((0.606, 0.375), (0.532, 0.703), (0.862, 0.644))):
        px, py = int(x * 1280), int(y * 720)
        image[py - 2 : py + 3, px - 2 : px + 3] = (250, 244, 253) if index < completed else 40
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
    ctrl._ctx = SimpleNamespace(
        stop_event=threading.Event(),
        update_ship_damage=MagicMock(),
        is_ship_available=lambda _name: True,
        config=SimpleNamespace(log=SimpleNamespace(dir=None, node_fusion_replay=False)),
    )
    ctrl._ctrl = MagicMock()
    ctrl._ocr = MagicMock()
    ctrl._config = DecisiveConfig(chapter=6, level1=fleet, useful_skill=False)
    ctrl._state = DecisiveState(chapter=6, stage=1, phase=DecisivePhase.PREPARE_COMBAT)
    ctrl._logic = DecisiveLogic(ctrl._config, ctrl._state, ctx=ctrl._ctx)
    ctrl._map = MagicMock()
    frame = CapturedFrame(np.zeros((2, 2, 3), dtype=np.uint8), 1, 1.0)
    ctrl._ctrl.screenshot.return_value = _chapter_overview(0)
    ctrl._map.wait_for_stable_map_frame.return_value = frame
    ctrl._map.detect_decisive_phase.return_value = DecisivePhase.PREPARE_COMBAT
    ctrl._map.recognize_node.return_value = None
    ctrl._map.is_skill_used.return_value = True
    ctrl._map.check_fleet.return_value = (fleet, {}, set(fleet))
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
    controller._tracking = None
    controller._handle_enter_map()
    controller._handle_prepare_combat()

    controller._map.check_fleet.assert_called_once()
    assert controller._tracking.tracker.initial is None


def test_stop_during_repair_never_starts_another_battle(controller: DecisiveController) -> None:
    page = handlers_module.DecisiveBattlePreparationPage.return_value
    page.apply_repair.side_effect = lambda *_args, **_kwargs: controller._ctx.stop_event.set()

    controller._handle_prepare_combat()

    page.apply_repair.assert_called_once()
    page.start_battle.assert_not_called()
    assert controller.state.phase == DecisivePhase.FINISHED
    assert not any(
        obs.action == 'encounter_complete' for obs in controller._tracking.tracker.observations
    )


@pytest.mark.parametrize(
    ('following_status', 'completed', 'valid'),
    [
        (DecisiveEntryStatus.REFRESHED, 0, True),
        (DecisiveEntryStatus.REFRESHED, 1, False),
        (DecisiveEntryStatus.REFRESH, 0, False),
    ],
)
def test_reset_needs_verified_first_stage_before_certain_a(
    controller: DecisiveController,
    following_status: DecisiveEntryStatus,
    completed: int,
    valid: bool,
) -> None:
    controller._inventory_refresh_required = False
    controller._battle_page.detect_entry_status.side_effect = [
        DecisiveEntryStatus.REFRESH,
        following_status,
    ]
    controller._ctrl.screenshot.return_value = _chapter_overview(completed)
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


@pytest.mark.parametrize('completed', [0, 1, 2])
def test_entry_converts_page_progress_to_domain_stage(
    controller: DecisiveController, completed: int
) -> None:
    controller._ctrl.screenshot.return_value = _chapter_overview(completed)

    controller._handle_enter_map()

    assert controller.state.stage == completed + 1
    assert controller.state.phase == DecisivePhase.WAITING_FOR_MAP
    assert controller._ensure_tracking().stage == completed + 1
    controller._battle_page.click_enter_map.assert_called_once()


def test_completed_page_conflicts_with_active_entry(controller: DecisiveController) -> None:
    controller._ctrl.screenshot.return_value = _chapter_overview(3)

    with pytest.raises(RuntimeError, match='已全部完成'):
        controller._handle_enter_map()

    controller._battle_page.click_enter_map.assert_not_called()
    assert controller.state.phase != DecisivePhase.CHAPTER_CLEAR


def test_unverified_retreat_does_not_create_a_start_prior(controller: DecisiveController) -> None:
    controller._known_start_stage = 1
    controller._inventory_refresh_required = False
    controller._execute_retreat()

    controller._map.confirm_retreat.assert_called_once()
    assert controller._known_start_stage is None
    assert controller._inventory_refresh_required
    assert controller._ensure_tracking().tracker.initial is None


def test_metadata_reports_missing_facts_without_disabling_decisive_history() -> None:
    metadata = TrackingMap.from_dict({'A': {'next': ['B']}, 'B': {'next': []}})
    reasons = '；'.join(metadata.degradation_reasons)
    assert '缺少起始点 0 声明' in reasons
    assert '由场景策略决定' in reasons
    assert '不启用遭遇次数推进' not in reasons
    assert '停用' not in reasons
    tracker = FusionTracker(metadata, dynamics='decisive', initial={'A': 1.0})
    assert tracker.estimate.current_node == 'A'
