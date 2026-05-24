"""测试 autowsgr.server.ws_manager."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock

from autowsgr.server.ws_manager import WebSocketManager


def _asyncio_run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_connect_adds_websocket() -> None:
    manager = WebSocketManager()
    ws = AsyncMock()
    _asyncio_run(manager.connect(ws))
    assert ws in manager._connections
    ws.accept.assert_awaited_once()


def test_disconnect_removes_websocket() -> None:
    manager = WebSocketManager()
    ws = AsyncMock()
    manager._connections.add(ws)
    _asyncio_run(manager.disconnect(ws))
    assert ws not in manager._connections


def test_broadcast_no_connections_is_noop() -> None:
    manager = WebSocketManager()
    _asyncio_run(manager.broadcast({'type': 'test'}))
    assert manager._connections == set()


def test_broadcast_sends_to_all_alive_connections() -> None:
    manager = WebSocketManager()
    ws1 = AsyncMock()
    ws2 = AsyncMock()
    manager._connections.add(ws1)
    manager._connections.add(ws2)
    _asyncio_run(manager.broadcast({'type': 'test'}))
    expected = json.dumps({'type': 'test'}, ensure_ascii=False)
    ws1.send_text.assert_awaited_once_with(expected)
    ws2.send_text.assert_awaited_once_with(expected)
    assert ws1 in manager._connections
    assert ws2 in manager._connections


def test_broadcast_removes_dead_connections() -> None:
    manager = WebSocketManager()
    alive_ws = AsyncMock()
    dead_ws = AsyncMock()
    dead_ws.send_text.side_effect = Exception('connection closed')
    manager._connections.add(alive_ws)
    manager._connections.add(dead_ws)
    _asyncio_run(manager.broadcast({'type': 'test'}))
    expected = json.dumps({'type': 'test'}, ensure_ascii=False)
    alive_ws.send_text.assert_awaited_once_with(expected)
    dead_ws.send_text.assert_awaited_once_with(expected)
    assert alive_ws in manager._connections
    assert dead_ws not in manager._connections


def test_send_log_payload_shape() -> None:
    manager = WebSocketManager()
    object.__setattr__(manager, 'broadcast', AsyncMock())
    _asyncio_run(manager.send_log('INFO', 'hello', channel='main'))
    manager.broadcast.assert_awaited_once()
    payload = manager.broadcast.call_args[0][0]
    assert payload['type'] == 'log'
    assert payload['level'] == 'INFO'
    assert payload['message'] == 'hello'
    assert payload['channel'] == 'main'
    assert 'timestamp' in payload
    assert isinstance(datetime.fromisoformat(payload['timestamp']), datetime)


def test_send_task_update_omits_none_progress_and_result() -> None:
    manager = WebSocketManager()
    object.__setattr__(manager, 'broadcast', AsyncMock())

    _asyncio_run(manager.send_task_update('task-1', 'running'))
    payload = manager.broadcast.call_args_list[0][0][0]
    assert payload['type'] == 'task_update'
    assert payload['task_id'] == 'task-1'
    assert payload['status'] == 'running'
    assert 'progress' not in payload
    assert 'result' not in payload

    _asyncio_run(
        manager.send_task_update(
            'task-2',
            'done',
            progress={'p': 1},
            result={'r': 2},
        )
    )
    payload = manager.broadcast.call_args_list[1][0][0]
    assert payload['progress'] == {'p': 1}
    assert payload['result'] == {'r': 2}


def test_send_task_completed_payload() -> None:
    manager = WebSocketManager()
    object.__setattr__(manager, 'broadcast', AsyncMock())

    _asyncio_run(manager.send_task_completed('task-1', True, result={'ok': True}))
    payload = manager.broadcast.call_args_list[0][0][0]
    assert payload['type'] == 'task_completed'
    assert payload['task_id'] == 'task-1'
    assert payload['success'] is True
    assert payload['result'] == {'ok': True}
    assert payload['error'] is None

    _asyncio_run(manager.send_task_completed('task-2', False, error='oops'))
    payload = manager.broadcast.call_args_list[1][0][0]
    assert payload['success'] is False
    assert payload['error'] == 'oops'
