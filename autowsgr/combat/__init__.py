"""战斗系统 — 独立于 UI 框架的战斗状态机引擎。"""

from .engine import CombatEngine, run_combat
from .fleet import (
    ALLOWED_SHIP_TYPE_CODES,
    FleetPreset,
    FleetSelectionSource,
    FleetSlotRule,
    ResolvedFleetSelection,
    ShipSelector,
    fleet_slot_from_api,
    resolve_fleet_selection,
)
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
    'ALLOWED_SHIP_TYPE_CODES',
    'SHIP_DROP_PAGE_SIGNATURE',
    'CombatEngine',
    'CombatEvent',
    'CombatHistory',
    'CombatMode',
    'CombatPhase',
    'CombatPlan',
    'CombatResult',
    'FightResult',
    'FleetPreset',
    'FleetSelectionSource',
    'FleetSlotRule',
    'MapNodeData',
    'NodeDecision',
    'NodeTracker',
    'ResolvedFleetSelection',
    'RuleEngine',
    'RuleResult',
    'ShipDropResult',
    'ShipSelector',
    'fleet_slot_from_api',
    'recognize_enemy_formation',
    'recognize_ship_drop',
    'resolve_fleet_selection',
    'run_combat',
]
