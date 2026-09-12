"""决战状态机的阶段处理器。

所有 ``_handle_*`` 方法在此模块中实现，
继承 :class:`~autowsgr.ops.decisive.base.DecisiveBase`。

.. note::

    部分方法 (``_prepare_entry_state``, ``_do_dock_full_destroy``)
    由 :class:`~autowsgr.ops.decisive.chapter.DecisiveChapterOps`
    提供，通过最终组装类 :class:`~autowsgr.ops.decisive.controller.DecisiveController`
    的 MRO 解析。
"""
# TODO 状态机建模一坨，之后再改

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from autowsgr.combat.actions import click_result
from autowsgr.combat.engine import run_combat
from autowsgr.combat.plan import CombatMode, CombatPlan, NodeDecision
from autowsgr.constants import DECISIVE_SKILL_NAMES
from autowsgr.infra.logger import get_logger
from autowsgr.ops.decisive.base import DecisiveBase
from autowsgr.ops.decisive.config import MapData
from autowsgr.ops.navigate import goto_bath_from_decisive_sortie
from autowsgr.ops.repair import repair_manual_targets_in_bath
from autowsgr.types import (
    ConditionFlag,
    DecisiveEntryStatus,
    DecisivePhase,
    FleetSelection,
    ShipDamageState,
)
from autowsgr.ui import RepairStrategy
from autowsgr.ui.decisive import DecisiveBattlePreparationPage
from autowsgr.ui.decisive.overlay import ADVANCE_CHOICE_ROI, ADVANCE_CHOICE_THREE_ROI


if TYPE_CHECKING:
    import numpy as np

    from autowsgr.vision import ROI


_log = get_logger('ops.decisive')


class DecisivePhaseHandlers(DecisiveBase):
    # ── 状态同步 ──────────────────────────────────────────────────────────

    def _recognize_fleet_options_with_retry(
        self,
        fallback_score: int | None,
        attempts: int = 3,
    ) -> tuple[np.ndarray, int, dict[str, FleetSelection]]:
        """仅在购买界面内重试 OCR；若界面已关闭则不再尝试回到该界面。"""
        screen = self._map.wait_for_fleet_overlay_stable()
        last_score = fallback_score or 0
        last_selections: dict[str, FleetSelection] = {}

        for attempt in range(1, attempts + 1):
            score, selections = self._map.recognize_fleet_options(
                screen,
                fallback_score=fallback_score,
            )
            if score:
                last_score = score
            last_selections = selections
            if selections:
                return screen, last_score, selections
            if not self._map.is_fleet_overlay_open():
                raise RuntimeError('战备舰队界面已关闭，无法继续在该界面重试 OCR')
            if attempt < attempts:
                _log.warning(
                    '[决战] 战备舰队 OCR 无结果，第 {} 次重试',
                    attempt,
                )
                screen = self._map.wait_for_fleet_overlay_stable(timeout=3.0)

        return screen, last_score, last_selections

    def _sync_ship_states(self) -> None:
        """将 ship_stats 同步到 ctx.ship_registry。"""
        for i, stat in enumerate(self._state.ship_stats):
            idx = i + 1
            if idx < len(self._state.fleet):
                name = self._state.fleet[idx]
                if name and stat != ShipDamageState.NO_SHIP:
                    self._ctx.update_ship_damage(name, stat)

    def _advance_choices(self) -> list[str]:
        source_node = getattr(self, '_advance_source_node', None)
        if source_node is None:
            source_node = self._state.node if self._state.node != 'U' else '0'
        choices = MapData.get_leftmost_choices(
            self._config.chapter,
            self._state.stage,
            source_node,
        )
        _log.debug(
            '[决战] 路线选择: source={} choices={}',
            source_node,
            choices,
        )
        return choices

    def _advance_choice_roi(self) -> ROI | None:
        if getattr(self, '_advance_source_node', None) is None and self._state.node == 'U':
            return None
        choice_count = len(self._advance_choices())
        if choice_count == 3:
            return ADVANCE_CHOICE_THREE_ROI
        if choice_count == 2:
            return ADVANCE_CHOICE_ROI
        return None

    """决战阶段处理器子类。

    包含所有 ``_handle_<phase>`` 方法:

    进入与等待
        :meth:`_handle_enter_map`, :meth:`_handle_waiting_for_map`,
        :meth:`_handle_use_last_fleet`, :meth:`_handle_dock_full`

    舰队与地图
        :meth:`_handle_advance_choice`

    战斗
        :meth:`_handle_prepare_combat`, :meth:`_handle_combat`

    结果
        :meth:`_handle_node_result`, :meth:`_handle_stage_clear`

    撤退
        :meth:`_execute_retreat`, :meth:`_execute_leave`
    """

    # ── 进入与等待 ────────────────────────────────────────────────────────

    def _handle_enter_map(self) -> None:
        """检测入口状态 → 按需重置 → 点击进入地图 → 转到 WAITING_FOR_MAP。

        通过 :meth:`DecisiveBattlePage.detect_entry_status` 识别当前章节的
        入口状态，根据 :class:`~autowsgr.types.DecisiveEntryStatus` 分别处理:

        - ``REFRESH``: 使用磁盘重置关卡后重新检测
        - ``REFRESHED``: 有存档进度，直接进入地图 (后续会弹出使用上次舰队)
        - ``CHALLENGING``: 挑战中，直接进入地图
        - ``CANT_FIGHT``: 无法出击，抛出异常
        """
        entry_status = self._battle_page.detect_entry_status()

        if entry_status == DecisiveEntryStatus.REFRESH:
            _log.info('[决战] 检测到「重置关卡」状态，执行章节重置')
            reset_success = self._battle_page.reset_chapter()
            if not reset_success:
                # 重置不成功是因为需要解装
                self._state.phase = DecisivePhase.DOCK_FULL
                return
            # 重置后重新检测入口状态
            entry_status = self._battle_page.detect_entry_status()

        if entry_status == DecisiveEntryStatus.CANT_FIGHT:
            raise RuntimeError(
                f'决战 Ex-{self._config.chapter}: 入口状态为「无法出击」，其他关卡正在进行中'
            )

        _log.info('[决战] 入口状态: {}', entry_status.value)

        stage = self._battle_page.detect_stage(
            self._ctrl.screenshot(),
            self._config.chapter,
        )
        if stage == 0:
            raise RuntimeError(f'决战 Ex-{self._config.chapter}: 无法识别有效小节')
        if stage is None:
            _log.info('[决战] Ex-{} 三个小节均已完成，结束本轮', self._config.chapter)
            self._state.phase = DecisivePhase.CHAPTER_CLEAR
            return
        self._state.stage = stage
        if self._config.chapter == 1:
            self._resume_mode = False
            _log.info(
                '[决战] Ex-1 总览页仅识别小节号: stage={}，首次进入/恢复模式改由进图后节点判定',
                self._state.stage,
            )
        self._battle_page.click_enter_map()
        self._use_last_fleet_attempts = 0
        self._skip_advance_choice = False
        self._advance_source_node = None
        self._wait_deadline = time.monotonic() + 15.0
        self._state.phase = DecisivePhase.WAITING_FOR_MAP

    def _handle_waiting_for_map(self) -> None:
        """等待地图页加载: 单次截图检测 → 转到对应阶段或继续等待。"""
        wait_for_advance = not self._skip_advance_choice
        full_recovery_check = getattr(self, '_full_recovery_check', False)
        entry_kwargs = {
            'wait_for_use_last': self._use_last_fleet_attempts == 0,
            'wait_for_advance': wait_for_advance,
            'wait_for_fleet': self._fleet_overlay_enabled
            and (
                full_recovery_check
                or self._advance_source_node is not None
                or self._skip_advance_choice
            ),
            'timeout': 3.0,
            'interval': 0.2,
        }
        if (advance_choice_roi := self._advance_choice_roi()) is not None:
            entry_kwargs['advance_choice_roi'] = advance_choice_roi
        phase = self._map.wait_for_entry_phase(
            **entry_kwargs,
        )
        self._skip_advance_choice = False

        if (
            phase is DecisivePhase.PREPARE_COMBAT
            and wait_for_advance
            and self._advance_source_node is None
            and not full_recovery_check
        ):
            _log.info('[决战] 未检测到前进点弹窗，按暂离恢复处理，关闭战备浮窗识别')
            self._fleet_overlay_enabled = False

        if phase is not None:
            self._state.phase = phase

        # 未检测到已知状态 — 重试或超时
        if time.monotonic() >= self._wait_deadline:
            raise TimeoutError('等待地图页或 overlay 超时')
        time.sleep(0.05)

    def _handle_use_last_fleet(self) -> None:
        """点击「使用上次舰队」按钮 → 转到 WAITING_FOR_MAP。"""
        self._use_last_fleet_attempts += 1
        if self._use_last_fleet_attempts > 5:
            raise TimeoutError('选择决战舰船失败 (超过 5 次尝试)')

        _log.info(
            '[决战] 「使用上次舰队」第 {} 次尝试',
            self._use_last_fleet_attempts,
        )
        self._map.click_use_last_fleet()
        self._wait_deadline = time.monotonic() + 10.0
        self._state.phase = DecisivePhase.WAITING_FOR_MAP

    def _handle_dock_full(self) -> None:
        """船坞已满: 自动解装 → ENTER_MAP。"""
        _log.warning('[决战] 处理船坞已满')
        self._do_dock_full_destroy()  # type: ignore[attr-defined]  # from DecisiveChapterOps
        self._prepare_entry_state()  # type: ignore[attr-defined]  # from DecisiveChapterOps
        self._state.phase = DecisivePhase.ENTER_MAP

    # ── 舰队与地图 ────────────────────────────────────────────────────────

    def _handle_choose_fleet(self) -> None:
        """战备舰队获取：OCR 识别选项 → 购买决策 → 关闭弹窗。"""
        self._has_chosen_fleet = False
        self._force_fleet_scan = False

        _log.info('[决战] 战备舰队获取')
        screen, score, selections = self._recognize_fleet_options_with_retry(
            fallback_score=self._state.score,
        )
        self._state.score = score or self._state.score
        to_buy: list[str] = []

        if selections:
            first_node = self._state.is_begin()
            if first_node:
                last_name = self._map.detect_last_offer_name(screen)
                if last_name in {'长跑训练', '肌肉记忆', '黑科技'}:
                    _log.info('[决战] 首节点判定修正: 最后一项为技能')
                    first_node = False

            to_buy = self._logic.choose_ships(selections, first_node=first_node)

            if not to_buy:
                self._map.refresh_fleet()
                screen, score, selections = self._recognize_fleet_options_with_retry(
                    fallback_score=self._state.score,
                )
                self._state.score = score or self._state.score
                to_buy = self._logic.choose_ships(
                    selections,
                    first_node=first_node,
                )

        _log.info('[决战] 选择购买: {}', to_buy)
        for name in to_buy:
            sel = selections[name]
            self._map.buy_fleet_option(sel.click_position)
            if name not in {'长跑训练', '肌肉记忆', '黑科技'}:
                self._state.ships.add(name)

        if not self._map.close_fleet_overlay():
            if to_buy:
                _log.warning('[决战] 已购买配置舰船但关闭选船界面失败, 准备撤退')
                self._state.phase = DecisivePhase.RETREAT
                return

            fallback_options = [
                (name, selection)
                for name, selection in selections.items()
                if name not in DECISIVE_SKILL_NAMES
            ]
            if not fallback_options:
                raise TimeoutError('未购买配置舰船且没有可用的舰船兜底卡')

            fallback_name, fallback = min(fallback_options, key=lambda item: item[1].cost)
            _log.info(
                '[决战] 首次关闭失败且未购买配置舰船, 选择最低费兜底舰船: {} (费用={})',
                fallback_name,
                fallback.cost,
            )
            self._map.buy_fleet_option(fallback.click_position)
            self._state.ships.add(fallback_name)
            if not self._map.close_fleet_overlay():
                raise TimeoutError('选择兜底舰船后仍无法关闭战备舰队弹窗')
            self._state.phase = DecisivePhase.RETREAT
            return

        if not to_buy:
            _log.info('[Decisive] defer current-fleet sufficiency check to preparation')
            self._force_fleet_scan = True

        self._has_chosen_fleet = True
        self._state.phase = DecisivePhase.PREPARE_COMBAT

    def _handle_advance_choice(self) -> None:
        """选择前进点。"""
        _log.info('[决战] 选择前进点')
        if (advance_choice_roi := self._advance_choice_roi()) is None:
            self._map.select_advance_card(0)
        else:
            self._map.select_advance_card(0, advance_choice_roi=advance_choice_roi)
        self._advance_source_node = None
        self._wait_deadline = time.monotonic() + 10.0
        self._skip_advance_choice = True
        self._state.phase = DecisivePhase.WAITING_FOR_MAP

    # ── 战斗 ──────────────────────────────────────────────────────────────

    def _handle_prepare_combat(self) -> None:  # noqa: PLR0912, PLR0915
        """出征准备：编队 → 修理 → 出征。"""
        screen = self._ctrl.screenshot()

        # 某些情况下地图页识别会先于 overlay 稳定，导致实际上仍停留在
        # 「战备舰队获取 / 前进点选择」时就误入 PREPARE_COMBAT。
        # 这里补一次即时探测，优先回到正确阶段，避免后续直接点“编队”超时。
        overlay_phase = self._map.detect_decisive_phase(
            screen,
            advance_choice_roi=self._advance_choice_roi(),
            allow_fleet_overlay=self._fleet_overlay_enabled,
        )
        if overlay_phase in (DecisivePhase.CHOOSE_FLEET, DecisivePhase.ADVANCE_CHOICE):
            _log.info('[决战] 出征准备前检测到 overlay，切回阶段: {}', overlay_phase.name)
            self._state.phase = overlay_phase
            return

        if self._state.node == 'U':
            # 初次进入都要进行节点识别
            recognized_node = self._map.recognize_node()
            if recognized_node == 'CHOOSE_FLEET':
                _log.info('[决战] 检测到战备舰队获取页面')
                self._state.phase = DecisivePhase.CHOOSE_FLEET
                return
            self._state.node = recognized_node
            _log.info(
                '[决战] 当前进入为章节 {} 小节 {} 的 {} 列',
                self._config.chapter,
                self._state.stage,
                recognized_node,
            )
        _log.info(
            '[决战] 出征准备 (小关 {} 节点 {})',
            self._state.stage,
            self._state.node,
        )

        # ── 恢复模式检测 ─────────────────────────────────────────────
        # 恢复模式逻辑修改，默认进入恢复模式，如果是首节点，则不进入恢复模式
        full_recovery_check = getattr(self, '_full_recovery_check', False)
        if self._state.is_begin() and not self._force_fleet_scan and not full_recovery_check:
            self._resume_mode = False
            _log.info(
                '[决战] 检测到恢复模式 (节点={}, has_chosen_fleet={})',
                self._state.node,
                self._has_chosen_fleet,
            )

        # 先使用技能，再注册舰船，如果是未知节点，也判定一下技能是否使用
        current_node = self._state.node
        time.sleep(0.5)  # 等待动画稳定后截图判定
        skill_used = self._map.is_skill_used()
        _log.debug('[决战] 节点: {}, 技能已使用检测: {}', current_node, skill_used)

        if not skill_used:
            gained = self._map.use_skill()
            _log.debug('[决战] 执行技能使用获得: {}', gained)
            if gained:
                if self._config.useful_skill and not self._logic.check_useful_skill(gained):
                    _log.info('[决战] 技能获得: {}, 效果不佳，撤退重试', gained)
                    self._state.phase = DecisivePhase.RETREAT
                    return
                self._state.ships.update(gained)
        else:
            _log.debug('[决战] 跳过技能使用: 节点={}, 技能已使用={}', current_node, skill_used)

        # 首次进入且尚未选择过舰队时，使用技能后可能出现战备舰队获取 overlay，
        # 先切回 WAITING_FOR_MAP 等待 overlay 稳定，避免直接点击编队超时。
        if not skill_used and not self._has_chosen_fleet:
            _log.info('[决战] 首次进入，使用技能后等待 overlay 稳定')
            self._wait_deadline = time.monotonic() + 10.0
            self._state.phase = DecisivePhase.WAITING_FOR_MAP
            return

        # ── 恢复模式: 扫描当前舰队与可用舰船 ─────────────────────────
        # 对齐 legacy: if fleet.empty() and not is_begin(): _check_fleet()
        formation_ready = False
        if self._resume_mode or self._force_fleet_scan or full_recovery_check:
            _log.info('[决战] 恢复模式: 扫描当前舰队')
            fleet, damage, all_ships = self._map.check_fleet(
                scan_ship_pool=full_recovery_check,
            )
            formation_ready = True
            self._state.ship_stats = [damage.get(i, ShipDamageState.NORMAL) for i in range(6)]
            self._state.ships.update(all_ships)
            # 将编队成员写入 state.fleet[1:]
            for i, name in enumerate(fleet):
                if i < 6:
                    self._state.fleet[i + 1] = name or ''
            self._force_fleet_scan = False
            self._sync_ship_states()
            self._resume_mode = False  # 扫描完成后退出恢复模式

        best_fleet = self._logic.get_best_fleet()
        if self._logic.should_retreat(best_fleet):
            _log.info('[决战] 舰船不足, 准备撤退')
            self._state.phase = DecisivePhase.RETREAT
            return

        if not formation_ready:
            self._map.enter_formation()
            time.sleep(0.5)  # 等待编队页加载完成（对齐 check_fleet 的做法）
        page = DecisiveBattlePreparationPage(self._ctx, self._config, self._ocr)

        current_fleet = self._state.fleet[:]
        if current_fleet != best_fleet:
            page.change_fleet(None, best_fleet[1:])
            self._state.fleet = best_fleet
        else:
            self._state.fleet = best_fleet

        strategy = (
            RepairStrategy.MODERATE if self._config.repair_level <= 1 else RepairStrategy.SEVERE
        )
        if self._config.use_quick_repair:
            page.apply_repair(strategy)
        else:

            def manual_repair_action(positions: list[int]) -> None:
                targets = [
                    self._state.fleet[position + 1]
                    for position in positions
                    if 0 <= position + 1 < len(self._state.fleet)
                    and self._state.fleet[position + 1]
                ]
                goto_bath_from_decisive_sortie(self._ctx)
                repair_manual_targets_in_bath(self._ctx, targets)

            page.apply_repair(
                strategy,
                repair_manually=True,
                manual_repair_action=manual_repair_action,
            )

        screen = self._ctrl.screenshot()
        damage = page.detect_ship_damage(screen)
        self._state.ship_stats = [damage.get(i, ShipDamageState.NORMAL) for i in range(6)]
        self._sync_ship_states()

        page.start_battle()
        time.sleep(1.0)
        self._full_recovery_check = False
        self._state.phase = DecisivePhase.IN_COMBAT

    def _handle_combat(self) -> None:
        """战斗阶段：委托 CombatEngine。"""
        _log.info(
            '[决战] 开始战斗 (小关 {} 节点 {})',
            self._state.stage,
            self._state.node,
        )

        plan = CombatPlan(
            name=f'决战-{self._state.stage}-{self._state.node}',
            mode=CombatMode.DECISIVE,
            default_node=NodeDecision(
                formation=self._logic.get_formation(),
                night=self._logic.is_key_point(),
            ),
        )
        result = run_combat(
            self._ctx,
            plan,
            ship_stats=self._state.ship_stats[:],
        )
        self._state.ship_stats = result.ship_stats[:]
        self._sync_ship_states()
        _log.info(
            '[决战] 战斗结束: {} (节点 {} 血量 {})',
            result.flag.value,
            self._state.node,
            self._state.ship_stats,
        )

        if result.flag == ConditionFlag.OPERATION_SUCCESS:
            _log.info('[决战] 战果识别成功，点击继续结束结算页')
            click_result(self._ctrl)
            time.sleep(0.3)

        # 处理战斗结果标志
        if result.flag == ConditionFlag.DOCK_FULL:
            _log.warning('[决战] 战斗中检测到船坞已满，转到 DOCK_FULL 阶段处理')
            self._state.phase = DecisivePhase.DOCK_FULL
        else:
            self._state.phase = DecisivePhase.NODE_RESULT

    # ── 节点结果 & 通关 ──────────────────────────────────────────────────

    _POST_COMBAT_TIMEOUT = 15.0  # 等待决战地图加载的最大时间
    _POST_COMBAT_INTERVAL = 0.5  # 检测间隔

    def _handle_node_result(self) -> None:
        """节点战斗结束：轮询检测决战地图状态并路由。

        战斗引擎在 RESULT 点击后退出，游戏随后回到决战地图。
        地图上可能出现以下几种情况：

        - **ADVANCE_CHOICE**: 分支路径选择 overlay
        - **CHOOSE_FLEET**: 战备舰队获取 overlay
        - **PREPARE_COMBAT**: 地图页无 overlay，准备下一节点
        - **STAGE_CLEAR**: 小关终止节点到达（通过逻辑判断，非图像检测）
        """
        _log.info('[决战] 节点 {} 战斗结束, 等待地图加载', self._state.node)

        # 先通过逻辑判断小关是否结束
        if self._logic.is_stage_end():
            self._fleet_overlay_enabled = False
            _log.info(
                '[决战] 小关 {} 终止节点 {} 已到达',
                self._state.stage,
                self._state.node,
            )
            self._state.phase = DecisivePhase.STAGE_CLEAR
            return

        # 非小关终止：推进节点计数
        # 使用逻辑递进：节点字母 +1（A→B→C...）
        # 注意：战斗结束后可能出现 ADVANCE_CHOICE/CHOOSE_FLEET overlay，
        # 此时不应调用 recognize_node()，因为舰标尚未出现。
        # 恢复模式（暂离后再进）时，节点识别在 _handle_prepare_combat 中进行。
        current_node = self._state.node
        self._fleet_overlay_enabled = True
        self._advance_source_node = current_node
        expected_node = chr(ord(current_node) + 1)
        self._state.node = expected_node
        _log.debug('[决战] 节点递进: {} -> {}', chr(ord(expected_node) - 1), expected_node)

        _log.info('[决战] 推进至节点 {}', self._state.node)

        # 轮询检测地图状态
        # TODO: 改进鲁棒性
        deadline = time.monotonic() + self._POST_COMBAT_TIMEOUT
        while time.monotonic() < deadline:
            time.sleep(self._POST_COMBAT_INTERVAL)
            phase = self._map.detect_decisive_phase(
                advance_choice_roi=self._advance_choice_roi(),
                allow_fleet_overlay=self._fleet_overlay_enabled,
            )
            if phase == DecisivePhase.PREPARE_COMBAT:
                continue
            if phase is not None:
                _log.info('[决战] 战后检测到: {}', phase.name)
                self._state.phase = phase
                return

        # 超时后继续等待入口 overlay，避免在未知画面上直接点击编队。
        _log.warning(
            '[决战] 战后状态检测超时 ({:.0f}s), 继续等待 overlay',
            self._POST_COMBAT_TIMEOUT,
        )
        self._wait_deadline = time.monotonic() + 10.0
        self._state.phase = DecisivePhase.WAITING_FOR_MAP

    def _handle_stage_clear(self) -> None:
        """小关通关：确认弹窗 → 收集掉落 → 下一小关或大关。"""
        _log.info('[决战] 小关 {} 通关!', self._state.stage)
        collected = self._map.confirm_stage_clear()
        # The next subsection must re-anchor from the live map. Do not carry
        # A across the stage boundary or route selection will use A as source
        # instead of the synthetic entry node 0.
        self._state.node = 'U'
        self._advance_source_node = None
        self._resume_mode = True
        self._fleet_overlay_enabled = True
        if collected:
            _log.info('[决战] 获得 {} 个掉落: {}', len(collected), collected)

        if self._state.stage >= 3:
            self._state.phase = DecisivePhase.CHAPTER_CLEAR
        else:
            self._state.phase = DecisivePhase.ENTER_MAP

    # ── 撤退与暂离 ──────────────────────────────────────────────────────

    def _execute_retreat(self) -> None:
        """执行撤退操作。"""
        _log.info('[决战] 执行撤退')
        self._map.open_retreat_dialog()
        self._map.confirm_retreat()
        self._fleet_overlay_enabled = True

    def _execute_leave(self) -> None:
        """执行暂离操作。"""
        _log.info('[决战] 执行暂离')
        self._map.open_retreat_dialog()
        self._map.confirm_leave()
        self._fleet_overlay_enabled = False
