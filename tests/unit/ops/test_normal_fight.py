"""测试 autowsgr.ops.normal_fight。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from autowsgr.combat import CombatMode, CombatPlan, CombatResult
from autowsgr.combat.history import FightResult
from autowsgr.ops.normal_fight import (
    NormalFightRunner,
    get_normal_fight_plan,
    run_normal_fight,
    run_normal_fight_from_yaml,
)
from autowsgr.types import ConditionFlag


class TestNormalFightRunnerInit:
    """NormalFightRunner.__init__ 测试。"""

    def _make_ctx(self) -> MagicMock:
        ctx = MagicMock()
        ctx.config.dock_full_destroy = False
        ctx.config.destroy_ship_types = None
        return ctx

    def test_mode_correction(self) -> None:
        """plan.mode 非 NORMAL 时警告并修正。"""
        ctx = self._make_ctx()
        plan = CombatPlan(mode=CombatMode.BATTLE, fleet_id=1)

        with patch('autowsgr.ops.normal_fight._log.warning') as mock_warn:
            runner = NormalFightRunner(ctx, plan)

        mock_warn.assert_called_once()
        assert plan.mode == CombatMode.NORMAL
        assert runner._plan is plan

    def test_mode_no_correction(self) -> None:
        """plan.mode 已经是 NORMAL 时不修正。"""
        ctx = self._make_ctx()
        plan = CombatPlan(mode=CombatMode.NORMAL, fleet_id=1)

        with patch('autowsgr.ops.normal_fight._log.warning') as mock_warn:
            runner = NormalFightRunner(ctx, plan)

        mock_warn.assert_not_called()
        assert runner._plan is plan

    def test_fleet_id_fallback(self) -> None:
        """fleet_id 默认从 plan.fleet_id 回退。"""
        ctx = self._make_ctx()
        plan = CombatPlan(fleet_id=3)
        runner = NormalFightRunner(ctx, plan)
        assert runner._fleet_id == 3

    def test_fleet_id_override(self) -> None:
        """显式传入 fleet_id 覆盖 plan.fleet_id。"""
        ctx = self._make_ctx()
        plan = CombatPlan(fleet_id=3)
        runner = NormalFightRunner(ctx, plan, fleet_id=5)
        assert runner._fleet_id == 5

    def test_fleet_fallback(self) -> None:
        """fleet 默认从 plan.fleet 回退。"""
        ctx = self._make_ctx()
        plan = CombatPlan(fleet=['ship1', 'ship2'])
        runner = NormalFightRunner(ctx, plan)
        assert runner._fleet == ['ship1', 'ship2']

    def test_fleet_override(self) -> None:
        """显式传入 fleet 覆盖 plan.fleet。"""
        ctx = self._make_ctx()
        plan = CombatPlan(fleet=['ship1', 'ship2'])
        runner = NormalFightRunner(ctx, plan, fleet=['ship3'])
        assert runner._fleet == ['ship3']

    def test_fleet_rules_set(self) -> None:
        """fleet_rules 被正确设置。"""
        ctx = self._make_ctx()
        plan = CombatPlan()
        rules = [{'candidates': ['A', 'B']}]
        runner = NormalFightRunner(ctx, plan, fleet_rules=rules)
        assert runner._fleet_rules is rules

    def test_dock_full_destroy_from_config(self) -> None:
        """从 ctx.config 读取 dock_full_destroy 和 destroy_ship_types。"""
        ctx = self._make_ctx()
        ctx.config.dock_full_destroy = True
        ctx.config.destroy_ship_types = ['DD', 'CL']
        plan = CombatPlan()
        runner = NormalFightRunner(ctx, plan)
        assert runner._dock_full_destroy is True
        assert runner._destroy_ship_types == ['DD', 'CL']


class TestPrimaryNamesFromRules:
    """_primary_names_from_rules 静态方法测试。"""

    def test_none_returns_none(self) -> None:
        assert NormalFightRunner._primary_names_from_rules(None) is None

    def test_empty_returns_none(self) -> None:
        assert NormalFightRunner._primary_names_from_rules([]) is None

    def test_list_of_strings(self) -> None:
        rules = ['ShipA', '  ShipB  ', 'ShipC']
        result = NormalFightRunner._primary_names_from_rules(rules)
        assert result == ['ShipA', 'ShipB', 'ShipC']

    def test_dict_with_candidates(self) -> None:
        rules = [{'candidates': ['First', 'Second']}, {'candidates': ['Only']}]
        result = NormalFightRunner._primary_names_from_rules(rules)
        assert result == ['First', 'Only']

    def test_object_with_candidates(self) -> None:
        class Rule:
            def __init__(self, candidates: list[str]) -> None:
                self.candidates = candidates

        rules = [Rule(['ObjA', 'ObjB']), Rule(['ObjC'])]
        result = NormalFightRunner._primary_names_from_rules(rules)
        assert result == ['ObjA', 'ObjC']

    def test_more_than_6_slots_ignored(self) -> None:
        rules = [f'ship{i}' for i in range(10)]
        result = NormalFightRunner._primary_names_from_rules(rules)
        assert result is not None
        assert len(result) == 6
        assert result == [f'ship{i}' for i in range(6)]

    def test_empty_string_returns_none(self) -> None:
        rules = ['', '  ', 'ShipA']
        result = NormalFightRunner._primary_names_from_rules(rules)
        assert result == [None, None, 'ShipA']

    def test_mixed_types(self) -> None:
        class Rule:
            def __init__(self, candidates: list[str]) -> None:
                self.candidates = candidates

        rules = ['ShipA', {'candidates': ['DictA']}, Rule(['ObjA']), '']
        result = NormalFightRunner._primary_names_from_rules(rules)
        assert result == ['ShipA', 'DictA', 'ObjA', None]


class TestRunForTimes:
    """run_for_times 测试。"""

    def _make_runner(self) -> NormalFightRunner:
        ctx = MagicMock()
        ctx.config.dock_full_destroy = False
        ctx.config.destroy_ship_types = None
        plan = CombatPlan()
        return NormalFightRunner(ctx, plan)

    @patch('autowsgr.ops.normal_fight.time.sleep')
    def test_loop_count(self, mock_sleep: MagicMock) -> None:
        """正常循环指定次数。"""
        runner = self._make_runner()
        with patch.object(runner, 'run') as mock_run:
            mock_run.return_value = CombatResult(flag=ConditionFlag.OPERATION_SUCCESS)
            results = runner.run_for_times(3)

        assert len(results) == 3
        assert mock_run.call_count == 3
        mock_sleep.assert_not_called()

    @patch('autowsgr.ops.normal_fight.time.sleep')
    def test_gap_sleep(self, mock_sleep: MagicMock) -> None:
        """gap 大于 0 时在非最后一次循环后 sleep。"""
        runner = self._make_runner()
        with patch.object(runner, 'run') as mock_run:
            mock_run.return_value = CombatResult(flag=ConditionFlag.OPERATION_SUCCESS)
            runner.run_for_times(3, gap=1.5)

        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(1.5)

    @patch('autowsgr.ops.normal_fight.time.sleep')
    def test_dock_full_break(self, mock_sleep: MagicMock) -> None:
        """DOCK_FULL 时提前终止循环。"""
        runner = self._make_runner()
        with patch.object(runner, 'run') as mock_run:
            mock_run.side_effect = [
                CombatResult(flag=ConditionFlag.OPERATION_SUCCESS),
                CombatResult(flag=ConditionFlag.DOCK_FULL),
                CombatResult(flag=ConditionFlag.OPERATION_SUCCESS),
            ]
            results = runner.run_for_times(3)

        assert len(results) == 2
        assert mock_run.call_count == 2
        mock_sleep.assert_not_called()


class TestRunForTimesCondition:
    """run_for_times_condition 测试。"""

    def _make_runner(self) -> NormalFightRunner:
        ctx = MagicMock()
        ctx.config.dock_full_destroy = False
        ctx.config.destroy_ship_types = None
        plan = CombatPlan()
        return NormalFightRunner(ctx, plan)

    def test_invalid_result_raises(self) -> None:
        """非法 result 参数抛出 ValueError。"""
        runner = self._make_runner()
        with pytest.raises(ValueError, match='战果要求'):
            runner.run_for_times_condition(1, 'A', result='X')

    def test_invalid_last_point_raises(self) -> None:
        """非法 last_point 参数抛出 ValueError。"""
        runner = self._make_runner()
        with pytest.raises(ValueError, match='最后一个节点'):
            runner.run_for_times_condition(1, 'AB')
        with pytest.raises(ValueError, match='最后一个节点'):
            runner.run_for_times_condition(1, '1')

    @patch('autowsgr.ops.normal_fight.time.time')
    def test_condition_met_decrements_times(self, mock_time: MagicMock) -> None:
        """满足条件时 times 递减。"""
        runner = self._make_runner()
        mock_time.side_effect = [0.0, 1.0, 2.0, 3.0]

        result = CombatResult(flag=ConditionFlag.OPERATION_SUCCESS)
        result.history.events = []
        # Inject fight_results via history
        fr = FightResult(node='A', grade='S')
        with (
            patch.object(result.history, 'get_fight_results_list', return_value=[fr]),
            patch.object(runner, 'run', return_value=result),
        ):
            results = runner.run_for_times_condition(2, 'A', result='S')

        assert isinstance(results, list)
        assert len(results) == 2

    @patch('autowsgr.ops.normal_fight.time.time')
    def test_condition_not_met_no_decrement(self, mock_time: MagicMock) -> None:
        """不满足条件时 times 不减, 超时时返回 False。"""
        runner = self._make_runner()
        mock_time.side_effect = [0.0, 1.0, 2.0, 15.0]

        result = CombatResult(flag=ConditionFlag.OPERATION_SUCCESS)
        fr = FightResult(node='B', grade='A')
        with (
            patch.object(result.history, 'get_fight_results_list', return_value=[fr]),
            patch.object(runner, 'run', return_value=result),
        ):
            results = runner.run_for_times_condition(1, 'A', result='S', insist_time=10.0)

        assert results is False

    @patch('autowsgr.ops.normal_fight.time.time')
    def test_timeout_returns_false(self, mock_time: MagicMock) -> None:
        """超时返回 False。"""
        runner = self._make_runner()
        mock_time.side_effect = [0.0, 100.0, 200.0]

        result = CombatResult(flag=ConditionFlag.OPERATION_SUCCESS)
        fr = FightResult(node='B', grade='A')
        with (
            patch.object(result.history, 'get_fight_results_list', return_value=[fr]),
            patch.object(runner, 'run', return_value=result),
        ):
            results = runner.run_for_times_condition(1, 'A', result='S', insist_time=50.0)

        assert results is False

    @patch('autowsgr.ops.normal_fight.time.time')
    def test_dock_full_returns_early(self, mock_time: MagicMock) -> None:
        """DOCK_FULL 时提前返回已收集结果。"""
        runner = self._make_runner()
        mock_time.side_effect = [0.0, 1.0]

        result = CombatResult(flag=ConditionFlag.DOCK_FULL)
        with patch.object(runner, 'run', return_value=result):
            results = runner.run_for_times_condition(1, 'A')

        assert isinstance(results, list)
        assert len(results) == 1


class TestGetNormalFightPlan:
    """get_normal_fight_plan 测试。"""

    @patch('autowsgr.infra.file_utils.resolve_plan_path')
    @patch('autowsgr.combat.plan.CombatPlan.from_yaml')
    def test_load_plan(self, mock_from_yaml: MagicMock, mock_resolve: MagicMock) -> None:
        mock_resolve.return_value = '/resolved/path.yaml'
        mock_plan = MagicMock()
        mock_from_yaml.return_value = mock_plan

        result = get_normal_fight_plan('some_plan')

        mock_resolve.assert_called_once_with('some_plan', category='normal_fight')
        mock_from_yaml.assert_called_once_with('/resolved/path.yaml')
        assert result is mock_plan


class TestRunNormalFight:
    """run_normal_fight 与 run_normal_fight_from_yaml 测试。"""

    @patch('autowsgr.ops.normal_fight.NormalFightRunner')
    def test_run_normal_fight(self, mock_runner_cls: MagicMock) -> None:
        ctx = MagicMock()
        plan = MagicMock()
        mock_runner = mock_runner_cls.return_value
        mock_runner.run_for_times.return_value = ['result1', 'result2']

        results = run_normal_fight(ctx, plan, times=2, gap=1.0, fleet_id=2)

        mock_runner_cls.assert_called_once_with(
            ctx,
            plan,
            fleet_id=2,
            fleet=None,
            fleet_rules=None,
        )
        mock_runner.run_for_times.assert_called_once_with(2, gap=1.0)
        assert results == ['result1', 'result2']

    @patch('autowsgr.ops.normal_fight.get_normal_fight_plan')
    @patch('autowsgr.ops.normal_fight.NormalFightRunner')
    def test_run_normal_fight_from_yaml(
        self,
        mock_runner_cls: MagicMock,
        mock_get_plan: MagicMock,
    ) -> None:
        ctx = MagicMock()
        mock_plan = MagicMock()
        mock_get_plan.return_value = mock_plan
        mock_runner = mock_runner_cls.return_value
        mock_runner.run_for_times.return_value = ['result']

        results = run_normal_fight_from_yaml(ctx, 'my_plan', times=3, fleet=['ship'])

        mock_get_plan.assert_called_once_with('my_plan')
        mock_runner_cls.assert_called_once_with(
            ctx,
            mock_plan,
            fleet_id=None,
            fleet=['ship'],
            fleet_rules=None,
        )
        mock_runner.run_for_times.assert_called_once_with(3, gap=0.0)
        assert results == ['result']
