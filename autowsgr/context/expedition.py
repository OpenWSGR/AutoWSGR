"""远征队列模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from .fleet import Fleet


# 游戏最多同时进行 4 条远征
_MAX_EXPEDITIONS = 4


@dataclass
class Expedition:
    """单条远征状态。

    远征共 9 章、每章最多 4 个节点。
    每条远征绑定一支舰队，有特定的时长和资源奖励。
    """

    chapter: int = 0
    """远征章节 (1–9)。"""
    node: int = 0
    """远征节点 (1–4)。"""
    fleet: Fleet | None = None
    """执行远征的舰队；``None`` 表示该槽位空闲。"""
    start_time: float | None = None
    """出发时间戳 (``time.time()``)。"""
    remaining_seconds: int | None = None
    """剩余秒数；``None`` 表示未激活。"""

    @property
    def is_active(self) -> bool:
        """是否正在执行远征。"""
        return self.fleet is not None


@dataclass
class ExpeditionQueue:
    """远征队列（最多 4 条同时进行）。"""

    expeditions: list[Expedition] = field(
        default_factory=lambda: [Expedition() for _ in range(_MAX_EXPEDITIONS)],
    )
    """远征槽位列表。"""

    @property
    def active_count(self) -> int:
        """正在执行的远征数。"""
        return sum(1 for e in self.expeditions if e.is_active)

    @property
    def idle_count(self) -> int:
        """空闲远征槽位数。"""
        return sum(1 for e in self.expeditions if not e.is_active)
