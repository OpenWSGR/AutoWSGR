"""演习战斗操作。

涉及跨页面操作: 主页面 → 地图页面(演习面板) → 出征准备 → 战斗 → 演习页面。

旧代码参考: ``fight/exercise.py`` (NormalExercisePlan)
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from loguru import logger

from autowsgr.combat.callbacks import CombatResult
from autowsgr.combat.engine import CombatEngine, run_combat
from autowsgr.combat.plan import CombatMode, CombatPlan, NodeDecision
from autowsgr.infra import ExerciseConfig
from autowsgr.ops.navigate import goto_page
from autowsgr.types import ConditionFlag, Formation, PageName, RepairMode
from autowsgr.ui.battle.preparation import BattlePreparationPage, RepairStrategy
from autowsgr.ui.map.page import MapPage
from autowsgr.ui.map.data import MapPanel

if TYPE_CHECKING:
    from autowsgr.combat.recognizer import ImageMatcherFunc
    from autowsgr.emulator import AndroidController


# ═══════════════════════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════════════════════


class ExerciseRunner:
    """演习战斗执行器。"""

    def __init__(
        self,
        ctrl: AndroidController,
        config: ExerciseConfig,
        image_matcher: ImageMatcherFunc | None = None,
    ) -> None:
        self._ctrl = ctrl
        self._config = config
        if image_matcher is None:
            raise ValueError("必须提供 image_matcher")
        self._image_matcher = image_matcher
        self._results: list[CombatResult] = []

    # ── 公共接口 ──

    def run(self) -> list[CombatResult]:
        """执行完整的演习流程。

        Returns
        -------
        list[CombatResult]
            每次演习的战斗结果列表。
        """
        logger.info("[OPS] 开始演习 (最多 {} 次)", self._config.exercise_times)
        self._results = []

        # 1. 导航到演习面板
        self._enter_exercise_page()

        for i in range(self._config.exercise_times):
            logger.info("[OPS] 演习第 {}/{} 次", i + 1, self._config.exercise_times)

            # 2. 选择对手
            selected = self._select_rival(i)
            if not selected:
                logger.info("[OPS] 无可挑战的对手, 演习结束")
                break

            # 3. 出征准备
            self._prepare_for_battle()

            # 4. 执行战斗
            result = self._do_combat()
            self._results.append(result)

            if result.flag == ConditionFlag.SL:
                logger.warning("[OPS] 演习 SL, 重试")
                self._enter_exercise_page()
                continue

            # 5. 等待回到演习页面
            time.sleep(2.0)

        logger.info("[OPS] 演习完成, 共 {} 次", len(self._results))
        goto_page(self._ctrl, PageName.MAIN)
        return self._results

    # ── 导航 ──

    def _enter_exercise_page(self) -> None:
        """导航到地图页面的演习面板。"""
        goto_page(self._ctrl, PageName.MAP)
        map_page = MapPage(self._ctrl)
        map_page.switch_panel(MapPanel.EXERCISE)
        time.sleep(1.0)

    # ── 对手选择 ──

    def _select_rival(self, attempt: int) -> bool:
        """选择一个可挑战的对手。"""
        rival_index = (attempt % 4) + 1
        map_page = MapPage(self._ctrl)
        map_page.click_rival(rival_index)
        time.sleep(1.5)
        return True

    # ── 出征准备 ──

    def _prepare_for_battle(self) -> None:
        """在出征准备页面执行舰队选择和修理。"""
        time.sleep(1.0)
        page = BattlePreparationPage(self._ctrl)

        # 选择舰队
        page.select_fleet(self._config.fleet_id)
        time.sleep(0.5)

        # 修理
        if self._config.repair_mode == RepairMode.moderate_damage:
            page.apply_repair(RepairStrategy.MODERATE)
        elif self._config.repair_mode == RepairMode.severe_damage:
            page.apply_repair(RepairStrategy.SEVERE)

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
                formation=Formation(self._config.formation),
                night=self._config.night,
            ),
        )

        return run_combat(
            self._ctrl,
            plan,
            self._image_matcher,
        )


def run_exercise(
    ctrl: AndroidController,
    config: ExerciseConfig | None = None,
    *,
    image_matcher: ImageMatcherFunc | None = None,
) -> list[CombatResult]:
    """执行演习的便捷函数。"""
    if config is None:
        config = ExerciseConfig()
    runner = ExerciseRunner(ctrl, config, image_matcher)
    return runner.run()
