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
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from autowsgr.combat import CombatResult
from autowsgr.infra.logger import get_logger
from autowsgr.types import ConditionFlag


if TYPE_CHECKING:
    from autowsgr.context import GameContext

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
    """

    runner: object
    times: int = 1
    name: str = ''

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
    ) -> None:
        self._ctx = ctx
        self._expedition_interval = expedition_interval
        self._tasks: list[FightTask] = []
        self._last_expedition_time: float = 0.0

    # ── 任务管理 ──

    def add(self, task: FightTask) -> TaskScheduler:
        """添加一个战斗任务。支持链式调用。"""
        self._tasks.append(task)
        _log.info(
            '[Scheduler] 添加任务: {} ×{}',
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
                '[Scheduler] ── 任务 {}/{}: {} ×{} ──',
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
        # 适配返回 list 的 runner
        runner = task.runner
        if not isinstance(runner, FightRunnerProtocol):
            runner = BatchRunnerAdapter(runner)

        for j in range(task.times):
            _log.info(
                '[Scheduler] {} 第 {}/{} 次',
                task.name,
                j + 1,
                task.times,
            )

            # 远征检查 (战斗前)
            self._maybe_collect_expedition()

            try:
                result = runner.run()
            except Exception as exc:
                _log.opt(exception=True).error(
                    '[Scheduler] {} 第 {} 次异常: {}',
                    task.name,
                    j + 1,
                    exc,
                )
                result = CombatResult(flag=ConditionFlag.DOCK_FULL)

            task.results.append(result)
            task.completed += 1

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
