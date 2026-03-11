"""战斗系统 — 独立于 UI 框架的战斗状态机引擎。"""

from .engine import CombatEngine, run_combat
from .history import CombatEvent, CombatHistory, CombatResult, FightResult
from .node_tracker import MapNodeData, NodeTracker
from .plan import CombatMode, CombatPlan, NodeDecision
from .recognition import (
    SHIP_DROP_PAGE_SIGNATURE,
    ShipDropResult,
    recognize_enemy_formation,
    recognize_ship_drop,
)
from .rules import RuleEngine, RuleResult
from .state import CombatPhase


__all__ = [
    'SHIP_DROP_PAGE_SIGNATURE',
    'CombatEngine',
    'CombatEvent',
    'CombatHistory',
    'CombatMode',
    'CombatPhase',
    'CombatPlan',
    'CombatResult',
    'FightResult',
    'MapNodeData',
    'NodeDecision',
    'NodeTracker',
    'RuleEngine',
    'RuleResult',
    'ShipDropResult',
    'recognize_enemy_formation',
    'recognize_ship_drop',
    'run_combat',
]
