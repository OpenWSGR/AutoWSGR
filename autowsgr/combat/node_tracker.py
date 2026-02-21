"""舰船位置追踪与节点判定。

在常规战（多节点地图）的战斗移动阶段，地图上有一个黄色小船图标
沿航线移动，表示舰队当前位置。通过模板匹配追踪小船图标的位置，
再结合预先标注的地图节点坐标数据，使用欧几里得距离判定舰队
当前所在的节点（如 ``"A"``、``"B"`` 等）。

节点判定是战斗决策的基础——不同节点可以配置不同的阵型、夜战策略、
索敌规则等。

数据来源:
  - 地图节点坐标: ``autowsgr/data/map/normal/{chapter}-{map}.yaml``
  - 小船图标模板: ``autowsgr/data/images/combat/ship_icon_{1,2}.png``
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from autowsgr.combat.image_resources import get_template
from autowsgr.vision import ImageChecker, ImageMatchDetail, ImageTemplate

# ═══════════════════════════════════════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════════════════════════════════════

# 地图节点坐标 YAML 文件的基准分辨率
_SOURCE_WIDTH = 960
_SOURCE_HEIGHT = 540

# 地图数据根目录
_MAP_DATA_ROOT = Path(__file__).resolve().parent.parent / "data" / "map" / "normal"


# ═══════════════════════════════════════════════════════════════════════════════
# 地图节点数据
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class NodePosition:
    """一个地图节点的位置信息。

    Attributes
    ----------
    name:
        节点标识符（如 ``"A"``、``"B"``）。
    x:
        节点 x 坐标（相对值 0.0–1.0）。
    y:
        节点 y 坐标（相对值 0.0–1.0）。
    next_nodes:
        从该节点可以到达的下一个节点名列表。
        仅在新格式 YAML 中提供；旧格式为空列表。
    """

    name: str
    x: float
    y: float
    next_nodes: list[str] = field(default_factory=list)


class MapNodeData:
    """单个地图的节点位置数据。

    从 YAML 文件加载并转换为相对坐标。

    **标准格式** (含路由信息)::

        "0":
          position: [200, 350]
          next: ["A"]
        A:
          position: [283, 282]
          next: ["B", "C"]
    """

    def __init__(self, nodes: dict[str, NodePosition]) -> None:
        self._nodes = nodes

    @property
    def node_names(self) -> list[str]:
        """所有节点名（排除起始点 "0"）。"""
        return [n for n in self._nodes if n != "0"]

    def get(self, name: str) -> NodePosition | None:
        """按名称获取节点。"""
        return self._nodes.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self._nodes

    def __len__(self) -> int:
        return len(self._nodes)

    @classmethod
    def load(cls, chapter: int | str, map_id: int | str) -> MapNodeData | None:
        """从 YAML 文件加载地图节点数据。

        Parameters
        ----------
        chapter:
            章节号。
        map_id:
            地图号。

        Returns
        -------
        MapNodeData | None
            加载成功返回数据对象；文件不存在返回 ``None``。
        """
        path = _MAP_DATA_ROOT / f"{chapter}-{map_id}.yaml"
        if not path.exists():
            logger.warning("[NodeTracker] 地图文件不存在: {}", path)
            return None

        from autowsgr.infra.file_utils import load_yaml

        raw: dict[str, Any] = load_yaml(path)
        return cls._parse(raw)

    @classmethod
    def _parse(cls, raw: dict[str, Any]) -> MapNodeData:
        """解析 YAML 数据为 MapNodeData。"""
        nodes: dict[str, NodePosition] = {}

        for key, value in raw.items():
            name = str(key)

            if isinstance(value, dict):
                # 新格式: {"position": [x, y], "next": ["B", "C"]}
                pos = value.get("position", [0, 0])
                next_nodes = value.get("next", [])
                rel_x = pos[0] / _SOURCE_WIDTH
                rel_y = pos[1] / _SOURCE_HEIGHT
                nodes[name] = NodePosition(
                    name=name, x=rel_x, y=rel_y,
                    next_nodes=list(next_nodes),
                )
            elif isinstance(value, (list, tuple)):
                # 旧格式: [x, y] 或 !!python/tuple
                rel_x = value[0] / _SOURCE_WIDTH
                rel_y = value[1] / _SOURCE_HEIGHT
                nodes[name] = NodePosition(name=name, x=rel_x, y=rel_y)
            else:
                logger.warning(
                    "[NodeTracker] 忽略无法解析的节点 '{}': {}", name, value,
                )

        logger.debug(
            "[NodeTracker] 加载 {} 个节点: {}",
            len(nodes), list(nodes.keys()),
        )
        return cls(nodes)


# ═══════════════════════════════════════════════════════════════════════════════
# 节点追踪器
# ═══════════════════════════════════════════════════════════════════════════════


def _euclidean_distance(
    x1: float, y1: float, x2: float, y2: float,
) -> float:
    """计算两点间欧几里得距离。"""
    return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)


class NodeTracker:
    """舰船位置追踪与节点判定器。

    通过模板匹配追踪地图上的黄色小船图标位置，
    然后使用欧几里得距离判定当前所在节点。

    Parameters
    ----------
    map_data:
        地图节点位置数据。
    """

    def __init__(self, map_data: MapNodeData) -> None:
        self._map_data = map_data
        self._ship_position: tuple[float, float] | None = None
        self._last_ship_position: tuple[float, float] | None = None
        self._current_node: str = "0"

    @property
    def current_node(self) -> str:
        """当前节点标识符。"""
        return self._current_node

    @property
    def ship_position(self) -> tuple[float, float] | None:
        """当前舰船位置（相对坐标），未检测到时为 ``None``。"""
        return self._ship_position

    def reset(self) -> None:
        """重置追踪状态。"""
        self._ship_position = None
        self._last_ship_position = None
        self._current_node = "0"

    def update_ship_position(self, screen) -> tuple[float, float] | None:
        """在战斗移动界面通过模板匹配更新黄色小船的位置。

        尝试匹配 ``ship_icon_1`` 和 ``ship_icon_2`` 两个模板图像
        （对应旧代码 ``fight_image[7]`` 和 ``fight_image[8]``）。

        Parameters
        ----------
        screen:
            当前截图 (H×W×3, RGB)。

        Returns
        -------
        tuple[float, float] | None
            检测到的相对坐标 ``(x, y)``；未检测到返回 ``None``。
        """
        templates = get_template("ship_icon")
        detail: ImageMatchDetail | None = ImageChecker.find_any(
            screen, templates, confidence=0.7,
        )
        if detail is not None:
            self._ship_position = detail.center
            logger.debug(
                "[NodeTracker] 舰船位置: ({:.4f}, {:.4f})",
                detail.center[0], detail.center[1],
            )
            return detail.center
        return None

    def update_node(self) -> str:
        """根据当前舰船位置判定所在节点。

        当舰船位置发生变化（与上次不同）时，遍历所有候选节点，
        使用欧几里得距离选择最近的节点作为当前节点。

        如果地图数据包含路由信息（新格式 YAML），则仅在当前节点的
        ``next_nodes`` 中搜索；否则搜索全部节点。

        Returns
        -------
        str
            更新后的当前节点标识符。
        """
        if self._ship_position is None:
            return self._current_node

        # 位置未变化时不更新
        if self._ship_position == self._last_ship_position:
            return self._current_node

        self._last_ship_position = self._ship_position
        sx, sy = self._ship_position

        current_data = self._map_data.get(self._current_node)

        # 确定候选节点列表
        if current_data is not None and current_data.next_nodes:
            # 新格式：仅在 next_nodes 中搜索
            candidate_names = current_data.next_nodes
        else:
            # 旧格式：搜索全部节点（排除 "0"）
            candidate_names = self._map_data.node_names

        best_node = self._current_node
        best_distance = float("inf")

        for name in candidate_names:
            node = self._map_data.get(name)
            if node is None:
                continue
            dist = _euclidean_distance(sx, sy, node.x, node.y)
            if dist < best_distance:
                best_distance = dist
                best_node = name

        if best_node != self._current_node:
            logger.info(
                "[NodeTracker] 节点更新: {} → {} (距离 {:.4f})",
                self._current_node, best_node, best_distance,
            )
            self._current_node = best_node

        return self._current_node

    def track(self, screen) -> str:
        """一站式追踪：更新位置 + 判定节点。

        在每轮匹配前的回调中调用此方法即可完成完整追踪。

        Parameters
        ----------
        screen:
            当前截图 (H×W×3, RGB)。

        Returns
        -------
        str
            当前节点标识符。
        """
        self.update_ship_position(screen)
        return self.update_node()
