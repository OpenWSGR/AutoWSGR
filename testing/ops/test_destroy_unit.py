"""destroy_ships_auto 模式调度单元测试 (无设备)。

验证 disable / include / exclude 三种工作模式 + remove_equipment 的派发逻辑。
通过 monkeypatch 拦截 ``destroy_ships``, 不触发真实导航 / IO。
"""

from __future__ import annotations

import pytest

from autowsgr.ops import destroy as destroy_module
from autowsgr.types import DestroyShipWorkMode, ShipType


class _FakeConfig:
    """最小 config 替身, 仅暴露 destroy 相关字段。"""

    def __init__(
        self,
        mode: DestroyShipWorkMode,
        types: list[ShipType] | None = None,
        remove_eq: bool = True,
    ) -> None:
        self.destroy_ship_work_mode = mode
        self.destroy_ship_types = types or []
        self.remove_equipment_mode = remove_eq


class _FakeCtx:
    def __init__(self, cfg: _FakeConfig) -> None:
        self.config = cfg


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """拦截 destroy_ships, 记录每次调用的参数。"""
    calls: list[dict] = []

    def _fake_destroy_ships(
        _ctx: object,
        *,
        ship_types: list[ShipType] | None = None,
        remove_equipment: bool = True,
    ) -> None:
        calls.append({'ship_types': ship_types, 'remove_equipment': remove_equipment})

    monkeypatch.setattr(destroy_module, 'destroy_ships', _fake_destroy_ships)
    return calls


def test_disable_skips_and_returns_false(recorded: list[dict]):
    from autowsgr.ops.destroy import destroy_ships_auto

    ctx = _FakeCtx(_FakeConfig(DestroyShipWorkMode.disable))
    assert destroy_ships_auto(ctx) is False
    assert recorded == []


def test_include_passes_listed_types(recorded: list[dict]):
    from autowsgr.ops.destroy import destroy_ships_auto

    types = [ShipType.DD, ShipType.CL]
    ctx = _FakeCtx(_FakeConfig(DestroyShipWorkMode.include, types=types, remove_eq=False))
    assert destroy_ships_auto(ctx) is True
    assert recorded == [{'ship_types': types, 'remove_equipment': False}]


def test_include_empty_types_means_all(recorded: list[dict]):
    """include + 空舰种列表 → ship_types=None (不过滤, 全量解装)。"""
    from autowsgr.ops.destroy import destroy_ships_auto

    ctx = _FakeCtx(_FakeConfig(DestroyShipWorkMode.include))
    assert destroy_ships_auto(ctx) is True
    assert recorded == [{'ship_types': None, 'remove_equipment': True}]


def test_exclude_computes_complement(recorded: list[dict]):
    """exclude (白名单): 解装除指定舰种外的所有非 Other 舰种。"""
    from autowsgr.ops.destroy import destroy_ships_auto

    protected = [ShipType.CV]
    ctx = _FakeCtx(_FakeConfig(DestroyShipWorkMode.exclude, types=protected))
    assert destroy_ships_auto(ctx) is True

    call = recorded[0]
    expected = {t for t in ShipType if t is not ShipType.Other and t not in set(protected)}
    assert set(call['ship_types']) == expected
    assert ShipType.CV not in call['ship_types']
    assert ShipType.Other not in call['ship_types']
    assert call['remove_equipment'] is True


def test_exclude_all_types_returns_false(recorded: list[dict]):
    """白名单覆盖全部非 Other 舰种 → 无可解装对象 → 返回 False。"""
    from autowsgr.ops.destroy import destroy_ships_auto

    all_real = [t for t in ShipType if t is not ShipType.Other]
    ctx = _FakeCtx(_FakeConfig(DestroyShipWorkMode.exclude, types=all_real))
    assert destroy_ships_auto(ctx) is False
    assert recorded == []
