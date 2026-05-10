"""测试 autowsgr.combat.node_tracker。"""

from __future__ import annotations

import numpy as np
import pytest

from autowsgr.combat.node_tracker import (
    MapNodeData,
    NodePosition,
    NodeTracker,
    _euclidean_distance,
    _point_to_ray_distance,
)


class TestNodePosition:
    """NodePosition 数据类测试。"""

    def test_defaults(self) -> None:
        pos = NodePosition(name='A', x=0.5, y=0.5)
        assert pos.name == 'A'
        assert pos.x == 0.5
        assert pos.y == 0.5
        assert pos.next_nodes == []

    def test_with_next_nodes(self) -> None:
        pos = NodePosition(name='A', x=0.1, y=0.2, next_nodes=['B', 'C'])
        assert pos.next_nodes == ['B', 'C']


class TestMapNodeData:
    """MapNodeData 解析与查询测试。"""

    def test_parse_standard_format(self) -> None:
        raw = {
            '0': {'position': [0.1, 0.2], 'next': ['A']},
            'A': {'position': [0.3, 0.4], 'next': ['B']},
            'B': {'position': [0.5, 0.6], 'next': []},
        }
        data = MapNodeData._parse(raw)
        assert len(data) == 3
        assert 'A' in data
        assert data.get('A') == NodePosition(name='A', x=0.3, y=0.4, next_nodes=['B'])

    def test_node_names_excludes_zero(self) -> None:
        raw = {
            '0': {'position': [0.0, 0.0], 'next': ['A']},
            'A': {'position': [0.1, 0.1], 'next': []},
        }
        data = MapNodeData._parse(raw)
        assert data.node_names == ['A']

    def test_contains(self) -> None:
        data = MapNodeData._parse({'A': {'position': [0.1, 0.2], 'next': []}})
        assert 'A' in data
        assert 'Z' not in data

    def test_get_missing_returns_none(self) -> None:
        data = MapNodeData._parse({})
        assert data.get('X') is None

    def test_parse_ignores_invalid_value(self) -> None:
        raw = {'A': 'invalid'}
        data = MapNodeData._parse(raw)
        assert 'A' not in data


class TestEuclideanDistance:
    """欧氏距离计算测试。"""

    def test_zero_distance(self) -> None:
        assert _euclidean_distance(1.0, 2.0, 1.0, 2.0) == 0.0

    def test_3_4_5_triangle(self) -> None:
        assert _euclidean_distance(0.0, 0.0, 3.0, 4.0) == 5.0

    def test_negative_coords(self) -> None:
        assert _euclidean_distance(-1.0, -1.0, 2.0, 3.0) == 5.0


class TestPointToRayDistance:
    """点到射线距离计算测试。"""

    def test_point_behind_ray(self) -> None:
        """点在射线后方，距离退化为到起点距离。"""
        dist = _point_to_ray_distance(0.0, 0.0, 1.0, 0.0, 1.0, 0.0)
        assert dist == pytest.approx(1.0)

    def test_point_on_ray(self) -> None:
        """点在射线上，距离为 0。"""
        dist = _point_to_ray_distance(2.0, 0.0, 1.0, 0.0, 1.0, 0.0)
        assert dist == pytest.approx(0.0)

    def test_perpendicular_distance(self) -> None:
        """点在射线正侧方。"""
        dist = _point_to_ray_distance(1.0, 1.0, 0.0, 0.0, 1.0, 0.0)
        assert dist == pytest.approx(1.0)

    def test_zero_direction(self) -> None:
        """方向向量为零时退化为到起点距离。"""
        dist = _point_to_ray_distance(3.0, 4.0, 0.0, 0.0, 0.0, 0.0)
        assert dist == pytest.approx(5.0)


class TestNodeTracker:
    """NodeTracker 节点判定逻辑测试。"""

    @pytest.fixture
    def map_data(self) -> MapNodeData:
        raw = {
            '0': {'position': [0.1, 0.1], 'next': ['A']},
            'A': {'position': [0.3, 0.3], 'next': ['B', 'C']},
            'B': {'position': [0.5, 0.3], 'next': []},
            'C': {'position': [0.3, 0.5], 'next': []},
        }
        return MapNodeData._parse(raw)

    def test_init_state(self, map_data: MapNodeData) -> None:
        tracker = NodeTracker(map_data)
        assert tracker.current_node == '0'
        assert tracker.ship_position is None

    def test_reset(self, map_data: MapNodeData) -> None:
        tracker = NodeTracker(map_data)
        tracker._ship_position = (0.5, 0.5)
        tracker._current_node = 'A'
        tracker.reset()
        assert tracker.current_node == '0'
        assert tracker.ship_position is None

    def test_update_node_no_position(self, map_data: MapNodeData) -> None:
        tracker = NodeTracker(map_data)
        assert tracker.update_node() == '0'

    def test_update_node_no_movement(self, map_data: MapNodeData) -> None:
        tracker = NodeTracker(map_data)
        tracker._ship_position = (0.3, 0.3)
        tracker._last_ship_position = (0.3, 0.3)
        assert tracker.update_node() == '0'

    def test_update_node_ray_hit_to_B(self, map_data: MapNodeData) -> None:
        tracker = NodeTracker(map_data)
        tracker._current_node = 'A'
        tracker._ship_position = (0.5, 0.3)
        tracker._last_ship_position = (0.3, 0.3)
        assert tracker.update_node() == 'B'

    def test_update_node_ray_hit_to_C(self, map_data: MapNodeData) -> None:
        tracker = NodeTracker(map_data)
        tracker._current_node = 'A'
        tracker._ship_position = (0.3, 0.5)
        tracker._last_ship_position = (0.3, 0.3)
        assert tracker.update_node() == 'C'

    def test_update_node_no_ray_fallback(self, map_data: MapNodeData) -> None:
        tracker = NodeTracker(map_data)
        tracker._current_node = 'A'
        tracker._ship_position = (0.5, 0.3)
        tracker._last_ship_position = (0.5, 0.3)
        assert tracker.update_node() == 'A'

    def test_update_node_missing_next_nodes(self, map_data: MapNodeData) -> None:
        tracker = NodeTracker(map_data)
        tracker._current_node = 'B'
        tracker._ship_position = (0.9, 0.9)
        tracker._last_ship_position = (0.8, 0.8)
        assert tracker.update_node() == 'B'

    def test_update_node_no_prev_position(self, map_data: MapNodeData) -> None:
        tracker = NodeTracker(map_data)
        tracker._current_node = 'A'
        tracker._ship_position = (0.5, 0.3)
        assert tracker.update_node() == 'A'


class TestNodeTrackerYellowCluster:
    """NodeTracker 黄色簇检测测试（使用小 ndarray）。"""

    def test_find_yellow_cluster_no_match(self) -> None:
        """全黑图像不应匹配任何黄色簇。"""
        screen = np.zeros((100, 100, 3), dtype=np.uint8)
        result = NodeTracker._find_yellow_cluster(screen)
        assert result is None

    def test_find_yellow_cluster_single_blob(self) -> None:
        """在图像中心绘制一个足够大的黄色块，应返回中心坐标。"""
        screen = np.zeros((100, 100, 3), dtype=np.uint8)
        screen[40:60, 40:60] = [230, 210, 100]  # RGB, 20x20=400 > _min_area 200
        result = NodeTracker._find_yellow_cluster(screen)
        assert result is not None
        rx, ry = result
        assert 0.45 <= rx <= 0.55
        assert 0.45 <= ry <= 0.55

    def test_recheck_pixel_true(self) -> None:
        screen = np.zeros((100, 100, 3), dtype=np.uint8)
        screen[50, 50] = [239, 219, 106]
        screen[50, 47] = [231, 222, 101]
        screen[50, 53] = [231, 222, 101]
        tracker = NodeTracker(MapNodeData._parse({}))
        assert tracker._recheck_pixel((0.5, 0.5), screen) is True

    def test_recheck_pixel_false(self) -> None:
        screen = np.zeros((100, 100, 3), dtype=np.uint8)
        tracker = NodeTracker(MapNodeData._parse({}))
        assert tracker._recheck_pixel((0.5, 0.5), screen) is False
