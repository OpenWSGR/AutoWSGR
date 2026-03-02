"""演习战斗操作。

TODO: 支持细化规则刷新对手
TODO: 支持细化阵形规则
TODO: 修船逻辑
涉及跨页面操作: 主页面 → 地图页面(演习面板) → 出征准备 → 战斗 → 演习页面。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from autowsgr.combat import CombatMode, CombatPlan, CombatResult, NodeDecision, run_combat
from autowsgr.infra.logger import get_logger
from autowsgr.ops.navigate import goto_page
from autowsgr.types import Formation, PageName, ShipDamageState
from autowsgr.ui import BattlePreparationPage, MapPage, MapPanel


if TYPE_CHECKING:
    from autowsgr.context import GameContext


_log = get_logger('ops')

# ═══════════════════════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════════════════════


class ExerciseRunner:
    """演习战斗执行器。"""

    def __init__(
        self,
        ctx: GameContext,
        fleet_id: int = 1,
    ) -> None:
        self._ctx = ctx
        self._ctrl = ctx.ctrl
        self._fleet_id = fleet_id
        self._results: list[CombatResult] = []

    # ── 公共接口 ──

    def run(self) -> list[CombatResult]:
        """执行完整的演习流程。

        Returns
        -------
        list[CombatResult]
            每次演习的战斗结果列表。
        """
        self._results = []
        _log.info('[OPS] 开始演习流程')

        # 1. 导航到演习面板
        self._enter_exercise_page()
        rivals_status = MapPage(self._ctx).get_exercise_rival_status()
        _log.info('[OPS] 当前可挑战对手: {}', rivals_status)
        for index, rival in enumerate(rivals_status.rivals, start=1):
            if rival:
                _log.info('[OPS] 正在挑战对手 {}', index)
                self._results.append(self._challenge_rival(index))
        _log.info('[OPS] 演习流程结束, 共完成 {} 场', len(self._results))
        return self._results

    # ── 导航 ──

    def _enter_exercise_page(self) -> None:
        """导航到地图页面的演习面板。"""
        goto_page(self._ctx, PageName.MAP)
        map_page = MapPage(self._ctx)
        map_page.switch_panel(MapPanel.EXERCISE)
        time.sleep(1.0)

    # ── 对手选择 ──

    def _challenge_rival(self, rival: int) -> CombatResult:
        """选择一个可挑战的对手。"""
        self._enter_exercise_page()
        if rival < 1 or rival > 5:
            raise ValueError(f'无效的对手索引: {rival} (应在 1–5 之间)')
        _log.info('[OPS] 选择对手 {}', rival)
        map_page = MapPage(self._ctx)
        map_page.select_exercise_rival(rival)
        map_page.enter_exercise_battle()
        ship_stats = self._prepare_for_battle()
        return self._do_combat(ship_stats)

    # ── 出征准备 ──

    def _prepare_for_battle(self) -> list[ShipDamageState]:
        """在出征准备页面执行舰队选择和修理。"""
        time.sleep(1.0)
        page = BattlePreparationPage(self._ctx)

        # 选择舰队
        page.select_fleet(self._fleet_id)
        time.sleep(0.5)

        screen = self._ctrl.screenshot()
        damage = page.detect_ship_damage(screen)
        ship_stats = [damage.get(i, ShipDamageState.NORMAL) for i in range(6)]

        # 出征
        page.start_battle()
        time.sleep(1.0)
        return ship_stats

    # ── 战斗 ──

    def _do_combat(self, ship_stats: list[ShipDamageState]) -> CombatResult:
        """构建 CombatPlan 并执行战斗。"""
        _log.debug('[OPS] 演习战斗开始')
        plan = CombatPlan(
            name='演习',
            mode=CombatMode.EXERCISE,
            default_node=NodeDecision(formation=Formation.single_column, night=True),
        )

        result = run_combat(
            self._ctx,
            plan,
            ship_stats=ship_stats,
        )
        _log.debug('[OPS] 演习战斗结束')
        return result


def run_exercise(
    ctx: GameContext,
    fleet_id: int = 1,
    rival: int | None = 1,
) -> list[CombatResult]:
    """执行演习的便捷函数。"""
    runner = ExerciseRunner(ctx, fleet_id)
    if rival is None:
        return runner.run()
    return [runner._challenge_rival(rival)]
