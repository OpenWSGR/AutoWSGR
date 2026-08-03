"""System lifecycle route tests."""

from __future__ import annotations

import asyncio
import sys
import threading
import types

import pytest
from fastapi import HTTPException

from autowsgr.server import main as server_main
from autowsgr.server.routes import system, task
from autowsgr.server.schemas import ExerciseRequest


class _RunningTaskManager:
    is_running = True

    def __init__(self, *, completed: bool) -> None:
        self.completed = completed
        self.stop_requested = False

    def stop_task(self) -> bool:
        self.stop_requested = True
        return True

    def wait_for_completion(self, timeout: float | None = None) -> bool:
        assert timeout is not None
        return self.completed


class _TerminalTaskManager:
    is_running = False

    def __init__(self, *, completed: bool) -> None:
        self.completed = completed
        self.wait_called = False

    def wait_for_completion(self, timeout: float | None = None) -> bool:
        assert timeout is not None
        self.wait_called = True
        return self.completed


class _StoppingTaskManager:
    def __init__(self) -> None:
        self.is_running = True
        self.stop_event = threading.Event()
        self.worker_terminal = threading.Event()
        self.release_wait = threading.Event()

    def stop_task(self) -> bool:
        return True

    def wait_for_completion(self, timeout: float | None = None) -> bool:
        assert timeout is not None
        self.is_running = False
        self.worker_terminal.set()
        return self.release_wait.wait(timeout=timeout)


def test_system_start_publishes_launched_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful start publishes the launched context exactly once."""
    launched_context = object()
    launch_calls: list[str] = []
    scheduler_module = types.ModuleType('autowsgr.scheduler')

    def launch(config_path: str) -> object:
        launch_calls.append(config_path)
        return launched_context

    scheduler_module.launch = launch  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, 'autowsgr.scheduler', scheduler_module)
    monkeypatch.setattr(server_main, '_ctx', None)

    response = asyncio.run(system.system_start(system.SystemStartRequest(config_path='test.yaml')))

    assert response.success is True
    assert launch_calls == ['test.yaml']
    assert server_main._ctx is launched_context


def test_system_start_is_idempotent_when_context_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An already published context is not launched again."""
    ctx = object()
    monkeypatch.setattr(server_main, '_ctx', ctx)

    response = asyncio.run(system.system_start(system.SystemStartRequest()))

    assert response.success is True
    assert response.message == '系统已启动'
    assert server_main._ctx is ctx


def test_system_start_reports_launch_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Launch errors leave the global context unpublished."""
    scheduler_module = types.ModuleType('autowsgr.scheduler')

    def launch(_config_path: str) -> object:
        raise RuntimeError('launch failed')

    scheduler_module.launch = launch  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, 'autowsgr.scheduler', scheduler_module)
    monkeypatch.setattr(server_main, '_ctx', None)

    response = asyncio.run(system.system_start(system.SystemStartRequest()))

    assert response.success is False
    assert response.error == 'launch failed'
    assert server_main._ctx is None


def test_system_stop_keeps_context_when_worker_does_not_finish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stop timeout must not release a context still used by the worker."""
    ctx = object()
    manager = _RunningTaskManager(completed=False)
    monkeypatch.setattr(server_main, '_ctx', ctx)
    monkeypatch.setattr(system, 'task_manager', manager)

    response = asyncio.run(system.system_stop())

    assert manager.stop_requested is True
    assert response.success is False
    assert server_main._ctx is ctx


def test_system_stop_releases_context_after_worker_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The global context is released only after worker termination is confirmed."""
    manager = _RunningTaskManager(completed=True)
    monkeypatch.setattr(server_main, '_ctx', object())
    monkeypatch.setattr(system, 'task_manager', manager)

    response = asyncio.run(system.system_stop())

    assert response.success is True
    assert server_main._ctx is None


def test_system_stop_keeps_context_until_terminal_worker_exits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A terminal task status must not be mistaken for worker termination."""
    ctx = object()
    manager = _TerminalTaskManager(completed=False)
    monkeypatch.setattr(server_main, '_ctx', ctx)
    monkeypatch.setattr(system, 'task_manager', manager)

    response = asyncio.run(system.system_stop())

    assert manager.wait_called is True
    assert response.success is False
    assert server_main._ctx is ctx


def test_task_start_cannot_reuse_context_being_stopped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A new task cannot claim a context already owned by system shutdown."""
    manager = _StoppingTaskManager()
    ctx = type('Context', (), {'stop_event': None})()
    started_contexts: list[object] = []
    monkeypatch.setattr(server_main, '_ctx', ctx)
    monkeypatch.setattr(system, 'task_manager', manager)
    monkeypatch.setattr(task, 'task_manager', manager)

    async def fake_start_exercise(
        received_ctx: object,
        _request: ExerciseRequest,
    ) -> object:
        started_contexts.append(received_ctx)
        return object()

    monkeypatch.setattr(task, '_start_exercise', fake_start_exercise)

    async def run_race() -> None:
        stop_call = asyncio.create_task(system.system_stop())
        assert await asyncio.to_thread(manager.worker_terminal.wait, 1)

        start_call = asyncio.create_task(task.task_start(ExerciseRequest()))
        await asyncio.sleep(0)

        assert start_call.done() is False
        assert started_contexts == []

        manager.release_wait.set()
        stop_response = await stop_call
        assert stop_response.success is True

        with pytest.raises(HTTPException) as exc_info:
            await start_call

        assert exc_info.value.status_code == 503

    asyncio.run(run_race())

    assert server_main._ctx is None
    assert started_contexts == []
