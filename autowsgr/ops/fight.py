"""简易战斗执行接口 — 最小化的通用战斗运行器。

只需提供控制器、引擎、作战计划即可执行一次完整的战斗流程::

    from autowsgr.combat.engine import CombatEngine
    from autowsgr.combat.plan import CombatPlan
    from autowsgr.ops.fight import run_fight

    plan = CombatPlan.from_yaml("examples/plans/normal_fight/7-46SS-all.yaml")
    engine = CombatEngine(ctrl)
    result = run_fight(ctrl, engine, plan)

与 ``NormalFightRunner`` / ``CampaignRunner`` 不同，本接口:

- **不负责导航** — 调用前应已在出征准备页
- **不负责编队切换** — 使用当前编队
- **只做**: 准备页修理 → 检测血量 → 出征 → 战斗引擎
"""

from __future__ import annotations

import time
from collections.abc import Callable

from loguru import logger

from autowsgr.combat import CombatResult, CombatEngine, CombatPlan
from autowsgr.types import RepairMode
from autowsgr.emulator import AndroidController
from autowsgr.ui import BattlePreparationPage, RepairStrategy
from .navigate import goto_page




def run_fight(
    ctrl: AndroidController,
    engine: CombatEngine,
    plan: CombatPlan,
    *,
    repair: bool = True,
) -> CombatResult:
    """执行一次完整战斗。
    TODO: 自动导航到准备页面（切换到地图页出征页面，选择地图并进入）

    调用前需确保已在出征准备页面。

    Parameters
    ----------
    ctrl:
        设备控制器。
    engine:
        战斗引擎实例。
    plan:
        作战计划 (节点决策 + 修理模式等)。
    repair:
        是否在出征前自动修理，默认 ``True``。

    Returns
    -------
    CombatResult
        本次战斗的完整结果。
    """
    page = BattlePreparationPage(ctrl)

    # 修理
    if repair:
        strategy = _resolve_repair_strategy(plan.repair_mode)
        if strategy is not None:
            page.apply_repair(strategy)

    # 检测战前血量
    screen = ctrl.screenshot()
    damage = page.detect_ship_damage(screen)
    ship_stats = [0] + [damage.get(i, 0) for i in range(1, 7)]

    # 出征
    page.start_battle()
    time.sleep(1.0)

    # 战斗
    result = engine.fight(plan, initial_ship_stats=ship_stats)
    logger.info(
        "[fight] 战斗完成: {} 血量={}",
        result.flag.value if result.flag else "N/A",
        result.ship_stats,
    )
    return result


def run_fight_n(
    ctrl: AndroidController,
    engine: CombatEngine,
    plan: CombatPlan,
    times: int = 1,
    *,
    repair: bool = True,
    enter_battle: Callable[[], None] | None = None,
) -> list[CombatResult]:
    """重复执行多次战斗。

    Parameters
    ----------
    ctrl:
        设备控制器。
    engine:
        战斗引擎实例。
    plan:
        作战计划。
    times:
        重复次数。
    repair:
        是否在出征前自动修理。
    enter_battle:
        可选的进入战斗函数 ``() -> None``。
        每轮战斗前调用，负责从地图页进入出征准备页。
        第一轮假设已在准备页，若提供则从第二轮起调用。

    Returns
    -------
    list[CombatResult]
    """
    results: list[CombatResult] = []
    for i in range(times):
        logger.info("[fight] 第 {}/{} 次", i + 1, times)

        if i > 0 and enter_battle is not None:
            enter_battle()

        result = run_fight(ctrl, engine, plan, repair=repair)
        results.append(result)

    logger.info(
        "[fight] 完成 {} 次战斗",
        len(results),
    )
    return results


def _resolve_repair_strategy(repair_mode: RepairMode | list[RepairMode]) -> RepairStrategy | None:
    """将 plan 的 repair_mode 映射为 RepairStrategy。"""
    mode = repair_mode[0] if isinstance(repair_mode, list) else repair_mode
    if mode == RepairMode.moderate_damage:
        return RepairStrategy.MODERATE
    if mode == RepairMode.severe_damage:
        return RepairStrategy.SEVERE
    return None
