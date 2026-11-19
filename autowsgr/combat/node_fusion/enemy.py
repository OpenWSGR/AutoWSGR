"""从同一张索敌截图识别敌方编队每个位置的舰种、敌方阵型和迂回按钮。

识别结果中的 ``None`` 表示该位置的舰种未知。native 返回 ``NO`` 有两种可能：
该位置没有舰船，或识别失败。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

from autowsgr_native.vessel_type import VesselType

from autowsgr.combat.recognition import (
    normalize_enemy_formation,
    read_enemy_formation,
    recognize_enemy_slots,
)
from autowsgr.image_resources import TemplateKey
from autowsgr.vision import ImageChecker


if TYPE_CHECKING:
    import numpy as np

    from autowsgr.vision import ApiDll, OCREngine


_FORMATION_IDS = {
    '单纵阵': 1,
    '复纵阵': 2,
    '轮型阵': 3,
    '梯形阵': 4,
    '单横阵': 5,
}


@dataclass(frozen=True, slots=True)
class EnemyObservation:
    """一张索敌截图的识别结果，按敌方编队的六个位置依次记录。

    ``raw_slots`` 保留 native 返回的原始舰种代码，``ships`` 保存对应的中文名称，
    例如 ``Airfield`` 对应机场。若返回的代码数量不是六个，保留原始代码，
    将该帧全部舰种记为未知。
    OCR 和模板分数只是各识别器的原始分数，不代表节点正确概率。
    """

    raw_slots: tuple[str, ...]
    ships: tuple[str | None, ...]
    formation: int | None
    formation_text: str
    formation_confidence: float | None
    detour: bool | None
    detour_score: float | None
    valid_slots: bool = True

    @property
    def counts(self) -> dict[str, int]:
        """保留旧敌舰规则语义：统计原始代号，忽略 NO，包含 ALL。"""
        counts = dict(Counter(code for code in self.raw_slots if code != 'NO'))
        counts['ALL'] = sum(counts.values())
        return counts


def _ship_name(code: str) -> str | None:
    if code == 'NO':
        return None
    vessel_type = VesselType.from_english(code)
    return None if vessel_type is None else vessel_type.as_chinese()


def observe_enemy(
    screen: np.ndarray,
    ocr: OCREngine | None = None,
    *,
    mode: str = 'fight',
    dll: ApiDll | None = None,
) -> EnemyObservation:
    """从给定截图读取全部证据，不访问设备或另取截图。

    迂回按钮没有达到模板阈值时记录 ``None``，不把漏检当作否定证据。
    未提供 OCR 或 OCR 未识别出标准阵型时，仍保留其他观察。
    """
    raw_slots = recognize_enemy_slots(screen, mode, dll=dll)
    valid_slots = len(raw_slots) == 6
    ships = tuple(map(_ship_name, raw_slots)) if valid_slots else (None,) * 6

    formation = None
    formation_text = ''
    formation_confidence = None
    if ocr is not None:
        result = read_enemy_formation(screen, ocr)
        formation_text = result.text.strip()
        formation_confidence = result.confidence
        formation = _FORMATION_IDS.get(normalize_enemy_formation(formation_text))

    detour_match = ImageChecker.find_any(screen, TemplateKey.BYPASS.templates, confidence=0.8)
    return EnemyObservation(
        raw_slots=raw_slots,
        ships=ships,
        formation=formation,
        formation_text=formation_text,
        formation_confidence=formation_confidence,
        detour=True if detour_match is not None else None,
        detour_score=detour_match.confidence if detour_match is not None else None,
        valid_slots=valid_slots,
    )
