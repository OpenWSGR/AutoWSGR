"""测试 autowsgr.context.resources。"""

from __future__ import annotations

from autowsgr.context.resources import Resources


def test_resources_defaults() -> None:
    """Resources 默认值应全为 0。"""
    res = Resources()
    assert res.fuel == 0
    assert res.ammo == 0
    assert res.steel == 0
    assert res.aluminum == 0
    assert res.diamond == 0
    assert res.fast_repair == 0
    assert res.fast_build == 0
    assert res.ship_blueprint == 0
    assert res.equipment_blueprint == 0


def test_resources_basic_property() -> None:
    """basic 应返回四项基础资源的元组。"""
    res = Resources(fuel=1000, ammo=2000, steel=3000, aluminum=4000)
    assert res.basic == (1000, 2000, 3000, 4000)


def test_resources_custom_values() -> None:
    """应能正确存储非默认资源值。"""
    res = Resources(diamond=500, fast_repair=20, fast_build=10)
    assert res.diamond == 500
    assert res.fast_repair == 20
    assert res.fast_build == 10
