"""基础任务调度器 — 按顺序执行提交的战斗任务，定时插入远征检查。

使用方式::

    from autowsgr.scheduler import launch, TaskScheduler, FightTask

    ctx = launch("user_settings.yaml")

    scheduler = TaskScheduler(ctx, expedition_interval=15 * 60)
    scheduler.add(FightTask(runner=my_event_runner, times=30))
    scheduler.add(FightTask(runner=my_normal_runner, times=5))
    scheduler.run()

调度逻辑:

1. 按提交顺序依次执行每个 ``FightTask``
2. 每个 task 内循环执行 ``runner.run()``，直到达到指定次数或船坞满
3. 每次战斗完成后检查距上次远征收取是否超过 ``expedition_interval``，
   若超过则插入一次 ``collect_expedition``
4. 所有 task 执行完毕后调度器退出
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from autowsgr.combat import CombatResult
from autowsgr.infra.logger import get_logger
from autowsgr.types import ConditionFlag


if TYPE_CHECKING:
    from collections.abc import Callable

    from autowsgr.context import GameContext
    from autowsgr.scheduler.triggers import Trigger

_log = get_logger('scheduler')


# ═══════════════════════════════════════════════════════════════════════════════
# Runner 协议
# ═══════════════════════════════════════════════════════════════════════════════


@runtime_checkable
class FightRunnerProtocol(Protocol):
    """所有战斗执行器的公共协议。

    要求实现 ``run() → CombatResult``。
    :class:`EventFightRunner`, :class:`NormalFightRunner` 天然满足。
    :class:`CampaignRunner`, :class:`ExerciseRunner` 返回 ``list[CombatResult]``，
    需要通过 :class:`BatchRunnerAdapter` 适配。
    """

    def run(self) -> CombatResult: ...


class BatchRunnerAdapter:
    """将 ``run() → list[CombatResult]`` 的 runner 适配为单次协议。

    适用于 :class:`CampaignRunner` (内部自带循环，每次 ``run()`` 已执行多场)
    和 :class:`ExerciseRunner`。

    每次 ``.run()`` 返回最后一场结果；若列表为空，返回默认成功。
    """

    def __init__(self, inner: object) -> None:
        if not hasattr(inner, 'run'):
            raise TypeError(f'{type(inner).__name__} 没有 run() 方法')
        self._inner = inner

    def run(self) -> CombatResult:
        results = self._inner.run()  # type: ignore[union-attr]
        if isinstance(results, list):
            return (
                results[-1]
                if results
                else CombatResult(
                    flag=ConditionFlag.OPERATION_SUCCESS,
                )
            )
        return results  # type: ignore[return-value]


# ═══════════════════════════════════════════════════════════════════════════════
# 战斗任务
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class FightTask:
    """一个战斗任务。

    Parameters
    ----------
    runner:
        战斗执行器实例。需满足 ``run() → CombatResult`` 协议。
        对于 ``CampaignRunner`` / ``ExerciseRunner``（返回 list），
        可传原始 runner，调度器会自动包装。
    times:
        执行次数。``CampaignRunner`` 自带 times 时此处设 1 即可。
    name:
        任务名称（用于日志），留空则自动推导。
    priority:
        优先级（数值越小越先执行），用于 ``run_daily`` 触发器队列排序。默认 50。
    on_done:
        每场战斗结束后的回调（接收 ``CombatResult``）。触发器用它更新
        ``_idle`` / ``_exhausted`` 等内部状态。
    """

    runner: object
    times: int = 1
    name: str = ''
    priority: int = 50
    on_done: Callable[[CombatResult], None] | None = None

    # 运行时状态
    completed: int = field(default=0, init=False, repr=False)
    results: list[CombatResult] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.name:
            self.name = type(self.runner).__name__


# ═══════════════════════════════════════════════════════════════════════════════
# 调度器
# ═══════════════════════════════════════════════════════════════════════════════


class TaskScheduler:
    """基础任务调度器。

    Parameters
    ----------
    ctx:
        游戏上下文 (用于远征检查)。
    expedition_interval:
        远征检查间隔 (秒)。默认 ``900`` (15 分钟)。
        设为 ``0`` 或负数则禁用自动远征。
    """

    def __init__(
        self,
        ctx: GameContext,
        *,
        expedition_interval: float = 900.0,
        idle_sleep: float = 5.0,
    ) -> None:
        self._ctx = ctx
        self._expedition_interval = expedition_interval
        self._idle_sleep = idle_sleep
        self._tasks: list[FightTask] = []
        self._last_expedition_time: float = 0.0
        # 触发器调度 (auto_daily 长期挂机)
        self._triggers: list[Trigger] = []
        self._queue: list[FightTask] = []
        self._last_date: date = date.today()  # noqa: DTZ011  # 跨日按本地墙上时钟 (游戏 0 点刷新)

    # ── 任务管理 ──

    def add(self, task: FightTask) -> TaskScheduler:
        """添加一个战斗任务。支持链式调用。"""
        self._tasks.append(task)
        _log.info(
            '[Scheduler] 添加任务: {} x{}',
            task.name,
            task.times,
        )
        return self

    @property
    def tasks(self) -> list[FightTask]:
        """当前任务列表 (只读副本)。"""
        return list(self._tasks)

    # ── 执行 ──

    def run(self) -> list[FightTask]:
        """按顺序执行所有任务。

        Returns
        -------
        list[FightTask]
            执行完毕的任务列表 (包含结果)。
        """
        if not self._tasks:
            _log.warning('[Scheduler] 无任务，直接退出')
            return []

        _log.info(
            '[Scheduler] 开始调度: {} 个任务',
            len(self._tasks),
        )
        self._last_expedition_time = time.monotonic()

        for i, task in enumerate(self._tasks):
            _log.info(
                '[Scheduler] ── 任务 {}/{}: {} x{} ──',
                i + 1,
                len(self._tasks),
                task.name,
                task.times,
            )
            self._run_task(task)

        self._print_summary()
        return list(self._tasks)

    def _run_task(self, task: FightTask) -> None:
        """执行单个任务的全部轮次。"""
        # 统一用 BatchRunnerAdapter 包装: 对 run()→list[CombatResult] 取最后一场,
        # 对 run()→单个 CombatResult 直接 passthrough, 兼容两类 runner
        # (CampaignRunner / ExerciseRunner 返回 list, 其余返回单个)。
        # 不能靠 isinstance(FightRunnerProtocol) 判断: @runtime_checkable 不检查
        # 返回类型, CampaignRunner 有 run() 方法即被误判满足协议而跳过适配
        # (曾致战役 on_done 回调 'list' object has no attribute 'flag' 崩溃)。
        runner = BatchRunnerAdapter(task.runner)

        self._ctx.active_fight_tasks += 1
        try:
            for j in range(task.times):
                if self._ctx.stop_event.is_set():
                    _log.info('[Scheduler] {} 检测到停止信号, 中断', task.name)
                    break

                _log.info(
                    '[Scheduler] {} 第 {}/{} 次',
                    task.name,
                    j + 1,
                    task.times,
                )

                # 远征检查 (战斗前) — 仅旧 run() 路径有效;run_daily() 下由触发器接管
                self._maybe_collect_expedition()

                try:
                    result = runner.run()
                except Exception as exc:
                    # 子任务异常: 结束本子任务, 不崩溃主循环。ACTION_FAILED 不属
                    # 于任何触发器的成功/耗尽标志, 故 on_done 不会计入战斗次数、
                    # 不会误判耗尽 —— 远征出错等下次定时重试, 战斗出错不扣次数。
                    _log.opt(exception=True).error(
                        '[Scheduler] {} 第 {} 次异常, 结束本子任务: {}',
                        task.name,
                        j + 1,
                        exc,
                    )
                    result = CombatResult(flag=ConditionFlag.ACTION_FAILED)

                task.results.append(result)
                task.completed += 1

                # 通知触发器更新状态 (auto_daily 触发器调度用)
                if task.on_done is not None:
                    try:
                        task.on_done(result)
                    except Exception as exc:
                        _log.opt(exception=True).warning(
                            '[Scheduler] {} on_done 回调异常: {}',
                            task.name,
                            exc,
                        )

                _log.info(
                    '[Scheduler] {} [{}/{}] → {}',
                    task.name,
                    task.completed,
                    task.times,
                    result.flag.value if result.flag else 'N/A',
                )

                # 船坞满则停止当前任务
                if result.flag == ConditionFlag.DOCK_FULL:
                    _log.warning(
                        '[Scheduler] {} 船坞已满, 跳过剩余 {} 次',
                        task.name,
                        task.times - task.completed,
                    )
                    break
        finally:
            self._ctx.active_fight_tasks -= 1

    # ═══════════════════════════════════════════════════════════════════════════════
    # 触发器调度 (auto_daily 长期挂机)
    # ═══════════════════════════════════════════════════════════════════════════════

    def register_trigger(self, trigger: Trigger) -> TaskScheduler:
        """注册一个触发器。支持链式调用。"""
        self._triggers.append(trigger)
        _log.info(
            '[Scheduler] 注册触发器: {} (prio={})',
            trigger.name,
            trigger.priority,
        )
        return self

    def run_daily(self) -> None:
        """触发器驱动的长期挂机主循环 (auto_daily)。

        循环逻辑::

            while not stop_event:
                1. 检测跨日 → reset 所有触发器 (战役 _exhausted / 常规战计数清零)
                2. 询问每个触发器 should_fire → 命中的任务按 priority 入队
                3. 队首有任务 → 执行;队列空 → idle_sleep 后继续 (挂机等待)

        与 :meth:`run` 的区别:后者顺序执行预提交任务后退出;
        本方法由触发器持续产出任务,适合全天 / 跨日挂机。
        """
        _log.info(
            '[Scheduler] 开始触发器调度: {} 个触发器',
            len(self._triggers),
        )
        self._last_date = date.today()  # noqa: DTZ011  # 本地墙上时钟
        # 启动时校准每日掉落计数器 (避免首次常规战误触发, 见 _sync_initial_counts)
        self._sync_initial_counts()

        while not self._ctx.stop_event.is_set():
            self._check_daily_reset()

            # 收集触发器产出的新任务
            for trigger in self._triggers:
                try:
                    task = trigger.should_fire(self._ctx)
                except Exception as exc:
                    _log.opt(exception=True).warning(
                        '[Scheduler] 触发器 {} 异常: {}',
                        trigger.name,
                        exc,
                    )
                    continue
                if task is not None:
                    self._enqueue(task)

            # 取队首执行
            task = self._dequeue()
            if task is not None:
                try:
                    self._run_task(task)
                except Exception as exc:
                    # _run_task 自身异常 (非 runner.run, 极少见) 兜底: 复位触发器
                    # _idle 避免该触发器卡死不再产出, 继续主循环, 不崩溃脚本。
                    _log.opt(exception=True).error(
                        '[Scheduler] 子任务 {} 执行崩溃, 已跳过: {}',
                        task.name,
                        exc,
                    )
                    if task.on_done is not None:
                        try:
                            task.on_done(
                                CombatResult(flag=ConditionFlag.ACTION_FAILED),
                            )
                        except Exception:  # noqa: S110  # on_done 回调异常不应影响主循环
                            pass
            else:
                # 队列空:所有触发器暂无任务 (常规战打满 / 只等远征定时) → 挂机等待
                time.sleep(self._idle_sleep)

        _log.info('[Scheduler] 收到停止信号, 调度结束')
        self._print_summary()

    def _enqueue(self, task: FightTask) -> None:
        """按 priority 插入队列 (数值小先出;同 priority FIFO)。"""
        idx = len(self._queue)
        for i, existing in enumerate(self._queue):
            if existing.priority > task.priority:
                idx = i
                break
        self._queue.insert(idx, task)
        _log.debug(
            '[Scheduler] 入队: {} (prio={}, 队列长度={})',
            task.name,
            task.priority,
            len(self._queue),
        )

    def _dequeue(self) -> FightTask | None:
        """取出队首任务 (priority 最小者)。"""
        if not self._queue:
            return None
        return self._queue.pop(0)

    def _check_daily_reset(self) -> None:
        """检测跨日 (0 点) → 通知所有触发器 reset。

        游戏每日 0 点刷新战役次数、演习时段、掉落上限。
        大部分由游戏自身重置 (脚本每次读画面值);脚本只需 reset 自身状态
        (战役 _exhausted、常规战完成计数、ctx 每日计数器)。
        """
        today = date.today()  # noqa: DTZ011  # 本地墙上时钟 (跨日检测)
        if today == self._last_date:
            return
        _log.info(
            '[Scheduler] 检测到跨日 ({} → {}), 重置触发器',
            self._last_date,
            today,
        )
        for trigger in self._triggers:
            try:
                trigger.reset()
            except Exception as exc:
                _log.opt(exception=True).warning(
                    '[Scheduler] 触发器 {} reset 异常: {}',
                    trigger.name,
                    exc,
                )
        # 清零 ctx 每日计数器 (掉落 / 快修累计)
        self._ctx.dropped_ship_count = 0
        self._ctx.dropped_loot_count = 0
        self._ctx.quick_repair_used = 0
        self._last_date = today

    # ── 启动校准 ──

    def _sync_initial_counts(self) -> None:
        """启动时校准每日掉落计数器, 避免常规战误触发。

        仅当启用了 ``stop_max_ship`` / ``stop_max_loot`` (二者依赖 ``ctx`` 每日
        计数器判断是否达上限) 时执行; 否则跳过 (常规战无限打, 计数器无需校准)。

        ``ctx.dropped_ship_count`` / ``dropped_loot_count`` 初始为 0; 若不同步,
        首次 :meth:`NormalFightTrigger.should_fire` 会因 ``0 >= limit`` 为假而误
        产出一场常规战 (即使游戏内已达上限)。

        校准失败 (OCR 引擎不可用 / 导航异常) **不降级** —— 战斗未必掉落, 降级
        靠首场战斗自行校准不可靠 (计数器可能一直为 0 → 持续误触发)。改为直接
        禁用依赖计数器的常规战触发器并提示用户, 不阻塞主循环。
        """
        da = self._ctx.config.daily_automation
        if da is None or not (da.stop_max_ship or da.stop_max_loot):
            return
        try:
            self._ctx.sync_daily_drop_counts()
        except Exception as exc:
            _log.opt(exception=True).error(
                '[Scheduler] 每日掉落计数器校准失败, 已禁用常规战触发器以避免误触发: {}',
                exc,
            )
            _log.error(
                '[Scheduler] 请检查 OCR 引擎 (ocr_backend) 与截图/导航是否正常后重启脚本',
            )
            self._disable_normal_fight(reason=str(exc))

    def _disable_normal_fight(self, reason: str) -> None:
        """禁用所有常规战触发器 (计数器无法校准时, 避免误触发)。"""
        from autowsgr.scheduler.triggers import NormalFightTrigger

        for trigger in self._triggers:
            if isinstance(trigger, NormalFightTrigger):
                trigger.disable(reason=reason)

    # ── 远征检查 ──

    def _maybe_collect_expedition(self) -> None:
        """若距上次远征检查超过 interval，执行一次收取。"""
        if self._expedition_interval <= 0:
            return

        elapsed = time.monotonic() - self._last_expedition_time
        if elapsed < self._expedition_interval:
            return

        _log.info(
            '[Scheduler] 远征检查 (距上次 {:.0f}s)',
            elapsed,
        )
        try:
            from autowsgr.ops.expedition import collect_expedition

            collect_expedition(self._ctx)
        except Exception as exc:
            _log.opt(exception=True).warning(
                '[Scheduler] 远征检查失败: {}',
                exc,
            )

        self._last_expedition_time = time.monotonic()

    # ── 汇总 ──

    def _print_summary(self) -> None:
        """打印执行汇总。"""
        _log.info('[Scheduler] ' + '=' * 50)
        _log.info('[Scheduler] 调度完成')

        total_fights = 0
        total_success = 0

        for task in self._tasks:
            success = sum(1 for r in task.results if r.flag == ConditionFlag.OPERATION_SUCCESS)
            total_fights += task.completed
            total_success += success
            _log.info(
                '[Scheduler]   {} : {}/{} 完成, {} 成功',
                task.name,
                task.completed,
                task.times,
                success,
            )

        _log.info(
            '[Scheduler] 总计: {} 场战斗, {} 成功',
            total_fights,
            total_success,
        )
        _log.info('[Scheduler] ' + '=' * 50)
