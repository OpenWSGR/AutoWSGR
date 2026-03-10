"""游戏对象序列化辅助函数。

将内部数据模型 (Resources, Fleet, Ship, ExpeditionQueue, BuildQueue, CombatResult)
转换为 JSON 可序列化的 dict，供 API 端点使用。
"""

from __future__ import annotations

from typing import Any


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


def convert_combat_result(result: Any, round_num: int) -> dict[str, Any]:
    """转换 CombatResult 为响应格式。"""
    nodes: list[str] = []
    mvp = None
    grade = None
    enemies_per_node: dict[str, dict[str, int]] = {}
    events: list[dict[str, Any]] = []

    if result.history:
        for event in result.history.events:
            if event.node and event.node not in nodes:
                nodes.append(event.node)

        fight_results = result.history.get_fight_results()
        if isinstance(fight_results, dict):
            for fr in fight_results.values():
                if fr.mvp and fr.mvp > 0 and mvp is None:
                    mvp = f'位置{fr.mvp}'
                if fr.grade and grade is None:
                    grade = fr.grade
        elif isinstance(fight_results, list):
            for fr in fight_results:
                if fr.mvp and fr.mvp > 0 and mvp is None:
                    mvp = f'位置{fr.mvp}'
                if fr.grade and grade is None:
                    grade = fr.grade

        for event in result.history.events:
            ev: dict[str, Any] = {
                'type': event.event_type.name,
                'node': event.node,
                'action': event.action,
            }
            if event.result:
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
    from autowsgr.types import Formation, RepairMode

    def _build_node_decision(node_req: Any) -> NodeDecision:
        return NodeDecision(
            formation=Formation(node_req.formation),
            night=node_req.night,
            proceed=node_req.proceed,
            proceed_stop=[RepairMode(r) for r in node_req.proceed_stop],
            detour=node_req.detour,
        )

    node_args = {k: _build_node_decision(v) for k, v in request.node_args.items()}

    return CombatPlan(
        name=request.name,
        mode=request.mode,
        chapter=request.chapter,
        map_id=request.map,
        fleet_id=request.fleet_id,
        fleet=request.fleet,
        repair_mode=[RepairMode(r) for r in request.repair_mode],
        fight_condition=request.fight_condition,
        selected_nodes=request.selected_nodes,
        default_node=_build_node_decision(request.node_defaults),
        nodes=node_args,
    )
