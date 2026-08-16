"""测试 autowsgr.ui.battle.constants."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

import autowsgr.ui.battle.constants as battle_consts
from autowsgr.ui.battle.constants import (
    AUTO_SUPPLY_ON,
    AUTO_SUPPLY_PROBE,
    BLOOD_BAR_PROBE,
    CLICK_FLEET,
    CLICK_SHIP_SLOT,
    FLEET_ACTIVE,
    FLEET_PROBE,
    PANEL_ACTIVE,
    STATE_TOLERANCE,
    SUPPORT_DISABLE,
    SUPPORT_ENABLE,
    SUPPORT_EXHAUSTED,
)
from autowsgr.vision import Color


if TYPE_CHECKING:
    from collections.abc import Sequence


# ═══════════════════════════════════════════════════════════════════════════════
# 类型与基础值
# ═══════════════════════════════════════════════════════════════════════════════


def test_color_constants_are_color_instances() -> None:
    """Color 常量应为 Color 实例。"""
    assert isinstance(FLEET_ACTIVE, Color)
    assert isinstance(PANEL_ACTIVE, Color)
    assert isinstance(AUTO_SUPPLY_ON, Color)


def test_state_tolerance_positive() -> None:
    """STATE_TOLERANCE 应大于 0。"""
    assert STATE_TOLERANCE > 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# 字典键集合
# ═══════════════════════════════════════════════════════════════════════════════


def test_fleet_probe_keys() -> None:
    """FLEET_PROBE 键集合应为 {1, 2, 3, 4}。"""
    assert set(FLEET_PROBE.keys()) == {1, 2, 3, 4}


def test_click_fleet_keys() -> None:
    """CLICK_FLEET 键集合应为 {1, 2, 3, 4}。"""
    assert set(CLICK_FLEET.keys()) == {1, 2, 3, 4}


def test_click_ship_slot_keys() -> None:
    """CLICK_SHIP_SLOT 键集合应为 {0, 1, 2, 3, 4, 5}。"""
    assert set(CLICK_SHIP_SLOT.keys()) == set(range(6))


def test_blood_bar_probe_keys() -> None:
    """BLOOD_BAR_PROBE 键集合应为 {0, 1, 2, 3, 4, 5}。"""
    assert set(BLOOD_BAR_PROBE.keys()) == set(range(6))


# ═══════════════════════════════════════════════════════════════════════════════
# 坐标结构校验
# ═══════════════════════════════════════════════════════════════════════════════


def _assert_2d_coordinate(coord: Sequence[float]) -> None:
    """校验坐标为 2 个 float 且均在 [0, 1] 区间内。"""
    assert isinstance(coord, (tuple, list))
    assert len(coord) == 2
    x, y = coord
    assert isinstance(x, float)
    assert isinstance(y, float)
    assert 0.0 <= x <= 1.0
    assert 0.0 <= y <= 1.0


@pytest.mark.parametrize(
    'name',
    [
        'FLEET_PROBE',
        'CLICK_FLEET',
        'CLICK_SHIP_SLOT',
        'BLOOD_BAR_PROBE',
        'CLICK_BACK',
        'CLICK_SUPPORT',
        'AUTO_SUPPLY_PROBE',
    ],
)
def test_all_coordinate_tuples_are_valid(name: str) -> None:
    """所有坐标元组均为 2-float 且落在 [0, 1]。"""
    value = getattr(battle_consts, name)
    if isinstance(value, dict):
        for coord in value.values():
            _assert_2d_coordinate(coord)
    else:
        _assert_2d_coordinate(value)


def test_auto_supply_probe_non_empty() -> None:
    """AUTO_SUPPLY_PROBE 为非空 list / tuple。"""
    assert isinstance(AUTO_SUPPLY_PROBE, (list, tuple))
    assert len(AUTO_SUPPLY_PROBE) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# 战役支援颜色
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    'color',
    [SUPPORT_ENABLE, SUPPORT_DISABLE, SUPPORT_EXHAUSTED],
    ids=['enable', 'disable', 'exhausted'],
)
def test_support_colors_structure(color: Color) -> None:
    """战役支援颜色为 Color 实例且 RGB 通道在合法范围。"""
    assert isinstance(color, Color)
    r, g, b = color.as_rgb_tuple()
    assert 0 <= r <= 255
    assert 0 <= g <= 255
    assert 0 <= b <= 255
