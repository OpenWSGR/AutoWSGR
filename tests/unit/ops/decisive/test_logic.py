"""测试 autowsgr.ops.decisive.logic。"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from autowsgr.infra.config import DecisiveConfig
from autowsgr.ops.decisive.logic import DecisiveLogic, _count_anti_sub, _is_ship
from autowsgr.ops.decisive.state import DecisiveState
from autowsgr.types import FleetSelection, Formation, ShipDamageState


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════════


def make_logic(
    *,
    chapter: int = 6,
    level1: list[str] | None = None,
    level2: list[str] | None = None,
    flagship_priority: list[str] | None = None,
    repair_level: int = 1,
    use_quick_repair: bool = True,
    useful_skill_strict: bool = False,
    state: DecisiveState | None = None,
) -> DecisiveLogic:
    """创建 DecisiveLogic 实例及配套 state。"""
    config = DecisiveConfig(
        chapter=chapter,
        level1=level1 or ['A1', 'A2'],
        level2=level2 or ['B1'],
        flagship_priority=flagship_priority or [],
        repair_level=repair_level,
        use_quick_repair=use_quick_repair,
        useful_skill_strict=useful_skill_strict,
    )
    if state is None:
        state = DecisiveState()
    return DecisiveLogic(config, state)


# ═══════════════════════════════════════════════════════════════════════════════
# _is_ship
# ═══════════════════════════════════════════════════════════════════════════════


class TestIsShip:
    """_is_ship 测试。"""

    @pytest.mark.parametrize(
        ('name', 'expected'),
        [
            ('长跑训练', False),
            ('肌肉记忆', False),
            ('黑科技', False),
            ('U-47', True),
            ('射水鱼', True),
            ('普通船名', True),
        ],
    )
    def test_is_ship(self, name: str, expected: bool) -> None:
        assert _is_ship(name) is expected


# ═══════════════════════════════════════════════════════════════════════════════
# _count_anti_sub
# ═══════════════════════════════════════════════════════════════════════════════


class TestCountAntiSub:
    """_count_anti_sub 测试。"""

    def test_empty(self) -> None:
        assert _count_anti_sub([]) == 0

    def test_no_anti_sub(self) -> None:
        assert _count_anti_sub(['BB', 'CV', 'SS']) == 0

    def test_mixed(self) -> None:
        assert _count_anti_sub(['CL', 'BB', 'DD', 'CVL', 'SS']) == 3

    def test_all_anti_sub(self) -> None:
        assert _count_anti_sub(['CL', 'DD', 'CVL']) == 3


# ═══════════════════════════════════════════════════════════════════════════════
# choose_ships
# ═══════════════════════════════════════════════════════════════════════════════


class TestChooseShips:
    """DecisiveLogic.choose_ships 测试。"""

    def test_empty_fleet_prioritizes_level1(self) -> None:
        state = DecisiveState(fleet=[''] * 7, score=10)
        logic = make_logic(level1=['A1', 'A2'], level2=['B1'], state=state)
        selections = {
            'A1': FleetSelection('A1', 3, (0.0, 0.0)),
            'A2': FleetSelection('A2', 4, (0.0, 0.0)),
            'B1': FleetSelection('B1', 2, (0.0, 0.0)),
        }
        result = logic.choose_ships(selections)
        assert result == ['A1', 'A2']

    def test_fleet_count_one_respects_cost_limit(self) -> None:
        state = DecisiveState(fleet=['', 'X', '', '', '', '', ''], score=5)
        logic = make_logic(level1=['A1', 'A2'], level2=['B1'], state=state)
        selections = {
            'A1': FleetSelection('A1', 3, (0.0, 0.0)),
            'A2': FleetSelection('A2', 4, (0.0, 0.0)),
            'B1': FleetSelection('B1', 2, (0.0, 0.0)),
        }
        result = logic.choose_ships(selections)
        assert result == ['A1']

    def test_fleet_count_two_can_buy_level1(self) -> None:
        state = DecisiveState(fleet=['', 'X', 'Y', '', '', '', ''], score=10)
        logic = make_logic(level1=['A1'], level2=['B1'], state=state)
        selections = {
            'A1': FleetSelection('A1', 2, (0.0, 0.0)),
        }
        result = logic.choose_ships(selections)
        assert result == ['A1']

    def test_fleet_count_two_excludes_skills(self) -> None:
        state = DecisiveState(fleet=['', 'X', 'Y', '', '', '', ''], score=10)
        logic = make_logic(level1=['A1'], level2=['B1'], state=state)
        selections = {
            'B1': FleetSelection('B1', 2, (0.0, 0.0)),
            '长跑训练': FleetSelection('长跑训练', 1, (0.0, 0.0)),
        }
        result = logic.choose_ships(selections)
        assert result == ['B1']
        assert '长跑训练' not in result

    def test_full_fleet_non_level1_reprioritizes_level1(self) -> None:
        state = DecisiveState(fleet=['', 'A1', 'A2', 'X', 'Y', 'Z', 'W'], score=10)
        logic = make_logic(level1=['A1', 'A2', 'A3'], level2=['B1'], state=state)
        selections = {
            'A3': FleetSelection('A3', 2, (0.0, 0.0)),
            'B1': FleetSelection('B1', 1, (0.0, 0.0)),
        }
        result = logic.choose_ships(selections)
        assert result == ['A3']

    def test_full_fleet_all_level1_allows_skills(self) -> None:
        state = DecisiveState(
            fleet=['', 'A1', 'A2', 'A3', 'A4', 'A5', 'A6'],
            score=10,
        )
        logic = make_logic(
            level1=['A1', 'A2', 'A3', 'A4', 'A5', 'A6'],
            level2=['B1'],
            state=state,
        )
        selections = {
            '长跑训练': FleetSelection('长跑训练', 1, (0.0, 0.0)),
        }
        result = logic.choose_ships(selections)
        assert result == ['长跑训练']

    def test_first_node_adds_level2(self) -> None:
        state = DecisiveState(fleet=[''] * 7, score=10)
        logic = make_logic(level1=['A1'], level2=['B1'], state=state)
        selections = {
            'A1': FleetSelection('A1', 3, (0.0, 0.0)),
            'B1': FleetSelection('B1', 2, (0.0, 0.0)),
        }
        result = logic.choose_ships(selections, first_node=True)
        assert result == ['A1', 'B1']

    def test_first_node_adds_level2_when_level1_missing(self) -> None:
        state = DecisiveState(fleet=[''] * 7, score=10)
        logic = make_logic(level1=['A1'], level2=['B1'], state=state)
        selections = {
            'B1': FleetSelection('B1', 2, (0.0, 0.0)),
        }
        result = logic.choose_ships(selections, first_node=True)
        assert result == ['B1']


# ═══════════════════════════════════════════════════════════════════════════════
# should_retreat
# ═══════════════════════════════════════════════════════════════════════════════


class TestShouldRetreat:
    """DecisiveLogic.should_retreat 测试。"""

    def test_node_a_threshold_2(self) -> None:
        logic = make_logic()
        logic.state.node = 'A'
        assert logic.should_retreat(['', '', '', '', '', '', '']) is True
        assert logic.should_retreat(['', 'X', '', '', '', '', '']) is True
        assert logic.should_retreat(['', 'X', 'Y', '', '', '', '']) is False
        assert logic.should_retreat(['', 'X', 'Y', 'Z', '', '', '']) is False

    def test_other_nodes_threshold_1(self) -> None:
        logic = make_logic()
        logic.state.node = 'B'
        assert logic.should_retreat(['', '', '', '', '', '', '']) is True
        assert logic.should_retreat(['', 'X', '', '', '', '', '']) is False
        assert logic.should_retreat(['', 'X', 'Y', '', '', '', '']) is False


# ═══════════════════════════════════════════════════════════════════════════════
# should_repair
# ═══════════════════════════════════════════════════════════════════════════════


class TestShouldRepair:
    """DecisiveLogic.should_repair 测试。"""

    def test_disabled(self) -> None:
        state = DecisiveState(ship_stats=[ShipDamageState.MODERATE] * 6)
        logic = make_logic(use_quick_repair=False, state=state)
        assert logic.should_repair() is False

    def test_no_damage(self) -> None:
        state = DecisiveState(ship_stats=[ShipDamageState.NORMAL] * 6)
        logic = make_logic(use_quick_repair=True, repair_level=1, state=state)
        assert logic.should_repair() is False

    def test_moderate_at_level_1(self) -> None:
        state = DecisiveState(
            ship_stats=[ShipDamageState.MODERATE, ShipDamageState.NORMAL] * 3,
        )
        logic = make_logic(use_quick_repair=True, repair_level=1, state=state)
        assert logic.should_repair() is True

    def test_moderate_at_level_2(self) -> None:
        state = DecisiveState(
            ship_stats=[ShipDamageState.MODERATE, ShipDamageState.NORMAL] * 3,
        )
        logic = make_logic(use_quick_repair=True, repair_level=2, state=state)
        assert logic.should_repair() is False

    def test_severe_at_level_2(self) -> None:
        state = DecisiveState(
            ship_stats=[ShipDamageState.SEVERE, ShipDamageState.NORMAL] * 3,
        )
        logic = make_logic(use_quick_repair=True, repair_level=2, state=state)
        assert logic.should_repair() is True

    def test_ignores_no_ship_slots(self) -> None:
        state = DecisiveState(
            ship_stats=[ShipDamageState.NO_SHIP, ShipDamageState.SEVERE] * 3,
        )
        logic = make_logic(use_quick_repair=True, repair_level=1, state=state)
        assert logic.should_repair() is True


# ═══════════════════════════════════════════════════════════════════════════════
# check_useful_skill
# ═══════════════════════════════════════════════════════════════════════════════


class TestCheckUsefulSkill:
    """DecisiveLogic.check_useful_skill 测试。"""

    def test_single_in_level2(self) -> None:
        logic = make_logic(level1=['A1'], level2=['B1'])
        assert logic.check_useful_skill(['B1']) is True

    def test_single_not_in_level2(self) -> None:
        logic = make_logic(level1=['A1'], level2=['B1'])
        assert logic.check_useful_skill(['C1']) is False

    def test_single_skill_not_ship(self) -> None:
        logic = make_logic(level1=['A1'], level2=['B1'])
        # 长跑训练 is in _level2_full but is not a ship
        assert logic.check_useful_skill(['长跑训练']) is True

    def test_strict_duplicate(self) -> None:
        state = DecisiveState(ships={'B1'})
        logic = make_logic(
            level1=['A1'],
            level2=['B1'],
            useful_skill_strict=True,
            state=state,
        )
        assert logic.check_useful_skill(['B1']) is False

    def test_strict_new_ship(self) -> None:
        state = DecisiveState(ships={'A1'})
        logic = make_logic(
            level1=['A1'],
            level2=['B1'],
            useful_skill_strict=True,
            state=state,
        )
        assert logic.check_useful_skill(['B1']) is True

    def test_multi_majority_level1(self) -> None:
        logic = make_logic(level1=['A1', 'A2', 'A3'])
        assert logic.check_useful_skill(['A1', 'A2', 'B1']) is True

    def test_multi_below_half(self) -> None:
        logic = make_logic(level1=['A1', 'A2', 'A3'])
        assert logic.check_useful_skill(['A1', 'B1', 'B2']) is False

    def test_multi_even_meets_half(self) -> None:
        logic = make_logic(level1=['A1', 'A2', 'A3'])
        assert logic.check_useful_skill(['A1', 'A2', 'B1', 'B2']) is True

    def test_multi_even_below_half(self) -> None:
        logic = make_logic(level1=['A1', 'A2', 'A3'])
        assert logic.check_useful_skill(['A1', 'B1', 'B2', 'B3']) is False


# ═══════════════════════════════════════════════════════════════════════════════
# get_best_fleet
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetBestFleet:
    """DecisiveLogic.get_best_fleet 测试。"""

    def test_level1_only(self) -> None:
        state = DecisiveState(ships={'A1', 'A2'})
        logic = make_logic(level1=['A1', 'A2'], level2=['B1'], state=state)
        assert logic.get_best_fleet() == ['', 'A1', 'A2', '', '', '', '']

    def test_level2_fallback(self) -> None:
        state = DecisiveState(ships={'A1', 'B1', 'B2'})
        logic = make_logic(level1=['A1', 'A2'], level2=['B1', 'B2'], state=state)
        assert logic.get_best_fleet() == ['', 'A1', 'B1', 'B2', '', '', '']

    def test_flagship_priority_reorders(self) -> None:
        state = DecisiveState(ships={'A1', 'A2'})
        logic = make_logic(
            level1=['A1', 'A2'],
            flagship_priority=['A2', 'A1'],
            state=state,
        )
        assert logic.get_best_fleet() == ['', 'A2', 'A1', '', '', '', '']

    def test_padded_to_7(self) -> None:
        state = DecisiveState(ships={'A1'})
        logic = make_logic(level1=['A1'], state=state)
        assert logic.get_best_fleet() == ['', 'A1', '', '', '', '', '']

    def test_no_duplicates(self) -> None:
        state = DecisiveState(ships={'A1', 'B1'})
        logic = make_logic(level1=['A1'], level2=['B1', 'A1'], state=state)
        assert logic.get_best_fleet() == ['', 'A1', 'B1', '', '', '', '']

    def test_available_with_ctx(self) -> None:
        ctx = object.__new__(
            type('MockCtx', (), {'is_ship_available': lambda _self, name: name == 'A1'})
        )
        state = DecisiveState(ships={'A1', 'A2'})
        config = DecisiveConfig(level1=['A1', 'A2'])
        logic = DecisiveLogic(config, state, ctx=ctx)
        assert logic.get_best_fleet() == ['', 'A1', '', '', '', '', '']


# ═══════════════════════════════════════════════════════════════════════════════
# get_advance_choice
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetAdvanceChoice:
    """DecisiveLogic.get_advance_choice 测试。"""

    def test_returns_zero(self) -> None:
        logic = make_logic()
        assert logic.get_advance_choice(['A1', 'A2']) == 0
        assert logic.get_advance_choice([]) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# get_formation
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetFormation:
    """DecisiveLogic.get_formation 测试。"""

    def test_no_anti_sub_returns_wedge(self) -> None:
        with patch('autowsgr.ops.decisive.logic.MapData.get_enemy', return_value=['BB', 'CV']):
            logic = make_logic(chapter=1)
            logic.state.stage = 1
            logic.state.node = 'A'
            assert logic.get_formation() == Formation.wedge

    def test_u1206_with_one_anti_sub_returns_wedge(self) -> None:
        with patch('autowsgr.ops.decisive.logic.MapData.get_enemy', return_value=['CL', 'BB']):
            logic = make_logic(chapter=1)
            logic.state.stage = 1
            logic.state.node = 'A'
            logic.state.fleet = ['', 'U-1206', '', '', '', '', '']
            assert logic.get_formation() == Formation.wedge

    def test_u1206_with_two_anti_sub_returns_double_column(self) -> None:
        with patch(
            'autowsgr.ops.decisive.logic.MapData.get_enemy',
            return_value=['CL', 'DD', 'BB'],
        ):
            logic = make_logic(chapter=1)
            logic.state.stage = 1
            logic.state.node = 'A'
            logic.state.fleet = ['', 'U-1206', '', '', '', '', '']
            assert logic.get_formation() == Formation.double_column

    def test_without_u1206_with_anti_sub_returns_double_column(self) -> None:
        with patch('autowsgr.ops.decisive.logic.MapData.get_enemy', return_value=['CL', 'BB']):
            logic = make_logic(chapter=1)
            logic.state.stage = 1
            logic.state.node = 'A'
            logic.state.fleet = ['', 'X', '', '', '', '', '']
            assert logic.get_formation() == Formation.double_column


# ═══════════════════════════════════════════════════════════════════════════════
# is_stage_end / is_key_point
# ═══════════════════════════════════════════════════════════════════════════════


class TestIsStageEnd:
    """DecisiveLogic.is_stage_end 测试。"""

    def test_uses_state_node(self) -> None:
        with patch(
            'autowsgr.ops.decisive.logic.MapData.is_stage_end',
            return_value=True,
        ) as mock:
            logic = make_logic(chapter=3, state=DecisiveState(stage=2, node='H'))
            assert logic.is_stage_end() is True
            mock.assert_called_once_with(3, 2, 'H')

    def test_explicit_node(self) -> None:
        with patch(
            'autowsgr.ops.decisive.logic.MapData.is_stage_end',
            return_value=False,
        ) as mock:
            logic = make_logic(chapter=3, state=DecisiveState(stage=2, node='H'))
            assert logic.is_stage_end('J') is False
            mock.assert_called_once_with(3, 2, 'J')


class TestIsKeyPoint:
    """DecisiveLogic.is_key_point 测试。"""

    def test_uses_state_node(self) -> None:
        with patch(
            'autowsgr.ops.decisive.logic.MapData.is_key_point',
            return_value=True,
        ) as mock:
            logic = make_logic(chapter=3, state=DecisiveState(stage=2, node='B'))
            assert logic.is_key_point() is True
            mock.assert_called_once_with(3, 2, 'B')

    def test_explicit_node(self) -> None:
        with patch(
            'autowsgr.ops.decisive.logic.MapData.is_key_point',
            return_value=False,
        ) as mock:
            logic = make_logic(chapter=3, state=DecisiveState(stage=2, node='B'))
            assert logic.is_key_point('C') is False
            mock.assert_called_once_with(3, 2, 'C')
