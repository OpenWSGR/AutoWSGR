"""Tests for autowsgr.vision.ocr — OCR engine abstractions and helpers."""

from __future__ import annotations

from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from autowsgr.constants import (
    SHIPNAME_GROUPS,
    SHIPNAMES,
    get_ship_name_variants,
    normalize_ship_name,
    ship_name_identity,
)
from autowsgr.vision import OCREngine, OCRResult, ShipNameMismatchError
from autowsgr.vision.ocr import (
    EasyOCREngine,
    FastOCREngine,
    _fuzzy_match,
    apply_ship_patches,
    set_ship_name_match_confidence,
)
from autowsgr.vision.ocr_rules import (
    LEVEL_OCR_ALLOWLIST,
    EasyOCRProfile,
    FastOCRProfile,
    get_easyocr_params,
    get_fastocr_params,
    get_user_ship_name_aliases,
    normalize_level_digits,
    set_user_ship_name_aliases,
    set_user_ship_name_corrections,
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
        _image: np.ndarray,
        _allowlist: str = '',
    ) -> list[OCRResult]:
        return self._results


def _dummy_image() -> np.ndarray:
    return np.zeros((10, 10, 3), dtype=np.uint8)


# ─────────────────────────────────────────────
# 等级 OCR 引擎
# ─────────────────────────────────────────────


class TestLevelOCREngines:
    def test_easyocr_disables_cpu_quantization(self):
        with (
            patch('autowsgr.vision.easyocr_models_checker.ensure_models'),
            patch('autowsgr.vision.ocr.easyocr.Reader') as reader,
        ):
            EasyOCREngine(gpu=False)

        reader.assert_called_once_with(
            ['ch_sim', 'en'],
            gpu=False,
            quantize=False,
        )

    def test_easyocr_line_uses_calibrated_parameters(self):
        reader = MagicMock()
        reader.recognize.return_value = [
            (
                [[0, 0], [9, 0], [9, 9], [0, 9]],
                'LV.110',
                0.99,
            ),
        ]
        engine = EasyOCREngine.__new__(EasyOCREngine)
        engine._reader = reader

        results = engine.recognize_line(
            _dummy_image(),
            easyocr_profile=EasyOCRProfile.FLEET_SHIP_LEVEL,
        )

        assert results == [
            OCRResult(
                text='LV.110',
                confidence=pytest.approx(0.99),
                bbox=(0, 0, 9, 9),
            ),
        ]
        assert reader.recognize.call_args.kwargs == {
            'decoder': 'greedy',
            'allowlist': LEVEL_OCR_ALLOWLIST,
            'detail': 1,
            'contrast_ths': 1.0,
            'adjust_contrast': 1.0,
        }

    @pytest.mark.parametrize('profile', list(EasyOCRProfile))
    def test_easyocr_parameter_profiles_are_registered(self, profile: EasyOCRProfile):
        params = get_easyocr_params(profile)

        if profile in {
            EasyOCRProfile.FLEET_SHIP_LEVEL,
            EasyOCRProfile.SHIP_POOL_LEVEL,
        }:
            assert params.allowlist == LEVEL_OCR_ALLOWLIST
        assert params.decoder == 'greedy'
        assert params.contrast_ths == 1.0
        assert params.adjust_contrast == 1.0

    def test_easyocr_unknown_parameter_profile_is_rejected(self):
        with pytest.raises(ValueError, match='未知的 EasyOCR 参数配置档案'):
            get_easyocr_params('unknown')

    @pytest.mark.parametrize('profile', list(FastOCRProfile))
    def test_fastocr_parameter_profiles_are_registered(self, profile: FastOCRProfile):
        params = get_fastocr_params(profile)

        assert params.only_rec is (profile is FastOCRProfile.SINGLE_LINE)

    def test_fastocr_unknown_parameter_profile_is_rejected(self):
        with pytest.raises(ValueError, match='未知的 FastOCR 参数配置档案'):
            get_fastocr_params('unknown')

    def test_fastocr_full_recognition_uses_detection(self):
        detail = SimpleNamespace(nodes=[])
        job = MagicMock(succeeded=True)
        job.get.return_value = detail
        tasker = MagicMock()
        tasker.post_recognition.return_value.wait.return_value = job

        options = MagicMock(return_value='options')
        engine = FastOCREngine.__new__(FastOCREngine)
        engine._tasker = tasker
        engine._recognition_type = 'ocr'
        engine._ocr_options_type = options
        engine._threshold = 0.3

        assert engine.recognize(_dummy_image()) == []
        options.assert_called_once_with(
            only_rec=False,
            threshold=0.3,
        )

    def test_fastocr_line_uses_profile_allowlist(self):
        raw_result = SimpleNamespace(
            text='LV.1D3@',
            score=0.98,
            box=[1, 2, 10, 4],
        )
        recognition = SimpleNamespace(filtered_results=[raw_result])
        detail = SimpleNamespace(
            nodes=[SimpleNamespace(recognition=recognition)],
        )
        job = MagicMock(succeeded=True)
        job.get.return_value = detail
        tasker = MagicMock()
        tasker.post_recognition.return_value.wait.return_value = job

        options = MagicMock(return_value='options')
        engine = FastOCREngine.__new__(FastOCREngine)
        engine._tasker = tasker
        engine._recognition_type = 'ocr'
        engine._ocr_options_type = options
        engine._threshold = 0.3

        results = engine.recognize_line(
            _dummy_image(),
            easyocr_profile=EasyOCRProfile.FLEET_SHIP_LEVEL,
        )

        assert results == [
            OCRResult(
                text='LV.1D3',
                confidence=pytest.approx(0.98),
                bbox=(1, 2, 11, 6),
            ),
        ]
        options.assert_called_once_with(
            only_rec=True,
            threshold=0.3,
        )


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        ('1I', '11'),
        ('1D3', '103'),
        ('S', '5'),
        ('B', '8'),
    ],
)
def test_normalize_level_digits_uses_shared_corrections(
    raw: str,
    expected: str,
):
    assert normalize_level_digits(raw) == expected


# ─────────────────────────────────────────────
# OCRResult
# ─────────────────────────────────────────────


class TestOCRResult:
    def test_immutable(self):
        r = OCRResult(text='x', confidence=0.5)
        with pytest.raises((AttributeError, TypeError)):
            r.text = 'y'  # type: ignore[misc]


# ─────────────────────────────────────────────
# _fuzzy_match
# ─────────────────────────────────────────────


class TestFuzzyMatch:
    SHIP_NAMES: ClassVar[list[str]] = ['雪风', '时雨', '由良', '爱宕', '高雄']

    def test_exact_match(self):
        assert _fuzzy_match('雪风', self.SHIP_NAMES) == '雪风'

    def test_one_char_off(self):
        # OCR 误识别一个字
        assert _fuzzy_match('雪凤', self.SHIP_NAMES) == '雪风'

    def test_no_match_exceeds_threshold(self):
        result = _fuzzy_match('全然不同', self.SHIP_NAMES, threshold=1)
        assert result is None

    def test_empty_candidates(self):
        assert _fuzzy_match('雪风', []) is None

    def test_threshold_zero_requires_exact(self):
        assert _fuzzy_match('雪凤', self.SHIP_NAMES, threshold=0) is None
        assert _fuzzy_match('雪风', self.SHIP_NAMES, threshold=0) == '雪风'

    def test_picks_closest(self):
        candidates = ['abc', 'xyz']
        # "abx" → "abc" distance=1, "xyz" distance=2
        result = _fuzzy_match('abx', candidates, threshold=3)
        assert result == 'abc'

    def test_default_threshold_is_3(self):
        # distance 3 should match
        result = _fuzzy_match('abcd', ['wxyz'], threshold=3)
        assert result is None  # distance = 4 > 3
        result = _fuzzy_match('abcd', ['abce'], threshold=3)
        assert result == 'abce'  # distance = 1


# ─────────────────────────────────────────────
# OCREngine.recognize_single
# ─────────────────────────────────────────────


class TestRecognizeSingle:
    def test_returns_highest_confidence(self):
        engine = MockOCREngine(
            [
                OCRResult(text='low', confidence=0.4),
                OCRResult(text='high', confidence=0.9),
                OCRResult(text='mid', confidence=0.6),
            ]
        )
        result = engine.recognize_single(_dummy_image())
        assert result.text == 'high'

    def test_empty_results_returns_empty(self):
        engine = MockOCREngine([])
        result = engine.recognize_single(_dummy_image())
        assert result.text == ''
        assert result.confidence == pytest.approx(0.0)

    def test_single_result_returned(self):
        r = OCRResult(text='42', confidence=0.95)
        engine = MockOCREngine([r])
        result = engine.recognize_single(_dummy_image())
        assert result.text == '42'


# ─────────────────────────────────────────────
# OCREngine.recognize_number
# ─────────────────────────────────────────────


class TestRecognizeNumber:
    def _engine(self, text: str) -> MockOCREngine:
        return MockOCREngine([OCRResult(text=text, confidence=0.9)])

    def test_plain_integer(self):
        assert self._engine('123').recognize_number(_dummy_image()) == 123

    def test_k_suffix_lowercase(self):
        assert self._engine('5k').recognize_number(_dummy_image()) == 5000

    def test_k_suffix_uppercase(self):
        assert self._engine('10K').recognize_number(_dummy_image()) == 10000

    def test_m_suffix(self):
        assert self._engine('2M').recognize_number(_dummy_image()) == 2_000_000

    def test_decimal_with_k(self):
        assert self._engine('1.5K').recognize_number(_dummy_image()) == 1500

    def test_no_text_returns_none(self):
        assert self._engine('').recognize_number(_dummy_image()) is None

    def test_invalid_text_returns_none(self):
        assert self._engine('abc').recognize_number(_dummy_image()) is None

    def test_whitespace_stripped(self):
        assert self._engine('  99  ').recognize_number(_dummy_image()) == 99

    def test_zero(self):
        assert self._engine('0').recognize_number(_dummy_image()) == 0


# ─────────────────────────────────────────────
# OCREngine.recognize_ship_name
# ─────────────────────────────────────────────


class TestRecognizeShipName:
    CANDIDATES: ClassVar[list[str]] = ['叢雲', '白雪', '初雪', '深雪']

    def _engine(self, text: str) -> MockOCREngine:
        return MockOCREngine([OCRResult(text=text, confidence=0.85)])

    def test_exact_recognition(self):
        result = self._engine('白雪').recognize_ship_name(_dummy_image(), self.CANDIDATES)
        assert result == '白雪'

    def test_fuzzy_recognition_one_off(self):
        result = self._engine('白霄').recognize_ship_name(_dummy_image(), self.CANDIDATES)
        assert result == '白雪'

    def test_empty_text_returns_none(self):
        result = self._engine('').recognize_ship_name(_dummy_image(), self.CANDIDATES)
        assert result is None

    def test_no_match_within_threshold_returns_none(self):
        result = self._engine('完全无关文字').recognize_ship_name(
            _dummy_image(), self.CANDIDATES, threshold=1
        )
        assert result is None

    def test_empty_candidates_returns_none(self):
        result = self._engine('白雪').recognize_ship_name(_dummy_image(), [])
        assert result is None


# ─────────────────────────────────────────────
# OCREngine.recognize_ship_names  (plural)
# ─────────────────────────────────────────────


class TestRecognizeShipNames:
    CANDIDATES: ClassVar[list[str]] = ['雪风', '时雨', '由良', '爱宕', '高雄']

    def _engine(self, *texts: str) -> MockOCREngine:
        """构造返回多个文本结果的 MockOCREngine。"""
        return MockOCREngine([OCRResult(text=t, confidence=0.85) for t in texts])

    def test_single_exact_match(self):
        result = self._engine('雪风').recognize_ship_names(_dummy_image(), self.CANDIDATES)
        assert result == ['雪风']

    def test_multi_exact_match_preserves_order(self):
        result = self._engine('时雨', '由良', '雪风').recognize_ship_names(
            _dummy_image(), self.CANDIDATES
        )
        assert result == ['时雨', '由良', '雪风']

    def test_fuzzy_correction(self):
        # OCR 误识别一个字
        result = self._engine('雪凤').recognize_ship_names(_dummy_image(), self.CANDIDATES)
        assert result == ['雪风']

    def test_deduplication(self):
        # 同一艘船被识别两次，去重
        result = self._engine('雪风', '雪凤').recognize_ship_names(_dummy_image(), self.CANDIDATES)
        assert result == ['雪风']

    def test_unmatched_text_silently_skipped_without_max_threshold(self):
        # 无关文字，不设 max_threshold 时静默跳过
        result = self._engine('标题文字', '雪风').recognize_ship_names(
            _dummy_image(), self.CANDIDATES, threshold=1
        )
        assert result == ['雪风']

    def test_empty_results_returns_empty_list(self):
        result = self._engine().recognize_ship_names(_dummy_image(), self.CANDIDATES)
        assert result == []

    def test_empty_candidates_returns_empty_list(self):
        result = self._engine('雪风').recognize_ship_names(_dummy_image(), [])
        assert result == []

    def test_empty_text_skipped(self):
        results = [
            OCRResult(text='', confidence=0.9),
            OCRResult(text='  ', confidence=0.9),
            OCRResult(text='雪风', confidence=0.8),
        ]
        engine = MockOCREngine(results)
        result = engine.recognize_ship_names(_dummy_image(), self.CANDIDATES)
        assert result == ['雪风']

    def test_max_threshold_raises_on_large_distance(self):
        with pytest.raises(ShipNameMismatchError) as exc_info:
            self._engine('完全无关的长文本').recognize_ship_names(
                _dummy_image(), self.CANDIDATES, threshold=2, max_threshold=4
            )
        err = exc_info.value
        assert err.text == '完全无关的长文本'
        assert err.max_threshold == 4
        assert err.distance > 4

    def test_max_threshold_not_triggered_when_distance_within(self):
        # 编辑距离 = 1，threshold=2 → 匹配；max_threshold 无触发
        result = self._engine('雪凤').recognize_ship_names(
            _dummy_image(), self.CANDIDATES, threshold=2, max_threshold=3
        )
        assert result == ['雪风']

    def test_max_threshold_not_triggers_if_skipped_within_range(self):
        # 无匹配且距离 <= max_threshold → 跳过不抛出
        result = self._engine('zzz').recognize_ship_names(
            _dummy_image(), self.CANDIDATES, threshold=0, max_threshold=100
        )
        # "zzz" 到任意候选距离 <= 100，不抛出，应跳过
        assert isinstance(result, list)

    def test_ship_name_mismatch_error_attributes(self):
        err = ShipNameMismatchError('foo', 'bar', 10, 5)
        assert err.text == 'foo'
        assert err.best_candidate == 'bar'
        assert err.distance == 10
        assert err.max_threshold == 5
        assert 'foo' in str(err)
        assert 'bar' in str(err)


# ─────────────────────────────────────────────
# OCREngine.create
# ─────────────────────────────────────────────


class TestOCREngineCreate:
    def test_invalid_engine_raises(self):
        with pytest.raises(ValueError, match='不支持的 OCR 引擎'):
            OCREngine.create('not_a_real_engine')

    def test_easyocr_import_error_propagates(self):
        """EasyOCR/PaddleOCR 未安装时抛出 ImportError（由真实引擎初始化触发）。"""
        import importlib.util

        if importlib.util.find_spec('easyocr') is None:
            with pytest.raises(ImportError):
                OCREngine.create('easyocr')

    def test_paddleocr_not_supported(self):
        with pytest.raises(ValueError, match='不支持的 OCR 引擎'):
            OCREngine.create('paddleocr')

    def test_rapidocr_not_supported(self):
        with pytest.raises(ValueError, match='不支持的 OCR 引擎'):
            OCREngine.create('rapidocr')


class TestPoolAwareMatch:
    """测试安全舰名匹配、明确后缀和长舰名片段。"""

    CANDIDATES: ClassVar[list[str]] = [
        '胡德',
        '扶桑',
        '岛风',
        '安德烈亚·多利亚',
        '卡约·杜伊里奥',
        '乌尔里希·冯·胡滕',
        '乌戈里尼·维瓦尔迪',
        'U-96',
        'Z21',
        'K-21',
    ]

    def setup_method(self):
        set_ship_name_match_confidence(0.0)
        set_user_ship_name_aliases({})
        set_user_ship_name_corrections({})

    def teardown_method(self):
        set_ship_name_match_confidence(0.0)
        set_user_ship_name_aliases({})
        set_user_ship_name_corrections({})

    @pytest.mark.parametrize(
        ('raw', 'expected'),
        [
            (None, None),
            ('', None),
            ('  岛风  ', '岛风'),
            ('岛风·改', '岛风'),
            ('飞龙（苍青幻影）', '飞龙'),
        ],
    )
    def test_ship_name_normalization(self, raw: object, expected: str | None):
        assert normalize_ship_name(raw) == expected

    def test_ship_name_normalization_resolves_registered_alias(self):
        set_user_ship_name_aliases({'契卡洛夫': '85工程'})

        assert normalize_ship_name(' 契卡洛夫·改 ') == '85工程'
        assert ship_name_identity('契卡洛夫（自定义）') == ship_name_identity('85工程')

    def test_only_confirmed_cjk_separator_is_corrected(self):
        assert apply_ship_patches('安德烈亚:多利亚') == '安德烈亚·多利亚'
        assert apply_ship_patches('鳟盹') == '鳞鲀'
        assert apply_ship_patches('U/96') == 'U/96'
        assert apply_ship_patches('U:96') == 'U:96'

    def test_user_ship_name_corrections_skip_unknown_targets(self):
        loaded = set_user_ship_name_corrections(
            {
                '用户误识别': '胡德',
                '无效规则': '不存在的舰名',
            },
        )

        assert loaded == 1
        assert apply_ship_patches('用户误识别') == '胡德'
        assert apply_ship_patches('无效规则') == '无效规则'

    def test_user_ship_name_corrections_override_system_rules(self):
        set_user_ship_name_corrections({'鲍鱼': '胡德'})

        assert apply_ship_patches('鲍鱼') == '胡德'

    def test_user_ship_name_aliases_map_display_names_to_standard_names(self):
        loaded = set_user_ship_name_aliases(
            {
                '希尔德布兰德': 'AIII',
                '契卡洛夫': '85工程',
                'U-47·狼群': 'U-47',
                '巴尔的摩·英魂': '巴尔的摩',
            },
        )

        assert loaded == 4
        assert _fuzzy_match(apply_ship_patches('希尔德布兰德'), SHIPNAMES) == 'AIII'
        assert _fuzzy_match(apply_ship_patches('契卡洛夫'), SHIPNAMES) == '85工程'
        assert _fuzzy_match(apply_ship_patches('U-47·狼群'), SHIPNAMES) == 'U-47'
        assert _fuzzy_match(apply_ship_patches('巴尔的摩:英魂'), SHIPNAMES) == '巴尔的摩'

    @pytest.mark.parametrize(
        'aliases',
        [
            {'别名甲': '85工程', '别名乙': '85工程'},
            {'别名乙': '85工程', '别名甲': '85工程'},
        ],
    )
    def test_reverse_alias_lookup_returns_all_aliases_in_stable_order(
        self,
        aliases: dict[str, str],
    ):
        set_user_ship_name_aliases(aliases)

        expected = tuple(sorted(aliases))
        assert get_user_ship_name_aliases('85工程') == expected
        assert get_user_ship_name_aliases(expected[0]) == (expected[0],)

    def test_user_ship_name_is_added_to_the_same_ship_group(self):
        set_user_ship_name_aliases({'契卡洛夫': '85工程'})

        assert SHIPNAME_GROUPS['No.285'] == ['85工程', '契卡洛夫']
        assert get_ship_name_variants('契卡洛夫') == ['85工程', '契卡洛夫']
        assert ship_name_identity('契卡洛夫') == ship_name_identity('85工程')
        assert '契卡洛夫' in SHIPNAMES

    def test_user_ship_name_aliases_participate_in_fuzzy_matching(self):
        set_user_ship_name_aliases({'契卡洛夫': '85工程'})

        assert apply_ship_patches('契卡洛大') == '契卡洛大'
        assert _fuzzy_match('契卡洛大', SHIPNAMES) == '85工程'

    def test_alias_tie_for_same_standard_name_is_not_ambiguous(self):
        set_user_ship_name_aliases(
            {
                '契卡洛夫': '85工程',
                '契卡洛天': '85工程',
            },
        )

        assert _fuzzy_match('契卡洛大', SHIPNAMES) == '85工程'

    def test_alias_tie_for_different_standard_names_is_rejected(self):
        set_user_ship_name_aliases(
            {
                '契卡洛夫': '85工程',
                '契卡洛天': 'AIII',
            },
        )

        assert _fuzzy_match('契卡洛大', SHIPNAMES) is None

    def test_user_ship_name_aliases_skip_invalid_entries(self):
        loaded = set_user_ship_name_aliases(
            {
                '自定义舰名': '不存在的舰名',
                '胡德': '雪风',
            },
        )

        assert loaded == 0
        assert apply_ship_patches('自定义舰名') == '自定义舰名'
        assert apply_ship_patches('胡德') == '胡德'

    def test_short_text_does_not_guess_from_full_ship_pool(self):
        set_ship_name_match_confidence(0.65)
        assert _fuzzy_match('71', SHIPNAMES, threshold=2) is None

    def test_single_character_only_accepts_exact_match(self):
        assert _fuzzy_match('帅', ['晓', '虎'], threshold=3) is None
        assert _fuzzy_match('虎', ['晓', '虎'], threshold=3) == '虎'

    def test_equal_edit_distance_candidates_are_rejected(self):
        assert _fuzzy_match('蜂风', ['雪风', '峰风', '东风'], threshold=2) is None

    def test_duplicate_names_do_not_create_false_ambiguity(self):
        assert _fuzzy_match('胡德', ['胡德', '胡德'], threshold=2) == '胡德'

    def test_short_unique_one_character_error_is_accepted(self):
        assert _fuzzy_match('帅力', ['火力', '胡德'], threshold=3) == '火力'

    def test_custom_suffix_obeys_confidence(self):
        set_ship_name_match_confidence(0.65)
        assert _fuzzy_match('胡德·荣耀', self.CANDIDATES) == '胡德'

        set_ship_name_match_confidence(0.67)
        assert _fuzzy_match('胡德·荣耀', self.CANDIDATES) is None

    def test_symbol_only_difference_is_exact(self):
        set_ship_name_match_confidence(0.65)
        text = apply_ship_patches('安德烈亚:多利亚')
        assert _fuzzy_match(text, self.CANDIDATES, threshold=0) == '安德烈亚·多利亚'

    def test_unregistered_symbol_substitution_is_not_ignored(self):
        set_ship_name_match_confidence(0.65)
        assert _fuzzy_match('U:96', ['U-96'], threshold=0) is None

    def test_four_character_truncation_obeys_confidence(self):
        set_ship_name_match_confidence(0.8)
        assert _fuzzy_match('卡约·杜伊', self.CANDIDATES) == '卡约·杜伊里奥'

        set_ship_name_match_confidence(0.84)
        assert _fuzzy_match('卡约·杜伊', self.CANDIDATES) is None

    def test_short_truncated_prefix_is_rejected(self):
        set_ship_name_match_confidence(0.1)
        assert _fuzzy_match('卡约·', self.CANDIDATES) is None

    def test_one_character_custom_name_is_rejected(self):
        set_ship_name_match_confidence(0.1)
        assert _fuzzy_match('狮·荣耀', ['狮', '哥特雄狮']) is None

    def test_longest_custom_name_prefix_wins(self):
        set_ship_name_match_confidence(0.65)
        assert _fuzzy_match('约克城·荣耀', ['约克', '约克城'], threshold=0) == '约克城'

    def test_ambiguous_truncated_prefix_is_rejected(self):
        set_ship_name_match_confidence(0.1)
        candidates = ['卡约·杜伊里奥', '卡约·杜伊长名']
        assert _fuzzy_match('卡约·杜伊', candidates) is None

    def test_unique_long_name_fragment_matches(self):
        set_ship_name_match_confidence(0.65)
        assert _fuzzy_match('维瓦尔迪', self.CANDIDATES) == '乌戈里尼·维瓦尔迪'
        assert _fuzzy_match('冯·胡滕', self.CANDIDATES) == '乌尔里希·冯·胡滕'

    def test_ambiguous_long_name_fragment_is_rejected(self):
        set_ship_name_match_confidence(0.65)
        candidates = ['乌尔里希·冯·胡滕', '测试舰·冯·胡滕']
        assert _fuzzy_match('冯·胡滕', candidates) is None

    def test_unrelated_text_falls_back_to_edit_distance(self):
        set_ship_name_match_confidence(0.65)
        assert _fuzzy_match('扶桑', self.CANDIDATES, threshold=2) == '扶桑'
        assert _fuzzy_match('战列舰', self.CANDIDATES, threshold=2) is None
