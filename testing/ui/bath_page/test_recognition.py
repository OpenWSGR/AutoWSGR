"""浴室卡片边框、点击坐标及修理时间识别的离线回归。"""

from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from autowsgr.ui.bath_page.recognition import _ocr_card, recognize_repair_cards
from autowsgr.vision.ocr import OCRResult


@pytest.mark.parametrize('size', [(1280, 720), (960, 540), (1920, 1080)])
def test_same_name_on_separate_bordered_cards(size: tuple[int, int]) -> None:
    screen = np.zeros((720, 1280, 3), np.uint8)
    # 整块面板也有边框；卡片应保留，两张卡片各自的内外沿只计一次。
    for start, end in [
        ((40, 30), (700, 650)),
        ((98, 64), (271, 548)),
        ((308, 64), (481, 548)),
    ]:
        cv2.rectangle(screen, start, end, (255, 255, 255), 3)
    name = OCRResult('胡德', 1, (10, 125, 60, 140))
    duration = OCRResult('00:17:59', 1, (0, 0, 80, 12))
    ocr = MagicMock()
    ocr.recognize.side_effect = [[name], [duration], [name], [duration]]

    cards = recognize_repair_cards(cv2.resize(screen, size), ocr)

    assert ocr.recognize.call_count == 4
    assert [(c.name, c.repair_time) for c in cards] == [('胡德', '00:17:59')] * 2
    for card, center in zip(cards, [185, 395], strict=True):
        assert card.position == pytest.approx((center / 1280, 0.5), abs=1 / 1280)


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        ('001759', '00:17:59'),
        ('00,17,59', '00:17:59'),
        ('耗时：00；17.59', '00:17:59'),
        ('00：00：00', '00:00:00'),
        ('00:60:00', ''),
        ('001760', ''),
        ('00,1,759', ''),
        ('0017590', ''),
        ('编号001759', ''),
        ('00:17:59级', ''),
        ('', ''),
    ],
)
def test_card_accepts_only_complete_time(raw: str, expected: str) -> None:
    ocr = MagicMock()
    ocr.recognize.side_effect = [
        [OCRResult('胡德', 1, (10, 125, 60, 140))],
        [OCRResult(raw, 1, (0, 0, 80, 12))],
    ]
    card = _ocr_card(np.zeros((480, 174, 3), np.uint8), ocr, 100, 174, 1280)
    assert card is not None
    assert (card.name, card.repair_time) == ('胡德', expected)
