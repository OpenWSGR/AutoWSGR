"""决战阶段枚举与运行时状态。"""

from __future__ import annotations

from dataclasses import dataclass, field

from autowsgr.types import DecisivePhase, ShipDamageState


@dataclass
class DecisiveState:
    """决战运行时可变状态。

    跟踪当前推进进度、舰队组成、资源等信息。

    Attributes
    ----------
    chapter:
        章节 (4-6)。
    stage:
        当前小关 (1-3), 0 表示尚未开始。
    node:
        当前节点字母 ('A', 'B', ...)。
    phase:
        当前宏观阶段。
    score:
        当前可用资源分数 (蜂蜜)。
    ships:
        已获取的全部舰船名集合。
    fleet:
        当前编队舰船列表 (索引 0 留空, 1-6 为位置)。
    ship_stats:
        舰船血量状态。
    """

    chapter: int = 6
    stage: int = 0
    node: str = 'U'  # U 表示未知节点
    phase: DecisivePhase = DecisivePhase.INIT
    score: int = 10
    ships: set[str] = field(default_factory=set)
    fleet: list[str] = field(default_factory=lambda: [''] * 7)
    ship_stats: list[ShipDamageState] = field(default_factory=lambda: [ShipDamageState.NO_SHIP] * 6)

    def reset(self) -> None:
        """重置状态 (保留 chapter)。"""
        chapter = self.chapter
        self.__init__()  # type: ignore[misc]
        self.chapter = chapter

    def is_begin(self) -> bool:
        """是否在第一小关第一节点。"""
        # 如果在第一关且是未知节点，仍返回True，以防不选船导致无法推进
        return self.stage <= 1 and (self.node == 'A' or self.node == 'U')
