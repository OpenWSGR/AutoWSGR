"""战斗引擎回调类型与结果数据类。

将回调类型签名和 :class:`CombatResult` 从 ``engine.py`` 中分离，
供 ``handlers.py`` 和 ``engine.py`` 共同引用，避免循环依赖。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from autowsgr.combat.history import CombatHistory
from autowsgr.types import ConditionFlag


# ═══════════════════════════════════════════════════════════════════════════════
# 回调类型签名
# ═══════════════════════════════════════════════════════════════════════════════

GetEnemyInfoFunc = Callable[[], dict[str, int]]
"""获取敌方编成信息的回调: ``() → {"BB": 2, "CV": 1, ...}``"""

GetEnemyFormationFunc = Callable[[], str]
"""获取敌方阵型的回调: ``() → "单纵阵"``"""

DetectShipStatsFunc = Callable[[str], list[int]]
"""检测我方血量的回调: ``(mode) → [0, 0, 1, 2, -1, -1, -1]``"""

DetectResultGradeFunc = Callable[[], str]
"""检测战果等级的回调: ``() → "S"``"""

GetShipDropFunc = Callable[[], str | None]
"""获取掉落舰船的回调: ``() → "吹雪" | None``"""

ImageExistFunc = Callable[[str, float], bool]
"""检查图像是否存在: ``(template_key, confidence) → bool``"""

ClickImageFunc = Callable[[str, float], bool]
"""点击指定图像: ``(template_key, timeout) → clicked``"""


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
    ship_stats: list[int] = field(default_factory=lambda: [0] * 7)
    node_count: int = 0
