"""测试 autowsgr.context.equipment。"""

from __future__ import annotations

from autowsgr.context.equipment import Equipment


def test_equipment_defaults() -> None:
    """Equipment 默认值应为空名称且未锁定。"""
    eq = Equipment()
    assert eq.name == ''
    assert eq.locked is False


def test_equipment_with_name() -> None:
    """应能正确存储装备名称。"""
    eq = Equipment(name='12.7cm连装炮')
    assert eq.name == '12.7cm连装炮'


def test_equipment_locked() -> None:
    """锁定状态应被正确记录。"""
    eq = Equipment(name='61cm四连装鱼雷', locked=True)
    assert eq.locked is True
