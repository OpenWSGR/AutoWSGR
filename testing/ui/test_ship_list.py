"""测试选船列表的等级 OCR 文本解析。"""

from unittest.mock import MagicMock

import numpy as np
import pytest

from autowsgr.ui.utils.ship_list import (
    _parse_level_with_status,
    _probe_level_near_name,
    locate_ship_rows,
    read_ship_levels,
)
from autowsgr.vision import OCRResult
from autowsgr.vision.ocr_rules import set_user_ship_name_aliases


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
    ],
)
def test_level_parser_accepts_two_ambiguous_digits(text: str, expected: int):
    assert _parse_level_with_status(text) == (expected, False)


def test_level_parser_retries_when_more_than_two_digits_are_ambiguous():
    assert _parse_level_with_status('LV.IIo44') == (None, True)


def _probe_with_binary_results(results: list[OCRResult]) -> int | None:
    ocr = MagicMock()
    ocr.recognize.side_effect = [[], results]
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


def test_read_ship_levels_pairs_original_level_with_upscaled_name(
    monkeypatch: pytest.MonkeyPatch,
):
    screen = _single_row_screen(monkeypatch)
    ocr = MagicMock()
    ocr.recognize.side_effect = [
        [OCRResult(text='Lv.110', confidence=0.99, bbox=(550, 2, 650, 18))],
        [OCRResult(text='火力', confidence=0.9, bbox=(1100, 4, 1300, 36))],
    ]

    assert read_ship_levels(ocr, screen) == [('火力', 110)]
    assert ocr.recognize.call_count == 2


def test_read_ship_levels_applies_alias_before_level_pairing(
    monkeypatch: pytest.MonkeyPatch,
):
    screen = _single_row_screen(monkeypatch)
    ocr = MagicMock()
    ocr.recognize.return_value = [
        OCRResult(text='希尔德布兰德', confidence=0.99, bbox=(200, 2, 320, 18)),
        OCRResult(text='Lv.110', confidence=0.99, bbox=(330, 2, 390, 18)),
    ]
    set_user_ship_name_aliases({'希尔德布兰德': 'AIII'})

    found = read_ship_levels(ocr, screen)

    assert found == [('AIII', 110)]
    assert ocr.recognize.call_count == 1


def test_read_ship_levels_includes_card_position_for_binding(
    monkeypatch: pytest.MonkeyPatch,
):
    screen = _single_row_screen(monkeypatch)
    ocr = MagicMock()
    ocr.recognize.return_value = [
        OCRResult(text='昆西', confidence=0.99, bbox=(200, 2, 300, 18)),
        OCRResult(text='Lv.110', confidence=0.99, bbox=(240, 2, 300, 18)),
    ]

    found = read_ship_levels(
        ocr,
        screen,
        deduplicate_by_name=False,
        include_row_key=True,
    )

    assert found == [
        (
            '昆西',
            110,
            pytest.approx(250 / 1280),
            pytest.approx(round(110 / 720, 4)),
        )
    ]
