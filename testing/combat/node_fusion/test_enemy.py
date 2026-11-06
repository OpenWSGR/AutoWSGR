"""验证敌情观测保留槽位，并从同一张输入截图采集证据。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from autowsgr.combat.node_fusion import enemy as observation_mod
from autowsgr.combat.node_fusion.enemy import observe_enemy
from autowsgr.combat.recognition import recognize_enemy_formation, recognize_enemy_ships
from autowsgr.vision.ocr import OCRResult


@pytest.fixture
def screen() -> np.ndarray:
    return np.zeros((540, 960, 3), dtype=np.uint8)


@pytest.fixture(autouse=True)
def native_types(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """模拟实际安装 native 的舰类语义，包括旧版 BG 与 NotDef。"""
    names = {'BB': '战列', 'DD': '驱逐', 'BG': '大巡', 'NotDef': '调谐', 'NO': '无'}

    def from_english(code: str) -> SimpleNamespace | None:
        name = names.get(code)
        return None if name is None else SimpleNamespace(as_chinese=lambda: name)

    native = MagicMock()
    native.from_english.side_effect = from_english
    monkeypatch.setattr(observation_mod, 'VesselType', native)
    return native


@pytest.fixture(autouse=True)
def detour_match(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    matcher = MagicMock(return_value=None)
    monkeypatch.setattr(observation_mod.ImageChecker, 'find_any', matcher)
    return matcher


def test_slots_keep_order_unknowns_and_actual_native_semantics(
    screen: np.ndarray, native_types: MagicMock
) -> None:
    dll = MagicMock()
    dll.recognize_enemy.return_value = 'BG DD NO NotDef BB unknown'

    observation = observe_enemy(screen, dll=dll)

    assert observation.raw_slots == ('BG', 'DD', 'NO', 'NotDef', 'BB', 'unknown')
    assert observation.ships == ('大巡', '驱逐', None, '调谐', '战列', None)
    assert observation.valid_slots
    assert observation.counts == {'BG': 1, 'DD': 1, 'NotDef': 1, 'BB': 1, 'unknown': 1, 'ALL': 5}
    assert [call.args[0] for call in native_types.from_english.call_args_list] == [
        'BG',
        'DD',
        'NotDef',
        'BB',
        'unknown',
    ]
    assert observation.counts == recognize_enemy_ships(screen, dll=dll)


@pytest.mark.parametrize('raw', ['', 'BB DD NO', 'BB BB BB BB BB BB BB'])
def test_invalid_slot_count_is_missing_evidence_without_padding(
    screen: np.ndarray, native_types: MagicMock, raw: str
) -> None:
    dll = MagicMock()
    dll.recognize_enemy.return_value = raw
    ocr = MagicMock()
    ocr.recognize_single.return_value = OCRResult('单纵阵', 0.98)

    observation = observe_enemy(screen, ocr, dll=dll)

    assert observation.raw_slots == tuple(raw.split())
    assert observation.ships == (None,) * 6
    assert not observation.valid_slots
    assert observation.formation == 1
    native_types.from_english.assert_not_called()
    assert observation.counts == recognize_enemy_ships(screen, dll=dll)


def test_same_frame_feeds_ordered_crops_ocr_and_detour(
    screen: np.ndarray, detour_match: MagicMock
) -> None:
    # 用不同亮度独立标识行列，避免测试仅重复实现。
    for (x, y), value in zip(
        [(39, 156), (322, 156), (39, 245), (322, 245), (39, 334), (322, 334)],
        [20, 40, 60, 80, 100, 120],
        strict=True,
    ):
        screen[y : y + 16, x : x + 32] = value
    screen[27:81, 105:192] = 170
    original = screen.copy()
    dll = MagicMock()
    dll.recognize_enemy.return_value = 'BB DD BB DD BB NO'
    ocr = MagicMock()
    ocr.recognize_single.return_value = OCRResult(' 梯形阵 ', 0.92, (1, 2, 3, 4))
    detour_match.return_value = SimpleNamespace(confidence=0.91)

    observation = observe_enemy(screen, ocr, dll=dll)

    crops = dll.recognize_enemy.call_args.args[0]
    assert len(crops) == 6
    assert all(crop.shape == (16, 32) and crop.dtype == np.uint8 for crop in crops)
    assert [int(crop[0, 0]) for crop in crops] == [20, 40, 60, 80, 100, 120]
    cropped_formation = ocr.recognize_single.call_args.args[0]
    assert np.shares_memory(cropped_formation, screen)
    assert np.all(cropped_formation == 170)
    assert detour_match.call_args.args[0] is screen
    assert detour_match.call_args.kwargs['confidence'] == 0.8
    assert observation.formation == 4
    assert observation.formation_text == '梯形阵'
    assert observation.formation_confidence == 0.92
    assert observation.detour is True
    assert observation.detour_score == 0.91
    np.testing.assert_array_equal(screen, original)


@pytest.mark.parametrize(
    ('text', 'expected'),
    [
        ('单纵阵', 1),
        ('复纵阵', 2),
        ('轮型阵', 3),
        ('梯形阵', 4),
        ('单横阵', 5),
        ('', None),
        ('阵', None),
    ],
)
def test_formation_normalization_preserves_raw_text_and_score(
    screen: np.ndarray, text: str, expected: int | None
) -> None:
    dll = MagicMock()
    dll.recognize_enemy.return_value = 'DD DD DD DD DD DD'
    ocr = MagicMock()
    ocr.recognize_single.return_value = OCRResult(text, 0.71)

    observation = observe_enemy(screen, ocr, dll=dll)

    assert observation.formation == expected
    assert observation.formation_text == text
    assert observation.formation_confidence == 0.71
    assert observation.ships == ('驱逐',) * 6
    # 原有接口仍为阵型规则保留无法识别的 OCR 原文。
    assert recognize_enemy_formation(screen, ocr) == text


def test_missing_ocr_and_detour_do_not_mean_negative_evidence(screen: np.ndarray) -> None:
    dll = MagicMock()
    dll.recognize_enemy.return_value = 'NO NO NO NO NO NO'

    observation = observe_enemy(screen, dll=dll)

    assert observation.valid_slots
    assert observation.ships == (None,) * 6
    assert observation.formation is None
    assert observation.formation_text == ''
    assert observation.formation_confidence is None
    assert observation.detour is None
    assert observation.detour_score is None
    assert observation.counts == {'ALL': 0}
    assert asdict(observation)['raw_slots'] == ('NO',) * 6
    with pytest.raises(FrozenInstanceError):
        observation.detour = False


def test_exercise_uses_existing_six_horizontal_crops(screen: np.ndarray) -> None:
    for x, value in zip([277, 380, 483, 587, 690, 793], range(10, 70, 10), strict=True):
        screen[312:328, x : x + 32] = value
    dll = MagicMock()
    dll.recognize_enemy.return_value = 'DD DD DD DD DD DD'

    observe_enemy(screen, mode='exercise', dll=dll)

    crops = dll.recognize_enemy.call_args.args[0]
    assert [int(crop[0, 0]) for crop in crops] == [10, 20, 30, 40, 50, 60]
