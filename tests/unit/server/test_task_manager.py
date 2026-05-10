"""测试 autowsgr.server.task_manager。"""

from __future__ import annotations

import threading
from typing import Any
from unittest.mock import patch

import pytest

from autowsgr.server.task_manager import (
    TaskInfo,
    TaskManager,
    TaskStatus,
    task_manager,
)


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
        lambda _task: [{'success': True}, {'success': False}],
    )
    assert tm._executor_thread is not None
    tm._executor_thread.join(timeout=2)
    status = tm.get_status()
    assert status['status'] == 'completed'
    assert status['progress'] is None
    assert status['result'] is not None
    assert status['result']['total_runs'] == 2
    assert status['result']['success_runs'] == 1
    assert status.get('error') is None


def test_get_status_failed() -> None:
    """FAILED 状态的 get_status 应包含错误信息。"""
    tm = TaskManager()

    def executor(_task: TaskInfo) -> list[dict[str, Any]]:
        raise ValueError('模拟错误')

    tm.start_task('fight', 2, executor)
    assert tm._executor_thread is not None
    tm._executor_thread.join(timeout=2)
    status = tm.get_status()
    assert status['status'] == 'failed'
    assert status['progress'] is None
    assert status['result'] is None
    assert status['error'] == '模拟错误'


def test_get_status_stopped() -> None:
    """STOPPED 状态的 get_status 应无结果且无错误。"""
    tm = TaskManager()
    started = threading.Event()

    def executor(_task: TaskInfo) -> list[dict[str, Any]]:
        started.set()
        while not tm.should_stop():
            threading.Event().wait(0.01)
        return []

    tm.start_task('fight', 5, executor)
    assert started.wait(timeout=2)
    tm.stop_task()
    assert tm._executor_thread is not None
    tm._executor_thread.join(timeout=2)
    status = tm.get_status()
    assert status['status'] == 'stopped'
    assert status['progress'] is None
    assert status['result'] is None
    assert status.get('error') is None


def test_thread_execution_completes() -> None:
    """线程执行成功时应以 COMPLETED 结束并保存结果。"""
    with patch('autowsgr.server.task_manager.ws_manager'):
        tm = TaskManager()
        tm.start_task('fight', 1, lambda _task: [{'success': True, 'round': 1}])
    assert tm._executor_thread is not None
    tm._executor_thread.join(timeout=2)
    assert tm.current_task is not None
    assert tm.current_task.status == TaskStatus.COMPLETED
    assert tm.current_task.results == [{'success': True, 'round': 1}]
    assert tm.current_task.finished_at is not None


def test_thread_execution_fails() -> None:
    """线程执行抛出异常时应以 FAILED 结束并记录错误。"""
    with patch('autowsgr.server.task_manager.ws_manager'):
        tm = TaskManager()

        def executor(_task: TaskInfo) -> list[dict[str, Any]]:
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

        def executor(_task: TaskInfo) -> list[dict[str, Any]]:
            started.set()
            while not tm.should_stop():
                threading.Event().wait(0.01)
            return []

        tm.start_task('fight', 5, executor)
        assert started.wait(timeout=2)
        tm.stop_task()
    assert tm._executor_thread is not None
    tm._executor_thread.join(timeout=2)
    assert tm.current_task is not None
    assert tm.current_task.status == TaskStatus.STOPPED
    assert tm.current_task.stop_requested is True
    assert tm.current_task.finished_at is not None
