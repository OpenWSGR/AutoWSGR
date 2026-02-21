"""战斗事件记录与历史。

记录一次完整战斗流程中每个节点发生的事件（索敌、阵型、夜战、结算等），
用于日志输出、战后分析和条件检查。

使用方式::

    history = CombatHistory()
    history.add(CombatEvent(
        event_type=EventType.SPOT_ENEMY,
        node="A",
        action="retreat",
        enemies={"BB": 2, "CV": 1},
    ))
    print(history)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from autowsgr.types import ShipDamageState


class EventType(Enum):
    """战斗事件类型。"""

    FIGHT_CONDITION = auto()
    """战况选择。"""

    SPOT_ENEMY = auto()
    """索敌成功。"""

    DETOUR = auto()
    """迂回尝试。"""

    FORMATION = auto()
    """阵型选择。"""

    ENTER_FIGHT = auto()
    """进入战斗。"""

    NIGHT_BATTLE = auto()
    """夜战选择。"""

    RESULT = auto()
    """战果结算。"""

    GET_SHIP = auto()
    """获取舰船。"""

    PROCEED = auto()
    """继续前进 / 回港。"""

    FLAGSHIP_DAMAGE = auto()
    """旗舰大破。"""

    AUTO_RETURN = auto()
    """自动回港。"""

    SL = auto()
    """SL 操作。"""


@dataclass
class CombatEvent:
    """单个战斗事件记录。

    Attributes
    ----------
    event_type:
        事件类型。
    node:
        事件发生时所在节点（如 ``"A"``, ``"B"``）。
    action:
        玩家执行的动作（如 ``"retreat"``, ``"fight"``, ``"追击"`` 等）。
    result:
        事件结果（如战果等级 ``"S"``、舰船名称等）。
    enemies:
        敌方编成信息（仅索敌事件）。
    ship_stats:
        我方舰船状态（仅继续前进事件）。
    extra:
        其他附加信息。
    """

    event_type: EventType
    node: str = ""
    action: str = ""
    result: str = ""
    enemies: dict[str, int] | None = None
    ship_stats: list[ShipDamageState] | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        parts = [f"[{self.event_type.name}]"]
        if self.node:
            parts.append(f"节点={self.node}")
        if self.action:
            parts.append(f"动作={self.action}")
        if self.result:
            parts.append(f"结果={self.result}")
        if self.enemies is not None:
            parts.append(f"敌方={self.enemies}")
        if self.ship_stats is not None:
            parts.append(f"血量={self.ship_stats}")
        return " | ".join(parts)


@dataclass
class FightResult:
    """单次战斗结算信息。

    Attributes
    ----------
    mvp:
        MVP 位置 (1-6)。
    grade:
        战果等级 (``"D"``/``"C"``/``"B"``/``"A"``/``"S"``/``"SS"``)。
    ship_stats:
        战后我方血量状态。
    """

    mvp: int = 0
    grade: str = ""
    ship_stats: list[ShipDamageState] = field(
        default_factory=lambda: [ShipDamageState.NORMAL] * 6,
    )

    _GRADE_ORDER = ["D", "C", "B", "A", "S", "SS"]

    def __str__(self) -> str:
        return f"MVP={self.mvp} 评价={self.grade}"

    def __lt__(self, other: object) -> bool:
        if isinstance(other, FightResult):
            return self._grade_index() < other._grade_index()
        if isinstance(other, str):
            return self._grade_index() < self._GRADE_ORDER.index(other)
        return NotImplemented

    def __le__(self, other: object) -> bool:
        if isinstance(other, FightResult):
            return self._grade_index() <= other._grade_index()
        if isinstance(other, str):
            return self._grade_index() <= self._GRADE_ORDER.index(other)
        return NotImplemented

    def __gt__(self, other: object) -> bool:
        result = self.__le__(other)
        if result is NotImplemented:
            return result
        return not result

    def __ge__(self, other: object) -> bool:
        result = self.__lt__(other)
        if result is NotImplemented:
            return result
        return not result

    def _grade_index(self) -> int:
        try:
            return self._GRADE_ORDER.index(self.grade)
        except ValueError:
            return -1


class CombatHistory:
    """一次完整战斗的事件历史记录。"""

    def __init__(self) -> None:
        self.events: list[CombatEvent] = []

    def add(self, event: CombatEvent) -> None:
        """添加一个事件。"""
        self.events.append(event)

    def reset(self) -> None:
        """清空历史。"""
        self.events = []

    @property
    def last_node(self) -> str:
        """最后一个事件的节点。"""
        if not self.events:
            return ""
        return self.events[-1].node

    def get_fight_results(self) -> dict[str, FightResult] | list[FightResult]:
        """提取所有战果结算事件的结果。

        Returns
        -------
        dict[str, FightResult] | list[FightResult]
            如果节点名为字母 → 按节点索引的字典。
            否则 → 按顺序的列表。
        """
        results_dict: dict[str, FightResult] = {}
        results_list: list[FightResult] = []

        for event in self.events:
            if event.event_type != EventType.RESULT:
                continue
            # 尝试解析结果
            fr = FightResult(grade=event.result)
            if event.node and event.node.isalpha():
                results_dict[event.node] = fr
            else:
                results_list.append(fr)

        return results_list if results_list else results_dict

    def __str__(self) -> str:
        return "\n".join(str(e) for e in self.events)

    def __repr__(self) -> str:
        return f"CombatHistory({len(self.events)} events)"

    def __len__(self) -> int:
        return len(self.events)
