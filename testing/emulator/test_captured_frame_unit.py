"""解码帧身份测试，不启动模拟器或网络连接。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import numpy as np

from autowsgr.emulator.controller import scrcpy
from autowsgr.emulator.controller.protocol import AndroidController
from autowsgr.emulator.controller.scrcpy import ScrcpyController


if TYPE_CHECKING:
    import pytest


def _controller() -> ScrcpyController:
    ctrl = ScrcpyController(serial='frame-test')
    ctrl._ensure_stream_alive = MagicMock()
    ctrl._alive = True
    return ctrl


def test_same_decoded_frame_has_stable_identity_and_time(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = _controller()
    image = np.zeros((3, 4, 3), dtype=np.uint8)
    monkeypatch.setattr(scrcpy.time, 'monotonic', lambda: 12.5)
    ctrl._publish_frame(image, ctrl._stream_id)
    first = ctrl.capture_frame()
    monkeypatch.setattr(scrcpy.time, 'monotonic', lambda: 20.0)
    second = ctrl.capture_frame()
    assert first.image is image
    assert second.image is image
    assert first.sequence == second.sequence
    assert first.sequence is not None
    assert first.captured_at == second.captured_at == 12.5
    assert ctrl.screenshot() is image


def test_identical_pixels_from_new_decode_still_get_new_sequence() -> None:
    ctrl = _controller()
    image = np.zeros((3, 4, 3), dtype=np.uint8)
    ctrl._publish_frame(image, ctrl._stream_id)
    first = ctrl.capture_frame()
    ctrl._publish_frame(image.copy(), ctrl._stream_id)
    second = ctrl.capture_frame()
    assert first.sequence is not None
    assert second.sequence is not None
    assert second.sequence > first.sequence


def test_stream_restart_does_not_reuse_ids_and_rejects_retired_frames(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctrl = _controller()
    image = np.zeros((3, 4, 3), dtype=np.uint8)
    old_stream = ctrl._stream_id
    ctrl._publish_frame(image, old_stream)
    old = ctrl.capture_frame()
    monkeypatch.setattr(scrcpy.threading, 'Thread', MagicMock())
    ctrl._start_decode_thread()
    assert ctrl._last_frame is None
    ctrl._publish_frame(image, old_stream)
    assert ctrl._last_frame is None
    fresh_image = np.ones_like(image)
    ctrl._publish_frame(fresh_image, ctrl._stream_id)
    fresh = ctrl.capture_frame()
    assert old.sequence is not None
    assert fresh.sequence is not None
    assert fresh.sequence > old.sequence
    assert fresh.image is fresh_image
    another = _controller()
    another._publish_frame(image, another._stream_id)
    assert another.capture_frame().sequence != fresh.sequence


def test_abc_fallback_keeps_identity_unknown() -> None:
    image = np.zeros((2, 2, 3), dtype=np.uint8)
    fake = SimpleNamespace(screenshot=lambda: image)
    first = AndroidController.capture_frame(fake)
    second = AndroidController.capture_frame(fake)
    assert first.image is image
    assert first.sequence is None
    assert second.sequence is None
    assert second.captured_at >= first.captured_at


def test_disconnect_rejects_late_decode_before_any_reconnection() -> None:
    ctrl = _controller()
    image = np.zeros((3, 4, 3), dtype=np.uint8)
    old_stream = ctrl._stream_id
    ctrl._publish_frame(image, old_stream)
    ctrl.disconnect()
    # 模拟等待超时后仍未退出的旧解码线程。
    ctrl._publish_frame(image, old_stream)
    assert ctrl._last_frame is None
    assert ctrl._last_frame_sequence is None
    assert not ctrl._frame_ready.is_set()
    assert not ctrl._alive


def test_decode_loop_publishes_every_decoded_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    import av

    ctrl = _controller()
    images = [np.zeros((2, 2, 3), dtype=np.uint8), np.ones((2, 2, 3), dtype=np.uint8)]
    codec = MagicMock()
    codec.parse.return_value = ['packet']
    codec.decode.return_value = [
        SimpleNamespace(to_ndarray=lambda image=x, **_: image) for x in images
    ]
    # av 的扩展类型不可修改，因此替换模块中暴露的类。
    monkeypatch.setattr(av, 'CodecContext', SimpleNamespace(create=lambda *_: codec))
    ctrl._video_socket = MagicMock()
    ctrl._video_socket.recv.side_effect = [b'packet', b'']
    captured = []
    publish = ctrl._publish_frame

    def record(image: np.ndarray, stream_id: int) -> None:
        publish(image, stream_id)
        captured.append(ctrl.capture_frame())

    monkeypatch.setattr(ctrl, '_publish_frame', record)
    ctrl._stream_loop(ctrl._stream_id)
    assert len(captured) == 2
    assert captured[0].image is images[0]
    assert captured[1].image is images[1]
    assert captured[0].sequence < captured[1].sequence
