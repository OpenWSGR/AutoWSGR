"""Task manager outcome contract tests."""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any
from unittest.mock import patch

import pytest

from autowsgr.server import task_manager as task_manager_module
from autowsgr.server.device_lease import DeviceOperationBusyError, DeviceOperationLease
from autowsgr.server.task_manager import (
    TaskInfo,
    TaskManager,
    TaskOutcome,
    TaskStatus,
    task_manager,
)


def _wait_until_finished(manager: TaskManager, timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while manager.is_running and time.monotonic() < deadline:
        time.sleep(0.01)
    assert manager.is_running is False


def test_failed_round_marks_task_failed_and_preserves_details() -> None:
    """A handled round failure must not be broadcast as task success."""
    manager = TaskManager()
    failed_round = {'round': 1, 'success': False, 'error': 'fleet change failed'}

    manager.start_task(
        task_type='normal_fight',
        total_rounds=1,
        executor=lambda _task: TaskOutcome.from_results([failed_round]),
    )
    _wait_until_finished(manager)

    assert manager.current_task is not None
    assert manager.current_task.status is TaskStatus.FAILED
    assert manager.current_task.results == [failed_round]
    assert manager.current_task.error == 'fleet change failed'
    assert manager.get_status()['result'] == {
        'total_runs': 1,
        'success_runs': 0,
        'details': [failed_round],
    }


def test_successful_rounds_mark_task_completed() -> None:
    """A task completes only when every returned round succeeded."""
    manager = TaskManager()
    results = [
        {'round': 1, 'success': True},
        {'round': 2, 'success': True},
    ]

    manager.start_task(
        task_type='normal_fight',
        total_rounds=2,
        executor=lambda _task: TaskOutcome.from_results(results),
    )
    _wait_until_finished(manager)

    assert manager.current_task is not None
    assert manager.current_task.status is TaskStatus.COMPLETED
    assert manager.current_task.error is None
    assert manager.get_status()['result'] == {
        'total_runs': 2,
        'success_runs': 2,
        'details': results,
    }


def test_empty_outcome_is_not_synthetic_success() -> None:
    """Returning no rounds without a stop request is an execution failure."""
    manager = TaskManager()

    manager.start_task(
        task_type='normal_fight',
        total_rounds=1,
        executor=lambda _task: TaskOutcome.from_results([]),
    )
    _wait_until_finished(manager)

    assert manager.current_task is not None
    assert manager.current_task.status is TaskStatus.FAILED
    assert manager.current_task.error == '任务未执行任何轮次'


def test_explicit_task_error_overrides_failed_round_error() -> None:
    """An aggregate failure reason must outrank an incidental round error."""
    failed_round = {'round': 1, 'success': False, 'error': 'low-level OCR failure'}

    outcome = TaskOutcome.from_results(
        [failed_round],
        error='决战异常退出',
    )

    assert outcome.results == [failed_round]
    assert outcome.success is False
    assert outcome.error == '决战异常退出'


def test_failed_round_error_is_inferred_without_explicit_task_error() -> None:
    """Existing callers retain first-specific-round error inference."""
    results = [
        {'round': 1, 'success': False},
        {'round': 2, 'success': False, 'error': 'fleet change failed'},
    ]

    outcome = TaskOutcome.from_results(results)

    assert outcome.success is False
    assert outcome.error == 'fleet change failed'


def test_explicit_task_error_explains_empty_result_failure() -> None:
    """An executor can explain why it terminated before producing a round."""
    outcome = TaskOutcome.from_results([], error='决战初始化失败')

    assert outcome.results == []
    assert outcome.success is False
    assert outcome.error == '决战初始化失败'


def test_stop_event_is_exposed_as_read_only_execution_token() -> None:
    """Callers can inject cancellation without reaching into private manager state."""
    manager = TaskManager()

    assert manager.stop_event is manager.stop_event
    assert manager.stop_event.is_set() is False


def test_wait_for_completion_does_not_acknowledge_a_running_worker() -> None:
    """Shutdown callers can distinguish a stop request from actual worker termination."""
    manager = TaskManager()
    worker_started = threading.Event()
    release_worker = threading.Event()

    def executor(_task: object) -> TaskOutcome:
        worker_started.set()
        release_worker.wait(timeout=1)
        return TaskOutcome.from_results([{'round': 1, 'success': True}])

    manager.start_task(task_type='normal_fight', total_rounds=1, executor=executor)
    assert worker_started.wait(timeout=1)
    assert manager.stop_task() is True

    assert manager.wait_for_completion(timeout=0.01) is False
    assert manager.current_task is not None
    assert manager.current_task.status is TaskStatus.RUNNING

    release_worker.set()
    assert manager.wait_for_completion(timeout=1) is True
    assert manager.current_task.status is TaskStatus.STOPPED


def test_task_owns_device_until_worker_exits() -> None:
    """A second task cannot start until the active worker releases the device."""
    lease = DeviceOperationLease()
    first_manager = TaskManager(device_lease=lease)
    second_manager = TaskManager(device_lease=lease)
    worker_started = threading.Event()
    release_worker = threading.Event()

    def blocking_executor(_task: object) -> TaskOutcome:
        worker_started.set()
        release_worker.wait(timeout=1)
        return TaskOutcome.from_results([{'round': 1, 'success': True}])

    first_manager.start_task(
        task_type='normal_fight',
        total_rounds=1,
        executor=blocking_executor,
    )
    assert worker_started.wait(timeout=1)

    with pytest.raises(DeviceOperationBusyError):
        second_manager.start_task(
            task_type='exercise',
            total_rounds=1,
            executor=lambda _task: TaskOutcome.from_results(
                [{'round': 1, 'success': True}],
            ),
        )

    assert second_manager.current_task is None

    release_worker.set()
    assert first_manager.wait_for_completion(timeout=1) is True

    second_manager.start_task(
        task_type='exercise',
        total_rounds=1,
        executor=lambda _task: TaskOutcome.from_results(
            [{'round': 1, 'success': True}],
        ),
    )
    assert second_manager.wait_for_completion(timeout=1) is True


@pytest.mark.parametrize(
    'executor',
    [
        lambda _task: TaskOutcome(results=[], success=False, error='failed'),
        lambda _task: (_ for _ in ()).throw(RuntimeError('crashed')),
    ],
)
def test_task_releases_device_after_failure(executor: object) -> None:
    """Failed outcomes and unexpected exceptions both release ownership."""
    lease = DeviceOperationLease()
    manager = TaskManager(device_lease=lease)

    manager.start_task(
        task_type='normal_fight',
        total_rounds=1,
        executor=executor,  # type: ignore[arg-type]
    )
    assert manager.wait_for_completion(timeout=1) is True

    token = lease.acquire('next-operation')
    lease.release(token)


def test_stop_request_does_not_release_device_before_worker_exit() -> None:
    """Cooperative cancellation retains ownership while code still runs."""
    lease = DeviceOperationLease()
    manager = TaskManager(device_lease=lease)
    worker_started = threading.Event()
    release_worker = threading.Event()

    def executor(_task: object) -> TaskOutcome:
        worker_started.set()
        release_worker.wait(timeout=1)
        return TaskOutcome.from_results([{'round': 1, 'success': True}])

    manager.start_task(task_type='normal_fight', total_rounds=1, executor=executor)
    assert worker_started.wait(timeout=1)
    assert manager.stop_task() is True

    with pytest.raises(DeviceOperationBusyError):
        lease.acquire('next-operation')

    release_worker.set()
    assert manager.wait_for_completion(timeout=1) is True
    token = lease.acquire('next-operation')
    lease.release(token)


def test_thread_start_failure_rolls_back_task_and_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failure to launch the worker cannot publish a task or leak ownership."""
    lease = DeviceOperationLease()
    manager = TaskManager(device_lease=lease)

    def fail_start(_thread: threading.Thread) -> None:
        raise RuntimeError('thread failed')

    monkeypatch.setattr(threading.Thread, 'start', fail_start)

    with pytest.raises(RuntimeError, match='thread failed'):
        manager.start_task(
            task_type='normal_fight',
            total_rounds=1,
            executor=lambda _task: TaskOutcome.from_results([]),
        )

    assert manager.current_task is None
    assert lease.owner is None


def test_stopped_task_exposes_completed_results_in_status_and_notification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancellation preserves completed rounds for polling and WebSocket clients."""
    completed_results = [
        {'round': 1, 'success': True},
        {'round': 2, 'success': True},
    ]
    completion_calls: list[dict[str, Any]] = []
    worker_ready = threading.Event()
    release_worker = threading.Event()

    async def run_scenario() -> tuple[TaskManager, str]:
        notification_sent = asyncio.Event()

        async def record_completion(
            task_id: str,
            success: bool,
            result: dict[str, Any] | None = None,
            error: str | None = None,
        ) -> None:
            completion_calls.append(
                {
                    'task_id': task_id,
                    'success': success,
                    'result': result,
                    'error': error,
                }
            )
            notification_sent.set()

        monkeypatch.setattr(
            task_manager_module.ws_manager,
            'send_task_completed',
            record_completion,
        )
        manager = TaskManager()
        manager.set_loop(asyncio.get_running_loop())

        def executor(_task: object) -> TaskOutcome:
            worker_ready.set()
            release_worker.wait(timeout=1)
            return TaskOutcome.from_results(completed_results)

        task_id = manager.start_task(
            task_type='normal_fight',
            total_rounds=3,
            executor=executor,
        )
        assert await asyncio.to_thread(worker_ready.wait, 1)
        assert manager.stop_task() is True
        assert completion_calls == []

        release_worker.set()
        assert await asyncio.to_thread(manager.wait_for_completion, 1) is True
        await asyncio.wait_for(notification_sent.wait(), timeout=1)
        return manager, task_id

    manager, task_id = asyncio.run(run_scenario())
    expected_result = {
        'total_runs': 3,
        'success_runs': 2,
        'details': completed_results,
    }

    assert manager.get_status()['result'] == expected_result
    assert completion_calls == [
        {
            'task_id': task_id,
            'success': False,
            'result': expected_result,
            'error': None,
        }
    ]


def test_stopped_task_before_first_round_exposes_empty_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancellation before work starts reports an empty result summary, not null."""
    completion_calls: list[dict[str, Any]] = []
    worker_ready = threading.Event()
    release_worker = threading.Event()

    async def run_scenario() -> tuple[TaskManager, str]:
        notification_sent = asyncio.Event()

        async def record_completion(
            task_id: str,
            success: bool,
            result: dict[str, Any] | None = None,
            error: str | None = None,
        ) -> None:
            completion_calls.append(
                {
                    'task_id': task_id,
                    'success': success,
                    'result': result,
                    'error': error,
                }
            )
            notification_sent.set()

        monkeypatch.setattr(
            task_manager_module.ws_manager,
            'send_task_completed',
            record_completion,
        )
        manager = TaskManager()
        manager.set_loop(asyncio.get_running_loop())

        def executor(_task: object) -> TaskOutcome:
            worker_ready.set()
            release_worker.wait(timeout=1)
            return TaskOutcome.from_results([])

        task_id = manager.start_task(
            task_type='normal_fight',
            total_rounds=3,
            executor=executor,
        )
        assert await asyncio.to_thread(worker_ready.wait, 1)
        assert manager.stop_task() is True
        release_worker.set()
        assert await asyncio.to_thread(manager.wait_for_completion, 1) is True
        await asyncio.wait_for(notification_sent.wait(), timeout=1)
        return manager, task_id

    manager, task_id = asyncio.run(run_scenario())
    expected_result = {
        'total_runs': 3,
        'success_runs': 0,
        'details': [],
    }

    assert manager.current_task is not None
    assert manager.current_task.status is TaskStatus.STOPPED
    assert manager.current_task.error is None
    assert manager.get_status()['result'] == expected_result
    assert completion_calls == [
        {
            'task_id': task_id,
            'success': False,
            'result': expected_result,
            'error': None,
        }
    ]


# ==============================================================
# 保留自 tests/unit 结构重构：TaskManager 基础 API 测试
# ==============================================================


def test_task_status_enum_values() -> None:
    """TaskStatus 应包含预期的枚举值。"""
    assert TaskStatus.IDLE.value == 'idle'
    assert TaskStatus.RUNNING.value == 'running'
    assert TaskStatus.COMPLETED.value == 'completed'
    assert TaskStatus.FAILED.value == 'failed'
    assert TaskStatus.STOPPED.value == 'stopped'


def test_task_info_defaults() -> None:
    """TaskInfo 默认值应符合预期。"""
    info = TaskInfo(task_id='t1', task_type='fight')
    assert info.status == TaskStatus.IDLE
    assert isinstance(info.created_at, str)
    assert info.started_at is None
    assert info.finished_at is None
    assert info.current_round == 0
    assert info.total_rounds == 0
    assert info.current_node is None
    assert info.results == []
    assert info.error is None
    assert info.stop_requested is False


def test_task_info_progress() -> None:
    """TaskInfo.progress 应返回正确的进度字典。"""
    info = TaskInfo(
        task_id='t1',
        task_type='fight',
        current_round=3,
        total_rounds=10,
        current_node='B',
    )
    assert info.progress == {'current': 3, 'total': 10, 'node': 'B'}


def test_task_info_result_summary() -> None:
    """TaskInfo.result_summary 应正确统计成功次数并返回详情。"""
    info = TaskInfo(
        task_id='t1',
        task_type='fight',
        total_rounds=5,
        results=[
            {'success': True, 'detail': 'a'},
            {'success': False, 'detail': 'b'},
            {'success': True, 'detail': 'c'},
        ],
    )
    summary = info.result_summary
    assert summary['total_runs'] == 5
    assert summary['success_runs'] == 2
    assert summary['details'] == info.results


def test_task_manager_initial_state() -> None:
    """TaskManager 初始状态应为空闲。"""
    tm = TaskManager()
    assert tm.is_running is False
    assert tm.current_task is None
    status = tm.get_status()
    assert status == {
        'task_id': None,
        'status': 'idle',
        'progress': None,
        'result': None,
    }


def test_task_manager_singleton_exists() -> None:
    """全局 task_manager 单例应为 TaskManager 实例。"""
    assert isinstance(task_manager, TaskManager)


def test_start_task_returns_task_id_and_sets_running() -> None:
    """start_task 应返回 task_id 并将任务设为 RUNNING。"""
    tm = TaskManager()
    started = threading.Event()
    block = threading.Event()

    def executor(_task: TaskInfo) -> list[dict[str, Any]]:
        started.set()
        block.wait(timeout=10)
        return []

    task_id = tm.start_task('normal_fight', 10, executor)
    assert started.wait(timeout=2)
    assert isinstance(task_id, str)
    assert task_id.startswith('task_')
    assert tm.is_running is True
    assert tm.current_task is not None
    assert tm.current_task.status == TaskStatus.RUNNING
    assert tm.current_task.total_rounds == 10
    block.set()
    assert tm._executor_thread is not None
    tm._executor_thread.join(timeout=2)


def test_start_task_raises_when_already_running() -> None:
    """已有任务运行时再次调用 start_task 应抛出 RuntimeError。"""
    tm = TaskManager()
    started = threading.Event()
    block = threading.Event()

    def slow_executor(_task: TaskInfo) -> list[dict[str, Any]]:
        started.set()
        block.wait(timeout=10)
        return []

    tm.start_task('fight', 5, slow_executor)
    assert started.wait(timeout=2)
    with pytest.raises(RuntimeError, match='已有任务正在运行'):
        tm.start_task('fight', 5, lambda _task: [])
    block.set()
    assert tm._executor_thread is not None
    tm._executor_thread.join(timeout=2)


def test_stop_task_when_not_running() -> None:
    """无任务运行时 stop_task 应返回 False。"""
    tm = TaskManager()
    assert tm.stop_task() is False


def test_stop_task_when_running() -> None:
    """任务运行时 stop_task 应返回 True 并设置 stop_requested。"""
    tm = TaskManager()
    started = threading.Event()
    block = threading.Event()

    def executor(_task: TaskInfo) -> list[dict[str, Any]]:
        started.set()
        block.wait(timeout=10)
        return []

    tm.start_task('fight', 5, executor)
    assert started.wait(timeout=2)
    assert tm.stop_task() is True
    assert tm.current_task is not None
    assert tm.current_task.stop_requested is True
    block.set()
    assert tm._executor_thread is not None
    tm._executor_thread.join(timeout=2)
    assert not tm._executor_thread.is_alive()


def test_should_stop_no_task() -> None:
    """无任务时 should_stop 应返回 True。"""
    tm = TaskManager()
    assert tm.should_stop() is True


def test_should_stop_initially_false() -> None:
    """任务启动后 should_stop 应返回 False。"""
    tm = TaskManager()
    started = threading.Event()

    def executor(_task: TaskInfo) -> list[dict[str, Any]]:
        started.set()
        for _ in range(100):
            if tm.should_stop():
                break
            threading.Event().wait(0.01)
        return []

    tm.start_task('fight', 5, executor)
    assert started.wait(timeout=2)
    assert tm.should_stop() is False
    assert tm._executor_thread is not None
    tm._executor_thread.join(timeout=2)


def test_should_stop_after_stop_task() -> None:
    """调用 stop_task 后 should_stop 应返回 True。"""
    tm = TaskManager()
    started = threading.Event()

    def executor(_task: TaskInfo) -> list[dict[str, Any]]:
        started.set()
        while not tm.should_stop():
            threading.Event().wait(0.01)
        return []

    tm.start_task('fight', 5, executor)
    assert started.wait(timeout=2)
    assert tm.should_stop() is False
    tm.stop_task()
    assert tm.should_stop() is True
    assert tm._executor_thread is not None
    tm._executor_thread.join(timeout=2)


def test_update_progress() -> None:
    """update_progress 应更新 current_round 和 current_node。"""
    tm = TaskManager()
    started = threading.Event()
    block = threading.Event()

    def executor(_task: TaskInfo) -> list[dict[str, Any]]:
        started.set()
        block.wait(timeout=10)
        return []

    tm.start_task('fight', 10, executor)
    assert started.wait(timeout=2)
    tm.update_progress(current_round=3, current_node='B')
    assert tm.current_task is not None
    assert tm.current_task.current_round == 3
    assert tm.current_task.current_node == 'B'
    tm.update_progress(current_round=5)
    assert tm.current_task.current_round == 5
    assert tm.current_task.current_node == 'B'
    block.set()
    tm._executor_thread.join(timeout=2)


def test_add_result() -> None:
    """add_result 应向 results 追加元素。"""
    tm = TaskManager()
    started = threading.Event()
    block = threading.Event()

    def executor(_task: TaskInfo) -> list[dict[str, Any]]:
        started.set()
        block.wait(timeout=10)
        return []

    tm.start_task('fight', 5, executor)
    assert started.wait(timeout=2)
    tm.add_result({'success': True, 'round': 1})
    tm.add_result({'success': False, 'round': 2})
    assert tm.current_task is not None
    assert len(tm.current_task.results) == 2
    assert tm.current_task.results[0] == {'success': True, 'round': 1}
    assert tm.current_task.results[1] == {'success': False, 'round': 2}
    block.set()
    tm._executor_thread.join(timeout=2)


def test_get_status_running() -> None:
    """RUNNING 状态的 get_status 应包含进度信息。"""
    tm = TaskManager()
    started = threading.Event()
    block = threading.Event()

    def executor(_task: TaskInfo) -> list[dict[str, Any]]:
        started.set()
        block.wait(timeout=10)
        return []

    tm.start_task('fight', 10, executor)
    assert started.wait(timeout=2)
    tm.update_progress(current_round=3, current_node='B')
    status = tm.get_status()
    assert status['task_id'].startswith('task_')
    assert status['status'] == 'running'
    assert status['progress'] == {'current': 3, 'total': 10, 'node': 'B'}
    assert status['result'] is None
    assert status.get('error') is None
    block.set()
    tm._executor_thread.join(timeout=2)


def test_get_status_completed() -> None:
    """COMPLETED 状态的 get_status 应包含结果摘要。"""
    tm = TaskManager()
    tm.start_task(
        'fight',
        2,
        lambda _task: TaskOutcome.from_results(
            [{'round': 1, 'success': True}, {'round': 2, 'success': True}]
        ),
    )
    assert tm._executor_thread is not None
    tm._executor_thread.join(timeout=2)
    status = tm.get_status()
    assert status['status'] == 'completed'
    assert status['result']['total_runs'] == 2
    assert status['result']['success_runs'] == 2
    assert status.get('error') is None


def test_get_status_failed() -> None:
    """FAILED 状态的 get_status 应包含错误信息。"""
    tm = TaskManager()

    def executor(_task: TaskInfo) -> TaskOutcome:
        raise ValueError('模拟错误')

    tm.start_task('fight', 2, executor)
    assert tm._executor_thread is not None
    tm._executor_thread.join(timeout=2)
    status = tm.get_status()
    assert status['status'] == 'failed'
    assert status['error'] == '模拟错误'


def test_get_status_stopped() -> None:
    """STOPPED 状态的 get_status 应无结果且无错误。"""
    tm = TaskManager()
    started = threading.Event()

    def executor(_task: TaskInfo) -> TaskOutcome:
        started.set()
        while not tm.should_stop():
            threading.Event().wait(0.01)
        return TaskOutcome.from_results([])

    tm.start_task('fight', 5, executor)
    assert started.wait(timeout=2)
    tm.stop_task()
    assert tm._executor_thread is not None
    tm._executor_thread.join(timeout=2)
    status = tm.get_status()
    assert status['status'] == 'stopped'
    assert status.get('error') is None


def test_thread_execution_completes() -> None:
    """线程执行成功时应以 COMPLETED 结束并保存结果。"""
    with patch('autowsgr.server.task_manager.ws_manager'):
        tm = TaskManager()
        tm.start_task(
            'fight',
            1,
            lambda _task: TaskOutcome.from_results([{'round': 1, 'success': True}]),
        )
    assert tm._executor_thread is not None
    tm._executor_thread.join(timeout=2)
    assert tm.current_task is not None
    assert tm.current_task.status == TaskStatus.COMPLETED
    assert tm.current_task.results == [{'round': 1, 'success': True}]
    assert tm.current_task.finished_at is not None


def test_thread_execution_fails() -> None:
    """线程执行抛出异常时应以 FAILED 结束并记录错误。"""
    with patch('autowsgr.server.task_manager.ws_manager'):
        tm = TaskManager()

        def executor(_task: TaskInfo) -> TaskOutcome:
            raise RuntimeError('执行失败')

        tm.start_task('fight', 1, executor)
    assert tm._executor_thread is not None
    tm._executor_thread.join(timeout=2)
    assert tm.current_task is not None
    assert tm.current_task.status == TaskStatus.FAILED
    assert tm.current_task.error == '执行失败'
    assert tm.current_task.finished_at is not None


def test_thread_execution_stops() -> None:
    """线程检测到停止请求后提前返回，任务状态应为 STOPPED。"""
    with patch('autowsgr.server.task_manager.ws_manager'):
        tm = TaskManager()
        started = threading.Event()

        def executor(_task: TaskInfo) -> TaskOutcome:
            started.set()
            while not tm.should_stop():
                threading.Event().wait(0.01)
            return TaskOutcome.from_results([])

        tm.start_task('fight', 5, executor)
        assert started.wait(timeout=2)
        tm.stop_task()
    assert tm._executor_thread is not None
    tm._executor_thread.join(timeout=2)
    assert tm.current_task is not None
    assert tm.current_task.status == TaskStatus.STOPPED
    assert tm.current_task.finished_at is not None
