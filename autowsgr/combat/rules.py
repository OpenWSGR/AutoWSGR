"""安全规则引擎 — 替代旧代码中的 ``eval()``。

旧代码使用类似 ``eval("(BB >= 2) and (CV > 0)")`` 的方式在运行时判断敌方编成，
存在代码注入风险。本模块提供结构化的规则评估，完全消除 ``eval`` 调用。

规则来源:
  - YAML 配置文件中的 ``enemy_rules`` 字段
  - 旧格式: ``[["(BB >= 2) and (CV > 0)", "retreat"], ["(SS >= 3)", 4]]``
  - 新格式（推荐）: 结构化条件字典

使用方式::

    engine = RuleEngine.from_legacy_rules([
        ["(BB >= 2) and (CV > 0)", "retreat"],
        ["(SS >= 3)", 4],
    ])
    result = engine.evaluate({"BB": 3, "CV": 1, "DD": 2})
    # → RuleResult.RETREAT

    engine2 = RuleEngine.from_formation_rules([
        ["单纵阵", "retreat"],
        ["复纵阵", 4],
    ])
    result2 = engine2.evaluate_formation("单纵阵")
    # → RuleResult.RETREAT
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from loguru import logger

from autowsgr.types import Formation, SearchEnemyAction

# 允许在规则中出现的舰种标识符
_SHIP_TYPE_PATTERN = re.compile(
    r"\b(CV|CVL|AV|BB|BBV|BC|CA|CAV|CLT|CL|BM|DD|SSG|SS|SC|NAP|"
    r"ASDG|AADG|KP|CG|CBG|BG)\b"
)


# ═══════════════════════════════════════════════════════════════════════════════
# 规则结果
# ═══════════════════════════════════════════════════════════════════════════════


class RuleResult(Enum):
    """规则评估结果。"""

    NO_ACTION = auto()
    """无特殊动作，正常进入战斗。"""

    RETREAT = auto()
    """撤退。"""

    DETOUR = auto()
    """迂回。"""

    FORMATION = auto()
    """选择指定阵型（附带 formation 值）。"""


@dataclass(frozen=True, slots=True)
class RuleAction:
    """规则评估的具体动作。

    Attributes
    ----------
    result:
        动作类型。
    formation:
        当 ``result == RuleResult.FORMATION`` 时，指定的阵型。
    """

    result: RuleResult
    formation: Formation | None = None

    @staticmethod
    def no_action() -> RuleAction:
        return RuleAction(result=RuleResult.NO_ACTION)

    @staticmethod
    def retreat() -> RuleAction:
        return RuleAction(result=RuleResult.RETREAT)

    @staticmethod
    def detour() -> RuleAction:
        return RuleAction(result=RuleResult.DETOUR)

    @staticmethod
    def set_formation(formation: Formation) -> RuleAction:
        return RuleAction(result=RuleResult.FORMATION, formation=formation)


# ═══════════════════════════════════════════════════════════════════════════════
# 单条件 & 规则
# ═══════════════════════════════════════════════════════════════════════════════

_OPERATORS: dict[str, Any] = {
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


@dataclass(frozen=True, slots=True)
class Condition:
    """单个比较条件。

    Attributes
    ----------
    field:
        要检查的字段名（如 ``"BB"``, ``"CV"``, ``"total"``）。
    op:
        比较操作符。
    value:
        比较目标值。
    """

    field: str
    op: str
    value: int | float

    def __post_init__(self) -> None:
        if self.op not in _OPERATORS:
            raise ValueError(f"不支持的操作符: '{self.op}'，支持: {list(_OPERATORS)}")

    def evaluate(self, context: dict[str, int | float]) -> bool:
        """在给定上下文中评估此条件。"""
        actual = context.get(self.field, 0)
        return _OPERATORS[self.op](actual, self.value)


@dataclass(frozen=True, slots=True)
class Rule:
    """一条规则：所有条件都满足时触发指定动作。

    Attributes
    ----------
    conditions:
        需要全部满足的条件列表（AND 语义）。
    action:
        条件全部满足时返回的动作。
    """

    conditions: list[Condition]
    action: RuleAction

    def evaluate(self, context: dict[str, int | float]) -> bool:
        """所有条件是否均满足。"""
        return all(c.evaluate(context) for c in self.conditions)


# ═══════════════════════════════════════════════════════════════════════════════
# 规则引擎
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class RuleEngine:
    """规则引擎 — 顺序评估规则列表，返回首个匹配的动作。

    Attributes
    ----------
    rules:
        规则列表，按优先级从高到低排列。
    default:
        所有规则都不匹配时的默认动作。
    """

    rules: list[Rule] = field(default_factory=list)
    default: RuleAction = field(default_factory=RuleAction.no_action)

    def evaluate(self, context: dict[str, int | float]) -> RuleAction:
        """对敌方编成上下文评估所有规则。

        Parameters
        ----------
        context:
            敌方舰船类型计数，如 ``{"BB": 2, "CV": 1, "DD": 3, "total": 6}``。

        Returns
        -------
        RuleAction
            首个匹配规则的动作，或 ``self.default``。
        """
        for rule in self.rules:
            if rule.evaluate(context):
                logger.debug(
                    "规则命中: {} → {}",
                    [(c.field, c.op, c.value) for c in rule.conditions],
                    rule.action.result.name,
                )
                return rule.action
        return self.default

    @classmethod
    def from_legacy_rules(cls, legacy_rules: list[list]) -> RuleEngine:
        """从旧版 ``enemy_rules`` 格式构建。

        旧格式: ``[["(BB >= 2) and (CV > 0)", "retreat"], ...]``

        Parameters
        ----------
        legacy_rules:
            旧格式规则列表。每项为 ``[condition_str, action]``，
            ``action`` 可以是字符串 (``"retreat"``/``"detour"``) 或整数 (阵型编号)。

        Returns
        -------
        RuleEngine
        """
        rules: list[Rule] = []
        for item in legacy_rules:
            condition_str, action_value = item[0], item[1]
            conditions = _parse_legacy_condition(condition_str)
            action = _parse_action_value(action_value)
            rules.append(Rule(conditions=conditions, action=action))
        return cls(rules=rules)

    @classmethod
    def from_formation_rules(cls, formation_rules: list[list]) -> RuleEngine:
        """从旧版 ``enemy_formation_rules`` 格式构建。

        旧格式: ``[["单纵阵", "retreat"], ["复纵阵", 4], ...]``

        这类规则不走条件评估，而是匹配敌方阵型字符串。
        内部转换为以 ``_formation`` 字段为键的条件。

        Parameters
        ----------
        formation_rules:
            旧格式阵型规则列表。

        Returns
        -------
        RuleEngine
        """
        rules: list[Rule] = []
        for item in formation_rules:
            formation_name, action_value = item[0], item[1]
            # 使用特殊字段 _formation 存储阵型名称的哈希
            conditions = [Condition(field=f"_formation:{formation_name}", op="==", value=1)]
            action = _parse_action_value(action_value)
            rules.append(Rule(conditions=conditions, action=action))
        return cls(rules=rules)

    def evaluate_formation(self, enemy_formation: str) -> RuleAction:
        """评估敌方阵型规则。

        Parameters
        ----------
        enemy_formation:
            敌方阵型名称。

        Returns
        -------
        RuleAction
        """
        # 构建特殊上下文
        context: dict[str, int | float] = {f"_formation:{enemy_formation}": 1}
        return self.evaluate(context)


# ═══════════════════════════════════════════════════════════════════════════════
# 旧格式解析
# ═══════════════════════════════════════════════════════════════════════════════

# 匹配 "BB >= 2" 形式的条件片段
_CONDITION_PIECE_RE = re.compile(
    r"([A-Z]{2,4})\s*(>=|<=|>|<|==|!=)\s*(\d+(?:\.\d+)?)"
)


def _parse_legacy_condition(condition_str: str) -> list[Condition]:
    """解析旧格式条件字符串为 ``Condition`` 列表。

    旧格式: ``"(BB >= 2) and (CV > 0)"``
    解析结果: ``[Condition("BB", ">=", 2), Condition("CV", ">", 0)]``

    用 ``and`` 连接的条件被拆分为独立的 ``Condition`` （AND 语义）。
    不支持 ``or`` — 用多条规则替代。
    """
    matches = _CONDITION_PIECE_RE.findall(condition_str)
    if not matches:
        raise ValueError(f"无法解析规则条件: '{condition_str}'")

    conditions: list[Condition] = []
    for field_name, op, value_str in matches:
        value = float(value_str) if "." in value_str else int(value_str)
        conditions.append(Condition(field=field_name, op=op, value=value))
    return conditions


def _parse_action_value(action_value: str | int) -> RuleAction:
    """将旧格式的动作值转换为 ``RuleAction``。

    - ``"retreat"`` → ``RuleAction.retreat()``
    - ``"detour"`` → ``RuleAction.detour()``
    - ``4`` (整数) → ``RuleAction.set_formation(Formation(4))``
    """
    if isinstance(action_value, int):
        return RuleAction.set_formation(Formation(action_value))
    if isinstance(action_value, str):
        action_lower = action_value.lower()
        if action_lower == "retreat":
            return RuleAction.retreat()
        if action_lower == "detour":
            return RuleAction.detour()
        # 尝试作为阵型数字
        try:
            return RuleAction.set_formation(Formation(int(action_value)))
        except (ValueError, KeyError):
            pass
    raise ValueError(f"无法识别的动作值: {action_value!r}")
