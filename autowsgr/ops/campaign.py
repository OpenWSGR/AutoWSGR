"""战役战斗操作 — 单点战役战斗。

涉及跨页面操作: 主页面 → 地图页面(战役面板) → 选择战役 → 出征准备 → 战斗 → 战役页面。

旧代码参考: ``fight/battle.py`` (BattlePlan)

使用方式::

    engine = CombatEngine(ctrl)
    runner = CampaignRunner(ctrl, engine, "困难航母")
    results = runner.run()
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from loguru import logger

from autowsgr.combat.callbacks import CombatResult
from autowsgr.combat.plan import CombatMode, CombatPlan, NodeDecision
from autowsgr.ops.navigate import goto_page
from autowsgr.types import ConditionFlag, Formation, RepairMode
from autowsgr.ui.battle.preparation import BattlePreparationPage, RepairStrategy
from autowsgr.ui.map.page import MapPage

if TYPE_CHECKING:
    from autowsgr.combat.engine import CombatEngine
    from autowsgr.emulator import AndroidController


CAMPAIGN_NAMES: dict[int, str] = {
    1: "驱逐",
    2: "巡洋",
    3: "战列",
    4: "航母",
    5: "潜艇",
}
"""战役编号 → 中文名称。"""

# 用户友好的战役名称 → (map_index, difficulty)
# 支持 "困难航母"、"简单驱逐" 等名称直接映射
CAMPAIGN_NAME_MAP: dict[str, tuple[int, str]] = {}
"""战役中文名 → ``(map_index, difficulty)``。"""

for _idx, _short_name in CAMPAIGN_NAMES.items():
    CAMPAIGN_NAME_MAP[f"简单{_short_name}"] = (_idx, "easy")
    CAMPAIGN_NAME_MAP[f"困难{_short_name}"] = (_idx, "hard")

def parse_campaign_name(name: str) -> tuple[int, str]:
    """解析战役名称为 ``(map_index, difficulty)``。

    Parameters
    ----------
    name:
        战役名称，如 ``"困难航母"``、``"简单驱逐"``。

    Returns
    -------
    tuple[int, str]
        ``(map_index, difficulty)``

    Raises
    ------
    ValueError
        名称无法识别。
    """
    result = CAMPAIGN_NAME_MAP.get(name)
    if result is None:
        raise ValueError(
            f"无法识别的战役名称: {name!r}，"
            f"可选: {', '.join(sorted(CAMPAIGN_NAME_MAP))}"
        )
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 战役执行器
# ═══════════════════════════════════════════════════════════════════════════════


class CampaignRunner:
    """战役战斗执行器。

    Parameters
    ----------
    ctrl:
        设备控制器。
    engine:
        自包含的战斗引擎 (无需外部回调)。
    campaign_name:
        战役名称，如 ``"困难航母"``、``"简单驱逐"``。
    times:
        重复次数。
    formation:
        战斗阵型。
    night:
        是否夜战。
    repair_mode:
        修理模式。
    """

    def __init__(
        self,
        ctrl: AndroidController,
        engine: CombatEngine,
        campaign_name: str,
        times: int = 3,
        formation: Formation = Formation.double_column,
        night: bool = True,
        repair_mode: RepairMode = RepairMode.moderate_damage,
    ) -> None:
        self._ctrl = ctrl
        self._engine = engine
        self._campaign_name = campaign_name
        self._times = times
        self._formation = formation
        self._night = night
        self._repair_mode = repair_mode

        # 解析战役名称
        self._map_index, self._difficulty = parse_campaign_name(campaign_name)

    # ── 公共接口 ──

    def run(self) -> list[CombatResult]:
        """执行战役。

        Returns
        -------
        list[CombatResult]
        """
        logger.info(
            "[OPS] 战役: {} 阵型={} 夜战={} 共 {} 次",
            self._campaign_name,
            self._formation.name,
            self._night,
            self._times,
        )
        results: list[CombatResult] = []

        for i in range(self._times):
            logger.info("[OPS] 战役第 {}/{} 次", i + 1, self._times)

            # 1. 进入战役
            self._enter_battle()

            # 2. 出征准备
            ship_stats = self._prepare_for_battle()

            # 3. 构建计划并执行战斗
            result = self._do_combat(ship_stats)
            results.append(result)

            if result.flag == ConditionFlag.BATTLE_TIMES_EXCEED:
                logger.info("[OPS] 战役次数已用完")
                break

            if result.flag == ConditionFlag.DOCK_FULL:
                logger.warning("[OPS] 船坞已满, 停止战役")
                break

        logger.info(
            "[OPS] 战役完成: {} 次 (成功 {} 次)",
            len(results),
            sum(1 for r in results if r.flag == ConditionFlag.OPERATION_SUCCESS),
        )
        return results

    # ── 进入战役 ──

    def _enter_battle(self) -> None:
        """导航到战役面板并选择战役。"""
        goto_page(self._ctrl, "地图页面")
        map_page = MapPage(self._ctrl)
        map_page.enter_campaign(
            map_index=self._map_index,
            difficulty=self._difficulty,
            campaign_name=self._campaign_name,
        )

    # ── 出征准备 ──

    def _prepare_for_battle(self) -> list[int]:
        """出征准备: 修理、出征。

        Returns
        -------
        list[int]
            战前血量状态。
        """
        time.sleep(0.25) # 等待页面稳定
        page = BattlePreparationPage(self._ctrl)

        # 修理策略
        if self._repair_mode == RepairMode.moderate_damage:
            page.apply_repair(RepairStrategy.MODERATE)
        elif self._repair_mode == RepairMode.severe_damage:
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
            name=f"战役-{self._campaign_name}",
            mode=CombatMode.BATTLE,
            default_node=NodeDecision(
                formation=self._formation,
                night=self._night,
            ),
        )

        return self._engine.fight(plan, initial_ship_stats=ship_stats)
