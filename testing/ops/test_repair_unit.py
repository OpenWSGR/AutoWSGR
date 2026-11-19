"""repair_one_available 循环派单单元测试 (无设备)。

回归: 浴室修理触发器每次产出应填满所有空闲槽, 而非只派一艘即返回。
用真实 :class:`BathRoom` 状态机验证循环终止 (occupy 填满 → is_available False),
死循环会直接卡住测试暴露问题。
"""

from __future__ import annotations

import types
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest

from autowsgr.context.bathroom import BathRoom
from autowsgr.context.game_context import GameContext
from autowsgr.types import ShipDamageState
from autowsgr.ui.bath_page import BathPage, RepairShipInfo


if TYPE_CHECKING:
    from collections.abc import Callable


# ── 替身 ──


class _FakeBathPage:
    """BathPage 替身: 按预设序列返回 repair_longest 结果。"""

    def __init__(self, results: list[int]) -> None:
        self._results = list(results)
        self.repair_longest_calls = 0
        self.go_to_choose_repair_calls = 0

    def go_to_choose_repair(self) -> None:
        self.go_to_choose_repair_calls += 1

    def repair_longest(
        self, *, blacklist: set[str], on_accepted: Callable[[str, int], None]
    ) -> int:
        self.repair_longest_calls += 1
        seconds = self._results.pop(0) if self._results else -1
        if seconds >= 0:
            name = f'舰船{self.repair_longest_calls}'
            assert name not in blacklist
            on_accepted(name, seconds)
        return seconds


class _FakeCtx:
    """最小 ctx 替身: 真实 bathroom 状态机 + bathroom_count 配置。"""

    def __init__(self, slot_count: int) -> None:
        self.bathroom = BathRoom(slot_count=slot_count)
        self.config = types.SimpleNamespace(bathroom_count=slot_count)
        self.ship_registry = {}
        self.ctrl = Mock()

    get_ship = GameContext.get_ship


def _patch_repair(monkeypatch: pytest.MonkeyPatch, fake_page: _FakeBathPage | BathPage) -> None:
    """把 repair 模块的设备依赖 (goto_page / BathPage / sleep) 替换为 no-op。"""
    import autowsgr.ops.repair as mod

    monkeypatch.setattr(mod, 'goto_page', lambda *_a, **_kw: None)
    monkeypatch.setattr(mod, 'BathPage', lambda _ctx: fake_page)
    monkeypatch.setattr(mod.time, 'sleep', lambda *_a, **_kw: None)
    monkeypatch.setattr(mod.time, 'time', lambda: 1000.0)


# ── 循环填满 ──


def test_fills_all_free_slots_then_stops(monkeypatch: pytest.MonkeyPatch):
    """两空闲槽 → 连续派修两艘, 槽填满后停止 (不死循环)。"""
    import autowsgr.ops.repair as mod

    fake = _FakeBathPage([100, 200])  # 两次都派单成功
    _patch_repair(monkeypatch, fake)

    ctx = _FakeCtx(slot_count=2)
    assert mod.repair_one_available(ctx) is True

    assert fake.repair_longest_calls == 2  # 恰好修 2 艘, 不是 1 也不是死循环
    assert fake.go_to_choose_repair_calls == 2  # 每艘都重开 overlay
    assert ctx.bathroom.is_available() is False  # 两槽全满
    assert ctx.bathroom.available_time == [1100.0, 1200.0]
    assert ctx.get_ship('舰船1').repair_end_time == 1100.0
    assert ctx.get_ship('舰船2').damage_state is ShipDamageState.REPAIRING


def test_partial_fill_then_no_candidates(monkeypatch: pytest.MonkeyPatch):
    """修一艘后剩余无可修候选 (secs==-1): 派 1 艘后停止, 仍留 1 空闲槽。"""
    import autowsgr.ops.repair as mod

    fake = _FakeBathPage([100, -1])
    _patch_repair(monkeypatch, fake)

    ctx = _FakeCtx(slot_count=2)
    assert mod.repair_one_available(ctx) is True  # 至少派了 1 艘

    assert fake.repair_longest_calls == 2  # 第 2 次返回 -1 触发停止
    assert ctx.bathroom.is_available() is True  # 仍有 1 空闲槽, 只是无船可修


def test_no_candidates_first_try(monkeypatch: pytest.MonkeyPatch):
    """首次即无可修候选 (secs==-1): 不占用任何槽, 返回 False。"""
    import autowsgr.ops.repair as mod

    fake = _FakeBathPage([-1])
    _patch_repair(monkeypatch, fake)

    ctx = _FakeCtx(slot_count=2)
    assert mod.repair_one_available(ctx) is False

    assert fake.repair_longest_calls == 1
    assert ctx.bathroom.is_available() is True  # 未占用


def test_bath_full_marks_unknown(monkeypatch: pytest.MonkeyPatch):
    """浴场满 (secs==-2): mark_unknown 退避, 返回 False。"""
    import autowsgr.ops.repair as mod

    fake = _FakeBathPage([-2])
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


@pytest.mark.parametrize('mode', ['具名', '空闲'])
@pytest.mark.parametrize(
    ('raw', 'accepted', 'registered'),
    [('00:12:18', True, 738), ('00:00:00', True, 0), ('', True, None), ('00:12:18', False, None)],
)
def test_registry_only_after_confirmed_quote(
    monkeypatch: pytest.MonkeyPatch, mode: str, raw: str, accepted: bool, registered: int | None
):
    """使用真实选船和入浴逻辑，核对点击、舰船记录和槽位时间。"""
    import autowsgr.ops.repair as mod

    ctx = _FakeCtx(slot_count=1)
    page = BathPage(ctx)
    monkeypatch.setattr(page, 'go_to_choose_repair', lambda: None)
    monkeypatch.setattr(BathPage, 'has_choose_repair_overlay', staticmethod(lambda _screen: True))
    card = RepairShipInfo('U-351', (0.3, 0.5), raw)
    monkeypatch.setattr(page, 'recognize_repair_ships', lambda: [card])
    monkeypatch.setattr(page, 'wait_repair_accepted', lambda: accepted)
    _patch_repair(monkeypatch, page)

    if mode == '空闲':
        assert mod.repair_one_available(ctx) is (registered is not None)
    elif not raw:
        with pytest.raises(ValueError, match=r'U-351.*时长'):
            mod.repair_ship_by_name(ctx, 'U-351')
    else:
        seconds = mod.repair_ship_by_name(ctx, 'U-351')
        assert seconds == (registered if registered is not None else -1)

    assert ctx.ctrl.click.call_count == bool(raw)
    if registered is None:
        assert not ctx.ship_registry
        assert ctx.bathroom.available_time is None
    else:
        ship = ctx.get_ship('U-351')
        assert ship.repair_end_time == 1000 + registered
        assert ship.damage_state is ShipDamageState.REPAIRING
        monkeypatch.setattr(mod.time, 'time', lambda: 2000.0)
        assert not ship.available
        assert ctx.bathroom.available_time == [1000 + registered if registered else 0.0]
