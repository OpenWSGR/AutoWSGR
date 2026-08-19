"""测试 autowsgr.ops.decisive.config。"""

from __future__ import annotations

import pytest

from autowsgr.ops.decisive.config import MapData


class TestMapDataGetStageEndNode:
    """MapData.get_stage_end_node 测试。"""

    def test_chapter1_stage1(self) -> None:
        assert MapData.get_stage_end_node(1, 1) == 'F'

    def test_chapter1_stage3(self) -> None:
        assert MapData.get_stage_end_node(1, 3) == 'H'

    def test_chapter6_stage3(self) -> None:
        assert MapData.get_stage_end_node(6, 3) == 'J'

    def test_invalid_chapter_raises(self) -> None:
        with pytest.raises(ValueError, match='无效'):
            MapData.get_stage_end_node(0, 1)

    def test_invalid_stage_raises(self) -> None:
        with pytest.raises(ValueError, match='无效'):
            MapData.get_stage_end_node(1, 4)


class TestMapDataIsStageEnd:
    """MapData.is_stage_end 测试。"""

    def test_is_end(self) -> None:
        assert MapData.is_stage_end(1, 1, 'F') is True

    def test_is_not_end(self) -> None:
        assert MapData.is_stage_end(1, 1, 'A') is False


class TestMapDataGetKeyPoints:
    """MapData.get_key_points 测试。"""

    def test_chapter1_stage2(self) -> None:
        kp = MapData.get_key_points(1, 2)
        assert 'B' in kp
        assert 'F' in kp
        assert 'H' in kp

    def test_invalid_returns_empty(self) -> None:
        assert MapData.get_key_points(1, 10) == set()


class TestMapDataIsKeyPoint:
    """MapData.is_key_point 测试。"""

    def test_is_key_point(self) -> None:
        assert MapData.is_key_point(1, 2, 'B') is True

    def test_is_not_key_point(self) -> None:
        assert MapData.is_key_point(1, 2, 'A') is False


class TestMapDataGetEnemy:
    """MapData.get_enemy 测试。"""

    def test_invalid_returns_empty(self) -> None:
        assert MapData.get_enemy(99, 1, 'A') == []
