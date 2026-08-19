"""测试 autowsgr.ui.battle.blood."""

from __future__ import annotations

import pytest

from autowsgr.types import ShipDamageState
from autowsgr.ui.battle.blood import (
    _BLOOD_COLORS,
    BLOOD_EMPTY,
    BLOOD_GREEN,
    BLOOD_NO_SHIP,
    BLOOD_RED,
    BLOOD_RED_PREPARE,
    BLOOD_YELLOW,
    classify_blood,
)
from autowsgr.vision import Color


@pytest.mark.parametrize(
    ('pixel', 'expected'),
    [
        (BLOOD_GREEN, ShipDamageState.NORMAL),
        (BLOOD_YELLOW, ShipDamageState.MODERATE),
        (BLOOD_RED, ShipDamageState.SEVERE),
        (BLOOD_RED_PREPARE, ShipDamageState.SEVERE),
        (BLOOD_EMPTY, ShipDamageState.SEVERE),
        (BLOOD_NO_SHIP, ShipDamageState.NO_SHIP),
    ],
)
def test_classify_blood_exact_colors(pixel: Color, expected: ShipDamageState) -> None:
    """每种参考颜色应被正确分类到对应状态。"""
    assert classify_blood(pixel) is expected


def test_classify_blood_closer_to_green() -> None:
    """距离绿血更近的颜色应被判为 NORMAL."""
    closer_to_green = Color.of(100, 170, 100)
    assert classify_blood(closer_to_green) is ShipDamageState.NORMAL


def test_classify_blood_closer_to_yellow() -> None:
    """距离黄血更近的颜色应被判为 MODERATE."""
    closer_to_yellow = Color.of(230, 160, 45)
    assert classify_blood(closer_to_yellow) is ShipDamageState.MODERATE


def test_blood_colors_structure() -> None:
    """_BLOOD_COLORS 长度与结构校验。"""
    assert len(_BLOOD_COLORS) == 6
    for item in _BLOOD_COLORS:
        assert isinstance(item, tuple)
        assert len(item) == 2
        color, state = item
        assert isinstance(color, Color)
        assert isinstance(state, ShipDamageState)
