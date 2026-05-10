"""测试 autowsgr.ops.decisive.controller。"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from autowsgr.ops.decisive.base import DecisiveBase
from autowsgr.ops.decisive.controller import DecisiveController, DecisiveResult
from autowsgr.ops.decisive.state import DecisiveState
from autowsgr.types import DecisivePhase


if TYPE_CHECKING:
    from unittest.mock import MagicMock as _MagicMock


class TestDecisiveResult:
    """DecisiveResult 枚举测试。"""

    def test_enum_values(self) -> None:
        assert DecisiveResult.CHAPTER_CLEAR.value == 'chapter_clear'
        assert DecisiveResult.RETREAT.value == 'retreat'
        assert DecisiveResult.LEAVE.value == 'leave'
        assert DecisiveResult.ERROR.value == 'error'


class TestDecisiveControllerRun:
    """DecisiveController.run() 测试。"""

    def _make_controller(self) -> DecisiveController:
        with patch.object(DecisiveBase, '__init__', lambda _self, _ctx, _config: None):
            ctrl = DecisiveController(MagicMock(), MagicMock())
            ctrl._state = DecisiveState(chapter=2)
            ctrl._config = MagicMock()
            ctrl._config.chapter = 2
            return ctrl

    def test_run_success(self) -> None:
        ctrl = self._make_controller()
        object.__setattr__(ctrl, '_prepare_entry_state', MagicMock())
        object.__setattr__(ctrl, '_main_loop', MagicMock(return_value=DecisiveResult.CHAPTER_CLEAR))

        result = ctrl.run()

        assert result == DecisiveResult.CHAPTER_CLEAR
        assert ctrl._state.phase == DecisivePhase.ENTER_MAP
        assert ctrl._state.chapter == 2
        assert ctrl._state.stage == 0
        assert ctrl._state.node == 'U'
        assert ctrl._resume_mode is True
        assert ctrl._has_chosen_fleet is False
        ctrl._prepare_entry_state.assert_called_once()
        ctrl._main_loop.assert_called_once()

    def test_run_exception(self) -> None:
        ctrl = self._make_controller()
        object.__setattr__(ctrl, '_prepare_entry_state', MagicMock())
        object.__setattr__(ctrl, '_main_loop', MagicMock(side_effect=RuntimeError('boom')))

        result = ctrl.run()

        assert result == DecisiveResult.ERROR
        assert ctrl._state.phase == DecisivePhase.FINISHED
        ctrl._main_loop.assert_called_once()


class TestDecisiveControllerRunForTimes:
    """DecisiveController.run_for_times() 测试。"""

    def _make_controller(self) -> DecisiveController:
        with patch.object(DecisiveBase, '__init__', lambda _self, _ctx, _config: None):
            ctrl = DecisiveController(MagicMock(), MagicMock())
            ctrl._state = DecisiveState(chapter=1)
            ctrl._config = MagicMock()
            return ctrl

    def test_run_for_times(self) -> None:
        ctrl = self._make_controller()
        object.__setattr__(
            ctrl,
            'run',
            MagicMock(
                side_effect=[
                    DecisiveResult.CHAPTER_CLEAR,
                    DecisiveResult.CHAPTER_CLEAR,
                ]
            ),
        )

        results = ctrl.run_for_times(2)

        assert len(results) == 2
        assert results == [DecisiveResult.CHAPTER_CLEAR, DecisiveResult.CHAPTER_CLEAR]
        assert ctrl.run.call_count == 2

    def test_run_for_times_breaks_on_leave(self) -> None:
        ctrl = self._make_controller()
        object.__setattr__(
            ctrl,
            'run',
            MagicMock(
                side_effect=[
                    DecisiveResult.CHAPTER_CLEAR,
                    DecisiveResult.LEAVE,
                    DecisiveResult.CHAPTER_CLEAR,
                ]
            ),
        )

        results = ctrl.run_for_times(3)

        assert len(results) == 2
        assert results == [DecisiveResult.CHAPTER_CLEAR, DecisiveResult.LEAVE]
        assert ctrl.run.call_count == 2

    def test_run_for_times_breaks_on_error(self) -> None:
        ctrl = self._make_controller()
        object.__setattr__(
            ctrl,
            'run',
            MagicMock(
                side_effect=[
                    DecisiveResult.CHAPTER_CLEAR,
                    DecisiveResult.ERROR,
                ]
            ),
        )

        results = ctrl.run_for_times(3)

        assert len(results) == 2
        assert results == [DecisiveResult.CHAPTER_CLEAR, DecisiveResult.ERROR]
        assert ctrl.run.call_count == 2


class _TestableController(DecisiveController):
    """用于测试 _main_loop 的可控子类。"""

    def __init__(self, state: DecisiveState) -> None:
        self._state = state
        self._config = MagicMock()
        self._execute_retreat: _MagicMock = MagicMock()
        self._execute_leave: _MagicMock = MagicMock()
        self._handle_enter_map: _MagicMock = MagicMock()
        self._handle_waiting_for_map: _MagicMock = MagicMock()
        self._handle_use_last_fleet: _MagicMock = MagicMock()
        self._handle_dock_full: _MagicMock = MagicMock()
        self._handle_choose_fleet: _MagicMock = MagicMock()
        self._handle_advance_choice: _MagicMock = MagicMock()
        self._handle_prepare_combat: _MagicMock = MagicMock()
        self._handle_combat: _MagicMock = MagicMock()
        self._handle_node_result: _MagicMock = MagicMock()
        self._handle_stage_clear: _MagicMock = MagicMock()


class TestDecisiveControllerMainLoop:
    """DecisiveController._main_loop() 测试。"""

    def test_chapter_clear(self) -> None:
        state = DecisiveState()
        state.phase = DecisivePhase.CHAPTER_CLEAR
        ctrl = _TestableController(state)

        result = ctrl._main_loop()

        assert result == DecisiveResult.CHAPTER_CLEAR
        assert state.phase == DecisivePhase.FINISHED
        ctrl._execute_retreat.assert_not_called()
        ctrl._execute_leave.assert_not_called()
        ctrl._handle_enter_map.assert_not_called()

    def test_retreat(self) -> None:
        state = DecisiveState(chapter=3)
        state.stage = 2
        state.node = 'C'
        state.phase = DecisivePhase.RETREAT
        ctrl = _TestableController(state)
        object.__setattr__(
            ctrl,
            '_handle_enter_map',
            MagicMock(
                side_effect=lambda: setattr(
                    state,
                    'phase',
                    DecisivePhase.FINISHED,
                )
            ),
        )

        result = ctrl._main_loop()

        assert result == DecisiveResult.CHAPTER_CLEAR
        ctrl._execute_retreat.assert_called_once()
        assert state.stage == 0
        assert state.node == 'U'
        assert state.chapter == 3
        ctrl._handle_enter_map.assert_called_once()

    def test_leave(self) -> None:
        state = DecisiveState()
        state.phase = DecisivePhase.LEAVE
        ctrl = _TestableController(state)

        result = ctrl._main_loop()

        assert result == DecisiveResult.LEAVE
        assert state.phase == DecisivePhase.FINISHED
        ctrl._execute_leave.assert_called_once()
        ctrl._execute_retreat.assert_not_called()

    def test_unknown_phase(self) -> None:
        state = DecisiveState()
        state.phase = DecisivePhase.INIT
        ctrl = _TestableController(state)

        result = ctrl._main_loop()

        assert result == DecisiveResult.ERROR
        assert state.phase == DecisivePhase.FINISHED
        ctrl._execute_leave.assert_not_called()
        ctrl._execute_retreat.assert_not_called()
        ctrl._handle_enter_map.assert_not_called()

    def test_known_handler_phase(self) -> None:
        state = DecisiveState()
        state.phase = DecisivePhase.ENTER_MAP
        ctrl = _TestableController(state)
        object.__setattr__(
            ctrl,
            '_handle_enter_map',
            MagicMock(
                side_effect=lambda: setattr(
                    state,
                    'phase',
                    DecisivePhase.FINISHED,
                )
            ),
        )

        result = ctrl._main_loop()

        assert result == DecisiveResult.CHAPTER_CLEAR
        ctrl._handle_enter_map.assert_called_once()
        ctrl._execute_leave.assert_not_called()
        ctrl._execute_retreat.assert_not_called()
