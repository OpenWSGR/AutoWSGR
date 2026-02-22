"""演习战斗操作。

TODO: 支持细化规则刷新对手
TODO: 支持细化阵形规则
TODO: 修船逻辑
涉及跨页面操作: 主页面 → 地图页面(演习面板) → 出征准备 → 战斗 → 演习页面。
"""

from __future__ import annotations

import time

from loguru import logger

from autowsgr.combat import CombatResult, run_combat, CombatMode, CombatPlan, NodeDecision
from autowsgr.infra import ExerciseConfig
from autowsgr.ops.navigate import goto_page
from autowsgr.types import ConditionFlag, Formation, PageName, RepairMode
from autowsgr.ui import BattlePreparationPage, RepairStrategy, MapPage, MapPanel
from autowsgr.emulator import AndroidController


# ═══════════════════════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════════════════════


class ExerciseRunner:
    """演习战斗执行器。"""

    def __init__(
        self,
        ctrl: AndroidController,
        fleet_id: int = 1,
    ) -> None:
        self._ctrl = ctrl
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

        # 1. 导航到演习面板
        self._enter_exercise_page()
        rivals_status = MapPage(self._ctrl).get_exercise_rival_status()
        logger.info("[OPS] 当前可挑战对手: {}", rivals_status)
        for index, rival in enumerate(rivals_status.rivals, start=1):
            if rival:
                logger.info("[OPS] 正在挑战对手 {}", index)
                self._results.append(self._challenge_rival(index))
        return self._results


    # ── 导航 ──

    def _enter_exercise_page(self) -> None:
        """导航到地图页面的演习面板。"""
        goto_page(self._ctrl, PageName.MAP)
        map_page = MapPage(self._ctrl)
        map_page.switch_panel(MapPanel.EXERCISE)
        time.sleep(1.0)

    # ── 对手选择 ──
    
    def _challenge_rival(self, rival: int) -> CombatResult:
        """选择一个可挑战的对手。"""
        self._enter_exercise_page()
        if rival < 1 or rival > 5:
            raise ValueError(f"无效的对手索引: {rival} (应在 1–5 之间)")
        logger.info("[OPS] 选择对手 {}", rival)
        map_page = MapPage(self._ctrl)
        map_page.select_exercise_rival(rival)
        map_page.enter_exercise_battle()
        self._prepare_for_battle()
        return self._do_combat()

    # ── 出征准备 ──

    def _prepare_for_battle(self) -> None:
        """在出征准备页面执行舰队选择和修理。"""
        time.sleep(1.0)
        page = BattlePreparationPage(self._ctrl)

        # 选择舰队
        page.select_fleet(self._fleet_id)
        time.sleep(0.5)

        # 出征
        page.start_battle()
        time.sleep(1.0)

    # ── 战斗 ──

    def _do_combat(self) -> CombatResult:
        """构建 CombatPlan 并执行战斗。"""
        plan = CombatPlan(
            name="演习",
            mode=CombatMode.EXERCISE,
            default_node=NodeDecision(
                formation=Formation.single_column,
                night=True
            ),
        )

        return run_combat(
            self._ctrl,
            plan,
        )


def run_exercise(
    ctrl: AndroidController,
    fleet_id: int = 1,
    rival: int | None = 1,
) -> list[CombatResult]:
    """执行演习的便捷函数。"""
    runner = ExerciseRunner(ctrl, fleet_id)
    if rival is None:
        return runner.run()
    return [runner._challenge_rival(rival)]

