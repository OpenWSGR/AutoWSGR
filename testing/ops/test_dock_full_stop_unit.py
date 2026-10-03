"""NormalFightTrigger 船坞满停止 (stop_dock_full) 单元测试 (无设备)。

回归: 常规战遇「禁止解装 + 船舱已满」时触发器应停止产出 (autodaily 自动
跳过常规战), 不再无限循环开启下一次任务; ``run_yaml_plan`` 看门狗复用同一
``_is_exhausted`` 判断后整体退出。
"""

from __future__ import annotations

import types

from autowsgr.combat import CombatResult
from autowsgr.scheduler.triggers import NormalFightPlan, NormalFightTrigger
from autowsgr.types import ConditionFlag


def _ctx() -> types.SimpleNamespace:
    """最小 ctx 替身: 未启用 stop_max_* 上限时短路到 _has_plan, 不触碰其它字段。"""
    return types.SimpleNamespace(
        dropped_ship_count=0,
        dropped_loot_count=0,
        quick_repair_used=0,
    )


def _make_trigger(
    *,
    target: int = 3,
    stop_dock_full: bool = True,
) -> tuple[NormalFightTrigger, NormalFightPlan]:
    plan = NormalFightPlan(
        factory=lambda _c: object(),
        name='x',
        fleet_id=1,
        target=target,
    )
    trigger = NormalFightTrigger(
        priority=100,
        name='常规战',
        plans=[plan],
        stop_dock_full=stop_dock_full,
    )
    return trigger, plan


# ── 船坞满停止 (默认开启) ──


def test_dock_full_stopped_when_enabled_not_destroyed():
    """默认 (stop_dock_full=True): DOCK_FULL 且未解装 → 会话级停止, 不再产出。"""
    trigger, plan = _make_trigger()
    ctx = _ctx()
    assert trigger.should_fire(ctx) is not None

    trigger._on_done(CombatResult(flag=ConditionFlag.DOCK_FULL, dock_full_destroyed=False))

    assert trigger.dock_full_stopped is True
    assert trigger._is_exhausted(ctx) is True  # 看门狗复用的同一耗尽判断
    assert trigger.should_fire(ctx) is None  # autodaily 自动跳过常规战


def test_dock_full_stopped_persists_over_repeated_calls():
    """置位后多次 should_fire 持续返回 None, 不再出现 break 后又产出的循环。"""
    trigger, _ = _make_trigger()
    ctx = _ctx()
    assert trigger.should_fire(ctx) is not None  # 先产出 (设置 _current)
    trigger._on_done(CombatResult(flag=ConditionFlag.DOCK_FULL, dock_full_destroyed=False))

    assert trigger.should_fire(ctx) is None
    assert trigger.should_fire(ctx) is None
    assert trigger.should_fire(ctx) is None


# ── 解装成功轮不停止 ──


def test_dock_full_resolved_keeps_producing():
    """解装成功轮 (dock_full_destroyed=True) 不置停止标志, 下轮继续产出重试。"""
    trigger, plan = _make_trigger()
    ctx = _ctx()

    trigger.should_fire(ctx)
    trigger._on_done(CombatResult(flag=ConditionFlag.DOCK_FULL, dock_full_destroyed=True))

    assert trigger.dock_full_stopped is False
    assert plan.completed == 0  # 未开打, 不计数
    assert trigger.should_fire(ctx) is not None  # 下轮重试


# ── 显式关闭 stop_dock_full ──


def test_stop_dock_full_disabled_keeps_old_semantics():
    """stop_dock_full=False: DOCK_FULL 未解装不置停止标志, 保持旧挂机语义。"""
    trigger, _ = _make_trigger(stop_dock_full=False)
    ctx = _ctx()

    assert trigger.should_fire(ctx) is not None  # 先产出 (设置 _current)
    trigger._on_done(CombatResult(flag=ConditionFlag.DOCK_FULL, dock_full_destroyed=False))

    assert trigger.dock_full_stopped is False
    assert trigger._is_exhausted(ctx) is False
    assert trigger.should_fire(ctx) is not None


# ── reset 不清除 (跨日语义) ──


def test_dock_full_stopped_survives_reset():
    """reset() (跨日) 不清除船坞满停止 (物理阻塞不因跨日自动缓解)。"""
    trigger, plan = _make_trigger()
    ctx = _ctx()
    assert trigger.should_fire(ctx) is not None  # 先产出 (设置 _current)
    trigger._on_done(CombatResult(flag=ConditionFlag.DOCK_FULL, dock_full_destroyed=False))

    trigger.reset()

    assert trigger.dock_full_stopped is True
    assert plan.completed == 0  # completed 照常清零
    assert trigger.should_fire(ctx) is None


# ── 有限 plan 耗尽 (看门狗复用 _is_exhausted 的依据) ──


def test_is_exhausted_when_target_met():
    """有限 plan 打满 target → 耗尽, 不再产出。"""
    trigger, plan = _make_trigger(target=2)
    ctx = _ctx()
    assert trigger._is_exhausted(ctx) is False

    plan.completed = 2

    assert trigger._is_exhausted(ctx) is True
    assert trigger.should_fire(ctx) is None


def test_is_exhausted_false_before_target():
    """有限 plan 未达 target → 未耗尽, 仍产出。"""
    trigger, plan = _make_trigger(target=2)
    ctx = _ctx()
    plan.completed = 1

    assert trigger._is_exhausted(ctx) is False
    assert trigger.should_fire(ctx) is not None


# ── AUTO_DAILY 常规战注册默认参数 ──


def test_register_normal_fight_defaults_stop_dock_full():
    """daily_plan 注册常规战触发器默认 stop_dock_full=True (无需显式传入即生效)。"""
    from unittest import mock

    from autowsgr.combat import CombatPlan
    from autowsgr.infra.config import DailyAutomationConfig
    from autowsgr.ops import normal_fight as nf_mod
    from autowsgr.scheduler.daily_plan import _register_normal_fight

    class _FakeScheduler:
        def __init__(self) -> None:
            self._triggers = []

        def register_trigger(self, t: object) -> None:
            self._triggers.append(t)

    plan = CombatPlan.from_dict({})
    cfg = DailyAutomationConfig(
        auto_normal_fight=True,
        normal_fight_tasks=[{'name': 'x', 'times': 3}],
    )

    with mock.patch.object(nf_mod, 'get_normal_fight_plan', return_value=plan):
        sched = _FakeScheduler()
        _register_normal_fight(sched, cfg)  # type: ignore[arg-type]

    trigger = sched._triggers[-1]
    assert isinstance(trigger, NormalFightTrigger)
    assert trigger._stop_dock_full is True
