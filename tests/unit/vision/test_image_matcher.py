"""Tests for autowsgr.vision.image_matcher — ImageChecker engine."""

from __future__ import annotations

import numpy as np
import pytest

from autowsgr.vision import (
    ROI,
    TEMPLATE_SOURCE_RESOLUTION,
    ImageChecker,
    ImageRule,
    ImageSignature,
    ImageTemplate,
    MatchStrategy,
)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────


def _solid_screen(r: int, g: int, b: int, h: int = 100, w: int = 100) -> np.ndarray:
    """Create a solid-color screenshot."""
    screen = np.zeros((h, w, 3), dtype=np.uint8)
    screen[:, :] = [r, g, b]
    return screen


def _make_template(
    name: str = 'tmpl',
    size: int = 20,
    resolution: tuple[int, int] = (100, 100),
) -> ImageTemplate:
    """Create a random template whose pattern depends on *name*."""
    rng = np.random.RandomState(hash(name) % (2**31))
    img = rng.randint(0, 256, (size, size, 3), dtype=np.uint8)
    return ImageTemplate(
        name=name,
        image=img,
        source='test',
        source_resolution=resolution,
    )


def _embed(screen: np.ndarray, img: np.ndarray, x: int, y: int) -> np.ndarray:
    """Embed an image into a screen at absolute pixel coordinates."""
    s = screen.copy()
    h, w = img.shape[:2]
    s[y : y + h, x : x + w] = img
    return s


# ─────────────────────────────────────────────
# _scale_template_if_needed
# ─────────────────────────────────────────────


class TestScaleTemplate:
    def test_same_resolution_returns_original(self) -> None:
        img = np.zeros((30, 40, 3), dtype=np.uint8)
        result = ImageChecker._scale_template_if_needed(
            img,
            960,
            540,
            source_resolution=(960, 540),
        )
        assert result is img

    def test_different_resolution_returns_new_array(self) -> None:
        img = np.zeros((60, 80, 3), dtype=np.uint8)
        result = ImageChecker._scale_template_if_needed(
            img,
            960,
            540,
            source_resolution=(1920, 1080),
        )
        assert result is not img
        assert result.shape == (30, 40, 3)

    def test_global_fallback_resolution(self) -> None:
        img = np.zeros((30, 40, 3), dtype=np.uint8)
        result = ImageChecker._scale_template_if_needed(img, 960, 540)
        assert result is img
        assert TEMPLATE_SOURCE_RESOLUTION == (960, 540)


# ─────────────────────────────────────────────
# crop
# ─────────────────────────────────────────────


class TestCrop:
    def test_crop_returns_correct_subarray(self) -> None:
        screen = _solid_screen(100, 150, 200)
        roi = ROI(0.0, 0.0, 0.5, 0.5)
        cropped = ImageChecker.crop(screen, roi)
        assert cropped.shape == (50, 50, 3)
        assert cropped[0, 0, 0] == 100

    def test_crop_returns_copy(self) -> None:
        screen = _solid_screen(100, 150, 200)
        roi = ROI(0.0, 0.0, 0.5, 0.5)
        cropped = ImageChecker.crop(screen, roi)
        cropped[0, 0] = [255, 0, 0]
        assert screen[0, 0, 0] == 100


# ─────────────────────────────────────────────
# find_template
# ─────────────────────────────────────────────


class TestFindTemplate:
    def test_perfect_match(self) -> None:
        screen = _solid_screen(0, 0, 0)
        tmpl = _make_template(name='exact')
        screen = _embed(screen, tmpl.image, 10, 10)
        detail = ImageChecker.find_template(screen, tmpl, confidence=0.9)
        assert detail is not None
        assert detail.confidence > 0.99
        assert detail.template_name == 'exact'
        cx, cy = detail.center
        assert cx == pytest.approx(0.2, abs=0.01)
        assert cy == pytest.approx(0.2, abs=0.01)

    def test_no_match(self) -> None:
        screen = _solid_screen(0, 0, 0)
        tmpl = _make_template(name='absent')
        detail = ImageChecker.find_template(screen, tmpl, confidence=0.9)
        assert detail is None


# ─────────────────────────────────────────────
# find_any
# ─────────────────────────────────────────────


class TestFindAny:
    def test_first_matching_template(self) -> None:
        screen = _solid_screen(0, 0, 0)
        t1 = _make_template(name='first')
        t2 = _make_template(name='second')
        screen = _embed(screen, t1.image, 10, 10)
        detail = ImageChecker.find_any(screen, [t1, t2], confidence=0.9)
        assert detail is not None
        assert detail.template_name == 'first'

    def test_second_matches_when_first_absent(self) -> None:
        screen = _solid_screen(0, 0, 0)
        t1 = _make_template(name='first')
        t2 = _make_template(name='second')
        screen = _embed(screen, t2.image, 10, 10)
        detail = ImageChecker.find_any(screen, [t1, t2], confidence=0.9)
        assert detail is not None
        assert detail.template_name == 'second'

    def test_none_match(self) -> None:
        screen = _solid_screen(0, 0, 0)
        t1 = _make_template(name='absent')
        detail = ImageChecker.find_any(screen, [t1], confidence=0.9)
        assert detail is None


# ─────────────────────────────────────────────
# find_best
# ─────────────────────────────────────────────


class TestFindBest:
    def test_highest_confidence_returned(self) -> None:
        screen = _solid_screen(0, 0, 0)
        exact = _make_template(name='exact')
        # Create a noisy variant by altering a small central block.
        noisy_img = exact.image.copy()
        noisy_img[8:12, 8:12] = [0, 0, 0]
        noisy = ImageTemplate(
            name='noisy',
            image=noisy_img,
            source='test',
            source_resolution=exact.source_resolution,
        )
        screen = _embed(screen, exact.image, 10, 10)

        # Verify exact template matches with higher confidence.
        exact_detail = ImageChecker._match_single_template(
            screen,
            exact,
            confidence=0.5,
        )
        noisy_detail = ImageChecker._match_single_template(
            screen,
            noisy,
            confidence=0.5,
        )
        assert exact_detail is not None
        assert noisy_detail is not None
        assert exact_detail.confidence > noisy_detail.confidence

        # Pass noisy first; find_best should still return exact.
        best = ImageChecker.find_best(screen, [noisy, exact], confidence=0.5)
        assert best is not None
        assert best.template_name == 'exact'

    def test_none_match(self) -> None:
        screen = _solid_screen(0, 0, 0)
        t1 = _make_template(name='absent')
        best = ImageChecker.find_best(screen, [t1], confidence=0.9)
        assert best is None


# ─────────────────────────────────────────────
# find_all
# ─────────────────────────────────────────────


class TestFindAll:
    def test_returns_all_matching(self) -> None:
        screen = _solid_screen(0, 0, 0)
        t1 = _make_template(name='a')
        t2 = _make_template(name='b')
        screen = _embed(screen, t1.image, 10, 10)
        screen = _embed(screen, t2.image, 60, 60)
        results = ImageChecker.find_all(screen, [t1, t2], confidence=0.9)
        assert len(results) == 2
        names = {r.template_name for r in results}
        assert names == {'a', 'b'}

    def test_skips_non_matching(self) -> None:
        screen = _solid_screen(0, 0, 0)
        t1 = _make_template(name='a')
        t2 = _make_template(name='absent')
        screen = _embed(screen, t1.image, 10, 10)
        results = ImageChecker.find_all(screen, [t1, t2], confidence=0.9)
        assert len(results) == 1
        assert results[0].template_name == 'a'


# ─────────────────────────────────────────────
# template_exists
# ─────────────────────────────────────────────


class TestTemplateExists:
    def test_single_template_true(self) -> None:
        screen = _solid_screen(0, 0, 0)
        tmpl = _make_template(name='btn')
        screen = _embed(screen, tmpl.image, 10, 10)
        assert ImageChecker.template_exists(screen, tmpl, confidence=0.9) is True

    def test_single_template_false(self) -> None:
        screen = _solid_screen(0, 0, 0)
        tmpl = _make_template(name='btn')
        assert ImageChecker.template_exists(screen, tmpl, confidence=0.9) is False

    def test_list_with_match(self) -> None:
        screen = _solid_screen(0, 0, 0)
        t1 = _make_template(name='a')
        t2 = _make_template(name='b')
        screen = _embed(screen, t2.image, 10, 10)
        assert ImageChecker.template_exists(screen, [t1, t2], confidence=0.9) is True

    def test_list_without_match(self) -> None:
        screen = _solid_screen(0, 0, 0)
        t1 = _make_template(name='a')
        t2 = _make_template(name='b')
        assert ImageChecker.template_exists(screen, [t1, t2], confidence=0.9) is False


# ─────────────────────────────────────────────
# identify
# ─────────────────────────────────────────────


class TestIdentify:
    def test_first_matching_signature(self) -> None:
        screen = _solid_screen(0, 0, 0)
        t1 = _make_template(name='a')
        screen = _embed(screen, t1.image, 10, 10)
        sig1 = ImageSignature(
            name='page_a',
            rules=[ImageRule(name='r1', templates=[t1], confidence=0.9)],
        )
        sig2 = ImageSignature(
            name='page_b',
            rules=[
                ImageRule(
                    name='r2',
                    templates=[_make_template(name='absent')],
                    confidence=0.9,
                ),
            ],
        )
        result = ImageChecker.identify(screen, [sig1, sig2])
        assert result is not None
        assert result.rule_name == 'page_a'

    def test_none_match(self) -> None:
        screen = _solid_screen(0, 0, 0)
        sig = ImageSignature(
            name='page_x',
            rules=[
                ImageRule(
                    name='r',
                    templates=[_make_template(name='absent')],
                    confidence=0.9,
                ),
            ],
        )
        assert ImageChecker.identify(screen, [sig]) is None


# ─────────────────────────────────────────────
# find_all_occurrences
# ─────────────────────────────────────────────


class TestFindAllOccurrences:
    def test_multiple_occurrences(self) -> None:
        screen = _solid_screen(0, 0, 0)
        tmpl = _make_template(name='icon')
        screen = _embed(screen, tmpl.image, 10, 10)
        screen = _embed(screen, tmpl.image, 60, 60)
        results = ImageChecker.find_all_occurrences(
            screen,
            tmpl,
            confidence=0.9,
            min_distance=10,
        )
        assert len(results) == 2

    def test_nms_deduplication(self) -> None:
        screen = _solid_screen(0, 0, 0)
        tmpl = _make_template(name='icon')
        screen = _embed(screen, tmpl.image, 10, 10)
        screen = _embed(screen, tmpl.image, 12, 12)
        results = ImageChecker.find_all_occurrences(
            screen,
            tmpl,
            confidence=0.9,
            min_distance=10,
        )
        assert len(results) == 1


# ─────────────────────────────────────────────
# match_rule
# ─────────────────────────────────────────────


class TestMatchRule:
    def test_or_semantics_one_matches(self) -> None:
        screen = _solid_screen(0, 0, 0)
        t1 = _make_template(name='v1')
        t2 = _make_template(name='v2')
        screen = _embed(screen, t2.image, 10, 10)
        rule = ImageRule(name='confirm', templates=[t1, t2], confidence=0.9)
        result = ImageChecker.match_rule(screen, rule)
        assert result.matched is True
        assert result.best is not None
        assert result.best.template_name == 'v2'

    def test_or_semantics_none_match(self) -> None:
        screen = _solid_screen(0, 0, 0)
        t1 = _make_template(name='v1')
        t2 = _make_template(name='v2')
        rule = ImageRule(name='confirm', templates=[t1, t2], confidence=0.9)
        result = ImageChecker.match_rule(screen, rule)
        assert result.matched is False
        assert result.best is None


# ─────────────────────────────────────────────
# check_signature
# ─────────────────────────────────────────────


class TestCheckSignature:
    def test_all_strategy_all_match(self) -> None:
        screen = _solid_screen(0, 0, 0)
        t1 = _make_template(name='a')
        t2 = _make_template(name='b')
        screen = _embed(screen, t1.image, 10, 10)
        screen = _embed(screen, t2.image, 60, 60)
        sig = ImageSignature(
            name='page',
            rules=[
                ImageRule(name='r1', templates=[t1], confidence=0.9),
                ImageRule(name='r2', templates=[t2], confidence=0.9),
            ],
            strategy=MatchStrategy.ALL,
        )
        result = ImageChecker.check_signature(screen, sig)
        assert result.matched is True

    def test_all_strategy_short_circuit_fail(self) -> None:
        screen = _solid_screen(0, 0, 0)
        t1 = _make_template(name='a')
        screen = _embed(screen, t1.image, 10, 10)
        sig = ImageSignature(
            name='page',
            rules=[
                ImageRule(name='r1', templates=[t1], confidence=0.9),
                ImageRule(
                    name='r2',
                    templates=[_make_template(name='absent')],
                    confidence=0.9,
                ),
            ],
            strategy=MatchStrategy.ALL,
        )
        result = ImageChecker.check_signature(screen, sig)
        assert result.matched is False

    def test_any_strategy_short_circuit_success(self) -> None:
        screen = _solid_screen(0, 0, 0)
        t1 = _make_template(name='a')
        screen = _embed(screen, t1.image, 10, 10)
        sig = ImageSignature(
            name='page',
            rules=[
                ImageRule(name='r1', templates=[t1], confidence=0.9),
                ImageRule(
                    name='r2',
                    templates=[_make_template(name='absent')],
                    confidence=0.9,
                ),
            ],
            strategy=MatchStrategy.ANY,
        )
        result = ImageChecker.check_signature(screen, sig)
        assert result.matched is True

    def test_any_strategy_none_match(self) -> None:
        screen = _solid_screen(0, 0, 0)
        sig = ImageSignature(
            name='page',
            rules=[
                ImageRule(name='r1', templates=[_make_template(name='a')], confidence=0.9),
                ImageRule(name='r2', templates=[_make_template(name='b')], confidence=0.9),
            ],
            strategy=MatchStrategy.ANY,
        )
        result = ImageChecker.check_signature(screen, sig)
        assert result.matched is False

    def test_count_strategy_meets_threshold(self) -> None:
        screen = _solid_screen(0, 0, 0)
        t1 = _make_template(name='a')
        t2 = _make_template(name='b')
        screen = _embed(screen, t1.image, 10, 10)
        screen = _embed(screen, t2.image, 60, 60)
        sig = ImageSignature(
            name='page',
            rules=[
                ImageRule(name='r1', templates=[t1], confidence=0.9),
                ImageRule(name='r2', templates=[t2], confidence=0.9),
                ImageRule(
                    name='r3',
                    templates=[_make_template(name='absent')],
                    confidence=0.9,
                ),
            ],
            strategy=MatchStrategy.COUNT,
            threshold=2,
        )
        result = ImageChecker.check_signature(screen, sig)
        assert result.matched is True

    def test_count_strategy_below_threshold(self) -> None:
        screen = _solid_screen(0, 0, 0)
        t1 = _make_template(name='a')
        screen = _embed(screen, t1.image, 10, 10)
        sig = ImageSignature(
            name='page',
            rules=[
                ImageRule(name='r1', templates=[t1], confidence=0.9),
                ImageRule(
                    name='r2',
                    templates=[_make_template(name='absent')],
                    confidence=0.9,
                ),
                ImageRule(
                    name='r3',
                    templates=[_make_template(name='absent2')],
                    confidence=0.9,
                ),
            ],
            strategy=MatchStrategy.COUNT,
            threshold=2,
        )
        result = ImageChecker.check_signature(screen, sig)
        assert result.matched is False
