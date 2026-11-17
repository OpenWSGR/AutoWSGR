"""战斗系统 — 独立于 UI 框架的战斗状态机引擎。"""

from autowsgr.combat.engine import CombatEngine, run_combat
from autowsgr.combat.fleet import (
    ALLOWED_SHIP_TYPE_CODES,
    FleetPreset,
    FleetSelectionSource,
    FleetSlotRule,
    ResolvedFleetSelection,
    ShipSelector,
    fleet_slot_from_api,
    resolve_fleet_selection,
)
from autowsgr.combat.history import (
    CombatEvent,
    CombatHistory,
    CombatResult,
    FightResult,
    grade_condition_met,
)
from autowsgr.combat.node_fusion import FusionTracker, NodeEstimate
from autowsgr.combat.node_fusion.coordinates import MapNodeData
from autowsgr.combat.plan import CombatMode, CombatPlan, GradeCondition, NodeDecision
from autowsgr.combat.recognition import (
    SHIP_DROP_PAGE_SIGNATURE,
    ShipDropResult,
    recognize_enemy_formation,
    recognize_ship_drop,
)
from autowsgr.combat.rules import RuleEngine, RuleResult
from autowsgr.combat.state import CombatPhase


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
    'FusionTracker',
    'GradeCondition',
    'MapNodeData',
    'NodeDecision',
    'NodeEstimate',
    'ResolvedFleetSelection',
    'RuleEngine',
    'RuleResult',
    'ShipDropResult',
    'ShipSelector',
    'fleet_slot_from_api',
    'grade_condition_met',
    'recognize_enemy_formation',
    'recognize_ship_drop',
    'resolve_fleet_selection',
    'run_combat',
]
