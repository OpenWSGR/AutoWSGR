"""战斗系统 — 独立于 UI 框架的战斗状态机引擎。

模块组成::

    combat/
    ├── state.py          # 战斗状态枚举与转移图
    ├── rules.py          # 安全规则引擎（替代 eval）
    ├── plan.py           # 作战计划（YAML 配置驱动）
    ├── history.py        # 战斗事件记录
    ├── recognizer.py     # 战斗状态视觉识别
    ├── actions.py        # 战斗操作函数（点击坐标封装）
    ├── node_tracker.py   # 舰船位置追踪与节点判定
    └── engine.py         # 战斗引擎（状态机主循环）

典型使用::

    from autowsgr.combat.engine import CombatEngine
    from autowsgr.combat.plan import CombatPlan

    engine = CombatEngine(device)
    result = engine.fight(plan)
"""

from .plan import CombatMode, CombatPlan, NodeDecision
from .callbacks import CombatResult
from .state import CombatPhase
from .rules import RuleEngine, RuleResult
from .history import CombatHistory, CombatEvent
from .node_tracker import MapNodeData, NodeTracker
from .engine import CombatEngine, run_combat

__all__ = [
    "CombatPhase",
    "CombatResult",
    "RuleEngine",
    "RuleResult",
    "CombatPlan",
    "NodeDecision",
    "CombatHistory",
    "CombatEvent",
    "MapNodeData",
    "NodeTracker",
    "CombatEngine",
    "CombatMode",
    "run_combat",
]
