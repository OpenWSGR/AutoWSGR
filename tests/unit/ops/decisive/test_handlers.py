"""测试 autowsgr.ops.decisive.handlers。"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from autowsgr.ops.decisive.handlers import DecisivePhaseHandlers
from autowsgr.ops.decisive.state import DecisiveState
from autowsgr.types import FleetSelection, ShipDamageState


class _TestableHandlers(DecisivePhaseHandlers):
    """绕过 DecisiveBase.__init__ 的可测试子类。"""

    def __init__(self) -> None:
        pass


@pytest.fixture
def handler() -> _TestableHandlers:
    """返回已注入 mock 依赖的 _TestableHandlers 实例。"""
    h = _TestableHandlers()
    h._map = MagicMock()
    h._ctx = MagicMock()
    h._state = DecisiveState()
    return h


# ═══════════════════════════════════════════════════════════════════════════════
# _sync_ship_states
# ═══════════════════════════════════════════════════════════════════════════════


class TestSyncShipStates:
    """_sync_ship_states 测试。"""

    def test_normal_case_skips_no_ship(self, handler: _TestableHandlers) -> None:
        handler._state.ship_stats = [
            ShipDamageState.NORMAL,
            ShipDamageState.MODERATE,
            ShipDamageState.NO_SHIP,
            ShipDamageState.SEVERE,
            ShipDamageState.NORMAL,
            ShipDamageState.NO_SHIP,
        ]
        handler._state.fleet = ['', 'A', 'B', 'C', 'D', 'E', 'F']
        handler._sync_ship_states()
        assert handler._ctx.update_ship_damage.call_count == 4
        handler._ctx.update_ship_damage.assert_any_call('A', ShipDamageState.NORMAL)
        handler._ctx.update_ship_damage.assert_any_call('B', ShipDamageState.MODERATE)
        handler._ctx.update_ship_damage.assert_any_call('D', ShipDamageState.SEVERE)
        handler._ctx.update_ship_damage.assert_any_call('E', ShipDamageState.NORMAL)

    def test_empty_fleet_no_calls(self, handler: _TestableHandlers) -> None:
        handler._state.ship_stats = [ShipDamageState.NORMAL] * 6
        handler._state.fleet = [''] * 7
        handler._sync_ship_states()
        handler._ctx.update_ship_damage.assert_not_called()

    def test_partial_fleet_only_valid_entries(self, handler: _TestableHandlers) -> None:
        handler._state.ship_stats = [
            ShipDamageState.NORMAL,
            ShipDamageState.MODERATE,
            ShipDamageState.SEVERE,
            ShipDamageState.NORMAL,
            ShipDamageState.NORMAL,
            ShipDamageState.NORMAL,
        ]
        handler._state.fleet = ['', 'X', 'Y', '', '', '', '']
        handler._sync_ship_states()
        assert handler._ctx.update_ship_damage.call_count == 2
        handler._ctx.update_ship_damage.assert_any_call('X', ShipDamageState.NORMAL)
        handler._ctx.update_ship_damage.assert_any_call('Y', ShipDamageState.MODERATE)


# ═══════════════════════════════════════════════════════════════════════════════
# _recognize_fleet_options_with_retry
# ═══════════════════════════════════════════════════════════════════════════════


class TestRecognizeFleetOptionsWithRetry:
    """_recognize_fleet_options_with_retry 测试。"""

    def _make_screen(self) -> np.ndarray:
        return np.zeros((10, 10, 3), dtype=np.uint8)

    def test_first_attempt_success(self, handler: _TestableHandlers) -> None:
        screen = self._make_screen()
        handler._map.wait_for_fleet_overlay_stable.return_value = screen
        selection = FleetSelection('A', 3, (0.0, 0.0))
        handler._map.recognize_fleet_options.return_value = (5, {'A': selection})

        result = handler._recognize_fleet_options_with_retry(fallback_score=10)

        assert result == (screen, 5, {'A': selection})
        handler._map.wait_for_fleet_overlay_stable.assert_called_once()
        handler._map.recognize_fleet_options.assert_called_once_with(
            screen,
            fallback_score=10,
        )

    def test_second_attempt_success(self, handler: _TestableHandlers) -> None:
        screen0 = self._make_screen()
        screen1 = self._make_screen() + 1
        handler._map.wait_for_fleet_overlay_stable.side_effect = [screen0, screen1]
        selection = FleetSelection('B', 4, (0.0, 0.0))
        handler._map.recognize_fleet_options.side_effect = [
            (0, {}),
            (7, {'B': selection}),
        ]
        handler._map.is_fleet_overlay_open.return_value = True

        result = handler._recognize_fleet_options_with_retry(fallback_score=10)

        assert result == (screen1, 7, {'B': selection})
        assert handler._map.wait_for_fleet_overlay_stable.call_count == 2
        assert handler._map.recognize_fleet_options.call_count == 2

    def test_all_attempts_empty_returns_fallback(self, handler: _TestableHandlers) -> None:
        screens = [self._make_screen() + i for i in range(3)]
        handler._map.wait_for_fleet_overlay_stable.side_effect = screens
        handler._map.recognize_fleet_options.return_value = (0, {})
        handler._map.is_fleet_overlay_open.return_value = True

        result = handler._recognize_fleet_options_with_retry(fallback_score=15)

        assert result[0] is screens[-1]
        assert result[1] == 15
        assert result[2] == {}
        assert handler._map.wait_for_fleet_overlay_stable.call_count == 3
        assert handler._map.recognize_fleet_options.call_count == 3

    def test_interface_closes_during_retry_raises(self, handler: _TestableHandlers) -> None:
        screen = self._make_screen()
        handler._map.wait_for_fleet_overlay_stable.return_value = screen
        handler._map.recognize_fleet_options.return_value = (0, {})
        handler._map.is_fleet_overlay_open.return_value = False

        with pytest.raises(RuntimeError, match='战备舰队界面已关闭'):
            handler._recognize_fleet_options_with_retry(fallback_score=10)

        handler._map.wait_for_fleet_overlay_stable.assert_called_once()
        handler._map.is_fleet_overlay_open.assert_called_once()
