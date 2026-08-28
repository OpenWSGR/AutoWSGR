"""游戏对象序列化辅助函数。

将内部数据模型 (Resources, Fleet, Ship, ExpeditionQueue, BuildQueue, CombatResult)
转换为 JSON 可序列化的 dict，供 API 端点使用。
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from autowsgr.combat import CombatPlan
    from autowsgr.combat.fleet import ResolvedFleetSelection
    from autowsgr.server.schemas import CombatPlanRequest


def serialize_resources(resources: Any) -> dict[str, int]:
    """序列化 Resources 对象。"""
    return {
        'fuel': resources.fuel,
        'ammo': resources.ammo,
        'steel': resources.steel,
        'aluminum': resources.aluminum,
        'diamond': resources.diamond,
        'fast_repair': resources.fast_repair,
        'fast_build': resources.fast_build,
        'ship_blueprint': resources.ship_blueprint,
        'equipment_blueprint': resources.equipment_blueprint,
    }


def serialize_ship(ship: Any) -> dict[str, Any]:
    """序列化 Ship 对象。"""
    return {
        'name': ship.name,
        'ship_type': ship.ship_type.value if ship.ship_type else None,
        'level': ship.level,
        'health': ship.health,
        'max_health': ship.max_health,
        'damage_state': ship.damage_state.value,
        'locked': ship.locked,
    }


def serialize_fleet(fleet: Any) -> dict[str, Any]:
    """序列化 Fleet 对象。"""
    return {
        'fleet_id': fleet.fleet_id,
        'ships': [serialize_ship(s) for s in fleet.ships],
        'size': fleet.size,
        'has_severely_damaged': fleet.has_severely_damaged,
    }


def serialize_expedition_queue(expeditions: Any) -> dict[str, Any]:
    """序列化 ExpeditionQueue 对象。"""
    return {
        'slots': [
            {
                'chapter': e.chapter,
                'node': e.node,
                'fleet_id': e.fleet.fleet_id if e.fleet else None,
                'is_active': e.is_active,
                'remaining_seconds': e.remaining_seconds,
            }
            for e in expeditions.expeditions
        ],
        'active_count': expeditions.active_count,
        'idle_count': expeditions.idle_count,
    }


def serialize_build_queue(build_queue: Any) -> dict[str, Any]:
    """序列化 BuildQueue 对象。"""
    return {
        'slots': [
            {
                'occupied': s.occupied,
                'remaining_seconds': s.remaining_seconds,
                'is_complete': s.is_complete,
                'is_idle': s.is_idle,
            }
            for s in build_queue.slots
        ],
        'idle_count': build_queue.idle_count,
        'complete_count': build_queue.complete_count,
    }


def convert_combat_result(result: Any, round_num: int) -> dict[str, Any]:  # noqa: PLR0912
    """转换 CombatResult 为响应格式。"""
    nodes: list[str] = []
    mvp = None
    grade = None
    enemies_per_node: dict[str, dict[str, int]] = {}
    events: list[dict[str, Any]] = []

    if result.history:
        fight_results = result.history.get_fight_results()
        fight_results_iter = (
            fight_results.values()
            if isinstance(fight_results, dict)
            else fight_results
        )
        for fr in fight_results_iter:
            if fr.mvp and fr.mvp > 0 and mvp is None:
                mvp = f'位置{fr.mvp}'
            if fr.grade and grade is None:
                grade = fr.grade

        for event in result.history.events:
            if event.node and event.node not in nodes:
                nodes.append(event.node)
            ev: dict[str, Any] = {
                'type': event.event_type.name,
                'node': event.node,
                'action': event.action,
            }
            # 仅当 result 有有效值时写入：'' (空字符串) 和 None (未识别/默认值)
            # 都视为无有效结果。注意: 不能用 `if event.result:`, 字符串'0'也能通过。
            if event.result and event.result.strip():
                ev['result'] = event.result
            if event.enemies:
                ev['enemies'] = event.enemies
                if event.node:
                    enemies_per_node[event.node] = event.enemies
            if event.ship_stats:
                ev['ship_stats'] = [s.value for s in event.ship_stats]
            events.append(ev)

    return {
        'round': round_num,
        'success': result.flag.value == 'success',
        'dock_full_destroyed': bool(getattr(result, 'dock_full_destroyed', False)),
        'nodes': nodes,
        'mvp': mvp,
        'grade': grade,
        'ship_damage': [s.value for s in result.ship_stats] if result.ship_stats else [],
        'node_count': result.node_count,
        'enemies': enemies_per_node,
        'events': events,
    }


def build_combat_plan(request: Any) -> Any:
    """从请求构建 CombatPlan 对象。"""
    from autowsgr.combat import CombatPlan, NodeDecision
    from autowsgr.combat.plan import parse_map_value
    from autowsgr.types import RepairMode

    node_defaults = request.node_defaults.model_dump(exclude_none=True)

    def _build_node_decision(
        node_req: Any,
        *,
        defaults: dict[str, Any] | None = None,
    ) -> NodeDecision:
        data = {} if defaults is None else dict(defaults)
        data.update(
            node_req.model_dump(
                exclude_none=True,
                exclude_unset=defaults is not None,
            ),
        )
        return NodeDecision.from_dict(data)

    node_args = {
        k: _build_node_decision(v, defaults=node_defaults) for k, v in request.node_args.items()
    }
    map_id, entrance = parse_map_value(request.map)

    return CombatPlan(
        name=request.name,
        mode=request.mode,
        chapter=request.chapter,
        map_id=map_id,
        entrance=entrance,
        fleet_id=request.fleet_id,
        fleet=request.fleet,
        repair_mode=[RepairMode(r) for r in request.repair_mode],
        fight_condition=request.fight_condition,
        selected_nodes=request.selected_nodes,
        default_node=NodeDecision.from_dict(node_defaults),
        nodes=node_args,
        node_overrides={
            node: node_request.model_dump(exclude_unset=True)
            for node, node_request in request.node_args.items()
        },
        event_name=request.event_name,
    )


def _overlay_node_decision_data(base: Any, data: dict[str, Any]) -> Any:
    """把明确提供的节点字段覆盖到默认决策。"""
    from autowsgr.combat import NodeDecision

    normalized_data = dict(data)
    legacy_sl_key = 'sl_when_detour_fails'
    canonical_sl_key = 'SL_when_detour_fails'
    if legacy_sl_key in normalized_data:
        normalized_data.setdefault(canonical_sl_key, normalized_data[legacy_sl_key])
        del normalized_data[legacy_sl_key]

    parsed = NodeDecision.from_dict(
        {key: value for key, value in normalized_data.items() if value is not None},
    )
    result = copy.deepcopy(base)
    attribute_names = {'enemy_formation_rules': 'formation_rules'}
    for field_name, value in normalized_data.items():
        attribute_name = attribute_names.get(field_name, field_name)
        setattr(
            result,
            attribute_name,
            None if value is None else copy.deepcopy(getattr(parsed, attribute_name)),
        )
    return result


def _overlay_node_decision(base: Any, request: Any) -> Any:
    """把请求中明确提供的字段覆盖到默认决策。"""
    return _overlay_node_decision_data(
        base,
        request.model_dump(exclude_unset=True),
    )


def apply_combat_plan_overrides(
    plan: CombatPlan,
    request: CombatPlanRequest | None,
) -> CombatPlan:
    """把 API 中明确给出的节点配置应用到 YAML 计划。"""
    if request is None:
        return plan

    fields = request.model_fields_set
    if 'selected_nodes' in fields:
        plan.selected_nodes = list(request.selected_nodes)

    if 'node_defaults' in fields:
        from autowsgr.combat import NodeDecision

        plan.default_node = NodeDecision.from_dict(
            request.node_defaults.model_dump(exclude_none=True),
        )
        plan.nodes = {
            node: _overlay_node_decision_data(
                plan.default_node,
                plan.node_overrides.get(node, {}),
            )
            for node in plan.nodes
        }
        for node in plan.selected_nodes:
            plan.nodes.setdefault(node, copy.deepcopy(plan.default_node))

    if 'node_args' in fields:
        plan.node_overrides = {
            node: node_request.model_dump(exclude_unset=True)
            for node, node_request in request.node_args.items()
        }
        plan.nodes = {
            node: _overlay_node_decision(plan.default_node, node_request)
            for node, node_request in request.node_args.items()
        }
        for node in plan.selected_nodes:
            plan.nodes.setdefault(node, copy.deepcopy(plan.default_node))

    return plan


def build_fleet_selection(
    plan: CombatPlan,
    request_plan: CombatPlanRequest | None,
    *,
    fleet_id: int | None = None,
) -> ResolvedFleetSelection:
    """在 server 边界把 API 覆盖值转换成最终舰队选择。"""
    from autowsgr.combat.fleet import fleet_slot_from_api, resolve_fleet_selection

    request_rules = request_plan.fleet_rules if request_plan is not None else None
    slot_rules = (
        tuple(
            fleet_slot_from_api(
                rule if isinstance(rule, str) else rule.model_dump(exclude_none=True),
            )
            for rule in request_rules
        )
        if request_rules is not None
        else None
    )
    request_fleet_id = request_plan.fleet_id if request_plan is not None else None
    request_fleet = request_plan.fleet if request_plan is not None else None
    return resolve_fleet_selection(
        plan,
        fleet_id=fleet_id if fleet_id is not None else request_fleet_id,
        fleet=request_fleet,
        slot_rules=slot_rules,
    )
