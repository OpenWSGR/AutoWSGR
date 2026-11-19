"""决战过程控制器（状态机核心）。

``DecisiveController`` 是决战的最高层编排器，**不直接执行任何 UI 操作**，
而是通过以下下层控制器的接口组装完整流程：

- :class:`~autowsgr.ui.decisive.map_controller.DecisiveMapController`
  — 决战地图页所有交互（overlay 处理、出征、撤退、节点间修理）
- :class:`~autowsgr.ui.decisive.preparation.DecisiveBattlePreparationPage`
  — 出征准备页操作（编队、修理、开始战斗）
- :class:`~autowsgr.ui.decisive.battle_page.DecisiveBattlePage`
  — 决战总览页操作（章节导航、重置）

继承体系::

    DecisiveBase                           ← base.py   (成员声明 & 初始化)
    ├── DecisiveChapterOps(DecisiveBase)   ← chapter.py (章节管理)
    ├── DecisivePhaseHandlers(DecisiveBase)← handlers.py (阶段处理器)
    └── DecisiveController(                ← 本文件      (状态机编排)
            DecisivePhaseHandlers,
            DecisiveChapterOps,
        )
"""

from __future__ import annotations

import enum
from dataclasses import replace
from typing import TYPE_CHECKING

from autowsgr.infra import ActionFailedError, DockFullError
from autowsgr.infra.logger import get_logger
from autowsgr.ops.decisive.chapter import DecisiveChapterOps
from autowsgr.ops.decisive.handlers import DecisivePhaseHandlers
from autowsgr.ops.decisive.repair import RepairOutcome, RepairStatus
from autowsgr.types import DecisiveEntryStatus, DecisivePhase, ShipDamageState
from autowsgr.ui.decisive import DecisiveBattlePreparationPage


if TYPE_CHECKING:
    from autowsgr.ui.decisive.preparation import RepairSnapshot


_log = get_logger('ops.decisive')

# ─────────────────────────────────────────────────────────────────────────────
# 结果枚举
# ─────────────────────────────────────────────────────────────────────────────


class DecisiveResult(enum.Enum):
    """单轮结果。NODE_COMPLETE 和 RETRY 只在调度器内部流转。"""

    NODE_COMPLETE = 'node_complete'
    RETRY = 'retry'

    CHAPTER_CLEAR = 'chapter_clear'
    """大关通关 (3 个小关全部完成)。"""

    RETREAT = 'retreat'
    """主动撤退 (清空进度)。"""

    LEAVE = 'leave'
    """暂离保存 (保留进度退出)。"""

    ERROR = 'error'
    """异常退出。"""

    STOPPED = 'stopped'
    """收到停止请求；不代表战斗完成或节点推进。"""


# ─────────────────────────────────────────────────────────────────────────────
# 组装控制器
# ─────────────────────────────────────────────────────────────────────────────


class DecisiveController(DecisivePhaseHandlers, DecisiveChapterOps):
    """决战过程控制器（状态机核心）。

    通过多重继承组合:
    - :class:`DecisivePhaseHandlers` — 所有阶段处理器
    - :class:`DecisiveChapterOps` — 章节管理操作

    两者均继承 :class:`~autowsgr.ops.decisive.base.DecisiveBase`，
    成员初始化由 ``DecisiveBase.__init__`` 统一完成。
    """

    # ── 主入口 ────────────────────────────────────────────────────────────

    def run(self) -> DecisiveResult:
        """执行一轮完整决战（3 个小关）。"""
        if self._ctx.stop_event.is_set():
            return DecisiveResult.STOPPED
        _log.info('[决战] 开始第 {} 章决战', self._config.chapter)
        self._close_tracking()
        self._known_start_stage = None
        self._state.reset()
        # 进入已有进度和重新开局都需要核实库存，确定 A 不能代替库存观察。
        self._inventory_refresh_required = True
        self._has_chosen_fleet = False
        self._repairs.reset_stage()
        self._scheduled_repair = None
        self._after_settlement = None
        self._map.reset_settlement()
        self._resume_outcome = None
        self._failures = 0
        try:
            return self._main_loop()
        except Exception:
            if self._ctx.stop_event.is_set():
                return DecisiveResult.STOPPED
            _log.exception('[决战] 调度中断，保留当前进度')
            self._log_failure_screen(1)
            return DecisiveResult.ERROR
        finally:
            self._close_tracking()

    def _resume_interrupted_sortie(self) -> bool:
        """冷启动时先检查进度现场。暂离后只允许进入同一章节的存档。"""
        try:
            if not self._map.try_leave_interrupted_sortie():
                return False
            status, screen = self._battle_page.wait_for_entry_status()
            chapter = self._config.chapter
            if (
                status not in (DecisiveEntryStatus.CHALLENGING, DecisiveEntryStatus.REFRESHED)
                or self._battle_page._read_chapter(screen) != chapter
            ):
                raise ActionFailedError('恢复决战', '暂离后未确认目标章节的存档入口')
            stage = self._battle_page.detect_stage(screen, chapter)
            self._enter_verified_stage(stage)
            _log.info('[决战] 已从中断现场暂离，继续第 {} 章第 {} 小关', chapter, stage)
        except (ActionFailedError, InterruptedError):
            raise
        except Exception as exc:
            # 返回或暂离可能已经生效，不能从新画面按普通入口重试或重置章节。
            raise ActionFailedError('恢复决战', str(exc)) from exc
        return True

    def _log_failure_screen(self, attempt: int) -> None:
        """只在识别或操作失败时保存现场，方便按日志还原问题。"""
        from autowsgr.infra.logger import save_image

        log_dir = self._ctx.config.log.dir
        if log_dir:
            try:
                save_image(self._ctrl.screenshot(), f'decisive-error-{attempt}', log_dir / 'images')
            except Exception as exc:
                _log.warning('[决战] 保存异常现场失败：{}', exc)

    def _recover_phase(self) -> None:
        """重试时按当前页面继续；已进入战果、通关结算或等待维修的，接着处理原步骤。"""
        phase = self._state.phase
        self._inventory_refresh_required = True
        if phase in {DecisivePhase.NODE_RESULT, DecisivePhase.STAGE_CLEAR}:
            return
        if phase in (DecisivePhase.INIT, DecisivePhase.WAITING_FOR_REPAIR):
            return
        if self._state.navigate_to_entry:
            return
        if phase in {DecisivePhase.IN_COMBAT, DecisivePhase.RETREAT, DecisivePhase.LEAVE}:
            raise ActionFailedError('无法确认战斗或退出操作是否生效，保留现场')
        screen = self._ctrl.capture_frame().image
        if self._battle_page.is_current_page(screen):
            self._state.phase = DecisivePhase.ENTER_MAP
            return
        if self._map.is_fleet_preparation(screen):
            page = DecisiveBattlePreparationPage(self._ctx, self._config, self._ocr)
            page.go_back()
        observed = self._map.detect_decisive_phase()
        if observed is None:
            raise RuntimeError('异常恢复未能确认当前决战页面')
        self._state.phase = observed

    def _repair_snapshot(
        self, page: DecisiveBattlePreparationPage, *, fresh: bool = False
    ) -> RepairSnapshot:
        target = self._state.fleet.copy()
        return self._repairs.read_complete_snapshot(
            page,
            expected=target[1:],
            fresh=fresh,
            recheck_fleet=lambda: self._verify_prepared_fleet(page, target, force_change=True),
        )

    def _observe_repairs(
        self, page: DecisiveBattlePreparationPage, snapshot: RepairSnapshot | None = None
    ) -> RepairSnapshot:
        if snapshot is None:
            snapshot = self._repairs.read_complete_snapshot(
                page, fresh=bool(self._repairs.due_identities)
            )
        names, damage = snapshot
        self._repairs.observe_inventory(
            self._state.ships,
            chapter=self._state.chapter,
            stage=self._state.stage,
            damage={name: damage[i] for i, name in enumerate(names) if name},
        )
        self._state.fleet = [''] + [name or '' for name in names]
        self._state.ship_stats = [damage[i] for i in range(6)]
        return names, damage

    def _leave_for_repairs(self, page: DecisiveBattlePreparationPage | None) -> None:
        self._repairs.save_progress(page, self._map)
        self._state.expected_stage = self._state.stage
        self._state.at_node_boundary = False
        self._state.node_completed = False
        self._route_repair(RepairOutcome(RepairStatus.NEEDS_BATH))

    def _prepare_repairs(
        self, page: DecisiveBattlePreparationPage, snapshot: RepairSnapshot | None = None
    ) -> bool:
        names, damage = snapshot if snapshot is not None else self._repair_snapshot(page)
        target = self._state.fleet.copy()
        result = self._repairs.prepare(
            page,
            fleet=names,
            damage=damage,
            acquired=self._state.ships,
            chapter=self._state.chapter,
            stage=self._state.stage,
            recheck_fleet=lambda: self._verify_prepared_fleet(page, target, force_change=True),
        )
        if result.status is RepairStatus.READY:
            if result.snapshot is not None:
                names, damage = result.snapshot
            if any(
                i not in damage
                or (damage[i] is ShipDamageState.NO_SHIP) != (not name)
                or damage[i] >= self._config.repair_level
                for i, name in enumerate(names)
            ):
                raise RuntimeError('决战出征前未确认全部舰位可用')
            self._state.ship_stats = [
                damage[i] if name else ShipDamageState.NO_SHIP for i, name in enumerate(names)
            ]
            self._sync_ship_states()
            return True
        if result.status is RepairStatus.NEEDS_BATH:
            self._leave_for_repairs(page)
        else:
            self._route_repair(result)
        return False

    def _route_repair(self, result: RepairOutcome) -> None:
        if result.status is RepairStatus.STOPPED or self._ctx.stop_event.is_set():
            self._state.phase = DecisivePhase.FINISHED
        elif result.status is RepairStatus.REENTER:
            if self._after_settlement is not None:
                phase = self._after_settlement
                self._repairs.reset_stage()
                self._after_settlement = None
                self._state.phase = phase
            else:
                self._state.phase = DecisivePhase.ENTER_MAP
                self._state.expected_stage = self._state.stage
            self._state.navigate_to_entry = self._state.phase is DecisivePhase.ENTER_MAP
            self._inventory_refresh_required = True
        elif result.status in (RepairStatus.WAITING, RepairStatus.NEEDS_BATH):
            self._scheduled_repair = replace(
                result, resume_immediately=self._repairs.can_continue_without_pending
            )
            self._state.phase = DecisivePhase.WAITING_FOR_REPAIR
        else:
            ships = '、'.join(result.targets)
            action = f'复核待修舰船（{ships}）' if ships else '复核决战编队'
            raise ActionFailedError(action, result.detail)

    def _next_repair(self) -> RepairOutcome:
        """先执行本次暂离请求；后续复查按各舰船的到期时间安排。"""
        if self._scheduled_repair is not None:
            result = self._scheduled_repair
            self._scheduled_repair = None
            return result
        return self._repairs.poll()

    def run_for_times(self, times: int = 1) -> list[DecisiveResult]:
        """执行多轮决战；未完成一轮时停止，不重新开始或清空进度。"""
        results: list[DecisiveResult] = []
        for i in range(times):
            _log.info('[决战] 第 {}/{} 轮', i + 1, times)
            result = self.run()
            results.append(result)
            if result != DecisiveResult.CHAPTER_CLEAR:
                _log.warning('[决战] 第 {} 轮终止: {}', i + 1, result.value)
                break
        return results

    # ── 主循环 ────────────────────────────────────────────────────────────

    def _main_loop(self) -> DecisiveResult:
        """同一控制器的多轮决战共用日常触发器和就绪队列。"""
        from autowsgr.scheduler import TaskScheduler

        if self._scheduler is None:
            self._scheduler = TaskScheduler.for_decisive(self._ctx, user_config=self._settings)
        return self._scheduler.run_decisive(
            self._advance_node,
            self._next_repair,
            self._repairs.dispatch_pending,
            self._resume_from_queue,
            park=self._park_for_daily,
        )

    def _resume_from_queue(self, outcome: RepairOutcome) -> None:
        self._resume_outcome = outcome

    def _park_for_daily(self) -> bool:
        """只有总览或已核实的节点地图能把页面交给其他任务。"""
        phase = self._state.phase
        if self._failures:
            return False
        if phase is DecisivePhase.INIT:
            from autowsgr.ui.main_page import MainPage

            screen = self._ctrl.screenshot()
            return bool(
                self._battle_page.is_current_page(screen) or MainPage.is_current_page(screen)
            )
        if phase is DecisivePhase.WAITING_FOR_REPAIR:
            return self._repairs.saved
        if phase is DecisivePhase.ENTER_MAP:
            self._state.navigate_to_entry = True
            return True
        if not self._state.at_node_boundary:
            return False
        self._map.leave_to_overview()
        self._state.expected_stage = self._state.stage
        self._state.at_node_boundary = False
        self._state.navigate_to_entry = True
        self._state.phase = DecisivePhase.ENTER_MAP
        self._inventory_refresh_required = True
        _log.info(
            '[决战] 已在 {}-{}-{} 暂离，先处理排在前面的任务',
            self._state.chapter,
            self._state.stage,
            self._state.node,
        )
        return True

    def _advance_node(self) -> DecisiveResult | None:
        """从实际页面续行，连续三次未能恢复就保留现场。"""
        try:
            if self._failures:
                self._recover_phase()
            if self._state.phase is DecisivePhase.INIT and not self._resume_interrupted_sortie():
                self._prepare_entry_state()
                self._state.phase = DecisivePhase.ENTER_MAP
            if self._resume_outcome is not None:
                outcome, self._resume_outcome = self._resume_outcome, None
                self._route_repair(outcome)
            if self._state.navigate_to_entry:
                self._prepare_entry_state()
                self._state.navigate_to_entry = False
                if self._tracking is not None:
                    self._tracking.request_node_sample('暂离后重新核实当前节点')
            result = self._advance_until_repair()
        except Exception as exc:
            if self._ctx.stop_event.is_set():
                return DecisiveResult.STOPPED
            self._failures += 1
            self._state.at_node_boundary = False
            _log.exception('[决战] 第 {}/3 次尝试失败，保留当前节点', self._failures)
            self._log_failure_screen(self._failures)
            if self._failures == 3 or isinstance(exc, (ActionFailedError, DockFullError)):
                return DecisiveResult.ERROR
            return DecisiveResult.RETRY
        self._failures = 0
        return result

    def _finish_node(self) -> bool:
        """已结算的战斗，等到下一节点地图或小关总览再交回队列。"""
        if self._state.phase is DecisivePhase.PREPARE_COMBAT:
            if not self._prepare_map_tracking():
                return False
            if self._repairs.needs_dispatch:
                self._leave_for_repairs(None)
                return False
            self._state.at_node_boundary = True
        elif self._state.phase is not DecisivePhase.ENTER_MAP:
            return False
        self._state.node_completed = False
        return True

    def _advance_until_repair(self) -> DecisiveResult | None:
        """最多打一个节点，处理完战备、选路和奖励后交回调度器。"""
        _handlers = {
            DecisivePhase.ENTER_MAP: self._handle_enter_map,
            DecisivePhase.WAITING_FOR_MAP: self._handle_waiting_for_map,
            DecisivePhase.USE_LAST_FLEET: self._handle_use_last_fleet,
            DecisivePhase.DOCK_FULL: self._handle_dock_full,
            DecisivePhase.CHOOSE_FLEET: self._handle_choose_fleet,
            DecisivePhase.ADVANCE_CHOICE: self._handle_advance_choice,
            DecisivePhase.PREPARE_COMBAT: self._handle_prepare_combat,
            DecisivePhase.IN_COMBAT: self._handle_combat,
            DecisivePhase.NODE_RESULT: self._handle_node_result,
            DecisivePhase.STAGE_CLEAR: self._handle_stage_clear,
        }

        while not self._ctx.stop_event.is_set():
            phase = self._state.phase
            if phase is DecisivePhase.WAITING_FOR_REPAIR:
                return None
            if self._state.node_completed:
                if self._finish_node():
                    return DecisiveResult.NODE_COMPLETE
                if self._state.phase is not phase:
                    continue

            # WAITING_FOR_MAP 太频繁，只在非等待阶段打日志
            if phase != DecisivePhase.WAITING_FOR_MAP:
                _log.debug(
                    '[决战] 阶段: {} | 小关: {} | 节点: {}',
                    phase.name,
                    self._state.stage,
                    self._state.node,
                )

            handler = _handlers.get(phase)
            if handler is None:
                return self._finish_attempt(phase)
            handler()

        return DecisiveResult.STOPPED

    def _finish_attempt(self, phase: DecisivePhase) -> DecisiveResult:
        if phase is DecisivePhase.RETREAT:
            self._execute_retreat()
            self._repairs.reset_stage()
            self._state.reset()
            self._state.phase = DecisivePhase.ENTER_MAP
            return DecisiveResult.NODE_COMPLETE
        if phase is DecisivePhase.LEAVE:
            self._execute_leave()
            result = DecisiveResult.LEAVE
        elif phase is DecisivePhase.CHAPTER_CLEAR:
            _log.info('[决战] 大关通关!')
            result = DecisiveResult.CHAPTER_CLEAR
        else:
            _log.error('[决战] 无法继续，当前阶段为 {}', phase)
            result = DecisiveResult.ERROR
        self._state.phase = DecisivePhase.FINISHED
        return result
