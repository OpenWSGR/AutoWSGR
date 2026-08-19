"""测试 autowsgr.server.routes.task."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from autowsgr.server.routes.task import (
    _start_normal_fight,
    router,
    task_start,
)
from autowsgr.server.schemas import (
    CombatPlanRequest,
    NormalFightRequest,
    TaskType,
)


@pytest.fixture
def client() -> TestClient:
    """创建包含 task 路由的最小 FastAPI 应用。"""
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# ═══════════════════════════════════════════════════════════════════════════════
# task_start 端点
# ═══════════════════════════════════════════════════════════════════════════════


def test_task_start_already_running(client: TestClient) -> None:
    """任务已在运行时返回 409。"""
    with patch('autowsgr.server.routes.task.task_manager') as mock_tm:
        mock_tm.is_running = True
        response = client.post('/api/task/start', json={'type': 'normal_fight', 'times': 1})
        assert response.status_code == 409
        assert response.json()['detail'] == '已有任务正在运行'


def test_task_start_no_context(client: TestClient) -> None:
    """无上下文时返回 503。"""
    with (
        patch('autowsgr.server.routes.task.task_manager') as mock_tm,
        patch('autowsgr.server.routes.task.get_context') as mock_get_ctx,
    ):
        mock_tm.is_running = False
        mock_get_ctx.side_effect = RuntimeError('系统未启动，请先调用 POST /api/system/start')
        response = client.post('/api/task/start', json={'type': 'normal_fight', 'times': 1})
        assert response.status_code == 503
        assert '系统未启动' in response.json()['detail']


def test_task_start_unknown_type() -> None:
    """未知任务类型时返回 400（绕过 Pydantic discriminator 直接调用）。"""
    mock_request = MagicMock()
    with (
        patch('autowsgr.server.routes.task.task_manager') as mock_tm,
        patch('autowsgr.server.routes.task.get_context'),
    ):
        mock_tm.is_running = False
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(task_start(mock_request))
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == '未知的任务类型'


@pytest.mark.parametrize(
    ('task_type', 'request_body', 'helper_name'),
    [
        (
            'normal_fight',
            {'type': 'normal_fight', 'times': 2, 'plan_id': 'test_plan'},
            '_start_normal_fight',
        ),
        (
            'event_fight',
            {'type': 'event_fight', 'times': 1, 'plan_id': 'event_plan'},
            '_start_event_fight',
        ),
        (
            'campaign',
            {'type': 'campaign', 'campaign_name': '困难航母', 'times': 1},
            '_start_campaign',
        ),
        (
            'exercise',
            {'type': 'exercise', 'fleet_id': 2},
            '_start_exercise',
        ),
        (
            'decisive',
            {'type': 'decisive', 'chapter': 3, 'decisive_rounds': 2},
            '_start_decisive',
        ),
    ],
)
def test_task_start_valid_types(
    client: TestClient,
    task_type: str,
    request_body: dict[str, Any],
    helper_name: str,
) -> None:
    """各有效任务类型正确分派到对应 helper 并返回 200。"""
    with (
        patch('autowsgr.server.routes.task.get_context') as mock_get_ctx,
        patch('autowsgr.server.routes.task.task_manager') as mock_tm,
        patch(
            f'autowsgr.server.routes.task.{helper_name}',
            new_callable=AsyncMock,
        ) as mock_helper,
    ):
        mock_get_ctx.return_value = MagicMock()
        mock_tm.is_running = False
        mock_helper.return_value = {
            'success': True,
            'data': {'task_id': f'task_{task_type}', 'status': 'running'},
            'message': '任务已启动',
        }

        response = client.post('/api/task/start', json=request_body)
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['data']['task_id'] == f'task_{task_type}'
        assert data['data']['status'] == 'running'
        mock_helper.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════════════════════
# task_stop 端点
# ═══════════════════════════════════════════════════════════════════════════════


def test_task_stop_not_running(client: TestClient) -> None:
    """无运行任务时返回提示消息。"""
    with patch('autowsgr.server.routes.task.task_manager') as mock_tm:
        mock_tm.is_running = False
        response = client.post('/api/task/stop')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['message'] == '没有正在运行的任务'


def test_task_stop_running(client: TestClient) -> None:
    """停止运行中的任务返回 task_id 和 stopped 状态。"""
    mock_task = MagicMock()
    mock_task.task_id = 'task_abc123'

    with patch('autowsgr.server.routes.task.task_manager') as mock_tm:
        mock_tm.is_running = True
        mock_tm.current_task = mock_task
        mock_tm.stop_task.return_value = True

        response = client.post('/api/task/stop')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['data']['task_id'] == 'task_abc123'
        assert data['data']['status'] == 'stopped'
        assert data['message'] == '已请求停止任务'


def test_task_stop_failure(client: TestClient) -> None:
    """停止任务失败时返回 success=False。"""
    with patch('autowsgr.server.routes.task.task_manager') as mock_tm:
        mock_tm.is_running = True
        mock_tm.stop_task.return_value = False

        response = client.post('/api/task/stop')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is False
        assert data['error'] == '停止失败'


# ═══════════════════════════════════════════════════════════════════════════════
# task_status 端点
# ═══════════════════════════════════════════════════════════════════════════════


def test_task_status(client: TestClient) -> None:
    """查询状态返回 task_manager.get_status() 的 ApiResponse 包装。"""
    with patch('autowsgr.server.routes.task.task_manager') as mock_tm:
        mock_tm.get_status.return_value = {
            'task_id': None,
            'status': 'idle',
            'progress': None,
            'result': None,
        }

        response = client.get('/api/task/status')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['data']['status'] == 'idle'
        assert data['data']['task_id'] is None


# ═══════════════════════════════════════════════════════════════════════════════
# _start_normal_fight helper
# ═══════════════════════════════════════════════════════════════════════════════


def test_start_normal_fight_plan_id() -> None:
    """_start_normal_fight 通过 plan_id 解析计划。"""
    request = NormalFightRequest(type=TaskType.NORMAL_FIGHT, plan_id='my_plan', times=1)
    ctx = MagicMock()

    with (
        patch('autowsgr.combat.CombatPlan') as mock_plan_cls,
        patch('autowsgr.ops.run_normal_fight') as mock_run,
        patch('autowsgr.server.routes.task.convert_combat_result') as mock_convert,
        patch('autowsgr.server.routes.task.build_combat_plan') as mock_build,
        patch('autowsgr.server.routes.task.task_manager') as mock_tm,
    ):
        mock_plan = MagicMock()
        mock_plan_cls.from_yaml.return_value = mock_plan
        mock_run.return_value = [MagicMock()]
        mock_convert.return_value = {'round': 1, 'success': True}
        mock_tm.start_task.return_value = 'task_123'
        mock_tm.should_stop.return_value = True  # 立刻终止循环

        result = asyncio.run(_start_normal_fight(ctx, request))
        assert result.success is True
        assert result.data == {'task_id': 'task_123', 'status': 'running'}

        # 运行 executor 验证计划解析逻辑
        executor = mock_tm.start_task.call_args[1]['executor']
        task_info = MagicMock()
        executor(task_info)

        mock_plan_cls.from_yaml.assert_called_once_with('my_plan')
        mock_build.assert_not_called()


def test_start_normal_fight_plan_object() -> None:
    """_start_normal_fight 通过 plan 对象构建计划。"""
    plan_req = CombatPlanRequest(name='test_plan', chapter=2, map=3)
    request = NormalFightRequest(type=TaskType.NORMAL_FIGHT, plan=plan_req, times=1)
    ctx = MagicMock()

    with (
        patch('autowsgr.combat.CombatPlan') as mock_plan_cls,
        patch('autowsgr.ops.run_normal_fight') as mock_run,
        patch('autowsgr.server.routes.task.convert_combat_result') as mock_convert,
        patch('autowsgr.server.routes.task.build_combat_plan') as mock_build,
        patch('autowsgr.server.routes.task.task_manager') as mock_tm,
    ):
        mock_plan = MagicMock()
        mock_build.return_value = mock_plan
        mock_run.return_value = [MagicMock()]
        mock_convert.return_value = {'round': 1, 'success': True}
        mock_tm.start_task.return_value = 'task_456'
        mock_tm.should_stop.return_value = True

        result = asyncio.run(_start_normal_fight(ctx, request))
        assert result.success is True
        assert result.data == {'task_id': 'task_456', 'status': 'running'}

        executor = mock_tm.start_task.call_args[1]['executor']
        task_info = MagicMock()
        executor(task_info)

        mock_build.assert_called_once()
        mock_plan_cls.from_yaml.assert_not_called()


def test_start_normal_fight_missing_plan() -> None:
    """_start_normal_fight 缺少 plan 和 plan_id 时 executor 抛出 ValueError。"""
    request = NormalFightRequest(type=TaskType.NORMAL_FIGHT, times=1)
    ctx = MagicMock()

    with (
        patch('autowsgr.combat.CombatPlan'),
        patch('autowsgr.ops.run_normal_fight'),
        patch('autowsgr.server.routes.task.convert_combat_result'),
        patch('autowsgr.server.routes.task.build_combat_plan'),
        patch('autowsgr.server.routes.task.task_manager') as mock_tm,
    ):
        mock_tm.start_task.return_value = 'task_789'
        mock_tm.should_stop.return_value = True

        result = asyncio.run(_start_normal_fight(ctx, request))
        assert result.success is True

        executor = mock_tm.start_task.call_args[1]['executor']
        task_info = MagicMock()
        with pytest.raises(ValueError, match='必须提供 plan 或 plan_id'):
            executor(task_info)
