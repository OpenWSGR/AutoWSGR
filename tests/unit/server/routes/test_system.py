"""测试 autowsgr.server.routes.system."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from autowsgr.server.main import app


client = TestClient(app)


class TestSystemStart:
    """system_start 测试。"""

    @patch('autowsgr.server.routes.system._main')
    def test_already_running(self, mock_main: MagicMock) -> None:
        """已启动时直接返回 '系统已启动'。"""
        mock_main._ctx = MagicMock()

        response = client.post('/api/system/start', json={})
        data = response.json()

        assert response.status_code == 200
        assert data['success'] is True
        assert data['message'] == '系统已启动'

    @patch('autowsgr.scheduler.launch')
    @patch('autowsgr.server.routes.system._main')
    def test_start_with_default_config(
        self,
        mock_main: MagicMock,
        mock_launch: MagicMock,
    ) -> None:
        """未启动时使用默认配置路径调用 launch。"""
        mock_main._ctx = None
        mock_ctx = MagicMock()
        mock_launch.return_value = mock_ctx

        response = client.post('/api/system/start', json={})
        data = response.json()

        assert response.status_code == 200
        assert data['success'] is True
        assert data['message'] == '系统启动成功'
        mock_launch.assert_called_once_with('usersettings.yaml')
        assert mock_main._ctx is mock_ctx

    @patch('autowsgr.scheduler.launch')
    @patch('autowsgr.server.routes.system._main')
    def test_start_with_custom_config(
        self,
        mock_main: MagicMock,
        mock_launch: MagicMock,
    ) -> None:
        """支持通过请求体传入自定义配置路径。"""
        mock_main._ctx = None
        mock_ctx = MagicMock()
        mock_launch.return_value = mock_ctx

        response = client.post(
            '/api/system/start',
            json={'config_path': '/custom/config.yaml'},
        )
        data = response.json()

        assert response.status_code == 200
        assert data['success'] is True
        mock_launch.assert_called_once_with('/custom/config.yaml')

    @patch('autowsgr.scheduler.launch')
    @patch('autowsgr.server.routes.system._main')
    def test_start_failure(
        self,
        mock_main: MagicMock,
        mock_launch: MagicMock,
    ) -> None:
        """launch 抛出异常时返回 success=False 并携带错误信息。"""
        mock_main._ctx = None
        mock_launch.side_effect = ValueError('config not found')

        response = client.post('/api/system/start', json={})
        data = response.json()

        assert response.status_code == 200
        assert data['success'] is False
        assert data['error'] == 'config not found'


class TestSystemStop:
    """system_stop 测试。"""

    @patch('autowsgr.server.routes.system._main')
    def test_not_running(self, mock_main: MagicMock) -> None:
        """未运行时返回 '系统未运行'。"""
        mock_main._ctx = None

        response = client.post('/api/system/stop')
        data = response.json()

        assert response.status_code == 200
        assert data['success'] is True
        assert data['message'] == '系统未运行'

    @patch('autowsgr.server.routes.system.task_manager')
    @patch('autowsgr.server.routes.system._main')
    def test_stop_running_with_task(
        self,
        mock_main: MagicMock,
        mock_task_manager: MagicMock,
    ) -> None:
        """运行中且有任务时先停止任务，再将上下文置为 None。"""
        mock_main._ctx = MagicMock()
        mock_task_manager.is_running = True

        response = client.post('/api/system/stop')
        data = response.json()

        assert response.status_code == 200
        assert data['success'] is True
        assert data['message'] == '系统已停止'
        mock_task_manager.stop_task.assert_called_once()
        assert mock_main._ctx is None


class TestSystemStatus:
    """system_status 测试。"""

    @patch('autowsgr.server.routes.system.task_manager')
    @patch('autowsgr.server.routes.system._main')
    def test_idle(self, mock_main: MagicMock, mock_task_manager: MagicMock) -> None:
        """空闲状态返回正确字段值。"""
        mock_main._ctx = None
        mock_task_manager.current_task = None

        response = client.get('/api/system/status')
        data = response.json()

        assert response.status_code == 200
        assert data['success'] is True
        assert data['data']['status'] == 'idle'
        assert data['data']['emulator_connected'] is False
        assert data['data']['game_running'] is False
        assert data['data']['current_task'] is None

    @patch('autowsgr.server.routes.system.task_manager')
    @patch('autowsgr.server.routes.system._main')
    def test_running_with_task(
        self,
        mock_main: MagicMock,
        mock_task_manager: MagicMock,
    ) -> None:
        """有任务运行时返回对应状态与任务 ID。"""
        mock_main._ctx = MagicMock()
        mock_task = MagicMock()
        mock_task.status.value = 'running'
        mock_task.task_id = 'task_123'
        mock_task_manager.current_task = mock_task

        response = client.get('/api/system/status')
        data = response.json()

        assert response.status_code == 200
        assert data['success'] is True
        assert data['data']['status'] == 'running'
        assert data['data']['emulator_connected'] is True
        assert data['data']['game_running'] is True
        assert data['data']['current_task'] == 'task_123'


class TestEmulatorDevices:
    """emulator_devices 测试。"""

    @patch('autowsgr.emulator.detector.connect_and_list_devices')
    def test_success(self, mock_connect: MagicMock) -> None:
        """成功查询设备列表并返回规范结构。"""
        mock_connect.return_value = [
            ('emulator-5554', 'device'),
            ('emulator-5556', 'offline'),
        ]

        response = client.get('/api/system/emulator/devices')
        data = response.json()

        assert response.status_code == 200
        assert data['success'] is True
        assert data['data'] == [
            {'serial': 'emulator-5554', 'status': 'device'},
            {'serial': 'emulator-5556', 'status': 'offline'},
        ]

    @patch('autowsgr.emulator.detector.connect_and_list_devices')
    def test_failure(self, mock_connect: MagicMock) -> None:
        """查询异常时返回 success=False 与错误信息。"""
        mock_connect.side_effect = RuntimeError('adb error')

        response = client.get('/api/system/emulator/devices')
        data = response.json()

        assert response.status_code == 200
        assert data['success'] is False
        assert data['error'] == 'adb error'
