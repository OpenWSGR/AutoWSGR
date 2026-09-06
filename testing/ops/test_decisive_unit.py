"""Focused tests for decisive map-entry timing."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from autowsgr.ops.decisive import handlers
from autowsgr.types import DecisiveEntryStatus, DecisivePhase


if TYPE_CHECKING:
    import pytest


def test_enter_map_waits_after_click_before_first_detection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first map screenshot is delayed until the entry animation settles."""
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

    assert events == ['enter', ('sleep', 2.0)]
    assert battle_page_context._state.phase is DecisivePhase.WAITING_FOR_MAP
