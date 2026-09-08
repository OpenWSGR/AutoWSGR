from __future__ import annotations

import re
from pathlib import Path

from autowsgr.contracts.vessel_types import FLEET_VESSEL_TYPE_BY_CODE
from autowsgr.infra import load_yaml
from autowsgr.ops.decisive.config import MapData


DATA_DIR = (
    Path(__file__).resolve().parents[2]
    / 'autowsgr'
    / 'data'
    / 'map'
    / 'decisive_battle'
    / 'silent_warrior'
)

ENEMY_CODES = {code.upper() for code in FLEET_VESSEL_TYPE_BY_CODE} | {'AF'}


def test_silent_warrior_map_graph_contract() -> None:
    paths = sorted(DATA_DIR.glob('EX-*.yaml'))

    assert len(paths) == 18
    maps = [load_yaml(path) for path in paths]
    assert {path.stem for path in paths} == {map_data['map_id'] for map_data in maps}
    assert sum(len(map_data['nodes']) for map_data in maps) == 319
    assert sum(len(node['next']) for map_data in maps for node in map_data['nodes'].values()) == 401

    for map_data in maps:
        map_id = map_data['map_id']
        chapter, stage = (int(value) for value in map_id.removeprefix('EX-').split('-'))
        assert map_data['chapter'] == chapter
        assert map_data['stage'] == stage

        nodes = map_data['nodes']
        labels = {node['label'] for node in nodes.values() if node['label'] != '0'}
        assert set(map_data['enemy']) == labels
        assert set(map_data['key_points']) <= labels
        for formation in map_data['enemy'].values():
            assert formation
            assert set(formation) <= ENEMY_CODES

        for node_id, node in nodes.items():
            assert all(next_id in nodes for next_id in node['next'])
            if node_id != '0':
                assert node['label'] == re.sub(r'\d+$', '', node_id)

        terminal_labels = {
            node['label'] for node in nodes.values() if node['label'] != '0' and not node['next']
        }
        assert len(terminal_labels) == 1


def test_decisive_runtime_queries_use_map_files() -> None:
    assert MapData.get_stage_end_node(6, 2) == 'J'
    assert MapData.get_key_points(6, 2) == {'C', 'H', 'J'}
    assert MapData.get_enemy(6, 1, 'J') == ['AF', 'BB', 'DD', 'BB', 'BC', 'AV']
    assert MapData.get_leftmost_choices(6, 2, '0') == ['A1', 'A2', 'A3']
    assert MapData.get_leftmost_choices(6, 2, 'A') == ['B1']
    assert MapData.get_leftmost_choices(6, 1, 'A') == ['B1', 'B2']
