"""决战控制器配置与地图数据。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from autowsgr.combat.node_fusion.map import SHIP_TYPES, TrackingMap
from autowsgr.infra.file_utils import load_yaml


_ENEMY_SPEC_PATH = (
    Path(__file__).resolve().parents[2] / 'data' / 'map' / 'decisive_battle' / 'enemy_spec.yaml'
)


# ═══════════════════════════════════════════════════════════════════════════════
# 地图静态数据
# ═══════════════════════════════════════════════════════════════════════════════

# 数据来源: autowsgr_legacy/data/map/decisive_battle/enemy_spec.yaml
# map_end[chapter][stage] → 该小关最后一个节点字母
# chapter 索引 0 为占位; 有效章节 1-6; stage 索引 0 为占位, 有效小关 1-3。
_MAP_END: list[str] = [
    '',  # 0: 占位
    ' FHH',  # chapter 1: stage1=F, stage2=H, stage3=H
    ' FHH',  # chapter 2
    ' HHJ',  # chapter 3
    ' HHJ',  # chapter 4
    ' HJJ',  # chapter 5
    ' JJJ',  # chapter 6
]

# key_points[chapter][stage] → 需要夜战的关键节点字母集合
_KEY_POINTS: dict[int, list[str]] = {
    1: ['', 'BDF', 'BFH', 'DHJ'],
    2: ['', 'CFH', 'BFH', 'DHJ'],
    3: ['', 'CFH', 'BFH', 'DHJ'],
    4: ['', 'CFH', 'BFH', 'DHJ'],
    5: ['', 'DFH', 'DGJ', 'CGJ'],
    6: ['', 'BGJ', 'CHJ', 'DGJ'],
}


@lru_cache(maxsize=1)
def _load_enemy_spec_data() -> dict:
    """加载决战 enemy_spec.yaml 数据。"""
    return load_yaml(_ENEMY_SPEC_PATH)


def _enemy_slots(raw: object, location: str) -> list[str | None]:
    """移除旧资料的首位占位，保留空槽位置并补足六槽；缺失资料不构造舰队。"""
    if raw is None or raw == []:
        return []
    if not isinstance(raw, list) or not 1 <= len(raw) <= 7 or raw[0] not in ('', None):
        raise ValueError(f'决战敌情必须包含首位占位和至多六槽: {location}')
    slots = [ship if ship not in ('', None) else None for ship in raw[1:]]
    if any(
        ship is not None and (not isinstance(ship, str) or ship not in SHIP_TYPES) for ship in slots
    ):
        raise ValueError(f'决战敌情包含未知中文舰类: {location}: {slots!r}')
    return slots + [None] * (6 - len(slots))


class MapData:
    """决战地图静态数据查询。

    封装 ``map_end`` 与 ``key_points``，提供按 *chapter / stage* 查询的方法。
    """

    @staticmethod
    def get_stage_end_node(chapter: int, stage: int) -> str:
        """获取指定章节、小关的终止节点字母。

        Parameters
        ----------
        chapter:
            章节编号 (1-6)。
        stage:
            小关编号 (1-3)。

        Returns
        -------
        str
            终止节点字母 (如 ``'H'``, ``'J'``)。
            若 chapter/stage 超出范围，抛出 ``ValueError``。
        """
        if 1 <= chapter < len(_MAP_END) and 1 <= stage <= 3:
            return _MAP_END[chapter][stage]
        raise ValueError(f'无效章节/小关: chapter={chapter}, stage={stage}')

    @staticmethod
    def is_stage_end(chapter: int, stage: int, node: str) -> bool:
        """判断当前节点是否为该小关的终止节点。

        Parameters
        ----------
        chapter:
            章节编号 (1-6)。
        stage:
            小关编号 (1-3)。
        node:
            当前节点字母 (如 ``'A'``, ``'H'``)。
        """
        return node == MapData.get_stage_end_node(chapter, stage)

    @staticmethod
    def get_key_points(chapter: int, stage: int) -> set[str]:
        """获取指定章节、小关的关键节点集合 (需夜战)。

        Parameters
        ----------
        chapter:
            章节编号 (4-6)。
        stage:
            小关编号 (1-3)。

        Returns
        -------
        set[str]
            关键节点字母集合；未找到时返回空集。
        """
        kps = _KEY_POINTS.get(chapter, [])
        if 1 <= stage < len(kps):
            return set(kps[stage])
        return set()

    @staticmethod
    def is_key_point(chapter: int, stage: int, node: str) -> bool:
        """判断当前节点是否为关键点 (需夜战)。"""
        return node in MapData.get_key_points(chapter, stage)

    @staticmethod
    def get_enemy(chapter: int, stage: int, node: str) -> list[str | None]:
        """获取有序六槽中文舰类；空槽为 None，缺失节点资料返回空列表。"""
        if not 1 <= chapter < len(_MAP_END) or not 1 <= stage <= 3:
            return []
        try:
            data = _load_enemy_spec_data()
            enemy_data = data.get('enemy', [])
            chapter_data = enemy_data[chapter]
            stage_data = chapter_data[stage]
        except (IndexError, TypeError):
            return []
        if not isinstance(stage_data, dict):
            return []
        return _enemy_slots(stage_data.get(node.upper()), f'{chapter}-{stage} {node}')

    @staticmethod
    def tracking_map(chapter: int, stage: int) -> TrackingMap:
        """构造小关顺序地图；不为未知阵型、坐标或敌情伪造观测。"""
        end = MapData.get_stage_end_node(chapter, stage)
        names = [chr(value) for value in range(ord('A'), ord(end) + 1)]
        raw = {}
        for index, name in enumerate(names):
            ships = MapData.get_enemy(chapter, stage, name)
            raw[name] = {
                'position': None,
                'next': names[index + 1 : index + 2],
                'type': 'FIGHT',
                'detour': None,
                'enemy_formations': ([{'formation': None, 'ships': ships}] if any(ships) else None),
            }
        return TrackingMap.from_dict(raw, source=str(_ENEMY_SPEC_PATH))
