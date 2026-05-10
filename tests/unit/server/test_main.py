"""测试 autowsgr.server.main。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from autowsgr.server.main import app, get_context


def test_get_context_raises_when_not_started() -> None:
    """未启动时 get_context 应抛出 RuntimeError。"""
    with pytest.raises(RuntimeError, match='系统未启动'):
        get_context()


def test_app_metadata() -> None:
    """FastAPI 应用元数据应正确。"""
    assert app.title == 'AutoWSGR HTTP API'
    assert app.version == '1.0.0'


def test_lifespan_triggers() -> None:
    """TestClient 上下文管理器应触发 lifespan 事件。"""
    with TestClient(app):
        pass  # lifespan 启动/关闭日志已由 loguru 输出


def test_websocket_logs_ping_pong() -> None:
    """/ws/logs 应响应 ping 消息。"""
    with TestClient(app) as client, client.websocket_connect('/ws/logs') as websocket:
        websocket.send_json({'type': 'ping'})
        data = websocket.receive_json()
        assert data['type'] == 'pong'


def test_websocket_task_ping_pong() -> None:
    """/ws/task 应响应 ping 消息。"""
    with TestClient(app) as client, client.websocket_connect('/ws/task') as websocket:
        websocket.send_json({'type': 'ping'})
        data = websocket.receive_json()
        assert data['type'] == 'pong'


def test_routes_registered() -> None:
    """核心路由应已被注册。"""
    routes = [route.path for route in app.routes]
    assert '/api/health' in routes or any('/api/health' in r for r in routes)
