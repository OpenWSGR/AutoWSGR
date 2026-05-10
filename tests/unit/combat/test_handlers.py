"""测试 autowsgr.combat.handlers 中的决策逻辑。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest

from autowsgr.combat.handlers import PhaseHandlersMixin
from autowsgr.combat.history import CombatHistory
from autowsgr.combat.state import CombatPhase
from autowsgr.types import ConditionFlag, Formation, ShipDamageState


if TYPE_CHECKING:
    from autowsgr.combat.plan import NodeDecision


class _TestableHandlers(PhaseHandlersMixin):
    """可测试的 PhaseHandlersMixin 实现。"""

    _plan: Any  # 覆盖 Mixin 的 CombatPlan 类型，以支持 MagicMock 属性

    def __init__(self) -> None:
        self._device = MagicMock()
        self._plan = MagicMock()
        self._ocr = None
        self._node = 'A'
        self._last_action = ''
        self._ship_stats = [ShipDamageState.NORMAL] * 6
        self._history = CombatHistory()
        self._node_count = 0
        self._formation_by_rule = None

    def _get_current_decision(self) -> NodeDecision:
        return self._plan.get_node_decision.return_value


@pytest.fixture
def handlers() -> _TestableHandlers:
    return _TestableHandlers()


class TestMakeDecision:
    """_make_decision 派发与终止态测试。"""

    def test_known_phase_dispatched(self, handlers: _TestableHandlers) -> None:
        handlers._plan.end_phase = CombatPhase.RESULT
        with patch.object(handlers, '_handle_result', return_value=ConditionFlag.FIGHT_CONTINUE):
            result = handlers._make_decision(CombatPhase.RESULT)
            assert result == ConditionFlag.FIGHT_END  # 终止态

    def test_unknown_phase_returns_continue(self, handlers: _TestableHandlers) -> None:
        handlers._plan.end_phase = CombatPhase.PROCEED
        result = handlers._make_decision(CombatPhase.START_FIGHT)
        assert result == ConditionFlag.FIGHT_CONTINUE

    def test_end_phase_adds_history(self, handlers: _TestableHandlers) -> None:
        handlers._plan.end_phase = CombatPhase.RESULT
        with patch.object(handlers, '_handle_result', return_value=ConditionFlag.FIGHT_CONTINUE):
            handlers._make_decision(CombatPhase.RESULT)
            assert len(handlers._history.events) == 1
            assert handlers._history.events[0].event_type.name == 'AUTO_RETURN'


class TestHandleFightCondition:
    """_handle_fight_condition 测试。"""

    def test_sets_last_action(self, handlers: _TestableHandlers) -> None:
        handlers._plan.fight_condition = MagicMock(value='优势')
        with patch('autowsgr.combat.handlers.click_fight_condition'):
            handlers._handle_fight_condition()
            assert handlers._last_action == '优势'


class TestHandleFormation:
    """_handle_formation 纯逻辑分支测试。"""

    def test_not_selected_node_sl(self, handlers: _TestableHandlers) -> None:
        handlers._plan.is_selected_node.return_value = False
        result = handlers._handle_formation()
        assert result == ConditionFlag.SL
        assert handlers._history.events[-1].action == 'SL'

    def test_detour_fails_sl(self, handlers: _TestableHandlers) -> None:
        handlers._plan.is_selected_node.return_value = True
        handlers._last_action = 'detour'
        decision = MagicMock()
        decision.SL_when_detour_fails = True
        decision.formation = Formation.single_column
        handlers._plan.get_node_decision.return_value = decision
        result = handlers._handle_formation()
        assert result == ConditionFlag.SL

    def test_spot_enemy_fails_sl(self, handlers: _TestableHandlers) -> None:
        handlers._plan.is_selected_node.return_value = True
        handlers._last_action = ''  # 不是 fight/detour，表示索敌失败直接到阵型
        decision = MagicMock()
        decision.SL_when_detour_fails = False
        decision.SL_when_spot_enemy_fails = True
        decision.formation = Formation.single_column
        decision.formation_when_spot_enemy_fails = None
        handlers._plan.get_node_decision.return_value = decision
        result = handlers._handle_formation()
        assert result == ConditionFlag.SL

    def test_spot_enemy_fails_fallback_formation(self, handlers: _TestableHandlers) -> None:
        handlers._plan.is_selected_node.return_value = True
        handlers._last_action = 'fight'
        decision = MagicMock()
        decision.SL_when_detour_fails = False
        decision.SL_when_spot_enemy_fails = False
        decision.formation = Formation.single_column
        decision.formation_when_spot_enemy_fails = Formation.double_column
        handlers._plan.get_node_decision.return_value = decision
        with patch('autowsgr.combat.handlers.click_formation'):
            result = handlers._handle_formation()
            assert result == ConditionFlag.FIGHT_CONTINUE

    def test_rule_formation_used(self, handlers: _TestableHandlers) -> None:
        handlers._plan.is_selected_node.return_value = True
        handlers._last_action = 'fight'
        handlers._formation_by_rule = Formation.double_column
        decision = MagicMock()
        decision.SL_when_detour_fails = False
        decision.SL_when_spot_enemy_fails = False
        decision.formation = Formation.single_column
        decision.formation_when_spot_enemy_fails = None
        handlers._plan.get_node_decision.return_value = decision
        with patch('autowsgr.combat.handlers.click_formation'):
            handlers._handle_formation()
            assert handlers._formation_by_rule is None  # 已清除


class TestHandleFightPeriod:
    """_handle_fight_period 测试。"""

    def test_sl_when_enter_fight(self, handlers: _TestableHandlers) -> None:
        decision = MagicMock()
        decision.SL_when_enter_fight = True
        handlers._plan.get_node_decision.return_value = decision
        result = handlers._handle_fight_period()
        assert result == ConditionFlag.SL

    def test_continue(self, handlers: _TestableHandlers) -> None:
        decision = MagicMock()
        decision.SL_when_enter_fight = False
        handlers._plan.get_node_decision.return_value = decision
        result = handlers._handle_fight_period()
        assert result == ConditionFlag.FIGHT_CONTINUE


class TestHandleNightPrompt:
    """_handle_night_prompt 测试。"""

    def test_pursue(self, handlers: _TestableHandlers) -> None:
        decision = MagicMock()
        decision.night = True
        handlers._plan.get_node_decision.return_value = decision
        with patch('autowsgr.combat.handlers.click_night_battle'):
            result = handlers._handle_night_prompt()
            assert handlers._last_action == 'yes'
            assert result == ConditionFlag.FIGHT_CONTINUE

    def test_retreat(self, handlers: _TestableHandlers) -> None:
        decision = MagicMock()
        decision.night = False
        handlers._plan.get_node_decision.return_value = decision
        with patch('autowsgr.combat.handlers.click_night_battle'):
            result = handlers._handle_night_prompt()
            assert handlers._last_action == 'no'
            assert result == ConditionFlag.FIGHT_CONTINUE


class TestHandleProceed:
    """_handle_proceed 测试。"""

    def test_proceed_true(self, handlers: _TestableHandlers) -> None:
        decision = MagicMock()
        decision.proceed = True
        decision.proceed_stop = [ShipDamageState.SEVERE]
        handlers._plan.get_node_decision.return_value = decision
        with (
            patch('autowsgr.combat.handlers.check_blood', return_value=True),
            patch('autowsgr.combat.handlers.click_proceed'),
        ):
            result = handlers._handle_proceed()
            assert handlers._last_action == 'yes'
            assert result == ConditionFlag.FIGHT_CONTINUE

    def test_proceed_false(self, handlers: _TestableHandlers) -> None:
        decision = MagicMock()
        decision.proceed = False
        decision.proceed_stop = []
        handlers._plan.get_node_decision.return_value = decision
        with (
            patch('autowsgr.combat.handlers.check_blood', return_value=False),
            patch('autowsgr.combat.handlers.click_proceed'),
        ):
            result = handlers._handle_proceed()
            assert handlers._last_action == 'no'
            assert result == ConditionFlag.FIGHT_END

    def test_blood_check_fails(self, handlers: _TestableHandlers) -> None:
        decision = MagicMock()
        decision.proceed = True
        decision.proceed_stop = [ShipDamageState.SEVERE]
        handlers._ship_stats = [ShipDamageState.SEVERE] + [ShipDamageState.NORMAL] * 5
        handlers._plan.get_node_decision.return_value = decision
        with (
            patch('autowsgr.combat.handlers.check_blood', return_value=False),
            patch('autowsgr.combat.handlers.click_proceed'),
        ):
            result = handlers._handle_proceed()
            assert result == ConditionFlag.FIGHT_END


class TestHandleDockFull:
    """_handle_dock_full 测试。"""

    def test_returns_dock_full(self, handlers: _TestableHandlers) -> None:
        result = handlers._handle_dock_full()
        assert result == ConditionFlag.DOCK_FULL
        assert handlers._history.events[-1].action == '船坞已满'


class TestHandleFlagshipSevereDamage:
    """_handle_flagship_severe_damage 测试。"""

    def test_returns_fight_end(self, handlers: _TestableHandlers) -> None:
        with patch('autowsgr.combat.handlers.click_image'):
            result = handlers._handle_flagship_severe_damage()
            assert result == ConditionFlag.FIGHT_END
            assert handlers._history.events[-1].event_type.name == 'FLAGSHIP_DAMAGE'


class TestHandleMissileAnimation:
    """_handle_missile_animation 测试。"""

    def test_returns_continue(self, handlers: _TestableHandlers) -> None:
        with patch('autowsgr.combat.handlers.click_skip_missile_animation'):
            result = handlers._handle_missile_animation()
            assert result == ConditionFlag.FIGHT_CONTINUE
            assert handlers._last_action == 'skip_animation'


class TestHandleGetShip:
    """_handle_get_ship 测试。"""

    def test_with_ship_name(self, handlers: _TestableHandlers) -> None:
        with patch('autowsgr.combat.handlers.get_ship_drop', return_value='岛风'):
            result = handlers._handle_get_ship()
            assert result == ConditionFlag.FIGHT_CONTINUE
            assert handlers._history.events[-1].result == '岛风'

    def test_without_ship_name(self, handlers: _TestableHandlers) -> None:
        with patch('autowsgr.combat.handlers.get_ship_drop', return_value=''):
            handlers._handle_get_ship()
            assert handlers._history.events[-1].result == ''
