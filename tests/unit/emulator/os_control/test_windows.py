"""Tests for autowsgr.emulator.os_control.windows."""

from __future__ import annotations

import re
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from autowsgr.emulator.os_control.windows import WindowsEmulatorManager
from autowsgr.infra import EmulatorConfig, EmulatorError, EmulatorNotFoundError
from autowsgr.types import EmulatorType


class TestIsRunning:
    """is_running tests."""

    def test_leidian_running_and_not_running(self) -> None:
        """Leidian is_running returns True when ldconsole says running, else False."""
        config = EmulatorConfig(
            type=EmulatorType.leidian,
            path='/emu/leidian.exe',
            serial='emulator-5554',
        )
        manager = WindowsEmulatorManager(config)
        with (
            patch(
                'autowsgr.emulator.os_control.windows.os.path.join',
                return_value='/emu/ldconsole.exe',
            ),
            patch(
                'autowsgr.emulator.os_control.windows.os.path.isfile',
                return_value=True,
            ),
            patch(
                'autowsgr.emulator.os_control.windows.os.path.dirname',
                return_value='/emu',
            ),
            patch(
                'autowsgr.emulator.os_control.windows.subprocess.Popen',
            ) as mock_popen,
        ):
            mock_popen.return_value.communicate.return_value = (b'running\n', b'')
            assert manager.is_running() is True

            mock_popen.return_value.communicate.return_value = (b'stopped\n', b'')
            assert manager.is_running() is False

    def test_mumu_started_and_parse_fail(self) -> None:
        """MuMu is_running returns True when JSON says started; False on parse failure."""
        config = EmulatorConfig(
            type=EmulatorType.mumu,
            path='/emu/mumu.exe',
            serial='127.0.0.1:16384',
        )
        manager = WindowsEmulatorManager(config)
        with (
            patch(
                'autowsgr.emulator.os_control.windows.os.path.join',
                return_value='/emu/MuMuManager.exe',
            ),
            patch(
                'autowsgr.emulator.os_control.windows.os.path.isfile',
                return_value=True,
            ),
            patch(
                'autowsgr.emulator.os_control.windows.os.path.dirname',
                return_value='/emu',
            ),
            patch(
                'autowsgr.emulator.os_control.windows.subprocess.Popen',
            ) as mock_popen,
        ):
            mock_popen.return_value.communicate.return_value = (
                b'{"is_android_started": true}',
                b'',
            )
            assert manager.is_running() is True

            mock_popen.return_value.communicate.return_value = (b'bad json', b'')
            assert manager.is_running() is False

    def test_yunshouji(self) -> None:
        """Yunshouji is_running always returns True."""
        config = EmulatorConfig(type=EmulatorType.yunshouji)
        manager = WindowsEmulatorManager(config)
        assert manager.is_running() is True

    def test_default_tasklist_finds_process(self) -> None:
        """Default is_running returns True when tasklist finds the process."""
        config = EmulatorConfig(
            type=EmulatorType.bluestacks,
            process_name='bs.exe',
        )
        manager = WindowsEmulatorManager(config)
        with patch(
            'autowsgr.emulator.os_control.windows.subprocess.check_output',
            return_value=b'ImageName  PID  SessionName\nbs.exe  1234  Console',
        ) as mock_co:
            assert manager.is_running() is True
            mock_co.assert_called_once_with(
                ['tasklist', '/fi', 'ImageName eq bs.exe'],
            )

    def test_default_tasklist_no_process(self) -> None:
        """Default is_running returns False when tasklist reports no process."""
        config = EmulatorConfig(
            type=EmulatorType.bluestacks,
            process_name='bs.exe',
        )
        manager = WindowsEmulatorManager(config)
        with patch(
            'autowsgr.emulator.os_control.windows.subprocess.check_output',
            return_value=b'INFO: No tasks are running',
        ) as mock_co:
            assert manager.is_running() is False
            mock_co.assert_called_once_with(
                ['tasklist', '/fi', 'ImageName eq bs.exe'],
            )


class TestStart:
    """start tests."""

    def test_yunshouji_no_op(self) -> None:
        """Yunshouji start is a no-op."""
        config = EmulatorConfig(type=EmulatorType.yunshouji)
        manager = WindowsEmulatorManager(config)
        manager.start()

    def test_leidian_calls_ldconsole_launch(self) -> None:
        """Leidian start calls _ldconsole('launch')."""
        config = EmulatorConfig(
            type=EmulatorType.leidian,
            path='/emu/leidian.exe',
        )
        manager = WindowsEmulatorManager(config)
        object.__setattr__(manager, 'wait_until_online', MagicMock())
        object.__setattr__(manager, '_ldconsole', MagicMock())
        manager.start()
        manager._ldconsole.assert_called_once_with('launch')

    def test_mumu_calls_mumuconsole_launch(self) -> None:
        """MuMu start calls _mumuconsole('launch')."""
        config = EmulatorConfig(
            type=EmulatorType.mumu,
            path='/emu/mumu.exe',
        )
        manager = WindowsEmulatorManager(config)
        object.__setattr__(manager, 'wait_until_online', MagicMock())
        object.__setattr__(manager, '_mumuconsole', MagicMock())
        manager.start()
        manager._mumuconsole.assert_called_once_with('launch')

    def test_default_calls_popen_with_path(self) -> None:
        """Default start calls subprocess.Popen with the executable path."""
        config = EmulatorConfig(
            type=EmulatorType.bluestacks,
            path='/emu/bs.exe',
        )
        manager = WindowsEmulatorManager(config)
        object.__setattr__(manager, 'wait_until_online', MagicMock())
        with patch(
            'autowsgr.emulator.os_control.windows.subprocess.Popen',
        ) as mock_popen:
            manager.start()
            mock_popen.assert_called_once_with(['/emu/bs.exe'])

    def test_no_path_raises(self) -> None:
        """start raises EmulatorNotFoundError when path is not set."""
        config = EmulatorConfig(type=EmulatorType.leidian, path=None)
        manager = WindowsEmulatorManager(config)
        with pytest.raises(EmulatorNotFoundError, match='未设置模拟器路径'):
            manager.start()


class TestStop:
    """stop tests."""

    def test_leidian_calls_ldconsole_quit(self) -> None:
        """Leidian stop calls _ldconsole('quit')."""
        config = EmulatorConfig(
            type=EmulatorType.leidian,
            path='/emu/leidian.exe',
        )
        manager = WindowsEmulatorManager(config)
        object.__setattr__(manager, '_ldconsole', MagicMock())
        manager.stop()
        manager._ldconsole.assert_called_once_with('quit')

    def test_mumu_calls_mumuconsole_shutdown(self) -> None:
        """MuMu stop calls _mumuconsole('shutdown')."""
        config = EmulatorConfig(
            type=EmulatorType.mumu,
            path='/emu/mumu.exe',
        )
        manager = WindowsEmulatorManager(config)
        object.__setattr__(manager, '_mumuconsole', MagicMock())
        manager.stop()
        manager._mumuconsole.assert_called_once_with('shutdown')

    def test_yunshouji_no_op(self) -> None:
        """Yunshouji stop is a no-op."""
        config = EmulatorConfig(type=EmulatorType.yunshouji)
        manager = WindowsEmulatorManager(config)
        manager.stop()

    def test_default_calls_taskkill(self) -> None:
        """Default stop calls taskkill with the process name."""
        config = EmulatorConfig(
            type=EmulatorType.bluestacks,
            process_name='bs.exe',
        )
        manager = WindowsEmulatorManager(config)
        with patch(
            'autowsgr.emulator.os_control.windows.subprocess.run',
        ) as mock_run:
            manager.stop()
            mock_run.assert_called_once_with(
                ['taskkill', '-f', '-im', 'bs.exe'],
                check=True,
                capture_output=True,
            )

    def test_no_process_name_raises(self) -> None:
        """stop raises EmulatorError for unsupported types without a process name."""
        config = EmulatorConfig(
            type=EmulatorType.others,
            process_name=None,
        )
        manager = WindowsEmulatorManager(config)
        with pytest.raises(EmulatorError, match='未设置进程名'):
            manager.stop()


class TestLdConsole:
    """_ldconsole tests."""

    def test_command_built_with_index_from_serial(self) -> None:
        """_ldconsole builds the correct command including index from serial."""
        config = EmulatorConfig(
            type=EmulatorType.leidian,
            path='/emu/leidian.exe',
            serial='emulator-5556',
        )
        manager = WindowsEmulatorManager(config)
        with (
            patch(
                'autowsgr.emulator.os_control.windows.os.path.join',
                return_value='/emu/ldconsole.exe',
            ),
            patch(
                'autowsgr.emulator.os_control.windows.os.path.isfile',
                return_value=True,
            ),
            patch(
                'autowsgr.emulator.os_control.windows.os.path.dirname',
                return_value='/emu',
            ),
            patch(
                'autowsgr.emulator.os_control.windows.subprocess.Popen',
            ) as mock_popen,
        ):
            mock_popen.return_value.communicate.return_value = (b'ok', b'')
            manager._ldconsole('launch')
            mock_popen.assert_called_once()
            cmd = mock_popen.call_args[0][0]
            assert cmd == [
                '/emu/ldconsole.exe',
                'launch',
                '--index',
                '1',
            ]

    def test_missing_console_raises(self) -> None:
        """_ldconsole raises EmulatorNotFoundError when ldconsole.exe is missing."""
        config = EmulatorConfig(
            type=EmulatorType.leidian,
            path='/emu/leidian.exe',
        )
        manager = WindowsEmulatorManager(config)
        with (
            patch(
                'autowsgr.emulator.os_control.windows.os.path.join',
                return_value='/emu/ldconsole.exe',
            ),
            patch(
                'autowsgr.emulator.os_control.windows.os.path.isfile',
                return_value=False,
            ),
            patch(
                'autowsgr.emulator.os_control.windows.os.path.dirname',
                return_value='/emu',
            ),
            pytest.raises(EmulatorNotFoundError, match=re.escape('找不到 ldconsole.exe')),
        ):
            manager._ldconsole('launch')


class TestMumuConsole:
    """_mumuconsole tests."""

    def test_command_built_with_index_from_serial(self) -> None:
        """_mumuconsole builds the correct command including index from serial."""
        config = EmulatorConfig(
            type=EmulatorType.mumu,
            path='/emu/mumu.exe',
            serial='127.0.0.1:16416',
        )
        manager = WindowsEmulatorManager(config)
        with (
            patch(
                'autowsgr.emulator.os_control.windows.os.path.join',
                return_value='/emu/MuMuManager.exe',
            ),
            patch(
                'autowsgr.emulator.os_control.windows.os.path.isfile',
                return_value=True,
            ),
            patch(
                'autowsgr.emulator.os_control.windows.os.path.dirname',
                return_value='/emu',
            ),
            patch(
                'autowsgr.emulator.os_control.windows.subprocess.Popen',
            ) as mock_popen,
        ):
            mock_popen.return_value.communicate.return_value = (b'ok', b'')
            manager._mumuconsole('launch')
            mock_popen.assert_called_once()
            cmd = mock_popen.call_args[0][0]
            assert cmd == [
                '/emu/MuMuManager.exe',
                'control',
                '-v',
                '1',
                'launch',
            ]

    def test_missing_console_raises(self) -> None:
        """_mumuconsole raises EmulatorNotFoundError when MuMuManager.exe is missing."""
        config = EmulatorConfig(
            type=EmulatorType.mumu,
            path='/emu/mumu.exe',
        )
        manager = WindowsEmulatorManager(config)
        with (
            patch(
                'autowsgr.emulator.os_control.windows.os.path.join',
                return_value='/emu/MuMuManager.exe',
            ),
            patch(
                'autowsgr.emulator.os_control.windows.os.path.isfile',
                return_value=False,
            ),
            patch(
                'autowsgr.emulator.os_control.windows.os.path.dirname',
                return_value='/emu',
            ),
            pytest.raises(EmulatorNotFoundError, match=re.escape('找不到 MuMuManager.exe')),
        ):
            manager._mumuconsole('launch')


class TestTasklistCheck:
    """_tasklist_check tests."""

    def test_process_found(self) -> None:
        """_tasklist_check returns True when tasklist output contains PID."""
        config = EmulatorConfig(process_name='emu.exe')
        manager = WindowsEmulatorManager(config)
        with patch(
            'autowsgr.emulator.os_control.windows.subprocess.check_output',
            return_value=b'ImageName  PID  SessionName\nemu.exe  1234  Console',
        ) as mock_co:
            assert manager._tasklist_check() is True
            mock_co.assert_called_once_with(
                ['tasklist', '/fi', 'ImageName eq emu.exe'],
            )

    def test_no_process(self) -> None:
        """_tasklist_check returns False when tasklist output has no PID."""
        config = EmulatorConfig(process_name='emu.exe')
        manager = WindowsEmulatorManager(config)
        with patch(
            'autowsgr.emulator.os_control.windows.subprocess.check_output',
            return_value=b'INFO: No tasks are running',
        ) as mock_co:
            assert manager._tasklist_check() is False
            mock_co.assert_called_once_with(
                ['tasklist', '/fi', 'ImageName eq emu.exe'],
            )


class TestRunCmd:
    """_run_cmd tests."""

    def test_returns_stdout_else_stderr(self) -> None:
        """_run_cmd returns stdout; falls back to stderr when stdout is empty."""
        with patch(
            'autowsgr.emulator.os_control.windows.subprocess.Popen',
        ) as mock_popen:
            mock_proc = MagicMock()
            mock_proc.communicate.return_value = (b'stdout content', b'stderr content')
            mock_popen.return_value = mock_proc

            result = WindowsEmulatorManager._run_cmd(['echo', 'hello'])
            assert result == 'stdout content'
            mock_popen.assert_called_once_with(
                ['echo', 'hello'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            mock_popen.reset_mock()
            mock_proc.communicate.return_value = (b'', b'stderr only')
            result = WindowsEmulatorManager._run_cmd(['echo', 'hello'])
            assert result == 'stderr only'
