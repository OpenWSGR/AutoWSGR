"""System lifecycle route tests."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from autowsgr.server import main as server_main
from autowsgr.server.routes import system


if TYPE_CHECKING:
    import pytest


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
