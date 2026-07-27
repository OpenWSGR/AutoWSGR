"""TaskScheduler runner 适配单元测试 (无设备)。

回归: CampaignRunner / ExerciseRunner 的 ``run()`` 返回 ``list[CombatResult]``,
调度器必须经 :class:`BatchRunnerAdapter` 适配为单个结果, 否则 ``on_done`` /
``result.flag`` 会触发 ``'list' object has no attribute 'flag'`` 崩溃。
"""

from __future__ import annotations

import threading
import types

import pytest

from autowsgr.combat import CombatResult
from autowsgr.context import GameContext
from autowsgr.scheduler.scheduler import BatchRunnerAdapter, FightTask, TaskScheduler
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
