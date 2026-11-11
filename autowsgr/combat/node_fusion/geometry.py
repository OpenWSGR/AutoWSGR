"""资料不足时使用的几何证据组合与实际路由可达性，不另建旧追踪器。"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from autowsgr.combat.node_fusion.map import TrackingMap


def reachable_paths(metadata: TrackingMap, source: str) -> dict[str, tuple[str, ...]]:
    """完整路由按实际边求可达性；缺路由时不虚构边或起点坐标。"""
    if not metadata.capabilities['topology'] or source not in metadata.nodes:
        return {name: () for name in metadata.nodes if name != '0'}
    paths = {source: (source,)}
    queue = deque([source])
    while queue:
        current = queue.popleft()
        for target in metadata.nodes[current].next_nodes or ():
            if target not in paths:
                paths[target] = (*paths[current], target)
                queue.append(target)
    return {name: path for name, path in paths.items() if name != '0'}


def combine_point_terms(
    terms: dict[str, dict[str, Any]], outlier: float
) -> dict[str, dict[str, Any]]:
    """先归一化几何通道，再把整帧异常质量均匀分配到候选节点。

    每节点固定噪声下限会随地图大小累积，导致大图永远无法确认。
    多个点共线、射线无法区分时，降低方向权重，保留明确的距离证据。
    """
    if not terms:
        return {}
    # 航段的垂直误差是一维；节点坐标误差是二维，使用二维柯西核。
    # 保留重尾容错，但不能直接沿用一维核让远点质量随地图大小累积。
    point_distances = {name: row['distance_likelihood'] ** 1.5 for name, row in terms.items()}
    distances = sum(point_distances.values())
    rays = sum(row['ray_likelihood'] for row in terms.values())
    ordered = sorted((row['ray_likelihood'] for row in terms.values()), reverse=True)
    discrimination = 1.0 - ordered[1] / ordered[0] if len(ordered) > 1 and ordered[0] else 0.0
    result = {}
    for name, row in terms.items():
        ray_weight = row['ray_mixture_weight'] * discrimination if rays else 0.0
        distance = point_distances[name] / distances
        ray = row['ray_likelihood'] / rays if rays else 0.0
        likelihood = (1 - outlier) * ((1 - ray_weight) * distance + ray_weight * ray)
        result[name] = {
            **row,
            'ray_mixture_weight': ray_weight,
            'ray_discrimination': discrimination,
            'point_distance_likelihood': point_distances[name],
            'point_likelihood': likelihood + outlier / len(terms),
        }
    return result
