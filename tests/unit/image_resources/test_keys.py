"""Tests for autowsgr.image_resources.keys."""

from __future__ import annotations

import pytest

from autowsgr.image_resources.keys import (
    RESULT_GRADE_KEYS,
    TemplateKey,
    get_templates,
)
from autowsgr.vision import ImageTemplate


EXPECTED_VALUES: dict[TemplateKey, str] = {
    TemplateKey.FORMATION: 'formation',
    TemplateKey.SPOT_ENEMY: 'spot_enemy',
    TemplateKey.RESULT: 'result',
    TemplateKey.FLAGSHIP_DAMAGE: 'flagship_damage',
    TemplateKey.PROCEED: 'proceed',
    TemplateKey.NIGHT_BATTLE: 'night_battle',
    TemplateKey.FIGHT_CONDITION: 'fight_condition',
    TemplateKey.BYPASS: 'bypass',
    TemplateKey.RESULT_PAGE: 'result_page',
    TemplateKey.MISSILE_SUPPORT: 'missile_support',
    TemplateKey.MISSILE_ANIMATION: 'missile_animation',
    TemplateKey.FIGHT_PERIOD: 'fight_period',
    TemplateKey.GET_SHIP: 'get_ship',
    TemplateKey.GET_ITEM: 'get_item',
    TemplateKey.GET_SHIP_OR_ITEM: 'get_ship_or_item',
    TemplateKey.END_MAP_PAGE: 'end_map_page',
    TemplateKey.END_BATTLE_PAGE: 'end_battle_page',
    TemplateKey.END_EXERCISE_PAGE: 'end_exercise_page',
    TemplateKey.DOCK_FULL: 'dock_full',
    TemplateKey.BATTLE_TIMES_EXCEED: 'battle_times_exceed',
    TemplateKey.GRADE_SS: 'grade_ss',
    TemplateKey.GRADE_S: 'grade_s',
    TemplateKey.GRADE_A: 'grade_a',
    TemplateKey.GRADE_B: 'grade_b',
    TemplateKey.GRADE_C: 'grade_c',
    TemplateKey.GRADE_D: 'grade_d',
    TemplateKey.GRADE_LOOT: 'grade_loot',
}


@pytest.mark.parametrize(('member', 'expected'), list(EXPECTED_VALUES.items()))
def test_member_string_values(member: TemplateKey, expected: str) -> None:
    """Key TemplateKey members have expected string values."""
    assert member.value == expected


@pytest.mark.parametrize('member', list(TemplateKey))
def test_templates_non_empty_list(member: TemplateKey) -> None:
    """Every TemplateKey member's .templates returns a non-empty list of ImageTemplate."""
    templates = member.templates
    assert isinstance(templates, list)
    assert len(templates) > 0
    assert all(isinstance(t, ImageTemplate) for t in templates)


@pytest.mark.parametrize('member', list(TemplateKey))
def test_get_templates_equivalent_to_property(member: TemplateKey) -> None:
    """get_templates(key) is equivalent to key.templates."""
    assert get_templates(member) is member.templates


def test_result_grade_keys() -> None:
    """RESULT_GRADE_KEYS keys are {'SS','S','A','B','C','D'}."""
    assert set(RESULT_GRADE_KEYS.keys()) == {'SS', 'S', 'A', 'B', 'C', 'D'}


def test_result_grade_values_are_valid_members() -> None:
    """RESULT_GRADE_KEYS values are valid TemplateKey members."""
    for value in RESULT_GRADE_KEYS.values():
        assert isinstance(value, TemplateKey)
        assert value in TemplateKey


def test_get_ship_or_item_has_exactly_two_templates() -> None:
    """TemplateKey.GET_SHIP_OR_ITEM.templates returns exactly 2 templates."""
    templates = TemplateKey.GET_SHIP_OR_ITEM.templates
    assert len(templates) == 2
    assert all(isinstance(t, ImageTemplate) for t in templates)
