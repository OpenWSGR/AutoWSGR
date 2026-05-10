"""测试 autowsgr.server.serializers。"""

from __future__ import annotations

from unittest.mock import MagicMock

from autowsgr.context.build import BuildQueue, BuildSlot
from autowsgr.context.expedition import Expedition, ExpeditionQueue
from autowsgr.context.fleet import Fleet
from autowsgr.context.resources import Resources
from autowsgr.context.ship import Ship
from autowsgr.server.serializers import (
    build_combat_plan,
    convert_combat_result,
    serialize_build_queue,
    serialize_expedition_queue,
    serialize_fleet,
    serialize_resources,
    serialize_ship,
)
from autowsgr.types import ConditionFlag, ShipDamageState


def test_serialize_resources() -> None:
    """serialize_resources 应包含所有字段。"""
    res = Resources(fuel=1000, ammo=2000, fast_repair=5)
    data = serialize_resources(res)
    assert data['fuel'] == 1000
    assert data['ammo'] == 2000
    assert data['fast_repair'] == 5


def test_serialize_ship() -> None:
    """serialize_ship 应正确转换 Ship 字段。"""
    ship = Ship(name='弗莱彻', level=90, damage_state=ShipDamageState.NORMAL)
    data = serialize_ship(ship)
    assert data['name'] == '弗莱彻'
    assert data['level'] == 90
    assert data['damage_state'] == ShipDamageState.NORMAL.value
    assert data['ship_type'] is None


def test_serialize_fleet() -> None:
    """serialize_fleet 应包含舰队成员和统计。"""
    fleet = Fleet(fleet_id=2, ships=[Ship(name='Z1'), Ship(name='Z16')])
    data = serialize_fleet(fleet)
    assert data['fleet_id'] == 2
    assert data['size'] == 2
    assert len(data['ships']) == 2
    assert data['has_severely_damaged'] is False


def test_serialize_expedition_queue() -> None:
    """serialize_expedition_queue 应正确反映激活状态。"""
    queue = ExpeditionQueue(
        expeditions=[
            Expedition(chapter=1, node=1, fleet=Fleet(fleet_id=2)),
            Expedition(),
        ],
    )
    data = serialize_expedition_queue(queue)
    assert data['active_count'] == 1
    assert data['idle_count'] == 1
    assert data['slots'][0]['fleet_id'] == 2
    assert data['slots'][1]['fleet_id'] is None


def test_serialize_build_queue() -> None:
    """serialize_build_queue 应正确反映槽位状态。"""
    queue = BuildQueue(
        slots=[
            BuildSlot(occupied=True, remaining_seconds=0),
            BuildSlot(),
        ],
    )
    data = serialize_build_queue(queue)
    assert data['idle_count'] == 1
    assert data['complete_count'] == 1
    assert data['slots'][0]['is_complete'] is True
    assert data['slots'][1]['is_idle'] is True


def test_convert_combat_result() -> None:
    """convert_combat_result 应提取节点与战果。"""
    result = MagicMock()
    result.flag = ConditionFlag.OPERATION_SUCCESS
    result.ship_stats = [ShipDamageState.NORMAL] * 6
    result.node_count = 2
    result.history = None
    data = convert_combat_result(result, round_num=1)
    assert data['round'] == 1
    assert data['success'] is True
    assert data['node_count'] == 2


def test_build_combat_plan() -> None:
    """build_combat_plan 应从请求构造 CombatPlan。"""
    req = MagicMock()
    req.name = 'test'
    req.mode = 'normal'
    req.chapter = 5
    req.map = 4
    req.fleet_id = 1
    req.fleet = None
    req.repair_mode = [2, 2, 2, 2, 2, 2]
    req.fight_condition = 4
    req.selected_nodes = ['A', 'B']
    req.node_defaults = MagicMock()
    req.node_defaults.formation = 2
    req.node_defaults.night = False
    req.node_defaults.proceed = True
    req.node_defaults.proceed_stop = [2, 2, 2, 2, 2, 2]
    req.node_defaults.detour = False
    req.node_args = {}

    plan = build_combat_plan(req)
    assert plan.name == 'test'
    assert plan.chapter == 5
    assert plan.map_id == 4
