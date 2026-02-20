"""决战控制器配置。"""

from __future__ import annotations

from dataclasses import dataclass, field


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
