"""验证 EX 地图迁移保留原图路线、敌方编队顺序和战术决策，资料缺失时保留未知。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from autowsgr.infra import DecisiveConfig
from autowsgr.ops.decisive.config import MapData, enemy_codes_to_slots
from autowsgr.ops.decisive.logic import DecisiveLogic, _count_anti_sub
from autowsgr.ops.decisive.state import DecisiveState
from autowsgr.types import Formation


# 18 份 ShiinaKuroko EX 原始 YAML 解析后的摘要，不受换行或字典顺序影响。
_SOURCE_DIGEST = '749a8c66348b7f9ac41d2a0a3ca04550d1d3c4c7f1e21d8a8c2da53a0407539d'


def test_all_ex_maps_preserve_topology_enemy_order_and_tactics() -> None:
    root = Path(__file__).resolve().parents[2] / 'autowsgr/data/map/decisive_battle/silent_warrior'
    rows = [yaml.safe_load(path.read_bytes()) for path in sorted(root.glob('EX-*.yaml'))]
    payload = json.dumps(rows, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
    assert hashlib.sha256(payload).hexdigest() == _SOURCE_DIGEST
    assert len(rows) == 18
    nodes = edges = records = 0
    for row in rows:
        chapter, stage = row['chapter'], row['stage']
        routes = MapData.get_route_nodes(chapter, stage)
        metadata = MapData.tracking_map(chapter, stage)
        nodes += len(routes)
        assert set(routes) == row['nodes'].keys()
        assert MapData.get_key_points(chapter, stage) == set(row['key_points'])
        state = DecisiveState(chapter=chapter, stage=stage)
        logic = DecisiveLogic(DecisiveConfig(chapter=chapter), state)
        for index, route in routes.items():
            assert route.next_nodes == tuple(row['nodes'][index]['next'])
            edges += len(route.next_nodes)
            if index != '0':
                assert MapData.is_stage_end(chapter, stage, index) == (not route.next_nodes)
                successors = tuple(dict.fromkeys(routes[item].label for item in route.next_nodes))
                assert metadata.nodes[route.label].next_nodes == successors
        for label, raw in row['enemy'].items():
            records += 1
            slots = MapData.get_enemy(chapter, stage, label)
            assert slots == enemy_codes_to_slots(raw)
            assert len(slots) == 6
            assert metadata.nodes[label].enemy_formations[0].ships == tuple(slots)
            for has_sub in (False, True):
                state.fleet[1] = 'U-1206' if has_sub else ''
                expected = (
                    Formation.wedge
                    if _count_anti_sub(slots) <= has_sub
                    else Formation.double_column
                )
                assert logic.get_formation(label) == expected
    assert (nodes, edges, records) == (319, 401, 154)


@pytest.mark.parametrize(
    ('chapter', 'stage', 'node', 'slots'),
    [
        (4, 1, 'G', ['战列', '大巡', '重巡', '重巡', '轻巡', '驱逐']),
        (4, 3, 'G', ['战列', '战列', '战列', '重巡', '重巡', '重巡']),
        (6, 3, 'D', ['战列', '战巡', '战列', '航母', '导驱', '轻巡']),
    ],
)
def test_conflicting_legacy_records_use_ex(
    chapter: int, stage: int, node: str, slots: list[str]
) -> None:
    assert MapData.get_enemy(chapter, stage, node) == slots


def test_six_slot_loader_preserves_airport_and_internal_empty_slot() -> None:
    assert MapData.get_enemy(6, 1, 'A') == ['轻巡', '轻巡', None, None, None, None]
    assert MapData.get_enemy(6, 1, 'J')[0] == '机场'
    assert MapData.get_enemy(6, 2, 'J')[3] == '机场'
    assert enemy_codes_to_slots(['大巡', '', '导战', '补给']) == [
        '大巡',
        None,
        '导战',
        '补给',
        None,
        None,
    ]


@pytest.mark.parametrize('raw', [['INVALID'], [42], ['', ['轻巡']], [''] * 7, '驱逐'])
def test_invalid_enemy_data_is_reported(raw: object) -> None:
    with pytest.raises((ValueError, TypeError), match='决战敌情'):
        enemy_codes_to_slots(raw)


def test_decisive_metadata_preserves_unknown_geometry_and_formation() -> None:
    metadata = MapData.tracking_map(6, 1)
    assert tuple(metadata.nodes) == tuple('ABCDEFGHIJ')
    assert metadata.nodes['A'].next_nodes == ('B',)
    assert metadata.nodes['J'].next_nodes == ()
    assert all(node.position is None and node.detour is None for node in metadata.nodes.values())
    assert metadata.nodes['J'].enemy_formations[0].formation is None
    assert metadata.nodes['J'].enemy_formations[0].ships[0] == '机场'
    assert not metadata.capabilities['distance']
    assert not metadata.capabilities['ray']
    assert '0' not in metadata.nodes
    assert MapData.tracking_map(1, 1).nodes['A'].enemy_formations[0].ships[0] == '轻巡'
    assert MapData.get_enemy(6, 1, 'unknown') == []


def test_ordered_signatures_distinguish_equal_ship_counts() -> None:
    first, later = MapData.get_enemy(6, 3, 'A'), MapData.get_enemy(6, 3, 'H')
    assert sorted(first) == sorted(later)
    assert first != later


def test_key_point_and_end_queries_keep_existing_semantics() -> None:
    assert MapData.get_key_points(1, 1) == set('BDF')
    assert MapData.get_key_points(6, 1) == set('BGJ')
    assert MapData.is_stage_end(6, 1, 'J')
    assert not MapData.is_stage_end(6, 1, 'K')
    with pytest.raises(ValueError, match='无效章节'):
        MapData.get_stage_end_node(6, 4)
