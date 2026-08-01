"""NormalFightRunner event/normal 融合分支单元测试。

不依赖实机: 用轻量 mock ctx 验证 ``plan.chapter`` (E/H vs 数字) → 导航分支的
路由逻辑 (event 走活动地图, normal 走常规出征面板)。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from autowsgr.combat import CombatMode, CombatPlan
from autowsgr.infra import ActionFailedError
from autowsgr.ops.normal_fight import NormalFightRunner, _require_fleet_change


def _make_ctx() -> SimpleNamespace:
    """构造满足 NormalFightRunner.__init__ 的最小 ctx mock。

    构造期仅访问 ``ctx.ctrl`` (存引用) 与 ``ctx.config`` 的两个拆船字段,
    不触发任何实机操作。
    """

    cfg = SimpleNamespace(dock_full_destroy=False, destroy_ship_types=None)
    return SimpleNamespace(ctrl=None, config=cfg)


class TestFleetChangeResult:
    def test_success_continues(self):
        _require_fleet_change(True, 'fleet')

    def test_failure_stops_fight(self):
        with pytest.raises(ActionFailedError, match='fleet 编队失败'):
            _require_fleet_change(False, 'fleet')


class TestEventNormalMerge:
    """chapter (E/H vs 数字) 决定导航分支与 plan.mode。"""

    def test_event_branch_hard(self):
        plan = CombatPlan.from_dict({'event': '20260730', 'chapter': 'H', 'map': '1a'})
        runner = NormalFightRunner(_make_ctx(), plan)
        assert runner._is_event is True
        assert plan.mode == CombatMode.EVENT
        assert runner._map_code == 'H1'
        assert runner._entrance == 'alpha'

    def test_event_branch_easy(self):
        plan = CombatPlan.from_dict({'event': '20260730', 'chapter': 'E', 'map': '3b'})
        runner = NormalFightRunner(_make_ctx(), plan)
        assert runner._is_event is True
        assert runner._map_code == 'E3'
        assert runner._entrance == 'beta'

    def test_event_no_entrance(self):
        plan = CombatPlan.from_dict({'event': '20260212', 'chapter': 'H', 'map': 5})
        runner = NormalFightRunner(_make_ctx(), plan)
        assert runner._is_event is True
        assert runner._entrance is None
        assert runner._map_code == 'H5'

    def test_normal_branch(self):
        plan = CombatPlan.from_dict({'chapter': 2, 'map': 1})
        runner = NormalFightRunner(_make_ctx(), plan)
        assert runner._is_event is False
        assert plan.mode == CombatMode.NORMAL
        assert runner._entrance is None
        assert runner._map_code == ''


class TestEventFightRunnerCompat:
    """EventFightRunner 兼容薄包装委托 NormalFightRunner。"""

    def test_inherits_normal_runner(self):
        from autowsgr.ops.event_fight import EventFightRunner

        plan = CombatPlan.from_dict({'event': '20260730', 'chapter': 'H', 'map': '1a'})
        runner = EventFightRunner(_make_ctx(), plan)
        assert isinstance(runner, NormalFightRunner)
        assert runner._is_event is True
        assert runner._map_code == 'H1'

    def test_entrance_override(self):
        from autowsgr.ops.event_fight import EventFightRunner

        plan = CombatPlan.from_dict({'event': '20260730', 'chapter': 'H', 'map': '1a'})
        runner = EventFightRunner(_make_ctx(), plan, entrance='beta')
        # override 回填 plan.entrance (alpha→'a', beta→'b')
        assert plan.entrance == 'b'
        assert runner._entrance == 'beta'
