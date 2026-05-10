"""测试 autowsgr.server.routes.game."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from autowsgr.server.main import app


client = TestClient(app)


class TestGameAcquisition:
    """game_acquisition 测试。"""

    @patch('autowsgr.server.routes.game.get_context')
    def test_no_context(self, mock_get_context: MagicMock) -> None:
        """无上下文时应返回 503。"""
        mock_get_context.side_effect = RuntimeError('系统未启动')

        response = client.get('/api/game/acquisition')
        assert response.status_code == 503
        assert response.json()['detail'] == '系统未启动'

    @patch('autowsgr.server.routes.game.task_manager')
    @patch('autowsgr.server.routes.game.get_context')
    def test_task_running(
        self,
        mock_get_context: MagicMock,
        mock_task_manager: MagicMock,
    ) -> None:
        """任务执行中时应返回 409。"""
        mock_get_context.return_value = MagicMock()
        mock_task_manager.is_running = True

        response = client.get('/api/game/acquisition')
        assert response.status_code == 409
        assert response.json()['detail'] == '任务执行中，无法查询获取数量'

    @patch('autowsgr.ui.map.page.MapPage')
    @patch('autowsgr.ops.navigate.goto_page')
    @patch('autowsgr.server.routes.game.task_manager')
    @patch('autowsgr.server.routes.game.get_context')
    def test_success(
        self,
        mock_get_context: MagicMock,
        mock_task_manager: MagicMock,
        mock_goto_page: MagicMock,
        mock_map_page_cls: MagicMock,
    ) -> None:
        """空闲时应成功识别并返回获取数量。"""
        mock_get_context.return_value = MagicMock()
        mock_task_manager.is_running = False

        mock_counts = MagicMock()
        mock_counts.ship_count = 100
        mock_counts.ship_max = 500
        mock_counts.loot_count = 10
        mock_counts.loot_max = 50

        mock_map_page = MagicMock()
        mock_map_page.get_acquisition_counts.return_value = mock_counts
        mock_map_page_cls.return_value = mock_map_page

        response = client.get('/api/game/acquisition')
        assert response.status_code == 200

        data: dict[str, Any] = response.json()
        assert data['success'] is True
        assert data['data'] == {
            'ship_count': 100,
            'ship_max': 500,
            'loot_count': 10,
            'loot_max': 50,
        }
        assert data['message'] == '获取数量识别完成'
        mock_goto_page.assert_called_once()
        mock_map_page_cls.assert_called_once()
        mock_map_page.get_acquisition_counts.assert_called_once()


class TestGameContextInfo:
    """game_context_info 测试。"""

    @patch('autowsgr.server.routes.game.get_context')
    def test_no_context(self, mock_get_context: MagicMock) -> None:
        """无上下文时应返回 503。"""
        mock_get_context.side_effect = RuntimeError('系统未启动')

        response = client.get('/api/game/context')
        assert response.status_code == 503
        assert response.json()['detail'] == '系统未启动'

    @patch('autowsgr.server.routes.game.get_context')
    def test_success(self, mock_get_context: MagicMock) -> None:  # noqa: PLR0915
        """有上下文时应返回完整游戏状态。"""
        mock_resources = MagicMock()
        mock_resources.fuel = 1000
        mock_resources.ammo = 2000
        mock_resources.steel = 3000
        mock_resources.aluminum = 4000
        mock_resources.diamond = 500
        mock_resources.fast_repair = 10
        mock_resources.fast_build = 5
        mock_resources.ship_blueprint = 3
        mock_resources.equipment_blueprint = 2

        mock_ship = MagicMock()
        mock_ship.name = '驱逐'
        mock_ship.ship_type = None
        mock_ship.level = 100
        mock_ship.health = 30
        mock_ship.max_health = 30
        mock_ship.damage_state = MagicMock()
        mock_ship.damage_state.value = 0
        mock_ship.locked = True

        mock_fleet = MagicMock()
        mock_fleet.fleet_id = 1
        mock_fleet.ships = [mock_ship]
        mock_fleet.size = 1
        mock_fleet.has_severely_damaged = False

        mock_expedition = MagicMock()
        mock_expedition.chapter = 2
        mock_expedition.node = 'A'
        mock_expedition.fleet = mock_fleet
        mock_expedition.is_active = True
        mock_expedition.remaining_seconds = 3600

        mock_expeditions = MagicMock()
        mock_expeditions.expeditions = [mock_expedition]
        mock_expeditions.active_count = 1
        mock_expeditions.idle_count = 3

        mock_build_slot = MagicMock()
        mock_build_slot.occupied = True
        mock_build_slot.remaining_seconds = 1800
        mock_build_slot.is_complete = False
        mock_build_slot.is_idle = False

        mock_build_queue = MagicMock()
        mock_build_queue.slots = [mock_build_slot]
        mock_build_queue.idle_count = 3
        mock_build_queue.complete_count = 0

        mock_ctx = MagicMock()
        mock_ctx.resources = mock_resources
        mock_ctx.fleets = [mock_fleet]
        mock_ctx.expeditions = mock_expeditions
        mock_ctx.build_queue = mock_build_queue
        mock_ctx.dropped_ship_count = 5
        mock_ctx.dropped_loot_count = 2
        mock_ctx.quick_repair_used = 1
        mock_ctx.current_page = '主页面'
        mock_get_context.return_value = mock_ctx

        response = client.get('/api/game/context')
        assert response.status_code == 200

        data: dict[str, Any] = response.json()
        assert data['success'] is True
        assert data['data']['dropped_ship_count'] == 5
        assert data['data']['dropped_loot_count'] == 2
        assert data['data']['quick_repair_used'] == 1
        assert data['data']['current_page'] == '主页面'
        assert data['data']['resources']['fuel'] == 1000
        assert len(data['data']['fleets']) == 1
        assert data['data']['fleets'][0]['fleet_id'] == 1
        assert data['data']['expeditions']['active_count'] == 1
        assert data['data']['build_queue']['idle_count'] == 3


class TestExpeditionStatus:
    """expedition_status 测试。"""

    @patch('autowsgr.server.routes.game.get_context')
    def test_no_context(self, mock_get_context: MagicMock) -> None:
        """无上下文时应返回 503。"""
        mock_get_context.side_effect = RuntimeError('系统未启动')

        response = client.get('/api/expedition/status')
        assert response.status_code == 503
        assert response.json()['detail'] == '系统未启动'

    @patch('autowsgr.server.routes.game.get_context')
    def test_success(self, mock_get_context: MagicMock) -> None:
        """有上下文时应返回远征队列。"""
        mock_expedition = MagicMock()
        mock_expedition.chapter = 1
        mock_expedition.node = 'B'
        mock_expedition.fleet = None
        mock_expedition.is_active = False
        mock_expedition.remaining_seconds = 0

        mock_expeditions = MagicMock()
        mock_expeditions.expeditions = [mock_expedition]
        mock_expeditions.active_count = 0
        mock_expeditions.idle_count = 4

        mock_ctx = MagicMock()
        mock_ctx.expeditions = mock_expeditions
        mock_get_context.return_value = mock_ctx

        response = client.get('/api/expedition/status')
        assert response.status_code == 200

        data: dict[str, Any] = response.json()
        assert data['success'] is True
        assert data['data']['active_count'] == 0
        assert data['data']['idle_count'] == 4
        assert len(data['data']['slots']) == 1
        assert data['data']['slots'][0]['chapter'] == 1


class TestBuildStatus:
    """build_status 测试。"""

    @patch('autowsgr.server.routes.game.get_context')
    def test_no_context(self, mock_get_context: MagicMock) -> None:
        """无上下文时应返回 503。"""
        mock_get_context.side_effect = RuntimeError('系统未启动')

        response = client.get('/api/build/status')
        assert response.status_code == 503
        assert response.json()['detail'] == '系统未启动'

    @patch('autowsgr.server.routes.game.get_context')
    def test_success(self, mock_get_context: MagicMock) -> None:
        """有上下文时应返回建造队列。"""
        mock_build_slot = MagicMock()
        mock_build_slot.occupied = False
        mock_build_slot.remaining_seconds = 0
        mock_build_slot.is_complete = False
        mock_build_slot.is_idle = True

        mock_build_queue = MagicMock()
        mock_build_queue.slots = [mock_build_slot]
        mock_build_queue.idle_count = 4
        mock_build_queue.complete_count = 0

        mock_ctx = MagicMock()
        mock_ctx.build_queue = mock_build_queue
        mock_get_context.return_value = mock_ctx

        response = client.get('/api/build/status')
        assert response.status_code == 200

        data: dict[str, Any] = response.json()
        assert data['success'] is True
        assert data['data']['idle_count'] == 4
        assert data['data']['complete_count'] == 0
        assert len(data['data']['slots']) == 1
        assert data['data']['slots'][0]['is_idle'] is True
