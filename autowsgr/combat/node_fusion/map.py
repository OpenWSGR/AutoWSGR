"""地图元数据校验，以及通往下一次可观测遭遇的具体路线。

分叉采用均匀先验，不表示游戏实际随机。
只有明确标记为 NULL、REWARD、LOSS 的节点可在没有遭遇观测时经过。
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from autowsgr_native.vessel_type import VesselType

from autowsgr.combat.node_fusion.coordinates import _resolve_event_map_path, read_coordinate_map


_MAP_ROOT = Path(__file__).resolve().parents[2] / 'data' / 'map' / 'normal'
_EVENT_MAP_ROOT = _MAP_ROOT.parent / 'event'
_SILENT_TYPES = frozenset({'NULL', 'REWARD', 'LOSS'})
_NODE_TYPES = _SILENT_TYPES | {'FIGHT', 'BOSS', 'LITTLE_BOSS', 'AIR_ATTACK', 'SPECIAL_POINT'}
# 从实际安装的 native 枚举取得中文舰类，空槽哨兵不属于敌舰类别。
SHIP_TYPES = frozenset(
    value.as_chinese()
    for name in dir(VesselType)
    if isinstance(value := getattr(VesselType, name), VesselType) and value.as_english() != 'NO'
)


@dataclass(frozen=True, slots=True)
class EnemyVariant:
    """一条阵型与有序舰队组成的联合敌情记录。"""

    formation: int
    ships: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TrackingNode:
    """包含归一化坐标及合法敌情变体的地图节点。"""

    name: str
    position: tuple[float, float]
    next_nodes: tuple[str, ...] | None
    node_type: str | None
    detour: bool | None
    enemy_formations: tuple[EnemyVariant, ...] | None

    @property
    def silent(self) -> bool:
        """节点类型是否明确表示没有战斗。"""
        return self.node_type in _SILENT_TYPES


@dataclass(frozen=True, slots=True)
class Route:
    """包含起终点的具体路线，先验为各分叉概率的乘积。"""

    nodes: tuple[str, ...]
    probability: float


def _parse_variant(raw: Any, node: str) -> EnemyVariant:
    if not isinstance(raw, dict) or set(raw) != {'formation', 'ships'}:
        raise ValueError(f'Invalid enemy variant at node {node}')
    formation, ships = raw['formation'], raw['ships']
    if type(formation) is not int or not 1 <= formation <= 5:
        raise ValueError(f'Invalid enemy formation at node {node}: {formation!r}')
    if not isinstance(ships, list) or not 1 <= len(ships) <= 6:
        raise ValueError(f'Enemy fleet at node {node} must contain 1..6 ships')
    if any(not isinstance(ship, str) or ship not in SHIP_TYPES for ship in ships):
        raise ValueError(
            f'Installed native does not support Chinese enemy ship type at node {node}: {ships!r}'
        )
    return EnemyVariant(formation, tuple(ships))


def _parse_node(name: str, raw: Any) -> TrackingNode:
    if not isinstance(raw, dict) or 'position' not in raw:
        raise ValueError(f'Missing position at node {name}')
    allowed = {'type', 'detour', 'position', 'next', 'enemy_formations', 'night'}
    if raw.keys() - allowed:
        raise ValueError(f'Unknown tracking fields at node {name}')
    node_type = raw.get('type')
    if node_type is not None and (not isinstance(node_type, str) or node_type not in _NODE_TYPES):
        raise ValueError(f'Unknown node type at {name}: {node_type!r}')
    detour = raw.get('detour')
    if (detour is not None and type(detour) is not bool) or (
        'night' in raw and type(raw['night']) is not bool
    ):
        raise ValueError(f'Invalid boolean metadata at node {name}')
    position = raw['position']
    if not isinstance(position, list) or len(position) != 2:
        raise ValueError(f'Invalid position at node {name}')
    if any(
        type(x) not in (int, float) or not 0 <= x <= 1 or not math.isfinite(x) for x in position
    ):
        raise ValueError(f'Position at node {name} must be finite and normalized')
    # 缺失路由与明确终点不同，不用空列表填补未知信息。
    next_nodes = raw.get('next')
    if next_nodes is not None:
        if not isinstance(next_nodes, list) or any(
            not isinstance(n, str) or not n for n in next_nodes
        ):
            raise ValueError(f'Invalid route list at node {name}')
        if len(set(next_nodes)) != len(next_nodes):
            raise ValueError(f'Duplicate outgoing route at node {name}')
    variants = raw.get('enemy_formations')
    if variants is not None and not isinstance(variants, list):
        raise ValueError(f'Invalid enemy variants at node {name}')
    parsed = (
        tuple(dict.fromkeys(_parse_variant(variant, name) for variant in variants))
        if variants is not None
        else None
    )
    if (
        parsed is not None
        and node_type is not None
        and ((node_type in _SILENT_TYPES) == bool(parsed))
    ):
        raise ValueError(f'Enemy variants disagree with node type at {name}')
    return TrackingNode(
        name,
        (float(position[0]), float(position[1])),
        tuple(next_nodes) if next_nodes is not None else None,
        node_type,
        detour,
        parsed,
    )


@dataclass(frozen=True)
class TrackingMap:
    """通过加载或解析校验后供推断使用的地图快照。"""

    nodes: dict[str, TrackingNode]
    source: str | None = field(default=None, compare=False)

    @property
    def capabilities(self) -> dict[str, bool]:
        """按实际资料声明能力；局部缺失不会改写成否定信息。"""
        encounters = [node for name, node in self.nodes.items() if name != '0' and not node.silent]
        topology = all(node.next_nodes is not None for node in self.nodes.values())
        node_types = all(node.node_type is not None for node in encounters)
        positions = any(name != '0' for name in self.nodes)
        return {
            'distance': positions,
            'ray': positions,
            'topology': topology,
            'node_types': node_types,
            'encounter_history': topology and node_types and '0' in self.nodes,
            'enemy': any(bool(node.enemy_formations) for node in encounters),
            'detour': any(node.detour is not None for node in encounters),
        }

    @property
    def degradation_reasons(self) -> tuple[str, ...]:
        """列出缺失信息及其影响，供出征时一次性警告。"""
        reasons = []
        if '0' not in self.nodes:
            reasons.append('缺少起始点：仅使用实际船位初始化，不启用遭遇次数推进')
        missing_routes = [name for name, node in self.nodes.items() if node.next_nodes is None]
        if missing_routes:
            reasons.append(f'缺少路由({", ".join(missing_routes)})：停用拓扑硬约束及遭遇次数推进')
        missing_types = [
            name for name, node in self.nodes.items() if name != '0' and node.node_type is None
        ]
        if missing_types:
            reasons.append(
                f'缺少节点类型({", ".join(missing_types)})：停用空白点跨越及遭遇次数推进'
            )
        encounters = [node for name, node in self.nodes.items() if name != '0' and not node.silent]
        missing_enemies = [node.name for node in encounters if not node.enemy_formations]
        if missing_enemies:
            reasons.append(f'缺少敌情({", ".join(missing_enemies)})：这些节点不进行阵容阵型匹配')
        missing_detours = [node.name for node in encounters if node.detour is None]
        if missing_detours:
            reasons.append(
                f'缺少迂回属性({", ".join(missing_detours)})：这些节点不进行迂回按钮匹配'
            )
        return tuple(reasons)

    def to_dict(self) -> dict[str, Any]:
        """导出可重建的元数据快照，保留未知值，不包含本机路径。"""
        return {
            name: {
                'position': list(node.position),
                'next': list(node.next_nodes) if node.next_nodes is not None else None,
                'type': node.node_type,
                'detour': node.detour,
                'enemy_formations': (
                    [
                        {'formation': item.formation, 'ships': list(item.ships)}
                        for item in node.enemy_formations
                    ]
                    if node.enemy_formations is not None
                    else None
                ),
            }
            for name, node in self.nodes.items()
        }

    @property
    def fingerprint(self) -> str:
        """规范化地图元数据的 SHA-256，不受 JSON 空白格式影响。"""
        payload = json.dumps(
            {'nodes': {name: asdict(node) for name, node in self.nodes.items()}},
            ensure_ascii=False,
            sort_keys=True,
            separators=(',', ':'),
        )
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()

    @classmethod
    def load(cls, chapter: int | str, map_id: int | str) -> TrackingMap | None:
        """加载常规地图；缺失文件返回 None，元数据无效时抛出 ValueError。"""
        if any(re.fullmatch(r'[1-9][0-9]*', str(part)) is None for part in (chapter, map_id)):
            raise ValueError('Tracking map identifiers must be positive decimal numbers')
        path = _MAP_ROOT / f'{chapter}-{map_id}.json'
        try:
            raw = json.loads(path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            return None
        return cls.from_dict(raw, source=str(path.resolve()))

    @classmethod
    def load_event(
        cls,
        event_name: str,
        chapter: int | str,
        map_id: int | str,
        entrance: str | None = None,
    ) -> TrackingMap | None:
        """优先加载活动 Tracking 元数据，缺失时读取对应入口的旧 YAML。

        保留资料缺失，不根据坐标或文件格式猜测节点类型。
        """
        chapter = str(chapter).upper()
        if (
            not isinstance(event_name, str)
            or not event_name
            or event_name in {'.', '..'}
            or any(char in event_name for char in '/\\:')
            or chapter not in {'E', 'H'}
            or re.fullmatch(r'[1-9][0-9]*', str(map_id)) is None
            or entrance not in (None, 'a', 'b')
        ):
            raise ValueError('Invalid event tracking map identifiers')
        suffix = f'-{entrance}' if entrance is not None else ''
        path = _EVENT_MAP_ROOT / event_name / f'{chapter}-{map_id}{suffix}.json'
        try:
            raw = json.loads(path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            coordinate_path = _resolve_event_map_path(
                _EVENT_MAP_ROOT, event_name, chapter, map_id, entrance
            )
            return cls._load_coordinates(coordinate_path)
        return cls.from_dict(raw, source=str(path.resolve()))

    @classmethod
    def _load_coordinates(cls, path: Path | None) -> TrackingMap | None:
        if path is None:
            return None
        try:
            raw = read_coordinate_map(path)
        except FileNotFoundError:
            return None
        return cls.from_dict(raw, source=str(path.resolve()))

    @classmethod
    def from_dict(cls, raw: Any, *, source: str | None = None) -> TrackingMap:
        """严格解析数据，保留舰船顺序，只合并完全相同的敌情变体。"""
        if not isinstance(raw, dict) or not raw:
            raise ValueError('Tracking map must be a nonempty object')
        if any(not isinstance(name, str) or not name for name in raw):
            raise ValueError('Tracking node names must be nonempty strings')
        nodes = {name: _parse_node(name, value) for name, value in raw.items()}
        if '0' in nodes and nodes['0'].node_type not in (None, 'NULL'):
            raise ValueError('Tracking map entry node 0 cannot be an encounter')
        for node in nodes.values():
            for target in node.next_nodes or ():
                if target not in nodes or target == '0':
                    raise ValueError(f'Invalid route {node.name} -> {target}')
        result = cls(nodes, source=source)
        result._validate_silent_cycles()
        return result

    def _validate_silent_cycles(self) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(name: str) -> None:
            if name in visiting:
                raise ValueError(f'Silent route cycle contains node {name}')
            if name in visited:
                return
            visiting.add(name)
            for target in self.nodes[name].next_nodes or ():
                if self.nodes[target].silent:
                    visit(target)
            visiting.remove(name)
            visited.add(name)

        for node in self.nodes.values():
            if node.silent:
                visit(node.name)

    def paths_from(self, node: str) -> tuple[Route, ...]:
        """枚举下一遭遇或非战斗终点；起点本身是终点时没有后续路线。

        每次分叉均匀分配权重。不同路径合流时仍保留各自的分叉乘积，
        不按路径条数给终点额外票数。展开到战斗点即停止，因此支持战斗环路。
        """
        if not self.capabilities['encounter_history']:
            # 资料不足时由几何路径处理，不能把未知节点当作固定遭遇或空白点。
            return ()
        routes: list[Route] = []

        def walk(path: tuple[str, ...], probability: float) -> None:
            current = self.nodes[path[-1]]
            if len(path) > 1 and (not current.silent or not current.next_nodes):
                routes.append(Route(path, probability))
                return
            if current.next_nodes:
                branch_probability = probability / len(current.next_nodes)
                for target in current.next_nodes:
                    walk((*path, target), branch_probability)

        walk((node,), 1.0)
        return tuple(routes)
