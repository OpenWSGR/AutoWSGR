"""战斗系统 — 独立于 UI 框架的战斗状态机引擎。"""

from .engine import CombatEngine, run_combat
from .history import CombatEvent, CombatHistory, CombatResult
from .node_tracker import MapNodeData, NodeTracker
from .plan import CombatMode, CombatPlan, NodeDecision
from .recognition import recognize_enemy_formation
from .rules import RuleEngine, RuleResult
from .state import CombatPhase


__all__ = [
    'CombatEngine',
    'CombatEvent',
    'CombatHistory',
    'CombatMode',
    'CombatPhase',
    'CombatPlan',
    'CombatResult',
    'MapNodeData',
    'NodeDecision',
    'NodeTracker',
    'RuleEngine',
    'RuleResult',
    'recognize_enemy_formation',
    'run_combat',
]
