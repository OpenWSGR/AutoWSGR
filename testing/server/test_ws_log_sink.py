"""Regression tests for GUI stats log forwarding."""

from __future__ import annotations

import asyncio
import json
import threading
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from fastapi import WebSocketDisconnect

from autowsgr.server import main as server_main
from autowsgr.server.ws_manager import WebSocketManager


if TYPE_CHECKING:
    from collections.abc import Callable

    import pytest


class _FakeLoguru:
    def __init__(self) -> None:
        self.sinks: dict[int, Callable[[Any], None]] = {}
        self.removed: list[int] = []
        self._next_id = 1

    def add(self, sink: Callable[[Any], None], **_: object) -> int:
        sink_id = self._next_id
        self._next_id += 1
        self.sinks[sink_id] = sink
        return sink_id

    def remove(self, sink_id: int) -> None:
        self.removed.append(sink_id)
        if sink_id not in self.sinks:
            raise ValueError('sink has already been removed')
        del self.sinks[sink_id]


class _FakeWebSocket:
    def __init__(self, delivered: asyncio.Event) -> None:
        self.delivered = delivered
        self.messages: list[dict[str, Any]] = []

    async def accept(self) -> None:
        return None

    async def send_text(self, data: str) -> None:
        self.messages.append(json.loads(data))
        self.delivered.set()


class _DisconnectingWebSocket:
    async def receive_text(self) -> str:
        raise WebSocketDisconnect(code=1000)


class _StreamSpy:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def connect(self, _websocket: object, stream: str) -> None:
        self.calls.append(('connect', stream))

    async def disconnect(self, _websocket: object, stream: str) -> None:
        self.calls.append(('disconnect', stream))


def test_ship_drop_sink_reregisters_and_dispatches_from_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A logger reset must not prevent worker-thread ship drops reaching the GUI."""

    async def exercise() -> None:
        manager = WebSocketManager()
        delivered = asyncio.Event()
        websocket = _FakeWebSocket(delivered)
        await manager.connect(websocket, 'logs')  # type: ignore[arg-type]

        loguru = _FakeLoguru()
        monkeypatch.setattr(server_main, '_loguru_logger', loguru)
        monkeypatch.setattr(server_main, 'ws_manager', manager)
        monkeypatch.setattr(server_main, '_stats_sink_id', 7)

        server_main.register_stats_log_sink(asyncio.get_running_loop())
        sink = loguru.sinks[1]
        worker = threading.Thread(
            target=sink,
            args=(
                SimpleNamespace(
                    record={
                        'message': '[Combat] 获得舰船: 测试舰',
                        'level': 'INFO',
                        'extra': {'ch': 'combat.handlers'},
                    }
                ),
            ),
        )
        worker.start()
        try:
            await asyncio.wait_for(delivered.wait(), timeout=1)
        finally:
            worker.join(timeout=1)
            server_main.remove_stats_log_sink()

        assert not worker.is_alive()
        assert loguru.removed == [7, 1]
        assert websocket.messages[0]['type'] == 'log'
        assert websocket.messages[0]['message'] == '[Combat] 获得舰船: 测试舰'
        assert websocket.messages[0]['channel'] == 'combat.handlers'

    asyncio.run(exercise())


def test_messages_stay_within_their_stream() -> None:
    async def exercise() -> None:
        manager = WebSocketManager()
        log_websocket = _FakeWebSocket(asyncio.Event())
        task_websocket = _FakeWebSocket(asyncio.Event())
        await manager.connect(log_websocket, 'logs')  # type: ignore[arg-type]
        await manager.connect(task_websocket, 'task')  # type: ignore[arg-type]

        await manager.send_log('INFO', '[Combat] 获得舰船: 测试舰')
        await manager.send_task_update('task_1', 'running')
        await manager.send_task_completed('task_1', True)

        assert [message['type'] for message in log_websocket.messages] == ['log']
        assert [message['type'] for message in task_websocket.messages] == [
            'task_update',
            'task_completed',
        ]

    asyncio.run(exercise())


def test_websocket_endpoints_use_matching_streams(monkeypatch: pytest.MonkeyPatch) -> None:
    async def exercise() -> None:
        spy = _StreamSpy()
        websocket = _DisconnectingWebSocket()
        monkeypatch.setattr(server_main, 'ws_manager', spy)

        await server_main.ws_logs(websocket)  # type: ignore[arg-type]
        await server_main.ws_task(websocket)  # type: ignore[arg-type]

        assert spy.calls == [
            ('connect', 'logs'),
            ('disconnect', 'logs'),
            ('connect', 'task'),
            ('disconnect', 'task'),
        ]

    asyncio.run(exercise())
