"""测试 autowsgr.combat.plan."""

from __future__ import annotations

from typing import Any

import pytest

from autowsgr.combat.plan import (
    MODE_CATEGORIES,
    MODE_END_PHASES,
    MODE_TRANSITIONS,
    CombatMode,
    CombatPlan,
    NodeDecision,
    _parse_rule_item,
)
from autowsgr.combat.state import ModeCategory
from autowsgr.types import FightCondition, Formation, RepairMode


# ═══════════════════════════════════════════════════════════════════════════════
# _parse_rule_item
# ═══════════════════════════════════════════════════════════════════════════════


def test_parse_rule_item_with_arrow() -> None:
    rule = '(BB >= 2) and (CV > 0) => retreat'
    assert _parse_rule_item(rule) == ['(BB >= 2) and (CV > 0)', 'retreat']


def test_parse_rule_item_bare_string() -> None:
    rule = '(BB >= 2) and (CV > 0)'
    assert _parse_rule_item(rule) == ['(BB >= 2) and (CV > 0)', 'retreat']


def test_parse_rule_item_list_format() -> None:
    rule = ['(BB >= 2) and (CV > 0)', 'retreat', 'extra']
    assert _parse_rule_item(rule) == ['(BB >= 2) and (CV > 0)', 'retreat']


def test_parse_rule_item_invalid() -> None:
    with pytest.raises(ValueError, match='无法解析规则'):
        _parse_rule_item(['only_one'])


# ═══════════════════════════════════════════════════════════════════════════════
# NodeDecision
# ═══════════════════════════════════════════════════════════════════════════════


def test_node_decision_from_dict_minimal() -> None:
    decision = NodeDecision.from_dict({})
    assert decision.formation == Formation.double_column
    assert decision.night is False
    assert decision.proceed is True
    assert decision.proceed_stop == RepairMode.severe_damage
    assert decision.enemy_rules is None
    assert decision.formation_rules is None
    assert decision.detour is False
    assert decision.long_missile_support is False
    assert decision.SL_when_spot_enemy_fails is False
    assert decision.SL_when_detour_fails is True
    assert decision.SL_when_enter_fight is False
    assert decision.formation_when_spot_enemy_fails is None


def test_node_decision_from_dict_full() -> None:
    data: dict[str, Any] = {
        'formation': 1,
        'night': True,
        'proceed': False,
        'proceed_stop': 1,
        'enemy_rules': ['BB >= 2 => retreat'],
        'enemy_formation_rules': ['单纵阵 => retreat'],
        'detour': True,
        'long_missile_support': True,
        'SL_when_spot_enemy_fails': True,
        'SL_when_detour_fails': False,
        'SL_when_enter_fight': True,
        'formation_when_spot_enemy_fails': 3,
    }
    decision = NodeDecision.from_dict(data)
    assert decision.formation == Formation.single_column
    assert decision.night is True
    assert decision.proceed is False
    assert decision.proceed_stop == RepairMode.moderate_damage
    assert decision.enemy_rules is not None
    assert decision.formation_rules is not None
    assert decision.detour is True
    assert decision.long_missile_support is True
    assert decision.SL_when_spot_enemy_fails is True
    assert decision.SL_when_detour_fails is False
    assert decision.SL_when_enter_fight is True
    assert decision.formation_when_spot_enemy_fails == Formation.circular


# ═══════════════════════════════════════════════════════════════════════════════
# CombatMode & 派生映射表
# ═══════════════════════════════════════════════════════════════════════════════


def test_combat_mode_constants() -> None:
    assert CombatMode.NORMAL == 'normal'
    assert CombatMode.BATTLE == 'battle'
    assert CombatMode.EXERCISE == 'exercise'
    assert CombatMode.DECISIVE == 'decisive'
    assert CombatMode.EVENT == 'event'


def test_mode_transitions_cover_all_modes() -> None:
    for mode in (
        CombatMode.NORMAL,
        CombatMode.BATTLE,
        CombatMode.EXERCISE,
        CombatMode.DECISIVE,
        CombatMode.EVENT,
    ):
        assert mode in MODE_TRANSITIONS


def test_mode_end_phases_cover_all_modes() -> None:
    for mode in (
        CombatMode.NORMAL,
        CombatMode.BATTLE,
        CombatMode.EXERCISE,
        CombatMode.DECISIVE,
        CombatMode.EVENT,
    ):
        assert mode in MODE_END_PHASES


def test_mode_categories_cover_all_modes() -> None:
    for mode in (
        CombatMode.NORMAL,
        CombatMode.BATTLE,
        CombatMode.EXERCISE,
        CombatMode.DECISIVE,
        CombatMode.EVENT,
    ):
        assert mode in MODE_CATEGORIES
        if mode in (CombatMode.NORMAL, CombatMode.EVENT):
            assert MODE_CATEGORIES[mode] == ModeCategory.MAP
        else:
            assert MODE_CATEGORIES[mode] == ModeCategory.SINGLE


# ═══════════════════════════════════════════════════════════════════════════════
# CombatPlan
# ═══════════════════════════════════════════════════════════════════════════════


def test_combat_plan_post_init_expands_repair_mode() -> None:
    plan = CombatPlan(repair_mode=RepairMode.moderate_damage)
    assert isinstance(plan.repair_mode, list)
    assert len(plan.repair_mode) == 6
    assert all(r == RepairMode.moderate_damage for r in plan.repair_mode)


def test_combat_plan_post_init_keeps_list() -> None:
    modes = [RepairMode.severe_damage] * 6
    plan = CombatPlan(repair_mode=modes)
    assert plan.repair_mode is modes


@pytest.mark.parametrize(
    'mode',
    [
        CombatMode.NORMAL,
        CombatMode.BATTLE,
        CombatMode.EXERCISE,
        CombatMode.DECISIVE,
        CombatMode.EVENT,
    ],
)
def test_combat_plan_transitions_and_end_phase(mode: str) -> None:
    plan = CombatPlan(mode=mode)
    assert plan.transitions == MODE_TRANSITIONS[mode]
    assert plan.end_phase == MODE_END_PHASES[mode]


def test_combat_plan_get_node_decision_existing() -> None:
    node_a = NodeDecision.from_dict({'night': True})
    default = NodeDecision.from_dict({'night': False})
    plan = CombatPlan(nodes={'A': node_a}, default_node=default)
    assert plan.get_node_decision('A').night is True


def test_combat_plan_get_node_decision_missing_returns_default() -> None:
    default = NodeDecision.from_dict({'night': False})
    plan = CombatPlan(default_node=default)
    assert plan.get_node_decision('B').night is False


def test_combat_plan_is_selected_node_empty_whitelist() -> None:
    plan = CombatPlan(selected_nodes=[])
    assert plan.is_selected_node('A') is True
    assert plan.is_selected_node('B') is True


def test_combat_plan_is_selected_node_non_empty() -> None:
    plan = CombatPlan(selected_nodes=['A', 'C'])
    assert plan.is_selected_node('A') is True
    assert plan.is_selected_node('B') is False
    assert plan.is_selected_node('C') is True


def test_combat_plan_from_dict_minimal() -> None:
    plan = CombatPlan.from_dict({})
    assert plan.name == ''
    assert plan.mode == CombatMode.NORMAL
    assert plan.chapter == 1
    assert plan.map_id == 1
    assert plan.fleet_id == 1
    assert plan.fleet is None
    assert plan.fight_condition == FightCondition.aim
    assert plan.selected_nodes == []
    assert plan.nodes == {}
    assert plan.event_name is None
    assert isinstance(plan.repair_mode, list)
    assert len(plan.repair_mode) == 6
    assert all(r == RepairMode.severe_damage for r in plan.repair_mode)


def test_combat_plan_from_dict_with_nodes() -> None:
    data: dict[str, Any] = {
        'node_args': {
            'A': {'night': True},
            'B': {'formation': 1},
        },
    }
    plan = CombatPlan.from_dict(data)
    assert set(plan.nodes.keys()) == {'A', 'B'}
    assert plan.get_node_decision('A').night is True
    assert plan.get_node_decision('B').formation == Formation.single_column


def test_combat_plan_from_dict_node_defaults_merging() -> None:
    data: dict[str, Any] = {
        'node_defaults': {'night': True, 'formation': 1},
        'node_args': {
            'A': {'formation': 3},
        },
    }
    plan = CombatPlan.from_dict(data)
    decision = plan.get_node_decision('A')
    assert decision.night is True
    assert decision.formation == Formation.circular


def test_combat_plan_from_dict_selected_nodes_backfill() -> None:
    data: dict[str, Any] = {
        'node_defaults': {'night': True},
        'selected_nodes': ['A', 'B'],
    }
    plan = CombatPlan.from_dict(data)
    assert 'A' in plan.nodes
    assert 'B' in plan.nodes
    assert plan.get_node_decision('A').night is True
    assert plan.get_node_decision('B').night is True


def test_combat_plan_from_dict_event_name() -> None:
    data: dict[str, Any] = {'event': '20260212'}
    plan = CombatPlan.from_dict(data)
    assert plan.event_name == '20260212'


def test_combat_plan_from_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    data: dict[str, Any] = {'mode': 'battle', 'chapter': 5}
    monkeypatch.setattr('autowsgr.combat.plan.load_yaml', lambda _path: data)
    plan = CombatPlan.from_yaml('/fake/path/plan.yaml')
    assert plan.name == 'plan'
    assert plan.mode == CombatMode.BATTLE
    assert plan.chapter == 5
