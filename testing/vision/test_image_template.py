"""Tests for ImageTemplate and ImageMatchResult data classes."""
from __future__ import annotations

import numpy as np
import pytest

from autowsgr.vision.image_matcher import (
    ImageMatchDetail,
    ImageMatchResult,
    ImageTemplate,
)

from ._helpers import make_template


# ─────────────────────────────────────────────
# ImageTemplate
# ─────────────────────────────────────────────


class TestImageTemplate:
    def test_from_ndarray(self):
        img = np.zeros((50, 80, 3), dtype=np.uint8)
        tmpl = ImageTemplate.from_ndarray(img, name="test")
        assert tmpl.name == "test"
        assert tmpl.height == 50
        assert tmpl.width == 80
        assert tmpl.shape == (50, 80)
        assert tmpl.source == "ndarray"

    def test_from_ndarray_bgr(self):
        """BGR 输入应自动转换为 RGB。"""
        bgr = np.zeros((10, 10, 3), dtype=np.uint8)
        bgr[:, :] = [255, 0, 0]  # BGR: blue
        tmpl = ImageTemplate.from_ndarray(bgr, name="blue", is_bgr=True)
        # 转换后 RGB 应为 (0, 0, 255)
        assert tmpl.image[0, 0, 0] == 0
        assert tmpl.image[0, 0, 2] == 255

    def test_from_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            ImageTemplate.from_file("/nonexistent/path.png")

    def test_repr(self):
        tmpl = make_template(seed=100, name="btn")
        r = repr(tmpl)
        assert "btn" in r
        assert "80x50" in r


# ─────────────────────────────────────────────
# ImageMatchResult 布尔行为
# ─────────────────────────────────────────────


class TestImageMatchResult:
    def test_bool_true(self):
        r = ImageMatchResult(matched=True, rule_name="test")
        assert r
        assert bool(r) is True

    def test_bool_false(self):
        r = ImageMatchResult(matched=False, rule_name="test")
        assert not r

    def test_center_when_matched(self):
        detail = ImageMatchDetail(
            template_name="t", confidence=0.95,
            center=(0.5, 0.5), top_left=(0.4, 0.4), bottom_right=(0.6, 0.6),
        )
        r = ImageMatchResult(matched=True, rule_name="test", best=detail)
        assert r.center == (0.5, 0.5)
        assert r.confidence == 0.95

    def test_center_when_not_matched(self):
        r = ImageMatchResult(matched=False, rule_name="test")
        assert r.center is None
        assert r.confidence == 0.0
