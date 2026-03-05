"""战役战斗操作 — 单点战役战斗。

涉及跨页面操作: 主页面 → 地图页面(战役面板) → 选择战役 → 出征准备 → 战斗 → 战役页面。

旧代码参考: ``fight/battle.py`` (BattlePlan)

使用方式::

    runner = CampaignRunner(ctx, "困难航母")
    results = runner.run()
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from autowsgr.combat import CombatEngine, CombatMode, CombatPlan, CombatResult, NodeDecision
from autowsgr.infra.logger import get_logger
from autowsgr.ops.navigate import goto_page
from autowsgr.types import ConditionFlag, Formation, PageName, RepairMode, ShipDamageState
from autowsgr.ui import (
    BattlePreparationPage,
    MapPage,
    NavigationError,
    RepairStrategy,
    wait_leave_page,
)
from autowsgr.ui.battle.base import BaseBattlePreparation


if TYPE_CHECKING:
    from autowsgr.context import GameContext


_log = get_logger('ops')

CAMPAIGN_NAMES: dict[int, str] = {
    1: '驱逐',
    2: '巡洋',
    3: '战列',
    4: '航母',
    5: '潜艇',
}
"""战役编号 → 中文名称。"""

# 用户友好的战役名称 → (map_index, difficulty)
# 支持 "困难航母"、"简单驱逐" 等名称直接映射
CAMPAIGN_NAME_MAP: dict[str, tuple[int, str]] = {}
"""战役中文名 → ``(map_index, difficulty)``。"""

for _idx, _short_name in CAMPAIGN_NAMES.items():
    CAMPAIGN_NAME_MAP[f'简单{_short_name}'] = (_idx, 'easy')
    CAMPAIGN_NAME_MAP[f'困难{_short_name}'] = (_idx, 'hard')


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
            f'无法识别的战役名称: {name!r}，可选: {", ".join(sorted(CAMPAIGN_NAME_MAP))}'
        )
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 战役执行器
# ═══════════════════════════════════════════════════════════════════════════════


class CampaignRunner:
    """战役战斗执行器。

    Parameters
    ----------
    ctx:
        游戏上下文。
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
        ctx: GameContext,
        campaign_name: str,
        times: int = 3,
        formation: Formation = Formation.double_column,
        night: bool = True,
        repair_mode: RepairMode = RepairMode.moderate_damage,
    ) -> None:
        self._ctx = ctx
        self._ctrl = ctx.ctrl
        self._engine = CombatEngine(ctx)
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
        _log.info(
            '[OPS] 战役: {} 阵型={} 夜战={} 共 {} 次',
            self._campaign_name,
            self._formation.name,
            self._night,
            self._times,
        )
        results: list[CombatResult] = []

        for i in range(self._times):
            _log.info('[OPS] 战役第 {}/{} 次', i + 1, self._times)

            # 1. 进入战役
            self._enter_battle()

            # 2. 出征准备
            ship_stats, started = self._prepare_for_battle()

            if not started:
                result = CombatResult(
                    flag=ConditionFlag.BATTLE_TIMES_EXCEED,
                    ship_stats=ship_stats,
                )
                results.append(result)
                _log.info('[OPS] 战役次数已用完')
                break

            # 3. 构建计划并执行战斗
            result = self._do_combat(ship_stats)
            results.append(result)

            if result.flag == ConditionFlag.BATTLE_TIMES_EXCEED:
                _log.info('[OPS] 战役次数已用完')
                break

            if result.flag == ConditionFlag.DOCK_FULL:
                _log.warning('[OPS] 船坞已满, 停止战役')
                break

        _log.info(
            '[OPS] 战役完成: {} 次 (成功 {} 次)',
            len(results),
            sum(1 for r in results if r.flag == ConditionFlag.OPERATION_SUCCESS),
        )
        return results

    # ── 进入战役 ──

    def _enter_battle(self) -> None:
        """导航到战役面板并选择战役。"""
        goto_page(self._ctx, PageName.MAP)
        map_page = MapPage(self._ctx)
        map_page.enter_campaign(
            map_index=self._map_index,
            difficulty=self._difficulty,
            campaign_name=self._campaign_name,
        )

    # ── 出征准备 ──

    def _prepare_for_battle(self) -> tuple[list[ShipDamageState], bool]:
        """出征准备: 修理、出征，并确认离开准备页面。

        点击出征后通过 ``wait_leave_page`` 确认离开；若超时则重试一次。
        两次均失败视为战役次数用尽。

        Returns
        -------
        tuple[list[ShipDamageState], bool]
            ``(战前血量状态, 是否成功出征)``。
            当 ``False`` 时表示战役次数已用完。
        """
        time.sleep(0.25)  # 等待页面稳定
        page = BattlePreparationPage(self._ctx)

        # 修理策略
        if self._repair_mode == RepairMode.moderate_damage:
            page.apply_repair(RepairStrategy.MODERATE)
        elif self._repair_mode == RepairMode.severe_damage:
            page.apply_repair(RepairStrategy.SEVERE)

        # 检测战前血量
        screen = self._ctrl.screenshot()
        damage = page.detect_ship_damage(screen)
        ship_stats = [damage.get(i, ShipDamageState.NORMAL) for i in range(6)]

        # 出征 + 确认离开
        left = self._start_battle_with_retry(page)

        return ship_stats, left

    def _try_start_battle(self, page: BattlePreparationPage) -> bool:
        """点击出征并等待离开准备页面。

        Returns
        -------
        bool
            ``True`` 表示已成功离开出征准备页面。
            ``False`` 表示超时仍在当前页面 (可能是战役次数用尽)。
        """
        page.start_battle()
        try:
            wait_leave_page(
                self._ctrl,
                checker=BaseBattlePreparation.is_current_page,
                timeout=1.5,
                source=PageName.BATTLE_PREP,
                target='combat',
            )
            return True
        except NavigationError:
            return False

    def _start_battle_with_retry(self, page: BattlePreparationPage) -> bool:
        """尝试出征，失败后重试一次。

        Returns
        -------
        bool
            ``True`` 成功出征；``False`` 战役次数用尽。
        """
        if self._try_start_battle(page):
            return True

        _log.warning('[OPS] 出征后未离开准备页面，重试一次')
        if self._try_start_battle(page):
            return True

        _log.info('[OPS] 两次出征均未离开准备页面，判定为战役次数已用完')
        return False

    # ── 战斗 ──

    def _do_combat(self, ship_stats: list[ShipDamageState]) -> CombatResult:
        """构建 CombatPlan 并执行战斗。"""
        plan = CombatPlan(
            name=f'战役-{self._campaign_name}',
            mode=CombatMode.BATTLE,
            default_node=NodeDecision(
                formation=self._formation,
                night=self._night,
            ),
        )

        return self._engine.fight(plan, initial_ship_stats=ship_stats)
