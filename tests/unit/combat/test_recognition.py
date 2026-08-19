"""测试 autowsgr.combat.recognition。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from autowsgr.combat import recognition
from autowsgr.combat.recognition import (
    ShipDropResult,
    detect_mvp,
    recognize_enemy_formation,
    recognize_enemy_ships,
    recognize_ship_drop,
)


class TestRecognizeEnemyShips:
    """recognize_enemy_ships 测试。"""

    def test_fight_mode(self) -> None:
        screen = np.zeros((1080, 1920, 3), dtype=np.uint8)
        dll = MagicMock()
        dll.recognize_enemy.return_value = 'BB CV DD DD DD NO'
        with patch('autowsgr.combat.recognition.get_api_dll', return_value=dll):
            result = recognize_enemy_ships(screen, mode='fight')
        assert result == {'BB': 1, 'CV': 1, 'DD': 3, 'ALL': 5}

    def test_exercise_mode(self) -> None:
        screen = np.zeros((1080, 1920, 3), dtype=np.uint8)
        dll = MagicMock()
        dll.recognize_enemy.return_value = 'NO NO NO BC BC BC'
        with patch('autowsgr.combat.recognition.get_api_dll', return_value=dll):
            result = recognize_enemy_ships(screen, mode='exercise')
        assert result == {'BC': 3, 'ALL': 3}

    def test_invalid_mode(self) -> None:
        with pytest.raises(ValueError, match='不支持的模式'):
            recognize_enemy_ships(np.zeros((10, 10, 3)), mode='invalid')

    def test_all_no_ship(self) -> None:
        screen = np.zeros((1080, 1920, 3), dtype=np.uint8)
        dll = MagicMock()
        dll.recognize_enemy.return_value = 'NO NO NO NO NO NO'
        with patch('autowsgr.combat.recognition.get_api_dll', return_value=dll):
            result = recognize_enemy_ships(screen)
        assert result == {'ALL': 0}


class TestRecognizeEnemyFormation:
    """recognize_enemy_formation 测试。"""

    def test_exact_match(self) -> None:
        screen = np.zeros((1080, 1920, 3), dtype=np.uint8)
        ocr = MagicMock()
        ocr.recognize_single.return_value = MagicMock(text='单纵阵')
        mock_roi = MagicMock()
        mock_roi.crop.return_value = np.zeros((50, 50, 3), dtype=np.uint8)
        with patch.object(recognition, '_FORMATION_ROI', mock_roi):
            result = recognize_enemy_formation(screen, ocr)
        assert result == '单纵阵'

    def test_fuzzy_match(self) -> None:
        screen = np.zeros((1080, 1920, 3), dtype=np.uint8)
        ocr = MagicMock()
        ocr.recognize_single.return_value = MagicMock(text='梯形')
        mock_roi = MagicMock()
        mock_roi.crop.return_value = np.zeros((50, 50, 3), dtype=np.uint8)
        with patch.object(recognition, '_FORMATION_ROI', mock_roi):
            result = recognize_enemy_formation(screen, ocr)
        assert result == '梯形阵'

    def test_empty_returns_empty(self) -> None:
        screen = np.zeros((1080, 1920, 3), dtype=np.uint8)
        ocr = MagicMock()
        ocr.recognize_single.return_value = MagicMock(text='')
        mock_roi = MagicMock()
        mock_roi.crop.return_value = np.zeros((50, 50, 3), dtype=np.uint8)
        with patch.object(recognition, '_FORMATION_ROI', mock_roi):
            result = recognize_enemy_formation(screen, ocr)
        assert result == ''

    def test_unknown_text_passes_through(self) -> None:
        screen = np.zeros((1080, 1920, 3), dtype=np.uint8)
        ocr = MagicMock()
        ocr.recognize_single.return_value = MagicMock(text='未知阵型')
        mock_roi = MagicMock()
        mock_roi.crop.return_value = np.zeros((50, 50, 3), dtype=np.uint8)
        with patch.object(recognition, '_FORMATION_ROI', mock_roi):
            result = recognize_enemy_formation(screen, ocr)
        assert result == '未知阵型'


class TestRecognizeShipDrop:
    """recognize_ship_drop 测试。"""

    def test_recognize_success(self) -> None:
        screen = np.zeros((1080, 1920, 3), dtype=np.uint8)
        ocr = MagicMock()
        ocr.recognize_ship_name.return_value = '岛风'
        ocr.recognize_single.return_value = MagicMock(text='驱逐舰')
        with patch(
            'autowsgr.combat.recognition.PixelChecker.crop_rotated',
            return_value=np.zeros((30, 100, 3), dtype=np.uint8),
        ):
            result = recognize_ship_drop(screen, ocr)
        assert result == ShipDropResult(ship_name='岛风', ship_type='驱逐舰')

    def test_empty_results(self) -> None:
        screen = np.zeros((1080, 1920, 3), dtype=np.uint8)
        ocr = MagicMock()
        ocr.recognize_ship_name.return_value = None
        ocr.recognize_single.return_value = MagicMock(text='')
        with patch(
            'autowsgr.combat.recognition.PixelChecker.crop_rotated',
            return_value=np.zeros((30, 100, 3), dtype=np.uint8),
        ):
            result = recognize_ship_drop(screen, ocr)
        assert result == ShipDropResult(ship_name=None, ship_type=None)


class TestDetectMvp:
    """detect_mvp 测试。"""

    def test_no_badge(self) -> None:
        screen = np.zeros((1080, 1920, 3), dtype=np.uint8)
        with patch(
            'autowsgr.vision.ImageChecker.find_template',
            return_value=None,
        ):
            assert detect_mvp(screen) is None

    def test_slot_1(self) -> None:
        screen = np.zeros((1080, 1920, 3), dtype=np.uint8)
        detail = MagicMock()
        detail.center = (0.5, 142 / 540)
        detail.confidence = 0.95
        with patch(
            'autowsgr.vision.ImageChecker.find_template',
            return_value=detail,
        ):
            assert detect_mvp(screen) == 1

    def test_slot_6(self) -> None:
        screen = np.zeros((1080, 1920, 3), dtype=np.uint8)
        detail = MagicMock()
        detail.center = (0.5, 517 / 540)
        detail.confidence = 0.92
        with patch(
            'autowsgr.vision.ImageChecker.find_template',
            return_value=detail,
        ):
            assert detect_mvp(screen) == 6

    def test_midpoint_slot_3(self) -> None:
        screen = np.zeros((1080, 1920, 3), dtype=np.uint8)
        detail = MagicMock()
        detail.center = (0.5, 292 / 540)
        detail.confidence = 0.90
        with patch(
            'autowsgr.vision.ImageChecker.find_template',
            return_value=detail,
        ):
            assert detect_mvp(screen) == 3
