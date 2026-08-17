"""后端编队请求契约的定向测试。"""

import pytest
from autowsgr_native.vessel_type import VesselType
from pydantic import ValidationError

from autowsgr.combat import CombatPlan
from autowsgr.combat.fleet import (
    NATIVE_VESSEL_TYPE_BY_CODE,
    FleetSelectionSource,
    fleet_slot_from_api,
    ship_type_from_native,
)
from autowsgr.server.schemas import (
    CombatPlanRequest,
    FleetRuleRequest,
    NodeDecisionRequest,
)
from autowsgr.server.serializers import (
    apply_combat_plan_overrides,
    build_combat_plan,
    build_fleet_selection,
)
from autowsgr.types import ShipType


def test_new_fleet_rule_keeps_independent_candidates():
    rule = FleetRuleRequest.model_validate(
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
    )

    assert rule.model_dump(exclude_none=True) == {
        'name': 'U-47',
        'ship_type': ['ss', 'ssg'],
        'min_level': 100,
        'max_level': 110,
        'candidates': [
            {
                'name': 'U-96',
                'ship_type': ['ss'],
                'min_level': 90,
                'max_level': 105,
                'relaxed': False,
            },
            {
                'name': 'U-47',
                'ship_type': ['ss'],
                'min_level': 100,
                'max_level': 110,
                'relaxed': False,
            },
        ],
        'relaxed': False,
    }


def test_candidate_only_fleet_rule_is_valid():
    rule = FleetRuleRequest.model_validate(
        {
            'candidates': [
                {'name': ' 胡德 ', 'ship_type': ['BC']},
                {'name': '扶桑', 'min_level': 80, 'max_level': 110},
            ],
        },
    )

    assert rule.model_dump(exclude_none=True) == {
        'candidates': [
            {'name': '胡德', 'ship_type': ['bc'], 'relaxed': False},
            {'name': '扶桑', 'min_level': 80, 'max_level': 110, 'relaxed': False},
        ],
        'relaxed': False,
    }
    slot = fleet_slot_from_api(rule.model_dump(exclude_none=True))
    assert slot.primary is None
    assert [candidate.name for candidate in slot.candidates] == ['胡德', '扶桑']
    assert all(not candidate.relaxed_constraints for candidate in slot.candidates)


def test_api_relaxed_flags_apply_per_rule():
    """API 的 relaxed 开关按规则各自生效，不互相继承。"""
    rule = FleetRuleRequest.model_validate(
        {
            'name': 'U-47',
            'relaxed': True,
            'min_level': 100,
            'candidates': [
                {'name': 'U-96', 'relaxed': True, 'min_level': 90},
                {'name': 'U-81', 'min_level': 95},
            ],
        },
    )
    slot = fleet_slot_from_api(rule.model_dump(exclude_none=True))

    assert slot.primary is not None
    assert slot.primary.relaxed_constraints is True
    assert [candidate.relaxed_constraints for candidate in slot.candidates] == [True, False]


def test_empty_fleet_slot_is_rejected():
    with pytest.raises(
        ValidationError,
        match='位置至少需要一艘主选或备选舰船',
    ):
        FleetRuleRequest.model_validate({})


def test_legacy_candidate_names_inherit_slot_search_name():
    rule = FleetRuleRequest.model_validate(
        {
            'search_name': '大淀',
            'candidates': ['大淀', '大淀·改'],
        },
    )
    slot = fleet_slot_from_api(rule.model_dump(exclude_none=True))

    assert [candidate.search_name for candidate in slot.candidates] == ['大淀', '大淀']


def test_api_accepts_legacy_candidate_names():
    rule = FleetRuleRequest.model_validate(
        {
            'candidates': [' 岛风 ', '雪风'],
            'ship_type': 'DD',
            'min_level': 80,
        },
    )
    slot = fleet_slot_from_api(rule.model_dump(exclude_none=True))
    assert slot.primary is None
    assert [candidate.name for candidate in slot.candidates] == ['岛风', '雪风']
    assert all(candidate.ship_types == (ShipType.DD,) for candidate in slot.candidates)
    assert all(candidate.min_level == 80 for candidate in slot.candidates)


def test_invalid_candidate_ship_type_is_rejected():
    with pytest.raises(ValidationError, match='ship_type 不合法'):
        FleetRuleRequest.model_validate(
            {
                'name': '岛风',
                'candidates': [
                    {
                        'name': '雪风',
                        'ship_type': ['invalid'],
                    },
                ],
            },
        )


@pytest.mark.parametrize(
    ('code', 'expected'),
    [
        ('aadg', (ShipType.AADG,)),
        ('ap', (ShipType.NAP,)),
        ('asdg', (ShipType.ASDG,)),
        ('av', (ShipType.AV,)),
        ('bb', (ShipType.BB,)),
        ('bbg', (ShipType.BG,)),
        ('bbv', (ShipType.BBV,)),
        ('bc', (ShipType.BC,)),
        ('bg', (ShipType.CBG,)),
        ('bm', (ShipType.BM,)),
        ('ca', (ShipType.CA,)),
        ('cav', (ShipType.CAV,)),
        ('cg', (ShipType.CG,)),
        ('cl', (ShipType.CL,)),
        ('clt', (ShipType.CLT,)),
        ('cv', (ShipType.CV,)),
        ('cvl', (ShipType.CVL,)),
        ('dd', (ShipType.DD,)),
        ('kp', (ShipType.KP,)),
        ('sc', (ShipType.SC,)),
        ('ss', (ShipType.SS,)),
        ('ssg', (ShipType.SSG,)),
        ('ss_or_ssg', (ShipType.SS, ShipType.SSG)),
    ],
)
def test_api_ship_type_code_maps_to_domain_enum(
    code: str,
    expected: tuple[ShipType, ...],
):
    rule = FleetRuleRequest.model_validate({'name': '测试舰船', 'ship_type': [code]})
    slot = fleet_slot_from_api(rule.model_dump(exclude_none=True))

    assert slot.primary is not None
    assert slot.primary.ship_types == expected


@pytest.mark.parametrize(
    ('native_type', 'expected'),
    [
        (VesselType.AADG, ShipType.AADG),
        (VesselType.AP, ShipType.NAP),
        (VesselType.ASDG, ShipType.ASDG),
        (VesselType.AV, ShipType.AV),
        (VesselType.BB, ShipType.BB),
        (VesselType.BBG, ShipType.BG),
        (VesselType.BG, ShipType.CBG),
        (VesselType.BBV, ShipType.BBV),
        (VesselType.BC, ShipType.BC),
        (VesselType.BM, ShipType.BM),
        (VesselType.CA, ShipType.CA),
        (VesselType.CAV, ShipType.CAV),
        (VesselType.CG, ShipType.CG),
        (VesselType.CL, ShipType.CL),
        (VesselType.CLT, ShipType.CLT),
        (VesselType.CV, ShipType.CV),
        (VesselType.CVL, ShipType.CVL),
        (VesselType.DD, ShipType.DD),
        (VesselType.KP, ShipType.KP),
        (VesselType.SC, ShipType.SC),
        (VesselType.SS, ShipType.SS),
        (VesselType.SSG, ShipType.SSG),
    ],
)
def test_native_vessel_type_maps_to_domain_enum(
    native_type: VesselType,
    expected: ShipType,
):
    assert ship_type_from_native(native_type) is expected
    assert native_type.as_chinese() == expected.value


def test_native_fleet_codes_are_complete():
    assert set(NATIVE_VESSEL_TYPE_BY_CODE) == {
        'cv',
        'cvl',
        'av',
        'bb',
        'bbv',
        'bc',
        'ca',
        'cav',
        'clt',
        'cl',
        'bm',
        'dd',
        'ssg',
        'ss',
        'sc',
        'ap',
        'asdg',
        'aadg',
        'kp',
        'cg',
        'bbg',
        'bg',
    }


def test_non_fleet_native_type_is_rejected():
    with pytest.raises(ValueError, match='不支持的 native 舰种'):
        ship_type_from_native(VesselType.Airfield)


@pytest.mark.parametrize(
    ('code', 'expected'),
    [
        ('cf', ShipType.CV),
        ('cgaa', ShipType.CG),
        ('cbg', ShipType.CBG),
        ('ddg', ShipType.ASDG),
        ('ddgaa', ShipType.AADG),
    ],
)
def test_legacy_ship_type_aliases_are_accepted(code: str, expected: ShipType):
    rule = FleetRuleRequest.model_validate({'name': '测试舰船', 'ship_type': [code]})
    slot = fleet_slot_from_api(rule.model_dump(exclude_none=True))
    assert slot.primary is not None
    assert slot.primary.ship_types == (expected,)


@pytest.mark.parametrize('action', [0, 6, True])
def test_invalid_rule_formation_action_is_rejected_at_http_boundary(action: object):
    with pytest.raises(ValidationError):
        NodeDecisionRequest.model_validate({'enemy_rules': [['BB > 0', action]]})


def test_yaml_and_api_candidate_only_rules_share_canonical_model():
    """YAML 与 API 的纯备选结构在入口转换后应完全一致。"""
    raw_rule = {
        'candidates': [
            {'name': '胡德', 'ship_type': ['bc']},
            {'name': '扶桑', 'min_level': 80, 'max_level': 110},
        ],
    }
    yaml_plan = CombatPlan.from_dict(
        {
            'fleet_presets': [
                {
                    'name': '纯备选',
                    'ships': [raw_rule],
                },
            ],
        },
    )
    request = CombatPlanRequest(fleet_rules=[FleetRuleRequest.model_validate(raw_rule)])

    selection = build_fleet_selection(CombatPlan(), request)

    assert yaml_plan.fleet_presets is not None
    assert selection.slot_rules == yaml_plan.fleet_presets[0].slots
    assert selection.source is FleetSelectionSource.OVERRIDE_RULES


def test_legacy_candidate_only_does_not_promote_first_candidate():
    plan = CombatPlan.from_dict(
        {
            'fleet_presets': [
                {'ships': [{'candidates': ['A', 'B'], 'ship_type': ['dd']}]},
            ],
        },
    )
    slot = plan.fleet_presets[0].slots[0]
    assert slot.primary is None
    assert [candidate.name for candidate in slot.candidates] == ['A', 'B']


def test_yaml_relaxed_parsing_keeps_strict_default():
    """YAML 的 relaxed 只作用于写它的规则；缺省保持严格，字符串备选不继承槽位开关。"""
    plan = CombatPlan.from_dict(
        {
            'fleet_presets': [
                {
                    'ships': [
                        {
                            'name': 'U-47',
                            'relaxed': True,
                            'min_level': 100,
                            'candidates': [
                                'U-96',
                                {'name': 'U-81', 'relaxed': True, 'min_level': 95},
                            ],
                        },
                    ],
                },
            ],
        },
    )
    slot = plan.fleet_presets[0].slots[0]
    assert slot.primary is not None
    assert slot.primary.relaxed_constraints is True
    assert [candidate.relaxed_constraints for candidate in slot.candidates] == [False, True]


def test_yaml_relaxed_must_be_boolean():
    """YAML 的 relaxed 必须是布尔值，字符串不静默转换。"""
    with pytest.raises(TypeError, match='relaxed'):
        CombatPlan.from_dict(
            {'fleet_presets': [{'ships': [{'name': 'U-47', 'relaxed': 'yes'}]}]},
        )


def test_empty_fleet_preset_is_rejected():
    with pytest.raises((TypeError, ValueError), match='ships'):
        CombatPlan.from_dict({'fleet_presets': [{}]})
    with pytest.raises(ValueError, match='不能包含空 ships'):
        CombatPlan.from_dict({'fleet_presets': [{'ships': []}]})


@pytest.mark.parametrize('field', ['fleet', 'fleet_rules'])
def test_http_rejects_empty_explicit_fleet_overrides(field: str):
    with pytest.raises(ValidationError):
        CombatPlanRequest.model_validate({field: []})


@pytest.mark.parametrize(
    ('top_level_id', 'request_id', 'plan_id', 'expected'),
    [
        (3, 2, 1, 3),
        (None, 2, 1, 2),
        (None, None, 1, 1),
    ],
)
def test_event_fleet_id_priority_is_resolved_at_server_boundary(
    top_level_id: int | None,
    request_id: int | None,
    plan_id: int,
    expected: int,
):
    """活动顶层覆盖、API plan 和 YAML plan 使用统一优先级。"""
    plan = CombatPlan(fleet_id=plan_id)
    request = CombatPlanRequest(fleet_id=request_id) if request_id is not None else None

    selection = build_fleet_selection(
        plan,
        request,
        fleet_id=top_level_id,
    )

    assert selection.fleet_id == expected


def test_node_decision_request_keeps_yaml_supported_fields():
    decision = NodeDecisionRequest.model_validate(
        {
            'enemy_rules': [['BB > 0', 'retreat']],
            'enemy_formation_rules': [['(line_ahead)', 'retreat']],
            'SL_when_spot_enemy_fails': True,
            'SL_when_enter_fight': True,
            'formation_when_spot_enemy_fails': 3,
        },
    )

    assert decision.enemy_rules == [('BB > 0', 'retreat')]
    assert decision.enemy_formation_rules == [('(line_ahead)', 'retreat')]
    assert decision.SL_when_spot_enemy_fails is True
    assert decision.SL_when_enter_fight is True
    assert decision.formation_when_spot_enemy_fails == 3


def test_api_combat_plan_parses_event_entrance_and_node_fields():
    request = CombatPlanRequest(
        mode='event',
        chapter='H',
        map='1a',
        node_defaults=NodeDecisionRequest(
            enemy_rules=[['BB > 0', 'retreat']],
            SL_when_spot_enemy_fails=True,
            formation_when_spot_enemy_fails=3,
        ),
        node_args={
            'A': NodeDecisionRequest(
                enemy_formation_rules=[['(line_ahead)', 'retreat']],
                SL_when_enter_fight=True,
            ),
        },
    )

    plan = build_combat_plan(request)

    assert plan.map_id == 1
    assert plan.entrance == 'a'
    assert plan.default_node.enemy_rules is not None
    assert plan.default_node.SL_when_spot_enemy_fails is True
    assert plan.default_node.formation_when_spot_enemy_fails.value == 3
    assert plan.nodes['A'].formation_rules is not None
    assert plan.nodes['A'].enemy_rules is not None
    assert plan.nodes['A'].SL_when_spot_enemy_fails is True
    assert plan.nodes['A'].formation_when_spot_enemy_fails.value == 3
    assert plan.nodes['A'].SL_when_enter_fight is True


def test_api_node_args_inherit_defaults_and_keep_explicit_overrides():
    request = CombatPlanRequest(
        node_defaults=NodeDecisionRequest(
            formation=4,
            night=True,
            detour=True,
        ),
        node_args={
            'A': NodeDecisionRequest(
                formation=3,
                detour=False,
            ),
        },
    )

    decision = build_combat_plan(request).nodes['A']

    assert decision.formation.value == 3
    assert decision.night is True
    assert decision.detour is False


def test_yaml_nodes_reinherit_api_defaults_and_keep_explicit_overrides():
    plan = CombatPlan.from_dict(
        {
            'selected_nodes': ['A', 'B', 'C'],
            'node_defaults': {'formation': 2, 'night': False},
            'node_args': {
                'B': {'formation': 3},
                'C': {'night': False},
            },
        },
    )

    apply_combat_plan_overrides(
        plan,
        CombatPlanRequest(
            node_defaults=NodeDecisionRequest(
                formation=4,
                night=True,
            ),
        ),
    )

    assert plan.nodes['A'].formation.value == 4
    assert plan.nodes['A'].night is True
    assert plan.nodes['B'].formation.value == 3
    assert plan.nodes['B'].night is True
    assert plan.nodes['C'].formation.value == 4
    assert plan.nodes['C'].night is False


def test_yaml_legacy_detour_sl_field_survives_api_default_override():
    plan = CombatPlan.from_dict(
        {
            'selected_nodes': ['A'],
            'node_args': {
                'A': {
                    'detour': True,
                    'sl_when_detour_fails': False,
                },
            },
        },
    )

    apply_combat_plan_overrides(
        plan,
        CombatPlanRequest(
            node_defaults=NodeDecisionRequest(formation=4),
        ),
    )

    assert plan.nodes['A'].detour is True
    assert plan.nodes['A'].SL_when_detour_fails is False
    assert not hasattr(plan.nodes['A'], 'sl_when_detour_fails')
