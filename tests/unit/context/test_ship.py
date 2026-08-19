"""测试 autowsgr.context.ship。"""

from __future__ import annotations

import time

from autowsgr.context.ship import Ship
from autowsgr.types import RepairMode, ShipDamageState


def test_ship_defaults() -> None:
    """Ship 默认值应符合预期。"""
    ship = Ship()
    assert ship.name == ''
    assert ship.level == 0
    assert ship.damage_state == ShipDamageState.NORMAL
    assert ship.health_ratio == 1.0


def test_health_ratio_known() -> None:
    """已知 max_health 时 health_ratio 应正确计算。"""
    ship = Ship(health=30, max_health=100)
    assert ship.health_ratio == 0.3


def test_health_ratio_zero_max() -> None:
    """max_health 为 0 时应返回 1.0。"""
    ship = Ship(health=0, max_health=0)
    assert ship.health_ratio == 1.0


def test_is_repairing_by_flag() -> None:
    """repairing=True 时应判定为修理中。"""
    ship = Ship(repairing=True)
    assert ship.is_repairing is True


def test_is_repairing_by_timestamp() -> None:
    """repair_end_time 在未来时应判定为修理中。"""
    ship = Ship(repair_end_time=time.time() + 3600)
    assert ship.is_repairing is True


def test_is_repairing_expired() -> None:
    """repair_end_time 已过期时不应判定为修理中。"""
    ship = Ship(repair_end_time=time.time() - 1)
    assert ship.is_repairing is False


def test_available_severe_damage() -> None:
    """大破时不可用。"""
    ship = Ship(damage_state=ShipDamageState.SEVERE)
    assert ship.available is False


def test_available_repairing() -> None:
    """修理中时不可用。"""
    ship = Ship(repairing=True, damage_state=ShipDamageState.NORMAL)
    assert ship.available is False


def test_set_repair() -> None:
    """set_repair 应设置结束时间并恢复状态。"""
    ship = Ship(damage_state=ShipDamageState.MODERATE)
    ship.set_repair(600)
    assert ship.damage_state == ShipDamageState.NORMAL
    assert ship.repair_end_time > time.time()


def test_needs_repair_moderate() -> None:
    """moderate_damage 策略应对中破和大破返回 True。"""
    ship_mod = Ship(damage_state=ShipDamageState.MODERATE)
    ship_sev = Ship(damage_state=ShipDamageState.SEVERE)
    ship_norm = Ship(damage_state=ShipDamageState.NORMAL)
    assert ship_mod.needs_repair(RepairMode.moderate_damage) is True
    assert ship_sev.needs_repair(RepairMode.moderate_damage) is True
    assert ship_norm.needs_repair(RepairMode.moderate_damage) is False


def test_needs_repair_severe_only() -> None:
    """severe_damage 策略仅对大破返回 True。"""
    ship_mod = Ship(damage_state=ShipDamageState.MODERATE)
    ship_sev = Ship(damage_state=ShipDamageState.SEVERE)
    assert ship_mod.needs_repair(RepairMode.severe_damage) is False
    assert ship_sev.needs_repair(RepairMode.severe_damage) is True


def test_needs_repair_while_repairing() -> None:
    """正在修理中时 needs_repair 应返回 False。"""
    ship = Ship(damage_state=ShipDamageState.SEVERE, repairing=True)
    assert ship.needs_repair(RepairMode.severe_damage) is False
