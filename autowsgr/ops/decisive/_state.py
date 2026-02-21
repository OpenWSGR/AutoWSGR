"""决战阶段枚举与运行时状态。"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

from autowsgr.types import ShipDamageState


class DecisivePhase(enum.Enum):
    """决战过程的宏观阶段。

    状态转移图::

        INIT → ENTER_MAP → [CHOOSE_FLEET] → MAP_READY
        MAP_READY → ADVANCE_CHOICE | PREPARE_COMBAT
        PREPARE_COMBAT → IN_COMBAT → NODE_RESULT
        NODE_RESULT → MAP_READY | STAGE_CLEAR | RETREAT | LEAVE
        STAGE_CLEAR → ENTER_MAP (下一小关) | CHAPTER_CLEAR
        CHAPTER_CLEAR → FINISHED
        RETREAT → ENTER_MAP (重置后重来)
        LEAVE → FINISHED
    """

    INIT = enum.auto()
    """初始状态，未进入决战。"""

    ENTER_MAP = enum.auto()
    """正在从总览页进入/重进地图。"""

    CHOOSE_FLEET = enum.auto()
    """战备舰队获取 overlay 弹出，选择购买舰船。"""

    MAP_READY = enum.auto()
    """地图页就绪，可以出征或选择前进点。"""

    ADVANCE_CHOICE = enum.auto()
    """选择前进点 overlay (分支路径)。"""

    PREPARE_COMBAT = enum.auto()
    """出征准备页 — 编队、修理。"""

    IN_COMBAT = enum.auto()
    """战斗引擎运行中。"""

    NODE_RESULT = enum.auto()
    """节点战斗结束，决定下一步。"""

    STAGE_CLEAR = enum.auto()
    """小关通关（第 1/2/3 小节结束）。"""

    CHAPTER_CLEAR = enum.auto()
    """大关通关（3 个小节全部完成）。"""

    RETREAT = enum.auto()
    """撤退中 (清空进度重来)。"""

    LEAVE = enum.auto()
    """暂离 (保存进度退出)。"""

    FINISHED = enum.auto()
    """本轮决战完成。"""


@dataclass
class DecisiveState:
    """决战运行时可变状态。

    跟踪当前推进进度、舰队组成、资源等信息。

    Attributes
    ----------
    chapter:
        章节 (4–6)。
    stage:
        当前小关 (1–3), 0 表示尚未开始。
    node:
        当前节点字母 ('A', 'B', ...)。
    phase:
        当前宏观阶段。
    score:
        当前可用资源分数 (蜂蜜)。
    ships:
        已获取的全部舰船名集合。
    fleet:
        当前编队舰船列表 (索引 0 留空, 1–6 为位置)。
    ship_stats:
        舰船血量状态。
    """

    chapter: int = 6
    stage: int = 0
    node: str = "A"
    phase: DecisivePhase = DecisivePhase.INIT
    score: int = 10
    ships: set[str] = field(default_factory=set)
    fleet: list[str] = field(default_factory=lambda: [""] * 7)
    ship_stats: list[ShipDamageState] = field(default_factory=lambda: [ShipDamageState.NO_SHIP] * 6)

    def reset(self) -> None:
        """重置状态 (保留 chapter)。"""
        chapter = self.chapter
        self.__init__()  # type: ignore[misc]
        self.chapter = chapter

    def is_begin(self) -> bool:
        """是否在第一小关第一节点。"""
        return self.stage <= 1 and self.node == "A"
