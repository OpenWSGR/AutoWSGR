"""战斗系统单元测试。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from autowsgr.combat.actions import check_blood
from autowsgr.combat.fleet import FleetSlotRule, ShipSelector
from autowsgr.combat.history import (
    CombatEvent,
    CombatHistory,
    EventType,
    FightResult,
)
from autowsgr.combat.node_tracker import MapNodeData, _resolve_event_map_path
from autowsgr.combat.plan import (
    _MODE_SPECS,
    MODE_TRANSITIONS,
    CombatMode,
    CombatPlan,
    NodeDecision,
    parse_map_value,
)
from autowsgr.combat.rules import (
    Condition,
    Rule,
    RuleAction,
    RuleEngine,
    RuleResult,
    _parse_legacy_condition,
)
from autowsgr.combat.state import (
    CombatPhase,
    ModeCategory,
    build_transitions,
    resolve_successors,
)
from autowsgr.types import Formation, RepairMode, ShipDamageState, ShipType


if TYPE_CHECKING:
    from pathlib import Path


# ═══════════════════════════════════════════════════════════════════════════════
# state.py 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestResolveSuccessors:
    """状态转移解析测试。"""

    def test_normal_proceed_yes(self):
        normal = MODE_TRANSITIONS[CombatMode.NORMAL]
        result = resolve_successors(normal, CombatPhase.PROCEED, 'yes')
        assert CombatPhase.FIGHT_CONDITION in result
        assert CombatPhase.MAP_PAGE in result

    def test_normal_proceed_no(self):
        normal = MODE_TRANSITIONS[CombatMode.NORMAL]
        result = resolve_successors(normal, CombatPhase.PROCEED, 'no')
        assert result == [CombatPhase.MAP_PAGE]

    def test_normal_night_no(self):
        normal = MODE_TRANSITIONS[CombatMode.NORMAL]
        result = resolve_successors(normal, CombatPhase.NIGHT_PROMPT, 'no')
        assert result == [CombatPhase.RESULT]

    def test_normal_formation_no_branch(self):
        normal = MODE_TRANSITIONS[CombatMode.NORMAL]
        result = resolve_successors(normal, CombatPhase.FORMATION, '')
        assert CombatPhase.FIGHT_PERIOD in result

    def test_battle_transitions(self):
        battle = MODE_TRANSITIONS[CombatMode.BATTLE]
        # SINGLE 模式无 PROCEED，直接从 START_FIGHT 开始
        result = resolve_successors(battle, CombatPhase.START_FIGHT, '')
        assert CombatPhase.SPOT_ENEMY_SUCCESS in result
        assert CombatPhase.FORMATION in result

    def test_exercise_transitions(self):
        exercise = MODE_TRANSITIONS[CombatMode.EXERCISE]
        # 演习: RESULT → 经验结算 → 结束页 (两跳)
        result = resolve_successors(exercise, CombatPhase.RESULT, '')
        assert result == [CombatPhase.EXP_SETTLEMENT]
        result = resolve_successors(exercise, CombatPhase.EXP_SETTLEMENT, '')
        assert CombatPhase.EXERCISE_PAGE in result

    def test_unknown_phase_raises(self):
        normal = MODE_TRANSITIONS[CombatMode.NORMAL]
        with pytest.raises(KeyError):
            resolve_successors(normal, CombatPhase.EXERCISE_PAGE, '')

    def test_spot_enemy_retreat_branch(self):
        normal = MODE_TRANSITIONS[CombatMode.NORMAL]
        result = resolve_successors(normal, CombatPhase.SPOT_ENEMY_SUCCESS, 'retreat')
        assert result == [CombatPhase.MAP_PAGE]

    def test_spot_enemy_fight_branch(self):
        normal = MODE_TRANSITIONS[CombatMode.NORMAL]
        result = resolve_successors(normal, CombatPhase.SPOT_ENEMY_SUCCESS, 'fight')
        assert CombatPhase.FORMATION in result
        assert CombatPhase.MISSILE_ANIMATION in result

    def test_build_transitions_categories(self):
        """ModeCategory + build_transitions 一致性检查。"""
        for cat, ep in _MODE_SPECS.values():
            t = build_transitions(cat, ep)
            # 核心循环必须存在
            assert CombatPhase.FIGHT_PERIOD in t
            assert CombatPhase.NIGHT_PROMPT in t
            # MAP 模式有导弹支援和战況选择
            if cat == ModeCategory.MAP:
                assert CombatPhase.MISSILE_ANIMATION in t
                assert CombatPhase.FIGHT_CONDITION in t
            else:
                assert CombatPhase.MISSILE_ANIMATION not in t
                assert CombatPhase.FIGHT_CONDITION not in t


# ═══════════════════════════════════════════════════════════════════════════════
# rules.py 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestCondition:
    """Condition 评估测试。"""

    def test_greater(self):
        c = Condition(field='BB', op='>=', value=2)
        assert c.evaluate({'BB': 2})
        assert c.evaluate({'BB': 3})
        assert not c.evaluate({'BB': 1})

    def test_less_than(self):
        c = Condition(field='CV', op='<', value=2)
        assert c.evaluate({'CV': 1})
        assert not c.evaluate({'CV': 2})

    def test_missing_field(self):
        c = Condition(field='SS', op='>', value=0)
        assert not c.evaluate({'BB': 1})  # SS defaults to 0

    def test_invalid_op(self):
        with pytest.raises(ValueError, match='不支持'):
            Condition(field='BB', op='~=', value=1)


class TestRule:
    """Rule 评估测试。"""

    def test_all_conditions_must_match(self):
        rule = Rule(
            conditions=[
                Condition('BB', '>=', 2),
                Condition('CV', '>', 0),
            ],
            action=RuleAction.retreat(),
        )
        assert rule.evaluate({'BB': 3, 'CV': 1})
        assert not rule.evaluate({'BB': 3, 'CV': 0})
        assert not rule.evaluate({'BB': 1, 'CV': 1})


class TestRuleEngine:
    """RuleEngine 测试。"""

    def test_first_match_wins(self):
        engine = RuleEngine(
            rules=[
                Rule([Condition('BB', '>=', 3)], RuleAction.retreat()),
                Rule([Condition('CV', '>', 0)], RuleAction.detour()),
            ]
        )
        # BB=3 matches first rule
        result = engine.evaluate({'BB': 3, 'CV': 1})
        assert result.result == RuleResult.RETREAT

        # BB=1, CV=1 matches second rule
        result = engine.evaluate({'BB': 1, 'CV': 1})
        assert result.result == RuleResult.DETOUR

    def test_default_action(self):
        engine = RuleEngine(rules=[Rule([Condition('BB', '>=', 10)], RuleAction.retreat())])
        result = engine.evaluate({'BB': 1})
        assert result.result == RuleResult.NO_ACTION

    def test_from_legacy_rules(self):
        engine = RuleEngine.from_legacy_rules(
            [
                ['(BB >= 2) and (CV > 0)', 'retreat'],
                ['(SS >= 3)', 4],
            ]
        )
        assert len(engine.rules) == 2

        result = engine.evaluate({'BB': 3, 'CV': 1})
        assert result.result == RuleResult.RETREAT

        result = engine.evaluate({'SS': 3})
        assert result.result == RuleResult.FORMATION
        assert result.formation == Formation.wedge

    def test_from_formation_rules(self):
        engine = RuleEngine.from_formation_rules(
            [
                ['单纵阵', 'retreat'],
                ['复纵阵', 4],
            ]
        )
        result = engine.evaluate_formation('单纵阵')
        assert result.result == RuleResult.RETREAT

        result = engine.evaluate_formation('复纵阵')
        assert result.result == RuleResult.FORMATION
        assert result.formation == Formation.wedge

        result = engine.evaluate_formation('轮型阵')
        assert result.result == RuleResult.NO_ACTION


class TestParseLegacyCondition:
    """旧格式条件解析测试。"""

    def test_simple(self):
        conditions = _parse_legacy_condition('(BB >= 2)')
        assert len(conditions) == 1
        assert conditions[0].field == 'BB'
        assert conditions[0].op == '>='
        assert conditions[0].value == 2

    def test_compound_and(self):
        conditions = _parse_legacy_condition('(BB >= 2) and (CV > 0)')
        assert len(conditions) == 2
        assert conditions[0].field == 'BB'
        assert conditions[1].field == 'CV'

    def test_complex(self):
        conditions = _parse_legacy_condition('(SS >= 2) and (DD <= 3)')
        assert len(conditions) == 2
        assert conditions[0].field == 'SS'
        assert conditions[0].op == '>='
        assert conditions[1].field == 'DD'
        assert conditions[1].op == '<='

    def test_sum_expression(self):
        conditions = _parse_legacy_condition('(CL + DD >= 1)')
        assert len(conditions) == 1
        assert conditions[0].field == 'CL+DD'
        assert conditions[0].op == '>='
        assert conditions[0].value == 1

    def test_sum_expression_triple(self):
        conditions = _parse_legacy_condition('(CL + DD + CA >= 3)')
        assert len(conditions) == 1
        assert conditions[0].field == 'CL+DD+CA'
        assert conditions[0].op == '>='
        assert conditions[0].value == 3

    def test_sum_compound_and(self):
        conditions = _parse_legacy_condition('(CL + DD >= 1) and (BB >= 2)')
        assert len(conditions) == 2
        assert conditions[0].field == 'CL+DD'
        assert conditions[1].field == 'BB'

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match='无法解析'):
            _parse_legacy_condition('hello world')

    @pytest.mark.parametrize(
        'condition',
        [
            'BB > 0 trailing garbage',
            'BB > 0 or CV > 0',
            '',
            '   ',
            'BB > 0 and',
        ],
    )
    def test_rejects_unsupported_or_trailing_tokens(self, condition: str):
        with pytest.raises(ValueError, match='无法解析'):
            _parse_legacy_condition(condition)

    def test_rejects_or_instead_of_changing_to_and(self):
        with pytest.raises(ValueError, match='无法解析'):
            RuleEngine.from_legacy_rules([['BB > 0 or CV > 0', 'retreat']])

    @pytest.mark.parametrize('condition', ['SAP != 1', 'ZZ > 0'])
    def test_rejects_unknown_ship_type_codes(self, condition: str):
        with pytest.raises(ValueError, match='未知舰种代码'):
            _parse_legacy_condition(condition)

    def test_accepts_total_ship_count_code(self):
        assert _parse_legacy_condition('ALL == 6') == [
            Condition(field='ALL', op='==', value=6),
        ]

    @pytest.mark.parametrize(
        'condition',
        [
            '(BB > 0',
            'BB > 0)',
            'BB > 0) and (CV > 0',
            '(BB > 0 and (CV > 0)',
            'BB > 0 and CV > 0)',
        ],
    )
    def test_rejects_unbalanced_parentheses(self, condition: str):
        with pytest.raises(ValueError, match='无法解析'):
            _parse_legacy_condition(condition)

    @pytest.mark.parametrize(
        ('condition', 'canonical_field'),
        [('NAP > 0', 'AP'), ('CBG > 0', 'BG')],
    )
    def test_unambiguous_legacy_ship_codes_are_normalized(
        self,
        condition: str,
        canonical_field: str,
    ):
        assert _parse_legacy_condition(condition)[0].field == canonical_field

    def test_ambiguous_bg_rule_requires_explicit_migration(self):
        with pytest.raises(ValueError, match=r'CBG.*BBG'):
            _parse_legacy_condition('BG > 0')

    def test_rejects_boolean_formation_action(self):
        with pytest.raises(ValueError, match='无法识别的动作值'):
            RuleEngine.from_legacy_rules([['BB > 0', True]])

    def test_action_strings_ignore_surrounding_whitespace(self):
        engine = RuleEngine.from_legacy_rules([['BB > 0', ' retreat ']])

        assert engine.evaluate({'BB': 1}).result is RuleResult.RETREAT


class TestConditionSumEvaluation:
    """Condition '+' sum evaluation tests."""

    def test_sum_basic(self):
        c = Condition(field='CL+DD', op='>=', value=2)
        assert c.evaluate({'CL': 1, 'DD': 1})
        assert c.evaluate({'CL': 2, 'DD': 0})
        assert not c.evaluate({'CL': 0, 'DD': 1})

    def test_sum_missing_fields(self):
        c = Condition(field='CL+DD', op='>=', value=1)
        assert c.evaluate({'CL': 1})
        assert not c.evaluate({'BB': 5})

    def test_sum_legacy_roundtrip(self):
        engine = RuleEngine.from_legacy_rules([['(CL + DD >= 2) and (BB > 0)', 'retreat']])
        assert engine.evaluate({'CL': 1, 'DD': 1, 'BB': 1}).result == RuleResult.RETREAT
        assert engine.evaluate({'CL': 0, 'DD': 0, 'BB': 3}).result == RuleResult.NO_ACTION


# ═══════════════════════════════════════════════════════════════════════════════
# history.py 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestFightResult:
    """FightResult 比较测试。"""

    def test_comparison(self):
        s = FightResult(grade='S')
        a = FightResult(grade='A')
        b = FightResult(grade='B')

        assert a < s
        assert b < a
        assert s > a
        assert s >= 'S'
        assert a < 'S'

    def test_str(self):
        fr = FightResult(mvp=3, grade='S')
        assert 'MVP=3' in str(fr)
        assert 'S' in str(fr)


class TestCombatHistory:
    """CombatHistory 测试。"""

    def test_add_and_reset(self):
        h = CombatHistory()
        h.add(CombatEvent(EventType.SPOT_ENEMY, node='A', action='战斗'))
        assert len(h) == 1
        h.reset()
        assert len(h) == 0

    def test_last_node(self):
        h = CombatHistory()
        h.add(CombatEvent(EventType.SPOT_ENEMY, node='A'))
        h.add(CombatEvent(EventType.RESULT, node='B'))
        assert h.last_node == 'B'

    def test_get_fight_results(self):
        h = CombatHistory()
        h.add(CombatEvent(EventType.RESULT, node='A', result='S'))
        h.add(CombatEvent(EventType.RESULT, node='B', result='A'))
        results = h.get_fight_results()
        assert isinstance(results, dict)
        assert 'A' in results
        assert 'B' in results

    def test_str(self):
        h = CombatHistory()
        h.add(CombatEvent(EventType.SPOT_ENEMY, node='A', action='战斗'))
        text = str(h)
        assert 'SPOT_ENEMY' in text
        assert 'A' in text


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
        nd = NodeDecision.from_dict(
            {
                'formation': 1,
                'night': True,
                'proceed': False,
            }
        )
        assert nd.formation == Formation.single_column
        assert nd.night is True
        assert nd.proceed is False


class TestCombatPlan:
    """CombatPlan 测试。"""

    def test_from_dict_basic(self):
        plan = CombatPlan.from_dict(
            {
                'chapter': 5,
                'map': 4,
                'fleet_id': 1,
                'selected_nodes': ['A', 'B', 'C'],
                'node_defaults': {'formation': 2, 'night': False},
                'node_args': {
                    'C': {'formation': 1, 'night': True},
                },
            }
        )
        assert plan.chapter == 5
        assert plan.map_id == 4
        assert len(plan.selected_nodes) == 3
        assert plan.get_node_decision('A').formation == Formation.double_column
        assert plan.get_node_decision('C').formation == Formation.single_column
        assert plan.get_node_decision('C').night is True

    def test_is_selected_node(self):
        plan = CombatPlan(selected_nodes=['A', 'B'])
        assert plan.is_selected_node('A') is True
        assert plan.is_selected_node('C') is False

    def test_empty_selected_nodes_allows_all(self):
        plan = CombatPlan(selected_nodes=[])
        assert plan.is_selected_node('A') is True

    def test_mode_transitions(self):
        plan = CombatPlan(mode=CombatMode.NORMAL)
        assert CombatPhase.PROCEED in plan.transitions
        assert plan.end_phase == CombatPhase.MAP_PAGE

        plan = CombatPlan(mode=CombatMode.BATTLE)
        assert plan.end_phase == CombatPhase.RESULT

    def test_with_enemy_rules(self):
        plan = CombatPlan.from_dict(
            {
                'chapter': 1,
                'map': 1,
                'selected_nodes': ['A'],
                'node_args': {
                    'A': {
                        'enemy_rules': [
                            ['(BB >= 2) and (CV > 0)', 'retreat'],
                        ],
                    },
                },
            }
        )
        decision = plan.get_node_decision('A')
        assert decision.enemy_rules is not None
        result = decision.enemy_rules.evaluate({'BB': 3, 'CV': 1})
        assert result.result == RuleResult.RETREAT


class TestFleetPresetsParsing:
    """fleet_presets 解析测试。"""

    def test_missing_presets_keeps_legacy_fleet(self):
        """未配置预设时，旧 fleet 字段保持不变。"""
        plan = CombatPlan.from_dict({'fleet': ['飞龙', 'U-1206']})
        assert plan.fleet == ['飞龙', 'U-1206']
        assert plan.fleet_presets is None

    @pytest.mark.parametrize('invalid_presets', [{}, 'preset', 1])
    def test_presets_must_be_list(self, invalid_presets: object):
        """fleet_presets 顶层必须使用列表。"""
        with pytest.raises(TypeError, match='fleet_presets 必须是列表'):
            CombatPlan.from_dict({'fleet_presets': invalid_presets})

    def test_empty_presets_is_preserved(self):
        """空列表由上层决定业务含义。"""
        plan = CombatPlan.from_dict({'fleet_presets': []})
        assert plan.fleet_presets == ()

    def test_preset_content_is_normalized(self):
        """旧字符串候选保留为有序候选规则。"""
        plan = CombatPlan.from_dict(
            {
                'fleet_presets': [
                    {
                        'name': ' 测试舰队 ',
                        'ships': [
                            ' 飞龙·改 ',
                            {
                                'candidates': [' 岛风 ', '黑潮', '岛风'],
                                'ship_type': ' dd ',
                                'min_level': 100,
                            },
                        ],
                    },
                ],
            },
        )

        assert plan.fleet_presets is not None
        preset = plan.fleet_presets[0]
        assert preset.name == '测试舰队'
        assert preset.slots[0] == FleetSlotRule(primary=ShipSelector(name='飞龙·改'))
        assert preset.slots[1] == FleetSlotRule(
            candidates=(
                ShipSelector(name='岛风', ship_types=(ShipType.DD,), min_level=100),
                ShipSelector(name='黑潮', ship_types=(ShipType.DD,), min_level=100),
            ),
        )

    def test_independent_candidate_rules_are_preserved(self):
        """主选和每个备选分别保留自己的舰种及等级范围。"""
        plan = CombatPlan.from_dict(
            {
                'fleet_presets': [
                    {
                        'name': '潜艇队',
                        'ships': [
                            {
                                'name': 'U-47',
                                'ship_type': ['SS', 'SSG'],
                                'min_level': 100,
                                'max_level': 110,
                                'candidates': [
                                    {
                                        'name': 'U-96',
                                        'ship_type': ['SS'],
                                        'min_level': 90,
                                        'max_level': 105,
                                    },
                                    {
                                        'name': 'U-47',
                                        'ship_type': ['SS'],
                                        'min_level': 100,
                                        'max_level': 110,
                                    },
                                ],
                            },
                        ],
                    },
                ],
            },
        )

        assert plan.fleet_presets is not None
        slot = plan.fleet_presets[0].slots[0]
        assert slot.primary == ShipSelector(
            name='U-47',
            ship_types=(ShipType.SS, ShipType.SSG),
            min_level=100,
            max_level=110,
        )
        assert slot.candidates == (
            ShipSelector(
                name='U-96',
                ship_types=(ShipType.SS,),
                min_level=90,
                max_level=105,
            ),
            ShipSelector(
                name='U-47',
                ship_types=(ShipType.SS,),
                min_level=100,
                max_level=110,
            ),
        )

    def test_candidate_only_slots_are_preserved(self):
        """结构化纯备选位置不把第一候选提升为严格主选。"""
        plan = CombatPlan.from_dict(
            {
                'fleet_presets': [
                    {
                        'name': '纯备选',
                        'ships': [
                            {
                                'candidates': [
                                    {'name': ' 胡德 ', 'ship_type': ['BC']},
                                    {
                                        'name': '扶桑',
                                        'ship_type': ['BB'],
                                        'min_level': 80,
                                        'max_level': 110,
                                    },
                                ],
                            },
                        ],
                    },
                ],
            },
        )

        assert plan.fleet_presets is not None
        slot = plan.fleet_presets[0].slots[0]
        assert slot.primary is None
        assert slot.candidates == (
            ShipSelector(
                name='胡德',
                ship_types=(ShipType.BC,),
            ),
            ShipSelector(
                name='扶桑',
                ship_types=(ShipType.BB,),
                min_level=80,
                max_level=110,
            ),
        )

    def test_slot_fields_are_converted_to_domain_model(self):
        """解析阶段把槽位字段转换成 canonical model。"""
        plan = CombatPlan.from_dict(
            {
                'fleet_presets': [
                    {
                        'ships': [
                            {'name': '契卡洛夫', 'max_level': 110},
                        ],
                    },
                ],
            },
        )
        assert plan.fleet_presets is not None
        assert plan.fleet_presets[0].slots == (
            FleetSlotRule(
                primary=ShipSelector(name='契卡洛夫', max_level=110),
            ),
        )

    def test_legacy_candidate_only_keeps_search_name_on_each_candidate(self):
        """旧字符串候选不提升主选，槽位搜索名不改变候选身份。"""
        plan = CombatPlan.from_dict(
            {
                'fleet_presets': [
                    {
                        'ships': [
                            {
                                'search_name': '契卡洛夫',
                                'candidates': ['85工程', '岛风'],
                            },
                        ],
                    },
                ],
            },
        )

        assert plan.fleet_presets is not None
        slot = plan.fleet_presets[0].slots[0]
        assert slot.primary is None
        assert [candidate.name for candidate in slot.candidates] == ['85工程', '岛风']

    def test_same_name_candidates_keep_distinct_rules_and_order(self):
        plan = CombatPlan.from_dict(
            {
                'fleet_presets': [
                    {
                        'ships': [
                            {
                                'candidates': [
                                    {'name': '大淀', 'search_name': '大淀'},
                                    {'name': '大淀', 'search_name': '大淀·改'},
                                ],
                            },
                        ],
                    },
                ],
            },
        )

        assert plan.fleet_presets is not None
        assert plan.fleet_presets[0].slots[0].candidates == (
            ShipSelector(name='大淀', search_name='大淀'),
            ShipSelector(name='大淀', search_name='大淀·改'),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# actions.py 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestCheckBlood:
    """check_blood 测试。"""

    def test_all_green_continues(self):
        s = ShipDamageState
        r = RepairMode
        stats = [s.NORMAL, s.NORMAL, s.NORMAL, s.NORMAL, s.NORMAL, s.NORMAL]
        assert check_blood(stats, r.severe_damage) is True

    def test_severe_damage_stops(self):
        s = ShipDamageState
        r = RepairMode
        stats = [s.NORMAL, s.NORMAL, s.SEVERE, s.NORMAL, s.NORMAL, s.NORMAL]
        assert check_blood(stats, r.severe_damage) is False

    def test_moderate_damage_with_severe_rule(self):
        s = ShipDamageState
        r = RepairMode
        stats = [s.NORMAL, s.NORMAL, s.MODERATE, s.NORMAL, s.NORMAL, s.NORMAL]
        assert check_blood(stats, r.severe_damage) is True

    def test_no_ship_ignored(self):
        s = ShipDamageState
        r = RepairMode
        stats = [s.NORMAL, s.NORMAL, s.NORMAL, s.NO_SHIP, s.NO_SHIP, s.NO_SHIP]
        assert check_blood(stats, r.severe_damage) is True

    def test_per_position_rules(self):
        s = ShipDamageState
        r = RepairMode
        stats = [s.NORMAL, s.MODERATE, s.SEVERE, s.NORMAL, s.NORMAL, s.NORMAL]
        rules = [
            r.severe_damage,
            r.moderate_damage,
            r.severe_damage,
            r.severe_damage,
            r.severe_damage,
            r.severe_damage,
        ]
        assert check_blood(stats, rules) is False  # position 1 has MODERATE >= moderate_damage

    def test_severe_always_stops(self):
        s = ShipDamageState
        r = RepairMode
        stats = [s.NORMAL, s.NORMAL, s.SEVERE, s.NORMAL, s.NORMAL, s.NORMAL]
        assert check_blood(stats, r.severe_damage) is False

    def test_moderate_stops_with_moderate_rule(self):
        s = ShipDamageState
        r = RepairMode
        stats = [s.NORMAL, s.MODERATE, s.NORMAL, s.NORMAL, s.NORMAL, s.NORMAL]
        assert check_blood(stats, r.moderate_damage) is False


# ═══════════════════════════════════════════════════════════════════════════════
# parse_map_value / entrance 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestParseMapValue:
    """parse_map_value 测试 (map 字段 → map_id + entrance)。"""

    def test_int(self):
        assert parse_map_value(5) == (5, None)

    def test_str_int(self):
        assert parse_map_value('1') == (1, None)

    def test_entrance_a(self):
        assert parse_map_value('1a') == (1, 'a')

    def test_entrance_b_upper(self):
        assert parse_map_value('3B') == (3, 'b')

    def test_whitespace(self):
        assert parse_map_value('  2A  ') == (2, 'a')

    def test_invalid_letters(self):
        with pytest.raises(ValueError, match='无法解析'):
            parse_map_value('1c')

    def test_invalid_non_numeric(self):
        with pytest.raises(ValueError, match='无法解析'):
            parse_map_value('abc')


class TestCombatPlanEntrance:
    """CombatPlan.entrance 从 map 字段解析。"""

    def test_entrance_from_map(self):
        plan = CombatPlan.from_dict({'chapter': 'H', 'map': '1a'})
        assert plan.map_id == 1
        assert plan.entrance == 'a'

    def test_no_entrance_pure_int(self):
        plan = CombatPlan.from_dict({'chapter': 5, 'map': 4})
        assert plan.map_id == 4
        assert plan.entrance is None

    def test_default_map_is_none(self):
        plan = CombatPlan.from_dict({})
        assert plan.entrance is None


# ═══════════════════════════════════════════════════════════════════════════════
# node_tracker load_event 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestResolveEventMapPath:
    """_resolve_event_map_path 中文命名 glob 测试 (自包含, 不依赖真实数据)。"""

    @pytest.fixture
    def event_root(self, tmp_path: Path) -> Path:
        """构造含中文命名地图文件的临时活动目录。"""
        d = tmp_path / '20260730'
        d.mkdir()
        yaml_body = 'A:\n  position: [0.1, 0.2]\n  next: []\n'
        (d / '激斗漩涡-Ex-1-α.yaml').write_text(yaml_body, encoding='utf-8')
        (d / '激斗漩涡-Ex-1-β.yaml').write_text(yaml_body, encoding='utf-8')
        (d / '激斗漩涡H-Ex-1-α.yaml').write_text(yaml_body, encoding='utf-8')
        (d / '激斗漩涡H-Ex-1-β.yaml').write_text(yaml_body, encoding='utf-8')
        return tmp_path

    def test_hard_alpha(self, event_root: Path) -> None:
        path = _resolve_event_map_path(event_root, '20260730', 'H', 1, 'a')
        assert path is not None
        assert path.name == '激斗漩涡H-Ex-1-α.yaml'

    def test_easy_alpha_excludes_hard(self, event_root: Path) -> None:
        """E 章 glob 须排除文件名含 H-Ex 的困难文件。"""
        path = _resolve_event_map_path(event_root, '20260730', 'E', 1, 'a')
        assert path is not None
        assert path.name == '激斗漩涡-Ex-1-α.yaml'

    def test_beta(self, event_root: Path) -> None:
        path = _resolve_event_map_path(event_root, '20260730', 'H', 1, 'b')
        assert path is not None
        assert path.name == '激斗漩涡H-Ex-1-β.yaml'

    def test_missing_returns_none(self, event_root: Path) -> None:
        assert _resolve_event_map_path(event_root, '20260730', 'H', 99, 'a') is None

    def test_no_entrance_legacy_naming(self, event_root: Path) -> None:
        """entrance=None 走旧命名 {chapter}-{map}.yaml。"""
        (event_root / '20260730' / 'H-1.yaml').write_text(
            'A:\n  position: [0.1, 0.2]\n  next: []\n',
            encoding='utf-8',
        )
        path = _resolve_event_map_path(event_root, '20260730', 'H', 1, None)
        assert path is not None
        assert path.name == 'H-1.yaml'


class TestLoadEvent:
    """MapNodeData.load_event 集成测试 (加载真实包数据文件)。"""

    def test_load_real_hard_alpha(self):
        """加载真实激斗漩涡 H1 α 地图文件。"""
        data = MapNodeData.load_event('20260730', 'H', 1, 'a')
        assert data is not None
        assert 'A' in data
        # 入口节点 α 已映射为起始点 '0' (不再以 α 命名)
        assert '0' in data
        assert 'α' not in data

    def test_entrance_remapped_to_zero(self):
        """活动入口节点 α/β 映射为 '0', 且 '0' 的 next 指向真实节点。"""
        data = MapNodeData.load_event('20260730', 'H', 1, 'a')
        assert data is not None
        start = data.get('0')
        assert start is not None
        assert len(start.next_nodes) > 0  # α → [A, B, C]

    def test_load_real_easy_alpha(self):
        """加载真实激斗漩涡 E1 α 地图文件。"""
        data = MapNodeData.load_event('20260730', 'E', 1, 'a')
        assert data is not None
        assert 'A' in data

    def test_missing_returns_none(self):
        assert MapNodeData.load_event('20260730', 'H', 99, 'a') is None
