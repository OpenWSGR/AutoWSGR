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

from autowsgr.combat.engine import run_combat
from autowsgr.combat.plan import CombatMode, CombatPlan, NodeDecision
from autowsgr.infra.logger import get_logger
from autowsgr.ops.decisive.base import DecisiveBase
from autowsgr.types import DecisiveEntryStatus, DecisivePhase, ShipDamageState
from autowsgr.ui import RepairStrategy
from autowsgr.ui.decisive import DecisiveBattlePreparationPage


_log = get_logger('ops.decisive')


class DecisivePhaseHandlers(DecisiveBase):
    # ── 状态同步 ──────────────────────────────────────────────────────────

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

        self._state.stage = self._battle_page.recognize_stage(
            self._ctrl.screenshot(),
            self._config.chapter,
        )
        self._battle_page.click_enter_map()
        self._use_last_fleet_attempts = 0
        self._wait_deadline = time.monotonic() + 15.0
        self._state.phase = DecisivePhase.WAITING_FOR_MAP

    def _handle_waiting_for_map(self) -> None:
        """等待地图页加载: 单次截图检测 → 转到对应阶段或继续等待。"""
        screen = self._ctrl.screenshot()
        phase = self._map.detect_decisive_phase(screen)

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
        time.sleep(0.25)  # 等待动画稳定
        screen = self._map.screenshot()
        score, selections = self._map.recognize_fleet_options(screen)
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
                screen = self._map.screenshot()
                score, selections = self._map.recognize_fleet_options(screen)
                self._state.score = score or self._state.score
                to_buy = self._logic.choose_ships(
                    selections,
                    first_node=first_node,
                )

            if not to_buy and len(self._state.ships) == 0 and self._state.is_begin():
                _log.info('[决战] 未选择舰船, 必须购买一项 → 选择第一项')
                self._map.buy_fleet_option(list(selections.values())[0].click_position)
                self._map.close_fleet_overlay()
                self._state.phase = DecisivePhase.RETREAT
                return

            _log.info('[决战] 选择购买: {}', to_buy)
            for name in to_buy:
                sel = selections[name]
                self._map.buy_fleet_option(sel.click_position)
                if name not in {'长跑训练', '肌肉记忆', '黑科技'}:
                    self._state.ships.add(name)

        self._map.close_fleet_overlay()
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
        if self._state.node == 'U':
            self._state.node = self._map.recognize_node(screen)
        _log.info(
            '[决战] 出征准备 (小关 {} 节点 {})',
            self._state.stage,
            self._state.node,
        )

        # ── 恢复模式检测 ─────────────────────────────────────────────
        # 判定标准: 首次进入时节点不是 1A，
        # 或者是 1A 但尚未经历过 choose_fleet（已有进度继续）
        if not self._resume_mode and (
            not self._state.is_begin() or (self._state.is_begin() and not self._has_chosen_fleet)
        ):
            self._resume_mode = True
            _log.info(
                '[决战] 检测到恢复模式 (节点={}, has_chosen_fleet={})',
                self._state.node,
                self._has_chosen_fleet,
            )

        # 先使用技能，再注册舰船，如果是未知节点，也判定一下技能是否使用
        current_node = self._state.node
        if (current_node == 'A' or current_node == 'U') and not self._map.is_skill_used():
            gained = self._map.use_skill()
            if gained:
                if self._config.useful_skill and not self._logic.check_useful_skill(gained):
                    _log.info('[决战] 技能获得: {}, 效果不佳，撤退重试', gained)
                    self._state.phase = DecisivePhase.RETREAT
                    return
                _log.info('[决战] 使用技能获得: {}', gained)
                self._state.ships.update(gained)

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
        page = DecisiveBattlePreparationPage(self._ctx, self._config, self._ocr)

        current_fleet = self._state.fleet[:]
        if current_fleet != best_fleet:
            time.sleep(0.5)  # 等待进入出征准备页面
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
        next_node = chr(ord(self._state.node) + 1)
        self._state.node = next_node
        _log.info('[决战] 推进至节点 {}', next_node)

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
