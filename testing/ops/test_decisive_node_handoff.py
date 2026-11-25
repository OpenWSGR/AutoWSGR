"""按 6-2 E 战果至 F 出征的实机记录，验证战备、暂离、入浴与续战顺序。"""

from __future__ import annotations

import itertools
import time
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import numpy as np

from autowsgr.combat.history import CombatResult
from autowsgr.context import GameContext
from autowsgr.emulator.frame import CapturedFrame
from autowsgr.infra import DecisiveConfig, EmulatorConfig, UserConfig
from autowsgr.ops.decisive.controller import DecisiveController, DecisiveResult
from autowsgr.scheduler import TaskScheduler
from autowsgr.types import ConditionFlag, DecisiveEntryStatus, DecisivePhase, FleetSelection, OSType
from autowsgr.types import ShipDamageState as Damage
from autowsgr.ui.bath_page.page import RepairShipInfo
from autowsgr.ui.bath_page.signatures import SWIPE_DELAY


if TYPE_CHECKING:
    from collections.abc import Callable

    import pytest

    from autowsgr.combat.plan import CombatPlan


_E_FLEET = ['U-1405', 'U-1206', '351', 'U-2540', '鲃鱼', 'U-47']


def _stub_pages(
    ctrl: DecisiveController, monkeypatch: pytest.MonkeyPatch, events: list[str]
) -> None:
    def record(name: str, result: object = None) -> Callable[..., object]:
        def observed(*_args: object, **_kwargs: object) -> object:
            events.append(name)
            return result

        return observed

    sequence = itertools.count(1)
    screen = np.zeros((2, 2, 3), dtype=np.uint8)

    def capture() -> CapturedFrame:
        return CapturedFrame(screen, next(sequence), time.monotonic())

    ctrl._ctrl.capture_frame.side_effect = capture
    ctrl._map = map_page = MagicMock()
    map_page.is_stage_clear.return_value = False
    map_page.detect_decisive_phase.side_effect = [
        DecisivePhase.CHOOSE_FLEET,
        DecisivePhase.PREPARE_COMBAT,
        DecisivePhase.PREPARE_COMBAT,
    ]
    offer = FleetSelection('肌肉记忆', 3, (0.8, 0.5))
    map_page.recognize_fleet_options.return_value = (3, {offer.name: offer})
    map_page.buy_fleet_option.side_effect = record('购买肌肉记忆')
    map_page.close_fleet_overlay.side_effect = record('关闭战备', True)

    def stable_map() -> CapturedFrame:
        events.append('确认稳定地图')
        return capture()

    map_page.wait_for_stable_map_frame.side_effect = stable_map
    map_page.recognize_node.side_effect = record('识别 F', 'F')
    map_page.leave_to_overview.side_effect = record('暂离至总览')
    map_page.wait_for_entry_phase.return_value = DecisivePhase.PREPARE_COMBAT
    map_page.is_skill_used.side_effect = record('检查 F 技能', True)
    map_page.enter_formation.side_effect = record('打开 F 编队')
    ctrl._battle_page = overview = MagicMock()
    overview.detect_entry_status.return_value = DecisiveEntryStatus.CHALLENGING
    overview._read_chapter.return_value, overview.detect_stage.return_value = 6, 2
    overview.click_enter_map.side_effect = record('重进 6-2')
    monkeypatch.setattr('autowsgr.ops.navigate.goto_page', MagicMock())
    monkeypatch.setattr('autowsgr.ops.decisive.repair.goto_page', MagicMock())
    bath = MagicMock()
    bath.has_choose_repair_overlay.return_value = False
    card = RepairShipInfo('351', (0.3, 0.4), '00:12:18')
    bath.recognize_repair_ships.return_value = [card]
    bath.wait_repair_accepted.side_effect = record('确认 351 入浴', True)
    monkeypatch.setattr('autowsgr.ops.decisive.repair.BathPage', lambda _ctx: bath)

    fleet = _E_FLEET.copy()

    def snapshot(**_kwargs: bool) -> tuple[list[str], dict[int, Damage]]:
        return fleet.copy(), {
            i: Damage.REPAIRING if name == '351' else Damage.NORMAL for i, name in enumerate(fleet)
        }

    def swap(_fleet_id: int | None, target: list[str]) -> bool:
        assert target == [ship for ship in _E_FLEET if ship != '351'] + ['U-96']
        events.append('换入 U-96')
        fleet[:] = target
        return True

    map_page.check_fleet.side_effect = lambda _observer: (*snapshot(), {*_E_FLEET, 'U-96'})
    prep = MagicMock()
    prep.change_fleet.side_effect = swap
    prep.read_repair_snapshot.side_effect = snapshot
    prep.start_battle.side_effect = record('F 出征')
    monkeypatch.setattr(
        'autowsgr.ops.decisive.handlers.DecisiveBattlePreparationPage', lambda *_: prep
    )


def test_351_enters_bath_after_f_purchase_then_u96_sorties_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = UserConfig(
        emulator=EmulatorConfig(serial='local', path='/tmp/emulator'),
        os_type=OSType.linux,
        quick_repair_threshold_seconds=900,
        repair_manually=False,
    )
    ctx = GameContext(ctrl=MagicMock(), ocr=MagicMock(), config=config)
    ctrl = DecisiveController(ctx, DecisiveConfig(chapter=6, level1=_E_FLEET, level2=['U-96']))
    ctrl._scheduler = TaskScheduler(ctx, expedition_interval=0)
    ctrl.state.stage, ctrl.state.node, ctrl.state.phase = 2, 'E', DecisivePhase.IN_COMBAT
    ctrl.state.fleet, ctrl.state.ships = ['', *_E_FLEET], {*_E_FLEET, 'U-96'}
    ctrl._has_chosen_fleet = True
    events = []
    _stub_pages(ctrl, monkeypatch, events)

    # U-96 可以马上补位。调度器若误等 738 秒，应立即让本次测试失败。
    def wait(seconds: float) -> bool:
        assert seconds <= SWIPE_DELAY
        return False

    monkeypatch.setattr(ctx.stop_event, 'wait', wait)
    session = ctrl._ensure_tracking()
    session.map_ready(ctx.ctrl.capture_frame(), 'E')
    assert session.current_node == 'E'
    e_encounter = ctrl._battle_encounter_id = session.encounter_id
    health = [Damage.NORMAL] * 6

    def combat(plan: CombatPlan) -> CombatResult:
        if plan.name == '决战-2-E':
            events.append('E 战果 351 中破')
            return CombatResult(
                flag=ConditionFlag.OPERATION_SUCCESS,
                ship_stats=[*health[:2], Damage.MODERATE, *health[3:]],
            )
        assert plan.name == '决战-2-F'
        events.append('F 战斗')
        ctx.stop_event.set()
        return CombatResult(flag=ConditionFlag.OPERATION_SUCCESS, ship_stats=health)

    monkeypatch.setattr(ctrl, '_run_combat', combat)
    assert ctrl._main_loop() is DecisiveResult.STOPPED
    # 暂离前可能已经认出了 F，重进地图后仍要从新画面识别 F。
    left = events.index('暂离至总览')
    assert [event for event in events[:left] if event != '识别 F'] == [
        'E 战果 351 中破',
        '购买肌肉记忆',
        '关闭战备',
        '确认稳定地图',
    ]
    assert events[left:] == [
        '暂离至总览',
        '确认 351 入浴',
        '重进 6-2',
        '确认稳定地图',
        '识别 F',
        '检查 F 技能',
        '打开 F 编队',
        '换入 U-96',
        'F 出征',
        'F 战斗',
    ]
    assert session.completed_encounter(e_encounter).decision_node == 'E'
    assert ctrl._tracking is session
    ctrl._map.buy_fleet_option.assert_called_once_with((0.8, 0.5))
    ctx.ctrl.click.assert_called_once_with(0.3, 0.4)
    assert ctx.quick_repair_used == 0
