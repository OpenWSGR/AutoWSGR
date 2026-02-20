"""战役战斗操作 — 单点战役战斗。

涉及跨页面操作: 主页面 → 地图页面(战役面板) → 选择战役 → 出征准备 → 战斗 → 战役页面。

旧代码参考: ``fight/battle.py`` (BattlePlan)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from loguru import logger

from autowsgr.combat.callbacks import CombatResult
from autowsgr.combat.engine import run_combat
from autowsgr.combat.plan import CombatMode, CombatPlan, NodeDecision
from autowsgr.ops.navigate import goto_page
from autowsgr.types import ConditionFlag, Formation, RepairMode
from autowsgr.ui.battle.preparation import BattlePreparationPage, RepairStrategy
from autowsgr.ui.map.data import CAMPAIGN_NAMES
from autowsgr.ui.map.page import MapPage

if TYPE_CHECKING:
    from autowsgr.combat.callbacks import (
        ClickImageFunc,
        DetectResultGradeFunc,
        DetectShipStatsFunc,
        GetEnemyFormationFunc,
        GetEnemyInfoFunc,
        GetShipDropFunc,
        ImageExistFunc,
    )
    from autowsgr.combat.recognizer import ImageMatcherFunc
    from autowsgr.emulator import AndroidController


# ═══════════════════════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class CampaignConfig:
    """战役配置。"""

    map_index: int = 2
    difficulty: str = "hard"
    fleet_id: int = 1
    formation: int = 2
    night: bool = True
    repair_mode: RepairMode = RepairMode.moderate_damage
    auto_support: bool = False
    max_times: int = 3


# ═══════════════════════════════════════════════════════════════════════════════
# 战役执行器
# ═══════════════════════════════════════════════════════════════════════════════


class CampaignRunner:
    """战役战斗执行器。"""

    def __init__(
        self,
        ctrl: AndroidController,
        config: CampaignConfig,
        image_matcher: ImageMatcherFunc,
        *,
        get_enemy_info: GetEnemyInfoFunc | None = None,
        get_enemy_formation: GetEnemyFormationFunc | None = None,
        detect_ship_stats: DetectShipStatsFunc | None = None,
        detect_result_grade: DetectResultGradeFunc | None = None,
        get_ship_drop: GetShipDropFunc | None = None,
        image_exist: ImageExistFunc | None = None,
        click_image: ClickImageFunc | None = None,
    ) -> None:
        self._ctrl = ctrl
        self._config = config
        self._image_matcher = image_matcher

        # 战斗引擎回调
        self._get_enemy_info = get_enemy_info
        self._get_enemy_formation = get_enemy_formation
        self._detect_ship_stats = detect_ship_stats
        self._detect_result_grade = detect_result_grade
        self._get_ship_drop = get_ship_drop
        self._image_exist = image_exist
        self._click_image = click_image

        self._results: list[CombatResult] = []

    # ── 公共接口 ──

    def run(self) -> CombatResult:
        """执行一次战役战斗。

        Returns
        -------
        CombatResult
        """
        battle_name = CAMPAIGN_NAMES.get(self._config.map_index, "未知")
        logger.info(
            "[OPS] 战役: {} ({}) 舰队 {}",
            battle_name,
            self._config.difficulty,
            self._config.fleet_id,
        )

        # 1. 进入战役
        self._enter_battle()

        # 2. 出征准备
        ship_stats = self._prepare_for_battle()

        # 3. 执行战斗
        result = self._do_combat(ship_stats)

        # 4. 处理结果
        self._handle_result(result)

        return result

    def run_for_times(self, times: int | None = None) -> list[CombatResult]:
        """重复执行战役。

        Parameters
        ----------
        times:
            重复次数。None 使用配置中的 max_times。

        Returns
        -------
        list[CombatResult]
        """
        if times is None:
            times = self._config.max_times

        logger.info("[OPS] 战役连续执行 {} 次", times)
        self._results = []

        for i in range(times):
            logger.info("[OPS] 战役第 {}/{} 次", i + 1, times)
            result = self.run()
            self._results.append(result)

            if result.flag == ConditionFlag.BATTLE_TIMES_EXCEED:
                logger.info("[OPS] 战役次数已用完")
                break

            if result.flag == ConditionFlag.DOCK_FULL:
                logger.warning("[OPS] 船坞已满, 停止战役")
                break

        logger.info(
            "[OPS] 战役完成: {} 次 (成功 {} 次)",
            len(self._results),
            sum(1 for r in self._results if r.flag == ConditionFlag.OPERATION_SUCCESS),
        )
        return self._results

    # ── 进入战役 ──

    def _enter_battle(self) -> None:
        """导航到战役面板并选择战役。"""
        goto_page(self._ctrl, "地图页面")
        map_page = MapPage(self._ctrl)
        map_page.enter_campaign(
            map_index=self._config.map_index,
            difficulty=self._config.difficulty,
        )

    # ── 出征准备 ──

    def _prepare_for_battle(self) -> list[int]:
        """出征准备: 舰队选择、修理、支援设置。

        Returns
        -------
        list[int]
            战前血量状态。
        """
        time.sleep(1.0)
        page = BattlePreparationPage(self._ctrl)

        # 修理策略
        if self._config.repair_mode == RepairMode.moderate_damage:
            page.apply_repair(RepairStrategy.MODERATE)
        elif self._config.repair_mode == RepairMode.severe_damage:
            page.apply_repair(RepairStrategy.SEVERE)

        # 检测战前血量
        screen = self._ctrl.screenshot()
        damage = page.detect_ship_damage(screen)
        ship_stats = [0] + [damage.get(i, 0) for i in range(1, 7)]

        # 出征
        page.start_battle()
        time.sleep(1.0)

        return ship_stats

    # ── 战斗 ──

    def _do_combat(self, ship_stats: list[int]) -> CombatResult:
        """构建 CombatPlan 并执行战斗。"""
        plan = CombatPlan(
            name=f"战役-{CAMPAIGN_NAMES.get(self._config.map_index, '?')}",
            mode=CombatMode.BATTLE,
            default_node=NodeDecision(
                formation=Formation(self._config.formation),
                night=self._config.night,
            ),
        )

        return run_combat(
            self._ctrl,
            plan,
            self._image_matcher,
            ship_stats=ship_stats,
            get_enemy_info=self._get_enemy_info,
            get_enemy_formation=self._get_enemy_formation,
            detect_ship_stats=self._detect_ship_stats,
            detect_result_grade=self._detect_result_grade,
            get_ship_drop=self._get_ship_drop,
            image_exist=self._image_exist,
            click_image=self._click_image,
        )

    # ── 结果处理 ──

    def _handle_result(self, result: CombatResult) -> None:
        """处理战役结果。"""
        logger.info("[OPS] 战役结果: {}", result.flag.value)


def run_campaign(
    ctrl: AndroidController,
    config: CampaignConfig,
    image_matcher: ImageMatcherFunc,
    *,
    times: int | None = None,
    **kwargs,
) -> list[CombatResult]:
    """执行战役的便捷函数。"""
    runner = CampaignRunner(ctrl, config, image_matcher, **kwargs)
    return runner.run_for_times(times)
