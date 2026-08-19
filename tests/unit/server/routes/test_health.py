"""测试 autowsgr.server.routes.health."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from autowsgr.server.routes.health import router


@pytest.fixture
def client() -> TestClient:
    """创建包含 health 路由的最小 FastAPI 应用。"""
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_health_check_no_context_no_task(client: TestClient) -> None:
    """无上下文、无任务时应返回基本健康信息。"""
    with (
        patch('autowsgr.server.routes.health._main') as mock_main,
        patch('autowsgr.server.routes.health.task_manager') as mock_task_manager,
    ):
        mock_main._ctx = None
        mock_task_manager.current_task = None
        mock_task_manager.is_running = False

        response = client.get('/api/health')
        assert response.status_code == 200

        data: dict[str, Any] = response.json()
        assert data['success'] is True
        assert data['data']['status'] == 'ok'
        assert data['data']['emulator_connected'] is False
        assert data['data']['current_task'] is None
        assert isinstance(data['data']['uptime_seconds'], int)
        assert data['data']['uptime_seconds'] >= 0


def test_health_check_emulator_connected(client: TestClient) -> None:
    """模拟器已连接时 emulator_connected 应为 True。"""
    with (
        patch('autowsgr.server.routes.health._main') as mock_main,
        patch('autowsgr.server.routes.health.task_manager') as mock_task_manager,
    ):
        mock_main._ctx = object()
        mock_task_manager.current_task = None
        mock_task_manager.is_running = False

        response = client.get('/api/health')
        assert response.status_code == 200

        data: dict[str, Any] = response.json()
        assert data['data']['emulator_connected'] is True
        assert data['data']['current_task'] is None


def test_health_check_with_running_task(client: TestClient) -> None:
    """有正在运行的任务时应返回任务信息。"""
    mock_task = MagicMock()
    mock_task.task_id = 'task_abc123'
    mock_task.status.value = 'running'

    with (
        patch('autowsgr.server.routes.health._main') as mock_main,
        patch('autowsgr.server.routes.health.task_manager') as mock_task_manager,
    ):
        mock_main._ctx = None
        mock_task_manager.current_task = mock_task
        mock_task_manager.is_running = True

        response = client.get('/api/health')
        assert response.status_code == 200

        data: dict[str, Any] = response.json()
        assert data['data']['emulator_connected'] is False
        assert data['data']['current_task'] == {
            'task_id': 'task_abc123',
            'status': 'running',
        }
