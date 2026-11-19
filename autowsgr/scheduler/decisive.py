"""一轮决战在就绪队列中的节点任务、具名维修任务和到期通知。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from autowsgr.infra.logger import get_logger
from autowsgr.scheduler.daily_plan import PRIO_DECISIVE, PRIO_REQUESTED_REPAIR


if TYPE_CHECKING:
    from collections.abc import Callable

    from autowsgr.ops.decisive.controller import DecisiveResult
    from autowsgr.ops.decisive.repair import RepairOutcome
    from autowsgr.scheduler.scheduler import FightTask, TaskScheduler


_log = get_logger('scheduler')


@dataclass(eq=False, slots=True)
class ScheduledAction:
    name: str
    priority: int
    run: Callable[[], None]


class DecisiveRound:
    """同一轮最多各排一个续战和派修；等待维修时只记录下一次唤醒时间。"""

    def __init__(
        self,
        scheduler: TaskScheduler,
        advance: Callable[[], DecisiveResult | None],
        next_repair: Callable[[], RepairOutcome],
        dispatch: Callable[[], RepairOutcome],
        resume: Callable[[RepairOutcome], None],
        park: Callable[[], bool] | None,
    ) -> None:
        self.scheduler = scheduler
        self.advance = advance
        self.next_repair = next_repair
        self.resume = resume
        self.park = park
        self.node = ScheduledAction('决战节点', PRIO_DECISIVE, self._run_node)
        self.repair = ScheduledAction(
            '决战舰船入浴', PRIO_REQUESTED_REPAIR, lambda: self._route(dispatch())
        )
        self.resume_with: RepairOutcome | None = None
        self.wake_at: float | None = None
        self.result: DecisiveResult | None = None
        # 冷启动也可能正停在决战里。第一次让出设备同样先确认现场。
        self.owns_ui = True

    def select(self, head: FightTask | ScheduledAction) -> FightTask | ScheduledAction:
        """只有队首要操作其他页面时才暂离；未到安全页面则先恢复本节点。"""
        if head is not self.node and self.owns_ui:
            if self.park is None or not self.park():
                return self.node
            self.owns_ui = False
        return head

    def _run_node(self) -> None:
        from autowsgr.ops.decisive.controller import DecisiveResult

        self.owns_ui = True
        if self.resume_with is not None:
            action, self.resume_with = self.resume_with, None
            self.resume(action)
        result = self.advance()
        if result in (DecisiveResult.NODE_COMPLETE, DecisiveResult.RETRY):
            self.scheduler._enqueue(self.node)
        elif result is None:
            # 控制器已确认暂离（或通关总览），可以把设备交给其他任务。
            self.owns_ui = False
            self._route(self.next_repair())
        else:
            self.result = result

    def _route(self, action: RepairOutcome) -> None:
        from autowsgr.ops.decisive.controller import DecisiveResult
        from autowsgr.ops.decisive.repair import RepairStatus

        self.wake_at = None
        if action.status is RepairStatus.NEEDS_BATH:
            self.scheduler._enqueue(self.repair)
            if action.resume_immediately:
                self.scheduler._enqueue(self.node)
        elif action.status is RepairStatus.WAITING:
            if action.wait_seconds is None or action.wait_seconds <= 0:
                raise ValueError('缺少有效的决战维修复查时间')
            self.scheduler._discard(self.node)
            self.wake_at = time.monotonic() + action.wait_seconds
            _log.info('[调度] {:.1f} 秒后复查决战维修，等待期间可执行日常任务', action.wait_seconds)
        elif action.status is RepairStatus.STOPPED:
            self.result = DecisiveResult.STOPPED
        else:
            self.resume_with = action
            self.scheduler._enqueue(self.node)

    def wake_if_due(self) -> None:
        if self.wake_at is not None and time.monotonic() >= self.wake_at:
            # 只计算维修结果及入队。所有导航都在对应任务拿到设备后执行。
            self._route(self.next_repair())
