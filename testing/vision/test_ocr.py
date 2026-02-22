"""Tests for autowsgr.vision.ocr — OCR engine abstractions and helpers."""
from __future__ import annotations

import numpy as np
import pytest

from autowsgr.vision import OCREngine, OCRResult, ShipNameMismatchError
from autowsgr.vision.ocr import (
    _edit_distance,
    _fuzzy_match,
)


# ─────────────────────────────────────────────
# MockOCREngine — no heavy dependencies
# ─────────────────────────────────────────────


class MockOCREngine(OCREngine):
    """Minimal OCR engine for unit testing without EasyOCR / PaddleOCR."""

    def __init__(self, results: list[OCRResult]) -> None:
        self._results = results

    def recognize(
        self,
        image: np.ndarray,
        allowlist: str = "",
    ) -> list[OCRResult]:
        return self._results


def _dummy_image() -> np.ndarray:
    return np.zeros((10, 10, 3), dtype=np.uint8)


# ─────────────────────────────────────────────
# OCRResult
# ─────────────────────────────────────────────


class TestOCRResult:
    def test_basic_fields(self):
        r = OCRResult(text="hello", confidence=0.95)
        assert r.text == "hello"
        assert r.confidence == pytest.approx(0.95)
        assert r.bbox is None

    def test_with_bbox(self):
        r = OCRResult(text="42", confidence=0.8, bbox=(10, 20, 50, 40))
        assert r.bbox == (10, 20, 50, 40)

    def test_immutable(self):
        r = OCRResult(text="x", confidence=0.5)
        with pytest.raises((AttributeError, TypeError)):
            r.text = "y"  # type: ignore[misc]


# ─────────────────────────────────────────────
# _fuzzy_match
# ─────────────────────────────────────────────


class TestFuzzyMatch:
    SHIP_NAMES = ["雪风", "时雨", "由良", "爱宕", "高雄"]

    def test_exact_match(self):
        assert _fuzzy_match("雪风", self.SHIP_NAMES) == "雪风"

    def test_one_char_off(self):
        # OCR 误识别一个字
        assert _fuzzy_match("雪凤", self.SHIP_NAMES) == "雪风"

    def test_no_match_exceeds_threshold(self):
        result = _fuzzy_match("全然不同", self.SHIP_NAMES, threshold=1)
        assert result is None

    def test_empty_candidates(self):
        assert _fuzzy_match("雪风", []) is None

    def test_threshold_zero_requires_exact(self):
        assert _fuzzy_match("雪凤", self.SHIP_NAMES, threshold=0) is None
        assert _fuzzy_match("雪风", self.SHIP_NAMES, threshold=0) == "雪风"

    def test_picks_closest(self):
        candidates = ["abc", "xyz"]
        # "abx" → "abc" distance=1, "xyz" distance=2
        result = _fuzzy_match("abx", candidates, threshold=3)
        assert result == "abc"

    def test_default_threshold_is_3(self):
        # distance 3 should match
        result = _fuzzy_match("abcd", ["wxyz"], threshold=3)
        assert result is None  # distance = 4 > 3
        result = _fuzzy_match("abcd", ["abce"], threshold=3)
        assert result == "abce"  # distance = 1


# ─────────────────────────────────────────────
# OCREngine.recognize_single
# ─────────────────────────────────────────────


class TestRecognizeSingle:
    def test_returns_highest_confidence(self):
        engine = MockOCREngine([
            OCRResult(text="low", confidence=0.4),
            OCRResult(text="high", confidence=0.9),
            OCRResult(text="mid", confidence=0.6),
        ])
        result = engine.recognize_single(_dummy_image())
        assert result.text == "high"

    def test_empty_results_returns_empty(self):
        engine = MockOCREngine([])
        result = engine.recognize_single(_dummy_image())
        assert result.text == ""
        assert result.confidence == pytest.approx(0.0)

    def test_single_result_returned(self):
        r = OCRResult(text="42", confidence=0.95)
        engine = MockOCREngine([r])
        result = engine.recognize_single(_dummy_image())
        assert result.text == "42"


# ─────────────────────────────────────────────
# OCREngine.recognize_number
# ─────────────────────────────────────────────


class TestRecognizeNumber:
    def _engine(self, text: str) -> MockOCREngine:
        return MockOCREngine([OCRResult(text=text, confidence=0.9)])

    def test_plain_integer(self):
        assert self._engine("123").recognize_number(_dummy_image()) == 123

    def test_k_suffix_lowercase(self):
        assert self._engine("5k").recognize_number(_dummy_image()) == 5000

    def test_k_suffix_uppercase(self):
        assert self._engine("10K").recognize_number(_dummy_image()) == 10000

    def test_m_suffix(self):
        assert self._engine("2M").recognize_number(_dummy_image()) == 2_000_000

    def test_decimal_with_k(self):
        assert self._engine("1.5K").recognize_number(_dummy_image()) == 1500

    def test_no_text_returns_none(self):
        assert self._engine("").recognize_number(_dummy_image()) is None

    def test_invalid_text_returns_none(self):
        assert self._engine("abc").recognize_number(_dummy_image()) is None

    def test_whitespace_stripped(self):
        assert self._engine("  99  ").recognize_number(_dummy_image()) == 99

    def test_zero(self):
        assert self._engine("0").recognize_number(_dummy_image()) == 0


# ─────────────────────────────────────────────
# OCREngine.recognize_ship_name
# ─────────────────────────────────────────────


class TestRecognizeShipName:
    CANDIDATES = ["叢雲", "白雪", "初雪", "深雪"]

    def _engine(self, text: str) -> MockOCREngine:
        return MockOCREngine([OCRResult(text=text, confidence=0.85)])

    def test_exact_recognition(self):
        result = self._engine("白雪").recognize_ship_name(_dummy_image(), self.CANDIDATES)
        assert result == "白雪"

    def test_fuzzy_recognition_one_off(self):
        result = self._engine("白霄").recognize_ship_name(_dummy_image(), self.CANDIDATES)
        assert result == "白雪"

    def test_empty_text_returns_none(self):
        result = self._engine("").recognize_ship_name(_dummy_image(), self.CANDIDATES)
        assert result is None

    def test_no_match_within_threshold_returns_none(self):
        result = self._engine("完全无关文字").recognize_ship_name(
            _dummy_image(), self.CANDIDATES, threshold=1
        )
        assert result is None

    def test_empty_candidates_returns_none(self):
        result = self._engine("白雪").recognize_ship_name(_dummy_image(), [])
        assert result is None


# ─────────────────────────────────────────────
# OCREngine.recognize_ship_names  (plural)
# ─────────────────────────────────────────────


class TestRecognizeShipNames:
    CANDIDATES = ["雪风", "时雨", "由良", "爱宕", "高雄"]

    def _engine(self, *texts: str) -> MockOCREngine:
        """构造返回多个文本结果的 MockOCREngine。"""
        return MockOCREngine([
            OCRResult(text=t, confidence=0.85) for t in texts
        ])

    def test_single_exact_match(self):
        result = self._engine("雪风").recognize_ship_names(_dummy_image(), self.CANDIDATES)
        assert result == ["雪风"]

    def test_multi_exact_match_preserves_order(self):
        result = self._engine("时雨", "由良", "雪风").recognize_ship_names(
            _dummy_image(), self.CANDIDATES
        )
        assert result == ["时雨", "由良", "雪风"]

    def test_fuzzy_correction(self):
        # OCR 误识别一个字
        result = self._engine("雪凤").recognize_ship_names(_dummy_image(), self.CANDIDATES)
        assert result == ["雪风"]

    def test_deduplication(self):
        # 同一艘船被识别两次，去重
        result = self._engine("雪风", "雪凤").recognize_ship_names(
            _dummy_image(), self.CANDIDATES
        )
        assert result == ["雪风"]

    def test_unmatched_text_silently_skipped_without_max_threshold(self):
        # 无关文字，不设 max_threshold 时静默跳过
        result = self._engine("标题文字", "雪风").recognize_ship_names(
            _dummy_image(), self.CANDIDATES, threshold=1
        )
        assert result == ["雪风"]

    def test_empty_results_returns_empty_list(self):
        result = self._engine().recognize_ship_names(_dummy_image(), self.CANDIDATES)
        assert result == []

    def test_empty_candidates_returns_empty_list(self):
        result = self._engine("雪风").recognize_ship_names(_dummy_image(), [])
        assert result == []

    def test_empty_text_skipped(self):
        results = [
            OCRResult(text="", confidence=0.9),
            OCRResult(text="  ", confidence=0.9),
            OCRResult(text="雪风", confidence=0.8),
        ]
        engine = MockOCREngine(results)
        result = engine.recognize_ship_names(_dummy_image(), self.CANDIDATES)
        assert result == ["雪风"]

    def test_max_threshold_raises_on_large_distance(self):
        with pytest.raises(ShipNameMismatchError) as exc_info:
            self._engine("完全无关的长文本").recognize_ship_names(
                _dummy_image(), self.CANDIDATES, threshold=2, max_threshold=4
            )
        err = exc_info.value
        assert err.text == "完全无关的长文本"
        assert err.max_threshold == 4
        assert err.distance > 4

    def test_max_threshold_not_triggered_when_distance_within(self):
        # 编辑距离 = 1，threshold=2 → 匹配；max_threshold 无触发
        result = self._engine("雪凤").recognize_ship_names(
            _dummy_image(), self.CANDIDATES, threshold=2, max_threshold=3
        )
        assert result == ["雪风"]

    def test_max_threshold_not_triggers_if_skipped_within_range(self):
        # 无匹配且距离 <= max_threshold → 跳过不抛出
        result = self._engine("zzz").recognize_ship_names(
            _dummy_image(), self.CANDIDATES, threshold=0, max_threshold=100
        )
        # "zzz" 到任意候选距离 <= 100，不抛出，应跳过
        assert isinstance(result, list)

    def test_ship_name_mismatch_error_attributes(self):
        err = ShipNameMismatchError("foo", "bar", 10, 5)
        assert err.text == "foo"
        assert err.best_candidate == "bar"
        assert err.distance == 10
        assert err.max_threshold == 5
        assert "foo" in str(err)
        assert "bar" in str(err)


# ─────────────────────────────────────────────
# OCREngine.create
# ─────────────────────────────────────────────


class TestOCREngineCreate:
    def test_invalid_engine_raises(self):
        with pytest.raises(ValueError, match="不支持的 OCR 引擎"):
            OCREngine.create("not_a_real_engine")

    def test_easyocr_import_error_propagates(self):
        """EasyOCR/PaddleOCR 未安装时抛出 ImportError（由真实引擎初始化触发）。"""
        import importlib.util

        if importlib.util.find_spec("easyocr") is None:
            with pytest.raises(ImportError):
                OCREngine.create("easyocr")

    def test_paddleocr_import_error_propagates(self):
        import importlib.util

        if importlib.util.find_spec("paddleocr") is None:
            with pytest.raises(ImportError):
                OCREngine.create("paddleocr")
