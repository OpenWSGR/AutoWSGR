"""测试 autowsgr.combat.history。"""

from __future__ import annotations

import pytest

from autowsgr.combat.history import (
    CombatEvent,
    CombatHistory,
    CombatResult,
    EventType,
    FightResult,
)
from autowsgr.types import ConditionFlag


class TestCombatEvent:
    """CombatEvent 测试。"""

    def test_str_basic(self) -> None:
        event = CombatEvent(event_type=EventType.RESULT, node='A', result='S')
        assert '[RESULT]' in str(event)
        assert '节点=A' in str(event)
        assert '结果=S' in str(event)

    def test_str_minimal(self) -> None:
        event = CombatEvent(event_type=EventType.SL)
        assert str(event) == '[SL]'

    def test_defaults(self) -> None:
        event = CombatEvent(event_type=EventType.FORMATION)
        assert event.node == ''
        assert event.action == ''
        assert event.enemies is None
        assert event.extra == {}


class TestFightResult:
    """FightResult 测试。"""

    def test_str_with_data(self) -> None:
        fr = FightResult(mvp=2, grade='S', dropped_ship='岛风')
        s = str(fr)
        assert 'MVP=2' in s
        assert '掉落=岛风' in s
        assert '评价=S' in s

    def test_grade_comparison(self) -> None:
        s = FightResult(grade='S')
        a = FightResult(grade='A')
        assert a < s
        assert s > a
        assert a <= s
        assert s >= a

    def test_grade_comparison_with_str(self) -> None:
        s = FightResult(grade='S')
        assert s > 'A'
        assert s >= 'S'
        assert s < 'SS'

    def test_grade_comparison_not_implemented(self) -> None:
        s = FightResult(grade='S')
        with pytest.raises(TypeError):
            _ = s < 123

    def test_defaults(self) -> None:
        fr = FightResult()
        assert fr.mvp is None
        assert fr.grade == ''
        assert len(fr.ship_stats) == 6


class TestCombatHistory:
    """CombatHistory 测试。"""

    def test_add_and_len(self) -> None:
        h = CombatHistory()
        h.add(CombatEvent(EventType.RESULT))
        assert len(h) == 1

    def test_reset(self) -> None:
        h = CombatHistory()
        h.add(CombatEvent(EventType.RESULT))
        h.reset()
        assert len(h) == 0

    def test_last_node(self) -> None:
        h = CombatHistory()
        assert h.last_node == ''
        h.add(CombatEvent(EventType.RESULT, node='B'))
        assert h.last_node == 'B'

    def test_get_fight_results_empty(self) -> None:
        h = CombatHistory()
        # 空结果时返回空 dict（因为 results_list or results_dict）
        assert h.get_fight_results() == {}

    def test_get_fight_results_with_ship_drop(self) -> None:
        h = CombatHistory()
        h.add(CombatEvent(EventType.RESULT, node='A', result='S'))
        h.add(CombatEvent(EventType.GET_SHIP, result='岛风'))
        results = h.get_fight_results_list()
        assert len(results) == 1
        assert results[0].grade == 'S'
        assert results[0].dropped_ship == '岛风'

    def test_get_fight_results_dict_format(self) -> None:
        h = CombatHistory()
        h.add(CombatEvent(EventType.RESULT, node='A', result='S'))
        h.add(CombatEvent(EventType.RESULT, node='B', result='A'))
        results = h.get_fight_results()
        assert isinstance(results, dict)
        assert results['A'].grade == 'S'
        assert results['B'].grade == 'A'

    def test_str_repr(self) -> None:
        h = CombatHistory()
        h.add(CombatEvent(EventType.SL))
        assert repr(h) == 'CombatHistory(1 events)'
        assert 'SL' in str(h)


class TestCombatResult:
    """CombatResult 测试。"""

    def test_defaults(self) -> None:
        result = CombatResult()
        assert result.flag == ConditionFlag.FIGHT_END
        assert result.node_count == 0
        assert result.ship_full is False

    def test_fight_results_property(self) -> None:
        result = CombatResult()
        result.history.add(CombatEvent(EventType.RESULT, result='S'))
        frs = result.fight_results
        assert len(frs) == 1
        assert frs[0].grade == 'S'
