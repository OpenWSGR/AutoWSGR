"""活动战斗操作 — 活动地图 (Event) 战斗。

涉及跨页面操作: 主页面 → 活动地图页面 → 选择节点 → 出征准备 → 战斗 → 活动地图页面。

使用方式::

    from autowsgr.ops.event_fight import EventFightRunner

    runner = EventFightRunner(ctx, plan, map_code="H3")
    result = runner.run()
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Literal

from autowsgr.combat import CombatMode, CombatPlan, CombatResult
from autowsgr.combat.engine import run_combat
from autowsgr.infra.logger import get_logger
from autowsgr.ops.navigate import goto_page
from autowsgr.types import ConditionFlag, PageName, RepairMode, ShipDamageState
from autowsgr.ui import BattlePreparationPage, RepairStrategy
from autowsgr.ui.event.event_page import BaseEventPage


if TYPE_CHECKING:
    from autowsgr.context import GameContext

_log = get_logger('ops')


# ═══════════════════════════════════════════════════════════════════════════════
# 活动战斗执行器
# ═══════════════════════════════════════════════════════════════════════════════


class EventFightRunner:
    """活动战斗执行器。

    与 ``NormalFightRunner`` 结构一致，但导航过程不同：

    - 进入战斗：主页面 → 活动地图 → ``start_fight(map)`` → 出征准备
    - 战斗结束：回到活动地图页面（而非常规地图页面）

    Parameters
    ----------
    ctx:
        游戏上下文。
    plan:
        战斗计划。
    map_code:
        活动地图代号，如 ``"H3"``、``"E1"``。
        若不提供则从 ``plan.chapter`` + ``plan.map_id`` 推导。
    entrance:
        入口选择 ``"alpha"``/``"beta"``/``None``。
    event_name:
        活动名称（如 ``"20260212"``），用于加载地图节点数据。
        优先取此参数；若为 ``None`` 则用 ``plan.event_name``；
        两者均未指定时节点追踪器不启用。
    """

    def __init__(
        self,
        ctx: GameContext,
        plan: CombatPlan,
        *,
        map_code: str | None = None,
        entrance: Literal['alpha', 'beta'] | None = None,
        event_name: str | None = None,
        fleet_id: int | None = None,
        fleet: list[str] | None = None,
    ) -> None:
        self._ctx = ctx
        self._ctrl = ctx.ctrl
        self._plan = plan
        self._entrance = entrance
        self._fleet_id = fleet_id if fleet_id is not None else (plan.fleet_id or 1)
        self._fleet = fleet if fleet is not None else plan.fleet
        self._skip_check = False  # 首次执行时检查难度和节点，后续重复执行时跳过检查以节省时间

        # 推导 map_code
        if map_code is not None:
            self._map_code = map_code
        else:
            # 从 plan.chapter + plan.map_id 推导: chapter="H", map_id=3 → "H3"
            ch = str(plan.chapter).upper() if plan.chapter else 'H'
            mid = str(plan.map_id) if plan.map_id else '1'
            if len(ch) == 1 and ch in ('H', 'E') and mid.isdigit():
                self._map_code = f'{ch}{mid}'
            else:
                self._map_code = f'H{mid}'

        # 活动名称：用于节点追踪器加载地图数据
        resolved_event_name = event_name or plan.event_name
        if resolved_event_name and not plan.event_name:
            plan.event_name = resolved_event_name

        # 从 config 读取拆船配置
        self._dock_full_destroy = ctx.config.dock_full_destroy
        self._destroy_ship_types = ctx.config.destroy_ship_types or None

        # 强制设置为 EVENT 模式
        if plan.mode != CombatMode.EVENT:
            _log.info(
                '[OPS] 活动战斗: 计划模式 {} → EVENT',
                plan.mode,
            )
            plan.mode = CombatMode.EVENT

        self._results: list[CombatResult] = []
        self._fleet_ships = None

    # ── 公共接口 ──

    def run(self) -> CombatResult:
        """执行一次完整的活动战斗。

        Returns
        -------
        CombatResult
        """
        _log.info(
            '[OPS] 活动战: {} ({})',
            self._map_code,
            self._plan.name,
        )

        # 1. 进入活动地图并选择节点 → 出征准备
        self._enter_fight()

        # 2. 出征准备
        ship_stats = self._prepare_for_battle()

        # 同步战前信息到上下文
        self._ctx.sync_before_combat(self._fleet_id, self._fleet_ships)

        # 3. 执行战斗
        result = self._do_combat(ship_stats)
        result.fleet = self._fleet_ships

        # 同步战后信息到上下文
        self._ctx.sync_after_combat(self._fleet_id, result)

        # 4. 处理结果
        self._handle_result(result)

        self._skip_check = True

        return result

    def run_for_times(
        self,
        times: int,
        *,
        gap: float = 0.0,
    ) -> list[CombatResult]:
        """重复执行活动战斗。

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
        _log.info('[OPS] 活动战连续执行 {} 次', times)
        self._results = []

        for i in range(times):
            _log.info('[OPS] 活动战第 {}/{} 次', i + 1, times)
            result = self.run()
            self._results.append(result)

            if result.flag == ConditionFlag.DOCK_FULL:
                _log.warning('[OPS] 船坞已满, 停止')
                break

            if gap > 0 and i < times - 1:
                time.sleep(gap)

        _log.info(
            '[OPS] 活动战完成: {} 次 (成功 {} 次)',
            len(self._results),
            sum(1 for r in self._results if r.flag == ConditionFlag.OPERATION_SUCCESS),
        )
        return self._results

    # ── 进入活动地图 ──

    def _enter_fight(self) -> None:
        """导航到活动地图并通过 UI 层完成: 难度切换 → 节点选择 → 出击。

        弹窗关闭由 UI 层 (:class:`BaseEventPage`) 内部处理，ops 不介入。
        """
        # 导航到活动地图页面
        goto_page(self._ctx, PageName.EVENT_MAP)
        time.sleep(0.25)

        # 委托 UI 层完成: 难度 / 节点 / 出击
        event_page = BaseEventPage(self._ctx)
        entrance: Literal['alpha', 'beta'] | None = self._entrance  # type: ignore[assignment]
        event_page.start_fight(self._map_code, entrance, self._skip_check)

    # ── 出征准备 ──

    def _prepare_for_battle(self) -> list[ShipDamageState]:
        """出征准备: 舰队选择、修理、检测血量。"""
        time.sleep(1.0)
        page = BattlePreparationPage(self._ctx)

        # 选择舰队
        page.select_fleet(self._fleet_id)
        time.sleep(0.5)

        # 换船 (如果指定了舰船列表)
        if self._plan.fleet is not None:
            page.change_fleet(
                self._fleet_id,
                self._plan.fleet,
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

        # 检测战前舰队信息 (血量 + 等级)
        fleet_info = page.detect_fleet_info()
        ship_stats = [fleet_info.ship_damage.get(i, ShipDamageState.NORMAL) for i in range(6)]
        self._fleet_ships = fleet_info.to_ships(self._plan.fleet)

        # 出征
        page.start_battle()
        time.sleep(1.0)

        return ship_stats

    # ── 战斗 ──

    def _do_combat(self, ship_stats: list[ShipDamageState]) -> CombatResult:
        """构建 CombatEngine 并执行战斗。"""
        return run_combat(
            self._ctx,
            self._plan,
            ship_stats=ship_stats,
        )

    # ── 结果处理 ──

    def _handle_result(self, result: CombatResult) -> None:
        """处理战斗结果。"""
        if result.flag == ConditionFlag.DOCK_FULL:
            self._handle_dock_full(result)
            return

    def _handle_dock_full(self, result: CombatResult) -> None:
        """船坞已满处理。"""
        if self._dock_full_destroy:
            from autowsgr.ops.destroy import destroy_ships

            _log.warning('[OPS] 船坞已满，执行自动解装')
            self._ctrl.click(0.38, 0.565)
            destroy_ships(
                self._ctx,
                ship_types=self._destroy_ship_types,
            )
            result.flag = ConditionFlag.OPERATION_SUCCESS
            return

        _log.warning('[OPS] 船坞已满, 未开启自动解装')


# ═══════════════════════════════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════════════════════════════


def run_event_fight(
    ctx: GameContext,
    plan: CombatPlan,
    *,
    map_code: str | None = None,
    entrance: Literal['alpha', 'beta'] | None = None,
    times: int = 1,
    gap: float = 0.0,
    fleet_id: int | None = None,
    fleet: list[str] | None = None,
) -> list[CombatResult]:
    """执行活动战的便捷函数。

    Parameters
    ----------
    ctx:
        游戏上下文。
    plan:
        战斗计划。
    map_code:
        活动地图代号，如 ``"H3"``。
    entrance:
        入口选择。
    times:
        重复次数。
    gap:
        每次间隔。

    Returns
    -------
    list[CombatResult]
    """
    runner = EventFightRunner(
        ctx,
        plan,
        map_code=map_code,
        entrance=entrance,
        fleet_id=fleet_id,
        fleet=fleet,
    )
    return runner.run_for_times(times, gap=gap)


def run_event_fight_from_yaml(
    ctx: GameContext,
    yaml_path: str,
    *,
    map_code: str | None = None,
    entrance: Literal['alpha', 'beta'] | None = None,
    times: int = 1,
    fleet_id: int | None = None,
    fleet: list[str] | None = None,
) -> list[CombatResult]:
    """从 YAML 文件加载计划并执行活动战。

    *yaml_path* 支持以下格式:

    - 绝对路径 / 相对路径: 直接加载。
    - 策略名称 (如 ``"E5ADE夜战"``): 自动在 ``autowsgr/data/plan/event/``
      包数据目录中查找，可省略 ``.yaml`` 后缀。

    Parameters
    ----------
    ctx:
        游戏上下文。
    yaml_path:
        YAML 配置路径或策略名称。
    map_code:
        活动地图代号。
    entrance:
        入口选择。
    times:
        重复次数。
    fleet_id:
        舰队 ID。
    fleet:
        舰船列表。

    Returns
    -------
    list[CombatResult]
    """
    from autowsgr.infra.file_utils import resolve_plan_path

    resolved = resolve_plan_path(yaml_path, category='event')
    plan = CombatPlan.from_yaml(resolved)
    return run_event_fight(
        ctx,
        plan,
        map_code=map_code,
        entrance=entrance,
        times=times,
        fleet_id=fleet_id,
        fleet=fleet,
    )
