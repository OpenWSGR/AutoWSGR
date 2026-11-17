"""节点定位和裁剪只使用调用者提供的同一张帧。"""

from __future__ import annotations

import threading
from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from autowsgr.emulator.frame import CapturedFrame
from autowsgr.image_resources import Templates
from autowsgr.infra import DecisiveConfig
from autowsgr.ui.decisive import map_controller as module
from autowsgr.ui.decisive.map_controller import DecisiveMapController


def make_controller() -> DecisiveMapController:
    ctx = SimpleNamespace(ctrl=MagicMock(), ocr=None, stop_event=threading.Event())
    return DecisiveMapController(ctx, DecisiveConfig(chapter=6))


def map_pixels() -> np.ndarray:
    pixels = np.zeros((720, 1280, 3), dtype=np.uint8)
    pixels[200:240, 480:520] = (230, 207, 95)
    template = Templates.Decisive.MAP_PAGE
    patch = cv2.resize(template.image, (160, 59))
    pixels[640:699, 1050:1210] = patch
    return pixels


def test_recognize_uses_given_frame_without_sleep_or_recapture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = make_controller()
    pixels = map_pixels()
    frame = CapturedFrame(pixels, 42, 12.0)
    dll = MagicMock()
    dll.recognize_map.return_value = 'J-extra'
    monkeypatch.setattr(module, 'get_api_dll', lambda: dll)
    monkeypatch.setattr(module.time, 'sleep', MagicMock(side_effect=AssertionError))
    assert controller.recognize_node(frame) == 'J'
    dll.recognize_map.assert_called_once()
    np.testing.assert_array_equal(dll.recognize_map.call_args.args[0], pixels[:, 461:514])
    controller._ctrl.screenshot.assert_not_called()
    controller._ctrl.capture_frame.assert_not_called()


def test_observation_preserves_frame_crop_raw_result_and_timings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = make_controller()
    frame = CapturedFrame(map_pixels(), 42, 12.0)
    dll = MagicMock()
    dll.recognize_map.return_value = 'J-extra'
    monkeypatch.setattr(module, 'get_api_dll', lambda: dll)
    observation = controller.observe_node(frame)
    assert observation.frame is frame
    assert observation.icon_x == 499.5 / 1280
    assert observation.crop_bounds == (461, 0, 514, 720)
    assert observation.raw_node == 'J-extra'
    assert observation.node_label == 'J'
    assert observation.failure is None
    assert observation.locate_seconds >= 0
    assert observation.native_seconds >= 0
    dll.recognize_map.assert_called_once()
    np.testing.assert_array_equal(observation.crop, dll.recognize_map.call_args.args[0])
    assert np.shares_memory(observation.crop, frame.image)
    with pytest.raises(FrozenInstanceError):
        observation.node_label = 'A'
    controller._ctrl.capture_frame.assert_not_called()


@pytest.mark.parametrize(
    ('raw', 'node'), [('', None), (' J', None), ('j', None), ('?', None), ('Zx', 'Z')]
)
def test_observation_keeps_raw_native_text_and_parses_only_initial_capital(
    monkeypatch: pytest.MonkeyPatch, raw: str, node: str | None
) -> None:
    dll = MagicMock()
    dll.recognize_map.return_value = raw
    monkeypatch.setattr(module, 'get_api_dll', lambda: dll)
    observation = make_controller().observe_node(CapturedFrame(map_pixels(), 1, 1.0))
    assert observation.raw_node == raw
    assert observation.node_label == node
    assert observation.failure == ('invalid_label' if node is None else None)
    dll.recognize_map.assert_called_once()


@pytest.mark.parametrize(('start', 'bounds'), [(0, (0, 0, 24, 720)), (1260, (1231, 0, 1280, 720))])
def test_observation_clamps_crop_to_real_frame_edges(
    monkeypatch: pytest.MonkeyPatch, start: int, bounds: tuple[int, int, int, int]
) -> None:
    pixels = np.zeros((720, 1280, 3), dtype=np.uint8)
    pixels[200:240, start : start + 20] = (230, 207, 95)
    dll = MagicMock()
    dll.recognize_map.return_value = 'A'
    monkeypatch.setattr(module, 'get_api_dll', lambda: dll)
    observation = make_controller().observe_node(CapturedFrame(pixels, 1, 1.0))
    assert observation.crop_bounds == bounds
    assert observation.crop.shape == (720, bounds[2] - bounds[0], 3)


def test_missing_icon_skips_native_and_reports_missing_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dll = MagicMock()
    monkeypatch.setattr(module, 'get_api_dll', lambda: dll)
    frame = CapturedFrame(np.zeros((720, 1280, 3), dtype=np.uint8), 1, 1.0)
    observation = make_controller().observe_node(frame)
    assert observation.failure == 'missing_icon'
    assert observation.crop is None
    assert observation.raw_node is None
    assert observation.node_label is None
    assert observation.native_seconds is None
    dll.recognize_map.assert_not_called()


def test_native_error_is_observable_and_public_wrapper_still_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dll = MagicMock()
    dll.recognize_map.side_effect = RuntimeError('native unavailable')
    monkeypatch.setattr(module, 'get_api_dll', lambda: dll)
    controller = make_controller()
    frame = CapturedFrame(map_pixels(), 1, 1.0)
    observation = controller.observe_node(frame)
    assert observation.failure == 'native_error'
    assert 'native unavailable' in observation.error
    assert observation.node_label is None
    assert observation.raw_node is None
    assert observation.native_seconds >= 0
    assert controller.recognize_node(frame) is None
    assert dll.recognize_map.call_count == 2


def test_public_wrapper_captures_once_when_frame_is_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dll = MagicMock()
    dll.recognize_map.return_value = 'J'
    monkeypatch.setattr(module, 'get_api_dll', lambda: dll)
    controller = make_controller()
    controller._ctrl.capture_frame.return_value = CapturedFrame(map_pixels(), 1, 1.0)
    assert controller.recognize_node() == 'J'
    controller._ctrl.capture_frame.assert_called_once()
    controller._ctrl.screenshot.assert_not_called()
    dll.recognize_map.assert_called_once()


def test_public_raw_recognizer_preserves_unparsed_result_and_crop() -> None:
    dll = MagicMock()
    dll.recognize_map.return_value = 'J-extra'
    pixels = map_pixels()
    assert make_controller().dll_recognize_map(dll, pixels, 499.5 / 1280) == 'J-extra'
    np.testing.assert_array_equal(dll.recognize_map.call_args.args[0], pixels[:, 461:514])


def test_public_wrapper_keeps_fleet_overlay_sentinel(monkeypatch: pytest.MonkeyPatch) -> None:
    pixels = map_pixels()
    patch = Templates.Decisive.FLEET_ACQUISITION.image
    height, width = patch.shape[:2]
    pixels[50 : 50 + height, 700 : 700 + width] = patch
    dll = MagicMock()
    monkeypatch.setattr(module, 'get_api_dll', lambda: dll)
    assert make_controller().recognize_node(CapturedFrame(pixels, 1, 1.0)) == 'CHOOSE_FLEET'
    dll.recognize_map.assert_not_called()


def test_stability_does_not_count_cached_frame_twice(monkeypatch: pytest.MonkeyPatch) -> None:
    controller = make_controller()
    pixels = map_pixels()
    first = CapturedFrame(pixels, 42, 12.0)
    second = CapturedFrame(pixels, 43, 12.1)
    controller._ctrl.capture_frame.side_effect = [first, first, second]
    monkeypatch.setattr(module.time, 'sleep', lambda _: None)
    assert controller.wait_for_stable_map_frame() is second
    assert controller._ctrl.capture_frame.call_count == 3


def test_stable_frame_wait_respects_stop() -> None:
    controller = make_controller()
    controller._ctx.stop_event.set()
    with pytest.raises(InterruptedError):
        controller.wait_for_stable_map_frame()
    controller._ctrl.capture_frame.assert_not_called()


def test_stable_map_accepts_missing_icon_as_missing_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = make_controller()
    pixels = map_pixels()
    pixels[200:240, 480:520] = 0
    first = CapturedFrame(pixels, 42, 12.0)
    second = CapturedFrame(pixels, 43, 12.1)
    controller._ctrl.capture_frame.side_effect = [first, first, second]
    monkeypatch.setattr(module.time, 'sleep', lambda _: None)
    assert controller.wait_for_stable_map_frame() is second
    assert controller._ctrl.capture_frame.call_count == 3
