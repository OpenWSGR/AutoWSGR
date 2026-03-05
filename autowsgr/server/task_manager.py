"""异步任务管理 — 后台执行战斗任务并管理状态。"""

from __future__ import annotations

import asyncio
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from autowsgr.infra.logger import get_logger
from autowsgr.server.ws_manager import ws_manager


if TYPE_CHECKING:
    from collections.abc import Callable


_log = get_logger('server.task')


class TaskStatus(Enum):
    """任务状态。"""

    IDLE = 'idle'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'
    STOPPED = 'stopped'


@dataclass
class TaskInfo:
    """任务信息。"""

    task_id: str
    task_type: str
    status: TaskStatus = TaskStatus.IDLE
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    started_at: str | None = None
    finished_at: str | None = None

    # 进度
    current_round: int = 0
    total_rounds: int = 0
    current_node: str | None = None

    # 结果
    results: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    # 控制
    stop_requested: bool = False

    @property
    def progress(self) -> dict[str, Any]:
        """返回进度信息。"""
        return {
            'current': self.current_round,
            'total': self.total_rounds,
            'node': self.current_node,
        }

    @property
    def result_summary(self) -> dict[str, Any]:
        """返回结果摘要。"""
        return {
            'total_runs': self.total_rounds,
            'success_runs': len([r for r in self.results if r.get('success', False)]),
            'details': self.results,
        }


class TaskManager:
    """任务管理器。

    管理任务的创建、执行、状态查询和取消。
    所有战斗操作在后台线程执行，避免阻塞事件循环。
    """

    def __init__(self) -> None:
        self._current_task: TaskInfo | None = None
        self._executor_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def current_task(self) -> TaskInfo | None:
        """当前任务。"""
        return self._current_task

    @property
    def is_running(self) -> bool:
        """是否有任务正在运行。"""
        return self._current_task is not None and self._current_task.status == TaskStatus.RUNNING

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """设置事件循环引用，用于从线程中调用 async 函数。"""
        self._loop = loop

    def start_task(
        self,
        task_type: str,
        total_rounds: int,
        executor: Callable[[TaskInfo], list[dict[str, Any]]],
    ) -> str:
        """启动新任务。

        Parameters
        ----------
        task_type:
            任务类型标识
        total_rounds:
            总轮次
        executor:
            执行函数，接收 TaskInfo，返回结果列表

        Returns
        -------
        str
            任务 ID
        """
        with self._lock:
            if self.is_running:
                raise RuntimeError('已有任务正在运行')

            task_id = f'task_{uuid.uuid4().hex[:8]}'
            self._current_task = TaskInfo(
                task_id=task_id,
                task_type=task_type,
                status=TaskStatus.RUNNING,
                total_rounds=total_rounds,
                started_at=datetime.now(UTC).isoformat(),
            )
            self._stop_event.clear()

            # 启动后台线程执行
            self._executor_thread = threading.Thread(
                target=self._run_in_thread,
                args=(executor,),
                daemon=True,
            )
            self._executor_thread.start()

            _log.info('[Task] 启动任务: {} ({})', task_id, task_type)
            return task_id

    def _run_in_thread(
        self,
        executor: Callable[[TaskInfo], list[dict[str, Any]]],
    ) -> None:
        """在后台线程中执行任务。"""
        assert self._current_task is not None
        task = self._current_task

        try:
            results = executor(task)

            # 检查是否被请求停止
            if task.stop_requested:
                task.status = TaskStatus.STOPPED
            else:
                task.status = TaskStatus.COMPLETED
                task.results = results

            task.finished_at = datetime.now(UTC).isoformat()
            _log.info('[Task] 任务完成: {} ({})', task.task_id, task.status.value)

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.finished_at = datetime.now(UTC).isoformat()
            _log.error('[Task] 任务失败: {} - {}', task.task_id, e)

        finally:
            # 通过事件循环发送 WebSocket 通知
            if self._loop:
                asyncio.run_coroutine_threadsafe(
                    self._notify_completion(task),
                    self._loop,
                )

    async def _notify_completion(self, task: TaskInfo) -> None:
        """发送任务完成通知。"""
        success = task.status == TaskStatus.COMPLETED
        result = task.result_summary if success else None
        await ws_manager.send_task_completed(
            task_id=task.task_id,
            success=success,
            result=result,
            error=task.error,
        )

    def stop_task(self) -> bool:
        """请求停止当前任务。"""
        with self._lock:
            if not self.is_running or self._current_task is None:
                return False

            self._current_task.stop_requested = True
            self._stop_event.set()
            _log.info('[Task] 请求停止任务: {}', self._current_task.task_id)
            return True

    def update_progress(
        self,
        current_round: int | None = None,
        current_node: str | None = None,
    ) -> None:
        """更新任务进度 (从执行线程调用)。"""
        if self._current_task is None:
            return

        if current_round is not None:
            self._current_task.current_round = current_round
        if current_node is not None:
            self._current_task.current_node = current_node

        # 通过事件循环发送 WebSocket 更新
        if self._loop:
            asyncio.run_coroutine_threadsafe(
                ws_manager.send_task_update(
                    task_id=self._current_task.task_id,
                    status='running',
                    progress=self._current_task.progress,
                ),
                self._loop,
            )

    def add_result(self, result: dict[str, Any]) -> None:
        """添加一轮结果 (从执行线程调用)。"""
        if self._current_task is None:
            return
        self._current_task.results.append(result)

    def should_stop(self) -> bool:
        """检查是否应该停止 (从执行线程调用)。"""
        if self._current_task is None:
            return True
        return self._current_task.stop_requested

    def get_status(self) -> dict[str, Any]:
        """获取当前任务状态。"""
        if self._current_task is None:
            return {
                'task_id': None,
                'status': TaskStatus.IDLE.value,
                'progress': None,
                'result': None,
            }

        task = self._current_task
        result = None
        if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.STOPPED):
            result = task.result_summary if task.status == TaskStatus.COMPLETED else None

        return {
            'task_id': task.task_id,
            'status': task.status.value,
            'progress': task.progress if task.status == TaskStatus.RUNNING else None,
            'result': result,
            'error': task.error,
        }


# 全局单例
task_manager = TaskManager()
