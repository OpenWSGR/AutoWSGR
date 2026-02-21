"""决战控制器配置与地图数据。"""

from __future__ import annotations

from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════════════════════════════
# 地图静态数据
# ═══════════════════════════════════════════════════════════════════════════════

# 数据来源: autowsgr_legacy/data/map/decisive_battle/enemy_spec.yaml
# map_end[chapter][stage] → 该小关最后一个节点字母
# chapter 索引 0 为占位; 有效章节 1–6; stage 索引 0 为占位, 有效小关 1–3。
_MAP_END: list[str] = [
    "",       # 0: 占位
    " FHH",   # chapter 1: stage1=F, stage2=H, stage3=H
    " FHH",   # chapter 2
    " HHJ",   # chapter 3
    " HHJ",   # chapter 4
    " HJJ",   # chapter 5
    " JJJ",   # chapter 6
]

# key_points[chapter][stage] → 需要夜战的关键节点字母集合
_KEY_POINTS: dict[int, list[str]] = {
    4: ["", "CFH", "BFH", "DHJ"],
    5: ["", "DFH", "DGJ", "CGJ"],
    6: ["", "BGJ", "CHJ", "DGJ"],
}


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
            章节编号 (1–6)。
        stage:
            小关编号 (1–3)。

        Returns
        -------
        str
            终止节点字母 (如 ``'H'``, ``'J'``)。
            若 chapter/stage 超出范围，返回 ``'J'`` 作为安全回退。
        """
        if 1 <= chapter < len(_MAP_END) and 1 <= stage <= 3:
            return _MAP_END[chapter][stage]
        return "J"

    @staticmethod
    def is_stage_end(chapter: int, stage: int, node: str) -> bool:
        """判断当前节点是否为该小关的终止节点。

        Parameters
        ----------
        chapter:
            章节编号 (1–6)。
        stage:
            小关编号 (1–3)。
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
            章节编号 (4–6)。
        stage:
            小关编号 (1–3)。

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


# ═══════════════════════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class DecisiveConfig:
    """决战控制器配置。

    Parameters
    ----------
    chapter:
        目标章节 (4–6)。
    level1:
        一级优先舰船 (核心编队成员)。
    level2:
        二级舰船 (补充编队 + 增益技能)。
    flagship_priority:
        旗舰优先级列表，按优先级排列。
    repair_level:
        修理等级 (1=中破修, 2=大破修)。
    full_destroy:
        船舱满时是否自动解装。
    """

    chapter: int = 6
    level1: list[str] = field(default_factory=list)
    level2: list[str] = field(default_factory=list)
    flagship_priority: list[str] = field(default_factory=list)
    repair_level: int = 2
    full_destroy: bool = False
