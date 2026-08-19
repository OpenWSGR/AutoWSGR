"""测试 autowsgr.combat.state。"""

from __future__ import annotations

import pytest

from autowsgr.combat.state import (
    CombatPhase,
    ModeCategory,
    build_transitions,
    resolve_successors,
)


class TestCombatPhase:
    """CombatPhase 枚举测试。"""

    def test_phase_values_distinct(self) -> None:
        values = list(CombatPhase)
        assert len(values) == len(set(v.value for v in values))

    def test_key_phases_exist(self) -> None:
        assert CombatPhase.START_FIGHT.name == 'START_FIGHT'
        assert CombatPhase.RESULT.name == 'RESULT'
        assert CombatPhase.PROCEED.name == 'PROCEED'


class TestBuildTransitions:
    """build_transitions 测试。"""

    def test_map_category_returns_dict(self) -> None:
        result = build_transitions(ModeCategory.MAP, CombatPhase.MAP_PAGE)
        assert isinstance(result, dict)
        assert CombatPhase.START_FIGHT in result

    def test_single_category_returns_dict(self) -> None:
        result = build_transitions(ModeCategory.SINGLE, None)
        assert isinstance(result, dict)
        assert CombatPhase.START_FIGHT in result

    def test_map_proceed_branch(self) -> None:
        t = build_transitions(ModeCategory.MAP, CombatPhase.MAP_PAGE)
        proceed = t[CombatPhase.PROCEED]
        assert isinstance(proceed, dict)
        assert 'yes' in proceed
        assert 'no' in proceed

    def test_map_spot_enemy_branch(self) -> None:
        t = build_transitions(ModeCategory.MAP, CombatPhase.MAP_PAGE)
        spot = t[CombatPhase.SPOT_ENEMY_SUCCESS]
        assert isinstance(spot, dict)
        assert 'fight' in spot
        assert 'detour' in spot
        assert 'retreat' in spot

    def test_single_no_end_page_result_termination(self) -> None:
        t = build_transitions(ModeCategory.SINGLE, None)
        assert CombatPhase.RESULT not in t or t[CombatPhase.RESULT] == []

    def test_single_with_end_page(self) -> None:
        t = build_transitions(ModeCategory.SINGLE, CombatPhase.EXERCISE_PAGE)
        assert CombatPhase.RESULT in t
        assert CombatPhase.EXERCISE_PAGE in t[CombatPhase.RESULT]


class TestResolveSuccessors:
    """resolve_successors 测试。"""

    def test_list_branch(self) -> None:
        t = build_transitions(ModeCategory.SINGLE, None)
        result = resolve_successors(t, CombatPhase.FORMATION, 'any')
        assert CombatPhase.FIGHT_PERIOD in result

    def test_dict_branch_known_action(self) -> None:
        t = build_transitions(ModeCategory.MAP, CombatPhase.MAP_PAGE)
        result = resolve_successors(t, CombatPhase.PROCEED, 'yes')
        assert CombatPhase.FIGHT_CONDITION in result

    def test_dict_branch_unknown_action_fallback(self) -> None:
        t = build_transitions(ModeCategory.MAP, CombatPhase.MAP_PAGE)
        result = resolve_successors(t, CombatPhase.PROCEED, 'unknown')
        # fallback 到第一个分支值
        assert len(result) > 0

    def test_key_error_missing_phase(self) -> None:
        t = build_transitions(ModeCategory.SINGLE, None)
        with pytest.raises(KeyError):
            resolve_successors(t, CombatPhase.MAP_PAGE, '')
