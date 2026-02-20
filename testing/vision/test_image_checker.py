"""Tests for ImageChecker engine — find/match/identify/crop operations."""
from __future__ import annotations

import pytest

from autowsgr.vision.image_matcher import (
    ROI,
    ImageChecker,
    ImageRule,
    ImageSignature,
)
from autowsgr.vision.matcher import MatchStrategy

from ._helpers import embed_template_in_screen, make_template, solid_screen


# ─────────────────────────────────────────────
# ImageChecker — find_template (单模板匹配)
# ─────────────────────────────────────────────


class TestFindTemplate:
    def test_exact_match(self):
        """模板完全嵌入截图中，应能精确匹配。"""
        screen = solid_screen(200, 200, 200)
        tmpl = make_template(seed=1, h=30, w=40)
        screen = embed_template_in_screen(screen, tmpl, x=100, y=200)

        detail = ImageChecker.find_template(screen, tmpl, confidence=0.9)
        assert detail is not None
        assert detail.confidence > 0.9
        # 中心应大致在 (100+20)/960, (200+15)/540
        cx, cy = detail.center
        assert cx == pytest.approx(120 / 960, abs=0.02)
        assert cy == pytest.approx(215 / 540, abs=0.02)

    def test_no_match_when_absent(self):
        """模板未嵌入截图，不应匹配。"""
        screen = solid_screen(200, 200, 200)
        tmpl = make_template(seed=2, name="absent")
        detail = ImageChecker.find_template(screen, tmpl, confidence=0.9)
        assert detail is None

    def test_match_with_roi(self):
        """仅在 ROI 内搜索。"""
        screen = solid_screen(200, 200, 200)
        tmpl = make_template(seed=3, h=20, w=30)
        # 模板放在左上角
        screen = embed_template_in_screen(screen, tmpl, x=10, y=10)

        # ROI 在右半边 → 不应匹配
        detail = ImageChecker.find_template(
            screen, tmpl, roi=ROI(0.5, 0.0, 1.0, 1.0), confidence=0.9,
        )
        assert detail is None

        # ROI 包含左上角 → 应匹配
        detail = ImageChecker.find_template(
            screen, tmpl, roi=ROI(0.0, 0.0, 0.5, 0.5), confidence=0.9,
        )
        assert detail is not None

    def test_template_larger_than_roi(self):
        """模板大于搜索区域时应返回 None。"""
        screen = solid_screen(200, 200, 200)
        tmpl = make_template(seed=4, h=300, w=500)
        detail = ImageChecker.find_template(
            screen, tmpl, roi=ROI(0.0, 0.0, 0.1, 0.1), confidence=0.5,
        )
        assert detail is None


# ─────────────────────────────────────────────
# ImageChecker — find_any / find_best / find_all
# ─────────────────────────────────────────────


class TestFindMultiple:
    def test_find_any_returns_first_match(self):
        screen = solid_screen(200, 200, 200)
        t1 = make_template(seed=10, name="t1")
        t2 = make_template(seed=20, name="t2")
        screen = embed_template_in_screen(screen, t1, x=100, y=100)
        screen = embed_template_in_screen(screen, t2, x=500, y=300)

        detail = ImageChecker.find_any(screen, [t1, t2], confidence=0.9)
        assert detail is not None
        assert detail.template_name == "t1"

    def test_find_any_none_when_no_match(self):
        screen = solid_screen(200, 200, 200)
        t1 = make_template(seed=30, name="absent")
        detail = ImageChecker.find_any(screen, [t1], confidence=0.9)
        assert detail is None

    def test_find_all(self):
        screen = solid_screen(200, 200, 200)
        t1 = make_template(seed=10, name="t1")
        t2 = make_template(seed=20, name="t2")
        screen = embed_template_in_screen(screen, t1, x=100, y=100)
        screen = embed_template_in_screen(screen, t2, x=500, y=300)

        results = ImageChecker.find_all(screen, [t1, t2], confidence=0.9)
        assert len(results) == 2


# ─────────────────────────────────────────────
# ImageChecker — template_exists
# ─────────────────────────────────────────────


class TestTemplateExists:
    def test_exists_single(self):
        screen = solid_screen(200, 200, 200)
        tmpl = make_template(seed=40)
        screen = embed_template_in_screen(screen, tmpl, x=100, y=100)
        assert ImageChecker.template_exists(screen, tmpl, confidence=0.9)

    def test_exists_list(self):
        screen = solid_screen(200, 200, 200)
        t1 = make_template(seed=41, name="t1")
        screen = embed_template_in_screen(screen, t1, x=100, y=100)
        assert ImageChecker.template_exists(screen, [t1], confidence=0.9)

    def test_not_exists_with_roi(self):
        screen = solid_screen(200, 200, 200)
        tmpl = make_template(seed=42)
        screen = embed_template_in_screen(screen, tmpl, x=10, y=10)
        # ROI 在右半边
        assert not ImageChecker.template_exists(
            screen, tmpl, roi=ROI(0.5, 0.0, 1.0, 1.0), confidence=0.9,
        )


# ─────────────────────────────────────────────
# ImageRule + ImageSignature
# ─────────────────────────────────────────────


class TestImageRuleAndSignature:
    def test_match_rule(self):
        screen = solid_screen(200, 200, 200)
        tmpl = make_template(seed=50, name="btn")
        screen = embed_template_in_screen(screen, tmpl, x=100, y=100)

        rule = ImageRule(name="test_rule", templates=[tmpl], confidence=0.85)
        result = ImageChecker.match_rule(screen, rule)
        assert result.matched
        assert result.best is not None
        assert result.best.template_name == "btn"

    def test_match_rule_with_roi(self):
        screen = solid_screen(200, 200, 200)
        tmpl = make_template(seed=51, name="btn")
        screen = embed_template_in_screen(screen, tmpl, x=100, y=100)

        # ROI 排除模板位置
        rule = ImageRule(
            name="test_rule",
            templates=[tmpl],
            roi=ROI(0.5, 0.5, 1.0, 1.0),
            confidence=0.85,
        )
        result = ImageChecker.match_rule(screen, rule)
        assert not result.matched

    def test_match_rule_multiple_templates(self):
        """多模板规则：任一匹配即可。"""
        screen = solid_screen(200, 200, 200)
        t1 = make_template(seed=52, name="v1")  # 不嵌入 → 不匹配
        t2 = make_template(seed=53, name="v2")
        screen = embed_template_in_screen(screen, t2, x=300, y=200)

        rule = ImageRule(name="confirm", templates=[t1, t2], confidence=0.85)
        result = ImageChecker.match_rule(screen, rule)
        assert result.matched
        assert result.best is not None
        assert result.best.template_name == "v2"

    def test_image_signature_all(self):
        screen = solid_screen(200, 200, 200)
        t1 = make_template(seed=54, name="a")
        t2 = make_template(seed=55, name="b")
        screen = embed_template_in_screen(screen, t1, x=100, y=100)
        screen = embed_template_in_screen(screen, t2, x=500, y=300)

        sig = ImageSignature(
            name="test_page",
            rules=[
                ImageRule(name="r1", templates=[t1], confidence=0.85),
                ImageRule(name="r2", templates=[t2], confidence=0.85),
            ],
            strategy=MatchStrategy.ALL,
        )
        result = ImageChecker.check_signature(screen, sig)
        assert result.matched

    def test_image_signature_any(self):
        screen = solid_screen(200, 200, 200)
        t1 = make_template(seed=56, name="a")
        screen = embed_template_in_screen(screen, t1, x=100, y=100)
        t_miss = make_template(seed=57, name="miss")  # 不嵌入

        sig = ImageSignature(
            name="test_page",
            rules=[
                ImageRule(name="r1", templates=[t1], confidence=0.85),
                ImageRule(name="r2", templates=[t_miss], confidence=0.99),
            ],
            strategy=MatchStrategy.ANY,
        )
        result = ImageChecker.check_signature(screen, sig)
        assert result.matched

    def test_image_signature_all_fails_on_missing(self):
        screen = solid_screen(200, 200, 200)
        t1 = make_template(seed=58, name="a")
        screen = embed_template_in_screen(screen, t1, x=100, y=100)
        t_miss = make_template(seed=59, name="miss")  # 不嵌入

        sig = ImageSignature(
            name="test_page",
            rules=[
                ImageRule(name="r1", templates=[t1], confidence=0.85),
                ImageRule(name="r2", templates=[t_miss], confidence=0.99),
            ],
            strategy=MatchStrategy.ALL,
        )
        result = ImageChecker.check_signature(screen, sig)
        assert not result.matched


# ─────────────────────────────────────────────
# ImageChecker — find_all_occurrences
# ─────────────────────────────────────────────


class TestFindAllOccurrences:
    def test_multiple_occurrences(self):
        """在截图中放置同一模板的多个副本。"""
        screen = solid_screen(200, 200, 200)
        tmpl = make_template(seed=60, h=20, w=30, name="icon")
        # 放两个足够远的副本
        screen = embed_template_in_screen(screen, tmpl, x=100, y=100)
        screen = embed_template_in_screen(screen, tmpl, x=500, y=400)

        results = ImageChecker.find_all_occurrences(
            screen, tmpl, confidence=0.9, min_distance=20,
        )
        assert len(results) >= 2

    def test_with_roi_restriction(self):
        """ROI 限制应排除区域外的副本。"""
        screen = solid_screen(200, 200, 200)
        tmpl = make_template(seed=61, h=20, w=30, name="icon")
        screen = embed_template_in_screen(screen, tmpl, x=100, y=100)
        screen = embed_template_in_screen(screen, tmpl, x=500, y=400)

        # ROI 仅包含左半边
        results = ImageChecker.find_all_occurrences(
            screen, tmpl, roi=ROI(0.0, 0.0, 0.4, 0.5), confidence=0.9,
        )
        assert len(results) == 1


# ─────────────────────────────────────────────
# ImageChecker — identify
# ─────────────────────────────────────────────


class TestIdentify:
    def test_identify_first_match(self):
        screen = solid_screen(200, 200, 200)
        t1 = make_template(seed=70, name="a")
        screen = embed_template_in_screen(screen, t1, x=100, y=100)
        t_miss = make_template(seed=71, name="miss")

        sig1 = ImageSignature(
            name="page_a",
            rules=[ImageRule(name="r1", templates=[t1], confidence=0.85)],
        )
        sig2 = ImageSignature(
            name="page_b",
            rules=[ImageRule(name="r2", templates=[t_miss], confidence=0.99)],
        )
        result = ImageChecker.identify(screen, [sig1, sig2])
        assert result is not None
        assert result.rule_name == "page_a"

    def test_identify_none_when_no_match(self):
        screen = solid_screen(200, 200, 200)
        t_miss = make_template(seed=72, name="miss")
        sig = ImageSignature(
            name="page_x",
            rules=[ImageRule(name="r", templates=[t_miss], confidence=0.99)],
        )
        result = ImageChecker.identify(screen, [sig])
        assert result is None


# ─────────────────────────────────────────────
# ImageChecker.crop
# ─────────────────────────────────────────────


class TestCrop:
    def test_crop_returns_copy(self):
        screen = solid_screen(100, 100, 100)
        roi = ROI(0.0, 0.0, 0.5, 0.5)
        cropped = ImageChecker.crop(screen, roi)
        assert cropped.shape[1] == 480
        assert cropped.shape[0] == 270
        # 修改裁切结果不影响原图
        cropped[0, 0] = [255, 0, 0]
        assert screen[0, 0, 0] == 100
