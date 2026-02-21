"""战斗引擎结果数据类。

所有识别与操作函数现已直接定义在 :mod:`~autowsgr.combat.actions` 中，
不再使用回调类型。此文件仅保留 :class:`CombatResult` 供引擎返回结果。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from autowsgr.combat.history import CombatHistory
from autowsgr.types import ConditionFlag, ShipDamageState


# ═══════════════════════════════════════════════════════════════════════════════
# 战斗结果
# ═══════════════════════════════════════════════════════════════════════════════


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
    """

    flag: ConditionFlag = ConditionFlag.FIGHT_END
    history: CombatHistory = field(default_factory=CombatHistory)
    ship_stats: list[ShipDamageState] = field(
        default_factory=lambda: [ShipDamageState.NORMAL] * 6,
    )
    node_count: int = 0
