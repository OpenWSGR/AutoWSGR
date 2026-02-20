"""Linux/WSL 模拟器进程管理。"""

from __future__ import annotations

import shlex
import subprocess

from loguru import logger

from .os_control import EmulatorProcessManager
from autowsgr.infra import EmulatorConfig, EmulatorError, EmulatorNotFoundError
from autowsgr.types import OSType


class LinuxEmulatorManager(EmulatorProcessManager):
    """Linux/WSL 宿主下的模拟器进程管理。

    WSL 模式下通过 ``tasklist.exe`` / ``taskkill.exe`` 控制 Windows 进程。
    """

    def __init__(self, config: EmulatorConfig) -> None:
        super().__init__(config)
        self._is_wsl = OSType._is_wsl()

    def is_running(self) -> bool:
        # 先检查 ADB 设备列表
        if self._serial and self._serial in self._adb_devices():
            return True
        if self._is_wsl:
            return self._is_windows_process_running()
        if not self._process_name:
            return False
        try:
            subprocess.run(
                ["pgrep", "-f", self._process_name],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except subprocess.CalledProcessError:
            return False

    def start(self) -> None:
        if not self._path:
            raise EmulatorNotFoundError(
                "未设置模拟器路径（WSL 需要显式设置）"
            )
        try:
            subprocess.Popen(shlex.split(self._path))
            logger.info("正在启动模拟器: {}", self._path)
            self.wait_until_online()
            logger.info("模拟器已启动")
        except EmulatorError:
            raise
        except Exception as exc:
            raise EmulatorError(f"启动模拟器失败: {exc}") from exc

    def stop(self) -> None:
        if not self._process_name:
            raise EmulatorError("未设置进程名，无法停止模拟器")
        try:
            if self._is_wsl:
                result = subprocess.run(
                    ["taskkill.exe", "/f", "/im", self._process_name],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    raise EmulatorError(
                        result.stderr.strip() or result.stdout.strip()
                    )
            else:
                subprocess.run(
                    ["pkill", "-9", "-f", self._process_name],
                    check=True,
                )
            logger.info("模拟器已停止: {}", self._process_name)
        except EmulatorError:
            raise
        except Exception as exc:
            raise EmulatorError(f"停止模拟器失败: {exc}") from exc

    # ── 辅助 ──

    @staticmethod
    def _adb_devices() -> list[str]:
        """列出通过 ADB 连接的设备。"""
        try:
            from airtest.core.android.adb import ADB

            adb = ADB().get_adb_path()
            result = subprocess.run(
                [adb, "devices"],
                capture_output=True,
                text=True,
                check=True,
            )
        except (ImportError, OSError, subprocess.CalledProcessError) as exc:
            logger.debug("[OS-Linux] ADB 设备列表获取失败: {}", exc)
            return []

        devices: list[str] = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("List of devices"):
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                devices.append(parts[0])
        return devices

    def _is_windows_process_running(self) -> bool:
        """WSL 下通过 tasklist.exe 检查 Windows 进程。"""
        if not self._process_name:
            return False
        result = subprocess.run(
            ["tasklist.exe", "/fi", f"IMAGENAME eq {self._process_name}"],
            capture_output=True,
            text=True,
        )
        output = (result.stdout or "").lower()
        if "no tasks" in output:
            return False
        return self._process_name.lower() in output
