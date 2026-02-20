"""模拟器进程管理抽象基类。"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

from autowsgr.infra import EmulatorConfig, EmulatorError


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
