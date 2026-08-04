"""NormalFightRunner event/normal 融合分支单元测试。

不依赖实机: 用轻量 mock ctx 验证 ``plan.chapter`` (E/H vs 数字) → 导航分支的
路由逻辑 (event 走活动地图, normal 走常规出征面板)。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

import autowsgr.ops.normal_fight as normal_fight_module
from autowsgr.combat import CombatMode, CombatPlan, CombatResult
from autowsgr.combat.fleet import (
    FleetSelectionSource,
    FleetSlotRule,
    ShipSelector,
    exact_fleet_rules,
    resolve_fleet_selection,
)
from autowsgr.infra import ActionFailedError
from autowsgr.ops.normal_fight import NormalFightRunner, _require_fleet_change
from autowsgr.types import ShipDamageState, ShipType
from autowsgr.ui.battle.fleet_change._detect import FleetSnapshot


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


class TestFleetPresetRules:
    def test_plan_preset_is_used_without_api_override(self):
        ships = [
            {
                'name': 'U-47',
                'candidates': [{'name': 'U-96'}],
            },
        ]
        plan = CombatPlan.from_dict(
            {
                'fleet_presets': [
                    {
                        'name': '潜艇队',
                        'ships': ships,
                    },
                ],
            },
        )

        selection = resolve_fleet_selection(plan)
        runner = NormalFightRunner(_make_ctx(), plan, selection)

        assert runner._fleet_selection is selection
        assert selection.source is FleetSelectionSource.PLAN_PRESET
        assert selection.slot_rules is not None
        assert selection.slot_rules[0].primary == ShipSelector(name='U-47')
        assert selection.primary_names == ['U-47']

    def test_api_rules_override_plan_preset(self):
        plan = CombatPlan.from_dict(
            {
                'fleet_presets': [
                    {
                        'name': '计划编队',
                        'ships': [{'name': 'U-47'}],
                    },
                ],
            },
        )
        override = (FleetSlotRule(primary=ShipSelector(name='岛风')),)
        selection = resolve_fleet_selection(plan, slot_rules=override)

        runner = NormalFightRunner(_make_ctx(), plan, selection)

        assert runner._fleet_selection.slot_rules == override
        assert runner._fleet_selection.source is FleetSelectionSource.OVERRIDE_RULES

    def test_candidate_only_slot_has_no_fixed_primary_name(self):
        rules = (
            FleetSlotRule(
                candidates=(
                    ShipSelector(name='胡德', relaxed_constraints=True),
                    ShipSelector(name='扶桑', relaxed_constraints=True),
                ),
            ),
        )
        selection = resolve_fleet_selection(
            CombatPlan(),
            slot_rules=rules,
        )

        assert selection.primary_names == [None]

    @pytest.mark.parametrize(
        ('fleet', 'slot_rules', 'expected_source'),
        [
            (['岛风'], None, FleetSelectionSource.OVERRIDE_FLEET),
            (
                ['岛风'],
                (FleetSlotRule(primary=ShipSelector(name='雪风')),),
                FleetSelectionSource.OVERRIDE_RULES,
            ),
        ],
    )
    def test_override_priority_is_centralized(
        self,
        fleet: list[str],
        slot_rules: tuple[FleetSlotRule, ...] | None,
        expected_source: FleetSelectionSource,
    ):
        plan = CombatPlan.from_dict(
            {
                'fleet': ['飞龙'],
                'fleet_presets': [{'ships': [{'name': 'U-47'}]}],
            },
        )

        selection = resolve_fleet_selection(
            plan,
            fleet=fleet,
            slot_rules=slot_rules,
        )

        assert selection.source is expected_source

    def test_plan_preset_has_priority_over_plain_plan_fleet(self):
        plan = CombatPlan.from_dict(
            {
                'fleet': ['飞龙'],
                'fleet_presets': [{'ships': [{'name': 'U-47'}]}],
            },
        )

        selection = resolve_fleet_selection(plan)

        assert selection.source is FleetSelectionSource.PLAN_PRESET


class _FleetInfo:
    def __init__(self) -> None:
        self.ship_damage: dict[int, ShipDamageState] = {}

    @staticmethod
    def to_ships(_names: list[str | None] | None) -> list[object]:
        return []


class _BattlePreparationPage:
    def __init__(self) -> None:
        self.changed_fleet_id: int | None = None
        self.changed_rules: tuple[FleetSlotRule, ...] | None = None
        self.last_changed_fleet: list[str | None] | None = ['导巡测试舰']

    @staticmethod
    def select_fleet(_fleet_id: int) -> None:
        return None

    def change_fleet(
        self,
        fleet_id: int,
        rules: tuple[FleetSlotRule, ...],
    ) -> bool:
        self.changed_fleet_id = fleet_id
        self.changed_rules = rules
        return True

    @staticmethod
    def detect_fleet() -> list[str]:
        raise AssertionError('runner 不应在换船成功后重复识别舰队')

    @staticmethod
    def apply_supply() -> None:
        return None

    @staticmethod
    def apply_repair(_strategy: object) -> None:
        return None

    @staticmethod
    def detect_fleet_info() -> _FleetInfo:
        return _FleetInfo()

    @staticmethod
    def start_battle() -> None:
        return None


class TestFleetSelectionCallChain:
    def test_runner_constructor_keeps_legacy_fleet_arguments(self):
        plan = CombatPlan.from_dict({'fleet': ['岛风']})
        runner = NormalFightRunner(_make_ctx(), plan, fleet_id=2)

        assert runner._fleet_id == 2
        assert runner._fleet_selection.plain_fleet == ('岛风',)

    def test_event_runner_constructor_keeps_legacy_fleet_arguments(self):
        from autowsgr.ops.event_fight import EventFightRunner

        plan = CombatPlan.from_dict({'chapter': 'H', 'map': '1a', 'fleet': ['岛风']})
        runner = EventFightRunner(_make_ctx(), plan, fleet_id=2)

        assert runner._fleet_id == 2
        assert runner._fleet_selection.plain_fleet == ('岛风',)

    def _prepare(
        self,
        monkeypatch: pytest.MonkeyPatch,
        plan: CombatPlan,
    ) -> tuple[object, _BattlePreparationPage]:
        selection = resolve_fleet_selection(plan)
        page = _BattlePreparationPage()
        monkeypatch.setattr(
            normal_fight_module,
            'BattlePreparationPage',
            lambda _ctx: page,
        )
        monkeypatch.setattr(normal_fight_module.time, 'sleep', lambda _seconds: None)

        runner = NormalFightRunner(_make_ctx(), plan, selection)
        runner._prepare_for_battle()
        return selection, page

    def test_yaml_preset_rules_reach_battle_preparation_unchanged(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        plan = CombatPlan.from_dict(
            {
                'fleet_id': 4,
                'fleet': ['被预设覆盖的舰船'],
                'fleet_presets': [
                    {
                        'ships': [
                            {
                                'name': '导巡测试舰',
                                'ship_type': ['kp'],
                                'min_level': 90,
                            },
                        ],
                    },
                ],
            },
        )

        selection, page = self._prepare(monkeypatch, plan)

        assert selection.source is FleetSelectionSource.PLAN_PRESET
        assert selection.slot_rules is not None
        assert page.changed_fleet_id == 4
        assert page.changed_rules is selection.slot_rules
        assert page.changed_rules[0].primary == ShipSelector(
            name='导巡测试舰',
            ship_types=(ShipType.KP,),
            min_level=90,
        )

    def test_plain_plan_fleet_is_converted_once_at_battle_preparation(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        plan = CombatPlan.from_dict(
            {
                'fleet_id': 2,
                'fleet': ['岛风', '雪风'],
            },
        )

        selection, page = self._prepare(monkeypatch, plan)

        assert selection.source is FleetSelectionSource.PLAN_FLEET
        assert page.changed_fleet_id == 2
        assert page.changed_rules == exact_fleet_rules(['岛风', '雪风'])

    def test_real_runner_reaches_fleet_change_and_choose_ship_boundary(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Runner uses the real fleet orchestration before the battle boundary."""
        from autowsgr.ui.battle.preparation import BattlePreparationPage

        ctrl = MagicMock()
        ctrl.screenshot.return_value = np.zeros((100, 100, 3), dtype=np.uint8)
        ctx = SimpleNamespace(
            ctrl=ctrl,
            config=SimpleNamespace(dock_full_destroy=False, destroy_ship_types=None),
            ocr=MagicMock(),
            sync_before_combat=MagicMock(),
            sync_after_combat=MagicMock(),
        )
        page = BattlePreparationPage(ctx)
        monkeypatch.setattr(normal_fight_module, 'BattlePreparationPage', lambda _ctx: page)

        class FakeChooseShipPage:
            def change_single_ship(
                self,
                selector: ShipSelector | None,
                *,
                use_search: bool,
            ) -> str | None:
                assert use_search is True
                return selector.name if selector is not None else None

        empty_snapshot = FleetSnapshot(
            names=[None] * 6,
            occupied=[False] * 6,
        )
        target_snapshot = FleetSnapshot(
            names=['导巡测试舰', None, None, None, None, None],
            occupied=[True, False, False, False, False, False],
        )
        snapshots = iter([empty_snapshot, target_snapshot, target_snapshot, target_snapshot])
        monkeypatch.setattr(BattlePreparationPage, 'get_selected_fleet', lambda _self, _screen: 4)
        monkeypatch.setattr(
            page,
            '_detect_initial_snapshot',
            lambda _pool: next(snapshots),
        )
        monkeypatch.setattr(page, 'detect_fleet_snapshot', lambda **_kwargs: next(snapshots))
        monkeypatch.setattr(page, 'detect_ship_damage', lambda _screen: {})
        monkeypatch.setattr(page, 'apply_supply', lambda: None)
        monkeypatch.setattr(page, 'apply_repair', lambda _strategy: None)
        monkeypatch.setattr(page, 'detect_fleet_info', _FleetInfo)
        monkeypatch.setattr(page, 'start_battle', MagicMock())
        monkeypatch.setattr(page, '_open_choose_page', lambda _slot: FakeChooseShipPage())
        monkeypatch.setattr(normal_fight_module.time, 'sleep', lambda _seconds: None)

        plan = CombatPlan.from_dict(
            {
                'fleet_id': 4,
                'fleet_presets': [{'ships': [{'name': '导巡测试舰'}]}],
            },
        )
        runner = NormalFightRunner(ctx, plan, resolve_fleet_selection(plan))
        monkeypatch.setattr(runner, '_enter_fight', lambda: None)
        monkeypatch.setattr(runner, '_do_combat', lambda _stats: CombatResult())
        monkeypatch.setattr(runner, '_handle_result', lambda _result: None)

        runner.run()

        page.start_battle.assert_called_once()


class TestEventNormalMerge:
    """chapter (E/H vs 数字) 决定导航分支与 plan.mode。"""

    def test_event_branch_hard(self):
        plan = CombatPlan.from_dict({'event': '20260730', 'chapter': 'H', 'map': '1a'})
        runner = NormalFightRunner(_make_ctx(), plan, resolve_fleet_selection(plan))
        assert runner._is_event is True
        assert plan.mode == CombatMode.EVENT
        assert runner._map_code == 'H1'
        assert runner._entrance == 'alpha'

    def test_event_branch_easy(self):
        plan = CombatPlan.from_dict({'event': '20260730', 'chapter': 'E', 'map': '3b'})
        runner = NormalFightRunner(_make_ctx(), plan, resolve_fleet_selection(plan))
        assert runner._is_event is True
        assert runner._map_code == 'E3'
        assert runner._entrance == 'beta'

    def test_event_no_entrance(self):
        plan = CombatPlan.from_dict({'event': '20260212', 'chapter': 'H', 'map': 5})
        runner = NormalFightRunner(_make_ctx(), plan, resolve_fleet_selection(plan))
        assert runner._is_event is True
        assert runner._entrance is None
        assert runner._map_code == 'H5'

    def test_normal_branch(self):
        plan = CombatPlan.from_dict({'chapter': 2, 'map': 1})
        runner = NormalFightRunner(_make_ctx(), plan, resolve_fleet_selection(plan))
        assert runner._is_event is False
        assert plan.mode == CombatMode.NORMAL
        assert runner._entrance is None
        assert runner._map_code == ''


class TestEventFightRunnerCompat:
    """EventFightRunner 兼容薄包装委托 NormalFightRunner。"""

    def test_inherits_normal_runner(self):
        from autowsgr.ops.event_fight import EventFightRunner

        plan = CombatPlan.from_dict({'event': '20260730', 'chapter': 'H', 'map': '1a'})
        runner = EventFightRunner(_make_ctx(), plan, resolve_fleet_selection(plan))
        assert isinstance(runner, NormalFightRunner)
        assert runner._is_event is True
        assert runner._map_code == 'H1'

    def test_entrance_override(self):
        from autowsgr.ops.event_fight import EventFightRunner

        plan = CombatPlan.from_dict({'event': '20260730', 'chapter': 'H', 'map': '1a'})
        runner = EventFightRunner(
            _make_ctx(),
            plan,
            resolve_fleet_selection(plan),
            entrance='beta',
        )
        # override 回填 plan.entrance (alpha→'a', beta→'b')
        assert plan.entrance == 'b'
        assert runner._entrance == 'beta'
