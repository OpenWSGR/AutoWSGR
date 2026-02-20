"""模拟器层 — 设备控制与进程管理。

提供两大核心能力：

1. **设备控制** (`AndroidController` / `ADBController`)：
   截图、点击、滑动、按键、应用管理等纯设备操作。
   所有触控坐标使用相对值 (0.0–1.0)。

2. **进程管理** (`EmulatorProcessManager` / `create_emulator_manager`)：
   在宿主操作系统上启动、停止、检测模拟器进程。
"""

from autowsgr.emulator.controller import (
    ADBController,
    AndroidController,
    DeviceInfo,
)
from autowsgr.emulator.detector import (
    EmulatorCandidate,
    detect_emulators,
    resolve_serial,
)
from autowsgr.emulator.os_control import (
    EmulatorProcessManager,
    create_emulator_manager,
)
from autowsgr.emulator._os_windows import WindowsEmulatorManager
from autowsgr.emulator._os_macos import MacEmulatorManager
from autowsgr.emulator._os_linux import LinuxEmulatorManager

__all__ = [
    # controller
    "AndroidController",
    "ADBController",
    "DeviceInfo",
    # detector
    "EmulatorCandidate",
    "detect_emulators",
    "resolve_serial",
    # os_control
    "EmulatorProcessManager",
    "WindowsEmulatorManager",
    "MacEmulatorManager",
    "LinuxEmulatorManager",
    "create_emulator_manager",
]
