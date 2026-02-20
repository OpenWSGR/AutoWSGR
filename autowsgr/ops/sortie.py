"""出征准备操作 — 换船、修理策略。

包含涉及多页面切换的出征相关操作:

- **change_fleet** — 换船（准备页 → 选船页 → 准备页）
- **apply_repair** — 按策略修理（读取血量 + 决策 + 修理）

单页面操作（选队伍、补给等）由 BattlePreparationPage 直接提供。
"""

from __future__ import annotations

import enum

from loguru import logger

from autowsgr.emulator.controller import AndroidController
from autowsgr.ui.battle_preparation import BattlePreparationPage


# ═══════════════════════════════════════════════════════════════════════════════
# 修理策略
# ═══════════════════════════════════════════════════════════════════════════════


class RepairStrategy(enum.Enum):
    """修理策略。"""

    MODERATE = "moderate"
    """修中破及以上 (damage >= 1)。"""

    SEVERE = "severe"
    """仅修大破 (damage >= 2)。"""

    ALWAYS = "always"
    """有损伤即修 (damage >= 1, 含黄血)。"""

    NEVER = "never"
    """不修理。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 修理
# ═══════════════════════════════════════════════════════════════════════════════


def apply_repair(
    ctrl: AndroidController,
    *,
    strategy: RepairStrategy = RepairStrategy.SEVERE,
) -> list[int]:
    """根据修理策略，在出征准备页面执行快速修理。

    流程:
    1. 截图检测 6 艘船血量状态
    2. 根据策略决定需要修理的位置
    3. 调用 BattlePreparationPage.repair_slots()

    **前提条件**: 调用时必须已在出征准备页面。

    Parameters
    ----------
    ctrl:
        Android 设备控制器。
    strategy:
        修理策略。

    Returns
    -------
    list[int]
        实际修理的槽位列表。
    """
    if strategy is RepairStrategy.NEVER:
        return []

    page = BattlePreparationPage(ctrl)
    screen = ctrl.screenshot()
    damage = page.detect_ship_damage(screen)

    positions_to_repair: list[int] = []
    for slot, dmg in damage.items():
        if dmg <= 0:  # 绿血或无船
            continue
        if dmg == 3:  # 维修中, 跳过
            continue
        if strategy is RepairStrategy.ALWAYS and dmg >= 1:
            positions_to_repair.append(slot)
        elif strategy is RepairStrategy.MODERATE and dmg >= 1:
            positions_to_repair.append(slot)
        elif strategy is RepairStrategy.SEVERE and dmg >= 2:
            positions_to_repair.append(slot)

    if positions_to_repair:
        page.repair_slots(positions_to_repair)
        logger.info("[OPS] 修理位置: {} (策略: {})", positions_to_repair, strategy.value)
    else:
        logger.info("[OPS] 无需修理 (策略: {})", strategy.value)

    return positions_to_repair
