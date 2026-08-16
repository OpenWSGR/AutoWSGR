"""Tests for autowsgr.ui.bath_page.signatures."""

from __future__ import annotations

import pytest

from autowsgr.ui.bath_page.signatures import (
    BATH_FULL_TIMEOUT,
    CHOOSE_REPAIR_OVERLAY_SIGNATURE,
    CLICK_BACK,
    CLICK_CHOOSE_REPAIR,
    CLICK_CLOSE_OVERLAY,
    CLICK_FIRST_REPAIR_SHIP,
    CLICK_REPAIR_ALL,
    CLOSE_OVERLAY_BUTTON_COLOR,
    PAGE_SIGNATURE,
    REPAIR_ALL_BUTTON_COLOR,
    SWIPE_DELAY,
    SWIPE_DURATION,
    SWIPE_END,
    SWIPE_START,
)
from autowsgr.vision import MatchStrategy, PixelSignature


CLICK_COORDS: list[tuple[float, float]] = [
    CLICK_REPAIR_ALL,
    CLICK_BACK,
    CLICK_CHOOSE_REPAIR,
    CLICK_CLOSE_OVERLAY,
    CLICK_FIRST_REPAIR_SHIP,
]

COLOR_SPECS: list[tuple[tuple[int, int, int], float]] = [
    REPAIR_ALL_BUTTON_COLOR,
    CLOSE_OVERLAY_BUTTON_COLOR,
]

SWIPE_COORDS: list[tuple[float, float]] = [SWIPE_START, SWIPE_END]

POSITIVE_FLOATS: list[float] = [SWIPE_DURATION, SWIPE_DELAY, BATH_FULL_TIMEOUT]


class TestSignatures:
    """Tests for page signatures."""

    def test_page_signature_type_and_strategy(self) -> None:
        """PAGE_SIGNATURE must be a PixelSignature using MatchStrategy.ALL."""
        assert isinstance(PAGE_SIGNATURE, PixelSignature)
        assert PAGE_SIGNATURE.strategy is MatchStrategy.ALL

    def test_choose_repair_overlay_signature_type(self) -> None:
        """CHOOSE_REPAIR_OVERLAY_SIGNATURE must be a PixelSignature."""
        assert isinstance(CHOOSE_REPAIR_OVERLAY_SIGNATURE, PixelSignature)


class TestClickCoordinates:
    """Tests for click coordinate constants."""

    @pytest.mark.parametrize('coord', CLICK_COORDS)
    def test_click_coords_are_valid(self, coord: tuple[float, float]) -> None:
        """Each CLICK_* must be a 2-float tuple with values in [0, 1]."""
        assert len(coord) == 2
        x, y = coord
        assert isinstance(x, float)
        assert isinstance(y, float)
        assert 0.0 <= x <= 1.0
        assert 0.0 <= y <= 1.0


class TestColorSpecs:
    """Tests for colour constants."""

    @pytest.mark.parametrize('color_spec', COLOR_SPECS)
    def test_color_specs_are_valid(self, color_spec: tuple[tuple[int, int, int], float]) -> None:
        """Each colour constant must be ((R, G, B), tolerance)."""
        color, tolerance = color_spec
        assert len(color) == 3
        r, g, b = color
        assert isinstance(r, int)
        assert isinstance(g, int)
        assert isinstance(b, int)
        assert isinstance(tolerance, float)


class TestSwipeConstants:
    """Tests for swipe-related constants."""

    @pytest.mark.parametrize('coord', SWIPE_COORDS)
    def test_swipe_coords_are_valid(self, coord: tuple[float, float]) -> None:
        """SWIPE_START and SWIPE_END must be 2-float tuples."""
        assert len(coord) == 2
        x, y = coord
        assert isinstance(x, float)
        assert isinstance(y, float)

    @pytest.mark.parametrize('value', POSITIVE_FLOATS)
    def test_positive_float_constants(self, value: float) -> None:
        """SWIPE_DURATION, SWIPE_DELAY, and BATH_FULL_TIMEOUT must be > 0."""
        assert value > 0.0
