"""Focused tests for decisive map-entry timing."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, call

import numpy as np
import pytest

from autowsgr.ops.decisive import handlers
from autowsgr.ops.decisive.logic import DecisiveLogic
from autowsgr.types import DecisiveEntryStatus, DecisivePhase, FleetSelection
from autowsgr.ui.decisive import battle_page, map_controller, overlay, preparation
from autowsgr.ui.decisive.overlay import (
    ADVANCE_CARD_POSITIONS,
    ADVANCE_CHOICE_ROI,
    ADVANCE_CHOICE_THREE_ROI,
    CONFIRM_EXIT_ROI,
    FLEET_ACQUISITION_ROI,
    CLICK_ADVANCE_CONFIRM,
    FLEET_NAME_ROI,
    USE_LAST_FLEET_ROI,
    DecisiveOverlay,
)


def test_enter_map_uses_overlay_detection_instead_of_fixed_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Map entry transitions to recognition-driven waiting without a fixed sleep."""
    events: list[object] = []
    battle_page = MagicMock()
    battle_page.detect_entry_status.return_value = DecisiveEntryStatus.CHALLENGING
    battle_page.detect_stage.return_value = 1
    battle_page.click_enter_map.side_effect = lambda: events.append('enter')
    battle_page_context = SimpleNamespace(
        _battle_page=battle_page,
        _config=SimpleNamespace(chapter=6),
        _ctrl=MagicMock(),
        _state=SimpleNamespace(stage=None, phase=None),
        _use_last_fleet_attempts=1,
        _wait_deadline=None,
        _resume_mode=True,
    )
    monkeypatch.setattr(handlers.time, 'monotonic', lambda: 100.0)
    monkeypatch.setattr(
        handlers.time,
        'sleep',
        lambda delay: events.append(('sleep', delay)),
    )

    handlers.DecisivePhaseHandlers._handle_enter_map(battle_page_context)

    assert events == ['enter']
    assert battle_page_context._state.phase is DecisivePhase.WAITING_FOR_MAP


def test_choose_ships_uses_level2_when_no_level1_is_available() -> None:
    """Backup ships are considered at every incomplete node, not only first_node."""
    config = SimpleNamespace(level1=['Primary'], level2=['Backup'])
    state = SimpleNamespace(fleet=[''] * 7, score=10)
    logic = DecisiveLogic(config, state)

    result = logic.choose_ships(
        {'Backup': FleetSelection('Backup', 4, (0.25, 0.5))},
        first_node=False,
    )

    assert result == ['Backup']


def test_choose_ships_prioritizes_level1_before_level2() -> None:
    """Primary ships consume the budget before backup ships are considered."""
    config = SimpleNamespace(level1=['Primary'], level2=['Backup'])
    state = SimpleNamespace(fleet=[''] * 7, score=10)
    logic = DecisiveLogic(config, state)

    result = logic.choose_ships(
        {
            'Primary': FleetSelection('Primary', 4, (0.25, 0.5)),
            'Backup': FleetSelection('Backup', 4, (0.375, 0.5)),
        },
        first_node=False,
    )

    assert result == ['Primary', 'Backup']


def test_choose_ships_first_node_preserves_two_ship_goal() -> None:
    """First-node purchasing prefers an affordable two-ship bundle over one primary."""
    config = SimpleNamespace(level1=['Primary'], level2=['BackupA', 'BackupB'])
    state = SimpleNamespace(fleet=[''] * 7, ships=set(), score=10)
    logic = DecisiveLogic(config, state)

    result = logic.choose_ships(
        {
            'Primary': FleetSelection('Primary', 6, (0.25, 0.5)),
            'BackupA': FleetSelection('BackupA', 5, (0.375, 0.5)),
            'BackupB': FleetSelection('BackupB', 5, (0.5, 0.5)),
        },
        first_node=True,
    )

    assert result == ['BackupA', 'BackupB']


def test_choose_ships_first_node_prefers_primary_when_two_ship_bundle_fits() -> None:
    """A 6+4 primary/backup bundle wins when it still reaches two ships."""
    config = SimpleNamespace(level1=['Primary'], level2=['Backup'])
    state = SimpleNamespace(fleet=[''] * 7, ships=set(), score=10)
    logic = DecisiveLogic(config, state)

    result = logic.choose_ships(
        {
            'Primary': FleetSelection('Primary', 6, (0.25, 0.5)),
            'Backup': FleetSelection('Backup', 4, (0.375, 0.5)),
        },
        first_node=True,
    )

    assert result == ['Primary', 'Backup']


def test_choose_ships_fills_pool_before_primary_upgrade() -> None:
    """Later nodes spend on missing ships before upgrading existing primaries."""
    config = SimpleNamespace(level1=['Primary'], level2=['BackupA', 'BackupB'])
    state = SimpleNamespace(
        fleet=[''] * 7,
        ships={'BackupA', 'OwnedA', 'OwnedB', 'OwnedC'},
        score=10,
    )
    logic = DecisiveLogic(config, state)

    result = logic.choose_ships(
        {
            'Primary': FleetSelection('Primary', 6, (0.25, 0.5)),
            'BackupB': FleetSelection('BackupB', 4, (0.375, 0.5)),
            'BackupA': FleetSelection('BackupA', 4, (0.5, 0.5)),
        },
        first_node=False,
    )

    assert result == ['Primary', 'BackupB']


def test_choose_ships_upgrades_existing_primary_only() -> None:
    """Once six ships exist, only an already-acquired primary may be upgraded."""
    config = SimpleNamespace(level1=['Primary'], level2=['Backup'])
    state = SimpleNamespace(
        fleet=[''] * 7,
        ships={'Primary', 'Backup', 'Ship3', 'Ship4', 'Ship5', 'Ship6'},
        score=10,
    )
    logic = DecisiveLogic(config, state)

    result = logic.choose_ships(
        {
            'Primary': FleetSelection('Primary', 4, (0.25, 0.5)),
            'Backup': FleetSelection('Backup', 1, (0.375, 0.5)),
        },
        first_node=False,
    )

    assert result == ['Primary']


def test_best_fleet_keeps_current_damaged_ship_until_repair() -> None:
    """A damaged ship already in formation stays in the decisive target fleet."""
    config = SimpleNamespace(
        level1=['Primary'],
        level2=['Backup'],
        flagship_priority=[],
    )
    state = SimpleNamespace(
        fleet=['', 'Primary', 'Backup', '', '', '', ''],
        ships={'Primary', 'Backup'},
    )
    ctx = SimpleNamespace(is_ship_available=lambda name: name != 'Primary')
    logic = DecisiveLogic(config, state, ctx=ctx)

    assert logic.get_best_fleet() == ['', 'Primary', 'Backup', '', '', '', '']


def test_refresh_entry_resets_before_entering_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A completed chapter resets first, then enters the refreshed map state."""
    events: list[str] = []
    battle_page = MagicMock()
    battle_page.detect_entry_status.side_effect = [
        DecisiveEntryStatus.REFRESH,
        DecisiveEntryStatus.REFRESHED,
    ]
    battle_page.reset_chapter.return_value = True
    battle_page.detect_stage.return_value = 1
    battle_page.click_enter_map.side_effect = lambda: events.append('enter')
    context = SimpleNamespace(
        _battle_page=battle_page,
        _config=SimpleNamespace(chapter=6),
        _ctrl=MagicMock(),
        _state=SimpleNamespace(stage=None, phase=None),
        _use_last_fleet_attempts=1,
        _skip_advance_choice=True,
        _wait_deadline=None,
        _resume_mode=True,
    )
    monkeypatch.setattr(handlers.time, 'monotonic', lambda: 100.0)

    handlers.DecisivePhaseHandlers._handle_enter_map(context)

    battle_page.reset_chapter.assert_called_once_with()
    assert battle_page.detect_entry_status.call_count == 2
    assert events == ['enter']
    assert context._state.phase is DecisivePhase.WAITING_FOR_MAP


def test_map_fallback_routes_to_prepare_without_state_guess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A confirmed map page falls through to formation without guessing state."""
    screen = np.zeros((720, 1280, 3), dtype=np.uint8)
    map_controller_mock = MagicMock()
    map_controller_mock.wait_for_entry_phase.return_value = DecisivePhase.PREPARE_COMBAT
    context = SimpleNamespace(
        _ctrl=SimpleNamespace(screenshot=lambda: screen),
        _map=map_controller_mock,
        _state=SimpleNamespace(
            stage=1,
            node='U',
            phase=DecisivePhase.WAITING_FOR_MAP,
        ),
        _has_chosen_fleet=False,
        _fleet_overlay_enabled=True,
        _advance_source_node=None,
        _use_last_fleet_attempts=0,
        _skip_advance_choice=False,
        _advance_choice_roi=lambda: None,
        _wait_deadline=101.0,
    )
    monkeypatch.setattr(handlers.time, 'monotonic', lambda: 100.0)
    events: list[float] = []
    monkeypatch.setattr(handlers.time, 'sleep', events.append)

    handlers.DecisivePhaseHandlers._handle_waiting_for_map(context)

    map_controller_mock.wait_for_entry_phase.assert_called_once_with(
        wait_for_use_last=True,
        wait_for_advance=True,
        wait_for_fleet=False,
        timeout=3.0,
        interval=0.2,
    )
    assert context._state.phase is DecisivePhase.PREPARE_COMBAT
    assert context._fleet_overlay_enabled is False
    assert events == [0.05]


def test_new_entry_enables_fleet_after_advance_choice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A normal new entry enables fleet detection after choosing advance."""
    map_controller_mock = MagicMock()
    map_controller_mock.wait_for_entry_phase.return_value = DecisivePhase.PREPARE_COMBAT
    context = SimpleNamespace(
        _ctrl=SimpleNamespace(screenshot=lambda: np.zeros((720, 1280, 3), dtype=np.uint8)),
        _map=map_controller_mock,
        _state=SimpleNamespace(
            stage=1,
            node='U',
            phase=DecisivePhase.WAITING_FOR_MAP,
        ),
        _fleet_overlay_enabled=True,
        _has_chosen_fleet=False,
        _advance_source_node=None,
        _use_last_fleet_attempts=0,
        _skip_advance_choice=True,
        _advance_choice_roi=lambda: None,
        _wait_deadline=101.0,
    )
    monkeypatch.setattr(handlers.time, 'monotonic', lambda: 100.0)
    monkeypatch.setattr(handlers.time, 'sleep', lambda _delay: None)

    handlers.DecisivePhaseHandlers._handle_waiting_for_map(context)

    map_controller_mock.wait_for_entry_phase.assert_called_once_with(
        wait_for_use_last=True,
        wait_for_advance=False,
        wait_for_fleet=True,
        timeout=3.0,
        interval=0.2,
    )


def test_full_recovery_keeps_fleet_check_enabled_without_advance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SL recovery keeps fleet detection enabled even when no advance popup appears."""
    map_controller_mock = MagicMock()
    map_controller_mock.wait_for_entry_phase.return_value = DecisivePhase.PREPARE_COMBAT
    context = SimpleNamespace(
        _ctrl=SimpleNamespace(screenshot=lambda: np.zeros((720, 1280, 3), dtype=np.uint8)),
        _map=map_controller_mock,
        _state=SimpleNamespace(
            stage=1,
            node='U',
            phase=DecisivePhase.WAITING_FOR_MAP,
        ),
        _fleet_overlay_enabled=True,
        _full_recovery_check=True,
        _has_chosen_fleet=False,
        _use_last_fleet_attempts=0,
        _skip_advance_choice=False,
        _advance_source_node=None,
        _advance_choice_roi=lambda: None,
        _wait_deadline=101.0,
    )
    monkeypatch.setattr(handlers.time, 'monotonic', lambda: 100.0)
    monkeypatch.setattr(handlers.time, 'sleep', lambda _delay: None)

    handlers.DecisivePhaseHandlers._handle_waiting_for_map(context)

    map_controller_mock.wait_for_entry_phase.assert_called_once_with(
        wait_for_use_last=True,
        wait_for_advance=True,
        wait_for_fleet=True,
        timeout=3.0,
        interval=0.2,
    )
    assert context._fleet_overlay_enabled is True


def test_entry_phase_checks_overlays_before_map_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Entry recognition checks both optional overlays before accepting the map page."""
    controller = object.__new__(map_controller.DecisiveMapController)
    controller._ctrl = MagicMock()
    controller._wait_for_use_last_fleet = MagicMock(return_value=False)
    controller._wait_for_advance_choice = MagicMock(return_value=False)
    monkeypatch.setattr(map_controller, 'is_fleet_acquisition', lambda _screen: False)
    monkeypatch.setattr(map_controller, 'is_decisive_map_page', lambda _screen: True)

    phase = controller.wait_for_entry_phase(
        wait_for_use_last=True,
        wait_for_advance=True,
        timeout=3.0,
        interval=0.2,
    )

    assert phase is DecisivePhase.PREPARE_COMBAT
    controller._wait_for_advance_choice.assert_called_once_with(
        None,
        timeout=3.0,
        interval=0.2,
    )


def test_entry_phase_can_skip_fleet_overlay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Initial entry can finish on the map without checking fleet acquisition."""
    controller = object.__new__(map_controller.DecisiveMapController)
    controller._ctrl = MagicMock()
    controller._wait_for_use_last_fleet = MagicMock(return_value=False)
    controller._wait_for_advance_choice = MagicMock(return_value=False)
    fleet_match = MagicMock(return_value=True)
    monkeypatch.setattr(map_controller, 'is_fleet_acquisition', fleet_match)
    monkeypatch.setattr(map_controller, 'is_decisive_map_page', lambda _screen: True)

    phase = controller.wait_for_entry_phase(
        wait_for_use_last=False,
        wait_for_advance=False,
        wait_for_fleet=False,
    )

    assert phase is DecisivePhase.PREPARE_COMBAT
    fleet_match.assert_not_called()


def test_decisive_overview_uses_entry_status_roi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Overview recognition searches the fixed entry-status button region."""
    calls: list[object] = []
    monkeypatch.setattr(
        battle_page.ImageChecker,
        'find_any',
        lambda _screen, _templates, **kwargs: calls.append(kwargs)
        or SimpleNamespace(confidence=0.91),
    )

    result = battle_page.DecisiveBattlePage.is_current_page(
        np.zeros((720, 1280, 3), dtype=np.uint8),
    )

    assert result.matched
    assert calls[0]['roi'] is battle_page.ENTRY_STATUS_ROI


def test_recognize_stage_uses_one_based_map_stage_numbers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stage detection aligns its return values with EX-<chapter>-<stage>.yaml."""
    screen = np.zeros((720, 1280, 3), dtype=np.uint8)
    points = battle_page._STAGE_CHECK_POINTS[6]
    white = battle_page._STAGE_CHECK_COLOR.as_rgb_tuple()

    assert battle_page.DecisiveBattlePage.recognize_stage(screen, 6) == 0

    for rx, ry in points[:1]:
        screen[int(ry * 720), int(rx * 1280)] = white
    assert battle_page.DecisiveBattlePage.recognize_stage(screen, 6) == 1

    for rx, ry in points[1:2]:
        screen[int(ry * 720), int(rx * 1280)] = white
    assert battle_page.DecisiveBattlePage.recognize_stage(screen, 6) == 2

    for rx, ry in points[2:]:
        screen[int(ry * 720), int(rx * 1280)] = white
    monkeypatch.setattr(
        battle_page.ImageChecker,
        'template_exists',
        lambda _screen, template, **_kwargs: template.name
        in {'decisive_entry_challenging', 'decisive_reset_button'},
    )
    assert battle_page.DecisiveBattlePage.recognize_stage(screen, 6) == 3


def test_recognize_stage_uses_entry_status_for_three_existing_nodes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Three visible nodes need entry status to distinguish stage 3 from clear."""
    screen = np.zeros((720, 1280, 3), dtype=np.uint8)
    points = battle_page._STAGE_CHECK_POINTS[6]
    color = battle_page._STAGE_CHECK_COLOR.as_rgb_tuple()
    for rx, ry in points:
        screen[int(ry * 720), int(rx * 1280)] = color

    def match_template(_screen: object, template: object, **_kwargs: object) -> bool:
        return template is battle_page.Templates.Decisive.ENTRY_CHALLENGING or template is (
            battle_page.Templates.Decisive.RESET_BUTTON
        )

    monkeypatch.setattr(battle_page.ImageChecker, 'template_exists', match_template)
    assert battle_page.DecisiveBattlePage.recognize_stage(screen, 6) == 3

    monkeypatch.setattr(
        battle_page.ImageChecker,
        'template_exists',
        lambda _screen, template, **_kwargs: template is battle_page.Templates.Decisive.ENTRY_REFRESH,
    )
    assert battle_page.DecisiveBattlePage.recognize_stage(screen, 6) is None


def test_completed_chapter_does_not_enter_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A completed overview enters the existing chapter-clear phase."""
    battle_page = MagicMock()
    battle_page.detect_entry_status.return_value = DecisiveEntryStatus.CHALLENGING
    battle_page.detect_stage.return_value = None
    context = SimpleNamespace(
        _battle_page=battle_page,
        _config=SimpleNamespace(chapter=6),
        _ctrl=MagicMock(),
        _state=SimpleNamespace(stage=0, phase=DecisivePhase.ENTER_MAP),
        _resume_mode=True,
    )

    handlers.DecisivePhaseHandlers._handle_enter_map(context)

    assert context._state.phase is DecisivePhase.CHAPTER_CLEAR
    battle_page.click_enter_map.assert_not_called()


def test_entry_status_uses_entry_status_roi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chapter-entry status recognition uses the same fixed ROI."""
    page = object.__new__(battle_page.DecisiveBattlePage)
    page._ctrl = MagicMock()
    screen = np.zeros((720, 1280, 3), dtype=np.uint8)
    page._ctrl.screenshot.return_value = screen
    calls: list[object] = []
    template_name = battle_page.Templates.Decisive.entry_status_templates()[1].name
    monkeypatch.setattr(
        battle_page.ImageChecker,
        'find_any',
        lambda _screen, _templates, **kwargs: calls.append(kwargs)
        or SimpleNamespace(template_name=template_name),
    )

    status = page.detect_entry_status(timeout=1.0)

    assert status is DecisiveEntryStatus.CHALLENGING
    assert calls[0]['roi'] is battle_page.ENTRY_STATUS_ROI


def test_fleet_overlay_requires_fresh_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stale fleet overlay match must not re-enter the OCR phase."""
    controller = object.__new__(map_controller.DecisiveMapController)
    controller._ctrl = MagicMock()
    screen = np.zeros((720, 1280, 3), dtype=np.uint8)
    controller._ctrl.screenshot.return_value = screen
    monkeypatch.setattr(
        map_controller.ImageChecker,
        'template_exists',
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        map_controller,
        'detect_decisive_overlay',
        MagicMock(side_effect=[DecisiveOverlay.FLEET_ACQUISITION, None]),
    )
    monkeypatch.setattr(map_controller, 'is_fleet_acquisition', lambda _screen: False)
    monkeypatch.setattr(map_controller, 'is_decisive_map_page', lambda _screen: True)
    monkeypatch.setattr(map_controller.time, 'sleep', lambda _delay: None)

    assert controller.detect_decisive_phase() is DecisivePhase.PREPARE_COMBAT


def test_advance_choice_overlay_uses_fixed_roi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Advance-choice matching is restricted to the annotated card region."""
    calls: list[object] = []

    def template_exists(
        _screen: object, _template: object, *, roi: object, confidence: float
    ) -> bool:
        calls.append((roi, confidence))
        return len(calls) == 3

    monkeypatch.setattr(overlay.ImageChecker, 'template_exists', template_exists)

    assert overlay.detect_decisive_overlay(np.zeros((720, 1280, 3), dtype=np.uint8)) is (
        DecisiveOverlay.ADVANCE_CHOICE
    )
    assert calls == [
        (FLEET_ACQUISITION_ROI, 0.70),
        (CONFIRM_EXIT_ROI, 0.85),
        (ADVANCE_CHOICE_ROI, 0.80),
    ]


def test_fleet_overlay_uses_fixed_roi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fleet acquisition matching is restricted to the annotated title ROI."""
    calls: list[tuple[object, float]] = []

    def template_exists(
        _screen: object, _template: object, *, roi: object, confidence: float
    ) -> bool:
        calls.append((roi, confidence))
        return True

    monkeypatch.setattr(overlay.ImageChecker, 'template_exists', template_exists)

    assert overlay.detect_decisive_overlay(np.zeros((720, 1280, 3), dtype=np.uint8)) is (
        DecisiveOverlay.FLEET_ACQUISITION
    )
    assert calls == [(FLEET_ACQUISITION_ROI, 0.70)]


def test_advance_choice_overlay_tries_three_branch_roi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fallback detector also checks the annotated three-card ROI."""
    calls: list[object] = []

    def template_exists(
        _screen: object, _template: object, *, roi: object, confidence: float
    ) -> bool:
        calls.append((roi, confidence))
        return roi is ADVANCE_CHOICE_THREE_ROI

    monkeypatch.setattr(overlay.ImageChecker, 'template_exists', template_exists)

    assert overlay.detect_decisive_overlay(np.zeros((720, 1280, 3), dtype=np.uint8)) is (
        DecisiveOverlay.ADVANCE_CHOICE
    )
    assert calls[-1] == (ADVANCE_CHOICE_THREE_ROI, 0.80)


def test_advance_choice_explicit_roi_falls_back_to_two_card_roi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A graph-selected three-card ROI still accepts a live two-card popup."""
    calls: list[object] = []

    def template_exists(
        _screen: object, _template: object, *, roi: object, confidence: float
    ) -> bool:
        calls.append((roi, confidence))
        return roi is ADVANCE_CHOICE_ROI

    monkeypatch.setattr(overlay.ImageChecker, 'template_exists', template_exists)

    assert overlay.detect_decisive_overlay(
        np.zeros((720, 1280, 3), dtype=np.uint8),
        advance_choice_roi=ADVANCE_CHOICE_THREE_ROI,
    ) is DecisiveOverlay.ADVANCE_CHOICE
    assert calls[-2:] == [
        (ADVANCE_CHOICE_THREE_ROI, 0.80),
        (ADVANCE_CHOICE_ROI, 0.80),
    ]


def test_node_result_timeout_keeps_waiting_for_late_overlay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A late post-combat advance popup must not fall through to formation."""
    context = SimpleNamespace(
        _logic=SimpleNamespace(is_stage_end=lambda: False),
        _map=SimpleNamespace(
            detect_decisive_phase=MagicMock(return_value=DecisivePhase.PREPARE_COMBAT)
        ),
        _state=SimpleNamespace(
            node='A',
            stage=1,
            phase=DecisivePhase.NODE_RESULT,
        ),
        _fleet_overlay_enabled=False,
        _POST_COMBAT_TIMEOUT=0.0,
        _wait_deadline=0.0,
    )
    monkeypatch.setattr(handlers.time, 'monotonic', lambda: 100.0)

    handlers.DecisivePhaseHandlers._handle_node_result(context)

    assert context._state.node == 'B'
    assert context._state.phase is DecisivePhase.WAITING_FOR_MAP
    assert context._wait_deadline == 110.0


def test_non_terminal_node_result_enables_fleet_overlay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-terminal result enables fleet detection for the next node."""
    detect_phase = MagicMock(return_value=DecisivePhase.CHOOSE_FLEET)
    context = SimpleNamespace(
        _logic=SimpleNamespace(is_stage_end=lambda: False),
        _map=SimpleNamespace(detect_decisive_phase=detect_phase),
        _state=SimpleNamespace(
            node='A',
            stage=1,
            phase=DecisivePhase.NODE_RESULT,
        ),
        _fleet_overlay_enabled=False,
        _advance_choice_roi=lambda: None,
        _POST_COMBAT_TIMEOUT=1.0,
        _POST_COMBAT_INTERVAL=0.0,
    )
    monkeypatch.setattr(handlers.time, 'monotonic', lambda: 100.0)
    monkeypatch.setattr(handlers.time, 'sleep', lambda _delay: None)

    handlers.DecisivePhaseHandlers._handle_node_result(context)

    assert context._fleet_overlay_enabled is True
    detect_phase.assert_called_once_with(
        advance_choice_roi=None,
        allow_fleet_overlay=True,
    )
    assert context._state.phase is DecisivePhase.CHOOSE_FLEET


def test_terminal_node_result_disables_fleet_overlay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A terminal result enters stage clear without enabling fleet detection."""
    context = SimpleNamespace(
        _logic=SimpleNamespace(is_stage_end=lambda: True),
        _state=SimpleNamespace(
            node='J',
            stage=1,
            phase=DecisivePhase.NODE_RESULT,
        ),
        _fleet_overlay_enabled=True,
    )

    handlers.DecisivePhaseHandlers._handle_node_result(context)

    assert context._fleet_overlay_enabled is False
    assert context._state.phase is DecisivePhase.STAGE_CLEAR


def test_stage_clear_reanchors_next_subsection_from_unknown_node() -> None:
    """A new subsection starts at U so its first live node is recognized."""
    context = SimpleNamespace(
        _map=SimpleNamespace(confirm_stage_clear=MagicMock(return_value=[])),
        _state=SimpleNamespace(
            stage=1,
            node='J',
            phase=DecisivePhase.STAGE_CLEAR,
        ),
        _advance_source_node='J',
        _resume_mode=False,
        _fleet_overlay_enabled=False,
    )

    handlers.DecisivePhaseHandlers._handle_stage_clear(context)

    assert context._state.node == 'U'
    assert context._advance_source_node is None
    assert context._resume_mode is True
    assert context._fleet_overlay_enabled is True
    assert context._state.phase is DecisivePhase.ENTER_MAP


def test_temporary_leave_disables_fleet_overlay_for_reentry() -> None:
    """A leave/re-entry context suppresses fleet detection until another result."""
    map_controller = SimpleNamespace(
        open_retreat_dialog=MagicMock(),
        confirm_leave=MagicMock(),
    )
    context = SimpleNamespace(
        _map=map_controller,
        _fleet_overlay_enabled=True,
    )

    handlers.DecisivePhaseHandlers._execute_leave(context)

    assert context._fleet_overlay_enabled is False
    map_controller.open_retreat_dialog.assert_called_once_with()
    map_controller.confirm_leave.assert_called_once_with()


def test_retreat_reenables_fleet_overlay_for_reentry() -> None:
    """A retreat starts a fresh entry path where fleet detection is allowed."""
    map_controller = SimpleNamespace(
        open_retreat_dialog=MagicMock(),
        confirm_retreat=MagicMock(),
    )
    context = SimpleNamespace(
        _map=map_controller,
        _fleet_overlay_enabled=False,
    )

    handlers.DecisivePhaseHandlers._execute_retreat(context)

    assert context._fleet_overlay_enabled is True
    map_controller.open_retreat_dialog.assert_called_once_with()
    map_controller.confirm_retreat.assert_called_once_with()


def test_choose_fleet_commits_state_only_after_purchase_and_close() -> None:
    """Fleet state is committed only after a purchase and successful close."""
    selection = SimpleNamespace(click_position=(0.25, 0.5))
    close = MagicMock(return_value=True)
    buy = MagicMock()
    context = SimpleNamespace(
        _has_chosen_fleet=False,
        _recognize_fleet_options_with_retry=MagicMock(
            return_value=(np.zeros((720, 1280, 3), dtype=np.uint8), 10, {'Ship': selection})
        ),
        _state=SimpleNamespace(
            score=10,
            ships=set(),
            phase=DecisivePhase.CHOOSE_FLEET,
            is_begin=lambda: False,
        ),
        _logic=SimpleNamespace(choose_ships=lambda _selections, first_node: ['Ship']),
        _map=SimpleNamespace(
            close_fleet_overlay=close,
            buy_fleet_option=buy,
            refresh_fleet=MagicMock(),
        ),
    )

    handlers.DecisivePhaseHandlers._handle_choose_fleet(context)

    assert context._has_chosen_fleet is True
    assert context._force_fleet_scan is False
    assert context._state.phase is DecisivePhase.PREPARE_COMBAT
    buy.assert_called_once_with(selection.click_position)
    close.assert_called_once_with()


def test_choose_fleet_without_purchase_defers_to_sufficiency_check() -> None:
    """An empty purchase decision closes and lets preparation judge sufficiency."""
    close = MagicMock(return_value=True)
    buy = MagicMock()
    context = SimpleNamespace(
        _has_chosen_fleet=False,
        _recognize_fleet_options_with_retry=MagicMock(
            return_value=(np.zeros((720, 1280, 3), dtype=np.uint8), 10, {})
        ),
        _state=SimpleNamespace(
            score=10,
            ships=set(),
            phase=DecisivePhase.CHOOSE_FLEET,
            is_begin=lambda: False,
        ),
        _logic=SimpleNamespace(choose_ships=MagicMock()),
        _map=SimpleNamespace(
            close_fleet_overlay=close,
            buy_fleet_option=buy,
            refresh_fleet=MagicMock(),
        ),
    )

    handlers.DecisivePhaseHandlers._handle_choose_fleet(context)

    assert context._has_chosen_fleet is True
    assert context._force_fleet_scan is True
    assert context._state.phase is DecisivePhase.PREPARE_COMBAT
    close.assert_called_once_with()
    buy.assert_not_called()


def test_choose_fleet_does_not_buy_unconfigured_card() -> None:
    """Unconfigured OCR cards are not valid substitutes for primary/backup ships."""
    selection = SimpleNamespace(name='Unconfigured', cost=1, click_position=(0.25, 0.5))
    close = MagicMock(return_value=True)
    buy = MagicMock()
    context = SimpleNamespace(
        _has_chosen_fleet=False,
        _recognize_fleet_options_with_retry=MagicMock(
            return_value=(np.zeros((720, 1280, 3), dtype=np.uint8), 10, {'Cheap': selection})
        ),
        _state=SimpleNamespace(
            score=10,
            ships=set(),
            phase=DecisivePhase.CHOOSE_FLEET,
            is_begin=lambda: False,
        ),
        _logic=SimpleNamespace(choose_ships=lambda _selections, first_node: []),
        _map=SimpleNamespace(
            close_fleet_overlay=close,
            buy_fleet_option=buy,
            refresh_fleet=MagicMock(),
        ),
    )

    handlers.DecisivePhaseHandlers._handle_choose_fleet(context)

    buy.assert_not_called()
    assert context._state.ships == set()
    assert context._force_fleet_scan is True
    assert context._state.phase is DecisivePhase.PREPARE_COMBAT
    close.assert_called_once_with()


def test_choose_fleet_falls_back_to_low_cost_ship_when_empty_close_fails() -> None:
    """An empty configured purchase selects one real ship, closes, then retreats."""
    ship = SimpleNamespace(name='Unconfigured', cost=4, click_position=(0.25, 0.5))
    skill = SimpleNamespace(name='长跑训练', cost=1, click_position=(0.375, 0.5))
    close = MagicMock(side_effect=[False, True])
    buy = MagicMock()
    context = SimpleNamespace(
        _has_chosen_fleet=False,
        _recognize_fleet_options_with_retry=MagicMock(
            return_value=(
                np.zeros((720, 1280, 3), dtype=np.uint8),
                10,
                {'Unconfigured': ship, '长跑训练': skill},
            )
        ),
        _state=SimpleNamespace(
            score=10,
            ships=set(),
            phase=DecisivePhase.CHOOSE_FLEET,
            is_begin=lambda: True,
        ),
        _logic=SimpleNamespace(choose_ships=lambda _selections, first_node: []),
        _map=SimpleNamespace(
            close_fleet_overlay=close,
            buy_fleet_option=buy,
            refresh_fleet=MagicMock(),
            detect_last_offer_name=MagicMock(return_value=None),
        ),
    )

    handlers.DecisivePhaseHandlers._handle_choose_fleet(context)

    buy.assert_called_once_with(ship.click_position)
    assert context._state.ships == {'Unconfigured'}
    assert context._state.phase is DecisivePhase.RETREAT
    assert close.call_count == 2


def test_close_fleet_overlay_waits_for_stable_map_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A confirmed title disappearance adds the broad post-close settle wait."""
    controller = object.__new__(map_controller.DecisiveMapController)
    controller._ctrl = MagicMock()
    controller._ctrl.screenshot.return_value = np.zeros((720, 1280, 3), dtype=np.uint8)
    monkeypatch.setattr(map_controller, 'is_fleet_acquisition', lambda _screen: False)
    monkeypatch.setattr(map_controller.time, 'monotonic', lambda: 0.0)
    sleeps: list[float] = []
    monkeypatch.setattr(map_controller.time, 'sleep', sleeps.append)

    assert controller.close_fleet_overlay() is True
    assert 1.5 in sleeps


def test_combat_success_clicks_result_page_before_node_poll(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful decisive combat dismisses the result page before polling."""
    result = SimpleNamespace(
        flag=handlers.ConditionFlag.OPERATION_SUCCESS,
        ship_stats=[],
    )
    context = SimpleNamespace(
        _ctx=SimpleNamespace(ctrl=MagicMock()),
        _ctrl=MagicMock(),
        _logic=SimpleNamespace(get_formation=lambda: 'single_column', is_key_point=lambda: False),
        _state=SimpleNamespace(node='A', stage=1, ship_stats=[]),
        _sync_ship_states=MagicMock(),
    )
    run_combat = MagicMock(return_value=result)
    click_result = MagicMock()
    sleeps: list[float] = []
    monkeypatch.setattr(handlers, 'run_combat', run_combat)
    monkeypatch.setattr(handlers, 'click_result', click_result)
    monkeypatch.setattr(handlers.time, 'sleep', sleeps.append)

    handlers.DecisivePhaseHandlers._handle_combat(context)

    click_result.assert_called_once_with(context._ctrl)
    assert context._state.phase is DecisivePhase.NODE_RESULT
    assert 0.3 in sleeps


def test_use_last_fleet_checks_fixed_roi_three_times(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The optional last-fleet stage settles, then performs three ROI checks."""
    controller = object.__new__(map_controller.DecisiveMapController)
    controller._ctrl = MagicMock()
    calls: list[tuple[object, float]] = []
    monkeypatch.setattr(
        map_controller.ImageChecker,
        'template_exists',
        lambda _screen, _template, *, roi, confidence: calls.append((roi, confidence)) or False,
    )
    events: list[float] = []
    monkeypatch.setattr(map_controller.time, 'sleep', events.append)

    assert controller._wait_for_use_last_fleet() is False
    assert calls == [(USE_LAST_FLEET_ROI, 0.8)] * 3
    assert events == [3.0, 0.2, 0.2, 0.2]


def test_reset_chapter_requires_recognized_reset_button(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reset opens confirmation only after its entry button is positively matched."""
    page = object.__new__(battle_page.DecisiveBattlePage)
    page._ctrl = MagicMock()
    match = SimpleNamespace(center=(0.75, 0.9))
    find_template = MagicMock(return_value=match)
    monkeypatch.setattr(
        battle_page.ImageChecker,
        'find_template',
        find_template,
    )
    monkeypatch.setattr(
        battle_page.ImageChecker,
        'template_exists',
        lambda *_args, **_kwargs: False,
    )
    confirm = MagicMock()
    monkeypatch.setattr(battle_page, 'confirm_operation', confirm)
    monkeypatch.setattr(battle_page.time, 'sleep', lambda _delay: None)

    assert page.reset_chapter() is True
    page._ctrl.click.assert_called_once_with(*match.center)
    assert find_template.call_args.kwargs['roi'] == battle_page.RESET_BUTTON_ROI
    confirm.assert_called_once_with(page._ctrl, must_confirm=True, timeout=5.0)


def test_reset_chapter_falls_back_to_refresh_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The completed-state reset button is the bottom-center entry template."""
    page = object.__new__(battle_page.DecisiveBattlePage)
    page._ctrl = MagicMock()
    match = SimpleNamespace(center=(0.53, 0.93))
    find_template = MagicMock(side_effect=[None, match])
    monkeypatch.setattr(battle_page.ImageChecker, 'find_template', find_template)
    monkeypatch.setattr(
        battle_page.ImageChecker,
        'template_exists',
        lambda *_args, **_kwargs: False,
    )
    confirm = MagicMock()
    monkeypatch.setattr(battle_page, 'confirm_operation', confirm)
    monkeypatch.setattr(battle_page.time, 'sleep', lambda _delay: None)

    assert page.reset_chapter() is True
    page._ctrl.click.assert_called_once_with(*match.center)
    assert find_template.call_args_list[1].kwargs['roi'] == battle_page.RESET_ENTRY_ROI
    confirm.assert_called_once_with(page._ctrl, must_confirm=True, timeout=5.0)


def test_reset_chapter_retries_entry_when_confirmation_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missed confirmation retries only after re-matching the reset entry."""
    page = object.__new__(battle_page.DecisiveBattlePage)
    page._ctrl = MagicMock()
    match = SimpleNamespace(center=(0.684, 0.932))
    monkeypatch.setattr(
        battle_page.ImageChecker,
        'find_template',
        MagicMock(side_effect=[match, match]),
    )
    monkeypatch.setattr(
        battle_page.ImageChecker,
        'template_exists',
        lambda *_args, **_kwargs: False,
    )
    confirm = MagicMock(side_effect=[battle_page.NavigationError('missing confirmation'), None])
    monkeypatch.setattr(battle_page, 'confirm_operation', confirm)
    monkeypatch.setattr(battle_page.time, 'sleep', lambda _delay: None)

    assert page.reset_chapter() is True
    assert page._ctrl.click.call_count == 2
    assert confirm.call_count == 2


def test_enter_formation_retries_after_fleet_name_miss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing decisive fleet title causes one map-back and formation retry."""
    controller = object.__new__(map_controller.DecisiveMapController)
    controller._ctrl = MagicMock()
    controller._wait_for_fleet_name = MagicMock(side_effect=[False, True])
    controller.go_to_map_page = MagicMock()
    clicks: list[object] = []
    monkeypatch.setattr(
        map_controller,
        'click_and_wait_for_page',
        lambda *_args, **_kwargs: clicks.append(True),
    )
    monkeypatch.setattr(
        map_controller.ImageChecker,
        'template_exists',
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(map_controller, 'is_decisive_map_page', lambda _screen: True)
    monkeypatch.setattr(map_controller.time, 'sleep', lambda _delay: None)

    controller.enter_formation()

    assert len(clicks) == 2
    controller.go_to_map_page.assert_called_once_with()


def test_enter_formation_refuses_unrecognized_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Formation must not click when the current page is not the decisive map."""
    controller = object.__new__(map_controller.DecisiveMapController)
    controller._ctrl = MagicMock()
    clicks: list[object] = []
    monkeypatch.setattr(
        map_controller,
        'click_and_wait_for_page',
        lambda *_args, **_kwargs: clicks.append(True),
    )
    monkeypatch.setattr(map_controller, 'is_decisive_map_page', lambda _screen: False)
    monkeypatch.setattr(map_controller.time, 'sleep', lambda _delay: None)

    with pytest.raises(TimeoutError, match='未识别到决战地图页'):
        controller.enter_formation()

    assert clicks == []


def test_decisive_preparation_go_back_uses_decisive_map_checker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Decisive preparation return waits for the decisive map recognizer."""
    page = object.__new__(preparation.DecisiveBattlePreparationPage)
    page._ctrl = MagicMock()
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        preparation,
        'click_and_wait_for_page',
        lambda ctrl, **kwargs: calls.append({'ctrl': ctrl, **kwargs}),
    )

    page.go_back()

    assert calls == [
        {
            'ctrl': page._ctrl,
            'click_coord': preparation.CLICK_BACK,
            'checker': preparation.is_decisive_map_page,
            'source': preparation.PageName.BATTLE_PREP,
            'target': preparation.PageName.MAP,
        }
    ]


def test_decisive_map_recognizer_uses_pixel_signature() -> None:
    """The decisive map recognizer accepts its existing pixel signature."""
    screen = np.zeros((720, 1280, 3), dtype=np.uint8)
    for rule in overlay.SIG_MAP_PAGE.rules:
        screen[int(rule.y * screen.shape[0]), int(rule.x * screen.shape[1])] = (
            rule.color.as_rgb_tuple()
        )

    assert overlay.is_decisive_map_page(screen)

    first_rule = overlay.SIG_MAP_PAGE.rules[0]
    screen[int(first_rule.y * screen.shape[0]), int(first_rule.x * screen.shape[1])] = 0
    assert not overlay.is_decisive_map_page(screen)


def test_fleet_name_checks_fixed_roi_three_times(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The decisive formation title uses three fixed-ROI template checks."""
    controller = object.__new__(map_controller.DecisiveMapController)
    controller._ctrl = MagicMock()
    calls: list[tuple[object, float]] = []
    monkeypatch.setattr(
        map_controller.ImageChecker,
        'template_exists',
        lambda _screen, _template, *, roi, confidence: calls.append((roi, confidence)) or False,
    )
    sleeps: list[float] = []
    monkeypatch.setattr(map_controller.time, 'sleep', sleeps.append)

    assert controller._wait_for_fleet_name() is False
    assert calls == [(FLEET_NAME_ROI, 0.8)] * 3
    assert sleeps == [0.2, 0.2, 0.2]


def test_select_advance_card_requires_recognized_overlay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Advance clicks are gated by a positive ADVANCE_CHOICE match."""
    controller = object.__new__(map_controller.DecisiveMapController)
    controller._ctrl = MagicMock()
    controller.wait_for_overlay = MagicMock()
    monkeypatch.setattr(map_controller.time, 'sleep', lambda _delay: None)

    controller.select_advance_card(0)

    controller.wait_for_overlay.assert_called_once_with(
        DecisiveOverlay.ADVANCE_CHOICE,
        timeout=5.0,
        interval=0.2,
    )
    assert controller._ctrl.click.call_args_list == [
        call(*ADVANCE_CARD_POSITIONS[0]),
        call(*CLICK_ADVANCE_CONFIRM),
    ]


def test_use_last_fleet_refuses_unrecognized_click(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The use-last-fleet path must fail closed when its template is absent."""
    controller = object.__new__(map_controller.DecisiveMapController)
    controller._ctrl = MagicMock()
    clock = iter((0.0, 6.0))
    monkeypatch.setattr(map_controller.time, 'monotonic', lambda: next(clock))

    with pytest.raises(TimeoutError, match='未识别到'):
        controller.click_use_last_fleet()

    controller._ctrl.click.assert_not_called()


def test_check_fleet_skips_ship_pool_when_current_formation_has_ships(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-empty formation is checked without opening the ship pool."""
    fleet = ['U-47', None, None, None, None, None]
    page = MagicMock()
    page.detect_fleet.return_value = fleet
    page.detect_ship_damage.return_value = {}
    controller = object.__new__(map_controller.DecisiveMapController)
    controller._ctx = object()
    controller._config = object()
    controller._ocr = object()
    controller._ctrl = MagicMock()
    controller._ctrl.screenshot.return_value = np.zeros((720, 1280, 3), dtype=np.uint8)
    controller.enter_formation = MagicMock()

    monkeypatch.setattr(
        map_controller,
        'DecisiveBattlePreparationPage',
        lambda *_args: page,
    )
    monkeypatch.setattr(map_controller.time, 'sleep', lambda _delay: None)
    recognize = MagicMock()
    monkeypatch.setattr(map_controller, '_recognize_ships', recognize)

    result = controller.check_fleet()

    assert result == (fleet, {}, {'U-47'})
    controller.enter_formation.assert_called_once_with()
    page.click_ship_slot.assert_not_called()
    page.go_back.assert_not_called()
    recognize.assert_not_called()


def test_check_fleet_forces_ship_pool_scan_for_full_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Full recovery rebuilds the ship context even with a non-empty formation."""
    fleet = ['U-47', None, None, None, None, None]
    page = MagicMock()
    page.detect_fleet.return_value = fleet
    page.detect_ship_damage.return_value = {}
    controller = object.__new__(map_controller.DecisiveMapController)
    controller._ctx = object()
    controller._config = object()
    controller._ocr = object()
    controller._ctrl = MagicMock()
    screen = np.zeros((720, 1280, 3), dtype=np.uint8)
    controller._ctrl.screenshot.side_effect = [screen, screen, screen]
    controller.enter_formation = MagicMock()

    monkeypatch.setattr(
        map_controller,
        'DecisiveBattlePreparationPage',
        lambda *_args: page,
    )
    monkeypatch.setattr(
        map_controller.BattlePreparationPage,
        'is_current_page',
        lambda _screen: False,
    )
    monkeypatch.setattr(map_controller.time, 'sleep', lambda _delay: None)
    recognize = MagicMock(return_value={'U-1206'})
    monkeypatch.setattr(map_controller, '_recognize_ships', recognize)

    result = controller.check_fleet(scan_ship_pool=True)

    assert result == (fleet, {}, {'U-47', 'U-1206'})
    page.click_ship_slot.assert_called_once_with(0)
    recognize.assert_called_once()
    page.go_back.assert_not_called()


def test_advance_choice_waits_for_next_recognized_phase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After choosing a card, the next phase comes from fresh screen recognition."""
    context = SimpleNamespace(
        _logic=SimpleNamespace(),
        _map=SimpleNamespace(select_advance_card=MagicMock()),
        _state=SimpleNamespace(phase=DecisivePhase.ADVANCE_CHOICE),
        _advance_choice_roi=lambda: None,
        _wait_deadline=0.0,
    )
    monkeypatch.setattr(handlers.time, 'monotonic', lambda: 100.0)

    handlers.DecisivePhaseHandlers._handle_advance_choice(context)

    context._map.select_advance_card.assert_called_once_with(0)
    assert context._state.phase is DecisivePhase.WAITING_FOR_MAP
    assert context._wait_deadline == 110.0
