"""Tests for autowsgr.vision.api_dll."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from autowsgr.vision.api_dll import ApiDll, get_api_dll


if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture(autouse=True)
def mock_native() -> Generator[MagicMock, None, None]:
    """Patch recognition functions bound in api_dll and clear the singleton cache."""
    get_api_dll.cache_clear()
    with (
        patch('autowsgr.vision.api_dll.locate', new_callable=MagicMock) as m_locate,
        patch('autowsgr.vision.api_dll.recognize_map', new_callable=MagicMock) as m_map,
        patch('autowsgr.vision.api_dll.recognize_enemy', new_callable=MagicMock) as m_enemy,
    ):
        mock = MagicMock()
        mock.locate = m_locate
        mock.recognize_map = m_map
        mock.recognize_enemy = m_enemy
        yield mock


@pytest.fixture
def mock_cv2_resize() -> Generator[MagicMock, None, None]:
    """Patch cv2.resize inside api_dll."""
    with patch('autowsgr.vision.api_dll.cv2.resize') as m:
        yield m


def test_get_api_dll_singleton() -> None:
    """Two calls to get_api_dll return the same object."""
    api1 = get_api_dll()
    api2 = get_api_dll()
    assert api1 is api2


def test_api_dll_instantiation() -> None:
    """ApiDll can be instantiated without crashing."""
    dll = ApiDll()
    assert isinstance(dll, ApiDll)


def test_recognize_map_tall_image(
    mock_native: MagicMock,
    mock_cv2_resize: MagicMock,
) -> None:
    """recognize_map resizes tall images before delegating."""
    image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    resized = np.zeros((720, 1280, 3), dtype=np.uint8)
    mock_cv2_resize.return_value = resized
    mock_native.recognize_map.return_value = 'map_result'

    dll = ApiDll()
    result = dll.recognize_map(image)

    mock_cv2_resize.assert_called_once()
    call_args = mock_cv2_resize.call_args
    assert call_args.args[0] is image
    assert call_args.args[1] == (1280, 720)
    assert call_args.kwargs['interpolation'] == cv2.INTER_AREA
    mock_native.recognize_map.assert_called_once()
    map_call = mock_native.recognize_map.call_args
    assert map_call.args[0].dtype == np.uint8
    assert map_call.args[0].shape == resized.shape
    assert result == 'map_result'


def test_recognize_map_short_image(
    mock_native: MagicMock,
    mock_cv2_resize: MagicMock,
) -> None:
    """recognize_map does not resize short images."""
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    mock_native.recognize_map.return_value = 'map_result'

    dll = ApiDll()
    result = dll.recognize_map(image)

    mock_cv2_resize.assert_not_called()
    mock_native.recognize_map.assert_called_once()
    map_call = mock_native.recognize_map.call_args
    assert map_call.args[0].dtype == np.uint8
    assert map_call.args[0].shape == image.shape
    assert result == 'map_result'


def test_locate_delegates(mock_native: MagicMock) -> None:
    """locate delegates to autowsgr_native.recognition.locate."""
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    mock_native.locate.return_value = [(1.0, 2.0)]

    dll = ApiDll()
    result = dll.locate(image)

    mock_native.locate.assert_called_once_with(image)
    assert result == [(1.0, 2.0)]


def test_recognize_enemy_delegates(mock_native: MagicMock) -> None:
    """recognize_enemy delegates to autowsgr_native.recognition.recognize_enemy."""
    images = [np.zeros((100, 100, 3), dtype=np.uint8)]
    mock_native.recognize_enemy.return_value = 'enemy_name'

    dll = ApiDll()
    result = dll.recognize_enemy(images)

    mock_native.recognize_enemy.assert_called_once_with(images)
    assert result == 'enemy_name'
