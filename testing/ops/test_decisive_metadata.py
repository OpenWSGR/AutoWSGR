"""决战中文迁移保留全部旧槽位及战术决策，未知资料不伪造信息。"""

from __future__ import annotations

import hashlib
import json

import pytest
from autowsgr_native.vessel_type import VesselType

from autowsgr.infra import DecisiveConfig
from autowsgr.ops.decisive.config import MapData, _enemy_slots, _load_enemy_spec_data
from autowsgr.ops.decisive.logic import DecisiveLogic, _count_anti_sub
from autowsgr.ops.decisive.state import DecisiveState
from autowsgr.types import Formation


# 282ca457 原始 84 节点列表的摘要；包含章、小关、节点、首位占位及空槽。
_LEGACY_DIGEST = 'b495cbe91e764f4bf319b367837ae6465da2b5df698953fe39761b9f9b8d063b'
_LEGACY_ANTI_SUB = {
    (4, 1): '32244322',
    (4, 2): '31212130',
    (4, 3): '0221120110',
    (5, 1): '11104431',
    (5, 2): '3210202210',
    (5, 3): '1220320121',
    (6, 1): '2002232331',
    (6, 2): '3101200012',
    (6, 3): '1011200110',
}


def test_all_84_migrated_fleets_preserve_order_and_placeholder() -> None:
    legacy_codes = {
        value.as_chinese(): value.as_english()
        for name in dir(VesselType)
        if isinstance(value := getattr(VesselType, name), VesselType)
    }
    legacy_codes.update({'机场': 'AF', '大巡': 'BG', '导战': 'BBG', '': ''})
    rows = [
        (chapter, stage, node, [legacy_codes[ship] for ship in ships])
        for chapter, chapters in enumerate(_load_enemy_spec_data()['enemy'])
        if isinstance(chapters, list)
        for stage, stages in enumerate(chapters)
        if isinstance(stages, dict)
        for node, ships in stages.items()
    ]
    assert len(rows) == 84
    payload = json.dumps(rows, ensure_ascii=False, separators=(',', ':')).encode()
    assert hashlib.sha256(payload).hexdigest() == _LEGACY_DIGEST


@pytest.mark.parametrize(('chapter', 'stage'), _LEGACY_ANTI_SUB)
@pytest.mark.parametrize('submarine', [False, True])
def test_all_84_formation_decisions_match_legacy(chapter: int, stage: int, submarine: bool) -> None:
    state = DecisiveState(chapter=chapter, stage=stage, node='A')
    if submarine:
        state.fleet[1] = 'U-1206'
    logic = DecisiveLogic(DecisiveConfig(chapter=chapter), state)
    for index, count in enumerate(_LEGACY_ANTI_SUB[chapter, stage]):
        node = chr(ord('A') + index)
        slots = MapData.get_enemy(chapter, stage, node)
        assert len(slots) == 6
        assert _count_anti_sub(slots) == int(count)
        expected = Formation.wedge if int(count) <= int(submarine) else Formation.double_column
        assert logic.get_formation(node) == expected
    # 计算其它候选的战术不修改用于界面显示的当前节点。
    assert state.node == 'A'


def test_six_slot_loader_preserves_airport_and_internal_empty_slot() -> None:
    assert MapData.get_enemy(6, 1, 'A') == ['轻巡', '轻巡', None, None, None, None]
    assert MapData.get_enemy(6, 1, 'J')[0] == '机场'
    assert MapData.get_enemy(6, 2, 'J')[3] == '机场'
    assert _enemy_slots(['', '大巡', '', '导战', '补给'], 'test') == [
        '大巡',
        None,
        '导战',
        '补给',
        None,
        None,
    ]


@pytest.mark.parametrize('raw', [['DD'], ['', 'AF'], ['', ['轻巡']], [''] * 8, '驱逐'])
def test_invalid_enemy_data_is_reported(raw: object) -> None:
    with pytest.raises(ValueError, match='决战敌情'):
        _enemy_slots(raw, '6-1 A')


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
    assert MapData.tracking_map(1, 1).nodes['A'].enemy_formations is None
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
