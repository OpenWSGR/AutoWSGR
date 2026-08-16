"""destroy_ships_auto 模式调度单元测试 (无设备)。

验证 disable / include / exclude 三种工作模式 + remove_equipment 的派发逻辑,
以及 ``from_dialog`` 弹窗直达路线的编排 (点弹窗按钮 → 解体标签 → 等待回
战斗准备页)。通过 monkeypatch 拦截导航 / UI 层, 不触发真实 IO。
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from autowsgr.ops import destroy as destroy_module
from autowsgr.ops.destroy import CLICK_DOCK_DIALOG_DESTROY, destroy_ships_from_dialog
from autowsgr.types import DestroyShipWorkMode, PageName, ShipType
from autowsgr.ui.build_page import BuildTab
from autowsgr.ui.utils import NavigationError


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
    """destroy_ships_auto(from_dialog=True) 派发到弹窗直达路线, 不走全局导航。"""

    def test_from_dialog_routes_to_dialog_entry(self, monkeypatch: pytest.MonkeyPatch):
        from autowsgr.ops.destroy import destroy_ships_auto

        calls: list[tuple] = []
        monkeypatch.setattr(
            destroy_module,
            'destroy_ships',
            lambda *_a, **_k: calls.append(('global',)),
        )
        monkeypatch.setattr(
            destroy_module,
            'destroy_ships_from_dialog',
            lambda _ctx, types, *, remove_equipment: calls.append(
                ('dialog', types, remove_equipment)
            ),
        )

        types = [ShipType.DD, ShipType.CL]
        ctx = _FakeCtx(_FakeConfig(DestroyShipWorkMode.include, types=types, remove_eq=False))
        assert destroy_ships_auto(ctx, from_dialog=True) is True
        # 只走弹窗直达, 参数透传
        assert calls == [('dialog', types, False)]

    def test_from_dialog_exhausted_whitelist_skips_route(self, monkeypatch: pytest.MonkeyPatch):
        """白名单覆盖全部舰种 → 不触发任何导航 (弹窗留在屏幕上)。"""
        from autowsgr.ops.destroy import destroy_ships_auto

        calls: list[tuple] = []
        monkeypatch.setattr(
            destroy_module,
            'destroy_ships_from_dialog',
            lambda *_a, **_k: calls.append(('dialog',)),
        )
        monkeypatch.setattr(
            destroy_module,
            'destroy_ships',
            lambda *_a, **_k: calls.append(('global',)),
        )

        all_real = [t for t in ShipType if t is not ShipType.Other]
        ctx = _FakeCtx(_FakeConfig(DestroyShipWorkMode.exclude, types=all_real))
        assert destroy_ships_auto(ctx, from_dialog=True) is False
        assert calls == []


class TestDestroyFromDialogRoute:
    """弹窗直达路线编排: 点弹窗「解装」→ 解体标签 → 解装 → 等回战斗准备页。"""

    def test_full_route(self, monkeypatch: pytest.MonkeyPatch):
        clicked: list[tuple] = []
        monkeypatch.setattr(
            destroy_module,
            'click_and_wait_for_page',
            lambda _ctrl, *, click_coord, source, target, **_k: clicked.append(
                (click_coord, source, target)
            ),
        )

        tabs: list[BuildTab] = []
        destroyed: list[tuple] = []
        page_fake = SimpleNamespace(
            switch_tab=tabs.append,
            destroy_ships=lambda types, *, remove_equipment: destroyed.append(
                (types, remove_equipment)
            ),
        )

        def _fake_build_cls(_ctx: object) -> SimpleNamespace:
            return page_fake

        _fake_build_cls.is_current_page = staticmethod(lambda _screen: True)  # type: ignore[attr-defined]
        monkeypatch.setattr(destroy_module, 'BuildPage', _fake_build_cls)

        waited: list[bool] = []
        monkeypatch.setattr(
            destroy_module, '_wait_battle_prep_return', lambda _ctx: waited.append(True)
        )

        ctx = _FakeCtx(_FakeConfig(DestroyShipWorkMode.disable))
        types = [ShipType.DD]
        destroy_ships_from_dialog(ctx, types, remove_equipment=True)

        # 点弹窗「解装」按钮等待建造页
        assert clicked == [(CLICK_DOCK_DIALOG_DESTROY, '船坞满弹窗', PageName.BUILD)]
        # 切到解体标签并执行解装
        assert tabs == [BuildTab.DESTROY]
        assert destroyed == [(types, True)]
        # 结束等待回战斗准备页 (不 goto_page 回主页)
        assert waited == [True]


class _FakeTime:
    """受控时钟: monotonic 每次调用 +1, sleep 只推进不睡眠。"""

    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        self.now += 1.0
        return self.now

    def sleep(self, _seconds: float) -> None:
        self.now += 0.5


class TestWaitBattlePrepReturn:
    """解装后返回战斗准备页: 自动返回 → 返回键兜底 → 超时抛错。"""

    @staticmethod
    def _make_ctx() -> tuple[SimpleNamespace, list[tuple[float, float]]]:
        """ctx 替身: screenshot 返回空帧 (NavigationError 存证需 ndarray), click 记录坐标。"""
        clicks: list[tuple[float, float]] = []
        ctrl = SimpleNamespace(
            screenshot=lambda: np.zeros((540, 960, 3), dtype=np.uint8),
            click=lambda x, y: clicks.append((x, y)),
        )
        return SimpleNamespace(ctrl=ctrl), clicks

    @staticmethod
    def _patch_prep(monkeypatch: pytest.MonkeyPatch, results: list[bool]) -> None:
        """is_current_page 按序消耗 results, 耗尽后恒 False。"""
        seq = list(results)
        monkeypatch.setattr(
            destroy_module,
            'BattlePreparationPage',
            SimpleNamespace(is_current_page=lambda _screen: seq.pop(0) if seq else False),
        )

    def test_auto_return_no_click(self, monkeypatch: pytest.MonkeyPatch):
        """解装完成游戏自动返回 → 不点返回键。"""
        monkeypatch.setattr(destroy_module, 'time', _FakeTime())
        ctx, clicks = self._make_ctx()
        self._patch_prep(monkeypatch, [False, True])

        destroy_module._wait_battle_prep_return(ctx)
        assert clicks == []

    def test_click_back_after_no_auto_return(self, monkeypatch: pytest.MonkeyPatch):
        """未自动返回 (超 6s) → 点建造页返回键 → 命中战斗准备页。"""
        monkeypatch.setattr(destroy_module, 'time', _FakeTime())
        ctx, clicks = self._make_ctx()
        # 未点返回键恒未到达, 点击后即命中 (不依赖精确轮询次数)
        monkeypatch.setattr(
            destroy_module,
            'BattlePreparationPage',
            SimpleNamespace(is_current_page=lambda _screen: bool(clicks)),
        )

        destroy_module._wait_battle_prep_return(ctx)
        assert clicks == [destroy_module.CLICK_BUILD_BACK]

    def test_timeout_raises(self, monkeypatch: pytest.MonkeyPatch):
        """两轮等待都未到达 → NavigationError。"""
        monkeypatch.setattr(destroy_module, 'time', _FakeTime())
        ctx, clicks = self._make_ctx()
        monkeypatch.setattr(
            destroy_module,
            'BattlePreparationPage',
            SimpleNamespace(is_current_page=lambda _screen: False),
        )

        with pytest.raises(NavigationError, match='战斗准备'):
            destroy_module._wait_battle_prep_return(ctx)
        assert clicks == [destroy_module.CLICK_BUILD_BACK]
