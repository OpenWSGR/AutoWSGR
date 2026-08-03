"""Task manager outcome contract tests."""

from __future__ import annotations

import threading
import time

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
