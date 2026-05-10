"""测试 autowsgr.scheduler.scheduler。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from autowsgr.combat import CombatResult
from autowsgr.scheduler.scheduler import (
    BatchRunnerAdapter,
    FightTask,
    TaskScheduler,
)
from autowsgr.types import ConditionFlag


def test_batch_runner_adapter_with_list() -> None:
    """BatchRunnerAdapter 应将 list 结果取最后一个元素。"""
    inner = MagicMock()
    inner.run.return_value = [
        CombatResult(flag=ConditionFlag.FIGHT_CONTINUE),
        CombatResult(flag=ConditionFlag.OPERATION_SUCCESS),
    ]
    adapter = BatchRunnerAdapter(inner)
    result = adapter.run()
    assert result.flag == ConditionFlag.OPERATION_SUCCESS


def test_batch_runner_adapter_empty_list() -> None:
    """空 list 时应返回默认成功结果。"""
    inner = MagicMock()
    inner.run.return_value = []
    adapter = BatchRunnerAdapter(inner)
    result = adapter.run()
    assert result.flag == ConditionFlag.OPERATION_SUCCESS


def test_batch_runner_adapter_single_result() -> None:
    """单条结果应原样返回。"""
    inner = MagicMock()
    inner.run.return_value = CombatResult(flag=ConditionFlag.FIGHT_END)
    adapter = BatchRunnerAdapter(inner)
    result = adapter.run()
    assert result.flag == ConditionFlag.FIGHT_END


def test_batch_runner_adapter_no_run_method() -> None:
    """inner 没有 run 方法时应抛出 TypeError。"""
    with pytest.raises(TypeError, match='没有 run\\(\\) 方法'):
        BatchRunnerAdapter(object())


def test_fight_task_default_name() -> None:
    """未指定名称时应自动使用 runner 类名。"""
    runner = MagicMock()
    task = FightTask(runner=runner, times=3)
    assert task.name == 'MagicMock'
    assert task.times == 3


def test_task_scheduler_add_and_tasks() -> None:
    """add 应支持链式调用，tasks 应返回只读副本。"""
    ctx = MagicMock()
    scheduler = TaskScheduler(ctx)
    t1 = FightTask(MagicMock(), times=1)
    t2 = FightTask(MagicMock(), times=2)
    ret = scheduler.add(t1).add(t2)
    assert ret is scheduler
    assert len(scheduler.tasks) == 2


def test_task_scheduler_run_empty() -> None:
    """无任务时应直接返回空列表。"""
    ctx = MagicMock()
    scheduler = TaskScheduler(ctx)
    assert scheduler.run() == []


def test_task_scheduler_run_success() -> None:
    """正常 runner 应被正确执行指定次数。"""
    ctx = MagicMock()
    scheduler = TaskScheduler(ctx, expedition_interval=0)
    runner = MagicMock()
    runner.run.return_value = CombatResult(flag=ConditionFlag.OPERATION_SUCCESS)
    task = FightTask(runner=runner, times=3)
    scheduler.add(task)
    results = scheduler.run()
    assert len(results) == 1
    assert results[0].completed == 3
    assert len(results[0].results) == 3
    assert runner.run.call_count == 3


def test_task_scheduler_dock_full_stops() -> None:
    """船坞满时应中断当前任务。"""
    ctx = MagicMock()
    scheduler = TaskScheduler(ctx, expedition_interval=0)
    runner = MagicMock()
    runner.run.return_value = CombatResult(flag=ConditionFlag.DOCK_FULL)
    task = FightTask(runner=runner, times=5)
    scheduler.add(task)
    scheduler.run()
    assert task.completed == 1
    assert runner.run.call_count == 1


def test_task_scheduler_may_collect_expedition_disabled() -> None:
    """interval <= 0 时不应触发远征检查。"""
    ctx = MagicMock()
    scheduler = TaskScheduler(ctx, expedition_interval=-1)
    scheduler._maybe_collect_expedition()
    # 只要不抛出异常即可
