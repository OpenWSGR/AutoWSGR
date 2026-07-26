"""auto_daily 触发器 — 决定何时把何种任务插入调度队列。

四类触发器,对应四类日常任务::

    ExpeditionTrigger  (定时, prio 0)   远征: 到点收取+重派, 无限循环
    CampaignTrigger    (条件, prio 5)   战役: 每次一场, BATTLE_TIMES_EXCEED 即停, 跨日 reset
    ExerciseTrigger    (条件, prio 10)  演习: 每次一场, 无可挑战对手即停, 跨时段 reset
    NormalFightTrigger (条件, prio 100) 常规战: 空闲填充, 到掉落/次数上限停, 跨日 reset

设计要点:

- 每个触发器同一时刻最多产出一个 pending 任务 (``_idle`` 标志), 避免队列堆积;
  任务完成后经 ``on_done`` 回调翻回 ``_idle``。
- 战役/演习是「返回标志驱动」的可耗尽触发器 (:class:`ExhaustibleTrigger`):
  runner 返回特定 :class:`~autowsgr.types.ConditionFlag` → 标记 ``_exhausted``,
  不再产出, 直到 ``reset()`` (跨日/跨时段)。
- 常规战不靠返回标志, 而是每次 ``should_fire`` 主动检查全局上限 (``ctx`` 每日计数器)。
- 跨日由 :class:`~autowsgr.scheduler.scheduler.TaskScheduler._check_daily_reset` 调
  ``reset()``;演习跨时段在 ``should_fire`` 内自检。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from autowsgr.infra.logger import get_logger
from autowsgr.scheduler.scheduler import FightTask
from autowsgr.types import ConditionFlag


if TYPE_CHECKING:
    from autowsgr.combat import CombatResult
    from autowsgr.context import GameContext

_log = get_logger('scheduler')

# 任务工厂: 接收 ctx, 返回一个有 run() 方法的 runner
# GameContext 仅运行时在 TYPE_CHECKING 下导入, 此处用字符串前向引用
TaskFactory = Callable[['GameContext'], object]

# 视为「成功打完一场」的标志 (用于常规战计数累加)
_DONE_FLAGS = {
    ConditionFlag.OPERATION_SUCCESS,
    ConditionFlag.FIGHT_END,
    ConditionFlag.SL,
}


# ═══════════════════════════════════════════════════════════════════════════════
# 基类
# ═══════════════════════════════════════════════════════════════════════════════


class Trigger:
    """触发器基类。

    Parameters
    ----------
    priority:
        产出任务的优先级 (数值越小越先执行)。
    name:
        触发器名称 (日志用)。
    task_factory:
        接收 ctx、返回 runner (有 ``run()`` 方法) 的工厂。每次 ``should_fire`` 命中时
        调用, 产出新 runner 包装进 :class:`FightTask`。常规战触发器不用它 (各 plan
        自带工厂), 可留空。
    """

    def __init__(
        self,
        *,
        priority: int,
        name: str,
        task_factory: TaskFactory | None = None,
    ) -> None:
        self.priority = priority
        self.name = name
        self._task_factory = task_factory
        # 同一时刻最多一个 pending 任务, 避免队列堆积
        self._idle = True

    def should_fire(self, ctx: GameContext) -> FightTask | None:
        """是否应产出任务。子类重写, 返回 FightTask 或 None。"""
        raise NotImplementedError

    def reset(self) -> None:
        """跨日/跨时段重置。子类按需重写。"""
        self._idle = True

    def _build_task(
        self,
        ctx: GameContext,
        on_done: Callable[[CombatResult], None] | None = None,
    ) -> FightTask:
        """用 ``task_factory`` 构造一个 FightTask。"""
        if self._task_factory is None:
            raise RuntimeError(f'触发器 {self.name} 未配置 task_factory')
        runner = self._task_factory(ctx)
        return FightTask(
            runner=runner,
            times=1,
            priority=self.priority,
            name=self.name,
            on_done=on_done,
        )


class ExhaustibleTrigger(Trigger):
    """返回标志驱动的可耗尽触发器 (战役/演习)。

    runner 返回的 ``CombatResult.flag`` 若命中 ``exhaust_flags``, 则标记
    ``_exhausted``, 不再产出新任务, 直到 :meth:`reset` (跨日/跨时段)。
    """

    #: 子类定义: 命中这些 flag 即视为本周期打满
    exhaust_flags: ClassVar[set[ConditionFlag]] = set()

    def __init__(
        self,
        *,
        task_factory: TaskFactory,
        priority: int,
        name: str,
    ) -> None:
        super().__init__(priority=priority, name=name, task_factory=task_factory)
        self._exhausted = False

    def should_fire(self, ctx: GameContext) -> FightTask | None:
        if not self._idle or self._exhausted:
            return None
        self._idle = False
        return self._build_task(ctx, on_done=self._on_done)

    def _on_done(self, result: CombatResult) -> None:
        self._idle = True
        if result.flag in self.exhaust_flags:
            self._exhausted = True
            _log.info(
                '[Trigger] {} 本周期已打满 ({}), 停止产出',
                self.name,
                result.flag,
            )

    def reset(self) -> None:
        self._exhausted = False
        self._idle = True


# ═══════════════════════════════════════════════════════════════════════════════
# 定时触发 (远征)
# ═══════════════════════════════════════════════════════════════════════════════


class TimerTrigger(Trigger):
    """定时触发器: 到间隔产出一个任务, 不耗尽 (远征用)。"""

    def __init__(
        self,
        *,
        task_factory: TaskFactory,
        priority: int,
        name: str,
        interval: float,
    ) -> None:
        super().__init__(priority=priority, name=name, task_factory=task_factory)
        self._interval = interval
        self._last_fire = 0.0

    def should_fire(self, ctx: GameContext) -> FightTask | None:
        if not self._idle:
            return None
        if time.monotonic() - self._last_fire < self._interval:
            return None
        self._idle = False
        self._last_fire = time.monotonic()
        return self._build_task(ctx, on_done=self._on_done)

    def _on_done(self, _result: CombatResult) -> None:
        self._idle = True


class ExpeditionTrigger(TimerTrigger):
    """远征触发器: 定时收取 + 重派 (无限循环, 永不耗尽)。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 条件触发 (战役 / 演习)
# ═══════════════════════════════════════════════════════════════════════════════


class CampaignTrigger(ExhaustibleTrigger):
    """战役触发器: ``BATTLE_TIMES_EXCEED`` 即停 (每日次数 8/12 自适应)。"""

    exhaust_flags: ClassVar[set[ConditionFlag]] = {ConditionFlag.BATTLE_TIMES_EXCEED}


class ExerciseTrigger(ExhaustibleTrigger):
    """演习触发器: 无可挑战对手 (``SKIP_FIGHT``) 即停, 跨时段 (0/12/18) reset。

    每日 0/12/18 三个时段各刷新 5 次机会;跨时段时 ``_exhausted`` 清零。
    """

    exhaust_flags: ClassVar[set[ConditionFlag]] = {ConditionFlag.SKIP_FIGHT}

    def __init__(
        self,
        *,
        task_factory: TaskFactory,
        priority: int,
        name: str,
    ) -> None:
        super().__init__(task_factory=task_factory, priority=priority, name=name)
        self._last_slot = self._current_slot()

    @staticmethod
    def _current_slot() -> int:
        """当前演习时段: 0 (0-12点) / 1 (12-18点) / 2 (18-24点)。"""
        hour = time.localtime().tm_hour
        if hour < 12:
            return 0
        if hour < 18:
            return 1
        return 2

    def should_fire(self, ctx: GameContext) -> FightTask | None:
        slot = self._current_slot()
        if slot != self._last_slot:
            _log.info(
                '[Trigger] 演习跨时段 ({}→{}), 重置可挑战次数',
                self._last_slot,
                slot,
            )
            self._exhausted = False
            self._idle = True
            self._last_slot = slot
        return super().should_fire(ctx)


# ═══════════════════════════════════════════════════════════════════════════════
# 条件触发 (常规战 — 空闲填充)
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class NormalFightPlan:
    """常规战单个 plan 的运行时状态。

    Attributes
    ----------
    factory:
        接收 ctx、返回该 plan 的 NormalFightRunner 的工厂。
    name:
        plan 名称 (如 ``8-5AI-only1DD``), 用于日志。
    fleet_id:
        出击舰队编号。
    target:
        本周期目标出击次数。``None`` 表示无限 (空闲填充, 仅受全局上限
        ``stop_max_ship`` / ``stop_max_loot`` / ``quick_repair_limit`` 约束)。
        dev 的 ``DailyAutomationConfig.normal_fight_tasks`` 只给 plan 名、不给次数,
        所以默认 ``None``, 多个无限 plan 会轮询执行。
    completed:
        已成功完成次数 (运行时, 仅日志/有限 plan 的停止判断用)。
    """

    factory: TaskFactory
    name: str
    fleet_id: int
    target: int | None = None
    completed: int = 0


class NormalFightTrigger(Trigger):
    """常规战触发器: 多 plan 列表 + 全局上限, 空闲填充 (priority 最低)。

    每次产出一个未达 ``target`` 的 plan 的任务;全部 plan 达 target, 或 ``ctx``
    每日掉落/船/快修达上限, 则停止产出 (直到 :meth:`reset`)。

    priority 设为最高数值 → 排队尾 → 只有没其他任务时才执行 (= 空闲填充)。
    """

    def __init__(
        self,
        *,
        priority: int,
        name: str,
        plans: list[NormalFightPlan],
        stop_max_ship: bool = False,
        ship_limit: int = 500,
        stop_max_loot: bool = False,
        loot_limit: int = 50,
        quick_repair_limit: int | None = None,
    ) -> None:
        super().__init__(priority=priority, name=name)
        self._plans = plans
        self._stop_max_ship = stop_max_ship
        self._ship_limit = ship_limit
        self._stop_max_loot = stop_max_loot
        self._loot_limit = loot_limit
        self._quick_repair_limit = quick_repair_limit
        self._current: NormalFightPlan | None = None
        # 无限 plan (target=None) 的轮询游标
        self._round_robin = 0

    def should_fire(self, ctx: GameContext) -> FightTask | None:
        if not self._idle:
            return None
        if self._is_exhausted(ctx):
            return None
        plan = self._pick_plan()
        if plan is None:
            return None
        self._idle = False
        self._current = plan
        runner = plan.factory(ctx)
        return FightTask(
            runner=runner,
            times=1,
            priority=self.priority,
            name=f'{self.name}/{plan.name}',
            on_done=self._on_done,
        )

    def _has_plan(self) -> bool:
        """是否有可产出的 plan (无副作用, 供耗尽判断用)。"""
        return any(plan.target is None or plan.completed < plan.target for plan in self._plans)

    def _pick_plan(self) -> NormalFightPlan | None:
        """选下一个 plan: 优先未完成的有 target 的; 再轮询无限的。"""
        for plan in self._plans:
            if plan.target is not None and plan.completed < plan.target:
                return plan
        unlimited = [p for p in self._plans if p.target is None]
        if unlimited:
            plan = unlimited[self._round_robin % len(unlimited)]
            self._round_robin += 1
            return plan
        return None

    def _is_exhausted(self, ctx: GameContext) -> bool:
        """是否本周期常规战已全部完成 / 达上限。"""
        if self._stop_max_ship and ctx.dropped_ship_count >= self._ship_limit:
            return True
        if self._stop_max_loot and ctx.dropped_loot_count >= self._loot_limit:
            return True
        if (
            self._quick_repair_limit is not None
            and ctx.quick_repair_used >= self._quick_repair_limit
        ):
            return True
        return not self._has_plan()

    def _on_done(self, result: CombatResult) -> None:
        self._idle = True
        if self._current is None:
            return
        # 仅成功打完一场才计数 (对齐 classic: SUCCESS/SL 才算)
        if result.flag in _DONE_FLAGS:
            self._current.completed += 1
            target = self._current.target
            progress = (
                f'{self._current.completed}/{target}'
                if target is not None
                else str(self._current.completed)
            )
            _log.info(
                '[Trigger] {} {} 出击 {}',
                self.name,
                self._current.name,
                progress,
            )

    def reset(self) -> None:
        for plan in self._plans:
            plan.completed = 0
        self._idle = True
        self._current = None
        self._round_robin = 0
