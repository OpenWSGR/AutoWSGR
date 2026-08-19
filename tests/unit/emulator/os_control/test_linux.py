"""测试 autowsgr.emulator.os_control.linux."""

from __future__ import annotations

import subprocess
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from autowsgr.emulator.os_control.linux import LinuxEmulatorManager
from autowsgr.infra import EmulatorConfig, EmulatorError, EmulatorNotFoundError


@pytest.fixture
def _patch_is_wsl() -> Any:
    with patch('autowsgr.emulator.os_control.linux.OSType._is_wsl', return_value=False):
        yield


@pytest.mark.usefixtures('_patch_is_wsl')
class TestIsRunning:
    def test_serial_in_adb_devices(self) -> None:
        config = EmulatorConfig(serial='emulator-5554')
        manager = LinuxEmulatorManager(config)
        with patch.object(manager, '_adb_devices', return_value=['emulator-5554']):
            assert manager.is_running() is True

    def test_wsl_process_found(self) -> None:
        with patch('autowsgr.emulator.os_control.linux.OSType._is_wsl', return_value=True):
            config = EmulatorConfig(process_name='emulator.exe')
            manager = LinuxEmulatorManager(config)
        with patch.object(manager, '_is_windows_process_running', return_value=True):
            assert manager.is_running() is True

    def test_wsl_no_tasks(self) -> None:
        with patch('autowsgr.emulator.os_control.linux.OSType._is_wsl', return_value=True):
            config = EmulatorConfig(process_name='emulator.exe')
            manager = LinuxEmulatorManager(config)
        with patch.object(manager, '_is_windows_process_running', return_value=False):
            assert manager.is_running() is False

    def test_linux_pgrep_success(self) -> None:
        config = EmulatorConfig(process_name='emulator')
        manager = LinuxEmulatorManager(config)
        with patch('autowsgr.emulator.os_control.linux.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert manager.is_running() is True
            mock_run.assert_called_once_with(
                ['pgrep', '-f', 'emulator'],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    def test_linux_pgrep_fails(self) -> None:
        config = EmulatorConfig(process_name='emulator')
        manager = LinuxEmulatorManager(config)
        with patch('autowsgr.emulator.os_control.linux.subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, ['pgrep'])
            assert manager.is_running() is False

    def test_no_serial_no_process_name(self) -> None:
        config = EmulatorConfig()
        manager = LinuxEmulatorManager(config)
        assert manager.is_running() is False


@pytest.mark.usefixtures('_patch_is_wsl')
class TestStart:
    def test_start_no_path_raises(self) -> None:
        config = EmulatorConfig()
        manager = LinuxEmulatorManager(config)
        with pytest.raises(EmulatorNotFoundError, match='未设置模拟器路径'):
            manager.start()

    def test_start_success(self) -> None:
        config = EmulatorConfig(path='/usr/bin/emulator')
        manager = LinuxEmulatorManager(config)
        with (
            patch('autowsgr.emulator.os_control.linux.subprocess.Popen') as mock_popen,
            patch.object(manager, 'wait_until_online') as mock_wait,
        ):
            manager.start()
            mock_popen.assert_called_once_with(['/usr/bin/emulator'])
            mock_wait.assert_called_once()


@pytest.mark.usefixtures('_patch_is_wsl')
class TestStop:
    def test_stop_wsl_taskkill_success(self) -> None:
        with patch('autowsgr.emulator.os_control.linux.OSType._is_wsl', return_value=True):
            config = EmulatorConfig(process_name='emulator.exe')
            manager = LinuxEmulatorManager(config)
        with patch('autowsgr.emulator.os_control.linux.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr='', stdout='')
            manager.stop()
            mock_run.assert_called_once_with(
                ['taskkill.exe', '/f', '/im', 'emulator.exe'],
                capture_output=True,
                text=True,
                check=False,
            )

    def test_stop_linux_pkill_success(self) -> None:
        config = EmulatorConfig(process_name='emulator')
        manager = LinuxEmulatorManager(config)
        with patch('autowsgr.emulator.os_control.linux.subprocess.run') as mock_run:
            manager.stop()
            mock_run.assert_called_once_with(
                ['pkill', '-9', '-f', 'emulator'],
                check=True,
            )

    def test_stop_no_process_name_raises(self) -> None:
        config = EmulatorConfig()
        manager = LinuxEmulatorManager(config)
        with pytest.raises(EmulatorError, match='未设置进程名'):
            manager.stop()


@pytest.mark.usefixtures('_patch_is_wsl')
class TestAdbDevices:
    def test_parses_normal_output(self) -> None:
        with (
            patch('autowsgr.emulator.os_control.linux._find_adb', return_value='/usr/bin/adb'),
            patch('autowsgr.emulator.os_control.linux.subprocess.run') as mock_run,
        ):
            mock_run.return_value = MagicMock(
                stdout='List of devices attached\nemulator-5554\tdevice\n127.0.0.1:16384\tdevice\n',
                returncode=0,
            )
            devices = LinuxEmulatorManager._adb_devices()
            assert devices == ['emulator-5554', '127.0.0.1:16384']

    def test_parses_offline_devices(self) -> None:
        with (
            patch('autowsgr.emulator.os_control.linux._find_adb', return_value='/usr/bin/adb'),
            patch('autowsgr.emulator.os_control.linux.subprocess.run') as mock_run,
        ):
            mock_run.return_value = MagicMock(
                stdout='List of devices attached\nemulator-5554\tdevice\nemulator-5556\toffline\n',
                returncode=0,
            )
            devices = LinuxEmulatorManager._adb_devices()
            assert devices == ['emulator-5554']

    def test_adb_fails_returns_empty(self) -> None:
        with (
            patch('autowsgr.emulator.os_control.linux._find_adb', return_value='/usr/bin/adb'),
            patch('autowsgr.emulator.os_control.linux.subprocess.run') as mock_run,
        ):
            mock_run.side_effect = subprocess.CalledProcessError(1, ['adb'])
            devices = LinuxEmulatorManager._adb_devices()
            assert devices == []


class TestIsWindowsProcessRunning:
    def test_process_found(self) -> None:
        with patch('autowsgr.emulator.os_control.linux.OSType._is_wsl', return_value=True):
            config = EmulatorConfig(process_name='emulator.exe')
            manager = LinuxEmulatorManager(config)
        with patch('autowsgr.emulator.os_control.linux.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                stdout='Image Name                     PID Session Name        Session#    Mem Usage\nemulator.exe                  1234 Console                    1     123456 K\n',
                returncode=0,
            )
            assert manager._is_windows_process_running() is True

    def test_no_tasks(self) -> None:
        with patch('autowsgr.emulator.os_control.linux.OSType._is_wsl', return_value=True):
            config = EmulatorConfig(process_name='emulator.exe')
            manager = LinuxEmulatorManager(config)
        with patch('autowsgr.emulator.os_control.linux.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                stdout='INFO: No tasks are running which match the specified criteria.\n',
                returncode=0,
            )
            assert manager._is_windows_process_running() is False
