"""测试 autowsgr.image_resources.combat."""

from __future__ import annotations

import pytest

from autowsgr.image_resources.combat import CombatTemplates, _ResultGrade
from autowsgr.vision import ImageTemplate


class TestResultGrade:
    """_ResultGrade 测试。"""

    def test_all_grades_count(self) -> None:
        grades = _ResultGrade.all_grades()
        assert len(grades) == 6

    def test_all_grades_order_and_no_loot(self) -> None:
        grades = _ResultGrade.all_grades()
        expected = [
            _ResultGrade.SS,
            _ResultGrade.S,
            _ResultGrade.A,
            _ResultGrade.B,
            _ResultGrade.C,
            _ResultGrade.D,
        ]
        assert grades == expected

    @pytest.mark.parametrize('grade_attr', ['SS', 'S', 'A', 'B', 'C', 'D'])
    def test_grade_is_image_template(self, grade_attr: str) -> None:
        template = getattr(_ResultGrade, grade_attr)
        assert isinstance(template, ImageTemplate)

    def test_loot_exists_and_is_image_template(self) -> None:
        assert isinstance(_ResultGrade.LOOT, ImageTemplate)

    def test_loot_not_in_all_grades(self) -> None:
        assert _ResultGrade.LOOT not in _ResultGrade.all_grades()


class TestCombatTemplates:
    """CombatTemplates 属性存在性与类型测试。"""

    @pytest.mark.parametrize(
        'attr',
        [
            'FORMATION',
            'SPOT_ENEMY',
            'RESULT',
            'FLAGSHIP_DAMAGE',
            'PROCEED',
            'NIGHT_BATTLE',
            'FIGHT_CONDITION',
            'BYPASS',
            'RESULT_PAGE',
            'MISSILE_SUPPORT',
            'MISSILE_ANIMATION',
            'FIGHT_PERIOD',
            'GET_SHIP',
            'GET_ITEM',
            'END_MAP_PAGE',
            'END_BATTLE_PAGE',
            'END_EXERCISE_PAGE',
            'MVP_BADGE',
            'DOCK_FULL',
            'BATTLE_TIMES_EXCEED',
        ],
    )
    def test_lazy_template_returns_image_template(self, attr: str) -> None:
        template = getattr(CombatTemplates, attr)
        assert isinstance(template, ImageTemplate)

    def test_result_nested_class(self) -> None:
        assert CombatTemplates.Result is _ResultGrade

    def test_key_attributes_exist(self) -> None:
        assert hasattr(CombatTemplates, 'FORMATION')
        assert hasattr(CombatTemplates, 'SPOT_ENEMY')
        assert hasattr(CombatTemplates, 'RESULT')
        assert hasattr(CombatTemplates, 'NIGHT_BATTLE')
        assert hasattr(CombatTemplates, 'END_MAP_PAGE')
        assert hasattr(CombatTemplates, 'DOCK_FULL')
        assert hasattr(CombatTemplates, 'BATTLE_TIMES_EXCEED')

    def test_lazy_loading_consistency(self) -> None:
        first = CombatTemplates.FORMATION
        second = CombatTemplates.FORMATION
        assert first is second

        first_result = CombatTemplates.Result.SS
        second_result = CombatTemplates.Result.SS
        assert first_result is second_result
