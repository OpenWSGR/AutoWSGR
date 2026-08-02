"""后端编队请求契约的定向测试。"""

import pytest
from pydantic import ValidationError

from autowsgr.server.schemas import FleetRuleRequest


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
            },
            {
                'name': 'U-47',
                'ship_type': ['ss'],
                'min_level': 100,
                'max_level': 110,
            },
        ],
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
            {'name': '胡德', 'ship_type': ['bc']},
            {'name': '扶桑', 'min_level': 80, 'max_level': 110},
        ],
    }


def test_empty_fleet_slot_is_rejected():
    with pytest.raises(
        ValidationError,
        match='位置至少需要一艘主选或备选舰船',
    ):
        FleetRuleRequest.model_validate({})


def test_candidate_only_slot_rejects_primary_constraints():
    with pytest.raises(
        ValidationError,
        match='没有主选 name 时不能填写主选规则',
    ):
        FleetRuleRequest.model_validate(
            {
                'ship_type': ['BB'],
                'candidates': [{'name': '胡德'}],
            },
        )


def test_legacy_candidate_names_are_migrated():
    rule = FleetRuleRequest.model_validate(
        {
            'candidates': [' 岛风 ', '雪风'],
            'ship_type': 'DD',
            'min_level': 80,
        },
    )

    assert rule.name == '岛风'
    assert rule.ship_type == ['dd']
    assert [candidate.model_dump(exclude_none=True) for candidate in rule.candidates] == [
        {
            'name': '雪风',
            'ship_type': ['dd'],
            'min_level': 80,
        },
    ]


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
