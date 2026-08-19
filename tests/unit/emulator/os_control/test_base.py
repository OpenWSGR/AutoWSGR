"""Tests for autowsgr.emulator.os_control.base."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from autowsgr.emulator.os_control import create_emulator_manager
from autowsgr.emulator.os_control.base import EmulatorProcessManager
from autowsgr.emulator.os_control.linux import LinuxEmulatorManager
from autowsgr.emulator.os_control.macos import MacEmulatorManager
from autowsgr.emulator.os_control.windows import WindowsEmulatorManager
from autowsgr.infra import EmulatorConfig, EmulatorError
from autowsgr.types import EmulatorType, OSType


class _ConcreteManager(EmulatorProcessManager):
    """Concrete subclass for testing."""

    def is_running(self) -> bool:
        return True

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


def test_cannot_instantiate_abc_directly() -> None:
    """Instantiating the ABC directly must raise TypeError."""
    config = EmulatorConfig()
    with pytest.raises(TypeError):
        EmulatorProcessManager(config)


def test_subclass_instantiation_sets_attributes() -> None:
    """A concrete subclass can be instantiated and attributes are set from config."""
    config = EmulatorConfig(
        type=EmulatorType.leidian,
        path='/emu/path',
        serial='emulator-5554',
        process_name='emulator.exe',
    )
    manager = _ConcreteManager(config)

    assert manager._config is config
    assert manager._emulator_type is EmulatorType.leidian
    assert manager._path == '/emu/path'
    assert manager._process_name == 'emulator.exe'
    assert manager._serial == 'emulator-5554'


def test_restart_calls_stop_then_start() -> None:
    """restart() must call stop() then start() in order."""
    config = EmulatorConfig()
    manager = _ConcreteManager(config)
    call_order: list[str] = []
    object.__setattr__(manager, 'stop', MagicMock(side_effect=lambda: call_order.append('stop')))
    object.__setattr__(manager, 'start', MagicMock(side_effect=lambda: call_order.append('start')))

    manager.restart()

    manager.stop.assert_called_once()
    manager.start.assert_called_once()
    assert call_order == ['stop', 'start']


def test_wait_until_online_succeeds_immediately() -> None:
    """wait_until_online returns at once when is_running is True."""
    config = EmulatorConfig()
    manager = _ConcreteManager(config)
    object.__setattr__(manager, 'is_running', MagicMock(return_value=True))

    manager.wait_until_online(timeout=10)

    manager.is_running.assert_called_once()


def test_wait_until_online_raises_on_timeout() -> None:
    """wait_until_online raises EmulatorError when is_running never becomes True."""
    config = EmulatorConfig()
    manager = _ConcreteManager(config)
    object.__setattr__(manager, 'is_running', MagicMock(return_value=False))

    with (
        patch(
            'autowsgr.emulator.os_control.base.time.monotonic',
            side_effect=[0.0, 0.5, 1.0, 2.0],
        ),
        patch('autowsgr.emulator.os_control.base.time.sleep'),
        pytest.raises(EmulatorError, match='模拟器启动超时'),
    ):
        manager.wait_until_online(timeout=1)


def test_wait_until_online_eventually_succeeds() -> None:
    """wait_until_online succeeds after a few False returns from is_running."""
    config = EmulatorConfig()
    manager = _ConcreteManager(config)
    object.__setattr__(
        manager,
        'is_running',
        MagicMock(
            side_effect=[False, False, True],
        ),
    )

    with (
        patch(
            'autowsgr.emulator.os_control.base.time.monotonic',
            side_effect=[0.0, 0.5, 1.0, 1.5, 2.0],
        ),
        patch('autowsgr.emulator.os_control.base.time.sleep') as mock_sleep,
    ):
        manager.wait_until_online(timeout=10)

    assert manager.is_running.call_count == 3
    assert mock_sleep.call_count == 2


def test_create_emulator_manager_windows() -> None:
    """create_emulator_manager with os_type=OSType.windows returns WindowsEmulatorManager."""
    config = MagicMock()
    manager = create_emulator_manager(config, os_type=OSType.windows)
    assert isinstance(manager, WindowsEmulatorManager)


def test_create_emulator_manager_macos() -> None:
    """create_emulator_manager with os_type=OSType.macos returns MacEmulatorManager."""
    config = MagicMock()
    manager = create_emulator_manager(config, os_type=OSType.macos)
    assert isinstance(manager, MacEmulatorManager)


def test_create_emulator_manager_linux() -> None:
    """create_emulator_manager with os_type=OSType.linux returns LinuxEmulatorManager."""
    config = MagicMock()
    manager = create_emulator_manager(config, os_type=OSType.linux)
    assert isinstance(manager, LinuxEmulatorManager)


def test_create_emulator_manager_unknown_os_raises() -> None:
    """create_emulator_manager with unknown os_type raises EmulatorError."""
    config = MagicMock()
    with pytest.raises(EmulatorError, match='不支持的操作系统'):
        create_emulator_manager(config, os_type=cast('Any', MagicMock()))


def test_create_emulator_manager_auto_detect_windows() -> None:
    """create_emulator_manager with os_type=None mocks OSType.auto to return windows."""
    config = MagicMock()
    with patch('autowsgr.emulator.os_control.OSType.auto', return_value=OSType.windows):
        manager = create_emulator_manager(config, os_type=None)
    assert isinstance(manager, WindowsEmulatorManager)
