"""地图元数据校验和非战斗路线概率测试。"""

from __future__ import annotations

import copy
import json
from collections import defaultdict
from dataclasses import FrozenInstanceError
from typing import TYPE_CHECKING, Any

import pytest
from autowsgr_native.vessel_type import VesselType

from autowsgr.combat.node_fusion import map as tracking_map
from autowsgr.combat.node_fusion.map import TrackingMap


if TYPE_CHECKING:
    from pathlib import Path


def _node(next_nodes: tuple[str, ...] = (), node_type: str = 'FIGHT') -> dict[str, Any]:
    return {
        'type': node_type,
        'detour': False,
        'night': False,
        'position': [0.5, 0.5],
        'next': list(next_nodes),
        'enemy_formations': (
            []
            if node_type in {'NULL', 'REWARD', 'LOSS'}
            else [{'formation': 1, 'ships': ['战列', '驱逐']}]
        ),
    }


def _simple() -> dict[str, Any]:
    return {'0': _node(('A',), 'NULL'), 'A': _node()}


def test_all_packaged_normal_maps_are_complete() -> None:
    paths = list(tracking_map._MAP_ROOT.glob('*.json'))
    assert len(paths) == 44
    for path in paths:
        metadata = TrackingMap.load(*path.stem.split('-'))
        assert metadata is not None
        for name in metadata.nodes:
            routes = metadata.paths_from(name)
            if metadata.nodes[name].next_nodes:
                assert sum(route.probability for route in routes) == pytest.approx(1)
            else:
                assert routes == ()


def test_ship_types_follow_installed_native_enum() -> None:
    names = {
        item.as_chinese()
        for name in dir(VesselType)
        if isinstance(item := getattr(VesselType, name), VesselType) and item.as_english() != 'NO'
    }
    assert names == tracking_map.SHIP_TYPES
    raw = _simple()
    for name in names:
        raw['A']['enemy_formations'] = [{'formation': 1, 'ships': [name]}]
        assert TrackingMap.from_dict(raw).nodes['A'].enemy_formations[0].ships == (name,)


@pytest.mark.parametrize('chapter', ['E', 'H'])
@pytest.mark.parametrize('map_id', range(1, 7))
def test_packaged_event_maps_keep_verified_routes(chapter: str, map_id: int) -> None:
    from autowsgr.infra.file_utils import load_yaml

    metadata = TrackingMap.load_event('20260930', chapter, map_id)
    assert metadata is not None
    coordinates = load_yaml(
        tracking_map._MAP_ROOT.parents[1] / 'event' / '20260930' / f'{chapter}-{map_id}.yaml'
    )
    assert set(metadata.nodes) == set(coordinates)
    for name, node in metadata.nodes.items():
        assert node.position == tuple(coordinates[name]['position'])
        assert node.next_nodes == tuple(coordinates[name]['next'])
        if not node.silent:
            assert node.enemy_formations


def test_event_metadata_does_not_guess_missing_types(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    metadata = TrackingMap.load_event('20260730', 'H', 1, 'a')
    assert metadata is not None
    assert metadata.nodes['0'].next_nodes
    assert metadata.nodes['0'].node_type is None
    assert metadata.capabilities['topology']
    assert not metadata.capabilities['encounter_history']
    monkeypatch.setattr(tracking_map, '_EVENT_MAP_ROOT', tmp_path)
    event = tmp_path / 'test_event'
    event.mkdir()
    (event / 'E-1-a.json').write_text(json.dumps(_simple()), encoding='utf-8')
    assert TrackingMap.load_event('test_event', 'E', 1, 'a') is not None
    assert TrackingMap.load_event('test_event', 'E', 1, 'b') is None
    assert TrackingMap.load_event('test_event', 'E', 1) is None
    (event / 'E-2.json').write_text(
        json.dumps({'0': {'position': [0, 0], 'next': ['A']}}), encoding='utf-8'
    )
    with pytest.raises(ValueError, match='Invalid route'):
        TrackingMap.load_event('test_event', 'E', 2)


@pytest.mark.parametrize(
    ('event', 'chapter', 'map_id', 'entrance'),
    [
        ('../test', 'E', 1, None),
        ('C:\\test', 'E', 1, None),
        ('test', '../E', 1, None),
        ('test', 'E', '../1', None),
        ('test', 'E', 1, '../a'),
    ],
)
def test_event_metadata_rejects_invalid_path_components(
    event: str, chapter: str, map_id: int | str, entrance: str | None
) -> None:
    with pytest.raises(ValueError, match='identifiers'):
        TrackingMap.load_event(event, chapter, map_id, entrance)


def test_branch_products_preserve_mass_when_silent_paths_merge() -> None:
    metadata = TrackingMap.from_dict(
        {
            '0': _node(('A', 'B'), 'NULL'),
            'A': _node(('C', 'D'), 'REWARD'),
            'B': _node(('D',), 'LOSS'),
            'C': _node(),
            'D': _node(),
        }
    )
    paths = {route.nodes: route.probability for route in metadata.paths_from('0')}
    assert paths == {('0', 'A', 'C'): 0.25, ('0', 'A', 'D'): 0.25, ('0', 'B', 'D'): 0.5}
    mass: defaultdict[str, float] = defaultdict(float)
    for path, probability in paths.items():
        mass[path[-1]] += probability
    assert mass == {'C': 0.25, 'D': 0.75}


def test_real_blank_node_routes_and_silent_terminal() -> None:
    metadata = TrackingMap.load(2, 1)
    assert metadata is not None
    assert {route.nodes for route in metadata.paths_from('0')} == {
        ('0', 'A'),
        ('0', 'B', 'C'),
        ('0', 'B', 'D', 'F'),
    }
    terminal = TrackingMap.from_dict({'0': _node(('A',), 'NULL'), 'A': _node((), 'LOSS')})
    (route,) = terminal.paths_from('0')
    assert route.nodes == ('0', 'A')
    assert terminal.nodes['A'].silent
    assert terminal.paths_from('A') == ()


def test_silent_cycles_are_rejected_but_battle_cycles_are_valid() -> None:
    raw = {'0': _node(('A',), 'NULL'), 'A': _node(('B',), 'NULL'), 'B': _node(('A',), 'LOSS')}
    with pytest.raises(ValueError, match='Silent route cycle'):
        TrackingMap.from_dict(raw)
    raw['A'] = _node(('B',))
    metadata = TrackingMap.from_dict(raw)
    (route,) = metadata.paths_from('A')
    assert route.nodes == ('A', 'B', 'A')
    assert TrackingMap.load(7, 4) is not None


def test_joint_variants_preserve_order_and_only_exact_duplicates_merge() -> None:
    raw = _simple()
    first = {'formation': 1, 'ships': ['战列', '驱逐']}
    raw['A']['enemy_formations'] = [
        first,
        copy.deepcopy(first),
        {'formation': 2, 'ships': ['战列', '驱逐']},
        {'formation': 1, 'ships': ['驱逐', '战列']},
    ]
    node = TrackingMap.from_dict(raw).nodes['A']
    assert [(v.formation, v.ships) for v in node.enemy_formations] == [
        (1, ('战列', '驱逐')),
        (2, ('战列', '驱逐')),
        (1, ('驱逐', '战列')),
    ]
    with pytest.raises(FrozenInstanceError):
        node.detour = True
    with pytest.raises(FrozenInstanceError):
        node.enemy_formations[0].formation = 2


@pytest.mark.parametrize(
    'position',
    [
        [0.5],
        [True, 0.5],
        [float('nan'), 0.5],
        [float('inf'), 0.5],
        [10**1000, 0.5],
        [-0.1, 0.5],
        [0.5, 1.1],
        ['0.5', 0.5],
    ],
)
def test_rejects_bad_positions(position: Any) -> None:
    raw = _simple()
    raw['A']['position'] = position
    with pytest.raises(ValueError, match=r'[Pp]osition'):
        TrackingMap.from_dict(raw)


@pytest.mark.parametrize(
    ('field', 'value'),
    [
        ('enemy_formations', []),
        ('next', ['missing']),
        ('next', ['A', 'A']),
        ('next', ['0']),
        ('next', 'A'),
        ('detour', 1),
        ('night', 'false'),
        ('type', 'UNKNOWN'),
    ],
)
def test_rejects_invalid_supplied_metadata(field: str, value: Any) -> None:
    raw = _simple()
    raw['A'][field] = value
    with pytest.raises(ValueError, match='A'):
        TrackingMap.from_dict(raw)


@pytest.mark.parametrize(
    'variant',
    [
        {'formation': True, 'ships': ['战列']},
        {'formation': 0, 'ships': ['战列']},
        {'formation': 6, 'ships': ['战列']},
        {'formation': 1.0, 'ships': ['战列']},
        {'formation': 1, 'ships': []},
        {'formation': 1, 'ships': ['驱逐'] * 7},
        {'formation': 1, 'ships': ['BB']},
        {'formation': 1, 'ships': ['未知舰种']},
        {'formation': 1, 'ships': ['无']},
        {'formation': 1, 'ships': [['战列']]},
        {'id': 1, 'formation': 1, 'ships': ['战列']},
    ],
)
def test_rejects_invalid_enemy_variants(variant: Any) -> None:
    raw = _simple()
    raw['A']['enemy_formations'] = [variant]
    with pytest.raises(ValueError, match='A'):
        TrackingMap.from_dict(raw)


def test_entry_and_silent_enemy_metadata_are_validated() -> None:
    metadata = TrackingMap.from_dict({'A': _node()})
    assert '0' not in metadata.nodes
    assert not metadata.capabilities['encounter_history']
    raw = _simple()
    raw['0']['enemy_formations'] = [{'formation': 1, 'ships': ['驱逐']}]
    with pytest.raises(ValueError, match='disagree'):
        TrackingMap.from_dict(raw)
    raw = _simple()
    del raw['A']['enemy_formations']
    metadata = TrackingMap.from_dict(raw)
    assert metadata.nodes['A'].enemy_formations is None
    assert metadata.capabilities['encounter_history']
    assert not metadata.capabilities['enemy']


@pytest.mark.parametrize('node_type', ['AIR_ATTACK', 'SPECIAL_POINT', 'LITTLE_BOSS'])
def test_unusual_encounters_are_not_silently_skipped(node_type: str) -> None:
    metadata = TrackingMap.from_dict(
        {
            '0': _node(('A',), 'NULL'),
            'A': _node(('B',), node_type),
            'B': _node(),
        }
    )
    assert not metadata.nodes['A'].silent
    assert metadata.paths_from('0')[0].nodes == ('0', 'A')


def test_load_missing_and_malformed_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(tracking_map, '_MAP_ROOT', tmp_path)
    assert TrackingMap.load(99, 99) is None
    bad = _simple()
    bad['0']['type'] = 'FIGHT'
    bad['0']['enemy_formations'] = [{'formation': 1, 'ships': ['驱逐']}]
    (tmp_path / '2-1.json').write_text(json.dumps(bad), encoding='utf-8')
    with pytest.raises(ValueError, match='entry node'):
        TrackingMap.load(2, 1)
    with pytest.raises(ValueError, match='identifiers'):
        TrackingMap.load('../2', 1)


def test_partial_metadata_keeps_unknown_distinct_from_false_or_terminal() -> None:
    metadata = TrackingMap.from_dict(
        {
            'A': {'position': [0.1, 0.2]},
            'B': {'position': [0.8, 0.2], 'next': [], 'detour': False},
        }
    )
    unknown = metadata.nodes['A']
    assert unknown.next_nodes is None
    assert unknown.node_type is None
    assert unknown.detour is None
    assert unknown.enemy_formations is None
    assert not unknown.silent
    assert metadata.nodes['B'].next_nodes == ()
    assert metadata.nodes['B'].detour is False
    assert metadata.capabilities == {
        'distance': True,
        'ray': True,
        'topology': False,
        'node_types': False,
        'encounter_history': False,
        'enemy': False,
        'detour': True,
    }
    assert metadata.paths_from('A') == ()
    assert any('缺少起始点' in reason for reason in metadata.degradation_reasons)
    assert any('缺少路由(A)' in reason for reason in metadata.degradation_reasons)
    assert any('缺少迂回属性(A)' in reason for reason in metadata.degradation_reasons)


def test_partial_enemy_data_keeps_known_variants_and_encounter_paths() -> None:
    raw = {'0': _node(('A', 'B'), 'NULL'), 'A': _node(), 'B': _node()}
    del raw['B']['enemy_formations']
    del raw['B']['detour']
    metadata = TrackingMap.from_dict(raw)
    assert metadata.capabilities['encounter_history']
    assert metadata.capabilities['enemy']
    assert metadata.capabilities['detour']
    assert metadata.nodes['A'].enemy_formations
    assert metadata.nodes['B'].enemy_formations is None
    assert {route.nodes for route in metadata.paths_from('0')} == {('0', 'A'), ('0', 'B')}
    assert any('缺少敌情(B)' in reason for reason in metadata.degradation_reasons)


def test_metadata_snapshot_preserves_unknown_fields_and_ignores_local_source() -> None:
    metadata = TrackingMap.from_dict(
        {'A': {'position': [0.3, 0.5]}, 'B': {'position': [0.8, 0.5], 'next': []}},
        source='first-location.yaml',
    )
    snapshot = metadata.to_dict()
    assert snapshot['A']['next'] is None
    assert snapshot['B']['next'] == []
    restored = TrackingMap.from_dict(snapshot, source='another-location.yaml')
    assert restored.fingerprint == metadata.fingerprint
    assert restored.nodes == metadata.nodes
    snapshot['A']['next'] = []
    assert TrackingMap.from_dict(snapshot).fingerprint != metadata.fingerprint


def test_old_pixel_maps_keep_no_entry_and_no_routing() -> None:
    metadata = TrackingMap.load_event('20220928', 'E', 1)
    assert metadata is not None
    assert '0' not in metadata.nodes
    assert metadata.nodes['A'].position == pytest.approx((405 / 960, 98 / 540))
    assert all(node.next_nodes is None for node in metadata.nodes.values())
    assert metadata.capabilities['distance']
    assert not metadata.capabilities['topology']
    assert not metadata.capabilities['encounter_history']
    assert metadata.source.endswith('E-1.yaml')


@pytest.mark.parametrize('chapter', ['E', 'H'])
@pytest.mark.parametrize('map_id', [3, 4, 6])
def test_old_maps_keep_multiple_known_entrances_separate(chapter: str, map_id: int) -> None:
    metadata = TrackingMap.load_event('20260104', chapter, map_id)
    assert metadata is not None
    assert '0' not in metadata.nodes
    assert metadata.nodes['α'].position != metadata.nodes['β'].position
    assert metadata.nodes['α'].silent
    assert metadata.nodes['β'].silent
    assert metadata.nodes['A'].node_type is None
    assert all(node.next_nodes is None for node in metadata.nodes.values())
    assert not metadata.capabilities['encounter_history']


def test_multiple_entrance_map_rejects_contradictory_type(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(tracking_map, '_MAP_ROOT', tmp_path / 'tracking')
    monkeypatch.setattr(tracking_map, '_COORDINATE_ROOT', tmp_path)
    (tmp_path / 'normal').mkdir()
    (tmp_path / 'normal' / '99-1.yaml').write_text(
        'α: {position: [0.1, 0.2], type: FIGTH}\nβ: [100, 200]\n', encoding='utf-8'
    )
    with pytest.raises(ValueError, match='entry node'):
        TrackingMap.load(99, 1)


def test_json_precedes_yaml_and_invalid_json_never_silently_falls_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    json_root = tmp_path / 'tracking'
    json_root.mkdir()
    coordinate_root = tmp_path / 'coordinates'
    (coordinate_root / 'normal').mkdir(parents=True)
    (coordinate_root / 'normal' / '2-1.yaml').write_text(
        'A: [405, 98]\nB: [600, 200]\n', encoding='utf-8'
    )
    monkeypatch.setattr(tracking_map, '_MAP_ROOT', json_root)
    monkeypatch.setattr(tracking_map, '_COORDINATE_ROOT', coordinate_root)
    fallback = TrackingMap.load(2, 1)
    assert fallback is not None
    assert fallback.source.endswith('.yaml')
    assert not fallback.capabilities['encounter_history']
    target = json_root / '2-1.json'
    target.write_text(json.dumps(_simple()), encoding='utf-8')
    preferred = TrackingMap.load(2, 1)
    assert preferred is not None
    assert preferred.source.endswith('.json')
    assert preferred.capabilities['encounter_history']
    target.write_text('{broken', encoding='utf-8')
    with pytest.raises(json.JSONDecodeError):
        TrackingMap.load(2, 1)


@pytest.mark.parametrize('body', ['A: [961, 20]', 'A: [20, 541]', 'A: [true, 20]', 'A: [20]'])
def test_old_pixel_map_rejects_invalid_positions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, body: str
) -> None:
    monkeypatch.setattr(tracking_map, '_MAP_ROOT', tmp_path / 'tracking')
    monkeypatch.setattr(tracking_map, '_COORDINATE_ROOT', tmp_path)
    (tmp_path / 'normal').mkdir()
    (tmp_path / 'normal' / '99-1.yaml').write_text(body, encoding='utf-8')
    with pytest.raises(ValueError, match='position'):
        TrackingMap.load(99, 1)
