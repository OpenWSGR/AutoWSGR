"""常规战斗操作 — 多节点地图战斗。

涉及跨页面操作: 主页面 → 地图页面(出征面板) → 选章节/地图 → 出征准备 → 战斗 → 地图页面。

旧代码参考: ``fight/normal_fight.py`` (NormalFightPlan)
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Literal

from autowsgr.combat import CombatMode, CombatPlan, CombatResult
from autowsgr.combat.engine import run_combat
from autowsgr.combat.fleet import (
    FleetSlotRule,
    ResolvedFleetSelection,
    exact_fleet_rules,
    resolve_fleet_selection,
    validate_fleet_selection_arguments,
)
from autowsgr.infra import ActionFailedError
from autowsgr.infra.logger import get_logger
from autowsgr.ops.navigate import goto_page
from autowsgr.types import ConditionFlag, PageName, RepairMode, ShipDamageState
from autowsgr.ui import BaseEventPage, BattlePreparationPage, MapPage, MapPanel, RepairStrategy
from autowsgr.ui.utils import NavigationError


if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from autowsgr.context import GameContext
    from autowsgr.context.ship import Ship


_log = get_logger('ops')


def _require_fleet_change(success: bool, source: str) -> None:
    """换船失败时停止出征，避免使用错误舰队进入战斗。"""
    if not success:
        raise ActionFailedError(f'{source} 编队失败')


class NormalFightRunner:
    """常规战斗执行器。"""

    def __init__(
        self,
        ctx: GameContext,
        plan: CombatPlan,
        fleet_selection: ResolvedFleetSelection | None = None,
        *,
        fleet_id: int | None = None,
        fleet: Sequence[str] | None = None,
        fleet_rules: Sequence[FleetSlotRule] | None = None,
    ) -> None:
        validate_fleet_selection_arguments(
            fleet_selection,
            fleet_id=fleet_id,
            fleet=fleet,
            slot_rules=fleet_rules,
        )
        self._ctx = ctx
        self._ctrl = ctx.ctrl
        self._plan = plan
        self._fleet_selection = fleet_selection or resolve_fleet_selection(
            plan,
            fleet_id=fleet_id,
            fleet=fleet,
            slot_rules=fleet_rules,
        )
        self._fleet_id = self._fleet_selection.fleet_id

        # 从 config 读取拆船配置
        self._dock_full_destroy = ctx.config.dock_full_destroy
        self._destroy_ship_types = ctx.config.destroy_ship_types or None

        # chapter 为 E/H → 活动地图入口; 否则常规地图。仅靠 plan 决定导航,
        # event 与 normal 共用本 runner (融合), 复用 normal_fight 触发器。
        self._is_event = str(plan.chapter).upper() in ('E', 'H')

        target_mode = CombatMode.EVENT if self._is_event else CombatMode.NORMAL
        if plan.mode != target_mode:
            _log.info(
                '[OPS] 出击: 计划模式 {} → {} (chapter={})',
                plan.mode,
                target_mode,
                plan.chapter,
            )
            plan.mode = target_mode

        if self._is_event:
            # 推导 UI 层入口 (a→alpha, b→beta) 与活动地图代号 (如 "H1")
            self._entrance: Literal['alpha', 'beta'] | None = {
                'a': 'alpha',
                'b': 'beta',
            }.get(plan.entrance or '')
            self._map_code: str = f'{str(plan.chapter).upper()}{plan.map_id}'
        else:
            self._entrance = None
            self._map_code = ''

        # 仅上一轮 OPERATION_SUCCESS (成功完成战斗, 战后回港必落关卡浮层态)
        # 才跳过难度/节点检查直接出击; 中途打断/失败一律恢复完整检查 (仅 event 分支使用)
        self._skip_check = False

        self._results: list[CombatResult] = []
        self._loot_count: int | None = None
        self._ship_acquired_count: int | None = None
        self._fleet_ships: list[Ship] | None = None

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
        _log.info(
            '[OPS] 常规战: {}-{} ({}), 舰队来源: {}',
            self._plan.chapter,
            self._plan.map_id,
            self._plan.name,
            self._fleet_selection.source,
        )
        try:
            # 1. 进入战斗地图
            self._enter_fight()

            # 2. 出征准备
            ship_stats = self._prepare_for_battle()

            # 同步战前信息到上下文
            self._ctx.sync_before_combat(
                self._fleet_id,
                self._fleet_ships,
                loot_count=self._loot_count,
                ship_acquired_count=self._ship_acquired_count,
            )

            # 3. 执行战斗
            result = self._do_combat(ship_stats)

            # 赋值出征面板识别到的今日获取数量和舰队信息
            result.loot_count = self._loot_count
            result.ship_acquired_count = self._ship_acquired_count
            result.fleet = self._fleet_ships

            # 同步战后信息到上下文
            self._ctx.sync_after_combat(self._fleet_id, result)

            # 4. 处理结果
            self._handle_result(result)
        except Exception:
            # 中途打断 (导航/编队/出征异常): 战后浮层态前提不可知,
            # 下一轮恢复完整检查 (选难度/节点/入口)
            self._skip_check = False
            raise

        # 仅成功完成一场战斗才允许下一轮跳过检查 (战后回港必落关卡浮层态);
        # 其余 (DOCK_FULL 解装 / SL / 次数用尽 / 失败) 浮层态前提破坏, 重新检查
        self._skip_check = result.flag == ConditionFlag.OPERATION_SUCCESS
        return result

    def run_for_times(
        self,
        times: int,
        *,
        gap: float = 0.0,
        **kwargs,
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
        _log.info('[OPS] 常规战连续执行 {} 次', times)
        self._results = []

        for i in range(times):
            _log.info('[OPS] 常规战第 {}/{} 次', i + 1, times)
            result = self.run(**kwargs)
            self._results.append(result)

            if result.flag == ConditionFlag.DOCK_FULL:
                _log.warning('[OPS] 船坞已满, 停止')
                break

            if gap > 0 and i < times - 1:
                time.sleep(gap)

        _log.info(
            '[OPS] 常规战完成: {} 次 (成功 {} 次)',
            len(self._results),
            sum(1 for r in self._results if r.flag == ConditionFlag.OPERATION_SUCCESS),
        )
        return self._results

    def run_for_times_condition(
        self,
        times: int,
        last_point: str,
        *,
        result: str = 'S',
        insist_time: float = 900.0,
    ) -> list[CombatResult] | bool:
        """有战果要求的多次运行。

        循环执行战斗直到满足预设条件。如果最后一个节点的战果未达到要求，
        此次战斗不计入次数。超过指定时间仍未完成则返回 False。

        Parameters
        ----------
        times:
            需要完成的次数。
        last_point:
            最后一个节点（如 "A"、"B" 等）。
        result:
            战果要求（"S"、"A"、"B"、"C"、"D"、"SS"），默认为 "S"。
        insist_time:
            超时时间（秒）。如果超过这个时间仍未完成则返回 False，默认为 900 秒。

        Returns
        -------
        list[CombatResult] | bool
            成功时返回战斗结果列表，超时返回 False。

        Raises
        ------
        ValueError:
            result 或 last_point 值不合法。
        """
        if result.upper() not in ['SS', 'S', 'A', 'B', 'C', 'D']:
            raise ValueError(
                f"战果要求: {result}, 不合法, 应为 'SS','S','A','B','C' 或 'D'",
            )
        if (
            len(last_point) != 1
            or ord(last_point.upper()) > ord('Z')
            or ord(last_point.upper()) < ord('A')
        ):
            raise ValueError(f'最后一个节点: {last_point}, 不合法, 应为A到Z的字母')

        result_list = ['D', 'C', 'B', 'A', 'S', 'SS']
        target_result_index = result_list.index(result.upper())
        start_time = time.time()
        self._results = []
        # 按评级判定是否计入次数 → 战果页需完整采集 (grade/MVP, 慢速通过)
        self._plan.collect_result_info = True

        while times > 0:
            _log.info('[OPS] 条件战斗，剩余次数：{}', times)
            r = self.run()
            self._results.append(r)

            if r.flag == ConditionFlag.DOCK_FULL:
                _log.error('[OPS] 条件战斗，船坞已满，无法继续')
                return self._results

            # 获取最后一个节点的战果
            fight_results = r.fight_results
            if not fight_results:
                _log.warning('[OPS] 条件战斗，未获取到有效战果')
                continue

            last_result = fight_results[-1]
            fight_result_index = result_list.index(last_result.grade)
            # 检查是否满足条件
            finish = (
                last_result.node == last_point.upper() and fight_result_index >= target_result_index
            )

            if not finish:
                _log.info(
                    '[OPS] 不满足预设条件 (节点={}, 战果={}), 此次战斗不计入次数，剩余次数: {}',
                    last_result.node,
                    last_result.grade,
                    times,
                )
                if time.time() - start_time > insist_time:
                    return False
            else:
                start_time = time.time()
                times -= 1
                _log.info(
                    '[OPS] 完成了一次满足预设条件的战斗，剩余次数: {}',
                    times,
                )

        return self._results

    # ── 进入地图 ──

    def _enter_fight(self) -> None:
        """导航到目标地图并进入 (按 chapter 自动选择常规/活动入口)。"""
        if self._is_event:
            self._enter_event()
        else:
            self._enter_normal()

    def _enter_normal(self) -> None:
        """导航到常规出征面板并进入地图。"""
        goto_page(self._ctx, PageName.MAP)
        map_page = MapPage(self._ctx)

        # 在出征面板读取今日已获取数量
        map_page.ensure_panel(MapPanel.SORTIE)
        time.sleep(0.25)
        try:
            counts = map_page.get_loot_and_ship_count()
            self._loot_count = counts.loot
            self._ship_acquired_count = counts.ship
        except RuntimeError:
            _log.warning('[OPS] 无法读取今日获取数量 (OCR 不可用)')

        try:
            map_page.enter_sortie(self._plan.chapter, self._plan.map_id)
        except NavigationError as e:
            _log.error('[OPS] 地图章节导航失败: {}', e)
            _log.warning('[OPS] 已放弃本轮常规战，尝试返回主页面以继续后续队列')
            try:
                goto_page(self._ctx, PageName.MAIN)
            except NavigationError as back_err:
                _log.error('[OPS] 返回主页面失败: {}', back_err)
            raise ActionFailedError('地图章节识别/导航失败，已跳过本轮并返回主页面') from e

    def _enter_event(self) -> None:
        """导航到活动地图页面并完成: 难度切换 → 节点选择 → 入口选择 → 出击。

        弹窗关闭由 UI 层 (:class:`BaseEventPage`) 内部处理。
        """
        goto_page(self._ctx, PageName.EVENT_MAP)
        time.sleep(0.25)
        event_page = BaseEventPage(self._ctx, event_name=self._plan.event_name)
        event_page.start_fight(self._map_code, self._entrance, self._skip_check)

    # ── 出征准备 ──

    def _prepare_for_battle(self) -> list[ShipDamageState]:
        """出征准备: 舰队选择、修理、检测血量。

        Returns
        -------
        list[int]
            战前血量状态。
        """
        time.sleep(1.0)
        page = BattlePreparationPage(self._ctx)

        # 选择舰队
        page.select_fleet(self._fleet_id)
        time.sleep(0.5)

        resolved_ship_names: list[str | None] | None = None

        # 换船规则已经在 runner 启动前完成优先级解析和入口转换。
        slot_rules = self._fleet_selection.slot_rules
        plain_fleet = self._fleet_selection.plain_fleet
        if slot_rules is not None:
            _require_fleet_change(
                page.change_fleet(self._fleet_id, slot_rules),
                'fleet_rules',
            )
            time.sleep(0.5)
            resolved_ship_names = page.last_changed_fleet
        elif plain_fleet is not None:
            _require_fleet_change(
                page.change_fleet(self._fleet_id, exact_fleet_rules(plain_fleet)),
                'fleet',
            )
            time.sleep(0.5)
            resolved_ship_names = page.last_changed_fleet

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
        if ShipDamageState.SEVERE in ship_stats:
            _log.error('[OPS] 出征前检测到大破舰船，退出程序')
            raise ActionFailedError('出征前检测到大破舰船，退出程序')
        ship_names = resolved_ship_names
        if ship_names is None:
            ship_names = self._fleet_selection.primary_names
        self._fleet_ships = fleet_info.to_ships(ship_names)

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
        """处理战斗结果。

        DOCK_FULL 由战斗引擎在 START_FIGHT → DOCK_FULL 转移中检测并返回，
        此处根据配置决定自动解装或保持标志交由上层处理。
        """
        if result.flag == ConditionFlag.DOCK_FULL:
            self._handle_dock_full(result)
            return
        _log.info('[OPS] 常规战结果: {}', result.flag.value)

    def _handle_dock_full(self, result: CombatResult) -> None:
        """船坞已满: 按配置自动解装，并保持 DOCK_FULL 标志。

        解装走弹窗直达路线: 点弹窗「解装」按钮直达解体标签 (不绕主
        菜单/侧边栏导航 — 旧全局导航在 event 场景死循环, 2026-08-16
        实机), 其后复用 destroy_ships, 结束在主页面, 下轮 run 重新
        导航进图出击。

        解装成功**不翻 flag**: 本轮引擎未开打 (node_count=0), 翻成功
        标志会让触发器把未打的轮次计入次数。改置 ``dock_full_destroyed``,
        由触发器/调度器识别"解装完毕、可重试"与"无法解装、须停止"。
        """
        mode = getattr(self._ctx.config, 'dock_full_mode', None)
        if mode is None:
            mode = 1 if self._dock_full_destroy else 0
        mode_val = int(mode)

        if mode_val == 0:
            _log.warning('[OPS] 船坞已满, 未开启自动处理')
            return

        # 模式 2 (强化) 或 模式 3 (自动/先强化后解装): 先执行自动强化
        if mode_val in (2, 3):
            from autowsgr.ops.intensify import auto_intensify

            _log.warning('[OPS] 船坞已满，执行自动强化...')
            try:
                intensify_res = auto_intensify(self._ctx)
                if intensify_res.total_materials_used > 0:
                    _log.info('[OPS] 自动强化完成，消耗 {} 艘素材', intensify_res.total_materials_used)
                    result.dock_full_destroyed = True
            except Exception as e:
                _log.warning('[OPS] 自动强化失败或无可消耗素材: {}', e)

        # 模式 1 (解装) 或 模式 3 (自动/混合): 执行自动解装
        if mode_val in (1, 3):
            from autowsgr.ops.destroy import destroy_ships_auto

            _log.warning('[OPS] 执行自动解装 (弹窗直达)...')
            try:
                destroyed = destroy_ships_auto(self._ctx, from_dialog=True)
                if destroyed:
                    result.dock_full_destroyed = True
            except NavigationError as e:
                _log.error('[OPS] 弹窗直达解装失败: {}, 回退主页面', e)
                try:
                    goto_page(self._ctx, PageName.MAIN)
                except NavigationError as back_err:
                    _log.error('[OPS] 返回主页面失败: {}', back_err)
                return
            return
        # result.flag 保持 DOCK_FULL, 由 run_for_times 终止循环


# ═══════════════════════════════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════════════════════════════


def get_normal_fight_plan(
    yaml_path: str,
    plan_root: str | Path | None = None,
) -> CombatPlan:
    """从 YAML 文件加载出击计划 (常规战或活动)。

    查找顺序: 先 ``normal_fight`` 再 ``event`` (活动 plan, chapter E/H)。
    这样 ``normal_fight_tasks`` 可直接容纳活动计划, 复用 normal_fight 触发器,
    无需为活动单独配置/调用。

    *plan_root* 透传给 :func:`resolve_plan_path`: 用户自定义目录优先于包内默认。
    """
    from autowsgr.infra.file_utils import resolve_plan_path

    last_err: Exception | None = None
    for category in ('normal_fight', 'event'):
        try:
            resolved = resolve_plan_path(
                yaml_path,
                category=category,
                plan_root=plan_root,
            )
        except FileNotFoundError as exc:
            last_err = exc
            continue
        return CombatPlan.from_yaml(resolved)
    raise FileNotFoundError(
        f'找不到计划 {yaml_path!r} (已查找 normal_fight / event)',
    ) from last_err


def run_normal_fight(
    ctx: GameContext,
    plan: CombatPlan,
    *,
    times: int = 1,
    gap: float = 0.0,
    fleet_id: int | None = None,
    fleet: Sequence[str] | None = None,
    fleet_rules: Sequence[FleetSlotRule] | None = None,
    fleet_selection: ResolvedFleetSelection | None = None,
) -> list[CombatResult]:
    """执行常规战的便捷函数。"""
    validate_fleet_selection_arguments(
        fleet_selection,
        fleet_id=fleet_id,
        fleet=fleet,
        slot_rules=fleet_rules,
    )
    resolved_selection = fleet_selection or resolve_fleet_selection(
        plan,
        fleet_id=fleet_id,
        fleet=fleet,
        slot_rules=fleet_rules,
    )
    runner = NormalFightRunner(
        ctx,
        plan,
        resolved_selection,
    )
    return runner.run_for_times(times, gap=gap)


def run_normal_fight_from_yaml(
    ctx: GameContext,
    yaml_path: str,
    *,
    times: int = 1,
    fleet_id: int | None = None,
    fleet: Sequence[str] | None = None,
    fleet_rules: Sequence[FleetSlotRule] | None = None,
    plan_root: str | Path | None = None,
) -> list[CombatResult]:
    """从 YAML 文件加载计划并执行常规战。

    *yaml_path* 支持以下格式:

    - 绝对路径 / 相对路径: 直接加载。
    - 策略名称 (如 ``"7-4千伪"``): 按 :func:`resolve_plan_path` 的优先级查找 ——
      若指定 *plan_root* 先在其中查找 (``{plan_root}/normal_fight/``), 未命中再
      回退到 ``autowsgr/data/plan/normal_fight/`` 包数据目录; 可省略 ``.yaml`` 后缀。
    """
    plan = get_normal_fight_plan(yaml_path, plan_root=plan_root)
    return run_normal_fight(
        ctx,
        plan,
        times=times,
        fleet_id=fleet_id,
        fleet=fleet,
        fleet_rules=fleet_rules,
    )
