"""TaskScheduler runner 适配单元测试 (无设备)。

回归: CampaignRunner / ExerciseRunner 的 ``run()`` 返回 ``list[CombatResult]``,
调度器必须经 :class:`BatchRunnerAdapter` 适配为单个结果, 否则 ``on_done`` /
``result.flag`` 会触发 ``'list' object has no attribute 'flag'`` 崩溃。
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from autowsgr.combat import CombatResult
from autowsgr.scheduler.scheduler import BatchRunnerAdapter, FightTask, TaskScheduler
from autowsgr.types import ConditionFlag


if TYPE_CHECKING:
    import pytest


# ── 假 runner ──


class _ListRunner:
    """模拟 CampaignRunner: run() 返回 list[CombatResult]。"""

    def __init__(self, results: list[CombatResult]) -> None:
        self._results = results

    def run(self) -> list[CombatResult]:
        return list(self._results)


class _SingleRunner:
    """模拟 NormalFightRunner: run() 返回单个 CombatResult。"""

    def __init__(self, result: CombatResult) -> None:
        self._result = result

    def run(self) -> CombatResult:
        return self._result


# ── BatchRunnerAdapter 行为 ──


def test_batch_adapter_list_takes_last():
    r1 = CombatResult(flag=ConditionFlag.OPERATION_SUCCESS)
    r2 = CombatResult(flag=ConditionFlag.BATTLE_TIMES_EXCEED)
    assert BatchRunnerAdapter(_ListRunner([r1, r2])).run() is r2


def test_batch_adapter_single_passthrough():
    r = CombatResult(flag=ConditionFlag.OPERATION_SUCCESS)
    assert BatchRunnerAdapter(_SingleRunner(r)).run() is r


def test_batch_adapter_empty_list_defaults_success():
    out = BatchRunnerAdapter(_ListRunner([])).run()
    assert out.flag == ConditionFlag.OPERATION_SUCCESS


# ── _run_task 端到端 (list runner 不再崩溃) ──


class _FakeCtx:
    """最小 ctx 替身: 仅暴露 _run_task 访问的成员。"""

    def __init__(self) -> None:
        self.active_fight_tasks = 0
        self.stop_event = threading.Event()


def test_run_task_handles_list_runner(monkeypatch: pytest.MonkeyPatch):
    """返回 list 的 runner 经调度器后, on_done 收到单个 CombatResult (回归崩溃)。"""
    ctx = _FakeCtx()
    sched = TaskScheduler(ctx, expedition_interval=0)  # type: ignore[arg-type]
    monkeypatch.setattr(sched, '_maybe_collect_expedition', lambda: None)

    received: list[CombatResult] = []
    result = CombatResult(flag=ConditionFlag.OPERATION_SUCCESS)
    task = FightTask(
        runner=_ListRunner([result]),
        times=1,
        on_done=received.append,
    )

    sched._run_task(task)  # 不应抛 AttributeError

    assert received == [result]  # on_done 收到单个, 不是 list
    assert task.results == [result]
    assert task.completed == 1


def test_run_task_list_runner_exceed_flag(monkeypatch: pytest.MonkeyPatch):
    """list runner 最后一场为 BATTLE_TIMES_EXCEED 时, 该 flag 正确传递给 on_done。"""
    ctx = _FakeCtx()
    sched = TaskScheduler(ctx, expedition_interval=0)  # type: ignore[arg-type]
    monkeypatch.setattr(sched, '_maybe_collect_expedition', lambda: None)

    seen: list[ConditionFlag] = []
    ok = CombatResult(flag=ConditionFlag.OPERATION_SUCCESS)
    exceed = CombatResult(flag=ConditionFlag.BATTLE_TIMES_EXCEED)
    task = FightTask(
        runner=_ListRunner([ok, exceed]),
        times=1,
        on_done=lambda r: seen.append(r.flag),
    )

    sched._run_task(task)

    assert seen == [ConditionFlag.BATTLE_TIMES_EXCEED]  # 取最后一场


def test_run_task_single_runner_still_works(monkeypatch: pytest.MonkeyPatch):
    """单个 CombatResult runner 经适配后仍正确 (passthrough 不破坏)。"""
    ctx = _FakeCtx()
    sched = TaskScheduler(ctx, expedition_interval=0)  # type: ignore[arg-type]
    monkeypatch.setattr(sched, '_maybe_collect_expedition', lambda: None)

    received: list[CombatResult] = []
    result = CombatResult(flag=ConditionFlag.OPERATION_SUCCESS)
    task = FightTask(runner=_SingleRunner(result), times=1, on_done=received.append)

    sched._run_task(task)

    assert received == [result]
    assert task.results == [result]


# ── 浴室修理优先级 (空闲修船: 所有战斗完成后才执行) ──


def test_bath_repair_priority_after_all_combat():
    """浴室修理优先级 > 所有战斗任务, 还原 classic '所有战斗 (含常规战) 完成后才修船'。"""
    from autowsgr.scheduler.daily_plan import (
        PRIO_BATH_REPAIR,
        PRIO_BONUS,
        PRIO_CAMPAIGN,
        PRIO_EXERCISE,
        PRIO_EXPEDITION,
        PRIO_NORMAL_FIGHT,
    )

    assert PRIO_BATH_REPAIR > PRIO_NORMAL_FIGHT
    assert PRIO_BATH_REPAIR > PRIO_EXERCISE
    assert PRIO_BATH_REPAIR > PRIO_CAMPAIGN
    assert PRIO_BATH_REPAIR > PRIO_BONUS
    assert PRIO_BATH_REPAIR > PRIO_EXPEDITION


def test_bath_repair_queues_behind_normal_fight():
    """同一队列里浴室修理 (prio 200) 永远排在常规战 (prio 100) 之后出队。"""
    ctx = _FakeCtx()
    sched = TaskScheduler(ctx, expedition_interval=0)  # type: ignore[arg-type]
    bath = FightTask(runner=object(), priority=200, name='浴室修理')
    normal = FightTask(runner=object(), priority=100, name='常规战')

    # 无论入队顺序, 常规战 (100) 先出队 → 浴室修理等常规战打完才轮到
    sched._enqueue(bath)
    sched._enqueue(normal)
    assert sched._dequeue().name == '常规战'
    assert sched._dequeue().name == '浴室修理'


# ── 无限常规战饿死浴室修理的启动告警 ──


def test_starvation_warned_when_infinite_normal_fight_no_limits():
    """无限常规战 (times=None) + 停止上限全关 + 启用浴室修理 → 应告警。"""
    from autowsgr.infra.config import DailyAutomationConfig
    from autowsgr.scheduler.daily_plan import _bath_repair_starved_by_normal_fight

    cfg = DailyAutomationConfig(
        auto_bath_repair=True,
        auto_normal_fight=True,
        normal_fight_tasks=[{'name': 'x'}],  # times 默认 None
    )
    assert _bath_repair_starved_by_normal_fight(cfg) is True


def test_starvation_not_warned_when_times_set():
    """常规战设了 times (有限) → 不会饿死浴室修理, 不告警。"""
    from autowsgr.infra.config import DailyAutomationConfig
    from autowsgr.scheduler.daily_plan import _bath_repair_starved_by_normal_fight

    cfg = DailyAutomationConfig(
        auto_bath_repair=True,
        auto_normal_fight=True,
        normal_fight_tasks=[{'name': 'x', 'times': 10}],
    )
    assert _bath_repair_starved_by_normal_fight(cfg) is False


def test_starvation_not_warned_when_stop_limit_enabled():
    """开启任一停止上限 → 常规战终会耗尽让位, 不告警。"""
    from autowsgr.infra.config import DailyAutomationConfig
    from autowsgr.scheduler.daily_plan import _bath_repair_starved_by_normal_fight

    cfg = DailyAutomationConfig(
        auto_bath_repair=True,
        auto_normal_fight=True,
        normal_fight_tasks=[{'name': 'x'}],
        stop_max_ship=True,
    )
    assert _bath_repair_starved_by_normal_fight(cfg) is False


def test_starvation_not_warned_when_bath_repair_off():
    """未启用浴室修理 → 无所谓饿死, 不告警。"""
    from autowsgr.infra.config import DailyAutomationConfig
    from autowsgr.scheduler.daily_plan import _bath_repair_starved_by_normal_fight

    cfg = DailyAutomationConfig(
        auto_bath_repair=False,
        auto_normal_fight=True,
        normal_fight_tasks=[{'name': 'x'}],
    )
    assert _bath_repair_starved_by_normal_fight(cfg) is False
