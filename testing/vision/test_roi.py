"""Tests for autowsgr.vision.roi — ROI class."""
from __future__ import annotations

import pytest

from autowsgr.vision.image_matcher import ROI

from ._helpers import solid_screen


class TestROI:
    def test_full_roi(self):
        roi = ROI.full()
        assert roi.x1 == 0.0 and roi.y1 == 0.0
        assert roi.x2 == 1.0 and roi.y2 == 1.0

    def test_from_tuple(self):
        roi = ROI.from_tuple((0.1, 0.2, 0.5, 0.6))
        assert roi.x1 == 0.1 and roi.y1 == 0.2
        assert roi.x2 == 0.5 and roi.y2 == 0.6

    def test_from_dict(self):
        roi = ROI.from_dict({"x1": 0.1, "y1": 0.2, "x2": 0.5, "y2": 0.6})
        assert roi.x1 == 0.1

    def test_from_dict_shorthand(self):
        roi = ROI.from_dict({"roi": [0.1, 0.2, 0.5, 0.6]})
        assert roi.x1 == 0.1 and roi.y2 == 0.6

    def test_to_dict(self):
        roi = ROI(0.1, 0.2, 0.5, 0.6)
        d = roi.to_dict()
        assert d == {"x1": 0.1, "y1": 0.2, "x2": 0.5, "y2": 0.6}

    def test_to_tuple(self):
        roi = ROI(0.1, 0.2, 0.5, 0.6)
        assert roi.to_tuple() == (0.1, 0.2, 0.5, 0.6)

    def test_to_absolute(self):
        roi = ROI(0.0, 0.0, 0.5, 0.5)
        px1, py1, px2, py2 = roi.to_absolute(960, 540)
        assert (px1, py1) == (0, 0)
        assert (px2, py2) == (480, 270)

    def test_crop(self):
        screen = solid_screen(100, 100, 100)
        roi = ROI(0.0, 0.0, 0.5, 0.5)
        cropped = roi.crop(screen)
        assert cropped.shape[1] == 480
        assert cropped.shape[0] == 270

    def test_properties(self):
        roi = ROI(0.1, 0.2, 0.5, 0.8)
        assert roi.width == pytest.approx(0.4)
        assert roi.height == pytest.approx(0.6)
        cx, cy = roi.center
        assert cx == pytest.approx(0.3)
        assert cy == pytest.approx(0.5)

    def test_contains(self):
        roi = ROI(0.1, 0.2, 0.5, 0.6)
        assert roi.contains(0.3, 0.4)
        assert not roi.contains(0.0, 0.0)
        assert not roi.contains(0.6, 0.5)

    def test_invalid_x_raises(self):
        with pytest.raises(ValueError, match="x 坐标无效"):
            ROI(0.5, 0.0, 0.3, 1.0)

    def test_invalid_y_raises(self):
        with pytest.raises(ValueError, match="y 坐标无效"):
            ROI(0.0, 0.6, 0.5, 0.3)

    def test_equal_x_raises(self):
        with pytest.raises(ValueError):
            ROI(0.5, 0.0, 0.5, 1.0)
