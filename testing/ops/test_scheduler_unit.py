"""TaskScheduler runner 适配单元测试 (无设备)。

回归: CampaignRunner / ExerciseRunner 的 ``run()`` 返回 ``list[CombatResult]``,
调度器必须经 :class:`BatchRunnerAdapter` 适配为单个结果, 否则 ``on_done`` /
``result.flag`` 会触发 ``'list' object has no attribute 'flag'`` 崩溃。
"""

from __future__ import annotations

import threading
import types
from unittest.mock import MagicMock

import pytest

from autowsgr.combat import CombatResult
from autowsgr.context import GameContext
from autowsgr.scheduler.scheduler import BatchRunnerAdapter, FightTask, TaskScheduler
from autowsgr.scheduler.triggers import NormalFightPlan, NormalFightTrigger
from autowsgr.types import ConditionFlag


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


def test_batch_adapter_preserves_all_results():
    r1 = CombatResult(flag=ConditionFlag.OPERATION_SUCCESS)
    r2 = CombatResult(flag=ConditionFlag.BATTLE_TIMES_EXCEED)
    assert BatchRunnerAdapter(_ListRunner([r1, r2])).run() == [r1, r2]


def test_batch_adapter_single_passthrough():
    r = CombatResult(flag=ConditionFlag.OPERATION_SUCCESS)
    assert BatchRunnerAdapter(_SingleRunner(r)).run() == [r]


def test_batch_adapter_preserves_empty_batch():
    assert BatchRunnerAdapter(_ListRunner([])).run() == []


# ── _run_task 端到端 (list runner 不再崩溃) ──


class _FakeCtx:
    """最小 ctx 替身: 仅暴露 _run_task 访问的成员。"""

    def __init__(self) -> None:
        self.active_fight_tasks = 0
        self.stop_event = threading.Event()


# ── 每日主页面浮层检查 ──


def test_ensure_main_page_clean_calls_daily_overlay_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """调度器将当前上下文交给每日浮层处理入口。"""
    from autowsgr.ops import startup

    handler = MagicMock()
    monkeypatch.setattr(startup, 'handle_daily_overlays', handler)
    ctx = _FakeCtx()
    sched = TaskScheduler(ctx, expedition_interval=0)  # type: ignore[arg-type]

    sched._ensure_main_page_clean()

    handler.assert_called_once_with(ctx)


def test_ensure_main_page_clean_does_not_interrupt_scheduler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """浮层识别异常只记录警告，不能中断后续任务。"""
    import autowsgr.scheduler.scheduler as scheduler_module
    from autowsgr.ops import startup

    handler = MagicMock(side_effect=RuntimeError('截图失败'))
    logger = MagicMock()
    monkeypatch.setattr(startup, 'handle_daily_overlays', handler)
    monkeypatch.setattr(scheduler_module, '_log', logger)
    sched = TaskScheduler(_FakeCtx(), expedition_interval=0)  # type: ignore[arg-type]

    sched._ensure_main_page_clean()

    logger.opt.assert_called_once_with(exception=True)
    logger.opt.return_value.warning.assert_called_once()


def test_run_checks_daily_overlays_before_each_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """顺序调度每项任务前都检查一次主页面浮层。"""
    result = CombatResult(flag=ConditionFlag.OPERATION_SUCCESS)
    task = FightTask(runner=_SingleRunner(result), times=1)
    sched = TaskScheduler(_FakeCtx(), expedition_interval=0)  # type: ignore[arg-type]
    sched.add(task)
    clean = MagicMock()
    run_task = MagicMock()
    monkeypatch.setattr(sched, '_ensure_main_page_clean', clean)
    monkeypatch.setattr(sched, '_run_task', run_task)
    monkeypatch.setattr(sched, '_print_summary', MagicMock())

    assert sched.run() == [task]

    clean.assert_called_once_with()
    run_task.assert_called_once_with(task)


def test_run_daily_checks_overlays_while_queue_is_idle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """长期挂机队列为空时检查浮层，并在停止信号到达后退出。"""
    import autowsgr.scheduler.scheduler as scheduler_module

    ctx = _FakeCtx()
    sched = TaskScheduler(ctx, expedition_interval=0, idle_sleep=0)  # type: ignore[arg-type]
    clean = MagicMock(side_effect=ctx.stop_event.set)
    monkeypatch.setattr(sched, '_ensure_main_page_clean', clean)
    monkeypatch.setattr(sched, '_sync_initial_counts', MagicMock())
    monkeypatch.setattr(sched, '_check_daily_reset', MagicMock())
    monkeypatch.setattr(sched, '_print_summary', MagicMock())
    sleep = MagicMock()
    monkeypatch.setattr(scheduler_module.time, 'sleep', sleep)

    sched.run_daily()

    clean.assert_called_once_with()
    sleep.assert_called_once_with(0)


def test_run_task_handles_list_runner(monkeypatch: pytest.MonkeyPatch):
    """返回 list 的 runner 经调度器后保留并通知每个结果。"""
    ctx = _FakeCtx()
    sched = TaskScheduler(ctx, expedition_interval=0)  # type: ignore[arg-type]
    monkeypatch.setattr(sched, '_maybe_collect_expedition', lambda: None)

    received: list[CombatResult] = []
    first = CombatResult(flag=ConditionFlag.OPERATION_SUCCESS)
    second = CombatResult(flag=ConditionFlag.ACTION_FAILED)
    task = FightTask(
        runner=_ListRunner([first, second]),
        times=1,
        on_done=received.append,
    )

    sched._run_task(task)  # 不应抛 AttributeError

    assert received == [first, second]
    assert task.results == [first, second]
    assert task.completed == 1


def test_run_task_list_runner_exceed_flag(monkeypatch: pytest.MonkeyPatch):
    """list runner 的每场 flag 都按顺序传递给 on_done。"""
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

    assert seen == [ConditionFlag.OPERATION_SUCCESS, ConditionFlag.BATTLE_TIMES_EXCEED]


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


def test_run_task_empty_batch_is_explicit_failure(monkeypatch: pytest.MonkeyPatch):
    """未执行任何战斗不能伪造成成功。"""
    ctx = _FakeCtx()
    sched = TaskScheduler(ctx, expedition_interval=0)  # type: ignore[arg-type]
    monkeypatch.setattr(sched, '_maybe_collect_expedition', lambda: None)
    received: list[CombatResult] = []
    task = FightTask(runner=_ListRunner([]), times=1, on_done=received.append)

    sched._run_task(task)

    assert len(task.results) == 1
    assert task.results[0].flag == ConditionFlag.ACTION_FAILED
    assert received == task.results
    assert task.completed == 1


def test_run_task_dock_full_batch_stops_outer_repetition(monkeypatch: pytest.MonkeyPatch):
    """批次内船坞满保留已返回结果，并阻止下一次 runner 调用。"""
    ctx = _FakeCtx()
    sched = TaskScheduler(ctx, expedition_interval=0)  # type: ignore[arg-type]
    monkeypatch.setattr(sched, '_maybe_collect_expedition', lambda: None)
    ok = CombatResult(flag=ConditionFlag.OPERATION_SUCCESS)
    full = CombatResult(flag=ConditionFlag.DOCK_FULL)
    runner = _ListRunner([ok, full])
    calls = 0

    def run() -> list[CombatResult]:
        nonlocal calls
        calls += 1
        return [ok, full]

    runner.run = run  # type: ignore[method-assign]
    task = FightTask(runner=runner, times=3)

    sched._run_task(task)

    assert calls == 1
    assert task.results == [ok, full]
    assert task.completed == 1


def test_run_task_concatenates_results_from_repeated_batches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """多次 runner 调用的批量结果按实际执行顺序完整保留。"""
    ctx = _FakeCtx()
    sched = TaskScheduler(ctx, expedition_interval=0)  # type: ignore[arg-type]
    monkeypatch.setattr(sched, '_maybe_collect_expedition', lambda: None)
    first = CombatResult(flag=ConditionFlag.OPERATION_SUCCESS)
    second = CombatResult(flag=ConditionFlag.ACTION_FAILED)
    third = CombatResult(flag=ConditionFlag.OPERATION_SUCCESS)
    batches = iter([[first, second], [third]])
    runner = _ListRunner([])
    runner.run = lambda: next(batches)  # type: ignore[method-assign]
    received: list[CombatResult] = []
    task = FightTask(runner=runner, times=2, on_done=received.append)

    sched._run_task(task)

    assert task.results == [first, second, third]
    assert received == task.results
    assert task.completed == 2


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


# ── 启动计数器校准 (避免常规战误触发) ──


class _FakeDA:
    """daily_automation 替身: 仅暴露 stop_max_ship / stop_max_loot。"""

    def __init__(self, stop_max_ship: bool = False, stop_max_loot: bool = False) -> None:
        self.stop_max_ship = stop_max_ship
        self.stop_max_loot = stop_max_loot


def _ctx_with_da(da: _FakeDA | None) -> _FakeCtx:
    ctx = _FakeCtx()
    ctx.config = types.SimpleNamespace(daily_automation=da)
    return ctx


def test_sync_initial_counts_skipped_when_no_stop_limit():
    """未启用 stop_max_ship/loot → 不校准 (常规战无限打, 计数器无需校准)。"""
    ctx = _ctx_with_da(_FakeDA(stop_max_ship=False, stop_max_loot=False))
    called: list = []
    ctx.sync_daily_drop_counts = lambda: called.append(1)  # type: ignore[method-assign]

    sched = TaskScheduler(ctx, expedition_interval=0)  # type: ignore[arg-type]
    sched._sync_initial_counts()
    assert called == []


def test_sync_initial_counts_runs_when_stop_max_ship():
    """启用 stop_max_ship → 调 ctx.sync_daily_drop_counts 校准。"""
    ctx = _ctx_with_da(_FakeDA(stop_max_ship=True))
    called: list = []
    ctx.sync_daily_drop_counts = lambda: called.append(1)  # type: ignore[method-assign]

    sched = TaskScheduler(ctx, expedition_interval=0)  # type: ignore[arg-type]
    sched._sync_initial_counts()
    assert called == [1]


def test_sync_initial_counts_runs_when_stop_max_loot():
    """启用 stop_max_loot (未启用 ship) → 仍校准。"""
    ctx = _ctx_with_da(_FakeDA(stop_max_loot=True))
    called: list = []
    ctx.sync_daily_drop_counts = lambda: called.append(1)  # type: ignore[method-assign]

    sched = TaskScheduler(ctx, expedition_interval=0)  # type: ignore[arg-type]
    sched._sync_initial_counts()
    assert called == [1]


def test_sync_initial_counts_skipped_when_da_none():
    """未配置 daily_automation (None) → 不校准。"""
    ctx = _ctx_with_da(None)
    called: list = []
    ctx.sync_daily_drop_counts = lambda: called.append(1)  # type: ignore[method-assign]

    sched = TaskScheduler(ctx, expedition_interval=0)  # type: ignore[arg-type]
    sched._sync_initial_counts()
    assert called == []


def test_sync_initial_counts_disables_normal_fight_on_failure():
    """校准抛异常 → 不降级, 直接禁用 NormalFightTrigger 并提示 (不阻塞主循环)。"""
    from autowsgr.scheduler.triggers import NormalFightPlan, NormalFightTrigger

    def boom() -> None:
        raise RuntimeError('OCR 不可用')

    ctx = _ctx_with_da(_FakeDA(stop_max_ship=True))
    ctx.sync_daily_drop_counts = boom  # type: ignore[method-assign]

    plan = NormalFightPlan(factory=lambda _c: object(), name='x', fleet_id=1)
    trigger = NormalFightTrigger(priority=100, name='常规战', plans=[plan])

    sched = TaskScheduler(ctx, expedition_interval=0)  # type: ignore[arg-type]
    sched.register_trigger(trigger)
    sched._sync_initial_counts()  # 不抛

    assert trigger._disabled is True
    assert trigger.should_fire(ctx) is None  # 禁用后不再产出


# ── GameContext.sync_daily_drop_counts (识别 + 同步每日计数器) ──


class _FakeSortiePage:
    """MapPage 替身: ensure_panel no-op, get_loot_and_ship_count 返回预设值。"""

    def __init__(
        self,
        *,
        ship: int | None,
        loot: int | None,
        raises: type[Exception] | None = None,
    ) -> None:
        self._ship = ship
        self._loot = loot
        self._raises = raises

    def ensure_panel(self, _panel: object) -> None:
        return None

    def get_loot_and_ship_count(self) -> types.SimpleNamespace:
        if self._raises is not None:
            raise self._raises('OCR 不可用')
        return types.SimpleNamespace(ship=self._ship, loot=self._loot)


def _patch_ctx_sortie(monkeypatch: pytest.MonkeyPatch, page: _FakeSortiePage) -> None:
    """替换 ctx.sync_daily_drop_counts 的设备依赖 (goto_page / MapPage / sleep) 为 no-op。"""
    import autowsgr.context.game_context as gc_mod
    import autowsgr.ops as ops_mod
    import autowsgr.ui as ui_mod

    monkeypatch.setattr(ops_mod, 'goto_page', lambda *_a, **_kw: None)
    monkeypatch.setattr(ui_mod, 'MapPage', lambda _ctx: page)
    monkeypatch.setattr(gc_mod, 'time', types.SimpleNamespace(sleep=lambda *_a: None))


def _make_ctx() -> GameContext:
    return GameContext(ctrl=object(), config=types.SimpleNamespace(), ocr=object())  # type: ignore[arg-type]


def test_ctx_sync_drop_counts_writes_both(monkeypatch: pytest.MonkeyPatch):
    """读到真实计数 → 同步到 dropped_ship_count / dropped_loot_count。"""
    _patch_ctx_sortie(monkeypatch, _FakeSortiePage(ship=500, loot=50))
    ctx = _make_ctx()
    ctx.dropped_ship_count = 0
    ctx.dropped_loot_count = 0

    ctx.sync_daily_drop_counts()
    assert ctx.dropped_ship_count == 500
    assert ctx.dropped_loot_count == 50


def test_ctx_sync_drop_counts_ignores_none(monkeypatch: pytest.MonkeyPatch):
    """单项 OCR 解析失败 (None) → 不覆盖, 只同步成功的那项。"""
    _patch_ctx_sortie(monkeypatch, _FakeSortiePage(ship=None, loot=50))
    ctx = _make_ctx()
    ctx.dropped_ship_count = 0
    ctx.dropped_loot_count = 0

    ctx.sync_daily_drop_counts()
    assert ctx.dropped_ship_count == 0  # None 未覆盖
    assert ctx.dropped_loot_count == 50


def test_ctx_sync_drop_counts_raises_on_ocr_unavailable(monkeypatch: pytest.MonkeyPatch):
    """OCR 引擎不可用 (RuntimeError) → 抛出, 不降级, 计数保持不变。"""
    _patch_ctx_sortie(monkeypatch, _FakeSortiePage(ship=500, loot=50, raises=RuntimeError))
    ctx = _make_ctx()
    ctx.dropped_ship_count = 0
    ctx.dropped_loot_count = 0

    with pytest.raises(RuntimeError):
        ctx.sync_daily_drop_counts()
    assert ctx.dropped_ship_count == 0  # 未同步
    assert ctx.dropped_loot_count == 0


# ── NormalFightTrigger.disable ──


def test_normal_fight_trigger_disable_stops_production():
    """disable() 后 should_fire 永远返回 None。"""
    from autowsgr.scheduler.triggers import NormalFightPlan, NormalFightTrigger

    plan = NormalFightPlan(factory=lambda _c: object(), name='x', fleet_id=1)
    ctx = _ctx_with_da(None)
    trigger = NormalFightTrigger(priority=100, name='常规战', plans=[plan])
    assert trigger.should_fire(ctx) is not None  # 未禁用能产出

    trigger.disable(reason='OCR 不可用')
    assert trigger._disabled is True
    assert trigger.should_fire(ctx) is None  # 禁用后不产出


def test_normal_fight_trigger_disable_survives_reset():
    """reset() (跨日) 不清除禁用 (OCR 可用性不跨日变化)。"""
    from autowsgr.scheduler.triggers import NormalFightPlan, NormalFightTrigger

    plan = NormalFightPlan(factory=lambda _c: object(), name='x', fleet_id=1)
    ctx = _ctx_with_da(None)
    trigger = NormalFightTrigger(priority=100, name='常规战', plans=[plan])
    trigger.disable(reason='OCR 不可用')
    trigger.reset()

    assert trigger._disabled is True
    assert trigger.should_fire(ctx) is None


# ── 战果条件计数 + DOCK_FULL 解装自愈 ──


def _fight_result(node: str, grade: str) -> CombatResult:
    """构造一场成功战斗: flag=SUCCESS + 单节点战果。"""
    from autowsgr.combat.history import CombatEvent, EventType

    result = CombatResult(flag=ConditionFlag.OPERATION_SUCCESS)
    result.history.add(CombatEvent(event_type=EventType.RESULT, node=node, result=grade))
    return result


def _make_normal_trigger(
    conditions: tuple = (),
    target: int = 3,
) -> tuple[NormalFightTrigger, NormalFightPlan]:
    plan: NormalFightPlan = NormalFightPlan(
        factory=lambda _c: object(),
        name='x',
        fleet_id=1,
        target=target,
        conditions=conditions,
    )
    trigger: NormalFightTrigger = NormalFightTrigger(priority=100, name='常规战', plans=[plan])
    return trigger, plan


def test_normal_fight_trigger_counts_condition_met():
    """conditions 计划: 达标场次计数, 打满 target 后停止产出。"""
    from autowsgr.combat import GradeCondition

    trigger, plan = _make_normal_trigger(
        conditions=(GradeCondition(node='F', grade='S'),),
        target=2,
    )
    ctx = _ctx_with_da(None)

    for _ in range(2):
        trigger.should_fire(ctx)
        trigger._on_done(_fight_result('F', 'S'))

    assert plan.completed == 2
    assert trigger.should_fire(ctx) is None  # 打满


def test_normal_fight_trigger_condition_not_met_not_counted():
    """conditions 计划: 不达标场次 (评级不足) 不计数, 触发器继续产出。"""
    from autowsgr.combat import GradeCondition

    trigger, plan = _make_normal_trigger(conditions=(GradeCondition(node='F', grade='S'),))
    ctx = _ctx_with_da(None)

    trigger.should_fire(ctx)
    trigger._on_done(_fight_result('F', 'A'))  # 评级不足

    assert plan.completed == 0
    assert trigger._idle is True
    assert trigger.should_fire(ctx) is not None  # 未达标 → 下轮继续产出


def test_normal_fight_trigger_dock_full_resolved_not_counted_retries():
    """计数污染根治的自愈路径: 解装轮未开打, 不计数; 触发器翻回后重新产出重打。"""
    trigger, plan = _make_normal_trigger(target=3)
    ctx = _ctx_with_da(None)

    trigger.should_fire(ctx)
    trigger._on_done(
        CombatResult(flag=ConditionFlag.DOCK_FULL, dock_full_destroyed=True),
    )

    assert plan.completed == 0  # 未开打, 不计数 (旧版翻 SUCCESS 会 +1)
    assert trigger._idle is True
    assert trigger.should_fire(ctx) is not None  # 下轮重试
    assert trigger._current is plan  # 有限未完成 plan 仍被选中


def test_run_task_dock_full_resolved_round_does_not_consume_times(
    monkeypatch: pytest.MonkeyPatch,
):
    """scheduler: 解装轮不占 times — 解装 1 次 + 真打 3 次, 共 4 次 run 打满 3 轮。"""
    ctx = _FakeCtx()
    sched = TaskScheduler(ctx, expedition_interval=0)  # type: ignore[arg-type]
    monkeypatch.setattr(sched, '_maybe_collect_expedition', lambda: None)

    resolved = CombatResult(flag=ConditionFlag.DOCK_FULL, dock_full_destroyed=True)
    ok = CombatResult(flag=ConditionFlag.OPERATION_SUCCESS)
    seq = [resolved, ok, ok, ok]
    calls: list[int] = []
    runner = _SingleRunner(ok)

    def run() -> CombatResult:
        calls.append(1)
        return seq[len(calls) - 1]

    runner.run = run  # type: ignore[method-assign]
    task = FightTask(runner=runner, times=3)

    sched._run_task(task)

    assert len(calls) == 4
    assert task.completed == 3
    assert task.results == [resolved, ok, ok, ok]


def test_register_normal_fight_passes_condition(monkeypatch: pytest.MonkeyPatch):
    """daily_plan: CombatPlan.condition 镜像到 NormalFightPlan (触发器按条件计数)。"""
    from autowsgr.combat import CombatPlan, GradeCondition
    from autowsgr.infra.config import DailyAutomationConfig
    from autowsgr.ops import normal_fight as nf_mod
    from autowsgr.scheduler.daily_plan import _register_normal_fight

    plan = CombatPlan.from_dict({'node_args': {'F': {'grade': 'S'}}})
    monkeypatch.setattr(nf_mod, 'get_normal_fight_plan', lambda *_a, **_k: plan)

    sched = TaskScheduler(_FakeCtx(), expedition_interval=0)  # type: ignore[arg-type]
    cfg = DailyAutomationConfig(
        auto_normal_fight=True,
        normal_fight_tasks=[{'name': 'x', 'times': 3}],
    )
    _register_normal_fight(sched, cfg)

    trigger = sched._triggers[-1]
    assert trigger._plans[0].conditions == (GradeCondition('F', 'S'),)
