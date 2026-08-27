"""Regression tests for GUI stats log forwarding."""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest

from autowsgr.server import main as server_main
from autowsgr.server.ws_manager import WebSocketManager


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


def test_ship_drop_sink_reregisters_and_dispatches_from_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A logger reset must not prevent worker-thread ship drops reaching the GUI."""

    async def exercise() -> None:
        manager = WebSocketManager()
        delivered = asyncio.Event()
        websocket = _FakeWebSocket(delivered)
        await manager.connect(websocket)  # type: ignore[arg-type]

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
