"""测试手动维修会终止整个调度任务。"""

from threading import Event
from types import SimpleNamespace

from autowsgr.combat import CombatResult
from autowsgr.infra import ManualRepairRequiredError
from autowsgr.scheduler.scheduler import FightTask, TaskScheduler
from autowsgr.types import ConditionFlag


def test_manual_repair_does_not_consume_remaining_scheduler_rounds() -> None:
    calls = 0

    class Runner:
        def run(self) -> CombatResult:
            nonlocal calls
            calls += 1
            raise ManualRepairRequiredError('需要进行手动修理')

    ctx = SimpleNamespace(stop_event=Event(), active_fight_tasks=0)
    scheduler = TaskScheduler(ctx, expedition_interval=0)
    task = FightTask(runner=Runner(), times=3)

    scheduler._run_task(task)

    assert calls == 1
    assert task.completed == 0
    assert len(task.results) == 1
    assert task.results[0].flag is ConditionFlag.ACTION_FAILED
