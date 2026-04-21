"""舰船位置追踪与节点判定。

在常规战（多节点地图）的战斗移动阶段，地图上有一个黄色小船图标
沿航线移动，表示舰队当前位置。通过模板匹配追踪小船图标的位置，
再结合预先标注的地图节点坐标数据，使用欧几里得距离判定舰队
当前所在的节点（如 ``"A"``、``"B"`` 等）。

节点判定是战斗决策的基础——不同节点可以配置不同的阵型、夜战策略、
索敌规则等。

数据来源:
  - 地图节点坐标: ``autowsgr/data/map/normal/{chapter}-{map}.yaml``
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from autowsgr.combat.recognizer import CombatRecognizer
from autowsgr.combat.state import CombatPhase
from autowsgr.infra.logger import get_logger
from autowsgr.vision import (
    MatchStrategy,
    PixelChecker,
    PixelRule,
    PixelSignature,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════════════════════════════════════

# 地图数据根目录
_MAP_DATA_ROOT = Path(__file__).resolve().parent.parent / 'data' / 'map' / 'normal'

_log = get_logger('combat.tracker')


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
        path = _MAP_DATA_ROOT / f'{chapter}-{map_id}.yaml'
        if not path.exists():
            _log.warning('[NodeTracker] 地图文件不存在: {}', path)
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
    ) -> MapNodeData | None:
        """从 YAML 文件加载活动地图节点数据。

        数据路径: ``autowsgr/data/map/event/{event_name}/{chapter}-{map_id}.yaml``

        Parameters
        ----------
        event_name:
            活动名称，如 ``"20260212"``。
        chapter:
            活动难度档，如 ``"H"``、``"E"``。
        map_id:
            地图编号，如 ``5``。

        Returns
        -------
        MapNodeData | None
            加载成功返回数据对象；文件不存在返回 ``None``。
        """
        _event_root = Path(__file__).resolve().parent.parent / 'data' / 'map' / 'event'
        path = _event_root / event_name / f'{chapter}-{map_id}.yaml'
        if not path.exists():
            _log.warning('[NodeTracker] 活动地图文件不存在: {}', path)
            return None

        from autowsgr.infra.file_utils import load_yaml

        raw: dict[str, Any] = load_yaml(path)
        _log.debug('[NodeTracker] 加载活动地图数据: {}', path)
        return cls._parse(raw)

    @classmethod
    def _parse(cls, raw: dict[str, Any]) -> MapNodeData:
        """解析 YAML 数据为 MapNodeData。"""
        nodes: dict[str, NodePosition] = {}

        for key, value in raw.items():
            name = str(key)

            if isinstance(value, dict):
                # 格式: {"position": [x, y], "next": ["B", "C"]}
                pos = value.get('position', [0, 0])
                next_nodes = value.get('next', [])
                rel_x = pos[0]
                rel_y = pos[1]
                nodes[name] = NodePosition(
                    name=name,
                    x=rel_x,
                    y=rel_y,
                    next_nodes=list(next_nodes),
                )
            else:
                _log.warning(
                    "[NodeTracker] 忽略无法解析的节点 '{}': {}",
                    name,
                    value,
                )

        _log.debug(
            '[NodeTracker] 加载 {} 个节点: {}',
            len(nodes),
            list(nodes.keys()),
        )
        return cls(nodes)


# ═══════════════════════════════════════════════════════════════════════════════
# 节点追踪器
# ═══════════════════════════════════════════════════════════════════════════════


def _euclidean_distance(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> float:
    """计算两点间欧几里得距离。"""
    return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)


def _point_to_ray_distance(
    px: float,
    py: float,
    ox: float,
    oy: float,
    dx: float,
    dy: float,
) -> float:
    """计算点到射线的最小距离。

    射线由起点 ``(ox, oy)`` 和方向向量 ``(dx, dy)`` 定义。
    当点落在射线反向半平面时，最小距离退化为点到射线起点的距离。
    """
    # 向量 OP
    vx = px - ox
    vy = py - oy

    # 点在射线后方：最短距离为到起点距离
    dot = vx * dx + vy * dy
    if dot <= 0:
        return math.hypot(vx, vy)

    # 射线方向单位向量的法向分量长度 = 到射线最短距离
    # |v x d| / |d|, 其中二维叉积标量为 v_x * d_y - v_y * d_x
    cross = abs(vx * dy - vy * dx)
    norm_d = math.hypot(dx, dy)
    if norm_d == 0:
        return math.hypot(vx, vy)
    return cross / norm_d


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
        self._current_node: str = '0'

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
        self._current_node = '0'

    def _recheck_pixel(self, center: tuple[float, float], screen) -> bool:
        """验证中心及其左右两侧的像素特征。
        Returns
        -------
        bool
            三个位置都满足像素特征时返回 ``True``。
        """
        cx, cy = center

        # 定义三个检查位置的像素规则
        rules = [
            PixelRule.of(cx, cy, (239, 219, 106), tolerance=40.0),  # 中心
            PixelRule.of(cx - 0.03, cy, (231, 222, 101), tolerance=40.0),  # 左侧
            PixelRule.of(cx + 0.03, cy, (231, 222, 101), tolerance=40.0),  # 右侧
        ]

        sig = PixelSignature(
            name='小船像素验证',
            strategy=MatchStrategy.ALL,
            rules=rules,
        )
        return PixelChecker.check_signature(screen, sig).matched

    @staticmethod
    def _find_yellow_cluster(screen: np.ndarray) -> tuple[float, float] | None:
        """在截图中查找最大的黄色像素簇，返回其质心的相对坐标。
        Returns
        -------
        tuple[float, float] | None
            最大黄色簇质心 ``(rel_x, rel_y)``；未找到返回 ``None``。
        """
        r, g, b = screen[:, :, 0], screen[:, :, 1], screen[:, :, 2]
        mask = (
            (r.astype(np.int16) > 200)
            & (g.astype(np.int16) > 180)
            & (b.astype(np.int16) > 50)
            & (b.astype(np.int16) < 150)
        ).astype(np.uint8)

        num_labels, _labels, stats, centroids = cv2.connectedComponentsWithStats(
            mask,
            connectivity=8,
        )
        # label 0 是背景，跳过
        if num_labels <= 1:
            return None

        # 按面积降序排列（排除背景 label 0）
        _MIN_AREA = 200
        best_label = -1
        best_area = 0
        for label_id in range(1, num_labels):
            area = int(stats[label_id, cv2.CC_STAT_AREA])
            if area >= _MIN_AREA and area > best_area:
                best_area = area
                best_label = label_id

        if best_label < 0:
            return None

        h, w = screen.shape[:2]
        cx_abs, cy_abs = centroids[best_label]
        return (cx_abs / w, cy_abs / h)

    def is_spot_page(self, screen):
        return (
            CombatRecognizer.identify_current(screen, [CombatPhase.SPOT_ENEMY_SUCCESS]) is not None
        )

    def update_ship_position(self, screen) -> tuple[float, float] | None:
        """在战斗移动界面检测黄色小船图标的位置。
        Returns
        -------
        tuple[float, float] | None
            检测到的相对坐标 ``(x, y)``；未检测到或像素验证失败返回 ``None``。
        """
        # 检查是否为索敌页面，如果是索敌页面，则返回None
        if self.is_spot_page(screen):
            _log.debug(
                '[NodeTracker] 检测到是索敌页面，不更新位置',
            )
            return None

        center = self._find_yellow_cluster(screen)
        if center is None:
            return None
        # save_image(screen, 'debug_node_tracker_cluster.png')
        if self._recheck_pixel(center, screen):
            self._ship_position = center
            _log.debug(
                '[NodeTracker] 小船位置更新: ({:.3f}, {:.3f}) [黄色簇检测+像素验证]',
                center[0],
                center[1],
            )
            return center

        _log.debug(
            '[NodeTracker] 黄色簇检测到但像素验证失败: ({:.3f}, {:.3f})',
            center[0],
            center[1],
        )
        return None

    def update_node(self) -> str:
        """根据当前舰船位置判定所在节点。

        当舰船位置发生变化（与上次不同）时，遍历候选节点（当前节点 + next_nodes），
        优先按"到当前速度方向射线的最小距离"选择节点；
        若射线距离相同，再按欧几里得距离打破平局。

        地图必须包含路由信息 (next_nodes)，否则无法判定。

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

        prev_position = self._last_ship_position
        self._last_ship_position = self._ship_position
        sx, sy = self._ship_position

        # 速度方向（上一帧 -> 当前帧）；首帧或零位移时退化为欧氏距离模式
        has_ray = False
        vx = 0.0
        vy = 0.0
        if prev_position is not None:
            vx = sx - prev_position[0]
            vy = sy - prev_position[1]
            has_ray = (vx * vx + vy * vy) > 1e-12

        if not has_ray:
            _log.debug(
                '[NodeTracker] has_ray=False，保持当前节点: {}，位置: ({:.3f}, {:.3f})',
                self._current_node,
                sx,
                sy,
            )
            return self._current_node

        current_data = self._map_data.get(self._current_node)

        # 要求地图必须包含路由信息
        if current_data is None or not current_data.next_nodes:
            _log.warning(
                "[NodeTracker] 节点 '{}' 缺少路由信息 (next_nodes)，无法判定下一节点",
                self._current_node,
            )
            return self._current_node

        _log.debug(
            "[NodeTracker] 当前节点 '{}', 下一节点候选列表: {}",
            self._current_node,
            current_data.next_nodes,
        )
        # 将当前节点也作为候选，避免在移动途中被强制前推
        candidate_names = list(dict.fromkeys([self._current_node, *current_data.next_nodes]))

        ray_hit_threshold = 0.01
        best_node = self._current_node
        best_ray_distance = float('inf')
        best_euclidean_distance = float('inf')
        candidate_metrics: list[str] = []
        candidate_distances: list[tuple[str, float, float]] = []

        for name in candidate_names:
            node = self._map_data.get(name)
            if node is None:
                continue

            euclidean_dist = _euclidean_distance(sx, sy, node.x, node.y)
            if has_ray:
                ray_dist = _point_to_ray_distance(node.x, node.y, sx, sy, vx, vy)
            else:
                # 无法构建射线时，退化为纯欧氏距离比较
                ray_dist = euclidean_dist

            candidate_metrics.append(
                f'{name}(ray={ray_dist:.4f}, euclid={euclidean_dist:.4f}, pos=({node.x:.3f},{node.y:.3f}))',
            )
            candidate_distances.append((name, ray_dist, euclidean_dist))

        ray_hits = [item for item in candidate_distances if item[1] < ray_hit_threshold]
        if ray_hits:
            best_node, best_ray_distance, best_euclidean_distance = min(
                ray_hits,
                key=lambda item: (item[2], item[1]),
            )
        elif candidate_distances:
            _log.warning(
                '[NodeTracker] 射线距离未命中阈值 (<{:.4f})，回退到最小射线距离选择',
                ray_hit_threshold,
            )
            best_node, best_ray_distance, best_euclidean_distance = min(
                candidate_distances,
                key=lambda item: (item[1], item[2]),
            )

        _log.debug(
            '[NodeTracker] 候选点评估: {} | 船位=({:.3f},{:.3f}) | 速度=({:.4f},{:.4f}) | has_ray={}',
            '; '.join(candidate_metrics),
            sx,
            sy,
            vx,
            vy,
            has_ray,
        )

        if best_node != self._current_node:
            _log.debug(
                '[NodeTracker] 节点更新: {} → {} (射线距 {:.4f}, 欧氏距 {:.4f}), 位置: ({:.3f}, {:.3f})',
                self._current_node,
                best_node,
                best_ray_distance,
                best_euclidean_distance,
                sx,
                sy,
            )
            self._current_node = best_node

        return self._current_node

    def track(self, screen) -> str:
        """一站式追踪：更新位置 + 判定节点。"""
        self.update_ship_position(screen)
        return self.update_node()
