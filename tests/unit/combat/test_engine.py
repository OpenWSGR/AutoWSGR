"""测试 autowsgr.combat.engine。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from autowsgr.combat.engine import CombatEngine, run_combat
from autowsgr.combat.history import CombatHistory
from autowsgr.combat.plan import CombatMode, CombatPlan
from autowsgr.combat.state import CombatPhase
from autowsgr.types import ConditionFlag, ShipDamageState


class TestCombatEngineInit:
    """CombatEngine 初始化测试。"""

    def test_init_attributes(self) -> None:
        ctx = MagicMock()
        ctx.ctrl = MagicMock()
        ctx.ocr = None
        engine = CombatEngine(ctx=ctx)
        assert engine.current_node == '0'
        assert engine._phase == CombatPhase.PROCEED
        assert engine._plan.name == ''
        assert engine._tracker is None
        assert isinstance(engine.history, CombatHistory)

    def test_set_node(self) -> None:
        ctx = MagicMock()
        engine = CombatEngine(ctx=ctx)
        engine.set_node('B')
        assert engine.current_node == 'B'


class TestCombatEngineReset:
    """CombatEngine._reset 测试。"""

    def test_reset_clears_state(self) -> None:
        ctx = MagicMock()
        engine = CombatEngine(ctx=ctx)
        engine._node = 'C'
        engine._node_count = 3
        engine._last_action = 'yes'
        engine._phase = CombatPhase.RESULT
        engine._reset()
        assert engine.current_node == '0'
        assert engine._node_count == 0
        assert engine._last_action == ''
        assert engine._phase == CombatPhase.START_FIGHT

    def test_reset_calls_tracker_reset(self) -> None:
        ctx = MagicMock()
        engine = CombatEngine(ctx=ctx)
        engine._tracker = MagicMock()
        engine._reset()
        engine._tracker.reset.assert_called_once()


class TestIsMapRoutingPhase:
    """CombatEngine._is_map_routing_phase 测试。"""

    @pytest.fixture
    def engine(self) -> CombatEngine:
        ctx = MagicMock()
        return CombatEngine(ctx=ctx)

    @pytest.mark.parametrize(
        'phase',
        [
            CombatPhase.PROCEED,
            CombatPhase.FIGHT_CONDITION,
            CombatPhase.START_FIGHT,
        ],
    )
    def test_true_phases(self, engine: CombatEngine, phase: CombatPhase) -> None:
        assert engine._is_map_routing_phase(phase) is True

    def test_true_detour(self, engine: CombatEngine) -> None:
        engine._last_action = 'detour'
        assert engine._is_map_routing_phase(CombatPhase.RESULT) is True

    def test_false(self, engine: CombatEngine) -> None:
        engine._last_action = 'yes'
        assert engine._is_map_routing_phase(CombatPhase.RESULT) is False


class TestGetPollAction:
    """CombatEngine._get_poll_action 测试。"""

    @pytest.fixture
    def engine(self) -> CombatEngine:
        ctx = MagicMock()
        return CombatEngine(ctx=ctx)

    def test_fight_period_returns_sleep(self, engine: CombatEngine) -> None:
        engine._plan = MagicMock()
        engine._plan.mode = CombatMode.NORMAL
        engine._phase = CombatPhase.FIGHT_PERIOD
        result = engine._get_poll_action(CombatPhase.FIGHT_PERIOD)
        assert result is not None
        # lambda 应执行 time.sleep(0.5)
        result(np.zeros((10, 10, 3), dtype=np.uint8))

    def test_map_routing_phase_returns_poll_map(self, engine: CombatEngine) -> None:
        engine._plan = MagicMock()
        engine._plan.mode = CombatMode.NORMAL
        engine._phase = CombatPhase.START_FIGHT
        engine._tracker = MagicMock()
        engine._node = 'A'
        result = engine._get_poll_action(CombatPhase.START_FIGHT)
        assert result is not None
        # 调用应触发 tracker 更新
        screen = MagicMock()
        with patch('autowsgr.combat.engine.dismiss_resource_confirm'):
            result(screen)
        engine._tracker.update_ship_position.assert_called_once_with(screen)
        engine._tracker.update_node.assert_called_once()

    def test_map_routing_no_tracker(self, engine: CombatEngine) -> None:
        engine._plan = MagicMock()
        engine._plan.mode = CombatMode.NORMAL
        engine._phase = CombatPhase.START_FIGHT
        engine._tracker = None
        result = engine._get_poll_action(CombatPhase.START_FIGHT)
        assert result is not None
        screen = MagicMock()
        result(screen)

    def test_single_start_fight_returns_poll_single(self, engine: CombatEngine) -> None:
        engine._plan = MagicMock()
        engine._plan.mode = CombatMode.EXERCISE
        engine._phase = CombatPhase.START_FIGHT
        result = engine._get_poll_action(CombatPhase.START_FIGHT)
        assert result is not None
        screen = MagicMock()
        result(screen)

    def test_other_returns_none(self, engine: CombatEngine) -> None:
        engine._plan = MagicMock()
        engine._plan.mode = CombatMode.NORMAL
        engine._phase = CombatPhase.FORMATION
        result = engine._get_poll_action(CombatPhase.FORMATION)
        assert result is None


class TestFightInitialization:
    """CombatEngine.fight 初始化逻辑测试。"""

    @pytest.fixture
    def engine(self) -> CombatEngine:
        ctx = MagicMock()
        ctx.ctrl = MagicMock()
        ctx.ocr = None
        return CombatEngine(ctx=ctx)

    def test_normal_mode_loads_map(self, engine: CombatEngine) -> None:
        plan = CombatPlan(
            name='test',
            mode=CombatMode.NORMAL,
            chapter=7,
            map_id=1,
        )
        with (
            patch(
                'autowsgr.combat.engine.MapNodeData.load',
                return_value=MagicMock(__len__=lambda _: 5),
            ) as mock_load,
            patch.object(
                engine,
                '_step',
                side_effect=[
                    ConditionFlag.FIGHT_END,
                ],
            ),
        ):
            result = engine.fight(plan, initial_ship_stats=[ShipDamageState.NORMAL] * 6)
            mock_load.assert_called_once_with(7, 1)
            assert engine._tracker is not None
            assert result.node_count == 0

    def test_normal_mode_missing_map(self, engine: CombatEngine) -> None:
        plan = CombatPlan(
            name='test',
            mode=CombatMode.NORMAL,
            chapter=99,
            map_id=99,
        )
        with (
            patch(
                'autowsgr.combat.engine.MapNodeData.load',
                return_value=None,
            ),
            patch.object(
                engine,
                '_step',
                side_effect=[
                    ConditionFlag.FIGHT_END,
                ],
            ),
        ):
            engine.fight(plan, initial_ship_stats=None)
            assert engine._tracker is None

    def test_event_mode_loads_event_map(self, engine: CombatEngine) -> None:
        plan = CombatPlan(
            name='test',
            mode=CombatMode.EVENT,
            event_name='20260212',
            chapter='H',
            map_id=5,
        )
        with (
            patch(
                'autowsgr.combat.engine.MapNodeData.load_event',
                return_value=MagicMock(__len__=lambda _: 3),
            ) as mock_load,
            patch.object(
                engine,
                '_step',
                side_effect=[
                    ConditionFlag.FIGHT_END,
                ],
            ),
        ):
            engine.fight(plan, initial_ship_stats=None)
            mock_load.assert_called_once_with('20260212', 'H', 5)

    def test_battle_mode_no_tracker(self, engine: CombatEngine) -> None:
        plan = CombatPlan(name='test', mode=CombatMode.BATTLE)
        with patch.object(
            engine,
            '_step',
            side_effect=[
                ConditionFlag.FIGHT_END,
            ],
        ):
            engine.fight(plan, initial_ship_stats=None)
            assert engine._tracker is None

    def test_fight_sets_ship_stats(self, engine: CombatEngine) -> None:
        plan = CombatPlan(name='test', mode=CombatMode.BATTLE)
        stats = [ShipDamageState.SEVERE, ShipDamageState.NORMAL] * 3
        with patch.object(
            engine,
            '_step',
            side_effect=[
                ConditionFlag.FIGHT_END,
            ],
        ):
            result = engine.fight(plan, initial_ship_stats=stats)
            assert result.ship_stats == stats


class TestRunCombat:
    """run_combat 便捷函数测试。"""

    def test_run_combat(self) -> None:
        ctx = MagicMock()
        ctx.ctrl = MagicMock()
        ctx.ocr = None
        plan = CombatPlan(name='test', mode=CombatMode.BATTLE)
        with patch.object(
            CombatEngine,
            'fight',
            return_value=MagicMock(flag=ConditionFlag.OPERATION_SUCCESS),
        ) as mock_fight:
            result = run_combat(ctx, plan, ship_stats=[ShipDamageState.NORMAL] * 6)
            mock_fight.assert_called_once()
            assert result.flag == ConditionFlag.OPERATION_SUCCESS
