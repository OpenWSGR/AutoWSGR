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
from autowsgr.constants import ship_name_identity
from autowsgr.infra.logger import get_logger
from autowsgr.ops.decisive.base import DecisiveBase
from autowsgr.types import (
    ConditionFlag,
    DecisiveEntryStatus,
    DecisivePhase,
    FleetSelection,
    Formation,
    ShipDamageState,
)
from autowsgr.ui import RepairStrategy
from autowsgr.ui.decisive import DecisiveBattlePreparationPage


if TYPE_CHECKING:
    import numpy as np

    from autowsgr.combat.history import CombatResult
    from autowsgr.emulator.frame import CapturedFrame


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
                fallback_score=last_score,
            )
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

    def _refresh_inventory(self) -> None:
        """只发布完整、已返回地图的库存；扫描异常或停止时保留原业务快照。"""
        self._inventory_refresh_required = True
        if self._ctx.stop_event.is_set():
            raise InterruptedError('核实决战库存前收到停止请求')
        fleet, damage, all_ships = self._map.check_fleet()
        if len(fleet) != 6 or any(
            name is not None and (not isinstance(name, str) or not name) for name in fleet
        ):
            raise ValueError('决战库存扫描未提供完整六槽编队')
        ships = set(all_ships)
        if any(not isinstance(name, str) or not name for name in ships) or not {
            name for name in fleet if name
        }.issubset(ships):
            raise ValueError('决战完整库存与当前编队不一致')
        new_fleet = [''] + [name or '' for name in fleet]
        stats = [
            damage.get(slot, ShipDamageState.NORMAL) if name else ShipDamageState.NO_SHIP
            for slot, name in enumerate(fleet)
        ]
        if self._ctx.stop_event.is_set():
            raise InterruptedError('核实决战库存时收到停止请求，保留原快照')
        previous = self._state.ships, self._state.fleet, self._state.ship_stats
        self._state.ships, self._state.fleet, self._state.ship_stats = ships, new_fleet, stats
        try:
            self._sync_ship_states()
        except Exception:
            self._state.ships, self._state.fleet, self._state.ship_stats = previous
            raise
        self._inventory_refresh_required = False

    def _verify_prepared_fleet(
        self, page: DecisiveBattlePreparationPage, target: list[str]
    ) -> None:
        """换船返回成功还须独立核对六槽身份和占用状态，确认后才发布编队。"""
        self._inventory_refresh_required = True
        if self._ctx.stop_event.is_set():
            raise InterruptedError('更换决战编队前收到停止请求')
        if self._state.fleet != target and not page.change_fleet(None, target[1:]):
            raise RuntimeError('决战编队更换未成功，停止并保留现场')
        snapshot = page.detect_fleet_snapshot()
        if (
            len(snapshot.names) != 6
            or len(snapshot.occupied) != 6
            or any(
                occupied != bool(expected)
                or ship_name_identity(actual) != ship_name_identity(expected)
                for actual, occupied, expected in zip(
                    snapshot.names, snapshot.occupied, target[1:], strict=True
                )
            )
        ):
            raise RuntimeError('决战实际编队与目标六槽不一致，停止并保留现场')
        if self._ctx.stop_event.is_set():
            raise InterruptedError('核实决战编队时收到停止请求')
        self._state.fleet = [''] + [name or '' for name in snapshot.names]
        self._inventory_refresh_required = False

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

    def _detect_entry_stage(self) -> int:
        """将总览页零基进度转换为领域小关；完成标记不能替代通关结算验证。"""
        progress = self._battle_page.detect_stage(self._ctrl.screenshot(), self._config.chapter)
        if progress == 3:
            raise RuntimeError('决战入口标记已全部完成，与当前入口状态冲突；停止并保留现场')
        if progress not in (0, 1, 2):
            raise RuntimeError(f'决战入口进度无效: {progress}')
        return progress + 1

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
        did_reset = False

        if entry_status == DecisiveEntryStatus.REFRESH:
            _log.info('[决战] 检测到「重置关卡」状态，执行章节重置')
            self._inventory_refresh_required = True
            reset_success = self._battle_page.reset_chapter()
            if not reset_success:
                # 重置不成功是因为需要解装
                self._state.phase = DecisivePhase.DOCK_FULL
                return
            self._close_tracking()
            did_reset = True
            # 重置后重新检测入口状态
            entry_status = self._battle_page.detect_entry_status()

        if entry_status == DecisiveEntryStatus.CANT_FIGHT:
            raise RuntimeError(
                f'决战 Ex-{self._config.chapter}: 入口状态为「无法出击」，其他关卡正在进行中'
            )

        _log.info('[决战] 入口状态: {}', entry_status.value)

        self._state.stage = self._detect_entry_stage()
        if did_reset:
            if entry_status == DecisiveEntryStatus.REFRESH or self._state.stage != 1:
                raise RuntimeError('重置后未确认第一小关入口，拒绝假定 A 起点')
            self._known_start_stage = 1
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
        self._state.score = score

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
                self._state.score = score
                to_buy = self._logic.choose_ships(
                    selections,
                    first_node=first_node,
                )

            _log.info('[决战] 选择购买: {}', to_buy)
            for name in to_buy:
                sel = selections[name]
                self._inventory_refresh_required = True
                self._map.buy_fleet_option(sel.click_position)
                # 点击不代表购买成功（费用 OCR 错误、余额不足或点击被动画吞掉）。
                # 包括免费卡和技能卡在内，都复用准备阶段的真实库存扫描确认结果。
                # 不把未经确认的卡片名称加入库存，否则后续编队会寻找不存在的舰船。

        self._state.phase = DecisivePhase.PREPARE_COMBAT
        if not self._map.close_fleet_overlay():
            _log.info('[决战] 关闭决战选船界面失败, 选择第一艘后撤退')
            self._state.phase = DecisivePhase.RETREAT
            _, first_value = next(iter(selections.items()))
            self._inventory_refresh_required = True
            self._map.buy_fleet_option(first_value.click_position)
            if not self._map.close_fleet_overlay():
                raise RuntimeError('关闭决战选船界面失败')

    def _handle_advance_choice(self) -> None:
        """选择前进点。"""
        _log.info('[决战] 选择前进点')
        choice_idx = self._logic.get_advance_choice([])
        self._map.select_advance_card(choice_idx)
        self._state.phase = DecisivePhase.CHOOSE_FLEET

    # ── 战斗 ──────────────────────────────────────────────────────────────

    def _prepare_map_tracking(self) -> bool:
        """准备前确认稳定地图；延迟出现的弹窗交回状态机处理。"""
        screen = self._ctrl.screenshot()

        # 某些情况下地图页识别会先于 overlay 稳定，导致实际上仍停留在
        # 「战备舰队获取 / 前进点选择」时就误入 PREPARE_COMBAT。
        # 这里补一次即时探测，优先回到正确阶段，避免后续直接点“编队”超时。
        overlay_phase = self._map.detect_decisive_phase(screen)
        if overlay_phase in (DecisivePhase.CHOOSE_FLEET, DecisivePhase.ADVANCE_CHOICE):
            _log.info('[决战] 出征准备前检测到 overlay，切回阶段: {}', overlay_phase.name)
            self._state.phase = overlay_phase
            return False

        try:
            frame = self._map.wait_for_stable_map_frame()
        except TimeoutError:
            # 等待稳定帧期间也可能才弹出购舰或前进页，交回状态机处理。
            phase = self._map.detect_decisive_phase()
            if phase in (DecisivePhase.CHOOSE_FLEET, DecisivePhase.ADVANCE_CHOICE):
                self._state.phase = phase
                return False
            raise
        self._observe_map_ready(frame)
        session = self._ensure_tracking()
        if session.tracker is None:
            raise RuntimeError('决战小关定位会话失效，停止以保留进度')
        self._state.node = session.current_node if session.current_node != '0' else 'U'
        return True

    def _handle_prepare_combat(self) -> None:
        """出征准备：编队 → 修理 → 出征。"""
        if self._ctx.stop_event.is_set():
            self._state.phase = DecisivePhase.FINISHED
            return
        if not self._prepare_map_tracking():
            return
        _log.info(
            '[决战] 出征准备 (小关 {} 节点 {})',
            self._state.stage,
            self._state.node,
        )

        # 先使用技能，再注册舰船，如果是未知节点，也判定一下技能是否使用
        current_node = self._state.node
        time.sleep(0.5)  # 等待动画稳定后截图判定
        skill_used = self._map.is_skill_used()
        _log.debug('[决战] 节点: {}, 技能已使用检测: {}', current_node, skill_used)

        if not skill_used:
            if (
                self._config.useful_skill
                and self._config.useful_skill_strict
                and self._inventory_refresh_required
            ):
                self._refresh_inventory()
            # 点击后可能实际获得舰船，即使结果 OCR 失败也必须重新核实。
            self._inventory_refresh_required = True
            gained = self._map.use_skill()
            _log.debug('[决战] 执行技能使用获得: {}', gained)
            # 技能结果文字同样来自 OCR；与购舰合并为本次准备前的一次库存刷新。
            if gained and self._config.useful_skill and not self._logic.check_useful_skill(gained):
                _log.info('[决战] 技能获得: {}, 效果不佳，撤退重试', gained)
                self._state.phase = DecisivePhase.RETREAT
                return
        else:
            _log.debug('[决战] 跳过技能使用: 节点={}, 技能已使用={}', current_node, skill_used)

        # 首次进入且尚未选择过舰队时，使用技能后可能出现战备舰队获取 overlay，
        # 先切回 WAITING_FOR_MAP 等待 overlay 稳定，避免直接点击编队超时。
        if not skill_used and not self._has_chosen_fleet:
            _log.info('[决战] 首次进入，使用技能后等待 overlay 稳定')
            self._wait_deadline = time.monotonic() + 10.0
            self._state.phase = DecisivePhase.WAITING_FOR_MAP
            return

        if self._inventory_refresh_required:
            self._refresh_inventory()

        best_fleet = self._logic.get_best_fleet()
        if self._logic.should_retreat(best_fleet):
            _log.info('[决战] 舰船不足, 准备撤退')
            self._state.phase = DecisivePhase.RETREAT
            return

        self._map.enter_formation()
        time.sleep(0.5)  # 等待编队页加载完成（对齐 check_fleet 的做法）
        page = DecisiveBattlePreparationPage(self._ctx, self._config, self._ocr)

        self._verify_prepared_fleet(page, best_fleet)

        strategy = (
            RepairStrategy.MODERATE if self._config.repair_level <= 1 else RepairStrategy.SEVERE
        )
        page.apply_repair(strategy, repair_manually=not self._config.use_quick_repair)

        screen = self._ctrl.screenshot()
        damage = page.detect_ship_damage(screen)
        self._state.ship_stats = [damage.get(i, ShipDamageState.NORMAL) for i in range(6)]
        self._sync_ship_states()

        if self._ctx.stop_event.is_set():
            self._state.phase = DecisivePhase.FINISHED
            return
        page.start_battle()
        time.sleep(1.0)
        self._state.phase = DecisivePhase.IN_COMBAT

    def _observe_map_ready(self, frame: CapturedFrame) -> None:
        """采集器可复用这个入口，保证字母识别与定位裁剪使用同一帧。"""
        session = self._ensure_tracking()
        node = self._map.recognize_node(frame) if session.sample_node_label else None
        session.map_ready(frame, node)

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
            chapter=self._state.chapter,
            map_id=self._state.stage,
            default_node=NodeDecision(
                formation=Formation.double_column,
                night=True,
            ),
            nodes={
                name: NodeDecision(
                    formation=self._logic.get_formation(name),
                    night=self._logic.is_key_point(name),
                )
                for name in self._ensure_tracking().tracker.map_data.nodes
            },
        )
        self._battle_encounter_id = self._tracking.encounter_id
        result = self._run_combat(plan)
        self._state.node = (
            self._tracking.current_node if self._tracking.current_node != '0' else 'U'
        )
        self._state.ship_stats = result.ship_stats[:]
        self._sync_ship_states()
        _log.info(
            '[决战] 战斗结束: {} (节点 {} 血量 {})',
            result.flag.value,
            self._state.node,
            self._state.ship_stats,
        )

        # 处理战斗结果标志
        if self._ctx.stop_event.is_set():
            self._state.phase = DecisivePhase.FINISHED
        elif result.flag == ConditionFlag.DOCK_FULL:
            _log.warning('[决战] 战斗中检测到船坞已满，转到 DOCK_FULL 阶段处理')
            self._state.phase = DecisivePhase.DOCK_FULL
        elif result.flag == ConditionFlag.OPERATION_SUCCESS:
            self._state.phase = DecisivePhase.NODE_RESULT
        else:
            _log.error('[决战] 战斗未完成，不推进节点: {}', result.flag.value)
            self._state.phase = DecisivePhase.FINISHED

    def _run_combat(self, plan: CombatPlan) -> CombatResult:
        """执行战斗；采集器可替换引擎，结果分类仍由控制器统一处理。"""
        return run_combat(
            self._ctx, plan, ship_stats=self._state.ship_stats[:], tracking_session=self._tracking
        )

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
        - **STAGE_CLEAR**: 独立通关页面确认，模型预测只决定是否复核
        """
        _log.info('[决战] 节点 {} 战斗结束, 等待地图加载', self._state.node)

        if self._ctx.stop_event.is_set():
            self._state.phase = DecisivePhase.FINISHED
            return

        session = self._ensure_tracking()
        if self._battle_encounter_id is None:
            raise RuntimeError('缺少成功战斗的遭遇标识，拒绝推进')
        session.complete_encounter(self._battle_encounter_id)
        self._state.node = session.current_node if session.current_node != '0' else 'U'
        terminal_weight = sum(
            row['weight']
            for row in session.estimate.state_weights
            if row['stage'] == 'TERMINAL_PENDING'
        )
        predicted_terminal = terminal_weight >= session.sampling.resume_threshold
        if predicted_terminal:
            session.request_node_sample('战斗完成后存在终点候选，等待真实页面复核')

        deadline = time.monotonic() + self._POST_COMBAT_TIMEOUT
        while time.monotonic() < deadline:
            if self._ctx.stop_event.is_set():
                self._state.phase = DecisivePhase.FINISHED
                return
            time.sleep(self._POST_COMBAT_INTERVAL)
            frame = self._ctrl.capture_frame()
            if self._map.is_stage_clear(frame.image):
                if session.stage_clear(frame):
                    self._state.phase = DecisivePhase.STAGE_CLEAR
                    return
                continue
            phase = self._map.detect_decisive_phase(frame.image)
            if phase == DecisivePhase.PREPARE_COMBAT:
                frame = self._map.wait_for_stable_map_frame()
                self._observe_map_ready(frame)
            elif phase in (DecisivePhase.CHOOSE_FLEET, DecisivePhase.ADVANCE_CHOICE):
                session.map_ready(frame)
            if phase is not None:
                _log.info('[决战] 战后检测到: {}', phase.name)
                self._state.phase = phase
                return

        session.request_node_sample('战后页面超时')
        raise TimeoutError('战后未确认下一节点或真实通关页面；保留现场，停止决战')

    def _handle_stage_clear(self, *, resume_rewards: bool = False) -> None:
        """小关通关：确认弹窗 → 收集掉落 → 下一小关或大关。"""
        _log.info('[决战] 小关 {} 通关!', self._state.stage)
        collected = self._map.confirm_stage_clear(resume_rewards=resume_rewards)
        self._close_tracking()
        self._known_start_stage = self._state.stage + 1
        self._state.node = 'A'
        self._inventory_refresh_required = True
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
        self._close_tracking()
        self._known_start_stage = None
        self._inventory_refresh_required = True

    def _execute_leave(self) -> None:
        """执行暂离操作。"""
        _log.info('[决战] 执行暂离')
        self._map.open_retreat_dialog()
        self._map.confirm_leave()
        self._close_tracking()
