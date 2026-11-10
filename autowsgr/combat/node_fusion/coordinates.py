"""读取地图坐标和路由，供地图展示及数据核对使用；不包含节点追踪算法。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from autowsgr.infra.logger import get_logger


# 地图数据根目录
_MAP_DATA_ROOT = Path(__file__).resolve().parents[2] / 'data' / 'map' / 'normal'
_EVENT_MAP_DATA_ROOT = _MAP_DATA_ROOT.parent / 'event'

# 活动入口标识 (内部 a/b) ↔ 地图文件名希腊字母 (α/β)；仅活动地图有 α/β 入口概念
ENTRANCE_TO_GREEK = {'a': 'α', 'b': 'β'}

# 单入口活动地图的入口节点 (α/β) 映射为起始点 '0'。
# 部分旧地图同时保存两个入口，不能把它们合并成一个坐标。
_START_NODE_REMAP = {'α': '0', 'β': '0'}

_log = get_logger('combat.tracker')


def read_coordinate_map(path: Path) -> dict[str, Any]:
    """读取旧地图并保留缺失字段，像素数组按旧版 960 x 540 坐标约定归一化。

    不经过展示用的 MapNodeData，避免把缺失路由补成终点，或把缺失坐标补成零点。
    """
    from autowsgr.infra.file_utils import load_yaml

    raw = load_yaml(path)
    if not isinstance(raw, dict) or not raw:
        raise ValueError('Coordinate map must be a nonempty object')
    entrances = {str(key) for key in raw} & _START_NODE_REMAP.keys()
    remap = _START_NODE_REMAP if len(entrances) < 2 else {}
    nodes: dict[str, Any] = {}
    for key, value in raw.items():
        if isinstance(key, bool) or not isinstance(key, (str, int)):
            raise TypeError(f'Invalid coordinate node name: {key!r}')
        name = remap.get(str(key), str(key))
        if not name or name in nodes:
            raise ValueError(f'Duplicate or empty coordinate node name: {name!r}')
        if isinstance(value, list):
            if len(value) != 2 or any(
                type(item) not in (int, float) or not 0 <= item <= limit
                for item, limit in zip(value, (960, 540), strict=True)
            ):
                raise ValueError(f'Invalid pixel position at node {name}')
            nodes[name] = {'position': [value[0] / 960, value[1] / 540]}
        elif isinstance(value, dict):
            node = dict(value)
            targets = node.get('next')
            if isinstance(targets, list):
                node['next'] = [remap.get(str(target), str(target)) for target in targets]
            nodes[name] = node
        else:
            raise TypeError(f'Invalid coordinate metadata at node {name}')
        if len(entrances) > 1 and name in entrances:
            # α/β 是格式明确规定的入口身份，不是由缺失类型推测出的空白点。
            if nodes[name].get('type') not in (None, 'NULL'):
                raise ValueError(f'Coordinate map entry node {name} cannot be an encounter')
            nodes[name]['type'] = 'NULL'
    return nodes


# ═══════════════════════════════════════════════════════════════════════════════
# 地图节点数据
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class NodePosition:
    """一个地图节点的位置信息。

    属性
    ----------
    name:
        节点标识符（如 ``"A"``、``"B"``）。
    x:
        节点 x 坐标（相对值 0.0-1.0）。
    y:
        节点 y 坐标（相对值 0.0-1.0）。
    next_nodes:
        从该节点可以到达的下一个节点名列表。
    """

    name: str
    x: float
    y: float
    next_nodes: list[str] = field(default_factory=list)


def _resolve_event_map_path(
    event_root: Path,
    event_name: str,
    chapter: int | str,
    map_id: int | str,
    entrance: str | None,
) -> Path | None:
    """解析活动地图文件路径。

    - ``entrance`` 为 ``None``: 旧命名 ``{chapter}-{map_id}.yaml`` (如 ``E-1.yaml``)
    - ``entrance`` 为 ``'a'``/``'b'``: 新活动中文命名
      ``{中文前缀}{H?}-Ex-{map_id}-{α|β}.yaml``。H 章 (困难) 文件名含 ``H-Ex``，
      E 章 (简单) 不含；用 glob 通配中文前缀，无需硬编码活动名。

    返回值
    -------
    Path | None
        唯一匹配返回路径；零个或多个匹配 (歧义) 返回 ``None``。
    """
    event_dir = event_root / event_name
    if entrance is None:
        return event_dir / f'{chapter}-{map_id}.yaml'

    greek = ENTRANCE_TO_GREEK.get(entrance)
    if greek is None:
        _log.warning('[地图坐标] 未知入口标识 {!r}, 应为 a/b', entrance)
        return None

    chap = str(chapter).upper()
    hard_prefix = 'H' if chap == 'H' else ''
    pattern = f'*{hard_prefix}-Ex-{map_id}-{greek}.yaml'
    matches = sorted(event_dir.glob(pattern))
    # E 章 (简单) 排除误匹配的困难文件 (其文件名含 H-Ex)
    if chap != 'H':
        matches = [p for p in matches if 'H-Ex' not in p.stem]
    if not matches:
        return None
    if len(matches) > 1:
        _log.warning(
            '[地图坐标] 活动地图文件匹配歧义 ({} 个): {}',
            len(matches),
            matches,
        )
        return None
    return matches[0]


class MapNodeData:
    """单个地图的节点位置数据。

    从 YAML 文件加载节点坐标和路由信息。
    节点坐标必须为归一化形式（0.0 ~ 1.0）。

    地图格式示例::

        "0":
          position: [0.208, 0.648]
          next: ["A"]
        A:
          position: [0.295, 0.522]
          next: ["B", "C"]
    """

    def __init__(self, nodes: dict[str, NodePosition]) -> None:
        self._nodes = nodes

    @property
    def node_names(self) -> list[str]:
        """所有节点名（排除起始点 "0"）。"""
        return [n for n in self._nodes if n != '0']

    def get(self, name: str) -> NodePosition | None:
        """按名称获取节点。"""
        return self._nodes.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self._nodes

    def __len__(self) -> int:
        return len(self._nodes)

    @classmethod
    def load(cls, chapter: int | str, map_id: int | str) -> MapNodeData | None:
        """从 YAML 文件加载常规地图节点数据。

        参数
        ----------
        chapter:
            章节号。
        map_id:
            地图号。

        返回值
        -------
        MapNodeData | None
            加载成功返回数据对象；文件不存在返回 ``None``。
        """
        path = _MAP_DATA_ROOT / f'{chapter}-{map_id}.yaml'
        if not path.exists():
            _log.warning('[地图坐标] 地图文件不存在: {}', path)
            return None

        from autowsgr.infra.file_utils import load_yaml

        raw: dict[str, Any] = load_yaml(path)
        return cls._parse(raw)

    @classmethod
    def load_event(
        cls,
        event_name: str,
        chapter: int | str,
        map_id: int | str,
        entrance: str | None = None,
    ) -> MapNodeData | None:
        """从 YAML 文件加载活动地图节点数据。

        支持两种命名 (见 :func:`_resolve_event_map_path`):

        - 旧活动 (``entrance`` 为 ``None``): ``{chapter}-{map_id}.yaml``
        - 新活动 (``entrance`` 为 ``'a'``/``'b'``): 中文命名
          ``{中文前缀}{H?}-Ex-{map_id}-{α|β}.yaml``

        参数
        ----------
        event_name:
            活动名称，如 ``"20260730"``。
        chapter:
            活动难度档，如 ``"H"``、``"E"``。
        map_id:
            地图编号，如 ``5``。
        entrance:
            活动入口 ``'a'`` (α) / ``'b'`` (β) / ``None``。新活动必填。

        返回值
        -------
        MapNodeData | None
            加载成功返回数据对象；文件不存在或匹配歧义返回 ``None``。
        """
        _event_root = _EVENT_MAP_DATA_ROOT
        path = _resolve_event_map_path(_event_root, event_name, chapter, map_id, entrance)
        if path is None or not path.exists():
            _log.warning(
                '[地图坐标] 活动地图文件不存在: {}/{}-{} (entrance={})',
                event_name,
                chapter,
                map_id,
                entrance,
            )
            return None

        from autowsgr.infra.file_utils import load_yaml

        raw: dict[str, Any] = load_yaml(path)
        _log.debug('[地图坐标] 加载活动地图数据: {}', path)
        return cls._parse(raw)

    @classmethod
    def _parse(cls, raw: dict[str, Any]) -> MapNodeData:
        """解析 YAML 数据为 MapNodeData。"""
        nodes: dict[str, NodePosition] = {}

        for key, value in raw.items():
            # 活动入口节点 α/β 映射为起始点 '0' (见 _START_NODE_REMAP)；
            # α/β 入口按规范拆分为单独文件，同文件多入口归并后拒绝。
            name = _START_NODE_REMAP.get(str(key), str(key))
            if name in nodes:
                raise ValueError(
                    f'Duplicate map node after entrance remap: {name!r}'
                    '（α/β 入口必须按入口拆分为单独文件）'
                )

            if isinstance(value, dict):
                # 格式: {"position": [x, y], "next": ["B", "C"]}
                pos = value.get('position', [0, 0])
                if not isinstance(pos, list) or len(pos) != 2:
                    _log.warning("[地图坐标] 忽略坐标非法的节点 '{}': {}", name, pos)
                    continue
                raw_next = value.get('next') or []
                if not isinstance(raw_next, list):
                    _log.warning("[地图坐标] 忽略非法 next 列表 '{}': {}", name, raw_next)
                    raw_next = []
                nodes[name] = NodePosition(
                    name=name,
                    x=pos[0],
                    y=pos[1],
                    next_nodes=[_START_NODE_REMAP.get(str(n), str(n)) for n in raw_next],
                )
            else:
                _log.warning(
                    "[地图坐标] 忽略无法解析的节点 '{}': {}",
                    name,
                    value,
                )

        _log.debug(
            '[地图坐标] 加载 {} 个节点: {}',
            len(nodes),
            list(nodes.keys()),
        )
        return cls(nodes)
