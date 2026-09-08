"""Decisive battle configuration and per-map data."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from autowsgr.infra.file_utils import load_yaml


_MAP_DATA_ROOT = (
    Path(__file__).resolve().parents[2] / 'data' / 'map' / 'decisive_battle' / 'silent_warrior'
)


@lru_cache(maxsize=18)
def _load_map_data(chapter: int, stage: int) -> dict[str, Any]:
    path = _MAP_DATA_ROOT / f'EX-{chapter}-{stage}.yaml'
    data = load_yaml(path)
    if not isinstance(data, dict) or not isinstance(data.get('nodes'), dict):
        raise TypeError(f'invalid decisive map data: {path}')
    return data


def _node_label(node_id: str, node: dict[str, Any]) -> str:
    return str(node.get('label', node_id)).upper()


def _leftmost_node_ids(data: dict[str, Any]) -> dict[str, str]:
    """Return the node IDs on the route that always takes the first edge."""
    nodes = data['nodes']
    result: dict[str, str] = {}
    current = '0'
    visited: set[str] = set()
    while current not in visited:
        visited.add(current)
        node = nodes.get(current)
        if not isinstance(node, dict):
            break
        label = _node_label(current, node)
        result.setdefault(label, current)
        next_nodes = node.get('next', [])
        if not next_nodes:
            break
        current = str(next_nodes[0])
    return result


class MapData:
    """Query the normalized per-EX decisive map files."""

    @staticmethod
    def get_stage_end_node(chapter: int, stage: int) -> str:
        data = _load_map_data(chapter, stage)
        terminal_labels = {
            _node_label(node_id, node)
            for node_id, node in data['nodes'].items()
            if isinstance(node, dict) and node_id != '0' and not node.get('next', [])
        }
        if len(terminal_labels) != 1:
            raise ValueError(f'invalid decisive terminal nodes: chapter={chapter}, stage={stage}')
        return terminal_labels.pop()

    @staticmethod
    def is_stage_end(chapter: int, stage: int, node: str) -> bool:
        return node.upper() == MapData.get_stage_end_node(chapter, stage)

    @staticmethod
    def get_key_points(chapter: int, stage: int) -> set[str]:
        data = _load_map_data(chapter, stage)
        return {str(node).upper() for node in data.get('key_points', [])}

    @staticmethod
    def is_key_point(chapter: int, stage: int, node: str) -> bool:
        return node.upper() in MapData.get_key_points(chapter, stage)

    @staticmethod
    def get_enemy(chapter: int, stage: int, node: str) -> list[str]:
        data = _load_map_data(chapter, stage)
        enemy = data.get('enemy', {}).get(node.upper(), [])
        return [str(value) for value in enemy if value]

    @staticmethod
    def get_leftmost_choices(chapter: int, stage: int, source_node: str) -> list[str]:
        """Return successors from the route node for an always-left path."""
        data = _load_map_data(chapter, stage)
        nodes = data['nodes']
        source = source_node.upper()
        source_id = '0' if source in {'', 'U', '0'} else _leftmost_node_ids(data).get(source)
        if source_id is None:
            candidates = [
                (node.get('column', 0), node.get('index', 0), node_id)
                for node_id, node in nodes.items()
                if isinstance(node, dict) and _node_label(node_id, node) == source
            ]
            source_id = min(candidates)[2] if candidates else None
        if source_id is None:
            return []
        return [str(node_id) for node_id in nodes[source_id].get('next', [])]
