"""测试 autowsgr.server.routes.ops."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from autowsgr.server.routes.ops import router


@pytest.fixture
def client() -> TestClient:
    """创建包含 ops 路由的最小 FastAPI 应用。"""
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestRequireIdle:
    """_require_idle 行为测试。"""

    @patch('autowsgr.server.routes.ops.task_manager')
    def test_raises_409_when_running(self, mock_task_manager: MagicMock) -> None:
        """任务执行中时应抛出 409。"""
        from fastapi import HTTPException

        from autowsgr.server.routes.ops import _require_idle

        mock_task_manager.is_running = True
        with pytest.raises(HTTPException) as exc_info:
            _require_idle()
        assert exc_info.value.status_code == 409
        assert '任务执行中' in exc_info.value.detail


class TestExpeditionCheck:
    """POST /api/expedition/check 测试。"""

    @patch('autowsgr.server.routes.ops.get_context')
    def test_503_no_context(self, mock_get_context: MagicMock, client: TestClient) -> None:
        """无上下文时返回 503。"""
        mock_get_context.side_effect = RuntimeError('context not initialized')

        response = client.post('/api/expedition/check')

        assert response.status_code == 503
        assert 'context not initialized' in response.json()['detail']

    @patch('autowsgr.server.routes.ops.task_manager')
    @patch('autowsgr.server.routes.ops.get_context')
    def test_409_busy(
        self,
        mock_get_context: MagicMock,
        mock_task_manager: MagicMock,
        client: TestClient,
    ) -> None:
        """任务执行中时返回 409。"""
        mock_get_context.return_value = MagicMock()
        mock_task_manager.is_running = True

        response = client.post('/api/expedition/check')

        assert response.status_code == 409

    @patch('autowsgr.ops.expedition.collect_expedition')
    @patch('autowsgr.server.routes.ops.task_manager')
    @patch('autowsgr.server.routes.ops.get_context')
    def test_success(
        self,
        mock_get_context: MagicMock,
        mock_task_manager: MagicMock,
        mock_collect: MagicMock,
        client: TestClient,
    ) -> None:
        """正常收取远征。"""
        mock_get_context.return_value = MagicMock()
        mock_task_manager.is_running = False
        mock_collect.return_value = 3

        response = client.post('/api/expedition/check')
        data: dict[str, Any] = response.json()

        assert response.status_code == 200
        assert data['success'] is True
        assert data['data']['collected'] == 3
        assert '远征检查完成' in data['message']
        mock_collect.assert_called_once()


class TestExpeditionAutoCheck:
    """POST /api/expedition/auto_check 测试。"""

    @patch('autowsgr.server.routes.ops.get_context')
    def test_503_no_context(self, mock_get_context: MagicMock, client: TestClient) -> None:
        """无上下文时返回 503。"""
        mock_get_context.side_effect = RuntimeError('context not initialized')

        response = client.post('/api/expedition/auto_check', json={})

        assert response.status_code == 503

    @patch('autowsgr.ops.repair.repair_in_bath')
    @patch('autowsgr.ops.reward.collect_rewards')
    @patch('autowsgr.ops.expedition.collect_expedition')
    @patch('autowsgr.server.routes.ops.task_manager')
    @patch('autowsgr.server.routes.ops.get_context')
    def test_repair_skipped_when_task_running(
        self,
        mock_get_context: MagicMock,
        mock_task_manager: MagicMock,
        mock_collect_exp: MagicMock,
        mock_collect_rew: MagicMock,
        mock_repair: MagicMock,
        client: TestClient,
    ) -> None:
        """有战斗任务运行时跳过维修。"""
        mock_get_context.return_value = MagicMock()
        mock_task_manager.is_running = True
        mock_collect_exp.return_value = 2
        mock_collect_rew.return_value = 5

        response = client.post('/api/expedition/auto_check', json={'allow_repair': True})
        data: dict[str, Any] = response.json()

        assert response.status_code == 200
        assert data['success'] is True
        assert data['data']['repair_skipped'] is True
        assert data['data']['repair_reason'] == '战斗任务进行中'
        mock_repair.assert_not_called()

    @patch('autowsgr.ops.repair.repair_in_bath')
    @patch('autowsgr.ops.reward.collect_rewards')
    @patch('autowsgr.ops.expedition.collect_expedition')
    @patch('autowsgr.server.routes.ops.task_manager')
    @patch('autowsgr.server.routes.ops.get_context')
    def test_repair_skipped_when_not_allowed(
        self,
        mock_get_context: MagicMock,
        mock_task_manager: MagicMock,
        mock_collect_exp: MagicMock,
        mock_collect_rew: MagicMock,
        mock_repair: MagicMock,
        client: TestClient,
    ) -> None:
        """allow_repair=False 时跳过维修。"""
        mock_get_context.return_value = MagicMock()
        mock_task_manager.is_running = False
        mock_collect_exp.return_value = 2
        mock_collect_rew.return_value = 5

        response = client.post('/api/expedition/auto_check', json={'allow_repair': False})
        data: dict[str, Any] = response.json()

        assert response.status_code == 200
        assert data['success'] is True
        assert data['data']['repair_skipped'] is True
        assert data['data']['repair_reason'] == '队列中有后续战斗任务'
        mock_repair.assert_not_called()

    @patch('autowsgr.ops.repair.repair_in_bath')
    @patch('autowsgr.ops.reward.collect_rewards')
    @patch('autowsgr.ops.expedition.collect_expedition')
    @patch('autowsgr.server.routes.ops.task_manager')
    @patch('autowsgr.server.routes.ops.get_context')
    def test_repair_runs_when_allowed(
        self,
        mock_get_context: MagicMock,
        mock_task_manager: MagicMock,
        mock_collect_exp: MagicMock,
        mock_collect_rew: MagicMock,
        mock_repair: MagicMock,
        client: TestClient,
    ) -> None:
        """allow_repair=True 且无任务时执行维修。"""
        mock_get_context.return_value = MagicMock()
        mock_task_manager.is_running = False
        mock_collect_exp.return_value = 2
        mock_collect_rew.return_value = 5

        response = client.post('/api/expedition/auto_check', json={'allow_repair': True})
        data: dict[str, Any] = response.json()

        assert response.status_code == 200
        assert data['success'] is True
        assert data['data']['repair'] is True
        assert 'repair_skipped' not in data['data']
        mock_repair.assert_called_once()


class TestBuildCollect:
    """POST /api/build/collect 测试。"""

    @patch('autowsgr.server.routes.ops.get_context')
    def test_503_no_context(self, mock_get_context: MagicMock, client: TestClient) -> None:
        """无上下文时返回 503。"""
        mock_get_context.side_effect = RuntimeError('context not initialized')

        response = client.post('/api/build/collect')

        assert response.status_code == 503

    @patch('autowsgr.server.routes.ops.task_manager')
    @patch('autowsgr.server.routes.ops.get_context')
    def test_409_busy(
        self,
        mock_get_context: MagicMock,
        mock_task_manager: MagicMock,
        client: TestClient,
    ) -> None:
        """任务执行中时返回 409。"""
        mock_get_context.return_value = MagicMock()
        mock_task_manager.is_running = True

        response = client.post('/api/build/collect')

        assert response.status_code == 409

    @patch('autowsgr.ops.collect_built_ships')
    @patch('autowsgr.server.routes.ops.task_manager')
    @patch('autowsgr.server.routes.ops.get_context')
    def test_success(
        self,
        mock_get_context: MagicMock,
        mock_task_manager: MagicMock,
        mock_collect: MagicMock,
        client: TestClient,
    ) -> None:
        """正常收取建造。"""
        mock_get_context.return_value = MagicMock()
        mock_task_manager.is_running = False
        mock_collect.return_value = 2

        response = client.post('/api/build/collect')
        data: dict[str, Any] = response.json()

        assert response.status_code == 200
        assert data['success'] is True
        assert data['data']['collected'] == 2
        mock_collect.assert_called_once()


class TestBuildStart:
    """POST /api/build/start 测试。"""

    @patch('autowsgr.server.routes.ops.get_context')
    def test_503_no_context(self, mock_get_context: MagicMock, client: TestClient) -> None:
        """无上下文时返回 503。"""
        mock_get_context.side_effect = RuntimeError('context not initialized')

        response = client.post('/api/build/start', json={})

        assert response.status_code == 503

    @patch('autowsgr.server.routes.ops.task_manager')
    @patch('autowsgr.server.routes.ops.get_context')
    def test_409_busy(
        self,
        mock_get_context: MagicMock,
        mock_task_manager: MagicMock,
        client: TestClient,
    ) -> None:
        """任务执行中时返回 409。"""
        mock_get_context.return_value = MagicMock()
        mock_task_manager.is_running = True

        response = client.post('/api/build/start', json={})

        assert response.status_code == 409

    @patch('autowsgr.ops.build_ship')
    @patch('autowsgr.ops.BuildRecipe')
    @patch('autowsgr.server.routes.ops.task_manager')
    @patch('autowsgr.server.routes.ops.get_context')
    def test_success_and_recipe_fields(
        self,
        mock_get_context: MagicMock,
        mock_task_manager: MagicMock,
        mock_recipe_cls: MagicMock,
        mock_build_ship: MagicMock,
        client: TestClient,
    ) -> None:
        """建造成功且 BuildRecipe 使用请求字段构造。"""
        mock_get_context.return_value = MagicMock()
        mock_task_manager.is_running = False
        mock_recipe = MagicMock()
        mock_recipe_cls.return_value = mock_recipe

        response = client.post(
            '/api/build/start',
            json={
                'fuel': 100,
                'ammo': 200,
                'steel': 300,
                'bauxite': 400,
                'build_type': 'equipment',
                'allow_fast_build': True,
            },
        )
        data: dict[str, Any] = response.json()

        assert response.status_code == 200
        assert data['success'] is True
        mock_recipe_cls.assert_called_once_with(
            fuel=100,
            ammo=200,
            steel=300,
            bauxite=400,
        )
        mock_build_ship.assert_called_once()
        call_kwargs = mock_build_ship.call_args.kwargs
        assert call_kwargs['recipe'] is mock_recipe
        assert call_kwargs['build_type'] == 'equipment'
        assert call_kwargs['allow_fast_build'] is True


class TestRewardCollect:
    """POST /api/reward/collect 测试。"""

    @patch('autowsgr.server.routes.ops.get_context')
    def test_503_no_context(self, mock_get_context: MagicMock, client: TestClient) -> None:
        """无上下文时返回 503。"""
        mock_get_context.side_effect = RuntimeError('context not initialized')

        response = client.post('/api/reward/collect')

        assert response.status_code == 503

    @patch('autowsgr.server.routes.ops.task_manager')
    @patch('autowsgr.server.routes.ops.get_context')
    def test_409_busy(
        self,
        mock_get_context: MagicMock,
        mock_task_manager: MagicMock,
        client: TestClient,
    ) -> None:
        """任务执行中时返回 409。"""
        mock_get_context.return_value = MagicMock()
        mock_task_manager.is_running = True

        response = client.post('/api/reward/collect')

        assert response.status_code == 409

    @patch('autowsgr.ops.collect_rewards')
    @patch('autowsgr.server.routes.ops.task_manager')
    @patch('autowsgr.server.routes.ops.get_context')
    def test_success(
        self,
        mock_get_context: MagicMock,
        mock_task_manager: MagicMock,
        mock_collect: MagicMock,
        client: TestClient,
    ) -> None:
        """正常收取奖励。"""
        mock_get_context.return_value = MagicMock()
        mock_task_manager.is_running = False
        mock_collect.return_value = 4

        response = client.post('/api/reward/collect')
        data: dict[str, Any] = response.json()

        assert response.status_code == 200
        assert data['success'] is True
        assert data['data']['collected'] == 4
        mock_collect.assert_called_once()


class TestCook:
    """POST /api/cook 测试。"""

    @patch('autowsgr.server.routes.ops.get_context')
    def test_503_no_context(self, mock_get_context: MagicMock, client: TestClient) -> None:
        """无上下文时返回 503。"""
        mock_get_context.side_effect = RuntimeError('context not initialized')

        response = client.post('/api/cook', json={})

        assert response.status_code == 503

    @patch('autowsgr.server.routes.ops.task_manager')
    @patch('autowsgr.server.routes.ops.get_context')
    def test_409_busy(
        self,
        mock_get_context: MagicMock,
        mock_task_manager: MagicMock,
        client: TestClient,
    ) -> None:
        """任务执行中时返回 409。"""
        mock_get_context.return_value = MagicMock()
        mock_task_manager.is_running = True

        response = client.post('/api/cook', json={})

        assert response.status_code == 409

    @patch('autowsgr.ops.cook')
    @patch('autowsgr.server.routes.ops.task_manager')
    @patch('autowsgr.server.routes.ops.get_context')
    def test_success(
        self,
        mock_get_context: MagicMock,
        mock_task_manager: MagicMock,
        mock_cook: MagicMock,
        client: TestClient,
    ) -> None:
        """正常烹饪。"""
        mock_get_context.return_value = MagicMock()
        mock_task_manager.is_running = False
        mock_cook.return_value = True

        response = client.post('/api/cook', json={'position': 2, 'force_cook': True})
        data: dict[str, Any] = response.json()

        assert response.status_code == 200
        assert data['success'] is True
        assert data['data']['cooked'] is True
        mock_cook.assert_called_once()
        call_kwargs = mock_cook.call_args.kwargs
        assert call_kwargs['position'] == 2
        assert call_kwargs['force_cook'] is True


class TestRepairBath:
    """POST /api/repair/bath 测试。"""

    @patch('autowsgr.server.routes.ops.get_context')
    def test_503_no_context(self, mock_get_context: MagicMock, client: TestClient) -> None:
        """无上下文时返回 503。"""
        mock_get_context.side_effect = RuntimeError('context not initialized')

        response = client.post('/api/repair/bath')

        assert response.status_code == 503

    @patch('autowsgr.server.routes.ops.task_manager')
    @patch('autowsgr.server.routes.ops.get_context')
    def test_409_busy(
        self,
        mock_get_context: MagicMock,
        mock_task_manager: MagicMock,
        client: TestClient,
    ) -> None:
        """任务执行中时返回 409。"""
        mock_get_context.return_value = MagicMock()
        mock_task_manager.is_running = True

        response = client.post('/api/repair/bath')

        assert response.status_code == 409

    @patch('autowsgr.ops.repair_in_bath')
    @patch('autowsgr.server.routes.ops.task_manager')
    @patch('autowsgr.server.routes.ops.get_context')
    def test_success(
        self,
        mock_get_context: MagicMock,
        mock_task_manager: MagicMock,
        mock_repair: MagicMock,
        client: TestClient,
    ) -> None:
        """正常浴室修理。"""
        mock_get_context.return_value = MagicMock()
        mock_task_manager.is_running = False

        response = client.post('/api/repair/bath')
        data: dict[str, Any] = response.json()

        assert response.status_code == 200
        assert data['success'] is True
        mock_repair.assert_called_once()


class TestRepairShip:
    """POST /api/repair/ship 测试。"""

    @patch('autowsgr.server.routes.ops.get_context')
    def test_503_no_context(self, mock_get_context: MagicMock, client: TestClient) -> None:
        """无上下文时返回 503。"""
        mock_get_context.side_effect = RuntimeError('context not initialized')

        response = client.post('/api/repair/ship', json={'ship_name': 'TestShip'})

        assert response.status_code == 503

    @patch('autowsgr.server.routes.ops.task_manager')
    @patch('autowsgr.server.routes.ops.get_context')
    def test_409_busy(
        self,
        mock_get_context: MagicMock,
        mock_task_manager: MagicMock,
        client: TestClient,
    ) -> None:
        """任务执行中时返回 409。"""
        mock_get_context.return_value = MagicMock()
        mock_task_manager.is_running = True

        response = client.post('/api/repair/ship', json={'ship_name': 'TestShip'})

        assert response.status_code == 409

    @patch('autowsgr.ops.repair.repair_ship_by_name')
    @patch('autowsgr.server.routes.ops.task_manager')
    @patch('autowsgr.server.routes.ops.get_context')
    def test_bath_full(
        self,
        mock_get_context: MagicMock,
        mock_task_manager: MagicMock,
        mock_repair_ship: MagicMock,
        client: TestClient,
    ) -> None:
        """repair_secs < 0 时返回浴场已满错误。"""
        mock_get_context.return_value = MagicMock()
        mock_task_manager.is_running = False
        mock_repair_ship.return_value = -1

        response = client.post('/api/repair/ship', json={'ship_name': 'TestShip'})
        data: dict[str, Any] = response.json()

        assert response.status_code == 200
        assert data['success'] is False
        assert '浴场已满' in data['error']
        mock_repair_ship.assert_called_once()

    @patch('autowsgr.ops.repair.repair_ship_by_name')
    @patch('autowsgr.server.routes.ops.task_manager')
    @patch('autowsgr.server.routes.ops.get_context')
    def test_success(
        self,
        mock_get_context: MagicMock,
        mock_task_manager: MagicMock,
        mock_repair_ship: MagicMock,
        client: TestClient,
    ) -> None:
        """repair_secs >= 0 时返回成功。"""
        mock_get_context.return_value = MagicMock()
        mock_task_manager.is_running = False
        mock_repair_ship.return_value = 3600

        response = client.post('/api/repair/ship', json={'ship_name': 'TestShip'})
        data: dict[str, Any] = response.json()

        assert response.status_code == 200
        assert data['success'] is True
        assert data['data']['ship_name'] == 'TestShip'
        assert data['data']['repair_seconds'] == 3600
        mock_repair_ship.assert_called_once()


class TestDestroy:
    """POST /api/destroy 测试。"""

    @patch('autowsgr.server.routes.ops.get_context')
    def test_503_no_context(self, mock_get_context: MagicMock, client: TestClient) -> None:
        """无上下文时返回 503。"""
        mock_get_context.side_effect = RuntimeError('context not initialized')

        response = client.post('/api/destroy', json={})

        assert response.status_code == 503

    @patch('autowsgr.server.routes.ops.task_manager')
    @patch('autowsgr.server.routes.ops.get_context')
    def test_409_busy(
        self,
        mock_get_context: MagicMock,
        mock_task_manager: MagicMock,
        client: TestClient,
    ) -> None:
        """任务执行中时返回 409。"""
        mock_get_context.return_value = MagicMock()
        mock_task_manager.is_running = True

        response = client.post('/api/destroy', json={})

        assert response.status_code == 409

    @patch('autowsgr.types.ShipType')
    @patch('autowsgr.ops.destroy_ships')
    @patch('autowsgr.server.routes.ops.task_manager')
    @patch('autowsgr.server.routes.ops.get_context')
    def test_ship_type_conversion(
        self,
        mock_get_context: MagicMock,
        mock_task_manager: MagicMock,
        mock_destroy: MagicMock,
        mock_ship_type: MagicMock,
        client: TestClient,
    ) -> None:
        """ship_types 被正确转换为 ShipType 枚举。"""
        mock_get_context.return_value = MagicMock()
        mock_task_manager.is_running = False
        mock_dd = MagicMock()
        mock_cl = MagicMock()
        mock_ship_type.side_effect = [mock_dd, mock_cl]

        response = client.post(
            '/api/destroy',
            json={
                'ship_types': ['DD', 'CL'],
                'remove_equipment': False,
            },
        )
        data: dict[str, Any] = response.json()

        assert response.status_code == 200
        assert data['success'] is True
        mock_ship_type.assert_any_call('DD')
        mock_ship_type.assert_any_call('CL')
        mock_destroy.assert_called_once()
        call_kwargs = mock_destroy.call_args.kwargs
        assert call_kwargs['ship_types'] == [mock_dd, mock_cl]
        assert call_kwargs['remove_equipment'] is False

    @patch('autowsgr.ops.destroy_ships')
    @patch('autowsgr.server.routes.ops.task_manager')
    @patch('autowsgr.server.routes.ops.get_context')
    def test_success_no_ship_types(
        self,
        mock_get_context: MagicMock,
        mock_task_manager: MagicMock,
        mock_destroy: MagicMock,
        client: TestClient,
    ) -> None:
        """未传入 ship_types 时正常解装。"""
        mock_get_context.return_value = MagicMock()
        mock_task_manager.is_running = False

        response = client.post('/api/destroy', json={'remove_equipment': True})
        data: dict[str, Any] = response.json()

        assert response.status_code == 200
        assert data['success'] is True
        mock_destroy.assert_called_once()
        call_kwargs = mock_destroy.call_args.kwargs
        assert call_kwargs['ship_types'] is None
        assert call_kwargs['remove_equipment'] is True
