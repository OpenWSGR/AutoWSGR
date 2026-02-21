"""战斗系统单元测试。"""

from __future__ import annotations

import pytest

from autowsgr.combat.state import (
    BATTLE_TRANSITIONS,
    EXERCISE_TRANSITIONS,
    NORMAL_FIGHT_TRANSITIONS,
    CombatPhase,
    resolve_successors,
)
from autowsgr.combat.rules import (
    Condition,
    Rule,
    RuleAction,
    RuleEngine,
    RuleResult,
    _parse_legacy_condition,
)
from autowsgr.combat.history import (
    CombatEvent,
    CombatHistory,
    EventType,
    FightResult,
)
from autowsgr.combat.plan import CombatPlan, NodeDecision, CombatMode
from autowsgr.combat.actions import check_blood
from autowsgr.types import Formation, RepairMode, ShipDamageState


# ═══════════════════════════════════════════════════════════════════════════════
# state.py 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestCombatPhase:
    """CombatPhase 枚举测试。"""

    def test_all_phases_exist(self):
        assert CombatPhase.PROCEED is not None
        assert CombatPhase.FIGHT_CONDITION is not None
        assert CombatPhase.SPOT_ENEMY_SUCCESS is not None
        assert CombatPhase.FORMATION is not None
        assert CombatPhase.MISSILE_ANIMATION is not None
        assert CombatPhase.FIGHT_PERIOD is not None
        assert CombatPhase.NIGHT_PROMPT is not None
        assert CombatPhase.RESULT is not None
        assert CombatPhase.GET_SHIP is not None
        assert CombatPhase.FLAGSHIP_SEVERE_DAMAGE is not None
        assert CombatPhase.MAP_PAGE is not None
        assert CombatPhase.BATTLE_PAGE is not None
        assert CombatPhase.EXERCISE_PAGE is not None


class TestResolveSuccessors:
    """状态转移解析测试。"""

    def test_normal_proceed_yes(self):
        result = resolve_successors(
            NORMAL_FIGHT_TRANSITIONS, CombatPhase.PROCEED, "yes"
        )
        phases = [r[0] for r in result]
        assert CombatPhase.FIGHT_CONDITION in phases
        assert CombatPhase.MAP_PAGE in phases

    def test_normal_proceed_no(self):
        result = resolve_successors(
            NORMAL_FIGHT_TRANSITIONS, CombatPhase.PROCEED, "no"
        )
        phases = [r[0] for r in result]
        assert phases == [CombatPhase.MAP_PAGE]

    def test_normal_night_no_with_timeout(self):
        result = resolve_successors(
            NORMAL_FIGHT_TRANSITIONS, CombatPhase.NIGHT_PROMPT, "no"
        )
        assert result == [(CombatPhase.RESULT, 10.0)]

    def test_normal_formation_no_branch(self):
        result = resolve_successors(
            NORMAL_FIGHT_TRANSITIONS, CombatPhase.FORMATION, ""
        )
        phases = [r[0] for r in result]
        assert CombatPhase.FIGHT_PERIOD in phases

    def test_battle_transitions(self):
        result = resolve_successors(
            BATTLE_TRANSITIONS, CombatPhase.PROCEED, ""
        )
        phases = [r[0] for r in result]
        assert CombatPhase.SPOT_ENEMY_SUCCESS in phases

    def test_exercise_transitions(self):
        result = resolve_successors(
            EXERCISE_TRANSITIONS, CombatPhase.RESULT, ""
        )
        phases = [r[0] for r in result]
        assert CombatPhase.EXERCISE_PAGE in phases

    def test_unknown_phase_raises(self):
        with pytest.raises(KeyError):
            resolve_successors(
                NORMAL_FIGHT_TRANSITIONS, CombatPhase.EXERCISE_PAGE, ""
            )

    def test_spot_enemy_retreat_branch(self):
        result = resolve_successors(
            NORMAL_FIGHT_TRANSITIONS, CombatPhase.SPOT_ENEMY_SUCCESS, "retreat"
        )
        phases = [r[0] for r in result]
        assert phases == [CombatPhase.MAP_PAGE]

    def test_spot_enemy_fight_branch(self):
        result = resolve_successors(
            NORMAL_FIGHT_TRANSITIONS, CombatPhase.SPOT_ENEMY_SUCCESS, "fight"
        )
        phases = [r[0] for r in result]
        assert CombatPhase.FORMATION in phases
        assert CombatPhase.MISSILE_ANIMATION in phases


# ═══════════════════════════════════════════════════════════════════════════════
# rules.py 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestCondition:
    """Condition 评估测试。"""

    def test_greater(self):
        c = Condition(field="BB", op=">=", value=2)
        assert c.evaluate({"BB": 2})
        assert c.evaluate({"BB": 3})
        assert not c.evaluate({"BB": 1})

    def test_less_than(self):
        c = Condition(field="CV", op="<", value=2)
        assert c.evaluate({"CV": 1})
        assert not c.evaluate({"CV": 2})

    def test_missing_field(self):
        c = Condition(field="SS", op=">", value=0)
        assert not c.evaluate({"BB": 1})  # SS defaults to 0

    def test_invalid_op(self):
        with pytest.raises(ValueError, match="不支持"):
            Condition(field="BB", op="~=", value=1)


class TestRule:
    """Rule 评估测试。"""

    def test_all_conditions_must_match(self):
        rule = Rule(
            conditions=[
                Condition("BB", ">=", 2),
                Condition("CV", ">", 0),
            ],
            action=RuleAction.retreat(),
        )
        assert rule.evaluate({"BB": 3, "CV": 1})
        assert not rule.evaluate({"BB": 3, "CV": 0})
        assert not rule.evaluate({"BB": 1, "CV": 1})


class TestRuleEngine:
    """RuleEngine 测试。"""

    def test_first_match_wins(self):
        engine = RuleEngine(
            rules=[
                Rule([Condition("BB", ">=", 3)], RuleAction.retreat()),
                Rule([Condition("CV", ">", 0)], RuleAction.detour()),
            ]
        )
        # BB=3 matches first rule
        result = engine.evaluate({"BB": 3, "CV": 1})
        assert result.result == RuleResult.RETREAT

        # BB=1, CV=1 matches second rule
        result = engine.evaluate({"BB": 1, "CV": 1})
        assert result.result == RuleResult.DETOUR

    def test_default_action(self):
        engine = RuleEngine(
            rules=[Rule([Condition("BB", ">=", 10)], RuleAction.retreat())]
        )
        result = engine.evaluate({"BB": 1})
        assert result.result == RuleResult.NO_ACTION

    def test_from_legacy_rules(self):
        engine = RuleEngine.from_legacy_rules([
            ["(BB >= 2) and (CV > 0)", "retreat"],
            ["(SS >= 3)", 4],
        ])
        assert len(engine.rules) == 2

        result = engine.evaluate({"BB": 3, "CV": 1})
        assert result.result == RuleResult.RETREAT

        result = engine.evaluate({"SS": 3})
        assert result.result == RuleResult.FORMATION
        assert result.formation == Formation.wedge

    def test_from_formation_rules(self):
        engine = RuleEngine.from_formation_rules([
            ["单纵阵", "retreat"],
            ["复纵阵", 4],
        ])
        result = engine.evaluate_formation("单纵阵")
        assert result.result == RuleResult.RETREAT

        result = engine.evaluate_formation("复纵阵")
        assert result.result == RuleResult.FORMATION
        assert result.formation == Formation.wedge

        result = engine.evaluate_formation("轮型阵")
        assert result.result == RuleResult.NO_ACTION


class TestParseLegacyCondition:
    """旧格式条件解析测试。"""

    def test_simple(self):
        conditions = _parse_legacy_condition("(BB >= 2)")
        assert len(conditions) == 1
        assert conditions[0].field == "BB"
        assert conditions[0].op == ">="
        assert conditions[0].value == 2

    def test_compound_and(self):
        conditions = _parse_legacy_condition("(BB >= 2) and (CV > 0)")
        assert len(conditions) == 2
        assert conditions[0].field == "BB"
        assert conditions[1].field == "CV"

    def test_complex(self):
        conditions = _parse_legacy_condition("(SS >= 2) and (DD <= 3)")
        assert len(conditions) == 2
        assert conditions[0].field == "SS"
        assert conditions[0].op == ">="
        assert conditions[1].field == "DD"
        assert conditions[1].op == "<="

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="无法解析"):
            _parse_legacy_condition("hello world")


# ═══════════════════════════════════════════════════════════════════════════════
# history.py 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestFightResult:
    """FightResult 比较测试。"""

    def test_comparison(self):
        s = FightResult(grade="S")
        a = FightResult(grade="A")
        b = FightResult(grade="B")

        assert a < s
        assert b < a
        assert s > a
        assert s >= "S"
        assert a < "S"

    def test_str(self):
        fr = FightResult(mvp=3, grade="S")
        assert "MVP=3" in str(fr)
        assert "S" in str(fr)


class TestCombatHistory:
    """CombatHistory 测试。"""

    def test_add_and_reset(self):
        h = CombatHistory()
        h.add(CombatEvent(EventType.SPOT_ENEMY, node="A", action="战斗"))
        assert len(h) == 1
        h.reset()
        assert len(h) == 0

    def test_last_node(self):
        h = CombatHistory()
        h.add(CombatEvent(EventType.SPOT_ENEMY, node="A"))
        h.add(CombatEvent(EventType.RESULT, node="B"))
        assert h.last_node == "B"

    def test_get_fight_results(self):
        h = CombatHistory()
        h.add(CombatEvent(EventType.RESULT, node="A", result="S"))
        h.add(CombatEvent(EventType.RESULT, node="B", result="A"))
        results = h.get_fight_results()
        assert isinstance(results, dict)
        assert "A" in results
        assert "B" in results

    def test_str(self):
        h = CombatHistory()
        h.add(CombatEvent(EventType.SPOT_ENEMY, node="A", action="战斗"))
        text = str(h)
        assert "SPOT_ENEMY" in text
        assert "A" in text


# ═══════════════════════════════════════════════════════════════════════════════
# plan.py 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestNodeDecision:
    """NodeDecision 测试。"""

    def test_default_values(self):
        nd = NodeDecision()
        assert nd.formation == Formation.double_column
        assert nd.night is False
        assert nd.proceed is True
        assert nd.proceed_stop == 2

    def test_from_dict(self):
        nd = NodeDecision.from_dict({
            "formation": 1,
            "night": True,
            "proceed": False,
        })
        assert nd.formation == Formation.single_column
        assert nd.night is True
        assert nd.proceed is False


class TestCombatPlan:
    """CombatPlan 测试。"""

    def test_from_dict_basic(self):
        plan = CombatPlan.from_dict({
            "chapter": 5,
            "map": 4,
            "fleet_id": 1,
            "selected_nodes": ["A", "B", "C"],
            "node_defaults": {"formation": 2, "night": False},
            "node_args": {
                "C": {"formation": 1, "night": True},
            },
        })
        assert plan.chapter == 5
        assert plan.map_id == 4
        assert len(plan.selected_nodes) == 3
        assert plan.get_node_decision("A").formation == Formation.double_column
        assert plan.get_node_decision("C").formation == Formation.single_column
        assert plan.get_node_decision("C").night is True

    def test_is_selected_node(self):
        plan = CombatPlan(selected_nodes=["A", "B"])
        assert plan.is_selected_node("A") is True
        assert plan.is_selected_node("C") is False

    def test_empty_selected_nodes_allows_all(self):
        plan = CombatPlan(selected_nodes=[])
        assert plan.is_selected_node("A") is True

    def test_mode_transitions(self):
        plan = CombatPlan(mode=CombatMode.NORMAL)
        assert CombatPhase.PROCEED in plan.transitions
        assert plan.end_phase == CombatPhase.MAP_PAGE

        plan = CombatPlan(mode=CombatMode.BATTLE)
        assert plan.end_phase == CombatPhase.BATTLE_PAGE

    def test_with_enemy_rules(self):
        plan = CombatPlan.from_dict({
            "chapter": 1,
            "map": 1,
            "selected_nodes": ["A"],
            "node_args": {
                "A": {
                    "enemy_rules": [
                        ["(BB >= 2) and (CV > 0)", "retreat"],
                    ],
                },
            },
        })
        decision = plan.get_node_decision("A")
        assert decision.enemy_rules is not None
        result = decision.enemy_rules.evaluate({"BB": 3, "CV": 1})
        assert result.result == RuleResult.RETREAT


# ═══════════════════════════════════════════════════════════════════════════════
# actions.py 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestCheckBlood:
    """check_blood 测试。"""

    def test_all_green_continues(self):
        S = ShipDamageState
        R = RepairMode
        stats = [S.NORMAL, S.NORMAL, S.NORMAL, S.NORMAL, S.NORMAL, S.NORMAL]
        assert check_blood(stats, R.severe_damage) is True

    def test_severe_damage_stops(self):
        S = ShipDamageState
        R = RepairMode
        stats = [S.NORMAL, S.NORMAL, S.SEVERE, S.NORMAL, S.NORMAL, S.NORMAL]
        assert check_blood(stats, R.severe_damage) is False

    def test_moderate_damage_with_severe_rule(self):
        S = ShipDamageState
        R = RepairMode
        stats = [S.NORMAL, S.NORMAL, S.MODERATE, S.NORMAL, S.NORMAL, S.NORMAL]
        assert check_blood(stats, R.severe_damage) is True

    def test_no_ship_ignored(self):
        S = ShipDamageState
        R = RepairMode
        stats = [S.NORMAL, S.NORMAL, S.NORMAL, S.NO_SHIP, S.NO_SHIP, S.NO_SHIP]
        assert check_blood(stats, R.severe_damage) is True

    def test_per_position_rules(self):
        S = ShipDamageState
        R = RepairMode
        stats = [S.NORMAL, S.MODERATE, S.SEVERE, S.NORMAL, S.NORMAL, S.NORMAL]
        rules = [R.severe_damage, R.moderate_damage, R.severe_damage, R.severe_damage, R.severe_damage, R.severe_damage]
        assert check_blood(stats, rules) is False  # position 1 has MODERATE >= moderate_damage

    def test_severe_always_stops(self):
        S = ShipDamageState
        R = RepairMode
        stats = [S.NORMAL, S.NORMAL, S.SEVERE, S.NORMAL, S.NORMAL, S.NORMAL]
        assert check_blood(stats, R.severe_damage) is False

    def test_moderate_stops_with_moderate_rule(self):
        S = ShipDamageState
        R = RepairMode
        stats = [S.NORMAL, S.MODERATE, S.NORMAL, S.NORMAL, S.NORMAL, S.NORMAL]
        assert check_blood(stats, R.moderate_damage) is False
