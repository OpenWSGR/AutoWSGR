"""建造 / 开发队列模型。"""

from __future__ import annotations

from dataclasses import dataclass, field


# 游戏默认建造槽位数量
_DEFAULT_BUILD_SLOTS = 4


@dataclass
class BuildSlot:
    """单个建造槽位。"""

    occupied: bool = False
    """是否有在建项目。"""
    remaining_seconds: int = 0
    """剩余建造时间（秒）。"""

    @property
    def is_complete(self) -> bool:
        """建造是否已完成（可收取）。"""
        return self.occupied and self.remaining_seconds <= 0

    @property
    def is_idle(self) -> bool:
        """槽位是否空闲。"""
        return not self.occupied


@dataclass
class BuildQueue:
    """建造队列。

    游戏默认 4 个槽位，可用钻石解锁更多。
    每个槽位可用于舰船建造或装备开发。
    """

    slots: list[BuildSlot] = field(
        default_factory=lambda: [BuildSlot() for _ in range(_DEFAULT_BUILD_SLOTS)],
    )
    """所有建造槽位。"""

    @property
    def idle_count(self) -> int:
        """空闲槽位数量。"""
        return sum(1 for s in self.slots if s.is_idle)

    @property
    def complete_count(self) -> int:
        """已完成可收取的数量。"""
        return sum(1 for s in self.slots if s.is_complete)
