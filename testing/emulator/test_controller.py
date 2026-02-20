"""测试 emulator.controller 模块。

由于 ADBController 依赖物理设备/模拟器，测试策略：
1. DeviceInfo — 不可变数据类
2. AndroidController — ABC 接口约束
3. ADBController — 坐标转换逻辑（mock airtest）
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from autowsgr.emulator import (
    ADBController,
    AndroidController,
    DeviceInfo,
)
from autowsgr.infra import EmulatorConnectionError


# ═══════════════════════════════════════════════
# AndroidController ABC
# ═══════════════════════════════════════════════


class TestAndroidControllerABC:
    """确保 AndroidController 不能直接实例化，且强制子类实现所有抽象方法。"""

    def test_complete_subclass(self):
        """实现全部抽象方法后可正常实例化。"""

        class Dummy(AndroidController):
            def connect(self):
                return DeviceInfo(serial="s", resolution=(100, 100))

            def disconnect(self):
                pass

            @property
            def resolution(self):
                return (100, 100)

            def screenshot(self):
                return np.zeros((100, 100, 3), dtype=np.uint8)

            def click(self, x, y):
                pass

            def swipe(self, x1, y1, x2, y2, duration=0.5):
                pass

            def long_tap(self, x, y, duration=1.0):
                pass

            def key_event(self, key_code):
                pass

            def text(self, content):
                pass

            def start_app(self, package):
                pass

            def stop_app(self, package):
                pass

            def is_app_running(self, package):
                return False

            def shell(self, cmd):
                return ""

        d = Dummy()
        assert isinstance(d, AndroidController)
        assert d.resolution == (100, 100)


# ═══════════════════════════════════════════════
# ADBController — 初始化 / 状态
# ═══════════════════════════════════════════════


class TestADBControllerInit:
    """ADBController 初始化行为。"""

    def test_disconnect_resets_state(self):
        ctrl = ADBController(serial="s")
        ctrl._resolution = (1920, 1080)
        ctrl._device = MagicMock()
        ctrl.disconnect()
        assert ctrl._device is None
        assert ctrl._resolution == (0, 0)


# ═══════════════════════════════════════════════
# ADBController — 坐标转换
# ═══════════════════════════════════════════════


class TestADBControllerCoordinates:
    """测试 click/swipe 的相对-绝对坐标转换。"""

    @pytest.fixture
    def ctrl(self):
        """创建一个 mock 设备的 ADBController。"""
        c = ADBController(serial="test")
        c._resolution = (960, 540)
        c._device = MagicMock()
        c._device.shell = MagicMock(return_value="")
        return c

    def test_click_center(self, ctrl):
        ctrl.click(0.5, 0.5)
        ctrl._device.shell.assert_called_once_with("input tap 480 270")

    def test_click_top_left(self, ctrl):
        ctrl.click(0.0, 0.0)
        ctrl._device.shell.assert_called_once_with("input tap 0 0")

    def test_click_bottom_right(self, ctrl):
        ctrl.click(1.0, 1.0)
        ctrl._device.shell.assert_called_once_with("input tap 960 540")

    def test_click_quarter(self, ctrl):
        ctrl.click(0.25, 0.75)
        ctrl._device.shell.assert_called_once_with("input tap 240 405")

    def test_swipe_default_duration(self, ctrl):
        ctrl.swipe(0.1, 0.2, 0.9, 0.8)
        ctrl._device.shell.assert_called_once_with("input swipe 96 108 864 432 500")

    def test_swipe_custom_duration(self, ctrl):
        ctrl.swipe(0.0, 0.0, 1.0, 1.0, duration=1.0)
        ctrl._device.shell.assert_called_once_with("input swipe 0 0 960 540 1000")

    def test_swipe_short_duration(self, ctrl):
        ctrl.swipe(0.5, 0.5, 0.6, 0.6, duration=0.2)
        ctrl._device.shell.assert_called_once_with("input swipe 480 270 576 324 200")

    def test_long_tap_delegates_to_swipe(self, ctrl):
        """long_tap 通过 swipe(x, y, x, y, duration) 实现。"""
        ctrl.long_tap(0.5, 0.5, duration=2.0)
        ctrl._device.shell.assert_called_once_with("input swipe 480 270 480 270 2000")

    def test_high_resolution(self):
        """1920×1080 分辨率下的转换。"""
        c = ADBController(serial="test")
        c._resolution = (1920, 1080)
        c._device = MagicMock()
        c._device.shell = MagicMock(return_value="")

        c.click(0.5, 0.5)
        c._device.shell.assert_called_once_with("input tap 960 540")


# ═══════════════════════════════════════════════
# ADBController — 截图
# ═══════════════════════════════════════════════


class TestADBControllerScreenshot:
    """测试截图功能（使用 mock）。"""

    def test_screenshot_bgr_to_rgb(self):
        """确认 BGR → RGB 转换。airtest snapshot 返回 BGR，screenshot() 转为 RGB。"""
        ctrl = ADBController(serial="test")
        ctrl._resolution = (4, 3)

        # 创建一个纯蓝色 BGR 图像（模拟 airtest snapshot 返回值）
        bgr = np.zeros((3, 4, 3), dtype=np.uint8)
        bgr[:, :, 0] = 255  # BGR 的 B 通道

        mock_device = MagicMock()
        mock_device.snapshot.return_value = bgr
        ctrl._device = mock_device

        result = ctrl.screenshot()
        # BGR(255,0,0) → RGB(0,0,255): 蓝色
        assert result.shape == (3, 4, 3)
        assert result[0, 0, 0] == 0    # R
        assert result[0, 0, 1] == 0    # G
        assert result[0, 0, 2] == 255  # B

    def test_screenshot_timeout(self):
        """截图超时应抛异常。"""
        ctrl = ADBController(serial="test", screenshot_timeout=0.2)
        ctrl._resolution = (4, 3)

        mock_device = MagicMock()
        mock_device.snapshot.return_value = None  # 始终返回 None
        ctrl._device = mock_device

        with pytest.raises(EmulatorConnectionError, match="截图超时"):
            ctrl.screenshot()

    def test_screenshot_retry_on_initial_none(self):
        """首次返回 None 后重试成功。"""
        ctrl = ADBController(serial="test", screenshot_timeout=5.0)
        ctrl._resolution = (2, 2)

        img = np.zeros((2, 2, 3), dtype=np.uint8)
        mock_device = MagicMock()
        mock_device.snapshot.side_effect = [None, img]
        ctrl._device = mock_device

        result = ctrl.screenshot()
        assert result.shape == (2, 2, 3)
        assert mock_device.snapshot.call_count == 2


# ═══════════════════════════════════════════════
# ADBController — 按键 / 文本 / 应用管理
# ═══════════════════════════════════════════════


class TestADBControllerAppManagement:
    """测试应用管理方法。"""

    @pytest.fixture
    def ctrl(self):
        c = ADBController(serial="test")
        c._device = MagicMock()
        return c

    def test_is_app_running_true(self, ctrl):
        ctrl._device.shell.return_value = "u0_a1 12345 com.example.app"
        assert ctrl.is_app_running("com.example.app") is True

    def test_is_app_running_false(self, ctrl):
        ctrl._device.shell.return_value = "u0_a1 12345 other.app"
        assert ctrl.is_app_running("com.example.app") is False

    def test_is_app_running_exception(self, ctrl):
        ctrl._device.shell.side_effect = Exception("device error")
        assert ctrl.is_app_running("com.example.app") is False


class TestADBControllerShell:
    """测试 shell 方法。"""

    def test_shell_non_string_result(self):
        ctrl = ADBController(serial="test")
        ctrl._device = MagicMock()  # type: ignore[assignment]
        ctrl._device.shell.return_value = 0  # type: ignore[union-attr]
        assert ctrl.shell("ls") == ""


# ═══════════════════════════════════════════════
# ADBController — 连接
# ═══════════════════════════════════════════════


class TestADBControllerConnect:
    """测试连接/断开功能。"""

    def test_connect_success(self):
        ctrl = ADBController(serial="emulator-5554")

        mock_device = MagicMock()
        mock_device.display_info = {"width": 960, "height": 540}

        with (
            patch(
                "autowsgr.emulator.controller.connect_device"
            ) as mock_connect,
            patch(
                "autowsgr.emulator.controller.get_device",
                return_value=mock_device,
            ),
        ):
            info = ctrl.connect()

        mock_connect.assert_called_once_with("Android:///emulator-5554")
        assert info.serial == "emulator-5554"
        assert info.resolution == (960, 540)
        assert ctrl.resolution == (960, 540)

    def test_connect_auto_serial(self):
        ctrl = ADBController()  # serial=None

        mock_device = MagicMock()
        mock_device.display_info = {"width": 1920, "height": 1080}

        with (
            patch(
                "autowsgr.emulator.controller.connect_device"
            ) as mock_connect,
            patch(
                "autowsgr.emulator.controller.get_device",
                return_value=mock_device,
            ),
        ):
            info = ctrl.connect()

        mock_connect.assert_called_once_with("Android:///")
        assert info.serial == "auto"
        assert info.resolution == (1920, 1080)
