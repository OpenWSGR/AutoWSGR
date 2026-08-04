"""Task manager outcome contract tests."""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any

import pytest

from autowsgr.server import task_manager as task_manager_module
from autowsgr.server.device_lease import DeviceOperationBusyError, DeviceOperationLease
from autowsgr.server.task_manager import TaskManager, TaskOutcome, TaskStatus


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
