"""测试 autowsgr.ops.event_fight。"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from autowsgr.combat import CombatMode, CombatPlan
from autowsgr.combat.history import CombatResult
from autowsgr.ops.event_fight import (
    EventFightRunner,
    run_event_fight,
    run_event_fight_from_yaml,
)
from autowsgr.types import ConditionFlag


def _make_ctx() -> MagicMock:
    """构造一个满足 EventFightRunner 初始化需求的 mock 上下文。"""
    ctx = MagicMock()
    ctx.config.dock_full_destroy = False
    ctx.config.destroy_ship_types = None
    return ctx


def _make_plan(**kwargs: Any) -> CombatPlan:
    """使用指定字段构造 CombatPlan，其余保持默认值。"""
    return CombatPlan(**kwargs)


class TestInitMapCode:
    """__init__ map_code 推导测试。"""

    def test_explicit_map_code_used(self) -> None:
        ctx = _make_ctx()
        plan = _make_plan(chapter='H', map_id=3)
        runner = EventFightRunner(ctx, plan, map_code='Z9')
        assert runner._map_code == 'Z9'

    def test_derived_h3(self) -> None:
        ctx = _make_ctx()
        plan = _make_plan(chapter='H', map_id=3)
        runner = EventFightRunner(ctx, plan)
        assert runner._map_code == 'H3'

    def test_derived_e1(self) -> None:
        ctx = _make_ctx()
        plan = _make_plan(chapter='E', map_id=1)
        runner = EventFightRunner(ctx, plan)
        assert runner._map_code == 'E1'

    def test_fallback_x5(self) -> None:
        ctx = _make_ctx()
        plan = _make_plan(chapter='X', map_id=5)
        runner = EventFightRunner(ctx, plan)
        assert runner._map_code == 'H5'

    def test_defaults_none(self) -> None:
        ctx = _make_ctx()
        plan = _make_plan(chapter=None, map_id=None)
        runner = EventFightRunner(ctx, plan)
        assert runner._map_code == 'H1'


class TestInitEventName:
    """__init__ event_name 优先级测试。"""

    def test_param_provided_sets_plan(self) -> None:
        ctx = _make_ctx()
        plan = _make_plan(event_name=None)
        runner = EventFightRunner(ctx, plan, event_name='20260212')
        assert runner._plan.event_name == '20260212'

    def test_param_none_plan_set(self) -> None:
        ctx = _make_ctx()
        plan = _make_plan(event_name='existing')
        runner = EventFightRunner(ctx, plan, event_name=None)
        assert runner._plan.event_name == 'existing'

    def test_both_none(self) -> None:
        ctx = _make_ctx()
        plan = _make_plan(event_name=None)
        runner = EventFightRunner(ctx, plan, event_name=None)
        assert runner._plan.event_name is None


class TestInitMode:
    """__init__ mode 强制修正测试。"""

    def test_normal_corrected_to_event(self) -> None:
        ctx = _make_ctx()
        plan = _make_plan(mode=CombatMode.NORMAL)
        runner = EventFightRunner(ctx, plan)
        assert runner._plan.mode == CombatMode.EVENT

    def test_event_unchanged(self) -> None:
        ctx = _make_ctx()
        plan = _make_plan(mode=CombatMode.EVENT)
        runner = EventFightRunner(ctx, plan)
        assert runner._plan.mode == CombatMode.EVENT


class TestInitFleetId:
    """__init__ fleet_id 回退测试。"""

    def test_param_provided(self) -> None:
        ctx = _make_ctx()
        plan = _make_plan(fleet_id=2)
        runner = EventFightRunner(ctx, plan, fleet_id=3)
        assert runner._fleet_id == 3

    def test_plan_fallback(self) -> None:
        ctx = _make_ctx()
        plan = _make_plan(fleet_id=2)
        runner = EventFightRunner(ctx, plan)
        assert runner._fleet_id == 2

    def test_default_to_one(self) -> None:
        ctx = _make_ctx()
        plan = _make_plan(fleet_id=None)
        runner = EventFightRunner(ctx, plan, fleet_id=None)
        assert runner._fleet_id == 1


class TestPrimaryNamesFromRules:
    """_primary_names_from_rules 静态方法测试。"""

    def test_none_returns_none(self) -> None:
        assert EventFightRunner._primary_names_from_rules(None) is None

    def test_empty_list_returns_none(self) -> None:
        assert EventFightRunner._primary_names_from_rules([]) is None

    def test_strings(self) -> None:
        rules = ['A', 'B', 'C']
        assert EventFightRunner._primary_names_from_rules(rules) == ['A', 'B', 'C']

    def test_whitespace(self) -> None:
        rules = ['  A  ', '', '   ']
        assert EventFightRunner._primary_names_from_rules(rules) == ['A', None, None]

    def test_dicts(self) -> None:
        rules = [
            {'candidates': ['X', 'Y']},
            {'candidates': []},
            {'candidates': ['Z']},
        ]
        assert EventFightRunner._primary_names_from_rules(rules) == ['X', None, 'Z']

    def test_objects(self) -> None:
        class Rule:
            def __init__(self, candidates: list[str] | None) -> None:
                self.candidates = candidates

        rules = [Rule(['A']), Rule([]), Rule(None)]
        assert EventFightRunner._primary_names_from_rules(rules) == ['A', None, None]

    def test_more_than_six_slots(self) -> None:
        rules = [f'ship{i}' for i in range(8)]
        result = EventFightRunner._primary_names_from_rules(rules)
        assert result is not None
        assert len(result) == 6
        assert result == ['ship0', 'ship1', 'ship2', 'ship3', 'ship4', 'ship5']

    def test_mixed(self) -> None:
        class Rule:
            def __init__(self, candidates: list[str] | None) -> None:
                self.candidates = candidates

        rules = [
            'A',
            {'candidates': ['B']},
            Rule(['C']),
            None,
            '',
            {'candidates': []},
            'D',
        ]
        result = EventFightRunner._primary_names_from_rules(rules)
        assert result is not None
        assert len(result) == 6
        assert result == ['A', 'B', 'C', None, None, None]


class TestRunForTimes:
    """run_for_times 循环与中断测试。"""

    def test_loop_count(self) -> None:
        ctx = _make_ctx()
        plan = _make_plan(mode=CombatMode.EVENT)
        runner = EventFightRunner(ctx, plan)
        with patch.object(runner, 'run') as mock_run:
            mock_run.return_value = CombatResult(flag=ConditionFlag.OPERATION_SUCCESS)
            results = runner.run_for_times(3)
        assert len(results) == 3
        assert mock_run.call_count == 3

    def test_dock_full_break(self) -> None:
        ctx = _make_ctx()
        plan = _make_plan(mode=CombatMode.EVENT)
        runner = EventFightRunner(ctx, plan)
        success = CombatResult(flag=ConditionFlag.OPERATION_SUCCESS)
        dock_full = CombatResult(flag=ConditionFlag.DOCK_FULL)
        with patch.object(runner, 'run', side_effect=[success, dock_full, success]):
            results = runner.run_for_times(3)
        assert len(results) == 2

    def test_gap_sleep(self) -> None:
        ctx = _make_ctx()
        plan = _make_plan(mode=CombatMode.EVENT)
        runner = EventFightRunner(ctx, plan)
        with (
            patch.object(
                runner, 'run', return_value=CombatResult(flag=ConditionFlag.OPERATION_SUCCESS)
            ),
            patch('autowsgr.ops.event_fight.time.sleep') as mock_sleep,
        ):
            runner.run_for_times(3, gap=1.5)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(1.5)


class TestRunEventFight:
    """run_event_fight 便捷函数测试。"""

    @patch('autowsgr.ops.event_fight.EventFightRunner')
    def test_calls_runner(self, mock_cls: MagicMock) -> None:
        ctx = _make_ctx()
        plan = _make_plan(mode=CombatMode.EVENT)
        mock_runner = mock_cls.return_value
        mock_runner.run_for_times.return_value = ['r1', 'r2']

        result = run_event_fight(ctx, plan, map_code='H3', times=2, gap=1.0)

        mock_cls.assert_called_once_with(
            ctx,
            plan,
            map_code='H3',
            entrance=None,
            fleet_id=None,
            fleet=None,
            fleet_rules=None,
        )
        mock_runner.run_for_times.assert_called_once_with(2, gap=1.0)
        assert result == ['r1', 'r2']


class TestRunEventFightFromYaml:
    """run_event_fight_from_yaml 便捷函数测试。"""

    @patch('autowsgr.ops.event_fight.run_event_fight')
    @patch('autowsgr.ops.event_fight.CombatPlan.from_yaml')
    @patch('autowsgr.infra.file_utils.resolve_plan_path')
    def test_calls_chain(
        self,
        mock_resolve: MagicMock,
        mock_from_yaml: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        ctx = _make_ctx()
        mock_resolve.return_value = Path('/fake/plan.yaml')
        plan = _make_plan(mode=CombatMode.EVENT)
        mock_from_yaml.return_value = plan
        mock_run.return_value = ['r1']

        result = run_event_fight_from_yaml(
            ctx,
            'my_plan',
            map_code='E1',
            entrance='alpha',
            times=3,
            fleet_id=2,
            fleet=['ship1'],
            fleet_rules=['rule1'],
        )

        mock_resolve.assert_called_once_with('my_plan', category='event')
        mock_from_yaml.assert_called_once_with(Path('/fake/plan.yaml'))
        mock_run.assert_called_once_with(
            ctx,
            plan,
            map_code='E1',
            entrance='alpha',
            times=3,
            fleet_id=2,
            fleet=['ship1'],
            fleet_rules=['rule1'],
        )
        assert result == ['r1']
