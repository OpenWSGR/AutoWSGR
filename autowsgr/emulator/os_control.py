"""模拟器进程管理 — 在宿主操作系统上控制模拟器的启动/停止/状态查询。

各操作系统有专属实现：

- **Windows**: 通过厂商 CLI 工具（ldconsole / MuMuManager）或 ``taskkill``
- **macOS**: 通过 ``open -a`` / ``pkill``
- **Linux (WSL)**: 通过 ``tasklist.exe`` / ``taskkill.exe`` + ADB devices 检测

使用方式::

    from autowsgr.emulator.os_control import create_emulator_manager

    manager = create_emulator_manager(config)
    manager.start()
    manager.wait_until_online(timeout=120)
    manager.stop()
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import time
from abc import ABC, abstractmethod

from loguru import logger

from autowsgr.infra.config import EmulatorConfig
from autowsgr.infra.exceptions import EmulatorError, EmulatorNotFoundError
from autowsgr.types import EmulatorType, OSType


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


# ── Windows 实现 ──


class WindowsEmulatorManager(EmulatorProcessManager):
    """Windows 宿主下的模拟器进程管理。

    针对不同厂商使用对应 CLI 工具：

    - 雷电 → ``ldconsole.exe``
    - MuMu → ``MuMuManager.exe``
    - 其他 → ``taskkill``
    """

    def is_running(self) -> bool:
        match self._emulator_type:
            case EmulatorType.leidian:
                raw = self._ldconsole("isrunning")
                logger.debug("雷电模拟器状态: {}", raw)
                return raw.strip() == "running"
            case EmulatorType.mumu:
                raw = self._mumuconsole("is_android_started")
                try:
                    result = json.loads(raw)
                    is_started = result.get("is_android_started", False)
                except (json.JSONDecodeError, KeyError):
                    is_started = False
                logger.debug("MuMu 模拟器状态: {}", is_started)
                return bool(is_started)
            case EmulatorType.yunshouji:
                return True  # 云手机始终在线
            case _:
                return self._tasklist_check()

    def start(self) -> None:
        if self._emulator_type == EmulatorType.yunshouji:
            logger.info("云手机无需启动")
            return

        if self._path is None:
            raise EmulatorNotFoundError("未设置模拟器路径，无法启动")

        try:
            match self._emulator_type:
                case EmulatorType.leidian:
                    self._ldconsole("launch")
                case EmulatorType.mumu:
                    self._mumuconsole("launch")
                case _:
                    os.popen(self._path)

            self.wait_until_online()
            logger.info("模拟器已启动")
        except EmulatorError:
            raise
        except Exception as exc:
            raise EmulatorError(f"启动模拟器失败: {exc}") from exc

    def stop(self) -> None:
        try:
            match self._emulator_type:
                case EmulatorType.leidian:
                    self._ldconsole("quit")
                case EmulatorType.mumu:
                    self._mumuconsole("shutdown")
                case EmulatorType.yunshouji:
                    logger.info("云手机无需关闭")
                    return
                case _:
                    if not self._process_name:
                        raise EmulatorError("未设置进程名，无法停止模拟器")
                    subprocess.run(
                        ["taskkill", "-f", "-im", self._process_name],
                        check=True,
                        capture_output=True,
                    )
            logger.info("模拟器已停止")
        except EmulatorError:
            raise
        except Exception as exc:
            raise EmulatorError(f"停止模拟器失败: {exc}") from exc

    # ── 雷电 CLI ──

    def _ldconsole(self, command: str, command_arg: str = "") -> str:
        """调用 ldconsole.exe 控制雷电模拟器。"""
        if not self._path:
            raise EmulatorNotFoundError("未设置雷电模拟器路径")

        console = os.path.join(os.path.dirname(self._path), "ldconsole.exe")
        if not os.path.isfile(console):
            raise EmulatorNotFoundError(f"找不到 ldconsole.exe: {console}")

        serial = self._serial or "emulator-5554"
        match = re.search(r"\d+", serial)
        emulator_index = int((int(match.group()) - 5554) / 2) if match else 0

        cmd: list[str] = [console, command, "--index", str(emulator_index)]
        if command_arg:
            cmd.append(command_arg)

        return self._run_cmd(cmd)

    # ── MuMu CLI ──

    def _mumuconsole(self, command: str, command_arg: str = "") -> str:
        """调用 MuMuManager.exe 控制 MuMu 模拟器。"""
        if not self._path:
            raise EmulatorNotFoundError("未设置 MuMu 模拟器路径")

        console = os.path.join(os.path.dirname(self._path), "MuMuManager.exe")
        if not os.path.isfile(console):
            raise EmulatorNotFoundError(f"找不到 MuMuManager.exe: {console}")

        serial = self._serial or "127.0.0.1:16384"
        num_match = re.search(r"[:-]\s*(\d+)", serial)
        if num_match:
            num = int(num_match.group(1))
            emulator_index = (num - 16384) // 32 if num >= 16384 else (num - 5555) // 2
        else:
            emulator_index = 0

        order = "info" if command == "is_android_started" else "control"
        cmd: list[str] = [console, order, "-v", str(emulator_index), command]
        if command_arg:
            cmd.append(command_arg)

        return self._run_cmd(cmd)

    # ── 通用进程检测 ──

    def _tasklist_check(self) -> bool:
        """通过 tasklist 检查进程是否存在。"""
        if not self._process_name:
            return False
        try:
            raw = subprocess.check_output(
                f'tasklist /fi "ImageName eq {self._process_name}"',
                shell=True,
            ).decode("gbk", errors="replace")
            return "PID" in raw
        except subprocess.CalledProcessError:
            return False

    @staticmethod
    def _run_cmd(cmd: list[str]) -> str:
        """执行外部命令并返回 stdout。"""
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True,
        )
        out, err = proc.communicate()
        return (
            out.decode("utf-8", errors="replace")
            if out
            else err.decode("utf-8", errors="replace")
        )


# ── macOS 实现 ──


class MacEmulatorManager(EmulatorProcessManager):
    """macOS 宿主下的模拟器进程管理。"""

    def is_running(self) -> bool:
        if not self._process_name:
            return False
        try:
            subprocess.check_output(f"pgrep -f {self._process_name}", shell=True)
        except subprocess.CalledProcessError:
            return False

        if self._emulator_type == EmulatorType.mumu:
            mumu_info = self._get_mumu_info()
            port = (self._serial or "").split(":")[-1]
            results = mumu_info.get("return", {}).get("results", [])
            return any(port == v.get("adb_port") for v in results)
        return True

    def start(self) -> None:
        if not self._path:
            raise EmulatorNotFoundError("未设置模拟器路径，无法启动")

        try:
            subprocess.Popen(f"open -a {self._path}", shell=True)
            if self._emulator_type == EmulatorType.mumu:
                self._mumu_restart_instance()
            self.wait_until_online()
            logger.info("模拟器已启动")
        except EmulatorError:
            raise
        except Exception as exc:
            raise EmulatorError(f"启动模拟器失败: {exc}") from exc

    def stop(self) -> None:
        if self._emulator_type == EmulatorType.mumu:
            logger.info("MuMu macOS 版暂不支持 CLI 关闭")
            return
        if not self._process_name:
            raise EmulatorError("未设置进程名，无法停止")
        try:
            subprocess.Popen(f"pkill -9 -f {self._process_name}", shell=True)
            logger.info("模拟器已停止")
        except Exception as exc:
            raise EmulatorError(f"停止模拟器失败: {exc}") from exc

    # ── MuMu macOS 辅助 ──

    @property
    def _mumu_tool(self) -> str:
        if not self._path:
            return ""
        return os.path.join(self._path, "Contents/MacOS/mumutool")

    def _get_mumu_info(self) -> dict:
        tool = self._mumu_tool
        if not tool or not os.path.isfile(tool):
            return {}
        proc = subprocess.Popen(
            f"{tool} info all",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True,
        )
        out, _ = proc.communicate()
        try:
            return json.loads(out.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def _mumu_restart_instance(self) -> None:
        """重启对应 MuMu 实例（通过端口匹配）。"""
        tool = self._mumu_tool
        port = (self._serial or "").split(":")[-1]
        info = self._get_mumu_info()
        for idx, v in enumerate(info.get("return", {}).get("results", [])):
            if port == v.get("adb_port"):
                subprocess.Popen(
                    f"{tool} restart {idx}",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=True,
                )
                break


# ── Linux (含 WSL) 实现 ──


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
            raise EmulatorNotFoundError("未设置模拟器路径（WSL 需要显式设置）")
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
        except Exception:
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
            return WindowsEmulatorManager(config)
        case OSType.macos:
            return MacEmulatorManager(config)
        case OSType.linux:
            return LinuxEmulatorManager(config)
        case _:
            raise EmulatorError(f"不支持的操作系统: {os_type}")
