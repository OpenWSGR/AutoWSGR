"""Tests for autowsgr.ui.utils.ship_list."""

from __future__ import annotations

from autowsgr.ui.utils.ship_list import (
    LevelOCRRetryNeededError,
    _center_x,
    _coerce_level_digits,
    _noise_char_count,
    _parse_level,
    _parse_level_with_status,
)


class TestNoiseCharCount:
    def test_all_noise_letters(self) -> None:
        # I, L, l, O, o are noise; 1 and 0 are valid digits and not counted.
        assert _noise_char_count('ILl1Oo0') == 5

    def test_no_noise(self) -> None:
        assert _noise_char_count('abc123') == 0

    def test_empty(self) -> None:
        assert _noise_char_count('') == 0


class TestCoerceLevelDigits:
    def test_simple_three_digit(self) -> None:
        assert _coerce_level_digits('120') == 120

    def test_truncates_to_first_three(self) -> None:
        assert _coerce_level_digits('1046') == 104

    def test_leading_zero(self) -> None:
        assert _coerce_level_digits('051') == 51

    def test_only_zeros_after_translation(self) -> None:
        assert _coerce_level_digits('O0') is None

    def test_letter_to_digit_translation(self) -> None:
        assert _coerce_level_digits('IL') == 11

    def test_no_digits(self) -> None:
        assert _coerce_level_digits('abc') is None


class TestParseLevel:
    def test_standard_level(self) -> None:
        assert _parse_level('Lv.120') == 120

    def test_no_level(self) -> None:
        assert _parse_level('abc') is None


class TestParseLevelWithStatus:
    def test_standard_level(self) -> None:
        assert _parse_level_with_status('Lv.120') == (120, False)

    def test_noisy_excessive_noise(self) -> None:
        assert _parse_level_with_status('Lv.IL') == (None, True)

    def test_noisy_pattern_valid(self) -> None:
        assert _parse_level_with_status('lV.12') == (12, False)


class TestCenterX:
    def test_none_bbox(self) -> None:
        assert _center_x(None, 100) == 50.0

    def test_valid_bbox(self) -> None:
        assert _center_x((10, 0, 30, 0), 100) == 20.0


class TestLevelOCRRetryNeededError:
    def test_is_runtime_error_subclass(self) -> None:
        assert issubclass(LevelOCRRetryNeededError, RuntimeError)
