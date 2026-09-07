"""Focused tests for decisive map-entry timing."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, call

import numpy as np
import pytest

from autowsgr.image_resources import Templates
from autowsgr.ops.decisive import handlers
from autowsgr.types import DecisiveEntryStatus, DecisivePhase
from autowsgr.ui.decisive import battle_page, map_controller
from autowsgr.ui.decisive.overlay import (
    ADVANCE_CARD_POSITIONS,
    CLICK_ADVANCE_CONFIRM,
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
        _use_last_fleet_attempts=0,
        _skip_advance_choice=False,
        _wait_deadline=101.0,
    )
    monkeypatch.setattr(handlers.time, 'monotonic', lambda: 100.0)
    events: list[float] = []
    monkeypatch.setattr(handlers.time, 'sleep', events.append)

    handlers.DecisivePhaseHandlers._handle_waiting_for_map(context)

    map_controller_mock.wait_for_entry_phase.assert_called_once_with(
        wait_for_use_last=True,
        wait_for_advance=True,
        timeout=3.0,
        interval=0.2,
    )
    assert context._state.phase is DecisivePhase.PREPARE_COMBAT
    assert events == [0.05]


def test_entry_phase_checks_overlays_before_map_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Entry recognition checks both optional overlays before accepting the map page."""
    controller = object.__new__(map_controller.DecisiveMapController)
    controller._ctrl = MagicMock()
    controller._wait_for_use_last_fleet = MagicMock(return_value=False)
    controller._wait_for_template = MagicMock(side_effect=[False, False])
    monkeypatch.setattr(map_controller, 'is_fleet_acquisition', lambda _screen: False)
    monkeypatch.setattr(map_controller, 'is_decisive_map_page', lambda _screen: True)

    phase = controller.wait_for_entry_phase(
        wait_for_use_last=True,
        wait_for_advance=True,
        timeout=3.0,
        interval=0.2,
    )

    assert phase is DecisivePhase.PREPARE_COMBAT
    controller._wait_for_template.assert_has_calls(
        [
            call(Templates.Decisive.ADVANCE_CHOICE, timeout=3.0, interval=0.2),
        ]
    )


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


def test_advance_choice_waits_for_next_recognized_phase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After choosing a card, the next phase comes from fresh screen recognition."""
    context = SimpleNamespace(
        _logic=SimpleNamespace(get_advance_choice=lambda _options: 0),
        _map=SimpleNamespace(select_advance_card=MagicMock()),
        _state=SimpleNamespace(phase=DecisivePhase.ADVANCE_CHOICE),
        _wait_deadline=0.0,
    )
    monkeypatch.setattr(handlers.time, 'monotonic', lambda: 100.0)

    handlers.DecisivePhaseHandlers._handle_advance_choice(context)

    context._map.select_advance_card.assert_called_once_with(0)
    assert context._state.phase is DecisivePhase.WAITING_FOR_MAP
    assert context._wait_deadline == 110.0
