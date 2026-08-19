"""destroy_ships_auto 模式调度单元测试 (无设备)。

验证 disable / include / exclude 三种工作模式 + remove_equipment 的派发逻辑,
以及 ``from_dialog`` 弹窗直达路线 (点弹窗「解装」直达建造页后复用
destroy_ships)。通过 monkeypatch 拦截导航 / UI 层, 不触发真实 IO。
"""

from __future__ import annotations

import pytest

from autowsgr.ops import destroy as destroy_module
from autowsgr.ops.destroy import CLICK_DOCK_DIALOG_DESTROY
from autowsgr.types import DestroyShipWorkMode, PageName, ShipType


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
        self.ctrl = None


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


def test_disable_uses_quick_route_no_filter(recorded: list[dict]):
    """disable (不启用舰种分类): 不过滤, 走快速拆解路线, 解装全部。"""
    from autowsgr.ops.destroy import destroy_ships_auto

    ctx = _FakeCtx(_FakeConfig(DestroyShipWorkMode.disable))
    assert destroy_ships_auto(ctx) is True
    assert recorded == [{'ship_types': None, 'remove_equipment': True}]


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


# ─────────────────────────────────────────────
# from_dialog 弹窗直达路线
# ─────────────────────────────────────────────


class TestFromDialogDispatch:
    """destroy_ships_auto(from_dialog=True): 点弹窗「解装」直达, 再复用 destroy_ships。"""

    def test_from_dialog_clicks_dialog_then_reuses_destroy_ships(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        from autowsgr.ops.destroy import destroy_ships_auto

        calls: list[tuple] = []
        monkeypatch.setattr(
            destroy_module,
            'click_and_wait_for_page',
            lambda _ctrl, *, click_coord, source, target, **_k: calls.append(
                ('dialog', click_coord, source, target)
            ),
        )
        monkeypatch.setattr(
            destroy_module,
            'destroy_ships',
            lambda _ctx, *, ship_types, remove_equipment: calls.append(
                ('destroy', ship_types, remove_equipment)
            ),
        )

        types = [ShipType.DD, ShipType.CL]
        ctx = _FakeCtx(_FakeConfig(DestroyShipWorkMode.include, types=types, remove_eq=False))
        assert destroy_ships_auto(ctx, from_dialog=True) is True
        # 先点弹窗「解装」直达建造页, 再复用 destroy_ships (其 goto_page 幂等直达)
        assert calls == [
            ('dialog', CLICK_DOCK_DIALOG_DESTROY, '船坞满弹窗', PageName.BUILD),
            ('destroy', types, False),
        ]

    def test_default_skips_dialog_entry(self, monkeypatch: pytest.MonkeyPatch):
        """from_dialog=False (默认): 不点弹窗, 直接全局导航 destroy_ships。"""
        from autowsgr.ops.destroy import destroy_ships_auto

        calls: list[tuple] = []
        monkeypatch.setattr(
            destroy_module,
            'click_and_wait_for_page',
            lambda *_a, **_k: calls.append(('dialog',)),
        )
        monkeypatch.setattr(
            destroy_module,
            'destroy_ships',
            lambda *_a, **_k: calls.append(('destroy',)),
        )

        ctx = _FakeCtx(_FakeConfig(DestroyShipWorkMode.disable))
        assert destroy_ships_auto(ctx) is True
        assert calls == [('destroy',)]

    def test_from_dialog_exhausted_whitelist_skips_all(self, monkeypatch: pytest.MonkeyPatch):
        """白名单覆盖全部舰种 → 弹窗不点、解装不执行。"""
        from autowsgr.ops.destroy import destroy_ships_auto

        calls: list[tuple] = []
        monkeypatch.setattr(
            destroy_module,
            'click_and_wait_for_page',
            lambda *_a, **_k: calls.append(('dialog',)),
        )
        monkeypatch.setattr(
            destroy_module,
            'destroy_ships',
            lambda *_a, **_k: calls.append(('destroy',)),
        )

        all_real = [t for t in ShipType if t is not ShipType.Other]
        ctx = _FakeCtx(_FakeConfig(DestroyShipWorkMode.exclude, types=all_real))
        assert destroy_ships_auto(ctx, from_dialog=True) is False
        assert calls == []
