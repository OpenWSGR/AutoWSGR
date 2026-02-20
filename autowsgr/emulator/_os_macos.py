"""macOS 模拟器进程管理。"""

from __future__ import annotations

import json
import os
import subprocess

from loguru import logger

from .os_control import EmulatorProcessManager
from autowsgr.infra import EmulatorError, EmulatorNotFoundError
from autowsgr.types import EmulatorType


class MacEmulatorManager(EmulatorProcessManager):
    """macOS 宿主下的模拟器进程管理。"""

    def is_running(self) -> bool:
        if not self._process_name:
            return False
        try:
            subprocess.check_output(
                f"pgrep -f {self._process_name}", shell=True
            )
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
            subprocess.Popen(
                f"pkill -9 -f {self._process_name}", shell=True
            )
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
        for idx, v in enumerate(
            info.get("return", {}).get("results", [])
        ):
            if port == v.get("adb_port"):
                subprocess.Popen(
                    f"{tool} restart {idx}",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=True,
                )
                break
