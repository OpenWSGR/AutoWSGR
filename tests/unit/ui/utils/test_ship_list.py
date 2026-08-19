"""测试选船列表的等级 OCR 文本解析。"""

from unittest.mock import MagicMock

import numpy as np
import pytest

from autowsgr.ui.utils.ship_list import (
    LevelOCRRetryNeededError,
    _center_x,
    _coerce_level_digits,
    _noise_char_count,
    _parse_level,
    _parse_level_with_status,
    _probe_level_near_name,
    locate_ship_rows,
    read_ship_level_at_card,
    read_ship_levels,
)
from autowsgr.vision import OCREngine, OCRResult
from autowsgr.vision.ocr import EasyOCREngine
from autowsgr.vision.ocr_rules import EasyOCRProfile, set_user_ship_name_aliases


@pytest.fixture(autouse=True)
def _reset_ship_name_aliases():
    set_user_ship_name_aliases({})
    yield
    set_user_ship_name_aliases({})


@pytest.mark.parametrize(
    ('text', 'expected'),
    [
        ('LV.Il0', 110),
        ('LV.ll0', 110),
        ('LVII04', 110),
        ('LVIo4', 104),
        ('L.1', 1),
        ('L.1I0', 110),
        ('L1.110', 110),
    ],
)
def test_level_parser_accepts_two_ambiguous_digits(text: str, expected: int):
    assert _parse_level_with_status(text) == (expected, False)


def test_level_parser_retries_when_more_than_two_digits_are_ambiguous():
    assert _parse_level_with_status('LV.IIo44') == (None, True)


def _probe_with_binary_results(results: list[OCRResult]) -> int | None:
    ocr = MagicMock(spec=EasyOCREngine)
    ocr.recognize_line.return_value = results
    screen = np.zeros((720, 1280, 3), dtype=np.uint8)
    return _probe_level_near_name(
        ocr,
        screen,
        y_start=335,
        y_end=373,
        name_x=262,
        max_x=1048,
    )


def test_level_probe_combines_split_label_and_high_confidence_digits():
    results = [
        OCRResult(text='1VLII', confidence=0.206),
        OCRResult(text='110', confidence=0.9998),
    ]
    assert _probe_with_binary_results(results) == 110


@pytest.mark.parametrize('text', ['110', '.110'])
def test_level_probe_accepts_high_confidence_three_digit_level_without_label(text: str):
    assert _probe_with_binary_results([OCRResult(text=text, confidence=0.99)]) == 110


@pytest.mark.parametrize(('text', 'expected'), [('99', 99), ('Il0', 110)])
def test_level_probe_accepts_high_confidence_digits_without_label(
    text: str,
    expected: int,
):
    assert _probe_with_binary_results([OCRResult(text=text, confidence=0.99)]) == expected


def test_level_probe_rejects_low_confidence_split_level():
    results = [
        OCRResult(text='Lv.', confidence=0.4),
        OCRResult(text='110', confidence=0.8),
    ]
    assert _probe_with_binary_results(results) is None


def test_level_probe_rejects_split_level_above_maximum():
    results = [
        OCRResult(text='Lv.', confidence=0.4),
        OCRResult(text='217', confidence=0.99),
    ]
    assert _probe_with_binary_results(results) is None


def test_level_probe_uses_x2_x3_x4_ordered_fallback():
    ocr = MagicMock(spec=EasyOCREngine)
    ocr.recognize_line.side_effect = [
        [],
        [],
        [OCRResult(text='LV.110', confidence=0.99)],
    ]
    screen = np.zeros((720, 1280, 3), dtype=np.uint8)

    level = _probe_level_near_name(
        ocr,
        screen,
        y_start=335,
        y_end=373,
        name_x=262,
        max_x=1048,
    )

    assert level == 110
    assert ocr.recognize_line.call_count == 3
    assert [call.args[0].shape for call in ocr.recognize_line.call_args_list] == [
        (36, 120, 3),
        (54, 180, 3),
        (72, 240, 3),
    ]
    assert all(
        call.kwargs['easyocr_profile'] is EasyOCRProfile.SHIP_POOL_LEVEL
        for call in ocr.recognize_line.call_args_list
    )


def test_level_probe_stops_after_first_valid_scale():
    ocr = MagicMock(spec=EasyOCREngine)
    ocr.recognize_line.side_effect = [
        [OCRResult(text='LV.1', confidence=0.99)],
        [OCRResult(text='LV.110', confidence=0.99)],
    ]
    screen = np.zeros((720, 1280, 3), dtype=np.uint8)

    level = _probe_level_near_name(
        ocr,
        screen,
        y_start=335,
        y_end=373,
        name_x=262,
        max_x=1048,
    )

    assert level == 1
    assert ocr.recognize_line.call_count == 1
    assert ocr.recognize_line.call_args.args[0].shape == (36, 120, 3)


def test_level_probe_binarizes_easyocr_input():
    ocr = MagicMock(spec=EasyOCREngine)
    ocr.recognize_line.return_value = [OCRResult(text='LV.110', confidence=0.99)]
    screen = np.zeros((720, 1280, 3), dtype=np.uint8)
    screen[:, :, 0] = np.arange(1280, dtype=np.uint16) % 256
    screen[:, :, 1] = 40
    screen[:, :, 2] = 180

    level = _probe_level_near_name(
        ocr,
        screen,
        y_start=335,
        y_end=373,
        name_x=262,
        max_x=1048,
    )

    prepared = ocr.recognize_line.call_args.args[0]
    assert level == 110
    assert set(np.unique(prepared)).issubset({0, 255})
    assert np.array_equal(prepared[:, :, 0], prepared[:, :, 1])
    assert np.array_equal(prepared[:, :, 1], prepared[:, :, 2])


def test_level_probe_keeps_non_easyocr_input_unbinarized():
    ocr = MagicMock(spec=OCREngine)
    ocr.recognize_line.return_value = [OCRResult(text='LV.110', confidence=0.99)]
    screen = np.zeros((720, 1280, 3), dtype=np.uint8)
    screen[:, :, 0] = np.arange(1280, dtype=np.uint16) % 256
    screen[:, :, 1] = 40
    screen[:, :, 2] = 180

    level = _probe_level_near_name(
        ocr,
        screen,
        y_start=335,
        y_end=373,
        name_x=262,
        max_x=1048,
    )

    prepared = ocr.recognize_line.call_args.args[0]
    assert level == 110
    assert not set(np.unique(prepared)).issubset({0, 255})
    assert not np.array_equal(prepared[:, :, 0], prepared[:, :, 1])


def test_level_parser_rejects_value_above_game_maximum():
    assert _parse_level_with_status('LV.200') == (None, False)


def _single_row_screen(monkeypatch: pytest.MonkeyPatch) -> np.ndarray:
    dll = MagicMock()
    dll.locate.return_value = [(100, 120)]
    monkeypatch.setattr(
        'autowsgr.ui.utils.ship_list.get_api_dll',
        lambda: dll,
    )
    monkeypatch.setattr('urllib.request.urlopen', MagicMock())
    return np.zeros((720, 1280, 3), dtype=np.uint8)


def test_locate_ship_rows_uses_upscaled_fallback_and_restores_coordinates(
    monkeypatch: pytest.MonkeyPatch,
):
    screen = _single_row_screen(monkeypatch)
    ocr = MagicMock()
    ocr.recognize.side_effect = [
        [OCRResult(text='NOT_A_SHIP', confidence=0.9, bbox=(100, 2, 180, 18))],
        [OCRResult(text='火力', confidence=0.9, bbox=(400, 4, 480, 36))],
    ]

    found = locate_ship_rows(ocr, screen)

    assert found == [
        ('火力', pytest.approx(220 / 1280), pytest.approx(109 / 720)),
    ]
    assert ocr.recognize.call_count == 2
    assert ocr.recognize.call_args_list[0].args[0].shape == (22, 1048, 3)
    assert ocr.recognize.call_args_list[1].args[0].shape == (44, 2096, 3)


def test_locate_ship_rows_applies_user_ship_name_alias(
    monkeypatch: pytest.MonkeyPatch,
):
    screen = _single_row_screen(monkeypatch)
    ocr = MagicMock()
    ocr.recognize.return_value = [
        OCRResult(text='契卡洛夫', confidence=0.99, bbox=(200, 2, 300, 18)),
    ]
    set_user_ship_name_aliases({'契卡洛夫': '85工程'})

    found = locate_ship_rows(ocr, screen)

    assert found == [
        ('85工程', pytest.approx(250 / 1280), pytest.approx(109 / 720)),
    ]
    assert ocr.recognize.call_count == 1


def test_read_ship_level_at_card_converts_relative_card_position(
    monkeypatch: pytest.MonkeyPatch,
):
    screen = np.zeros((720, 1280, 3), dtype=np.uint8)
    ocr = MagicMock()
    probe = MagicMock(return_value=101)
    monkeypatch.setattr('autowsgr.ui.utils.ship_list._probe_level_near_name', probe)

    level = read_ship_level_at_card(
        ocr,
        screen,
        card_x=0.25,
        row_key=0.5,
    )

    assert level == 101
    probe.assert_called_once_with(
        ocr,
        screen,
        y_start=360,
        y_end=360,
        name_x=320,
        max_x=1048,
    )


def test_read_ship_levels_probes_level_from_upscaled_name_position(
    monkeypatch: pytest.MonkeyPatch,
):
    screen = _single_row_screen(monkeypatch)
    ocr = MagicMock()
    ocr.recognize.side_effect = [
        [OCRResult(text='Lv.110', confidence=0.99, bbox=(550, 2, 650, 18))],
        [OCRResult(text='火力', confidence=0.9, bbox=(1100, 4, 1300, 36))],
    ]
    probe = MagicMock(return_value=103)
    monkeypatch.setattr('autowsgr.ui.utils.ship_list._probe_level_near_name', probe)

    assert read_ship_levels(ocr, screen) == [('火力', 103)]
    assert ocr.recognize.call_count == 2
    probe.assert_called_once_with(
        ocr,
        screen,
        y_start=99,
        y_end=121,
        name_x=600,
        max_x=1048,
    )


def test_read_ship_levels_applies_alias_before_card_level_probe(
    monkeypatch: pytest.MonkeyPatch,
):
    screen = _single_row_screen(monkeypatch)
    ocr = MagicMock()
    ocr.recognize.return_value = [
        OCRResult(text='希尔德布兰德', confidence=0.99, bbox=(200, 2, 320, 18)),
        OCRResult(text='Lv.110', confidence=0.99, bbox=(330, 2, 390, 18)),
    ]
    set_user_ship_name_aliases({'希尔德布兰德': 'AIII'})
    probe = MagicMock(return_value=101)
    monkeypatch.setattr('autowsgr.ui.utils.ship_list._probe_level_near_name', probe)

    found = read_ship_levels(ocr, screen)

    assert found == [('AIII', 101)]
    assert ocr.recognize.call_count == 1
    probe.assert_called_once_with(
        ocr,
        screen,
        y_start=99,
        y_end=121,
        name_x=260,
        max_x=1048,
    )


def test_read_ship_levels_includes_card_position_for_binding(
    monkeypatch: pytest.MonkeyPatch,
):
    screen = _single_row_screen(monkeypatch)
    ocr = MagicMock()
    ocr.recognize.return_value = [
        OCRResult(text='昆西', confidence=0.99, bbox=(200, 2, 300, 18)),
        OCRResult(text='Lv.110', confidence=0.99, bbox=(240, 2, 300, 18)),
    ]
    probe = MagicMock(return_value=1)
    monkeypatch.setattr('autowsgr.ui.utils.ship_list._probe_level_near_name', probe)

    found = read_ship_levels(
        ocr,
        screen,
        deduplicate_by_name=False,
        include_row_key=True,
    )

    assert found == [
        (
            '昆西',
            1,
            pytest.approx(250 / 1280),
            pytest.approx(round(110 / 720, 4)),
        )
    ]
    probe.assert_called_once_with(
        ocr,
        screen,
        y_start=99,
        y_end=121,
        name_x=250,
        max_x=1048,
    )


# ==============================================================
# 保留自 tests/unit 结构重构：ship_list 内部辅助函数测试
# ==============================================================


class TestNoiseCharCount:
    def test_all_noise_letters(self) -> None:
        # I, L, l, O, o are noise; 1 and 0 are valid digits and not counted.
        assert _noise_char_count('ILl1Oo0') == 5

    def test_no_noise(self) -> None:
        # 'b' 与 '8'/'6' 形似，main 实现将其计入噪声
        assert _noise_char_count('ac123') == 0
        assert _noise_char_count('abc123') == 1

    def test_empty(self) -> None:
        assert _noise_char_count('') == 0


class TestCoerceLevelDigits:
    def test_simple_three_digit(self) -> None:
        assert _coerce_level_digits('110') == 110

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
        assert _parse_level('Lv.110') == 110

    def test_no_level(self) -> None:
        assert _parse_level('abc') is None


class TestParseLevelWithStatus:
    def test_standard_level(self) -> None:
        assert _parse_level_with_status('Lv.110') == (110, False)

    def test_noisy_excessive_noise(self) -> None:
        # 'IL' 翻译为 11（合法等级），不再判为噪声
        assert _parse_level_with_status('Lv.IL') == (11, False)

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
