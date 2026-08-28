"""repair_one_available 循环派单单元测试 (无设备)。

回归: 浴室修理触发器每次产出应填满所有空闲槽, 而非只派一艘即返回。
用真实 :class:`BathRoom` 状态机验证循环终止 (occupy 填满 → is_available False),
死循环会直接卡住测试暴露问题。
"""

from __future__ import annotations

import types
from typing import TYPE_CHECKING

from autowsgr.combat.history import CombatResult
from autowsgr.context import GameContext, Ship
from autowsgr.context.bathroom import BathRoom
from autowsgr.types import ConditionFlag, ShipDamageState


if TYPE_CHECKING:
    import pytest


# ── 替身 ──


class _FakeBathPage:
    """BathPage 替身: 按预设序列返回 repair_longest 结果。"""

    def __init__(self, results: list[tuple[str, int]]) -> None:
        self._results = list(results)
        self.repair_longest_calls = 0
        self.go_to_choose_repair_calls = 0

    def go_to_choose_repair(self) -> None:
        self.go_to_choose_repair_calls += 1

    def repair_longest(
        self,
        blacklist: set[str] | None = None,  # noqa: ARG002  # 签名匹配真实接口 (调用方按关键字传 blacklist=)
    ) -> tuple[str, int]:
        self.repair_longest_calls += 1
        return self._results.pop(0) if self._results else ('', -1)

    def click_repair_all(self) -> None:
        return None


class _FakeCtx:
    """最小 ctx 替身: 真实 bathroom 状态机 + bathroom_count 配置。"""

    def __init__(self, slot_count: int) -> None:
        self.bathroom = BathRoom(slot_count=slot_count)
        self.config = types.SimpleNamespace(bathroom_count=slot_count)
        self.ship_registry: dict[str, Ship] = {}

    def get_ship(self, name: str) -> Ship:
        if name not in self.ship_registry:
            self.ship_registry[name] = Ship(name=name)
        return self.ship_registry[name]

    def update_ship_damage(self, name: str, state: ShipDamageState) -> None:
        self.get_ship(name).damage_state = state


def _context_with_ship() -> tuple[GameContext, Ship, Ship]:
    ctx = GameContext(
        ctrl=object(),
        config=types.SimpleNamespace(bathroom_count=1),
        ocr=object(),
    )
    registry_ship = Ship(name='测试舰', damage_state=ShipDamageState.SEVERE)
    fleet_ship = Ship(name='测试舰', damage_state=ShipDamageState.SEVERE)
    ctx.ship_registry['测试舰'] = registry_ship
    ctx.fleets[0].ships = [fleet_ship]
    return ctx, registry_ship, fleet_ship


def _patch_repair(monkeypatch: pytest.MonkeyPatch, fake_page: _FakeBathPage) -> None:
    """把 repair 模块的设备依赖 (goto_page / BathPage / sleep) 替换为 no-op。"""
    import autowsgr.ops.repair as mod

    monkeypatch.setattr(mod, 'goto_page', lambda *_a, **_kw: None)
    monkeypatch.setattr(mod, 'BathPage', lambda _ctx: fake_page)
    monkeypatch.setattr(mod, 'time', types.SimpleNamespace(sleep=lambda *_a, **_kw: None))


# ── 循环填满 ──


def test_named_repair_syncs_fleet_damage_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    import autowsgr.ops.repair as mod

    class _NamedRepairPage:
        def go_to_choose_repair(self) -> None:
            return None

        def repair_ship(self, ship_name: str) -> int:
            assert ship_name == '测试舰'
            return 120

    monkeypatch.setattr(mod, 'goto_page', lambda *_a, **_kw: None)
    monkeypatch.setattr(mod, 'BathPage', lambda _ctx: _NamedRepairPage())

    ctx, registry_ship, fleet_ship = _context_with_ship()
    assert mod.repair_ship_by_name(ctx, '测试舰') == 120

    assert registry_ship.damage_state is ShipDamageState.NORMAL
    assert fleet_ship.damage_state is ShipDamageState.NORMAL
    assert registry_ship.repair_end_time > 0
    assert fleet_ship.repair_end_time == 0


def test_automatic_repair_syncs_known_ship_damage_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import autowsgr.ops.repair as mod

    fake = _FakeBathPage([('测试舰', 120)])
    _patch_repair(monkeypatch, fake)
    ctx, registry_ship, fleet_ship = _context_with_ship()

    assert mod.repair_one_available(ctx) is True

    assert registry_ship.damage_state is ShipDamageState.NORMAL
    assert fleet_ship.damage_state is ShipDamageState.NORMAL
    assert registry_ship.repair_end_time > 0
    assert fleet_ship.repair_end_time == 0


def test_batch_repair_does_not_guess_ship_state(monkeypatch: pytest.MonkeyPatch) -> None:
    import autowsgr.ops.repair as mod

    fake = _FakeBathPage([])
    _patch_repair(monkeypatch, fake)
    ctx, registry_ship, fleet_ship = _context_with_ship()

    assert mod.repair_in_bath(ctx) is None

    assert registry_ship.damage_state is ShipDamageState.SEVERE
    assert fleet_ship.damage_state is ShipDamageState.SEVERE
    assert registry_ship.repair_end_time == 0
    assert fleet_ship.repair_end_time == 0


def test_sync_after_combat_uses_shared_damage_sync() -> None:
    ctx, registry_ship, fleet_ship = _context_with_ship()
    duplicate_fleet_ship = Ship(name='测试舰', damage_state=ShipDamageState.SEVERE)
    ctx.fleets[1].ships = [duplicate_fleet_ship]

    ctx.sync_after_combat(
        1,
        CombatResult(
            flag=ConditionFlag.FIGHT_END,
            ship_stats=[ShipDamageState.NORMAL],
        ),
    )

    assert registry_ship.damage_state is ShipDamageState.NORMAL
    assert fleet_ship.damage_state is ShipDamageState.NORMAL
    assert duplicate_fleet_ship.damage_state is ShipDamageState.NORMAL


def test_sync_before_combat_uses_shared_damage_sync() -> None:
    ctx, registry_ship, _ = _context_with_ship()
    duplicate_fleet_ship = Ship(name='测试舰', damage_state=ShipDamageState.SEVERE)
    ctx.fleets[1].ships = [duplicate_fleet_ship]
    new_fleet_ship = Ship(name='测试舰', damage_state=ShipDamageState.NORMAL)

    ctx.sync_before_combat(1, [new_fleet_ship])

    assert registry_ship.damage_state is ShipDamageState.NORMAL
    assert new_fleet_ship.damage_state is ShipDamageState.NORMAL
    assert duplicate_fleet_ship.damage_state is ShipDamageState.NORMAL


def test_fills_all_free_slots_then_stops(monkeypatch: pytest.MonkeyPatch):
    """两空闲槽 → 连续派修两艘, 槽填满后停止 (不死循环)。"""
    import autowsgr.ops.repair as mod

    fake = _FakeBathPage([('测试舰1', 100), ('测试舰2', 200)])  # 两次都派单成功
    _patch_repair(monkeypatch, fake)

    ctx = _FakeCtx(slot_count=2)
    assert mod.repair_one_available(ctx) is True

    assert fake.repair_longest_calls == 2  # 恰好修 2 艘, 不是 1 也不是死循环
    assert fake.go_to_choose_repair_calls == 2  # 每艘都重开 overlay
    assert ctx.bathroom.is_available() is False  # 两槽全满


def test_partial_fill_then_no_candidates(monkeypatch: pytest.MonkeyPatch):
    """修一艘后剩余无可修候选 (secs==-1): 派 1 艘后停止, 仍留 1 空闲槽。"""
    import autowsgr.ops.repair as mod

    fake = _FakeBathPage([('测试舰', 100), ('', -1)])
    _patch_repair(monkeypatch, fake)

    ctx = _FakeCtx(slot_count=2)
    assert mod.repair_one_available(ctx) is True  # 至少派了 1 艘

    assert fake.repair_longest_calls == 2  # 第 2 次返回 -1 触发停止
    assert ctx.bathroom.is_available() is True  # 仍有 1 空闲槽, 只是无船可修


def test_no_candidates_first_try(monkeypatch: pytest.MonkeyPatch):
    """首次即无可修候选 (secs==-1): 不占用任何槽, 返回 False。"""
    import autowsgr.ops.repair as mod

    fake = _FakeBathPage([('', -1)])
    _patch_repair(monkeypatch, fake)

    ctx = _FakeCtx(slot_count=2)
    assert mod.repair_one_available(ctx) is False

    assert fake.repair_longest_calls == 1
    assert ctx.bathroom.is_available() is True  # 未占用


def test_bath_full_marks_unknown(monkeypatch: pytest.MonkeyPatch):
    """浴场满 (secs==-2): mark_unknown 退避, 返回 False。"""
    import autowsgr.ops.repair as mod

    fake = _FakeBathPage([('', -2)])
    _patch_repair(monkeypatch, fake)

    ctx = _FakeCtx(slot_count=2)
    assert mod.repair_one_available(ctx) is False

    assert ctx.bathroom.available_time is None  # mark_unknown → 强制下次重试


def test_skip_when_no_free_slot(monkeypatch: pytest.MonkeyPatch):
    """无空闲槽 → 直接返回, 不开 overlay (省一次截图)。"""
    import autowsgr.ops.repair as mod

    fake = _FakeBathPage([])  # 不应被调用
    _patch_repair(monkeypatch, fake)

    ctx = _FakeCtx(slot_count=1)
    ctx.bathroom.occupy(999)  # 占满唯一槽
    assert ctx.bathroom.is_available() is False

    assert mod.repair_one_available(ctx) is False
    assert fake.go_to_choose_repair_calls == 0  # 没开 overlay
