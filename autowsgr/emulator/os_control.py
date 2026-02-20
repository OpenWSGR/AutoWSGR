"""模拟器进程管理 — 在宿主操作系统上控制模拟器的启动/停止/状态查询。

各操作系统有专属实现（分文件存放）：

- **Windows**: :mod:`autowsgr.emulator._os_windows`
- **macOS**: :mod:`autowsgr.emulator._os_macos`
- **Linux (WSL)**: :mod:`autowsgr.emulator._os_linux`

使用方式::

    from autowsgr.emulator.os_control import create_emulator_manager

    manager = create_emulator_manager(config)
    manager.start()
    manager.wait_until_online(timeout=120)
    manager.stop()
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

from autowsgr.infra import EmulatorConfig, EmulatorError
from autowsgr.types import OSType


class EmulatorProcessManager(ABC):
    """模拟器进程管理抽象基类。

    仅负责在宿主 OS 上管理模拟器 **进程** 的生命周期。
    与 *设备内部* 的 ADB 操作（截图/点击等）无关。

    Parameters
    ----------
    config:
        模拟器配置，包含类型、路径、进程名等。
    """

    def __init__(self, config: EmulatorConfig) -> None:
        self._config = config
        self._emulator_type = config.type
        self._path = config.path
        self._process_name = config.process_name
        self._serial = config.serial

    # ── 公共接口 ──

    @abstractmethod
    def is_running(self) -> bool:
        """模拟器进程是否正在运行。"""
        ...

    @abstractmethod
    def start(self) -> None:
        """启动模拟器进程。

        Raises
        ------
        EmulatorError
            启动失败时抛出。
        """
        ...

    @abstractmethod
    def stop(self) -> None:
        """停止（强杀）模拟器进程。

        Raises
        ------
        EmulatorError
            停止失败时抛出。
        """
        ...

    def restart(self) -> None:
        """先停止再启动模拟器。"""
        self.stop()
        self.start()

    def wait_until_online(self, timeout: float = 120) -> None:
        """阻塞等待模拟器上线。

        Parameters
        ----------
        timeout:
            超时秒数，超过后抛出异常。

        Raises
        ------
        EmulatorError
            超时仍未上线。
        """
        start_time = time.monotonic()
        while not self.is_running():
            if time.monotonic() - start_time > timeout:
                raise EmulatorError(f"模拟器启动超时 ({timeout}s)")
            time.sleep(1)


# ── 工厂函数 ──


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
            from autowsgr.emulator._os_windows import WindowsEmulatorManager

            return WindowsEmulatorManager(config)
        case OSType.macos:
            from autowsgr.emulator._os_macos import MacEmulatorManager

            return MacEmulatorManager(config)
        case OSType.linux:
            from autowsgr.emulator._os_linux import LinuxEmulatorManager

            return LinuxEmulatorManager(config)
        case _:
            raise EmulatorError(f"不支持的操作系统: {os_type}")
