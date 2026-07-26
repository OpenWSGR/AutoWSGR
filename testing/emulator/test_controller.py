"""测试 emulator.controller 模块。

由于 ScrcpyController 依赖物理设备/模拟器，测试策略：
1. DeviceInfo — 不可变数据类
2. ScrcpyController — ABC 接口约束
3. ScrcpyController — 控制流消息序列化与坐标转换（mock control socket）
"""

from __future__ import annotations

import struct
import time
from unittest.mock import MagicMock

import numpy as np
import pytest

from autowsgr.emulator import (
    ScrcpyController,
)
from autowsgr.infra import EmulatorConnectionError


# ── 控制流协议常量（与 scrcpy.py 保持一致）──
_TYPE_INJECT_TOUCH_EVENT = 2
_TYPE_INJECT_KEYCODE = 0
_TYPE_INJECT_TEXT = 1
_TYPE_SET_CLIPBOARD = 9
_ACTION_DOWN = 0
_ACTION_UP = 1
_ACTION_MOVE = 2
_POINTER_ID_FINGER = -2


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
# ScrcpyController — 控制流消息序列化与坐标转换
# ═══════════════════════════════════════════════


class TestScrcpyControllerControlFlow:
    """测试 click/swipe/key_event/text 通过控制流发送正确的二进制消息。"""

    @pytest.fixture
    def ctrl(self) -> ScrcpyController:
        """创建一个 mock 设备 + mock 控制通道的 ScrcpyController。"""
        c = ScrcpyController(serial='test')
        c._resolution = (960, 540)
        c._device = MagicMock()
        c._alive = True
        c._control_socket = MagicMock()
        return c

    @staticmethod
    def _parse_touch(data: bytes) -> tuple:
        """解析 INJECT_TOUCH_EVENT 消息，返回各字段元组。

        布局：type(1) | action(1) | pointer_id(8) | x(4) | y(4)
              | width(2) | height(2) | pressure(2) | action_button(4) | buttons(4)

        返回索引：[0]type [1]action [2]pointer_id [3]x [4]y
                  [5]width [6]height [7]pressure [8]action_button [9]buttons
        """
        return struct.unpack('>BBqIIHHHII', data)

    def test_click_center(self, ctrl: ScrcpyController):
        """click(0.5, 0.5) 在 960x540 上 → DOWN+UP at (480, 270)。"""
        sock = ctrl._control_socket
        ctrl.click(0.5, 0.5, delay=False)
        assert sock.sendall.call_count == 2
        down = self._parse_touch(sock.sendall.call_args_list[0].args[0])
        up = self._parse_touch(sock.sendall.call_args_list[1].args[0])
        assert down[0] == _TYPE_INJECT_TOUCH_EVENT
        assert down[1] == _ACTION_DOWN
        assert down[3] == 480 and down[4] == 270
        assert up[1] == _ACTION_UP
        assert down[5] == 960 and down[6] == 540  # width, height

    def test_click_top_left(self, ctrl: ScrcpyController):
        ctrl.click(0.0, 0.0, delay=False)
        down = self._parse_touch(ctrl._control_socket.sendall.call_args_list[0].args[0])
        assert down[3] == 0 and down[4] == 0

    def test_click_bottom_right(self, ctrl: ScrcpyController):
        ctrl.click(1.0, 1.0, delay=False)
        down = self._parse_touch(ctrl._control_socket.sendall.call_args_list[0].args[0])
        assert down[3] == 960 and down[4] == 540

    def test_click_quarter(self, ctrl: ScrcpyController):
        ctrl.click(0.25, 0.75, delay=False)
        down = self._parse_touch(ctrl._control_socket.sendall.call_args_list[0].args[0])
        assert down[3] == 240 and down[4] == 405

    def test_swipe_down_move_up(self, ctrl: ScrcpyController):
        """swipe 发送 DOWN、中间多个 MOVE、最后 UP。"""
        sock = ctrl._control_socket
        ctrl.swipe(0.1, 0.2, 0.9, 0.8, duration=0.1, delay=False)
        frames = [c.args[0] for c in sock.sendall.call_args_list]
        first = self._parse_touch(frames[0])
        last = self._parse_touch(frames[-1])
        assert first[0] == _TYPE_INJECT_TOUCH_EVENT
        assert first[1] == _ACTION_DOWN
        assert first[3] == 96 and first[4] == 108
        assert last[1] == _ACTION_UP
        assert last[3] == 864 and last[4] == 432
        # 中间应有 MOVE
        middle_actions = {self._parse_touch(f)[1] for f in frames[1:-1]}
        assert _ACTION_MOVE in middle_actions

    def test_long_tap_down_then_up(self, ctrl: ScrcpyController):
        """long_tap 发送 DOWN、等待、UP，坐标相同。"""
        sock = ctrl._control_socket
        ctrl.long_tap(0.5, 0.5, duration=0.05)
        assert sock.sendall.call_count == 2
        down = self._parse_touch(sock.sendall.call_args_list[0].args[0])
        up = self._parse_touch(sock.sendall.call_args_list[1].args[0])
        assert down[3] == up[3] == 480
        assert down[4] == up[4] == 270

    def test_key_event_sends_keycode_down_up(self, ctrl: ScrcpyController):
        """key_event 通过 INJECT_KEYCODE 发送 DOWN+UP。"""
        sock = ctrl._control_socket
        ctrl.key_event(4, delay=False)  # BACK
        assert sock.sendall.call_count == 2
        # 每条 14 字节：type(1) action(1) keycode(4) repeat(4) meta(4)
        d0 = sock.sendall.call_args_list[0].args[0]
        d1 = sock.sendall.call_args_list[1].args[0]
        assert len(d0) == 14 and len(d1) == 14
        t0, a0, k0, _, _ = struct.unpack('>BBIII', d0)
        t1, a1, k1, _, _ = struct.unpack('>BBIII', d1)
        assert t0 == _TYPE_INJECT_KEYCODE and t1 == _TYPE_INJECT_KEYCODE
        assert k0 == 4 and k1 == 4
        assert a0 == 0  # DOWN
        assert a1 == 1  # UP

    def test_text_sends_inject_text(self, ctrl: ScrcpyController):
        """text 通过 INJECT_TEXT 发送 UTF-8 文本。"""
        sock = ctrl._control_socket
        ctrl.text('hello', delay=False)
        assert sock.sendall.call_count == 1
        data = sock.sendall.call_args_list[0].args[0]
        msg_type = data[0]
        length = struct.unpack('>I', data[1:5])[0]
        payload = data[5:]
        assert msg_type == _TYPE_INJECT_TEXT
        assert length == 5
        assert payload == b'hello'

    def test_text_chinese_uses_set_clipboard(self, ctrl: ScrcpyController):
        """中文文本走 SET_CLIPBOARD+paste 路径。"""
        sock = ctrl._control_socket
        ctrl.text('你好', delay=False)
        assert sock.sendall.call_count == 1
        data = sock.sendall.call_args_list[0].args[0]
        # type(1) | sequence(8) | paste(1) | length(4) | utf8
        assert data[0] == _TYPE_SET_CLIPBOARD
        assert data[9] == 1  # paste=True
        length = struct.unpack('>I', data[10:14])[0]
        assert length == 6  # 你好 = 6 bytes UTF-8
        assert data[14:] == '你好'.encode('utf-8')

    def test_high_resolution(self):
        """1920x1080 分辨率下坐标转换正确。"""
        c = ScrcpyController(serial='test')
        c._resolution = (1920, 1080)
        c._device = MagicMock()
        c._alive = True
        c._control_socket = MagicMock()
        c.click(0.5, 0.5, delay=False)
        down = TestScrcpyControllerControlFlow._parse_touch(
            c._control_socket.sendall.call_args_list[0].args[0]
        )
        assert down[3] == 960 and down[4] == 540

    def test_control_socket_none_raises(self, ctrl: ScrcpyController):
        """控制通道未连接时调用触控应抛异常。"""
        ctrl._control_socket = None
        ctrl._alive = False
        ctrl._ensure_stream_alive = MagicMock(side_effect=EmulatorConnectionError('mock'))
        with pytest.raises(EmulatorConnectionError):
            ctrl._send_control(b'\x00')


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
        ctrl._ensure_stream_alive = MagicMock()
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
        ctrl._ensure_stream_alive = MagicMock()
        ctrl._alive = True
        ctrl._last_frame = None  # 始终无帧

        with pytest.raises(EmulatorConnectionError, match='截图超时'):
            ctrl.screenshot()

    def test_screenshot_retry_on_initial_none(self):
        """首次返回 None 后重试成功。"""
        ctrl = ScrcpyController(serial='test', screenshot_timeout=5.0)
        ctrl._resolution = (2, 2)

        # mock 视频流，避免启动真实 scrcpy 连接
        ctrl._ensure_stream_alive = MagicMock()
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
