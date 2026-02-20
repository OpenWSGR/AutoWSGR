"""常规战斗操作 — 多节点地图战斗。

涉及跨页面操作: 主页面 → 地图页面(出征面板) → 选章节/地图 → 出征准备 → 战斗 → 地图页面。

旧代码参考: ``fight/normal_fight.py`` (NormalFightPlan)
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

from autowsgr.combat.callbacks import CombatResult
from autowsgr.combat.engine import CombatEngine, run_combat
from autowsgr.combat.plan import CombatMode, CombatPlan
from autowsgr.combat.recognition import make_enemy_callbacks
from autowsgr.ops.navigate import goto_page
from autowsgr.types import ConditionFlag, RepairMode
from autowsgr.ui.battle.preparation import BattlePreparationPage, RepairStrategy
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
    from autowsgr.vision import OCREngine


class NormalFightRunner:
    """常规战斗执行器。"""

    def __init__(
        self,
        ctrl: AndroidController,
        plan: CombatPlan,
        image_matcher: ImageMatcherFunc,
        *,
        ocr: OCREngine | None = None,
        get_enemy_info: GetEnemyInfoFunc | None = None,
        get_enemy_formation: GetEnemyFormationFunc | None = None,
        detect_ship_stats: DetectShipStatsFunc | None = None,
        detect_result_grade: DetectResultGradeFunc | None = None,
        get_ship_drop: GetShipDropFunc | None = None,
        image_exist: ImageExistFunc | None = None,
        click_image: ClickImageFunc | None = None,
    ) -> None:
        self._ctrl = ctrl
        self._plan = plan
        self._ocr = ocr

        # 确保 plan 模式是 NORMAL
        if plan.mode != CombatMode.NORMAL:
            logger.warning(
                "[OPS] NormalFightRunner 收到非 NORMAL 模式的计划: {}, 已修正",
                plan.mode,
            )
            plan.mode = CombatMode.NORMAL

        # 战斗引擎回调
        self._image_matcher = image_matcher

        # 若未提供敌方识别回调, 自动用 DLL + OCR 创建
        if get_enemy_info is None and get_enemy_formation is None:
            auto_info, auto_formation = make_enemy_callbacks(
                ctrl, ocr, mode="fight",
            )
            self._get_enemy_info = auto_info
            self._get_enemy_formation = auto_formation
        else:
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
        """执行一次完整的常规战。

        1. 进入地图
        2. 出征准备
        3. 战斗
        4. 处理结果

        Returns
        -------
        CombatResult
        """
        logger.info(
            "[OPS] 常规战: {}-{} ({})",
            self._plan.chapter,
            self._plan.map_id,
            self._plan.name,
        )

        # 1. 进入战斗地图
        self._enter_fight()

        # 2. 出征准备
        ship_stats = self._prepare_for_battle()

        # 3. 执行战斗
        result = self._do_combat(ship_stats)

        # 4. 处理结果
        self._handle_result(result)

        return result

    def run_for_times(
        self,
        times: int,
        *,
        gap: float = 0.0,
    ) -> list[CombatResult]:
        """重复执行常规战。

        Parameters
        ----------
        times:
            重复次数。
        gap:
            每次战斗之间的间隔 (秒)。

        Returns
        -------
        list[CombatResult]
        """
        logger.info("[OPS] 常规战连续执行 {} 次", times)
        self._results = []

        for i in range(times):
            logger.info("[OPS] 常规战第 {}/{} 次", i + 1, times)
            result = self.run()
            self._results.append(result)

            if result.flag == ConditionFlag.DOCK_FULL:
                logger.warning("[OPS] 船坞已满, 停止")
                break

            if gap > 0 and i < times - 1:
                time.sleep(gap)

        logger.info(
            "[OPS] 常规战完成: {} 次 (成功 {} 次)",
            len(self._results),
            sum(1 for r in self._results if r.flag == ConditionFlag.OPERATION_SUCCESS),
        )
        return self._results

    # ── 进入地图 ──

    def _enter_fight(self) -> None:
        """导航到目标地图并进入。"""
        goto_page(self._ctrl, "地图页面")
        map_page = MapPage(self._ctrl, self._ocr)
        map_page.enter_sortie(self._plan.chapter, self._plan.map_id)

    # ── 出征准备 ──

    def _prepare_for_battle(self) -> list[int]:
        """出征准备: 舰队选择、修理、检测血量。

        Returns
        -------
        list[int]
            战前血量状态。
        """
        time.sleep(1.0)
        page = BattlePreparationPage(self._ctrl)

        # 选择舰队
        page.select_fleet(self._plan.fleet_id)
        time.sleep(0.5)

        # 换船 (如果指定了舰船列表)
        if self._plan.fleet is not None:
            page.change_fleet(
                self._plan.fleet_id,
                self._plan.fleet,
                ocr=self._ocr,
            )
            time.sleep(0.5)

        # 补给
        page.apply_supply()
        time.sleep(0.3)

        # 修理策略
        repair_modes = self._plan.repair_mode
        if isinstance(repair_modes, list):
            min_mode = min(m.value for m in repair_modes)
        else:
            min_mode = repair_modes.value

        if min_mode <= RepairMode.moderate_damage.value:
            page.apply_repair(RepairStrategy.MODERATE)
        elif min_mode <= RepairMode.severe_damage.value:
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
        """构建 CombatEngine 并执行战斗。"""
        return run_combat(
            self._ctrl,
            self._plan,
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
        """处理战斗结果。"""
        logger.info("[OPS] 常规战结果: {}", result.flag.value)


# ═══════════════════════════════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════════════════════════════


def run_normal_fight(
    ctrl: AndroidController,
    plan: CombatPlan,
    image_matcher: ImageMatcherFunc,
    *,
    times: int = 1,
    gap: float = 0.0,
    ocr: OCREngine | None = None,
    get_enemy_info: GetEnemyInfoFunc | None = None,
    get_enemy_formation: GetEnemyFormationFunc | None = None,
    detect_ship_stats: DetectShipStatsFunc | None = None,
    detect_result_grade: DetectResultGradeFunc | None = None,
    get_ship_drop: GetShipDropFunc | None = None,
    image_exist: ImageExistFunc | None = None,
    click_image: ClickImageFunc | None = None,
) -> list[CombatResult]:
    """执行常规战的便捷函数。"""
    runner = NormalFightRunner(
        ctrl, plan, image_matcher,
        ocr=ocr,
        get_enemy_info=get_enemy_info,
        get_enemy_formation=get_enemy_formation,
        detect_ship_stats=detect_ship_stats,
        detect_result_grade=detect_result_grade,
        get_ship_drop=get_ship_drop,
        image_exist=image_exist,
        click_image=click_image,
    )
    return runner.run_for_times(times, gap=gap)


def run_normal_fight_from_yaml(
    ctrl: AndroidController,
    yaml_path: str,
    image_matcher: ImageMatcherFunc,
    *,
    times: int = 1,
    **kwargs,
) -> list[CombatResult]:
    """从 YAML 文件加载计划并执行常规战。"""
    plan = CombatPlan.from_yaml(yaml_path)
    return run_normal_fight(ctrl, plan, image_matcher, times=times, **kwargs)
