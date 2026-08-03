"""Task route admission tests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest
from fastapi import HTTPException

from autowsgr.server import main as server_main
from autowsgr.server.routes import task
from autowsgr.server.schemas import (
    CampaignRequest,
    DecisiveRequest,
    EventFightRequest,
    ExerciseRequest,
    NormalFightRequest,
)


@dataclass
class _TaskManager:
    is_running: bool = False
    stop_event: object = field(default_factory=object)


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
