"""记录决战舰船的伤情和维修进度，确认编队能否出征。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from autowsgr.constants import DECISIVE_SKILL_NAMES, normalize_ship_name, ship_name_identity
from autowsgr.infra import ActionFailedError
from autowsgr.infra.logger import get_logger
from autowsgr.ops.navigate import goto_page
from autowsgr.ops.repair_policy import (
    BLIND_RECHECK_SECONDS,
    RepairAction,
    decide_repair,
    parse_repair_duration,
)
from autowsgr.types import DecisiveEntryStatus, PageName, ShipDamageState
from autowsgr.ui.bath_page import BathPage
from autowsgr.ui.bath_page.signatures import SWIPE_DELAY, SWIPE_DURATION, SWIPE_END, SWIPE_START
from autowsgr.ui.decisive.preparation import is_complete_fleet, read_complete_fleet
from autowsgr.ui.utils.navigation import NavigationError


if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

    from autowsgr.context import GameContext
    from autowsgr.context.ship import Ship
    from autowsgr.infra import DecisiveConfig, UserConfig
    from autowsgr.ui.bath_page.page import RepairShipInfo
    from autowsgr.ui.decisive.battle_page import DecisiveBattlePage
    from autowsgr.ui.decisive.map_controller import DecisiveMapController
    from autowsgr.ui.decisive.preparation import DecisiveBattlePreparationPage, RepairSnapshot


_log = get_logger('ops.decisive')


class RepairStatus(StrEnum):
    READY = 'ready'
    NEEDS_BATH = 'needs_bath'
    WAITING = 'waiting'
    REENTER = 'reenter'
    RECHECK = 'recheck'
    STOPPED = 'stopped'


@dataclass(frozen=True, slots=True)
class RepairOutcome:
    status: RepairStatus
    target_size: int = 0
    wait_seconds: float | None = None
    targets: tuple[str, ...] = ()
    detail: str = ''
    snapshot: RepairSnapshot | None = None
    resume_immediately: bool = False


def _named_ships(names: Iterable[str | None]) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in names:
        name = normalize_ship_name(raw)
        identity = ship_name_identity(name)
        if name and identity and name not in DECISIVE_SKILL_NAMES:
            result.setdefault(identity, name)
    return result


class DecisiveRepairCoordinator:
    """记录本小关已获得的舰船及其维修状态。

    出征前，从同一张准备页截图核对每艘在队舰船的名称和伤情，并确认哪些位置是空的。
    """

    def __init__(
        self,
        ctx: GameContext,
        config: DecisiveConfig,
        *,
        user_config: UserConfig | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._clock = clock
        self._settings = user_config if user_config is not None else ctx.config
        self._ctx = ctx
        self._config = config
        self._configured = _named_ships([*config.level1, *config.level2])
        self.reset_stage()

    def reset_stage(self) -> None:
        """开始新一轮或确认切换小关时，清理本小关的登记。"""
        self._chapter_stage: tuple[int, int] | None = None
        self._acquired: dict[str, Ship] = {}  # 只引用本小关实见舰船在 ctx 中的记录
        self._damage: dict[str, ShipDamageState] = {}
        self._pending: dict[str, str] = {}
        self._long_repairs: set[str] = set()
        self._unconfirmed_bucket: tuple[str, int] | None = None
        self._target_size = 0
        self._saved = False
        self._settled = False
        self._retry_at: dict[str, float] = {}
        self._failed_quotes: set[str] = set()

    @property
    def saved(self) -> bool:
        return self._saved

    @property
    def _deadlines(self) -> dict[str, float]:
        return {
            identity: at
            for identity, ship in self._acquired.items()
            if (at := ship.repair_recheck_at or ship.repair_end_time)
        }

    @property
    def due_identities(self) -> frozenset[str]:
        now = self._clock()
        return frozenset(identity for identity, end in self._deadlines.items() if end <= now)

    @property
    def target_size(self) -> int:
        return self._target_size

    @property
    def acquired(self) -> tuple[str, ...]:
        return tuple(ship.name for ship in self._acquired.values())

    @property
    def can_continue_without_pending(self) -> bool:
        """已获得的其他配置舰足以组队时，将节点与派修一同排队。"""
        pool = self._acquired.keys() & self._configured.keys()
        return len(pool - self.blocked_identities) >= self.target_size > 0

    @property
    def damaged_identities(self) -> frozenset[str]:
        """按本轮维修标准标出应优先换下的舰船。"""
        return frozenset(
            identity
            for identity, state in self._damage.items()
            if self._config.repair_level <= state < ShipDamageState.REPAIRING
        )

    @property
    def protected_identities(self) -> frozenset[str]:
        """保护配置舰、已获得舰及其别名。"""
        return frozenset(self._configured.keys() | self._acquired.keys())

    @property
    def blocked_identities(self) -> frozenset[str]:
        """等待派修或等待复查的舰船不能出征。"""
        return frozenset(
            identity
            for identity in self._acquired
            if self._is_repairing(identity)
            or (identity in self._pending and identity not in self._long_repairs)
        )

    def observe_inventory(
        self,
        acquired: Iterable[str],
        *,
        chapter: int,
        stage: int,
        damage: Mapping[str, ShipDamageState] | None = None,
    ) -> None:
        """按名登记已获得舰船和已确认的伤情。"""
        pair = (chapter, stage)
        if self._chapter_stage is not None and pair != self._chapter_stage:
            raise ValueError('决战小关已改变，无法沿用之前的维修记录')
        self._chapter_stage = pair
        for identity, name in _named_ships(acquired).items():
            ship = self._ctx.get_ship(name)
            self._acquired[identity] = ship
            if ship.repair_end_time or ship.repair_recheck_at:
                self._pending[identity] = name
                self._failed_quotes.discard(identity)
                self._long_repairs.discard(identity)
                self._retry_at.pop(identity, None)
            elif ship.damage_state is ShipDamageState.REPAIRING or ship.repairing:
                self._record_repair_marker(identity, self._clock(), 0.0)
            elif ship.damage_state >= self._config.repair_level:
                self._damage[identity] = ship.damage_state
                if self._settings.quick_repair_threshold_seconds is not None:
                    self._pending[identity] = name
        count = len(self._acquired.keys() & self._configured.keys())
        self._target_size = max(self._target_size, min(6, count))
        for name, state in (damage or {}).items():
            identity = ship_name_identity(name)
            if identity in self._acquired:
                self._record_health(identity, state)

    def _is_repairing(self, identity: str) -> bool:
        ship = self._acquired[identity]
        return ship.repairing or bool(ship.repair_end_time or ship.repair_recheck_at)

    def _record_health(self, identity: str, state: ShipDamageState) -> None:
        if not isinstance(state, ShipDamageState) or state is ShipDamageState.NO_SHIP:
            raise ValueError('准备页未能确认这艘船的伤情')
        now = self._clock()
        ship = self._acquired[identity]
        known_end = ship.repair_end_time
        due = ship.repair_recheck_at or known_end or None
        if state is ShipDamageState.REPAIRING or ship.repairing:
            state = ShipDamageState.REPAIRING
            self._record_repair_marker(identity, now, known_end)
        elif due is not None and now < due:
            # 同一段维修时间内的重复观察不改变复查时刻。
            return
        else:
            ship.repair_end_time = ship.repair_recheck_at = 0.0
            if state != self._damage.get(identity):
                self._long_repairs.discard(identity)
            if state < self._config.repair_level:
                self._pending.pop(identity, None)
                self._failed_quotes.discard(identity)
                self._retry_at.pop(identity, None)
            elif due is not None or self._settings.quick_repair_threshold_seconds is not None:
                self._pending[identity] = ship.name
        self._damage[identity] = state
        ship.damage_state = state

    def _record_repair_marker(self, identity: str, now: float, known_end: float) -> None:
        ship = self._acquired[identity]
        name = ship.name
        if self._damage.get(identity) is not ShipDamageState.REPAIRING:
            if known_end > now:
                _log.info(
                    '[决战] {} 显示维修中，按已登记的入浴时间 {:.1f} 秒后复查',
                    name,
                    known_end - now,
                )
            else:
                _log.info(
                    '[决战] {} 显示维修中，时长未知，{} 秒后复查', name, BLIND_RECHECK_SECONDS
                )
        if max(ship.repair_recheck_at, known_end) <= now:
            ship.repair_recheck_at = now + BLIND_RECHECK_SECONDS
        self._pending[identity] = name
        self._long_repairs.discard(identity)
        self._failed_quotes.discard(identity)
        self._retry_at.pop(identity, None)

    @property
    def needs_dispatch(self) -> bool:
        """是否有需在浴室读取时长或安排入浴的舰船。"""
        return bool(self._dispatchable())

    def _dispatchable(self) -> set[str]:
        now = self._clock()
        return {
            key
            for key in self._pending
            if key not in self._long_repairs
            and not self._is_repairing(key)
            and key not in self._failed_quotes
            and self._retry_at.get(key, 0) <= now
        }

    def _healthy_count(self, identities: Iterable[str]) -> int:
        blocked = self.blocked_identities
        return sum(
            self._damage.get(key) in (ShipDamageState.NORMAL, ShipDamageState.MODERATE)
            and self._damage[key] < self._config.repair_level
            and key not in blocked
            for key in identities
        )

    def _outcome(
        self,
        status: RepairStatus,
        *,
        wait_seconds: float | None = None,
        detail: str = '',
        snapshot: RepairSnapshot | None = None,
    ) -> RepairOutcome:
        return RepairOutcome(
            status,
            self.target_size,
            wait_seconds,
            tuple(self._pending.values()),
            detail,
            snapshot,
        )

    def _check_stop(self) -> None:
        if self._ctx.stop_event.is_set():
            raise InterruptedError('决战维修期间收到停止请求')

    def read_complete_snapshot(
        self,
        page: DecisiveBattlePreparationPage,
        *,
        fresh: bool = False,
        expected: Sequence[str | None] | None = None,
        recheck_fleet: Callable[[], None] | None = None,
    ) -> tuple[list[str | None], dict[int, ShipDamageState]]:
        """舰名或伤情没读全时重新截图；舰名或顺序与预期不符时，核对编队后再读一次。"""
        names, damage = read_complete_fleet(page, self._ctx.stop_event, fresh=fresh)
        if expected is not None and list(map(ship_name_identity, names)) != list(
            map(ship_name_identity, expected)
        ):
            if recheck_fleet is None:
                raise ActionFailedError('决战维修复核的舰船名称或顺序与已确认编队不一致')
            _log.info('[决战] 准备页读到的舰名或顺序与预期不符，重新核对编队 {}', names)
            recheck_fleet()
            return self.read_complete_snapshot(page, fresh=True, expected=expected)
        return names, damage

    def _quick_repair(
        self,
        page: DecisiveBattlePreparationPage,
        fleet: Sequence[str | None],
        slot: int,
        identity: str,
        recheck_fleet: Callable[[], None] | None,
    ) -> RepairSnapshot:
        """按舰名和编队顺序找到要快修的船，确认它已达到出征标准后才计入用桶数。"""
        limited = self._settings.quick_repair_threshold_seconds is not None
        selected = _named_ships(fleet).keys() & self._configured.keys()
        while True:
            names, damage = self.read_complete_snapshot(
                page, fresh=True, expected=fleet, recheck_fleet=recheck_fleet
            )
            self._record_fleet(names, damage)
            state = damage[slot]
            ready = self._healthy_count(self._configured.keys() & self._acquired.keys())
            missing = max(0, self.target_size - ready)
            attempts = self._unconfirmed_bucket[1] if self._unconfirmed_bucket else 0
            if state < self._config.repair_level and identity not in self.blocked_identities:
                if attempts:
                    self._ctx.quick_repair_used += 1
                    self._unconfirmed_bucket = None
                    _log.info('[决战] 已确认 {} 快修后可出击，仍缺 {} 艘', names[slot], missing)
                return names, damage
            unavailable = self._is_repairing(identity)
            if attempts and (attempts >= (1 if limited else 3) or unavailable):
                raise ActionFailedError(f'决战快修后未确认 {names[slot]} 恢复')
            if unavailable:
                return names, damage
            if limited and (
                not missing
                or identity not in selected
                or identity not in self._long_repairs
                or self.needs_dispatch
                or self._healthy_count(selected) + len(selected & self._long_repairs)
                < self.target_size
            ):
                return names, damage
            if self._settings.repair_manually or not self._config.use_quick_repair:
                raise ActionFailedError('需要进行手动修理')
            _log.info(
                '[决战] 快修前有 {} 艘可出击，缺 {} 艘，对 {} 使用一个快修桶',
                ready,
                missing,
                names[slot],
            )
            self._check_stop()
            self._unconfirmed_bucket = identity, attempts + 1
            page.repair_slots([slot])
            if self._ctx.stop_event.is_set():
                return names, damage

    def _record_fleet(
        self, fleet: Sequence[str | None], damage: Mapping[int, ShipDamageState]
    ) -> dict[int, str] | None:
        """核对在队舰船的名称和伤情，并按编队顺序登记需要维修的舰船。"""
        if len(fleet) != 6:
            raise ValueError(f'准备页共有 6 个编队位置（含空位），本次读到 {len(fleet)} 个')
        present = _named_ships(fleet)
        if len(present) != sum(bool(name) for name in fleet):
            raise ValueError('准备页存在同名舰船，无法确定维修目标')
        if not present.keys() <= self._acquired.keys():
            raise ValueError('准备页出现未登记的舰船，请复核库存')
        if not is_complete_fleet(fleet, damage):
            return None
        required: dict[int, str] = {}
        for slot, raw_name in enumerate(fleet):
            identity = ship_name_identity(raw_name)
            if identity is None:
                continue
            state = damage[slot]
            self._record_health(identity, state)
            if state >= self._config.repair_level:
                required[slot] = identity
                self._pending[identity] = present[identity]
        return required

    def prepare(
        self,
        page: DecisiveBattlePreparationPage,
        *,
        fleet: Sequence[str | None],
        damage: Mapping[int, ShipDamageState],
        acquired: Iterable[str],
        chapter: int,
        stage: int,
        recheck_fleet: Callable[[], None] | None = None,
    ) -> RepairOutcome:
        """核对实际编队，按缺额快修或暂离前往浴室。"""
        if self._ctx.stop_event.is_set():
            return self._outcome(RepairStatus.STOPPED)
        self.observe_inventory(acquired, chapter=chapter, stage=stage)
        required = self._record_fleet(fleet, damage)
        if required is None:
            return self._outcome(RepairStatus.RECHECK, detail='无法确认当前舰名或伤情')
        if self._settings.repair_manually and self.damaged_identities:
            raise ActionFailedError('需要进行手动修理')
        last_snapshot = None
        if self._unconfirmed_bucket is not None:
            identity, _ = self._unconfirmed_bucket
            slots = [ship_name_identity(name) for name in fleet]
            if identity not in slots:
                raise ActionFailedError(
                    f'用桶后在准备页找不到 {self._acquired[identity].name}，无法确认快修结果'
                )
            slot = slots.index(identity)
            last_snapshot = self._quick_repair(page, fleet, slot, identity, recheck_fleet)
            required.pop(slot, None)
            if self._ctx.stop_event.is_set():
                return self._outcome(RepairStatus.STOPPED)
        if self.needs_dispatch and self._settings.quick_repair_threshold_seconds is not None:
            return self._outcome(RepairStatus.NEEDS_BATH)
        # 先核对能否用这些长修候选补齐整队，以免只修一部分后仍需等待。
        selected = _named_ships(fleet).keys() & self._configured.keys()
        possible = self._healthy_count(selected) + len(selected & self._long_repairs)
        if self._settings.quick_repair_threshold_seconds is None or possible >= self.target_size:
            for slot, identity in required.items():
                if self._is_repairing(identity):
                    continue
                last_snapshot = self._quick_repair(page, fleet, slot, identity, recheck_fleet)
                if self._ctx.stop_event.is_set():
                    break
        if self._ctx.stop_event.is_set():
            return self._outcome(RepairStatus.STOPPED)
        return self._check_readiness(selected, last_snapshot)

    def _check_readiness(
        self, selected: set[str], snapshot: RepairSnapshot | None
    ) -> RepairOutcome:
        healthy = self._healthy_count(selected)
        if healthy >= self.target_size and healthy > 0:
            self._saved = False
            return self._outcome(RepairStatus.READY, snapshot=snapshot)
        if self._pending:
            return self._outcome(RepairStatus.NEEDS_BATH)
        return self._outcome(
            RepairStatus.RECHECK,
            detail=f'本小关需要 {self.target_size} 艘舰船，当前编队有 {healthy} 艘可以出征',
        )

    def park_after_settlement(self) -> bool:
        """已回到总览，可直接处理终点产生或浴室满时保留的伤舰。"""
        remaining = self._pending.keys() - self._long_repairs - self._deadlines.keys()
        if not remaining:
            return False
        self._check_stop()
        if self._settings.repair_manually:
            raise ActionFailedError('需要进行手动修理')
        self._saved = self._settled = True
        return True

    def save_progress(
        self,
        preparation: DecisiveBattlePreparationPage | None,
        map_controller: DecisiveMapController,
    ) -> None:
        """暂离并确认返回章节总览，交由调度器按名派修。"""
        self._check_stop()
        if self._settings.repair_manually and self.needs_dispatch:
            raise ActionFailedError('需要进行手动修理')
        if not self._pending or self._chapter_stage is None:
            raise RuntimeError('缺少可确认的维修目标，无法暂离')
        if preparation is not None and preparation.is_current_page(self._ctx.ctrl.screenshot()):
            self._check_stop()
            preparation.go_back()
        self._check_stop()
        map_controller.leave_to_overview()
        self._saved = True
        self._check_stop()
        _log.info(
            '[决战] 已暂离第 {} 章第 {} 小关，待处理舰船：{}',
            *self._chapter_stage,
            '、'.join(self._pending.values()),
        )

    @staticmethod
    def _card_signature(cards: Sequence[RepairShipInfo]) -> tuple:
        return tuple((card.name, round(card.position[0], 2)) for card in cards)

    def _find_card(self, page: BathPage, identity: str) -> RepairShipInfo | None:
        self._check_stop()
        if page.has_choose_repair_overlay(self._ctx.ctrl.screenshot()):
            page.close_choose_repair_overlay()
        self._check_stop()
        page.go_to_choose_repair()
        # 弹窗可能保留上次的滚动位置，两边都查到页尾。遇到目标舰即按这张卡的时长处理。
        for toward_start in (True, False):
            seen = set()
            while True:
                self._check_stop()
                cards = page.recognize_repair_ships()
                matches = [card for card in cards if ship_name_identity(card.name) == identity]
                if len(matches) > 1:
                    raise ActionFailedError('浴室出现多个同名维修目标，无法区分')
                if matches:
                    return matches[0]
                signature = self._card_signature(cards)
                if signature in seen:
                    break
                seen.add(signature)
                self._check_stop()
                if toward_start:
                    self._ctx.ctrl.swipe(*SWIPE_END, *SWIPE_START, duration=SWIPE_DURATION)
                    self._ctx.stop_event.wait(SWIPE_DELAY)
                else:
                    page._swipe_left()
        return None

    def _quote_and_dispatch(self, page: BathPage, identity: str, name: str) -> bool:
        """读取时长并处理一艘舰。浴室无法接单时暂停本批操作。"""
        try:
            card = self._find_card(page, identity)
        except NavigationError:
            self._check_stop()
            screen = self._ctx.ctrl.screenshot()
            if not page.is_current_page(screen) or page.has_choose_repair_overlay(screen):
                raise
            # 浴室没有打开选船页，等有空闲浴位后再派这艘船入浴。
            self._retry_at[identity] = self._clock() + max(
                5.0, self._ctx.bathroom.get_waiting_time()
            )
            return False
        seconds = parse_repair_duration(card.repair_time) if card else None
        decision = decide_repair(
            required=True,
            repairing=False,
            repair_seconds=seconds,
            quick_threshold_seconds=self._settings.quick_repair_threshold_seconds,
        )
        if decision.action is RepairAction.RECHECK:
            self._failed_quotes.add(identity)
            self._retry_at.pop(identity, None)
            _log.warning('[决战] 在浴室未读到 {} 的维修时长，本次跳过这艘船', name)
            return True
        if decision.action is RepairAction.QUICK:
            self._long_repairs.add(identity)
            self._retry_at.pop(identity, None)
            _log.info('[决战] {} 需修 {} 秒，保留为缺员时的快修候选', name, seconds)
            return True
        assert card is not None
        assert decision.action is RepairAction.BATH
        if not self._ctx.bathroom.is_available():
            self._retry_at[identity] = self._clock() + max(
                1.0, self._ctx.bathroom.get_waiting_time()
            )
            return True
        self._check_stop()
        dispatched_at = self._clock()
        self._ctx.ctrl.click(*card.position)
        if not page.wait_repair_accepted():
            self._ctx.bathroom.mark_unknown()
            self._retry_at[identity] = self._clock() + 5.0
            return False
        assert seconds is not None
        deadline = dispatched_at + seconds
        self._acquired[identity].record_bath(deadline)
        self._retry_at.pop(identity, None)
        _log.info('[决战] {} 已入浴，{} 秒后复查', name, seconds)
        self._ctx.bathroom.occupy(seconds)
        self._check_stop()
        return True

    def dispatch_pending(self) -> RepairOutcome:
        """到浴室逐一核实待修舰名和耗时，立即安排短修。"""
        if self._ctx.stop_event.is_set():
            return self._outcome(RepairStatus.STOPPED)
        if not self._saved:
            raise RuntimeError('尚未确认决战暂离，请先保存进度')
        needs_quote = self._dispatchable()
        if not needs_quote:
            return self.poll()
        goto_page(self._ctx, PageName.BATH)
        self._check_stop()
        page = BathPage(self._ctx)
        self._ctx.bathroom.slot_count = self._settings.bathroom_count
        for identity, name in tuple(self._pending.items()):
            if identity not in needs_quote:
                continue
            if self._ctx.stop_event.is_set():
                return self._outcome(RepairStatus.STOPPED)
            if self._is_repairing(identity):
                return self._outcome(RepairStatus.RECHECK, detail=f'需复核舰船在修状态：{name}')
            if not self._quote_and_dispatch(page, identity, name):
                break
        if self._ctx.stop_event.is_set():
            return self._outcome(RepairStatus.STOPPED)
        if page.has_choose_repair_overlay(self._ctx.ctrl.screenshot()):
            self._check_stop()
            page.close_choose_repair_overlay()
        self._check_stop()
        goto_page(self._ctx, PageName.MAIN)
        return self.poll()

    def poll(self) -> RepairOutcome:
        """根据当前时间、可用舰和维修队列决定下一步。"""
        if self._ctx.stop_event.is_set():
            return self._outcome(RepairStatus.STOPPED)
        if not self._saved:
            raise RuntimeError('没有已保存的决战维修进度')
        now = self._clock()
        pool = self._acquired.keys() & self._configured.keys()
        if self._dispatchable():
            return self._outcome(RepairStatus.NEEDS_BATH)
        return self._next_resume(now, pool)

    def _next_resume(self, now: float, pool: set[str]) -> RepairOutcome:
        slot_waits = [at - now for at in self._retry_at.values() if at > now]
        if self._settled:
            if slot_waits:
                return self._outcome(RepairStatus.WAITING, wait_seconds=min(slot_waits))
            return self._outcome(RepairStatus.REENTER)
        # 有些候补舰只知道舰名，要换入编队后才能核对伤情。
        if self._failed_quotes and len(pool - self._failed_quotes) < self.target_size:
            names = '、'.join(self._pending[key] for key in sorted(self._failed_quotes & pool))
            return self._outcome(
                RepairStatus.RECHECK, detail=f'未读到维修时长，缺少可补位的舰船，保留存档：{names}'
            )
        if self.can_continue_without_pending or self.due_identities:
            return self._outcome(RepairStatus.REENTER)
        future = slot_waits + [end - now for end in self._deadlines.values() if end > now]
        if future:
            return self._outcome(RepairStatus.WAITING, wait_seconds=min(future))
        return self._outcome(RepairStatus.RECHECK, detail='未能确认有足够的舰船可以出征')

    def validate_resume(self, battle_page: DecisiveBattlePage) -> None:
        """重入前核实保存的章节与小关。"""
        self._check_stop()
        if not self._saved or self._chapter_stage is None:
            raise RuntimeError('未找到可恢复的决战维修进度')
        self.validate_stage(battle_page, *self._chapter_stage)

    def validate_stage(self, battle_page: DecisiveBattlePage, chapter: int, stage: int) -> None:
        """暂离重进或切换小关时，先核实总览的真实存档入口。"""
        self._check_stop()
        status = battle_page.detect_entry_status(timeout=5.0)
        self._check_stop()
        if status not in {DecisiveEntryStatus.CHALLENGING, DecisiveEntryStatus.REFRESHED}:
            raise RuntimeError('当前决战入口无法继续已保存的进度')
        screen = self._ctx.ctrl.screenshot()
        if battle_page._read_chapter(screen) != chapter:
            raise RuntimeError(f'准备继续决战第 {chapter} 章，总览未显示该章节')
        actual_stage = battle_page.detect_stage(screen, chapter)
        self._check_stop()
        if type(actual_stage) is not int or actual_stage != stage:
            raise RuntimeError(f'准备继续决战第 {chapter} 章第 {stage} 小关，总览未显示该小关')
