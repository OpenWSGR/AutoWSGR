"""Windows 模拟器进程管理。"""

from __future__ import annotations

import json
import os
import re
import subprocess

from loguru import logger

from .base import EmulatorProcessManager
from autowsgr.infra import EmulatorError, EmulatorNotFoundError
from autowsgr.types import EmulatorType


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
            emulator_index = (
                (num - 16384) // 32 if num >= 16384 else (num - 5555) // 2
            )
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
