"""测试 emulator.os_control 模块。

由于 OS 控制依赖真实进程/命令行工具，大部分测试使用 mock。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from autowsgr.emulator import (
    EmulatorProcessManager,
    create_emulator_manager,
    WindowsEmulatorManager,
    MacEmulatorManager,
    LinuxEmulatorManager,
)
from autowsgr.infra import EmulatorConfig, EmulatorError, EmulatorNotFoundError
from autowsgr.types import EmulatorType, OSType


# ═══════════════════════════════════════════════
# EmulatorProcessManager ABC
# ═══════════════════════════════════════════════


class TestEmulatorProcessManagerABC:
    """ABC 不能直接实例化。"""

    def test_cannot_instantiate(self):
        config = EmulatorConfig()
        with pytest.raises(TypeError, match="abstract"):
            EmulatorProcessManager(config)  # type: ignore[abstract]

    def test_abstract_methods(self):
        expected = {"is_running", "start", "stop"}
        assert EmulatorProcessManager.__abstractmethods__ == expected

    def test_restart_calls_stop_then_start(self):
        """restart 默认实现 = stop + start。"""

        class Stub(EmulatorProcessManager):
            calls: list[str] = []

            def is_running(self):
                return True

            def start(self):
                self.calls.append("start")

            def stop(self):
                self.calls.append("stop")

        mgr = Stub(EmulatorConfig())
        mgr.restart()
        assert mgr.calls == ["stop", "start"]

    def test_wait_until_online_immediate(self):
        """is_running 立刻返回 True 时直接通过。"""

        class Stub(EmulatorProcessManager):
            def is_running(self):
                return True

            def start(self):
                pass

            def stop(self):
                pass

        mgr = Stub(EmulatorConfig())
        mgr.wait_until_online(timeout=1)  # 不应抛异常

    def test_wait_until_online_timeout(self):
        """始终 False 时应超时。"""

        class Stub(EmulatorProcessManager):
            def is_running(self):
                return False

            def start(self):
                pass

            def stop(self):
                pass

        mgr = Stub(EmulatorConfig())
        with pytest.raises(EmulatorError, match="启动超时"):
            mgr.wait_until_online(timeout=0.5)


# ═══════════════════════════════════════════════
# 工厂函数
# ═══════════════════════════════════════════════


class TestCreateEmulatorManager:
    """create_emulator_manager 工厂函数。"""

    def test_windows(self):
        config = EmulatorConfig(type=EmulatorType.leidian)
        mgr = create_emulator_manager(config, os_type=OSType.windows)
        assert isinstance(mgr, WindowsEmulatorManager)

    def test_macos(self):
        config = EmulatorConfig(type=EmulatorType.mumu)
        mgr = create_emulator_manager(config, os_type=OSType.macos)
        assert isinstance(mgr, MacEmulatorManager)

    def test_linux(self):
        config = EmulatorConfig(type=EmulatorType.leidian)
        mgr = create_emulator_manager(config, os_type=OSType.linux)
        assert isinstance(mgr, LinuxEmulatorManager)

    def test_auto_os_detection(self):
        """不传 os_type 时自动检测。"""
        config = EmulatorConfig()
        mgr = create_emulator_manager(config)
        # 验证类型是三种之一
        assert isinstance(
            mgr, (WindowsEmulatorManager, MacEmulatorManager, LinuxEmulatorManager)
        )


# ═══════════════════════════════════════════════
# WindowsEmulatorManager
# ═══════════════════════════════════════════════


class TestWindowsEmulatorManager:
    """Windows 模拟器管理器测试。"""

    def test_yunshouji_always_running(self):
        config = EmulatorConfig(type=EmulatorType.yunshouji)
        mgr = WindowsEmulatorManager(config)
        assert mgr.is_running() is True

    def test_yunshouji_start_noop(self):
        config = EmulatorConfig(type=EmulatorType.yunshouji)
        mgr = WindowsEmulatorManager(config)
        mgr.start()  # 不应抛异常

    def test_yunshouji_stop_noop(self):
        config = EmulatorConfig(type=EmulatorType.yunshouji)
        mgr = WindowsEmulatorManager(config)
        mgr.stop()  # 不应抛异常

    def test_leidian_is_running_true(self):
        config = EmulatorConfig(
            type=EmulatorType.leidian,
            path=r"C:\LDPlayer\dnplayer.exe",
            serial="emulator-5554",
        )
        mgr = WindowsEmulatorManager(config)
        with patch.object(mgr, "_ldconsole", return_value="running"):
            assert mgr.is_running() is True

    def test_leidian_is_running_false(self):
        config = EmulatorConfig(
            type=EmulatorType.leidian,
            path=r"C:\LDPlayer\dnplayer.exe",
            serial="emulator-5554",
        )
        mgr = WindowsEmulatorManager(config)
        with patch.object(mgr, "_ldconsole", return_value="stopped"):
            assert mgr.is_running() is False

    def test_mumu_is_running_true(self):
        config = EmulatorConfig(
            type=EmulatorType.mumu,
            path=r"C:\MuMu\MuMuPlayer.exe",
            serial="127.0.0.1:16384",
        )
        mgr = WindowsEmulatorManager(config)
        json_resp = '{"is_android_started": true}'
        with patch.object(mgr, "_mumuconsole", return_value=json_resp):
            assert mgr.is_running() is True

    def test_mumu_is_running_false(self):
        config = EmulatorConfig(
            type=EmulatorType.mumu,
            path=r"C:\MuMu\MuMuPlayer.exe",
            serial="127.0.0.1:16384",
        )
        mgr = WindowsEmulatorManager(config)
        json_resp = '{"is_android_started": false}'
        with patch.object(mgr, "_mumuconsole", return_value=json_resp):
            assert mgr.is_running() is False

    def test_mumu_is_running_bad_json(self):
        config = EmulatorConfig(type=EmulatorType.mumu, path=r"C:\MuMu\x.exe")
        mgr = WindowsEmulatorManager(config)
        with patch.object(mgr, "_mumuconsole", return_value="not json"):
            assert mgr.is_running() is False

    def test_others_tasklist_check_running(self):
        config = EmulatorConfig(
            type=EmulatorType.bluestacks,
            process_name="HD-Player.exe",
        )
        mgr = WindowsEmulatorManager(config)
        fake_output = "映像名称  PID  会话名  会话#  内存使用\nHD-Player.exe  1234  Console  1  100,000 K".encode("gbk")
        with patch("autowsgr.emulator.os_control.subprocess.check_output", return_value=fake_output):
            assert mgr.is_running() is True

    def test_others_tasklist_check_not_running(self):
        config = EmulatorConfig(
            type=EmulatorType.bluestacks,
            process_name="HD-Player.exe",
        )
        mgr = WindowsEmulatorManager(config)
        fake_output = "信息: 没有运行的任务匹配".encode("gbk")
        with patch("subprocess.check_output", return_value=fake_output):
            assert mgr.is_running() is False

    def test_start_no_path_raises(self):
        config = EmulatorConfig(type=EmulatorType.leidian, path=None)
        mgr = WindowsEmulatorManager(config)
        with pytest.raises(EmulatorNotFoundError, match="路径"):
            mgr.start()

    def test_stop_no_process_name_raises(self):
        config = EmulatorConfig(type=EmulatorType.bluestacks, process_name=None)
        mgr = WindowsEmulatorManager(config)
        with pytest.raises(EmulatorError, match="进程名"):
            mgr.stop()


# ═══════════════════════════════════════════════
# MacEmulatorManager
# ═══════════════════════════════════════════════


class TestMacEmulatorManager:
    """macOS 模拟器管理器测试。"""

    def test_is_running_no_process_name(self):
        config = EmulatorConfig(type=EmulatorType.mumu, process_name=None)
        mgr = MacEmulatorManager(config)
        assert mgr.is_running() is False

    def test_is_running_process_not_found(self):
        config = EmulatorConfig(type=EmulatorType.bluestacks, process_name="bluestacks")
        mgr = MacEmulatorManager(config)
        from subprocess import CalledProcessError
        with patch("subprocess.check_output", side_effect=CalledProcessError(1, "pgrep")):
            assert mgr.is_running() is False

    def test_is_running_non_mumu(self):
        config = EmulatorConfig(type=EmulatorType.bluestacks, process_name="bluestacks")
        mgr = MacEmulatorManager(config)
        with patch("subprocess.check_output", return_value=b"12345"):
            assert mgr.is_running() is True

    def test_start_no_path_raises(self):
        config = EmulatorConfig(type=EmulatorType.bluestacks, path=None)
        mgr = MacEmulatorManager(config)
        with pytest.raises(EmulatorNotFoundError, match="路径"):
            mgr.start()

    def test_stop_no_process_name_raises(self):
        config = EmulatorConfig(type=EmulatorType.bluestacks, process_name=None)
        mgr = MacEmulatorManager(config)
        with pytest.raises(EmulatorError, match="进程名"):
            mgr.stop()

    def test_stop_mumu_noop(self):
        config = EmulatorConfig(type=EmulatorType.mumu, process_name="mumu")
        mgr = MacEmulatorManager(config)
        mgr.stop()  # MuMu macOS 暂不支持关闭，不应报错


# ═══════════════════════════════════════════════
# LinuxEmulatorManager
# ═══════════════════════════════════════════════


class TestLinuxEmulatorManager:
    """Linux/WSL 模拟器管理器测试。"""

    def test_start_no_path_raises(self):
        config = EmulatorConfig(type=EmulatorType.leidian, path=None)
        mgr = LinuxEmulatorManager(config)
        with pytest.raises(EmulatorNotFoundError, match="路径"):
            mgr.start()

    def test_stop_no_process_name_raises(self):
        config = EmulatorConfig(type=EmulatorType.leidian, process_name=None)
        mgr = LinuxEmulatorManager(config)
        with pytest.raises(EmulatorError, match="进程名"):
            mgr.stop()

    def test_adb_devices_empty(self):
        """_adb_devices 在异常时返回空列表。"""
        with patch(
            "autowsgr.emulator.os_control.LinuxEmulatorManager._adb_devices",
            return_value=[],
        ):
            config = EmulatorConfig(
                type=EmulatorType.leidian,
                serial="emulator-5554",
                process_name="ld",
            )
            mgr = LinuxEmulatorManager(config)
            # Patch is_wsl and pgrep
            mgr._is_wsl = False
            with patch("subprocess.run") as mock_run:
                from subprocess import CalledProcessError
                mock_run.side_effect = CalledProcessError(1, "pgrep")
                assert mgr.is_running() is False

    def test_is_running_adb_online(self):
        """设备在 ADB 列表中应返回 True。"""
        config = EmulatorConfig(
            type=EmulatorType.leidian,
            serial="emulator-5554",
        )
        mgr = LinuxEmulatorManager(config)
        with patch.object(
            LinuxEmulatorManager, "_adb_devices", return_value=["emulator-5554"]
        ):
            assert mgr.is_running() is True


# ═══════════════════════════════════════════════
# EmulatorConfig 集成
# ═══════════════════════════════════════════════


class TestEmulatorConfigIntegration:
    """验证 EmulatorConfig 与管理器联动。"""

    def test_default_config(self):
        config = EmulatorConfig()
        assert config.type == EmulatorType.leidian
        assert config.path is None
        assert config.serial is None
        assert config.process_name is None

    def test_config_types(self):
        for emu_type in EmulatorType:
            config = EmulatorConfig(type=emu_type)
            mgr = create_emulator_manager(config, os_type=OSType.windows)
            assert isinstance(mgr, WindowsEmulatorManager)
