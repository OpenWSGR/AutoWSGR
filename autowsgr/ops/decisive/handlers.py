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

from autowsgr.combat.engine import run_combat
from autowsgr.combat.plan import CombatMode, CombatPlan, NodeDecision
from autowsgr.constants import DECISIVE_SKILL_NAMES, ship_name_identity
from autowsgr.infra.logger import get_logger
from autowsgr.ops.decisive.base import DecisiveBase
from autowsgr.ops.decisive.config import MapData
from autowsgr.ops.decisive.repair import RepairOutcome, RepairStatus
from autowsgr.types import (
    ConditionFlag,
    DecisiveEntryStatus,
    DecisivePhase,
    FleetSelection,
    Formation,
    ShipDamageState,
)
from autowsgr.ui.decisive import DecisiveBattlePreparationPage
from autowsgr.ui.decisive.battle_page import ResetConfirmationTimeoutError
from autowsgr.ui.utils.navigation import check_stop


if TYPE_CHECKING:
    import numpy as np

    from autowsgr.combat.history import CombatResult
    from autowsgr.emulator.frame import CapturedFrame
    from autowsgr.ops.decisive.tracking import DecisiveTrackingSession
    from autowsgr.ui.decisive.preparation import RepairSnapshot


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
        """返回地图后更新当前编队及选船列表首屏读到的舰船。"""
        self._inventory_refresh_required = True
        if self._ctx.stop_event.is_set():
            raise InterruptedError('核实决战库存前收到停止请求')

        def observe_repairing(name: str) -> None:
            # 扫描库存可能耗时，从首次读到在修标记起计时；到期复核使用准备页新帧。
            if ship_name_identity(name) not in self._repairs.due_identities:
                self._repairs.observe_inventory(
                    [name],
                    chapter=self._state.chapter,
                    stage=self._state.stage,
                    damage={name: ShipDamageState.REPAIRING},
                )

        fleet, damage, all_ships = self._map.check_fleet(observe_repairing)
        if len(fleet) != 6 or any(
            name is not None and (not isinstance(name, str) or not name) for name in fleet
        ):
            raise ValueError('未能识别当前编队的全部舰船名称')
        ships = set(all_ships)
        if any(not isinstance(name, str) or not name for name in ships) or not {
            name for name in fleet if name
        }.issubset(ships):
            raise ValueError('可选舰船记录与当前编队不一致')
        if any(
            name and damage.get(slot) in (None, ShipDamageState.NO_SHIP)
            for slot, name in enumerate(fleet)
        ):
            raise ValueError('未能确认当前编队中全部舰船的损伤状态')
        # 首屏可能看不到上次确认的候补；本小关已实见的舰船仍可参与编队。
        ships.update(self._repairs.acquired)
        new_fleet = [''] + [name or '' for name in fleet]
        stats = [
            damage[slot] if name else ShipDamageState.NO_SHIP for slot, name in enumerate(fleet)
        ]
        if self._ctx.stop_event.is_set():
            raise InterruptedError('核对已获得的决战舰船时收到停止请求，保留上次的编队和舰船记录')
        previous = self._state.ships, self._state.fleet, self._state.ship_stats
        self._state.ships, self._state.fleet, self._state.ship_stats = ships, new_fleet, stats
        try:
            self._sync_ship_states()
            self._repairs.observe_inventory(
                ships,
                chapter=self._state.chapter,
                stage=self._state.stage,
                damage={
                    name: stats[i]
                    for i, name in enumerate(fleet)
                    if name and ship_name_identity(name) not in self._repairs.due_identities
                },
            )
        except Exception:
            self._state.ships, self._state.fleet, self._state.ship_stats = previous
            raise
        self._inventory_refresh_required = False

    def _verify_prepared_fleet(
        self, page: DecisiveBattlePreparationPage, target: list[str], *, force_change: bool = False
    ) -> RepairSnapshot:
        """换船后从新画面核对整队舰名、顺序和血量。"""
        self._inventory_refresh_required = True
        if self._ctx.stop_event.is_set():
            raise InterruptedError('更换决战编队前收到停止请求')
        changed = force_change or self._state.fleet != target
        if changed and not page.change_fleet(None, target[1:]):
            raise RuntimeError('决战编队更换未成功，停止并保留现场')
        snapshot = self._repairs.read_complete_snapshot(page, fresh=True)
        names, _ = snapshot
        if list(map(ship_name_identity, names)) != list(map(ship_name_identity, target[1:])):
            raise RuntimeError('换船后未能确认实际编队中的舰船名称和顺序')
        if self._ctx.stop_event.is_set():
            raise InterruptedError('核实决战编队时收到停止请求')
        self._state.fleet = [''] + [name or '' for name in names]
        self._inventory_refresh_required = False
        return snapshot

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
        """沿用旧版直接读取小关号；入口标记不能替代真实通关结算。"""
        return self._battle_page.detect_stage(self._ctrl.screenshot(), self._config.chapter)

    def _handle_enter_map(self) -> None:
        """检测入口状态 → 按需重置 → 点击进入地图 → 转到 WAITING_FOR_MAP。

        通过 :meth:`DecisiveBattlePage.detect_entry_status` 识别当前章节的
        入口状态，根据 :class:`~autowsgr.types.DecisiveEntryStatus` 分别处理:

        - ``REFRESH``: 使用磁盘重置关卡后重新检测
        - ``REFRESHED``: 有存档进度，直接进入地图 (后续会弹出使用上次舰队)
        - ``CHALLENGING``: 挑战中，直接进入地图
        - ``CANT_FIGHT``: 无法出击，抛出异常
        """
        check_stop(self._ctx.stop_event)
        expected = self._state.expected_stage
        if expected is not None:
            self._repairs.validate_stage(self._battle_page, self._state.chapter, expected)
            _log.info(
                '[决战] 已在总览确认第 {} 章第 {} 小关的进度，准备进入地图',
                self._state.chapter,
                expected,
            )
            self._enter_verified_stage(expected)
            return
        entry_status = self._battle_page.detect_entry_status()
        did_reset = False

        if entry_status == DecisiveEntryStatus.REFRESH:
            _log.info('[决战] 检测到「重置关卡」状态，执行章节重置')
            self._inventory_refresh_required = True
            try:
                reset_success = self._battle_page.reset_chapter(self._config.chapter)
            except ResetConfirmationTimeoutError:
                # 磁盘可能已消耗，下一次调度只能核实同一章第一小关。
                self._state.expected_stage = 1
                self._close_tracking()
                self._repairs.reset_stage()
                self._has_chosen_fleet = False
                self._known_start_stage = 1
                raise
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

        stage = self._detect_entry_stage()
        _log.info(
            '[决战] 第 {} 章第 {} 小关，{}',
            self._config.chapter,
            stage,
            '已重置，从头开始' if did_reset else '从当前进度进入',
        )
        if did_reset:
            if entry_status == DecisiveEntryStatus.REFRESH or stage != 1:
                raise RuntimeError('重置后未确认第一小关入口，拒绝假定 A 起点')
            self._repairs.reset_stage()
            self._has_chosen_fleet = False
            self._known_start_stage = 1
        self._enter_verified_stage(stage)

    def _enter_verified_stage(self, stage: int) -> None:
        if stage not in (1, 2, 3):
            raise RuntimeError(f'决战 Ex-{self._config.chapter} 未识别有效小节')
        if self._state.stage != stage:
            # 下一张图的战备窗口可能先于库存检查出现，不能拿上一张图的舰船做购买决策。
            self._state.ships.clear()
            self._state.fleet = [''] * 7
            self._state.ship_stats = [ShipDamageState.NO_SHIP] * 6
        self._state.stage = stage
        branches = None
        if self._known_start_stage == stage:
            branches = len(MapData.get_leftmost_choices(self._config.chapter, stage, '0'))
        if self._tracking is None or self._tracking.stage != stage:
            self._map.configure_route(branches)
        check_stop(self._ctx.stop_event)
        self._use_last_fleet_attempts = 0
        self._wait_deadline = time.monotonic() + 15.0
        self._state.phase = DecisivePhase.WAITING_FOR_MAP
        self._battle_page.click_enter_map()

    def _handle_waiting_for_map(self) -> None:
        """按新帧确认入口浮窗或稳定的地图，消费过的上次舰队弹窗只能遮挡地图。"""
        remaining = self._wait_deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('等待地图页或浮窗 超时')
        self._state.phase = self._map.wait_for_entry_phase(
            timeout=remaining,
            wait_for_use_last=self._use_last_fleet_attempts == 0,
        )

    def _handle_use_last_fleet(self) -> None:
        """点击「使用上次舰队」按钮 → 转到 WAITING_FOR_MAP。"""
        check_stop(self._ctx.stop_event)
        self._map.click_use_last_fleet()
        self._use_last_fleet_attempts = 1
        self._wait_deadline = time.monotonic() + 10.0
        self._state.phase = DecisivePhase.WAITING_FOR_MAP

    def _handle_dock_full(self) -> None:
        """船坞已满: 自动解装 → ENTER_MAP。"""
        _log.warning('[决战] 处理船坞已满')
        self._do_dock_full_destroy()  # type: ignore[attr-defined]
        self._prepare_entry_state()  # type: ignore[attr-defined]
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

        self._inventory_refresh_required = True
        attempted: set[str] = set()
        if selections:
            first_node = self._state.is_begin()
            if first_node:
                last_name = self._map.detect_last_offer_name(screen)
                if last_name in DECISIVE_SKILL_NAMES:
                    _log.info('[决战] 首节点判定修正: 最后一项为技能')
                    first_node = False

            to_buy = self._logic.choose_ships(selections, first_node=first_node)

            if not to_buy:
                check_stop(self._ctx.stop_event)
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
                check_stop(self._ctx.stop_event)
                attempted.add(name)
                self._map.buy_fleet_option(sel.click_position)
                # 点击不代表购买成功（费用 OCR 错误、余额不足或点击被动画吞掉）。
                # 包括免费卡和技能卡在内，都复用准备阶段的真实库存扫描确认结果。
                # 不把未经确认的卡片名称加入库存，否则后续编队会寻找不存在的舰船。

        check_stop(self._ctx.stop_event)
        if self._map.close_fleet_overlay():
            self._state.phase = DecisivePhase.PREPARE_COMBAT
            return

        # 重新读取卡面和余额，避免按旧截图购买已经消费的卡或超支。
        _, score, remaining = self._recognize_fleet_options_with_retry(fallback_score=0)
        self._state.score = score
        affordable = [
            offer
            for name, offer in remaining.items()
            if name
            and not name.startswith('未识别_')
            and name not in attempted
            and name not in DECISIVE_SKILL_NAMES
            and 0 <= offer.cost <= score
        ]
        if not affordable:
            raise RuntimeError('决战选船界面无法关闭，也没有可支付的非技能舰卡')
        fallback = min(affordable, key=lambda offer: offer.cost)
        check_stop(self._ctx.stop_event)
        self._map.buy_fleet_option(fallback.click_position)
        check_stop(self._ctx.stop_event)
        if not self._map.close_fleet_overlay():
            raise RuntimeError('决战选船界面在购买最低费舰卡后仍未关闭')
        self._state.phase = DecisivePhase.RETREAT

    def _handle_advance_choice(self) -> None:
        """选择前进点。"""
        _log.info('[决战] 选择前进点')
        self._map.select_advance_card(0)
        self._wait_deadline = time.monotonic() + 10.0
        self._state.phase = DecisivePhase.WAITING_FOR_MAP

    # ── 战斗 ──────────────────────────────────────────────────────────────

    def _prepare_map_tracking(self) -> bool:
        """准备前确认稳定地图；延迟出现的弹窗交回状态机处理。"""
        screen = self._ctrl.screenshot()

        # 某些情况下地图页识别会先于浮窗稳定，导致实际上仍停留在
        # 「战备舰队获取 / 前进点选择」时就误入 PREPARE_COMBAT。
        # 这里补一次即时探测，优先回到正确阶段，避免后续直接点“编队”超时。
        overlay_phase = self._map.detect_decisive_phase(screen)
        if overlay_phase in (DecisivePhase.CHOOSE_FLEET, DecisivePhase.ADVANCE_CHOICE):
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
        check_stop(self._ctx.stop_event)
        if not self._state.at_node_boundary and not self._prepare_map_tracking():
            return
        self._state.at_node_boundary = False
        _log.info(
            '[决战] 出征准备 (小关 {} 节点 {})',
            self._state.stage,
            self._state.node,
        )

        if not self._prepare_node_supplies():
            return
        # 缺船撤退依据实际拥有的主备舰数；在修造成的暂时缺员交给维修协调器。
        if self._logic.should_retreat(self._logic.get_best_fleet()):
            _log.info('[决战] 舰船不足, 准备撤退')
            self._state.phase = DecisivePhase.RETREAT
            return
        self._map.enter_formation()
        page = DecisiveBattlePreparationPage(self._ctx, self._config, self._ocr)
        if not self._prepare_available_fleet(page):
            return

        if self._ctx.stop_event.is_set():
            self._state.phase = DecisivePhase.FINISHED
            return
        self._battle_encounter_id = self._ensure_tracking().encounter_id
        self._state.phase = DecisivePhase.IN_COMBAT
        page.start_battle()
        time.sleep(1.0)

    def _prepare_node_supplies(self) -> bool:
        """使用本节点技能，处理首次战备浮窗并核实已获得的舰船。"""
        # 战果页已核实的受伤舰，在确认地图可暂离后优先派修。
        if self._repairs.needs_dispatch:
            self._leave_for_repairs(None)
            return False

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
                if self._repairs.needs_dispatch:
                    self._leave_for_repairs(None)
                    return False
            # 点击后可能实际获得舰船，即使结果 OCR 失败也必须重新核实。
            self._inventory_refresh_required = True
            gained = self._map.use_skill()
            _log.debug('[决战] 执行技能使用获得: {}', gained)
            # 技能结果文字同样来自 OCR；与购舰合并为本次准备前的一次库存刷新。
            if gained and self._config.useful_skill and not self._logic.check_useful_skill(gained):
                _log.info('[决战] 技能获得: {}, 效果不佳，撤退重试', gained)
                self._state.phase = DecisivePhase.RETREAT
                return False
        else:
            _log.debug('[决战] 跳过技能使用: 节点={}, 技能已使用={}', current_node, skill_used)

        # 首次进入且尚未选择过舰队时，使用技能后可能出现战备舰队获取浮窗，
        # 先切回 WAITING_FOR_MAP 等待浮窗稳定，避免直接点击编队超时。
        if not skill_used and not self._has_chosen_fleet:
            _log.info('[决战] 首次进入，使用技能后等待浮窗稳定')
            self._wait_deadline = time.monotonic() + 10.0
            self._state.phase = DecisivePhase.WAITING_FOR_MAP
            return False

        if self._inventory_refresh_required:
            self._refresh_inventory()
        if self._repairs.needs_dispatch:
            self._leave_for_repairs(None)
            return False
        return True

    def _prepare_available_fleet(self, page: DecisiveBattlePreparationPage) -> bool:
        """检查主力和候补舰的伤情，选出本小关出征所需的舰船。"""
        snapshot = self._observe_repairs(page)
        snapshot = self._review_due_reserves(page, snapshot)

        # 替补也可能正在维修。换入后重读健康状态，必要时再选下一艘。
        tried = set()
        while True:
            if self._repairs.needs_dispatch:
                self._leave_for_repairs(page)
                return False
            best_fleet = self._logic.get_best_fleet(
                self._repairs.blocked_identities, self._repairs.damaged_identities
            )
            if sum(bool(name) for name in best_fleet) < self._repairs.target_size:
                if self._prepare_repairs(page, snapshot):
                    raise RuntimeError(f'可选舰船不足 {self._repairs.target_size} 艘，无法出征')
                return False
            key = tuple(map(ship_name_identity, best_fleet[1:]))
            if key == tuple(map(ship_name_identity, snapshot[0])):
                return self._prepare_repairs(page, snapshot)
            if key in tried:
                raise RuntimeError('决战编队反复变化，保留现场')
            tried.add(key)
            snapshot = self._verify_prepared_fleet(page, best_fleet)
            self._observe_repairs(page, snapshot)

    def _review_due_reserves(
        self, page: DecisiveBattlePreparationPage, snapshot: RepairSnapshot
    ) -> RepairSnapshot:
        """到了复查时间，把候补舰临时换入编队，核对它的舰名和伤情。"""
        due = self._repairs.due_identities
        for name in sorted(self._state.ships):
            identity = ship_name_identity(name)
            if identity not in due or identity in {
                ship_name_identity(n) for n in self._state.fleet
            }:
                continue
            target = self._state.fleet.copy()
            slot = next((i for i in range(1, 7) if not target[i]), 6)
            target[slot] = name
            snapshot = self._verify_prepared_fleet(page, target)
            self._observe_repairs(page, snapshot)
        return snapshot

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
        result = self._run_combat(plan)
        self._state.node = (
            self._tracking.current_node if self._tracking.current_node != '0' else 'U'
        )
        self._state.ship_stats = result.ship_stats[:]
        self._sync_ship_states()
        health = {
            ShipDamageState.NORMAL: '绿血',
            ShipDamageState.MODERATE: '中破',
            ShipDamageState.SEVERE: '大破',
            ShipDamageState.REPAIRING: '维修中',
            ShipDamageState.NO_SHIP: '未读到血条',
        }
        report = '、'.join(
            f'{name}（{health[damage]}）'
            for name, damage in zip(self._state.fleet[1:], result.ship_stats, strict=True)
            if name
        )
        _log.info('[决战] 节点 {} 的战斗结束，{}', self._state.node, report or '未识别到舰船')

        # 处理战斗结果标志
        if self._ctx.stop_event.is_set():
            self._state.phase = DecisivePhase.FINISHED
        elif result.flag == ConditionFlag.DOCK_FULL:
            _log.warning('[决战] 船坞已满，准备解装')
            self._state.phase = DecisivePhase.DOCK_FULL
        elif result.flag == ConditionFlag.OPERATION_SUCCESS:
            self._repairs.observe_inventory(
                self._state.ships,
                chapter=self._state.chapter,
                stage=self._state.stage,
                damage={
                    name: status
                    for name, status in zip(self._state.fleet[1:], result.ship_stats, strict=True)
                    if name and status is not ShipDamageState.NO_SHIP
                },
            )
            self._state.phase = DecisivePhase.NODE_RESULT
        else:
            _log.error('[决战] 战斗未完成，保留当前节点')
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

        - **ADVANCE_CHOICE**: 分支路径选择浮窗
        - **CHOOSE_FLEET**: 战备舰队获取浮窗
        - **PREPARE_COMBAT**: 地图页无浮窗，准备下一节点
        - **STAGE_CLEAR**: 独立通关页面确认，模型预测只决定是否复核
        """
        _log.info('[决战] 节点 {} 战斗结束, 等待地图加载', self._state.node)

        if self._ctx.stop_event.is_set():
            self._state.phase = DecisivePhase.FINISHED
            return

        session = self._ensure_tracking()
        self._complete_battle_encounter(session)
        self._state.node_completed = True
        self._wait_for_post_combat_page(session)

    def _complete_battle_encounter(self, session: DecisiveTrackingSession) -> None:
        """按遭遇标识只推进一次，并记录真实分支的来源节点。"""
        if self._battle_encounter_id is None:
            raise RuntimeError('缺少成功战斗的遭遇标识，拒绝推进')
        if session.complete_encounter(self._battle_encounter_id):
            completion = session.completed_encounter(self._battle_encounter_id)
            source = completion.decision_node
            branches = (
                len(MapData.get_leftmost_choices(self._state.chapter, self._state.stage, source))
                if source and source not in {'0', 'U'}
                else None
            )
            self._map.configure_route(branches)
        self._state.node = session.current_node if session.current_node != '0' else 'U'
        terminal_weight = sum(
            row['weight']
            for row in session.estimate.state_weights
            if row['stage'] == 'TERMINAL_PENDING'
        )
        predicted_terminal = terminal_weight >= session.sampling.resume_threshold
        if predicted_terminal:
            session.request_node_sample('战斗完成后存在终点候选，等待真实页面复核')

    def _wait_for_post_combat_page(self, session: DecisiveTrackingSession) -> None:
        """战果可能经过短暂地图后才显示选路或战备，等待控件稳定。"""
        previous = None
        stable_map = None
        map_since = 0.0
        deadline = time.monotonic() + self._POST_COMBAT_TIMEOUT
        while time.monotonic() < deadline:
            check_stop(self._ctx.stop_event)
            time.sleep(self._POST_COMBAT_INTERVAL)
            check_stop(self._ctx.stop_event)
            frame = self._ctrl.capture_frame()
            if self._ctx.stop_event.is_set():
                self._state.phase = DecisivePhase.FINISHED
                return
            if not frame.is_newer_than(previous, allow_static=stable_map is not None):
                continue
            previous = frame.snapshot()
            if self._map.is_stage_clear(frame.image):
                if session.stage_clear(frame):
                    self._state.phase = DecisivePhase.STAGE_CLEAR
                    return
                continue
            phase = self._map.detect_decisive_phase(frame.image)
            if phase != DecisivePhase.PREPARE_COMBAT:
                stable_map = None
            if phase is None:
                self._map.continue_combat_result(frame.image)
                continue
            if phase == DecisivePhase.PREPARE_COMBAT:
                if stable_map is None or not self._map.map_icon_is_stable(stable_map, frame):
                    map_since = time.monotonic()
                    stable_map = previous
                    continue
                stable_map = previous
                if time.monotonic() - map_since < 1.0:
                    continue
                self._observe_map_ready(frame)
            elif phase in (DecisivePhase.CHOOSE_FLEET, DecisivePhase.ADVANCE_CHOICE):
                session.map_ready(frame)
            self._state.phase = phase
            return

        session.request_node_sample('战后页面超时')
        raise TimeoutError('战斗已结束，等待下一节点地图或小关通关画面超时')

    def _handle_stage_clear(self, *, resume_rewards: bool = False) -> None:
        """小关通关：确认弹窗 → 收集掉落 → 下一小关或大关。"""
        _log.info('[决战] 小关 {} 通关!', self._state.stage)
        collected = self._map.confirm_stage_clear(resume_rewards=resume_rewards)
        self._close_tracking()
        self._has_chosen_fleet = False
        self._known_start_stage = self._state.stage + 1
        self._state.expected_stage = self._known_start_stage if self._state.stage < 3 else None
        self._state.node = 'A'
        self._inventory_refresh_required = True
        if collected:
            _log.info('[决战] 获得 {} 个掉落: {}', len(collected), collected)

        next_phase = (
            DecisivePhase.CHAPTER_CLEAR if self._state.stage >= 3 else DecisivePhase.ENTER_MAP
        )
        if self._repairs.park_after_settlement():
            self._after_settlement = next_phase
            self._route_repair(RepairOutcome(RepairStatus.NEEDS_BATH))
        else:
            self._repairs.reset_stage()
            self._state.phase = next_phase

    # ── 撤退与暂离 ──────────────────────────────────────────────────────

    def _execute_retreat(self) -> None:
        """执行撤退操作。"""
        _log.info('[决战] 执行撤退')
        self._map.open_retreat_dialog()
        self._map.confirm_retreat()
        self._close_tracking()
        self._known_start_stage = None
        self._has_chosen_fleet = False
        self._inventory_refresh_required = True

    def _execute_leave(self) -> None:
        """执行暂离操作。"""
        _log.info('[决战] 执行暂离')
        self._map.open_retreat_dialog()
        self._map.confirm_leave()
        self._close_tracking()
