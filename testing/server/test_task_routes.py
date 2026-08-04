"""Task route admission tests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pytest
from fastapi import HTTPException

from autowsgr.server import main as server_main
from autowsgr.server.device_lease import DeviceOperationBusyError
from autowsgr.server.routes import task
from autowsgr.server.schemas import (
    CampaignRequest,
    DecisiveRequest,
    EventFightRequest,
    ExerciseRequest,
    NormalFightRequest,
)


if TYPE_CHECKING:
    from collections.abc import Callable

    from autowsgr.server.task_manager import TaskOutcome


@dataclass
class _TaskManager:
    is_running: bool = False
    stop_event: object = field(default_factory=object)


@dataclass
class _ExecutingTaskManager:
    outcome: TaskOutcome | None = None

    def should_stop(self) -> bool:
        return False

    def update_progress(self, **_progress: object) -> None:
        return None

    def add_result(self, _result: dict[str, Any]) -> None:
        return None

    def start_task(
        self,
        task_type: str,
        total_rounds: int,
        executor: Callable[[object], TaskOutcome],
    ) -> str:
        del task_type, total_rounds
        self.outcome = executor(object())
        return 'task_decisive'


def test_task_start_rejects_concurrent_task(monkeypatch: pytest.MonkeyPatch) -> None:
    """Task admission rejects a second running task under the lifecycle lock."""
    monkeypatch.setattr(task, 'task_manager', _TaskManager(is_running=True))

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(task.task_start(ExerciseRequest()))

    assert exc_info.value.status_code == 409


def test_task_start_requires_system_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """Task admission fails after system shutdown removed the context."""
    monkeypatch.setattr(task, 'task_manager', _TaskManager())
    monkeypatch.setattr(server_main, '_ctx', None)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(task.task_start(ExerciseRequest()))

    assert exc_info.value.status_code == 503


def test_task_start_reports_device_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    """Task lease conflicts are returned synchronously as HTTP 409."""
    manager = _TaskManager()
    ctx = type('Context', (), {'stop_event': None})()

    async def busy_start(_ctx: object, _request: ExerciseRequest) -> object:
        raise DeviceOperationBusyError('设备正由 api:repair 使用')

    monkeypatch.setattr(task, 'task_manager', manager)
    monkeypatch.setattr(server_main, '_ctx', ctx)
    monkeypatch.setattr(task, '_start_exercise', busy_start)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(task.task_start(ExerciseRequest()))

    assert exc_info.value.status_code == 409


@pytest.mark.parametrize(
    ('task_request', 'helper_name'),
    [
        (NormalFightRequest(plan_id='plan.yaml'), '_start_normal_fight'),
        (EventFightRequest(plan_id='event.yaml'), '_start_event_fight'),
        (CampaignRequest(campaign_name='困难航母'), '_start_campaign'),
        (ExerciseRequest(), '_start_exercise'),
        (DecisiveRequest(), '_start_decisive'),
    ],
)
def test_task_start_dispatches_request_with_shared_context(
    monkeypatch: pytest.MonkeyPatch,
    task_request: object,
    helper_name: str,
) -> None:
    """Each supported request is admitted with the current context and stop token."""
    manager = _TaskManager()
    ctx = type('Context', (), {'stop_event': None})()
    calls: list[tuple[object, object]] = []
    response = object()

    async def start_helper(received_ctx: object, received_request: object) -> object:
        calls.append((received_ctx, received_request))
        return response

    monkeypatch.setattr(task, 'task_manager', manager)
    monkeypatch.setattr(server_main, '_ctx', ctx)
    monkeypatch.setattr(task, helper_name, start_helper)

    result = asyncio.run(task.task_start(task_request))  # type: ignore[arg-type]

    assert result is response
    assert calls == [(ctx, task_request)]
    assert ctx.stop_event is manager.stop_event


def test_decisive_error_result_marks_task_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A decisive ERROR is a task failure, not a successful completed round."""
    from autowsgr import ops
    from autowsgr.ops import DecisiveResult

    class ErrorController:
        def __init__(self, _ctx: object, _config: object) -> None:
            pass

        def run(self) -> DecisiveResult:
            return DecisiveResult.ERROR

    manager = _ExecutingTaskManager()
    monkeypatch.setattr(task, 'task_manager', manager)
    monkeypatch.setattr(ops, 'DecisiveController', ErrorController)

    asyncio.run(task._start_decisive(object(), DecisiveRequest()))

    assert manager.outcome is not None
    assert manager.outcome.success is False
    assert manager.outcome.error == '决战异常退出'
    assert manager.outcome.results == [
        {
            'round': 1,
            'success': False,
            'result': 'error',
            'error': '决战异常退出',
        }
    ]


def test_decisive_leave_result_remains_successful(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An intentional decisive leave remains a successful terminal result."""
    from autowsgr import ops
    from autowsgr.ops import DecisiveResult

    class LeaveController:
        def __init__(self, _ctx: object, _config: object) -> None:
            pass

        def run(self) -> DecisiveResult:
            return DecisiveResult.LEAVE

    manager = _ExecutingTaskManager()
    monkeypatch.setattr(task, 'task_manager', manager)
    monkeypatch.setattr(ops, 'DecisiveController', LeaveController)

    asyncio.run(task._start_decisive(object(), DecisiveRequest()))

    assert manager.outcome is not None
    assert manager.outcome.success is True
    assert manager.outcome.error is None
    assert manager.outcome.results == [{'round': 1, 'success': True, 'result': 'leave'}]
