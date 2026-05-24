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
    """Patch autowsgr_native in api_dll and clear the singleton cache."""
    get_api_dll.cache_clear()
    with patch('autowsgr.vision.api_dll.autowsgr_native', new_callable=MagicMock) as m:
        yield m


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

    mock_cv2_resize.assert_called_once_with(
        image,
        (1280, 720),
        interpolation=cv2.INTER_AREA,
    )
    mock_native.recognize_map.assert_called_once_with(resized)
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
    mock_native.recognize_map.assert_called_once_with(image)
    assert result == 'map_result'


def test_locate_delegates(mock_native: MagicMock) -> None:
    """locate delegates to autowsgr_native.locate."""
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    mock_native.locate.return_value = [(1.0, 2.0)]

    dll = ApiDll()
    result = dll.locate(image)

    mock_native.locate.assert_called_once_with(image)
    assert result == [(1.0, 2.0)]


def test_recognize_enemy_delegates(mock_native: MagicMock) -> None:
    """recognize_enemy delegates to autowsgr_native.recognize_enemy."""
    images = [np.zeros((100, 100, 3), dtype=np.uint8)]
    mock_native.recognize_enemy.return_value = 'enemy_name'

    dll = ApiDll()
    result = dll.recognize_enemy(images)

    mock_native.recognize_enemy.assert_called_once_with(images)
    assert result == 'enemy_name'
