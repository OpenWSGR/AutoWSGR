"""测试 autowsgr.context.fleet。"""

from __future__ import annotations

from unittest.mock import MagicMock

from autowsgr.context.fleet import Fleet
from autowsgr.types import RepairMode, ShipDamageState


def test_fleet_defaults() -> None:
    """Fleet 默认应为空且编号为 1。"""
    fleet = Fleet()
    assert fleet.fleet_id == 1
    assert fleet.size == 0
    assert fleet.has_severely_damaged is False
    assert fleet.damage_states == []


def test_fleet_size_and_damage_states() -> None:
    """size 和 damage_states 应反映成员状态。"""
    s1 = MagicMock(damage_state=ShipDamageState.NORMAL)
    s2 = MagicMock(damage_state=ShipDamageState.MODERATE)
    fleet = Fleet(fleet_id=2, ships=[s1, s2])
    assert fleet.size == 2
    assert fleet.damage_states == [ShipDamageState.NORMAL, ShipDamageState.MODERATE]
    assert fleet.has_severely_damaged is False


def test_fleet_has_severely_damaged() -> None:
    """有大破成员时应返回 True。"""
    s1 = MagicMock(damage_state=ShipDamageState.NORMAL)
    s2 = MagicMock(damage_state=ShipDamageState.SEVERE)
    fleet = Fleet(ships=[s1, s2])
    assert fleet.has_severely_damaged is True


def test_fleet_needs_repair() -> None:
    """needs_repair 应按策略正确判断。"""
    s1 = MagicMock()
    s1.needs_repair.return_value = False
    s2 = MagicMock()
    s2.needs_repair.return_value = True
    fleet = Fleet(ships=[s1, s2])
    assert fleet.needs_repair(RepairMode.moderate_damage) is True
    s2.needs_repair.assert_called_once_with(RepairMode.moderate_damage)


def test_fleet_no_repair_needed() -> None:
    """所有成员均不需要修理时应返回 False。"""
    s1 = MagicMock(needs_repair=lambda _m: False)
    s2 = MagicMock(needs_repair=lambda _m: False)
    fleet = Fleet(ships=[s1, s2])
    assert fleet.needs_repair(RepairMode.severe_damage) is False
