"""Tests for autowsgr.emulator.os_control.macos."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from autowsgr.emulator.os_control.macos import MacEmulatorManager
from autowsgr.infra import EmulatorConfig, EmulatorError, EmulatorNotFoundError
from autowsgr.types import EmulatorType


# ── is_running ──


def test_is_running_no_process_name() -> None:
    """is_running returns False when process_name is not set."""
    config = EmulatorConfig(type=EmulatorType.leidian, process_name=None)
    manager = MacEmulatorManager(config)
    assert manager.is_running() is False


def test_is_running_pgrep_fails() -> None:
    """is_running returns False when pgrep finds no process."""
    config = EmulatorConfig(type=EmulatorType.leidian, process_name='test')
    manager = MacEmulatorManager(config)
    with patch(
        'autowsgr.emulator.os_control.macos.subprocess.check_output',
        side_effect=subprocess.CalledProcessError(1, 'pgrep'),
    ):
        assert manager.is_running() is False


def test_is_running_non_mumu_pgrep_succeeds() -> None:
    """is_running returns True for non-mumu when pgrep succeeds."""
    config = EmulatorConfig(type=EmulatorType.leidian, process_name='test')
    manager = MacEmulatorManager(config)
    with patch(
        'autowsgr.emulator.os_control.macos.subprocess.check_output',
        return_value=b'1234',
    ):
        assert manager.is_running() is True


def test_is_running_mumu_matching_port() -> None:
    """is_running returns True for mumu when adb_port matches."""
    config = EmulatorConfig(
        type=EmulatorType.mumu,
        process_name='test',
        serial='127.0.0.1:5555',
    )
    manager = MacEmulatorManager(config)
    with (
        patch(
            'autowsgr.emulator.os_control.macos.subprocess.check_output',
            return_value=b'1234',
        ),
        patch.object(
            manager,
            '_get_mumu_info',
            return_value={'return': {'results': [{'adb_port': '5555'}]}},
        ),
    ):
        assert manager.is_running() is True


def test_is_running_mumu_no_matching_port() -> None:
    """is_running returns False for mumu when adb_port does not match."""
    config = EmulatorConfig(
        type=EmulatorType.mumu,
        process_name='test',
        serial='127.0.0.1:5555',
    )
    manager = MacEmulatorManager(config)
    with (
        patch(
            'autowsgr.emulator.os_control.macos.subprocess.check_output',
            return_value=b'1234',
        ),
        patch.object(
            manager,
            '_get_mumu_info',
            return_value={'return': {'results': [{'adb_port': '5556'}]}},
        ),
    ):
        assert manager.is_running() is False


# ── start ──


def test_start_no_path_raises() -> None:
    """start raises EmulatorNotFoundError when path is not set."""
    config = EmulatorConfig(type=EmulatorType.leidian, path=None)
    manager = MacEmulatorManager(config)
    with pytest.raises(EmulatorNotFoundError, match='未设置模拟器路径'):
        manager.start()


def test_start_non_mumu_success() -> None:
    """start opens non-mumu emulator with 'open -a' and waits until online."""
    config = EmulatorConfig(type=EmulatorType.leidian, path='/App')
    manager = MacEmulatorManager(config)
    with (
        patch(
            'autowsgr.emulator.os_control.macos.subprocess.Popen',
        ) as mock_popen,
        patch.object(manager, 'wait_until_online'),
    ):
        manager.start()
        mock_popen.assert_called_once_with(['open', '-a', '/App'])


def test_start_mumu_success() -> None:
    """start opens mumu emulator and calls _mumu_restart_instance."""
    config = EmulatorConfig(type=EmulatorType.mumu, path='/App')
    manager = MacEmulatorManager(config)
    with (
        patch(
            'autowsgr.emulator.os_control.macos.subprocess.Popen',
        ) as mock_popen,
        patch.object(manager, 'wait_until_online'),
        patch.object(manager, '_mumu_restart_instance') as mock_restart,
    ):
        manager.start()
        mock_popen.assert_called_once_with(['open', '-a', '/App'])
        mock_restart.assert_called_once()


# ── stop ──


def test_stop_mumu_logs_and_returns() -> None:
    """stop logs a warning for mumu and does not kill the process."""
    config = EmulatorConfig(type=EmulatorType.mumu)
    manager = MacEmulatorManager(config)
    with (
        patch('autowsgr.emulator.os_control.macos._log.info') as mock_log,
        patch(
            'autowsgr.emulator.os_control.macos.subprocess.Popen',
        ) as mock_popen,
    ):
        manager.stop()
        mock_popen.assert_not_called()
        mock_log.assert_called_once_with(
            'MuMu macOS 版暂不支持 CLI 关闭',
        )


def test_stop_non_mumu_no_process_name_raises() -> None:
    """stop raises EmulatorError for non-mumu when process_name is not set."""
    config = EmulatorConfig(type=EmulatorType.leidian, process_name=None)
    manager = MacEmulatorManager(config)
    with pytest.raises(EmulatorError, match='未设置进程名'):
        manager.stop()


def test_stop_non_mumu_success() -> None:
    """stop kills non-mumu process with pkill."""
    config = EmulatorConfig(type=EmulatorType.leidian, process_name='test')
    manager = MacEmulatorManager(config)
    with patch(
        'autowsgr.emulator.os_control.macos.subprocess.Popen',
    ) as mock_popen:
        manager.stop()
        mock_popen.assert_called_once_with(
            ['pkill', '-9', '-f', 'test'],
        )


# ── _get_mumu_info ──


def test_get_mumu_info_valid_json() -> None:
    """_get_mumu_info returns parsed dict for valid JSON output."""
    config = EmulatorConfig(type=EmulatorType.mumu, path='/App')
    manager = MacEmulatorManager(config)
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = (b'{"return":{"results":[]}}', b'')
    with (
        patch(
            'autowsgr.emulator.os_control.macos.os.path.join',
            return_value='/App/Contents/MacOS/mumutool',
        ),
        patch(
            'autowsgr.emulator.os_control.macos.os.path.isfile',
            return_value=True,
        ),
        patch(
            'autowsgr.emulator.os_control.macos.subprocess.Popen',
            return_value=mock_proc,
        ) as mock_popen,
    ):
        result = manager._get_mumu_info()
        assert result == {'return': {'results': []}}
        mock_popen.assert_called_once_with(
            ['/App/Contents/MacOS/mumutool', 'info', 'all'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )


def test_get_mumu_info_invalid_json() -> None:
    """_get_mumu_info returns {} when mumutool output is not valid JSON."""
    config = EmulatorConfig(type=EmulatorType.mumu, path='/App')
    manager = MacEmulatorManager(config)
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = (b'not json', b'')
    with (
        patch(
            'autowsgr.emulator.os_control.macos.os.path.join',
            return_value='/App/Contents/MacOS/mumutool',
        ),
        patch(
            'autowsgr.emulator.os_control.macos.os.path.isfile',
            return_value=True,
        ),
        patch(
            'autowsgr.emulator.os_control.macos.subprocess.Popen',
            return_value=mock_proc,
        ) as mock_popen,
    ):
        result = manager._get_mumu_info()
        assert result == {}
        mock_popen.assert_called_once_with(
            ['/App/Contents/MacOS/mumutool', 'info', 'all'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )


def test_get_mumu_info_missing_tool() -> None:
    """_get_mumu_info returns {} when mumutool executable does not exist."""
    config = EmulatorConfig(type=EmulatorType.mumu, path='/App')
    manager = MacEmulatorManager(config)
    with (
        patch(
            'autowsgr.emulator.os_control.macos.os.path.join',
            return_value='/App/Contents/MacOS/mumutool',
        ),
        patch(
            'autowsgr.emulator.os_control.macos.os.path.isfile',
            return_value=False,
        ),
        patch(
            'autowsgr.emulator.os_control.macos.subprocess.Popen',
        ) as mock_popen,
    ):
        result = manager._get_mumu_info()
        assert result == {}
        mock_popen.assert_not_called()


# ── _mumu_restart_instance ──


def test_mumu_restart_instance_matching_port() -> None:
    """_mumu_restart_instance calls mumutool restart with correct idx."""
    config = EmulatorConfig(
        type=EmulatorType.mumu,
        path='/App',
        serial='127.0.0.1:5555',
    )
    manager = MacEmulatorManager(config)
    with (
        patch(
            'autowsgr.emulator.os_control.macos.os.path.join',
            return_value='/App/Contents/MacOS/mumutool',
        ),
        patch(
            'autowsgr.emulator.os_control.macos.os.path.isfile',
            return_value=True,
        ),
        patch.object(
            manager,
            '_get_mumu_info',
            return_value={
                'return': {
                    'results': [
                        {'adb_port': '5555'},
                        {'adb_port': '5556'},
                    ],
                },
            },
        ),
        patch(
            'autowsgr.emulator.os_control.macos.subprocess.Popen',
        ) as mock_popen,
    ):
        manager._mumu_restart_instance()
        mock_popen.assert_called_once_with(
            ['/App/Contents/MacOS/mumutool', 'restart', '0'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )


def test_mumu_restart_instance_no_match() -> None:
    """_mumu_restart_instance does nothing when no adb_port matches."""
    config = EmulatorConfig(
        type=EmulatorType.mumu,
        path='/App',
        serial='127.0.0.1:5555',
    )
    manager = MacEmulatorManager(config)
    with (
        patch(
            'autowsgr.emulator.os_control.macos.os.path.join',
            return_value='/App/Contents/MacOS/mumutool',
        ),
        patch(
            'autowsgr.emulator.os_control.macos.os.path.isfile',
            return_value=True,
        ),
        patch.object(
            manager,
            '_get_mumu_info',
            return_value={'return': {'results': [{'adb_port': '5556'}]}},
        ),
        patch(
            'autowsgr.emulator.os_control.macos.subprocess.Popen',
        ) as mock_popen,
    ):
        manager._mumu_restart_instance()
        mock_popen.assert_not_called()
