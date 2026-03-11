"""战斗事件记录与历史。

记录一次完整战斗流程中每个节点发生的事件（索敌、阵型、夜战、结算等），
用于日志输出、战后分析和条件检查。

"""

from __future__ import annotations

import typing
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Any

from autowsgr.infra.logger import get_logger
from autowsgr.types import ConditionFlag, ShipDamageState


if TYPE_CHECKING:
    from autowsgr.context.ship import Ship


_log = get_logger('combat')


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
    node: str = ''
    action: str = ''
    result: str = ''
    enemies: dict[str, int] | None = None
    ship_stats: list[ShipDamageState] | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        parts = [f'[{self.event_type.name}]']
        if self.node:
            parts.append(f'节点={self.node}')
        if self.action:
            parts.append(f'动作={self.action}')
        if self.result:
            parts.append(f'结果={self.result}')
        if self.enemies is not None:
            parts.append(f'敌方={self.enemies}')
        if self.ship_stats is not None:
            parts.append(f'血量={self.ship_stats}')
        return ' | '.join(parts)


@dataclass
class FightResult:
    """单次战斗结算信息。

    Attributes
    ----------
    node:
        节点名称 (如 ``"A"``, ``"B"``)。
    mvp:
        MVP 位置 (1-6), ``None`` 表示未识别。
    grade:
        战果等级 (``"D"``/``"C"``/``"B"``/``"A"``/``"S"``/``"SS"``)。
    ship_stats:
        战后我方血量状态。
    dropped_ship:
        本节点掉落的舰船名称, 空字符串表示无掉落。
    """

    node: str = ''
    mvp: int | None = None
    grade: str = ''
    ship_stats: list[ShipDamageState] = field(
        default_factory=lambda: [ShipDamageState.NORMAL] * 6,
    )
    dropped_ship: str = ''

    _GRADE_ORDER: typing.ClassVar[list[str]] = ['D', 'C', 'B', 'A', 'S', 'SS']

    def __str__(self) -> str:
        parts = []
        if self.mvp is not None:
            parts.append(f'MVP={self.mvp}')
        if self.dropped_ship:
            parts.append(f'掉落={self.dropped_ship}')
        parts.append(f'评价={self.grade}')
        return ' '.join(parts)

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
            _log.debug("[History] 未知战果等级: '{}'", self.grade)
            return -1


class CombatHistory:
    """一次完整战斗的事件历史记录。"""

    def __init__(self) -> None:
        self.events: list[CombatEvent] = []

    def add(self, event: CombatEvent) -> None:
        """添加一个事件。"""
        self.events.append(event)
        _log.debug('[History] 记录事件: {}', event)

    def reset(self) -> None:
        """清空历史。"""
        count = len(self.events)
        self.events = []
        _log.debug('[History] 历史已清空 (原 {} 条记录)', count)

    @property
    def last_node(self) -> str:
        """最后一个事件的节点。"""
        if not self.events:
            return ''
        return self.events[-1].node

    def get_fight_results(self) -> dict[str, FightResult] | list[FightResult]:
        """提取所有战果结算事件的结果。

        Returns
        -------
        dict[str, FightResult] | list[FightResult]
            如果节点名为字母 -> 按节点索引的字典。
            否则 -> 按顺序的列表。
        """
        fight_results = self._build_fight_results()

        results_dict: dict[str, FightResult] = {}
        results_list: list[FightResult] = []
        for fr in fight_results:
            if fr.node and fr.node.isalpha():
                results_dict[fr.node] = fr
            else:
                results_list.append(fr)

        results = results_list or results_dict
        _log.debug('[History] 提取战果: {} 条结算记录', len(results))
        return results

    def get_fight_results_list(self) -> list[FightResult]:
        """提取所有战果结算信息 (始终返回列表)。"""
        return self._build_fight_results()

    def _build_fight_results(self) -> list[FightResult]:
        """从事件列表构建 FightResult。"""
        results: list[FightResult] = []
        for i, event in enumerate(self.events):
            if event.event_type != EventType.RESULT:
                continue
            fr = FightResult(
                node=event.node,
                grade=event.result,
                ship_stats=(
                    event.ship_stats[:] if event.ship_stats else [ShipDamageState.NORMAL] * 6
                ),
            )
            # 查找紧邻的 GET_SHIP 事件
            if i + 1 < len(self.events) and self.events[i + 1].event_type == EventType.GET_SHIP:
                fr.dropped_ship = self.events[i + 1].result
            results.append(fr)
        return results

    def __str__(self) -> str:
        return '\n'.join(str(e) for e in self.events)

    def __repr__(self) -> str:
        return f'CombatHistory({len(self.events)} events)'

    def __len__(self) -> int:
        return len(self.events)


@dataclass
class CombatResult:
    """一次完整战斗的结果。

    Attributes
    ----------
    flag:
        流程状态标记。
    history:
        完整战斗事件历史。
    ship_stats:
        战后血量状态。
    node_count:
        推进节点数。
    loot_count:
        战斗开始时今日已获取战利品数量 (仅常规战, 出征面板识别)。
    ship_acquired_count:
        战斗开始时今日已获取舰船数量 (仅常规战, 出征面板识别)。
    fleet:
        出击舰队 (含等级、血量等信息, 战斗准备页面识别)。
    ship_full:
        是否已获取满 500 船。
    """

    flag: ConditionFlag = ConditionFlag.FIGHT_END
    history: CombatHistory = field(default_factory=CombatHistory)
    ship_stats: list[ShipDamageState] = field(
        default_factory=lambda: [ShipDamageState.NORMAL] * 6,
    )
    node_count: int = 0
    loot_count: int | None = None
    ship_acquired_count: int | None = None
    fleet: list[Ship] | None = None
    ship_full: bool = False

    @property
    def fight_results(self) -> list[FightResult]:
        """各节点战斗结算信息列表, 从 history 解析。"""
        return self.history.get_fight_results_list()
