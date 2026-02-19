"""Tests for autowsgr.vision.matcher — pixel-based detection engine."""
from __future__ import annotations

import math

import numpy as np
import pytest

from autowsgr.vision.matcher import (
    Color,
    MatchStrategy,
    PixelChecker,
    PixelDetail,
    PixelMatchResult,
    PixelRule,
    PixelSignature,
)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────


def solid_screen(b: int, g: int, r: int, h: int = 540, w: int = 960) -> np.ndarray:
    """创建纯色截图 (H×W×3, BGR uint8)。"""
    screen = np.zeros((h, w, 3), dtype=np.uint8)
    screen[:, :] = [b, g, r]
    return screen


def patch_screen(screen: np.ndarray, patches: dict[tuple[int, int], tuple[int, int, int]]) -> np.ndarray:
    """在截图指定坐标写入颜色 {(x,y): (b,g,r)}。"""
    s = screen.copy()
    for (x, y), bgr in patches.items():
        s[y, x] = bgr
    return s


# ─────────────────────────────────────────────
# Color
# ─────────────────────────────────────────────


class TestColor:
    def test_of_creates_bgr_color(self):
        c = Color.of(10, 20, 30)
        assert c.b == 10 and c.g == 20 and c.r == 30

    def test_from_rgb_swaps_channels(self):
        c = Color.from_rgb(r=10, g=20, b=30)
        assert c.r == 10 and c.g == 20 and c.b == 30

    def test_from_bgr_tuple(self):
        c = Color.from_bgr_tuple((1, 2, 3))
        assert c == Color(b=1, g=2, r=3)

    def test_from_rgb_tuple(self):
        c = Color.from_rgb_tuple((10, 20, 30))
        assert c.r == 10 and c.g == 20 and c.b == 30

    def test_distance_same_color_is_zero(self):
        c = Color.of(100, 100, 100)
        assert c.distance(c) == pytest.approx(0.0)

    def test_distance_known_value(self):
        a = Color.of(0, 0, 0)
        b = Color.of(3, 4, 0)
        assert a.distance(b) == pytest.approx(5.0)

    def test_near_within_tolerance(self):
        a = Color.of(100, 150, 200)
        b = Color.of(105, 145, 192)
        dist = a.distance(b)
        assert a.near(b, tolerance=dist + 1)
        assert not a.near(b, tolerance=dist - 1)

    def test_near_default_tolerance_30(self):
        a = Color.of(100, 100, 100)
        b = Color.of(120, 110, 95)
        assert a.near(b)  # distance ≈ 22.9 < 30

    def test_as_bgr_tuple(self):
        c = Color.of(5, 10, 15)
        assert c.as_bgr_tuple() == (5, 10, 15)

    def test_as_rgb_tuple(self):
        c = Color.of(5, 10, 15)
        assert c.as_rgb_tuple() == (15, 10, 5)

    def test_repr(self):
        c = Color(b=1, g=2, r=3)
        assert "Color" in repr(c)

    def test_immutable(self):
        c = Color.of(10, 20, 30)
        with pytest.raises((AttributeError, TypeError)):
            c.b = 99  # type: ignore[misc]


# ─────────────────────────────────────────────
# PixelRule
# ─────────────────────────────────────────────


class TestPixelRule:
    def test_basic_construction(self):
        r = PixelRule(x=70, y=485, color=Color.of(201, 129, 54))
        assert r.x == 70 and r.y == 485

    def test_of_convenience(self):
        r = PixelRule.of(10, 20, (50, 60, 70))
        assert r.color == Color(b=50, g=60, r=70)
        assert r.tolerance == 30.0

    def test_of_custom_tolerance(self):
        r = PixelRule.of(0, 0, (0, 0, 0), tolerance=15.0)
        assert r.tolerance == 15.0

    def test_from_dict_list_color(self):
        d = {"x": 10, "y": 20, "color": [50, 60, 70]}
        r = PixelRule.from_dict(d)
        assert r.x == 10 and r.color.b == 50

    def test_from_dict_with_tolerance(self):
        d = {"x": 5, "y": 5, "color": [10, 20, 30], "tolerance": 40.0}
        r = PixelRule.from_dict(d)
        assert r.tolerance == 40.0

    def test_from_dict_dict_color(self):
        d = {"x": 0, "y": 0, "color": {"b": 1, "g": 2, "r": 3}}
        r = PixelRule.from_dict(d)
        assert r.color == Color(b=1, g=2, r=3)

    def test_from_dict_invalid_color_raises(self):
        with pytest.raises(ValueError):
            PixelRule.from_dict({"x": 0, "y": 0, "color": "bad"})

    def test_to_dict_round_trip(self):
        original = PixelRule.of(0.50, 0.85, (201, 129, 54), tolerance=25.0)
        d = original.to_dict()
        restored = PixelRule.from_dict(d)
        assert original == restored

    def test_immutable(self):
        r = PixelRule.of(0.0, 0.0, (0, 0, 0))
        with pytest.raises((AttributeError, TypeError)):
            r.x = 99  # type: ignore[misc]


# ─────────────────────────────────────────────
# MatchStrategy
# ─────────────────────────────────────────────


class TestMatchStrategy:
    def test_values(self):
        assert MatchStrategy.ALL.value == "all"
        assert MatchStrategy.ANY.value == "any"
        assert MatchStrategy.COUNT.value == "count"

    def test_from_string(self):
        assert MatchStrategy("all") is MatchStrategy.ALL
        assert MatchStrategy("any") is MatchStrategy.ANY
        assert MatchStrategy("count") is MatchStrategy.COUNT


# ─────────────────────────────────────────────
# PixelSignature
# ─────────────────────────────────────────────


class TestPixelSignature:
    def _two_rules(self) -> list[PixelRule]:
        return [
            PixelRule.of(0.10, 0.20, (50, 60, 70)),
            PixelRule.of(0.30, 0.40, (80, 90, 100)),
        ]

    def test_list_rules_normalised_to_tuple(self):
        sig = PixelSignature(name="test", rules=self._two_rules())
        assert isinstance(sig.rules, tuple)

    def test_len(self):
        sig = PixelSignature(name="test", rules=self._two_rules())
        assert len(sig) == 2

    def test_default_strategy_all(self):
        sig = PixelSignature(name="test", rules=self._two_rules())
        assert sig.strategy == MatchStrategy.ALL

    def test_from_dict_minimal(self):
        d = {
            "name": "main_page",
            "rules": [
                {"x": 0.10, "y": 0.20, "color": [50, 60, 70]},
            ],
        }
        sig = PixelSignature.from_dict(d)
        assert sig.name == "main_page"
        assert len(sig) == 1
        assert sig.strategy == MatchStrategy.ALL

    def test_from_dict_with_strategy(self):
        d = {
            "name": "any_page",
            "strategy": "any",
            "rules": [{"x": 0.0, "y": 0.0, "color": [0, 0, 0]}],
        }
        sig = PixelSignature.from_dict(d)
        assert sig.strategy == MatchStrategy.ANY

    def test_from_dict_with_threshold(self):
        d = {
            "name": "count_sig",
            "strategy": "count",
            "threshold": 2,
            "rules": [
                {"x": 0.0, "y": 0.0, "color": [0, 0, 0]},
                {"x": 0.1, "y": 0.0, "color": [1, 1, 1]},
                {"x": 0.2, "y": 0.0, "color": [2, 2, 2]},
            ],
        }
        sig = PixelSignature.from_dict(d)
        assert sig.threshold == 2

    def test_to_dict_round_trip(self):
        rules = self._two_rules()
        sig = PixelSignature(name="pg", rules=rules, strategy=MatchStrategy.ANY)
        d = sig.to_dict()
        restored = PixelSignature.from_dict(d)
        assert restored.name == sig.name
        assert len(restored.rules) == len(sig.rules)
        assert restored.strategy == sig.strategy


# ─────────────────────────────────────────────
# PixelMatchResult
# ─────────────────────────────────────────────


class TestPixelMatchResult:
    def test_bool_true(self):
        r = PixelMatchResult(matched=True, signature_name="x", matched_count=3, total_count=3)
        assert bool(r) is True

    def test_bool_false(self):
        r = PixelMatchResult(matched=False, signature_name="x", matched_count=0, total_count=3)
        assert bool(r) is False

    def test_ratio_full_match(self):
        r = PixelMatchResult(matched=True, signature_name="x", matched_count=3, total_count=3)
        assert r.ratio == pytest.approx(1.0)

    def test_ratio_partial(self):
        r = PixelMatchResult(matched=False, signature_name="x", matched_count=1, total_count=4)
        assert r.ratio == pytest.approx(0.25)

    def test_ratio_zero_rules(self):
        r = PixelMatchResult(matched=False, signature_name="x", matched_count=0, total_count=0)
        assert r.ratio == pytest.approx(0.0)


# ─────────────────────────────────────────────
# PixelChecker.get_pixel / check_pixel
# ─────────────────────────────────────────────


class TestPixelCheckerSingle:
    def test_get_pixel_reads_correct_position(self):
        # 纯色屏，任意相对坐标均返回相同颜色
        screen = solid_screen(100, 150, 200)
        c = PixelChecker.get_pixel(screen, x=0.5, y=0.5)
        assert c == Color(b=100, g=150, r=200)

    def test_get_pixel_origin(self):
        screen = solid_screen(0, 0, 0)
        screen[0, 0] = [1, 2, 3]
        c = PixelChecker.get_pixel(screen, x=0.0, y=0.0)
        assert c == Color(b=1, g=2, r=3)

    def test_get_pixel_reads_y_then_x(self):
        """确保内部转换为 screen[py, px] 顺序正确。
        10×10 屏幕: x=0.7 → col 7,  y=0.3 → row 3
        """
        screen = np.zeros((10, 10, 3), dtype=np.uint8)
        screen[3, 7] = [11, 22, 33]  # row=3, col=7
        c = PixelChecker.get_pixel(screen, x=0.7, y=0.3)
        assert c.b == 11 and c.g == 22 and c.r == 33

    def test_check_pixel_match(self):
        screen = solid_screen(100, 150, 200)
        assert PixelChecker.check_pixel(screen, 0.5, 0.5, Color.of(100, 150, 200)) is True

    def test_check_pixel_within_tolerance(self):
        screen = solid_screen(100, 100, 100)
        assert PixelChecker.check_pixel(screen, 0.0, 0.0, Color.of(115, 108, 98), tolerance=30) is True

    def test_check_pixel_outside_tolerance(self):
        screen = solid_screen(0, 0, 0)
        assert PixelChecker.check_pixel(screen, 0.0, 0.0, Color.of(255, 255, 255), tolerance=30) is False

    def test_check_pixel_exact_tolerance_boundary(self):
        screen = solid_screen(0, 0, 0)
        # distance to (3,4,0) = 5.0
        target = Color.of(3, 4, 0)
        assert PixelChecker.check_pixel(screen, 0.0, 0.0, target, tolerance=5.0) is True
        assert PixelChecker.check_pixel(screen, 0.0, 0.0, target, tolerance=4.9) is False


# ─────────────────────────────────────────────
# PixelChecker.get_pixels / check_pixels
# ─────────────────────────────────────────────


class TestPixelCheckerBatch:
    def test_get_pixels_returns_list(self):
        screen = solid_screen(50, 60, 70)
        colors = PixelChecker.get_pixels(screen, [(0.0, 0.0), (0.1, 0.1), (0.2, 0.2)])
        assert len(colors) == 3
        assert all(c == Color(b=50, g=60, r=70) for c in colors)

    def test_get_pixels_empty(self):
        screen = solid_screen(0, 0, 0)
        assert PixelChecker.get_pixels(screen, []) == []

    def test_check_pixels_all_match(self):
        screen = solid_screen(50, 60, 70)
        rules = [
            PixelRule.of(0.0, 0.0, (50, 60, 70)),
            PixelRule.of(0.5, 0.5, (50, 60, 70)),
        ]
        results = PixelChecker.check_pixels(screen, rules)
        assert results == [True, True]

    def test_check_pixels_mixed(self):
        screen = solid_screen(50, 60, 70)
        rules = [
            PixelRule.of(0.0, 0.0, (50, 60, 70)),      # match
            PixelRule.of(0.0, 0.0, (200, 200, 200)),   # mismatch
        ]
        results = PixelChecker.check_pixels(screen, rules)
        assert results == [True, False]

    def test_check_pixels_empty(self):
        screen = solid_screen(0, 0, 0)
        assert PixelChecker.check_pixels(screen, []) == []


# ─────────────────────────────────────────────
# PixelChecker.check_signature — ALL strategy
# ─────────────────────────────────────────────


class TestCheckSignatureAll:
    def _sig(self, rules: list[PixelRule]) -> PixelSignature:
        return PixelSignature(name="test_all", rules=rules, strategy=MatchStrategy.ALL)

    def test_all_match(self):
        screen = solid_screen(100, 100, 100)
        sig = self._sig([PixelRule.of(0.0, 0.0, (100, 100, 100)), PixelRule.of(0.5, 0.5, (100, 100, 100))])
        result = PixelChecker.check_signature(screen, sig)
        assert result.matched is True
        assert result.matched_count == 2

    def test_one_mismatch_fails_all(self):
        screen = solid_screen(100, 100, 100)
        sig = self._sig([
            PixelRule.of(0.0, 0.0, (100, 100, 100)),   # pass
            PixelRule.of(0.0, 0.0, (200, 200, 200)),   # fail
        ])
        result = PixelChecker.check_signature(screen, sig)
        assert result.matched is False

    def test_empty_rules_matches(self):
        screen = solid_screen(0, 0, 0)
        sig = self._sig([])
        result = PixelChecker.check_signature(screen, sig)
        # all() of empty is True
        assert result.matched is True
        assert result.matched_count == 0
        assert result.total_count == 0

    def test_with_details_populates_details(self):
        screen = solid_screen(100, 100, 100)
        sig = self._sig([PixelRule.of(0.0, 0.0, (100, 100, 100))])
        result = PixelChecker.check_signature(screen, sig, with_details=True)
        assert len(result.details) == 1
        assert isinstance(result.details[0], PixelDetail)

    def test_without_details_empty_tuple(self):
        screen = solid_screen(100, 100, 100)
        sig = self._sig([PixelRule.of(0.0, 0.0, (100, 100, 100))])
        result = PixelChecker.check_signature(screen, sig, with_details=False)
        assert result.details == ()

    def test_details_contain_actual_color(self):
        b, g, r = 55, 66, 77
        screen = solid_screen(b, g, r)
        sig = self._sig([PixelRule.of(0.0, 0.0, (b, g, r))])
        result = PixelChecker.check_signature(screen, sig, with_details=True)
        detail = result.details[0]
        assert detail.actual == Color(b=b, g=g, r=r)
        assert detail.matched is True
        assert detail.distance == pytest.approx(0.0)

    def test_early_exit_on_mismatch_without_details(self):
        """ALL 模式无详情时遇到第一个失败直接返回，不再检查后续规则。"""
        screen = solid_screen(0, 0, 0)
        # 第一条规则就失败
        sig = self._sig([
            PixelRule.of(0.0, 0.0, (255, 255, 255)),  # fail
            PixelRule.of(0.0, 0.0, (0, 0, 0)),        # would pass, but never checked
        ])
        result = PixelChecker.check_signature(screen, sig, with_details=False)
        assert result.matched is False
        # matched_count 为 0（第二条没机会匹配）
        assert result.matched_count == 0


# ─────────────────────────────────────────────
# PixelChecker.check_signature — ANY strategy
# ─────────────────────────────────────────────


class TestCheckSignatureAny:
    def _sig(self, rules: list[PixelRule]) -> PixelSignature:
        return PixelSignature(name="test_any", rules=rules, strategy=MatchStrategy.ANY)

    def test_first_rule_matches(self):
        screen = solid_screen(50, 50, 50)
        sig = self._sig([
            PixelRule.of(0.0, 0.0, (50, 50, 50)),    # match
            PixelRule.of(0.0, 0.0, (200, 200, 200)), # never reached
        ])
        result = PixelChecker.check_signature(screen, sig)
        assert result.matched is True

    def test_second_rule_matches(self):
        screen = solid_screen(50, 50, 50)
        sig = self._sig([
            PixelRule.of(0.0, 0.0, (200, 200, 200)), # fail
            PixelRule.of(0.0, 0.0, (50, 50, 50)),    # match
        ])
        result = PixelChecker.check_signature(screen, sig)
        assert result.matched is True

    def test_none_matches(self):
        screen = solid_screen(50, 50, 50)
        sig = self._sig([
            PixelRule.of(0.0, 0.0, (200, 200, 200)),
            PixelRule.of(0.0, 0.0, (210, 210, 210)),
        ])
        result = PixelChecker.check_signature(screen, sig)
        assert result.matched is False

    def test_empty_rules_not_matched(self):
        screen = solid_screen(0, 0, 0)
        sig = self._sig([])
        result = PixelChecker.check_signature(screen, sig)
        assert result.matched is False


# ─────────────────────────────────────────────
# PixelChecker.check_signature — COUNT strategy
# ─────────────────────────────────────────────


class TestCheckSignatureCount:
    def _sig(self, rules: list[PixelRule], threshold: int) -> PixelSignature:
        return PixelSignature(
            name="test_count", rules=rules,
            strategy=MatchStrategy.COUNT, threshold=threshold,
        )

    def test_meets_threshold(self):
        screen = solid_screen(0, 0, 0)
        sig = self._sig([
            PixelRule.of(0.0, 0.0, (0, 0, 0)),      # match
            PixelRule.of(0.0, 0.0, (0, 0, 0)),      # match
            PixelRule.of(0.0, 0.0, (255, 0, 0), tolerance=1),  # fail
        ], threshold=2)
        result = PixelChecker.check_signature(screen, sig)
        assert result.matched is True

    def test_below_threshold(self):
        screen = solid_screen(0, 0, 0)
        sig = self._sig([
            PixelRule.of(0.0, 0.0, (0, 0, 0)),     # match
            PixelRule.of(0.0, 0.0, (255, 0, 0), tolerance=1),  # fail
            PixelRule.of(0.0, 0.0, (255, 0, 0), tolerance=1),  # fail
        ], threshold=2)
        result = PixelChecker.check_signature(screen, sig)
        assert result.matched is False

    def test_threshold_exactly_zero_always_true(self):
        screen = solid_screen(0, 0, 0)
        sig = self._sig([PixelRule.of(0.0, 0.0, (255, 0, 0), tolerance=1)], threshold=0)
        result = PixelChecker.check_signature(screen, sig)
        assert result.matched is True


# ─────────────────────────────────────────────
# PixelChecker.identify / identify_all
# ─────────────────────────────────────────────


class TestIdentify:
    # 100×100 screen: x=0.10 → col 10, y=0.10 → row 10
    def _make_screen_with_marker(self, marker_color=(0, 0, 0)) -> np.ndarray:
        screen = np.full((100, 100, 3), 100, dtype=np.uint8)
        screen[10, 10] = marker_color  # row=10, col=10
        return screen

    def test_identify_returns_first_match(self):
        screen = self._make_screen_with_marker((200, 0, 0))
        page_a = PixelSignature(name="a", rules=[PixelRule.of(0.10, 0.10, (200, 0, 0))])
        page_b = PixelSignature(name="b", rules=[PixelRule.of(0.10, 0.10, (200, 0, 0))])
        result = PixelChecker.identify(screen, [page_a, page_b])
        assert result is not None
        assert result.signature_name == "a"  # returns first

    def test_identify_returns_none_if_no_match(self):
        screen = solid_screen(50, 50, 50)
        sig = PixelSignature(name="x", rules=[PixelRule.of(0.0, 0.0, (200, 200, 200))])
        assert PixelChecker.identify(screen, [sig]) is None

    def test_identify_empty_list(self):
        screen = solid_screen(0, 0, 0)
        assert PixelChecker.identify(screen, []) is None

    def test_identify_skips_unmatched(self):
        screen = self._make_screen_with_marker((99, 0, 0))
        page_a = PixelSignature(name="a", rules=[PixelRule.of(0.10, 0.10, (200, 0, 0))])  # wrong color
        page_b = PixelSignature(name="b", rules=[PixelRule.of(0.10, 0.10, (99, 0, 0))])   # correct
        result = PixelChecker.identify(screen, [page_a, page_b])
        assert result is not None
        assert result.signature_name == "b"

    def test_identify_all_returns_all_matches(self):
        screen = solid_screen(100, 100, 100)
        r1 = PixelRule.of(0.0, 0.0, (100, 100, 100))
        r2 = PixelRule.of(0.0, 0.0, (100, 100, 100))
        sig_a = PixelSignature(name="a", rules=[r1])
        sig_b = PixelSignature(name="b", rules=[r2])
        results = PixelChecker.identify_all(screen, [sig_a, sig_b])
        names = [r.signature_name for r in results]
        assert "a" in names and "b" in names

    def test_identify_all_empty_on_no_match(self):
        screen = solid_screen(0, 0, 0)
        sig = PixelSignature(name="x", rules=[PixelRule.of(0.0, 0.0, (255, 255, 255))])
        assert PixelChecker.identify_all(screen, [sig]) == []


# ─────────────────────────────────────────────
# PixelChecker.classify_color
# ─────────────────────────────────────────────


class TestClassifyColor:
    BLOOD_COLORS = {
        "green":  Color.of(69, 162, 117),
        "yellow": Color.of(246, 184, 51),
        "red":    Color.of(230, 58, 89),
    }

    def _screen_with_pixel(self, b, g, r) -> np.ndarray:
        s = np.zeros((10, 10, 3), dtype=np.uint8)
        s[5, 5] = [b, g, r]
        return s

    # _screen_with_pixel 使用 10×10 屏幕，s[5,5] 对应 x=0.5, y=0.5
    def test_classify_green(self):
        screen = self._screen_with_pixel(69, 162, 117)
        result = PixelChecker.classify_color(screen, 0.5, 0.5, self.BLOOD_COLORS)
        assert result == "green"

    def test_classify_yellow(self):
        screen = self._screen_with_pixel(246, 184, 51)
        result = PixelChecker.classify_color(screen, 0.5, 0.5, self.BLOOD_COLORS)
        assert result == "yellow"

    def test_classify_undefined_color_returns_none(self):
        screen = self._screen_with_pixel(128, 128, 128)
        result = PixelChecker.classify_color(
            screen, 0.5, 0.5, self.BLOOD_COLORS, tolerance=5.0
        )
        assert result is None

    def test_classify_nearest_within_tolerance(self):
        # Slightly off from green
        screen = self._screen_with_pixel(72, 160, 115)
        result = PixelChecker.classify_color(screen, 0.5, 0.5, self.BLOOD_COLORS, tolerance=30)
        assert result == "green"

    def test_classify_empty_map(self):
        screen = self._screen_with_pixel(100, 100, 100)
        assert PixelChecker.classify_color(screen, 0.5, 0.5, {}) is None


# ─────────────────────────────────────────────
# PixelChecker.crop / crop_relative
# ─────────────────────────────────────────────


class TestCrop:
    """crop() 现在接受相对坐标 (0.0–1.0)，内部转换为绝对像素索引。"""

    def test_crop_returns_correct_shape(self):
        # 100×200 屏幕: x1=0.05→10, y1=0.20→20, x2=0.25→50, y2=0.80→80
        screen = solid_screen(0, 0, 0, h=100, w=200)
        cropped = PixelChecker.crop(screen, x1=0.05, y1=0.20, x2=0.25, y2=0.80)
        assert cropped.shape == (60, 40, 3)

    def test_crop_is_copy(self):
        screen = solid_screen(0, 0, 0)
        cropped = PixelChecker.crop(screen, 0.0, 0.0, 0.5, 0.5)
        cropped[0, 0] = [99, 99, 99]
        assert screen[0, 0, 0] != 99

    def test_crop_content(self):
        # 100×100 屏幕: screen[50,50] → x=0.50,y=0.50; crop [0.45,0.45)→(0.55,0.55) = pixels [45:55, 45:55]
        screen = np.zeros((100, 100, 3), dtype=np.uint8)
        screen[50, 50] = [1, 2, 3]
        cropped = PixelChecker.crop(screen, x1=0.45, y1=0.45, x2=0.55, y2=0.55)
        # screen[50,50] → cropped[5,5]
        assert list(cropped[5, 5]) == [1, 2, 3]

    def test_crop_full_width(self):
        # x2=1.0 应该等于整列宽
        screen = solid_screen(7, 8, 9, h=50, w=100)
        cropped = PixelChecker.crop(screen, 0.0, 0.0, 1.0, 1.0)
        assert cropped.shape == (50, 100, 3)


# ─────────────────────────────────────────────
# Integration: real-world-like scenario
# ─────────────────────────────────────────────


class TestIntegration:
    """模拟真实页面识别流程。"""

    def test_page_identification(self):
        # 100×100 合成屏幕，两个页面特征点位于不同坐标
        # main_page: (0.50, 0.50) 和 (0.20, 0.30)
        # map_page:  (0.80, 0.10) 和 (0.90, 0.20)
        main_page_sig = PixelSignature(
            name="main_page",
            rules=[
                PixelRule.of(0.50, 0.50, (201, 129, 54)),
                PixelRule.of(0.20, 0.30, (47, 253, 226)),
            ],
        )
        map_page_sig = PixelSignature(
            name="map_page",
            rules=[
                PixelRule.of(0.80, 0.10, (255, 200, 100)),
                PixelRule.of(0.90, 0.20, (200, 230, 80)),
            ],
        )

        # 构建「主页」截图：在对应相对坐标写入特征颜色
        # col=50,row=50 和 col=20,row=30
        screen = np.zeros((100, 100, 3), dtype=np.uint8)
        screen[50, 50] = [201, 129, 54]
        screen[30, 20] = [47, 253, 226]

        result = PixelChecker.identify(screen, [main_page_sig, map_page_sig])
        assert result is not None
        assert result.signature_name == "main_page"

    def test_signature_yaml_round_trip(self):
        original = PixelSignature(
            name="fight_prepare",
            strategy=MatchStrategy.COUNT,
            threshold=2,
            rules=[
                PixelRule.of(0.50, 0.50, (10, 20, 30), tolerance=25.0),
                PixelRule.of(0.60, 0.70, (40, 50, 60)),
            ],
        )
        restored = PixelSignature.from_dict(original.to_dict())
        assert restored.name == original.name
        assert restored.strategy == original.strategy
        assert restored.threshold == original.threshold
        assert len(restored.rules) == len(original.rules)
        assert restored.rules[0].tolerance == 25.0
