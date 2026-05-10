"""测试 autowsgr.context.game_context。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from autowsgr.context.game_context import GameContext
from autowsgr.context.ship import Ship
from autowsgr.types import ConditionFlag, ShipDamageState


def _make_ctx() -> GameContext:
    """构造一个使用 Mock 基础设施的 GameContext。"""
    return GameContext(ctrl=MagicMock(), config=MagicMock())


def test_fleet_accessor_valid() -> None:
    """fleet() 应返回对应编号的舰队。"""
    ctx = _make_ctx()
    assert ctx.fleet(1).fleet_id == 1
    assert ctx.fleet(4).fleet_id == 4


def test_fleet_accessor_invalid() -> None:
    """fleet() 传入非法编号应抛出 ValueError。"""
    ctx = _make_ctx()
    with pytest.raises(ValueError, match='fleet_id 应在 1-4 范围内'):
        ctx.fleet(0)
    with pytest.raises(ValueError, match='fleet_id 应在 1-4 范围内'):
        ctx.fleet(5)


def test_get_ship_auto_register() -> None:
    """get_ship 应自动注册不存在的舰船。"""
    ctx = _make_ctx()
    ship = ctx.get_ship('俾斯麦')
    assert ship.name == '俾斯麦'
    assert '俾斯麦' in ctx.ship_registry


def test_is_ship_available() -> None:
    """is_ship_available 应反映舰船可用状态。"""
    ctx = _make_ctx()
    ship = ctx.get_ship('空想')
    ship.damage_state = ShipDamageState.NORMAL
    ship.repairing = False
    assert ctx.is_ship_available('空想') is True

    ship.damage_state = ShipDamageState.SEVERE
    assert ctx.is_ship_available('空想') is False


def test_update_ship_damage() -> None:
    """update_ship_damage 应同步更新注册表中的状态。"""
    ctx = _make_ctx()
    ctx.update_ship_damage('黎塞留', ShipDamageState.MODERATE)
    assert ctx.get_ship('黎塞留').damage_state == ShipDamageState.MODERATE


def test_sync_before_combat() -> None:
    """sync_before_combat 应同步舰队成员与每日计数器。"""
    ctx = _make_ctx()
    ships = [Ship(name='Z1', level=80), Ship(name='Z16', level=75)]
    ctx.sync_before_combat(
        fleet_id=1,
        ships=ships,
        loot_count=10,
        ship_acquired_count=3,
    )
    assert ctx.fleet(1).ships == ships
    assert ctx.dropped_loot_count == 10
    assert ctx.dropped_ship_count == 3
    assert ctx.get_ship('Z1').level == 80


def test_sync_after_combat_updates_damage() -> None:
    """sync_after_combat 应更新舰队战后血量。"""
    ctx = _make_ctx()
    ctx.fleet(1).ships = [Ship(name='A'), Ship(name='B')]
    result = MagicMock()
    result.flag = ConditionFlag.OPERATION_SUCCESS
    result.ship_stats = [ShipDamageState.MODERATE, ShipDamageState.NORMAL]
    result.fight_results = []
    ctx.sync_after_combat(1, result)
    assert ctx.fleet(1).ships[0].damage_state == ShipDamageState.MODERATE
    assert ctx.get_ship('A').damage_state == ShipDamageState.MODERATE
