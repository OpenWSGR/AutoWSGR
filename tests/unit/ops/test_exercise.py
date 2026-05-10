"""测试 autowsgr.ops.exercise。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from autowsgr.ops.exercise import ExerciseRunner, run_exercise


class TestExerciseRunner:
    """ExerciseRunner 初始化测试。"""

    def test_init_defaults(self) -> None:
        ctx = MagicMock()
        runner = ExerciseRunner(ctx)
        assert runner._fleet_id == 1
        assert runner._results == []

    def test_init_custom_fleet(self) -> None:
        ctx = MagicMock()
        runner = ExerciseRunner(ctx, fleet_id=2)
        assert runner._fleet_id == 2


class TestRunExercise:
    """run_exercise 便捷函数测试。"""

    @patch('autowsgr.ops.exercise.ExerciseRunner')
    def test_run_all(self, mock_runner_cls: MagicMock) -> None:
        ctx = MagicMock()
        mock_runner = mock_runner_cls.return_value
        mock_runner.run.return_value = ['result1', 'result2']

        result = run_exercise(ctx, rival=None)

        mock_runner_cls.assert_called_once_with(ctx, 1)
        mock_runner.run.assert_called_once()
        assert result == ['result1', 'result2']

    @patch('autowsgr.ops.exercise.ExerciseRunner')
    def test_run_specific_rival(self, mock_runner_cls: MagicMock) -> None:
        ctx = MagicMock()
        mock_runner = mock_runner_cls.return_value
        mock_runner._challenge_rival.return_value = 'result1'

        result = run_exercise(ctx, fleet_id=2, rival=3)

        mock_runner_cls.assert_called_once_with(ctx, 2)
        mock_runner._challenge_rival.assert_called_once_with(3)
        assert result == ['result1']
