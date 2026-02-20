"""模拟器进程管理子包。

将各操作系统的模拟器进程管理器统一组织在此包中：

- :mod:`.base`    — 抽象基类 :class:`EmulatorProcessManager`
- :mod:`.windows` — :class:`WindowsEmulatorManager`
- :mod:`.macos`   — :class:`MacEmulatorManager`
- :mod:`.linux`   — :class:`LinuxEmulatorManager`

使用方式::

    from autowsgr.emulator.os_control import create_emulator_manager

    manager = create_emulator_manager(config)
    manager.start()
    manager.wait_until_online(timeout=120)
    manager.stop()
"""

from __future__ import annotations

from .base import EmulatorProcessManager
from .linux import LinuxEmulatorManager
from .macos import MacEmulatorManager
from .windows import WindowsEmulatorManager

from autowsgr.infra import EmulatorConfig, EmulatorError
from autowsgr.types import OSType


def create_emulator_manager(
    config: EmulatorConfig,
    os_type: OSType | None = None,
) -> EmulatorProcessManager:
    """根据当前操作系统创建对应的模拟器进程管理器。

    Parameters
    ----------
    config:
        模拟器配置。
    os_type:
        操作系统类型，为 None 时自动检测。

    Returns
    -------
    EmulatorProcessManager
        对应操作系统的管理器实例。

    Raises
    ------
    EmulatorError
        不支持的操作系统。
    """
    if os_type is None:
        os_type = OSType.auto()

    match os_type:
        case OSType.windows:
            return WindowsEmulatorManager(config)
        case OSType.macos:
            return MacEmulatorManager(config)
        case OSType.linux:
            return LinuxEmulatorManager(config)
        case _:
            raise EmulatorError(f"不支持的操作系统: {os_type}")


__all__ = [
    "EmulatorProcessManager",
    "WindowsEmulatorManager",
    "MacEmulatorManager",
    "LinuxEmulatorManager",
    "create_emulator_manager",
]
