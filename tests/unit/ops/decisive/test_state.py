"""测试 autowsgr.ops.decisive.state。"""

from __future__ import annotations

from autowsgr.ops.decisive.state import DecisiveState
from autowsgr.types import DecisivePhase


class TestDecisiveState:
    """DecisiveState 测试。"""

    def test_defaults(self) -> None:
        s = DecisiveState()
        assert s.chapter == 6
        assert s.stage == 0
        assert s.node == 'U'
        assert s.phase == DecisivePhase.INIT
        assert s.score == 10
        assert s.ships == set()
        assert len(s.fleet) == 7
        assert s.fleet[0] == ''
        assert len(s.ship_stats) == 6

    def test_custom_chapter(self) -> None:
        s = DecisiveState(chapter=3)
        assert s.chapter == 3

    def test_reset_preserves_chapter(self) -> None:
        s = DecisiveState(chapter=2)
        s.stage = 2
        s.node = 'C'
        s.reset()
        assert s.chapter == 2
        assert s.stage == 0
        assert s.node == 'U'

    def test_is_begin_initial(self) -> None:
        s = DecisiveState()
        assert s.is_begin() is True

    def test_is_begin_stage1(self) -> None:
        s = DecisiveState()
        s.stage = 1
        s.node = 'A'
        assert s.is_begin() is True

    def test_is_begin_not_begin(self) -> None:
        s = DecisiveState()
        s.stage = 2
        s.node = 'B'
        assert s.is_begin() is False
