"""测试 emulator.controller 模块。

由于 ScrcpyController 依赖物理设备/模拟器，测试策略：
1. DeviceInfo — 不可变数据类
2. ScrcpyController — ABC 接口约束
3. ScrcpyController — 坐标转换逻辑（mock airtest）
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import numpy as np
import pytest

from autowsgr.emulator import (
    ScrcpyController,
)
from autowsgr.infra import EmulatorConnectionError


# ═══════════════════════════════════════════════
# ScrcpyController — 初始化 / 状态
# ═══════════════════════════════════════════════


class TestScrcpyControllerInit:
    """ScrcpyController 初始化行为。"""

    def test_disconnect_resets_state(self):
        ctrl = ScrcpyController(serial='s')
        ctrl._resolution = (1920, 1080)
        ctrl._device = MagicMock()
        ctrl.disconnect()
        assert ctrl._device is None
        assert ctrl._resolution == (0, 0)


# ═══════════════════════════════════════════════
# ScrcpyController — 坐标转换
# ═══════════════════════════════════════════════


class TestScrcpyControllerCoordinates:
    """测试 click/swipe 的相对-绝对坐标转换。"""

    @pytest.fixture
    def ctrl(self) -> ScrcpyController:
        """创建一个 mock 设备的 ScrcpyController。"""
        c = ScrcpyController(serial='test')
        c._resolution = (960, 540)
        c._device = MagicMock()
        c._device.shell = MagicMock(return_value='')
        return c

    def test_click_center(self, ctrl: ScrcpyController):
        ctrl.click(0.5, 0.5)
        ctrl._device.shell.assert_called_once_with('input tap 480 270')  # ty: ignore[unresolved-attribute]

    def test_click_top_left(self, ctrl: ScrcpyController):
        ctrl.click(0.0, 0.0)
        ctrl._device.shell.assert_called_once_with('input tap 0 0')  # ty: ignore[unresolved-attribute]

    def test_click_bottom_right(self, ctrl: ScrcpyController):
        ctrl.click(1.0, 1.0)
        ctrl._device.shell.assert_called_once_with('input tap 960 540')  # ty: ignore[unresolved-attribute]

    def test_click_quarter(self, ctrl: ScrcpyController):
        ctrl.click(0.25, 0.75)
        ctrl._device.shell.assert_called_once_with('input tap 240 405')  # ty: ignore[unresolved-attribute]

    def test_swipe_default_duration(self, ctrl: ScrcpyController):
        ctrl.swipe(0.1, 0.2, 0.9, 0.8)
        ctrl._device.shell.assert_called_once_with('input swipe 96 108 864 432 500')  # ty: ignore[unresolved-attribute]

    def test_swipe_custom_duration(self, ctrl: ScrcpyController):
        ctrl.swipe(0.0, 0.0, 1.0, 1.0, duration=1.0)
        ctrl._device.shell.assert_called_once_with('input swipe 0 0 960 540 1000')  # ty: ignore[unresolved-attribute]

    def test_swipe_short_duration(self, ctrl: ScrcpyController):
        ctrl.swipe(0.5, 0.5, 0.6, 0.6, duration=0.2)
        ctrl._device.shell.assert_called_once_with('input swipe 480 270 576 324 200')  # ty: ignore[unresolved-attribute]

    def test_long_tap_delegates_to_swipe(self, ctrl: ScrcpyController):
        """long_tap 通过 swipe(x, y, x, y, duration) 实现。"""
        ctrl.long_tap(0.5, 0.5, duration=2.0)
        ctrl._device.shell.assert_called_once_with('input swipe 480 270 480 270 2000')  # ty: ignore[unresolved-attribute]

    def test_high_resolution(self):
        """1920x1080 分辨率下的转换。"""
        c = ScrcpyController(serial='test')
        c._resolution = (1920, 1080)
        c._device = MagicMock()
        c._device.shell = MagicMock(return_value='')

        c.click(0.5, 0.5)
        c._device.shell.assert_called_once_with('input tap 960 540')


# ═══════════════════════════════════════════════
# ScrcpyController — 截图
# ═══════════════════════════════════════════════


class TestScrcpyControllerScreenshot:
    """测试截图功能（使用 mock）。"""

    def test_screenshot_returns_last_frame(self):
        """screenshot() 返回 _last_frame 中的图像。"""
        ctrl = ScrcpyController(serial='test')
        ctrl._resolution = (4, 3)

        # mock 视频流，避免启动真实 scrcpy 连接
        object.__setattr__(ctrl, '_ensure_stream_alive', MagicMock())
        ctrl._alive = True

        img = np.zeros((3, 4, 3), dtype=np.uint8)
        ctrl._last_frame = img

        result = ctrl.screenshot()
        assert result.shape == (3, 4, 3)
        assert result is img

    def test_screenshot_timeout(self):
        """截图超时应抛异常。"""
        ctrl = ScrcpyController(serial='test', screenshot_timeout=0.2)
        ctrl._resolution = (4, 3)

        # mock 视频流，避免启动真实 scrcpy 连接
        object.__setattr__(ctrl, '_ensure_stream_alive', MagicMock())
        ctrl._alive = True
        ctrl._last_frame = None  # 始终无帧

        with pytest.raises(EmulatorConnectionError, match='截图超时'):
            ctrl.screenshot()

    def test_screenshot_retry_on_initial_none(self):
        """首次返回 None 后重试成功。"""
        ctrl = ScrcpyController(serial='test', screenshot_timeout=5.0)
        ctrl._resolution = (2, 2)

        # mock 视频流，避免启动真实 scrcpy 连接
        object.__setattr__(ctrl, '_ensure_stream_alive', MagicMock())
        ctrl._alive = True

        img = np.zeros((2, 2, 3), dtype=np.uint8)

        # 直接测试逻辑：先 None 后成功
        ctrl._last_frame = None
        # 在 screenshot() 循环中手动注入帧
        import threading

        def _inject_frame():
            time.sleep(0.05)
            ctrl._last_frame = img

        threading.Thread(target=_inject_frame, daemon=True).start()
        result = ctrl.screenshot()
        assert result.shape == (2, 2, 3)
        assert result is img
