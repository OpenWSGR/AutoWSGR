"""测试 autowsgr.combat.rules."""

from __future__ import annotations

import pytest

from autowsgr.combat.rules import (
    Condition,
    Rule,
    RuleAction,
    RuleEngine,
    RuleResult,
    _parse_action_value,
    _parse_legacy_condition,
)
from autowsgr.types import Formation


# 1. RuleResult values exist


def test_rule_result_members() -> None:
    assert RuleResult.NO_ACTION is not None
    assert RuleResult.RETREAT is not None
    assert RuleResult.DETOUR is not None
    assert RuleResult.FORMATION is not None
    assert len(RuleResult) == 4


# 2. RuleAction factories return correct objects


def test_rule_action_no_action() -> None:
    action = RuleAction.no_action()
    assert action.result == RuleResult.NO_ACTION
    assert action.formation is None


def test_rule_action_retreat() -> None:
    action = RuleAction.retreat()
    assert action.result == RuleResult.RETREAT
    assert action.formation is None


def test_rule_action_detour() -> None:
    action = RuleAction.detour()
    assert action.result == RuleResult.DETOUR
    assert action.formation is None


def test_rule_action_set_formation() -> None:
    action = RuleAction.set_formation(Formation.wedge)
    assert action.result == RuleResult.FORMATION
    assert action.formation == Formation.wedge


# 3. Condition validates operator, evaluates simple/combined/missing fields, all 6 operators


def test_condition_invalid_operator_raises() -> None:
    with pytest.raises(ValueError, match='不支持的操作符'):
        Condition(field='BB', op='~~', value=2)


@pytest.mark.parametrize(
    ('op', 'value', 'context', 'expected'),
    [
        ('>', 2, {'BB': 3}, True),
        ('>', 2, {'BB': 1}, False),
        ('>=', 2, {'BB': 2}, True),
        ('>=', 2, {'BB': 1}, False),
        ('<', 2, {'BB': 1}, True),
        ('<', 2, {'BB': 3}, False),
        ('<=', 2, {'BB': 2}, True),
        ('<=', 2, {'BB': 3}, False),
        ('==', 2, {'BB': 2}, True),
        ('==', 2, {'BB': 3}, False),
        ('!=', 2, {'BB': 3}, True),
        ('!=', 2, {'BB': 2}, False),
    ],
)
def test_condition_operators(op: str, value: int, context: dict[str, int], expected: bool) -> None:
    cond = Condition(field='BB', op=op, value=value)
    assert cond.evaluate(context) == expected


def test_condition_combined_fields() -> None:
    cond = Condition(field='CL+DD', op='>=', value=5)
    assert cond.evaluate({'CL': 2, 'DD': 3}) is True
    assert cond.evaluate({'CL': 1, 'DD': 3}) is False


def test_condition_missing_field_defaults_to_zero() -> None:
    cond = Condition(field='CV', op='==', value=0)
    assert cond.evaluate({'BB': 2}) is True


def test_condition_combined_with_missing_field() -> None:
    cond = Condition(field='BB+CV', op='==', value=2)
    assert cond.evaluate({'BB': 2}) is True


# 4. Rule AND semantics


def test_rule_and_semantics_all_match() -> None:
    rule = Rule(
        conditions=[
            Condition(field='BB', op='>=', value=2),
            Condition(field='CV', op='>', value=0),
        ],
        action=RuleAction.retreat(),
    )
    assert rule.evaluate({'BB': 2, 'CV': 1}) is True


def test_rule_and_semantics_partial_match() -> None:
    rule = Rule(
        conditions=[
            Condition(field='BB', op='>=', value=2),
            Condition(field='CV', op='>', value=0),
        ],
        action=RuleAction.retreat(),
    )
    assert rule.evaluate({'BB': 2, 'CV': 0}) is False
    assert rule.evaluate({'BB': 1, 'CV': 1}) is False


# 5. RuleEngine first-match, default action


def test_rule_engine_first_match_priority() -> None:
    engine = RuleEngine(
        rules=[
            Rule(
                conditions=[Condition(field='BB', op='>=', value=3)],
                action=RuleAction.retreat(),
            ),
            Rule(
                conditions=[Condition(field='BB', op='>=', value=2)],
                action=RuleAction.detour(),
            ),
        ],
        default=RuleAction.no_action(),
    )
    assert engine.evaluate({'BB': 3}) == RuleAction.retreat()
    assert engine.evaluate({'BB': 2}) == RuleAction.detour()


def test_rule_engine_default_action() -> None:
    engine = RuleEngine(
        rules=[
            Rule(
                conditions=[Condition(field='SS', op='>=', value=3)],
                action=RuleAction.retreat(),
            ),
        ],
        default=RuleAction.no_action(),
    )
    assert engine.evaluate({'BB': 1}) == RuleAction.no_action()


# 6. _parse_legacy_condition


def test_parse_legacy_condition_basic() -> None:
    conds = _parse_legacy_condition('(BB >= 2) and (CV > 0)')
    assert len(conds) == 2
    assert conds[0] == Condition(field='BB', op='>=', value=2)
    assert conds[1] == Condition(field='CV', op='>', value=0)


def test_parse_legacy_condition_combined_fields() -> None:
    conds = _parse_legacy_condition('CL + DD >= 1')
    assert len(conds) == 1
    assert conds[0] == Condition(field='CL+DD', op='>=', value=1)


def test_parse_legacy_condition_decimal() -> None:
    conds = _parse_legacy_condition('BB >= 2.5')
    assert len(conds) == 1
    assert conds[0] == Condition(field='BB', op='>=', value=2.5)
    assert isinstance(conds[0].value, float)


def test_parse_legacy_condition_malformed_raises() -> None:
    with pytest.raises(ValueError, match='无法解析规则条件'):
        _parse_legacy_condition('not a condition')


# 7. _parse_action_value


def test_parse_action_value_retreat() -> None:
    assert _parse_action_value('retreat') == RuleAction.retreat()


def test_parse_action_value_detour() -> None:
    assert _parse_action_value('detour') == RuleAction.detour()


def test_parse_action_value_int_formation() -> None:
    action = _parse_action_value(4)
    assert action == RuleAction.set_formation(Formation.wedge)


def test_parse_action_value_string_number_fallback() -> None:
    action = _parse_action_value('4')
    assert action == RuleAction.set_formation(Formation.wedge)


def test_parse_action_value_invalid_raises() -> None:
    with pytest.raises(ValueError, match='无法识别的动作值'):
        _parse_action_value('flyaway')


# 8. from_legacy_rules end-to-end


def test_from_legacy_rules_end_to_end() -> None:
    engine = RuleEngine.from_legacy_rules(
        [
            ['(BB >= 2) and (CV > 0)', 'retreat'],
            ['(SS >= 3)', 4],
        ]
    )
    assert len(engine.rules) == 2

    assert engine.evaluate({'BB': 3, 'CV': 1}) == RuleAction.retreat()
    assert engine.evaluate({'BB': 2, 'CV': 0}) == RuleAction.no_action()

    action = engine.evaluate({'SS': 3})
    assert action == RuleAction.set_formation(Formation.wedge)


# 9. from_formation_rules end-to-end


def test_from_formation_rules_end_to_end() -> None:
    engine = RuleEngine.from_formation_rules(
        [
            ['单纵阵', 'retreat'],
            ['复纵阵', 4],
        ]
    )
    assert len(engine.rules) == 2

    assert engine.evaluate_formation('单纵阵') == RuleAction.retreat()
    assert engine.evaluate_formation('复纵阵') == RuleAction.set_formation(Formation.wedge)
    assert engine.evaluate_formation('轮型阵') == RuleAction.no_action()


# 10. evaluate_formation with matching/non-matching formation


def test_evaluate_formation_matching() -> None:
    engine = RuleEngine.from_formation_rules(
        [
            ['梯形阵', 'detour'],
        ]
    )
    assert engine.evaluate_formation('梯形阵') == RuleAction.detour()


def test_evaluate_formation_non_matching() -> None:
    engine = RuleEngine.from_formation_rules(
        [
            ['梯形阵', 'detour'],
        ]
    )
    assert engine.evaluate_formation('单横阵') == RuleAction.no_action()
