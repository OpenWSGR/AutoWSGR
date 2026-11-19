"""决战 EX 地图：分支路线 ID 与可观测的节点字母分别查询。"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from autowsgr_native.vessel_type import VesselType

from autowsgr.combat.node_fusion.map import SHIP_TYPES, TrackingMap
from autowsgr.infra.file_utils import load_yaml


if TYPE_CHECKING:
    from collections.abc import Sequence


_MAP_DATA_ROOT = (
    Path(__file__).resolve().parents[2] / 'data' / 'map' / 'decisive_battle' / 'silent_warrior'
)


@dataclass(frozen=True, slots=True)
class DecisiveRouteNode:
    """一个路线卡片的位置；column/index 是拓扑索引，不是屏幕坐标。"""

    label: str
    column: int
    index: int
    next_nodes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _MapGraph:
    nodes: dict[str, DecisiveRouteNode]
    enemies: dict[str, tuple[str | None, ...]]
    key_points: frozenset[str]
    stage_end: str


def enemy_codes_to_slots(enemy: Sequence[str | None]) -> list[str | None]:
    """按 EX 敌方编队顺序返回六个位置的中文舰种。空位记为 None，缺失敌情返回 []。

    AF 是 EX 资料的机场代码，与 native 的 AP 补给舰不同。
    遇到未知代码时报错，以便核对原始敌情。
    """
    if not isinstance(enemy, (list, tuple)) or len(enemy) > 6:
        raise ValueError('决战敌情应为列表，最多容纳六艘舰船')
    if not enemy:
        return []
    slots: list[str | None] = []
    for code in enemy:
        if code is None or code == '':
            slots.append(None)
            continue
        if not isinstance(code, str):
            raise TypeError(f'决战敌情包含无效舰类: {code!r}')
        if code in SHIP_TYPES:
            slots.append(code)
            continue
        native_code = 'Airfield' if code.upper() == 'AF' else code.upper()
        try:
            native = VesselType.from_english(native_code)
        except (AttributeError, ValueError) as exc:
            raise ValueError(f'决战敌情包含未知舰类: {code!r}') from exc
        if native is None or native.as_chinese() not in SHIP_TYPES:
            raise ValueError(f'决战敌情包含未知舰类: {code!r}')
        slots.append(native.as_chinese())
    return slots + [None] * (6 - len(slots))


def _check_map_id(chapter: int, stage: int) -> None:
    if (
        type(chapter) is not int
        or type(stage) is not int
        or not 1 <= chapter <= 6
        or not 1 <= stage <= 3
    ):
        raise ValueError(f'无效章节/小关: chapter={chapter}, stage={stage}')


@lru_cache(maxsize=18)
def _load_map_data(chapter: int, stage: int) -> _MapGraph:
    _check_map_id(chapter, stage)
    path = _MAP_DATA_ROOT / f'EX-{chapter}-{stage}.yaml'
    data = load_yaml(path)
    if not isinstance(data, dict) or data.get('chapter') != chapter or data.get('stage') != stage:
        raise ValueError(f'决战地图编号不一致: {path}')
    raw_nodes = data.get('nodes')
    if not isinstance(raw_nodes, dict) or '0' not in raw_nodes:
        raise ValueError(f'决战地图缺少路线图: {path}')
    nodes = {}
    for node_id, raw in raw_nodes.items():
        if not isinstance(node_id, str) or not isinstance(raw, dict):
            raise TypeError(f'决战路线节点无效: {path}: {node_id!r}')
        label, successors = raw.get('label'), raw.get('next')
        if (
            not isinstance(label, str)
            or not label
            or not isinstance(successors, list)
            or any(not isinstance(target, str) or target not in raw_nodes for target in successors)
            or len(set(successors)) != len(successors)
            or type(raw.get('column')) is not int
            or type(raw.get('index')) is not int
            or raw['column'] < 0
            or raw['index'] < 0
        ):
            raise ValueError(f'决战路线数据无效: {path}: {node_id}')
        nodes[node_id] = DecisiveRouteNode(
            label.upper(), raw['column'], raw['index'], tuple(successors)
        )
    terminal_labels = {
        node.label for node_id, node in nodes.items() if node_id != '0' and not node.next_nodes
    }
    if len(terminal_labels) != 1:
        raise ValueError(f'决战地图必须具有唯一终点字母: {path}')
    labels = {node.label for node_id, node in nodes.items() if node_id != '0'}
    raw_enemies = data.get('enemy', {})
    raw_keys = data.get('key_points', [])
    if not isinstance(raw_enemies, dict) or any(label not in labels for label in raw_enemies):
        raise ValueError(f'决战敌情节点无效: {path}')
    if not isinstance(raw_keys, list) or any(label not in labels for label in raw_keys):
        raise ValueError(f'决战关键节点无效: {path}')
    enemies = {label: tuple(enemy_codes_to_slots(ships)) for label, ships in raw_enemies.items()}
    return _MapGraph(nodes, enemies, frozenset(raw_keys), terminal_labels.pop())


class MapData:
    """唯一 EX 数据源；原生定位使用字母，路线选择使用带后缀的 ID。"""

    @staticmethod
    def get_stage_end_node(chapter: int, stage: int) -> str:
        """返回共同终点字母；这是静态预测，不能代替实际通关画面。"""
        return _load_map_data(chapter, stage).stage_end

    @staticmethod
    def get_node_label(chapter: int, stage: int, node: str) -> str | None:
        """接受节点字母或精确路线 ID，未知节点返回 None。"""
        graph = _load_map_data(chapter, stage)
        value = node.strip().upper()
        route_node = graph.nodes.get(value)
        if route_node is not None:
            return route_node.label
        return value if any(item.label == value for item in graph.nodes.values()) else None

    @staticmethod
    def is_stage_end(chapter: int, stage: int, node: str) -> bool:
        return MapData.get_node_label(chapter, stage, node) == MapData.get_stage_end_node(
            chapter, stage
        )

    @staticmethod
    def get_key_points(chapter: int, stage: int) -> set[str]:
        """返回 EX 声明的夜战关键字母，非法编号不产生关键节点。"""
        try:
            _check_map_id(chapter, stage)
        except ValueError:
            return set()
        return set(_load_map_data(chapter, stage).key_points)

    @staticmethod
    def is_key_point(chapter: int, stage: int, node: str) -> bool:
        return MapData.get_node_label(chapter, stage, node) in MapData.get_key_points(
            chapter, stage
        )

    @staticmethod
    def get_enemy(chapter: int, stage: int, node: str) -> list[str | None]:
        """按 EX 敌方编队顺序返回中文舰种，空位为 None。缺少该节点的记录时返回 []。"""
        try:
            _check_map_id(chapter, stage)
        except ValueError:
            return []
        graph = _load_map_data(chapter, stage)
        label = MapData.get_node_label(chapter, stage, node)
        return list(graph.enemies.get(label, ()))

    @staticmethod
    def get_route_nodes(chapter: int, stage: int) -> dict[str, DecisiveRouteNode]:
        """返回保留 A1/A2 等分支 ID 的路线快照，调用者不能修改缓存字典。"""
        return dict(_load_map_data(chapter, stage).nodes)

    @staticmethod
    def get_leftmost_choices(chapter: int, stage: int, source_node: str) -> list[str]:
        """精确 ID 取其真实后继；裸字母沿始终选择首条边的路线定位。"""
        nodes = _load_map_data(chapter, stage).nodes
        source = source_node.strip().upper()
        if source in {'', 'U'}:
            source = '0'
        if source in nodes:
            return list(nodes[source].next_nodes)
        current = '0'
        visited: set[str] = set()
        while current not in visited:
            visited.add(current)
            node = nodes[current]
            if node.label == source:
                return list(node.next_nodes)
            if not node.next_nodes:
                break
            current = node.next_nodes[0]
        return []

    @staticmethod
    def tracking_map(chapter: int, stage: int) -> TrackingMap:
        """将 EX 的真实边投影到可观测字母，保留 #580 的顺序小关生命周期。

        相同字母的路线卡必须具有相同的后继字母，才可合并为一个追踪节点。
        分支索引不是屏幕坐标；EX 未提供的坐标、阵型、类型、迂回均保持未知。
        """
        graph = _load_map_data(chapter, stage)
        raw = {}
        for node_id, node in graph.nodes.items():
            if node_id == '0':
                continue
            successors = list(
                dict.fromkeys(graph.nodes[target].label for target in node.next_nodes)
            )
            if len(successors) > 1 or (node.label in raw and raw[node.label]['next'] != successors):
                raise ValueError(
                    f'决战路线不能无歧义地投影到顺序字母: {chapter}-{stage}: {node_id}'
                )
            ships = list(graph.enemies.get(node.label, ()))
            raw[node.label] = {
                'position': None,
                'next': successors,
                'type': None,
                'detour': None,
                'enemy_formations': [{'formation': None, 'ships': ships}] if ships else None,
            }
        return TrackingMap.from_dict(raw, source=str(_MAP_DATA_ROOT / f'EX-{chapter}-{stage}.yaml'))
