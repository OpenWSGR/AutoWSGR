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

import cv2

from autowsgr.combat.engine import run_combat
from autowsgr.combat.plan import CombatMode, CombatPlan, NodeDecision
from autowsgr.infra.logger import get_logger
from autowsgr.ops.decisive.base import DecisiveBase
from autowsgr.types import DecisiveEntryStatus, DecisivePhase, FleetSelection, ShipDamageState
from autowsgr.ui import RepairStrategy
from autowsgr.ui.decisive import DecisiveBattlePreparationPage


if TYPE_CHECKING:
    import numpy as np


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
            self._battle_page.reset_chapter()
            # 重置后重新检测入口状态
            entry_status = self._battle_page.detect_entry_status()

        if entry_status == DecisiveEntryStatus.CANT_FIGHT:
            raise RuntimeError(
                f'决战 Ex-{self._config.chapter}: 入口状态为「无法出击」，其他关卡正在进行中'
            )

        _log.info('[决战] 入口状态: {}', entry_status.value)

        self._state.stage = self._battle_page.detect_stage(
            self._ctrl.screenshot(),
            self._config.chapter,
        )
        if self._config.chapter == 1:
            self._resume_mode = False
            _log.info(
                '[决战] Ex-1 总览页仅识别小节号: stage={}，首次进入/恢复模式改由进图后节点判定',
                self._state.stage,
            )
        self._battle_page.click_enter_map()
        self._use_last_fleet_attempts = 0
        self._wait_deadline = time.monotonic() + 15.0
        self._state.phase = DecisivePhase.WAITING_FOR_MAP

    def _handle_waiting_for_map(self) -> None:
        """等待地图页加载: 单次截图检测 → 转到对应阶段或继续等待。"""
        screen = self._ctrl.screenshot()
        phase = self._map.detect_decisive_phase(screen)

        # Ex-1 首次进入第 1 小节时，理论上应先经历一次战备舰队获取。
        # 若此时尚未进入过 CHOOSE_FLEET，却稳定识别成 PREPARE_COMBAT，
        # 则将其视为购买界面漏判并自动修正到 CHOOSE_FLEET。
        # 注意：暂离后重进时 node='U'，此时舰标已在地图上，不应修正到 CHOOSE_FLEET
        if (
            phase == DecisivePhase.PREPARE_COMBAT
            and self._state.stage == 1
            and not self._has_chosen_fleet
        ):
            if self._state.node != 'U':
                _log.warning('[决战] 首进第 1 小节将 PREPARE_COMBAT 修正为 CHOOSE_FLEET')
                self._state.phase = DecisivePhase.CHOOSE_FLEET
                return
            # node == 'U' 时，通过舰标检测区分暂离重进与 overlay 延迟加载
            bgr = cv2.cvtColor(screen, cv2.COLOR_RGB2BGR)
            icon_x = self._map._locate_ship_icon(bgr)
            if icon_x is None:
                _log.warning(
                    '[决战] 首进第 1 小节未检测到舰标，将 PREPARE_COMBAT 修正为 CHOOSE_FLEET'
                )
                self._state.phase = DecisivePhase.CHOOSE_FLEET
                return

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
        self._has_chosen_fleet = True

        _log.info('[决战] 战备舰队获取')
        screen, score, selections = self._recognize_fleet_options_with_retry(
            fallback_score=self._state.score,
        )
        self._state.score = score or self._state.score

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
            _log.info('[决战] 关闭决战选船界面失败, 选择第一艘后撤退')
            self._state.phase = DecisivePhase.RETREAT
            _, first_value = next(iter(selections.items()))
            self._map.buy_fleet_option(first_value.click_position)
            if not self._map.close_fleet_overlay():
                raise RuntimeError('关闭决战选船界面失败')
        self._state.phase = DecisivePhase.PREPARE_COMBAT

    def _handle_advance_choice(self) -> None:
        """选择前进点。"""
        _log.info('[决战] 选择前进点')
        choice_idx = self._logic.get_advance_choice([])
        self._map.select_advance_card(choice_idx)
        self._state.phase = DecisivePhase.CHOOSE_FLEET

    # ── 战斗 ──────────────────────────────────────────────────────────────

    def _handle_prepare_combat(self) -> None:
        """出征准备：编队 → 修理 → 出征。"""
        screen = self._ctrl.screenshot()

        # 某些情况下地图页识别会先于 overlay 稳定，导致实际上仍停留在
        # 「战备舰队获取 / 前进点选择」时就误入 PREPARE_COMBAT。
        # 这里补一次即时探测，优先回到正确阶段，避免后续直接点“编队”超时。
        overlay_phase = self._map.detect_decisive_phase(screen)
        if overlay_phase in (DecisivePhase.CHOOSE_FLEET, DecisivePhase.ADVANCE_CHOICE):
            _log.info('[决战] 出征准备前检测到 overlay，切回阶段: {}', overlay_phase.name)
            self._state.phase = overlay_phase
            return

        if self._state.node == 'U':
            # 初次进入都要进行节点识别
            self._state.node = self._map.recognize_node()
        _log.info(
            '[决战] 出征准备 (小关 {} 节点 {})',
            self._state.stage,
            self._state.node,
        )

        # ── 恢复模式检测 ─────────────────────────────────────────────
        # 恢复模式逻辑修改，默认进入恢复模式，如果是首节点，则不进入恢复模式
        if self._state.is_begin():
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
        if self._resume_mode:
            _log.info('[决战] 恢复模式: 扫描当前舰队')
            fleet, damage, all_ships = self._map.check_fleet()
            self._state.ship_stats = [damage.get(i, ShipDamageState.NORMAL) for i in range(6)]
            self._state.ships = all_ships
            # 将编队成员写入 state.fleet[1:]
            for i, name in enumerate(fleet):
                if i < 6:
                    self._state.fleet[i + 1] = name or ''
            self._sync_ship_states()
            self._resume_mode = False  # 扫描完成后退出恢复模式

        best_fleet = self._logic.get_best_fleet()
        if self._logic.should_retreat(best_fleet):
            _log.info('[决战] 舰船不足, 准备撤退')
            self._state.phase = DecisivePhase.RETREAT
            return

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
            RepairStrategy.NEVER
            if not self._config.use_quick_repair
            else RepairStrategy.MODERATE
            if self._config.repair_level <= 1
            else RepairStrategy.SEVERE
        )
        page.apply_repair(strategy)

        screen = self._ctrl.screenshot()
        damage = page.detect_ship_damage(screen)
        self._state.ship_stats = [damage.get(i, ShipDamageState.NORMAL) for i in range(6)]
        self._sync_ship_states()

        page.start_battle()
        time.sleep(1.0)
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
        expected_node = chr(ord(self._state.node) + 1)
        self._state.node = expected_node
        _log.debug('[决战] 节点递进: {} -> {}', chr(ord(expected_node) - 1), expected_node)

        _log.info('[决战] 推进至节点 {}', self._state.node)

        # 轮询检测地图状态
        # TODO: 改进鲁棒性
        deadline = time.monotonic() + self._POST_COMBAT_TIMEOUT
        while time.monotonic() < deadline:
            time.sleep(self._POST_COMBAT_INTERVAL)
            phase = self._map.detect_decisive_phase()
            if phase == DecisivePhase.PREPARE_COMBAT:
                continue
            if phase is not None:
                _log.info('[决战] 战后检测到: {}', phase.name)
                self._state.phase = phase
                return

        # 超时回退到 PREPARE_COMBAT
        _log.warning(
            '[决战] 战后状态检测超时 ({:.0f}s), 回退到 PREPARE_COMBAT',
            self._POST_COMBAT_TIMEOUT,
        )
        self._state.phase = DecisivePhase.PREPARE_COMBAT

    def _handle_stage_clear(self) -> None:
        """小关通关：确认弹窗 → 收集掉落 → 下一小关或大关。"""
        _log.info('[决战] 小关 {} 通关!', self._state.stage)
        collected = self._map.confirm_stage_clear()
        self._state.node = 'A'
        self._resume_mode = True
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

    def _execute_leave(self) -> None:
        """执行暂离操作。"""
        _log.info('[决战] 执行暂离')
        self._map.open_retreat_dialog()
        self._map.confirm_leave()
