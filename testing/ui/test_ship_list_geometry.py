"""Shared list geometry is proven from pixels independently of ship-name OCR."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from autowsgr.ui.utils.ship_list_geometry import (
    ShipListGeometryError,
    ShipListGeometryReader,
    ShipListScrollbar,
)


def _screen(row_columns: tuple[int, ...]) -> np.ndarray:
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    for (top, bottom), count in zip(((346, 374), (634, 662)), row_columns, strict=False):
        for left, right in ShipListGeometryReader.column_bounds(1280)[:count]:
            image[top:bottom, left:right] = (18, 98, 162)
            image[bottom - 270 : bottom - 266, left:right] = (0, 170, 235)
    return image


def test_missing_name_bands_are_rejected_by_default() -> None:
    locate = MagicMock(return_value=[])
    reader = ShipListGeometryReader(locate=locate)

    with pytest.raises(ShipListGeometryError, match='未定位到任何舰名蓝条'):
        reader.capture(_screen(()))
    locate.assert_called_once()


def test_explicit_empty_capture_reports_only_zero_geometry_observation() -> None:
    locate = MagicMock(return_value=[])
    reader = ShipListGeometryReader(locate=locate)

    capture = reader.capture(_screen(()), allow_empty=True)

    assert capture.crops == ()
    assert capture.row_lengths == ()
    assert capture.bands == ()
    assert capture.row_columns == ()
    assert capture.screen_height == 720
    assert capture.clipped_bands == ()
    assert not capture.has_leading_partial
    assert not capture.has_trailing_partial
    locate.assert_called_once()


def test_empty_capture_flag_preserves_complete_card_observations() -> None:
    reader = ShipListGeometryReader(locate=lambda _image: [[346, 374]])
    image = _screen((3,))

    capture = reader.capture(image, allow_empty=True)

    assert capture.row_lengths == (3,)
    assert capture.row_columns == ((0, 1, 2),)
    assert len(capture.crops) == 3


def test_empty_capture_flag_does_not_suppress_non_empty_geometry_errors() -> None:
    reader = ShipListGeometryReader(locate=lambda _image: [[346, 374]])

    with pytest.raises(ShipListGeometryError, match='没有固定列卡位证据'):
        reader.capture(_screen(()), allow_empty=True)


@pytest.mark.parametrize('row_columns', [(7, 7), (7, 1), (1,)])
def test_capture_preserves_all_complete_pixel_card_slots(row_columns: tuple[int, ...]) -> None:
    reader = ShipListGeometryReader(
        locate=lambda _image: [[346, 374], [634, 662]][: len(row_columns)]
    )

    capture = reader.capture(_screen(row_columns))

    assert capture.row_lengths == row_columns
    assert capture.row_columns == tuple(tuple(range(count)) for count in row_columns)
    assert len(capture.crops) == sum(row_columns)
    assert capture.screen_height == 720
    assert capture.clipped_bands == ()
    assert not capture.has_trailing_partial
    assert not capture.has_leading_partial
    assert all(crop.shape == (270, 128, 3) for crop in capture.crops)


def test_capture_keeps_evidence_of_filtered_partial_row() -> None:
    image = _screen((1,))
    left, right = ShipListGeometryReader.column_bounds(1280)[0]
    image[100:128, left:right] = (18, 98, 162)
    reader = ShipListGeometryReader(locate=lambda _image: [[100, 128], [346, 374]])

    capture = reader.capture(image)

    assert capture.row_lengths == (1,)
    assert capture.bands == ((346, 374),)
    assert capture.clipped_bands == ((100, 128),)


def test_native_missing_first_row_keeps_independent_leading_card_evidence() -> None:
    reader = ShipListGeometryReader(locate=lambda _image: [[634, 662]])

    capture = reader.capture(_screen((7, 7)))

    assert capture.row_lengths == (7,)
    assert capture.has_leading_partial


def test_capture_rejects_non_contiguous_card_slots() -> None:
    image = _screen((3,))
    left, right = ShipListGeometryReader.column_bounds(1280)[1]
    image[346:374, left:right] = 0
    reader = ShipListGeometryReader(locate=lambda _image: [[346, 374]])

    with pytest.raises(ShipListGeometryError, match='非连续'):
        reader.capture(image)


def test_explicit_leading_control_retains_real_ship_column_numbers() -> None:
    image = _screen((7, 7))
    left, right = ShipListGeometryReader.column_bounds(1280)[0]
    image[346:374, left:right] = 0
    reader = ShipListGeometryReader(locate=lambda _image: [[346, 374], [634, 662]])

    capture = reader.capture(image, leading_control=True)

    assert capture.row_lengths == (6, 7)
    assert capture.row_columns == (tuple(range(1, 7)), tuple(range(7)))
    assert len(capture.crops) == 13
    with pytest.raises(ShipListGeometryError, match='非连续'):
        reader.capture(image)


def test_leading_control_does_not_allow_another_missing_card() -> None:
    image = _screen((7, 7))
    left, right = ShipListGeometryReader.column_bounds(1280)[2]
    image[346:374, left:right] = 0
    reader = ShipListGeometryReader(locate=lambda _image: [[346, 374], [634, 662]])

    with pytest.raises(ShipListGeometryError, match='非连续'):
        reader.capture(image, leading_control=True)


def test_clipped_trailing_card_is_not_hidden_by_a_thin_native_band() -> None:
    image = _screen((1,))
    left, right = ShipListGeometryReader.column_bounds(1280)[0]
    image[428:432, left:right] = (0, 170, 235)
    image[673:674, left:right] = (18, 98, 162)
    reader = ShipListGeometryReader(locate=lambda _image: [[346, 374], [673, 674]])

    capture = reader.capture(image)

    assert capture.row_lengths == (1,)
    assert capture.has_trailing_partial


def test_blue_list_background_is_not_a_trailing_card_top() -> None:
    image = _screen((1,))
    image[380:674] = (24, 65, 99)
    reader = ShipListGeometryReader(locate=lambda _image: [[346, 374]])

    assert not reader.capture(image).has_trailing_partial


@pytest.mark.parametrize(
    ('bounds', 'at_top', 'at_bottom'),
    [((90, 540), True, False), ((281, 689), False, True), ((90, 689), True, True)],
)
def test_scrollbar_endpoints_follow_pixels_without_assuming_thumb_length(
    bounds: tuple[int, int], at_top: bool, at_bottom: bool
) -> None:
    image = np.full((720, 1280, 3), 70, dtype=np.uint8)
    image[bounds[0] : bounds[1], 1053:1056] = (192, 193, 195)
    scrollbar = ShipListScrollbar(MagicMock())

    assert scrollbar.thumb_bounds(image) == bounds
    assert scrollbar.is_top(image) is at_top
    assert scrollbar.is_bottom(image) is at_bottom


def test_missing_scrollbar_does_not_imply_a_single_page() -> None:
    with pytest.raises(ShipListGeometryError, match='定位不唯一'):
        ShipListScrollbar(MagicMock()).thumb_bounds(np.zeros((720, 1280, 3), dtype=np.uint8))


@pytest.mark.parametrize('resolution', [(1280, 720), (1920, 1080)])
def test_chroma_fringe_does_not_hide_neutral_scrollbar_center(
    resolution: tuple[int, int],
) -> None:
    width, height = resolution
    image = np.full((height, width, 3), 70, dtype=np.uint8)
    x = round(1580 * width / 1920)
    stripe_width = max(2, round(3 * width / 1280))
    top, bottom = round(0.35 * height), round(0.70 * height)
    image[top:bottom, x : x + stripe_width] = (188, 191, 198)
    image[top:bottom, x] = (171, 196, 222)
    image[top:bottom, x + 2] = (183, 186, 193)

    assert ShipListScrollbar(MagicMock()).thumb_bounds(image) == (top, bottom)


@pytest.mark.parametrize(
    'colors',
    [
        ((192, 193, 195), (70, 70, 70), (70, 70, 70)),
        ((175, 178, 183), (220, 223, 225), (70, 70, 70)),
        ((171, 196, 222), (171, 196, 222), (171, 196, 222)),
    ],
)
def test_track_requires_adjacent_bright_similar_low_chroma_columns(colors: tuple) -> None:
    image = np.full((720, 1280, 3), 70, dtype=np.uint8)
    for offset, color in enumerate(colors):
        image[90:540, 1053 + offset] = color

    with pytest.raises(ShipListGeometryError, match='定位不唯一'):
        ShipListScrollbar(MagicMock()).thumb_bounds(image)
