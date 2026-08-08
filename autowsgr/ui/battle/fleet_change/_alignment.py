"""舰队成员调整与船池页面操作。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from autowsgr.combat.fleet import FleetSlotRule, ShipSelector
from autowsgr.constants import ship_name_identity
from autowsgr.infra.logger import get_logger
from autowsgr.ui.battle.constants import CLICK_BACK, CLICK_SHIP_SLOT

from ._planning import FleetPlanningMixin


if TYPE_CHECKING:
    from collections.abc import Sequence

    from autowsgr.ui.choose_ship_page import ChooseShipPage

    from ._detect import FleetSnapshot


_log = get_logger('ui.preparation')

# 等待选船页面出现的超时 (秒)
_CHOOSE_PAGE_TIMEOUT: float = 5.0


@dataclass(frozen=True, slots=True)
class _ShipSelection:
    """选船页实际命中的舰名和精确规则。"""

    name: str | None
    option: ShipSelector | None


class _UnresolvedPrimaryError(RuntimeError):
    """连续 OCR 后仍无法确认唯一主选时终止本次换船。"""


class FleetAlignmentMixin(FleetPlanningMixin):
    """执行成员替换、清理、排序和选船页操作。"""

    @staticmethod
    def _deferred_primary_slots(
        snapshot: FleetSnapshot,
        selectors: Sequence[FleetSlotRule | None],
        assigned: Sequence[ShipSelector | None],
    ) -> set[int]:
        """标记身份未知且需要进入主选兜底流程的槽位。"""
        return {
            slot
            for slot, (name, occupied, selector, option) in enumerate(
                zip(snapshot.names, snapshot.occupied, selectors, assigned, strict=True),
            )
            if occupied
            and name is None
            and selector is not None
            and selector.primary is not None
            and option == selector.primary
        }

    def _select_deferred_fallback(
        self,
        target_slot: int,
        selector: FleetSlotRule,
        current: list[str | None],
        occupied: list[bool],
        assigned: list[ShipSelector | None],
        unavailable: set[tuple[int, ShipSelector]],
    ) -> ShipSelector | None:
        """在原物理槽位按 YAML 顺序选择一个全局不冲突的备选。"""
        blocked_identities = {
            identity
            for slot, name in enumerate(current)
            if slot != target_slot
            and occupied[slot]
            and (identity := ship_name_identity(name)) is not None
        }
        blocked_identities.update(
            identity
            for slot, option in enumerate(assigned)
            if slot != target_slot
            and option is not None
            and (identity := ship_name_identity(option.name)) is not None
        )
        for candidate in selector.candidates:
            identity = ship_name_identity(candidate.name)
            if (
                identity is None
                or identity in blocked_identities
                or (target_slot, candidate) in unavailable
            ):
                continue

            _log.info(
                "[准备页] 槽位 {} 身份未知，先用备选 '{}' 释放原舰船",
                target_slot,
                candidate.name,
            )
            selection = self._try_select_option(target_slot, candidate)
            if selection.name is None:
                unavailable.add((target_slot, candidate))
                continue
            if not self._option_matches_name(selection.name, candidate):
                raise RuntimeError(
                    f'选船结果 {selection.name!r} 与规则 {candidate.name!r} 不一致',
                )

            current[target_slot] = selection.name
            occupied[target_slot] = True
            time.sleep(0.3)
            return candidate
        return None

    def _try_deferred_primary(
        self,
        target_slot: int,
        primary: ShipSelector,
        current: list[str | None],
        verified_slots: set[int],
        locked: dict[int, ShipSelector],
    ) -> bool:
        """尝试主选并同步已确认的槽位状态。"""
        selection = self._try_select_option(target_slot, primary)
        if selection.name is None:
            return False
        if not self._option_matches_name(selection.name, primary):
            raise RuntimeError(
                f'选船结果 {selection.name!r} 与规则 {primary.name!r} 不一致',
            )

        current[target_slot] = selection.name
        locked[target_slot] = primary
        verified_slots.discard(target_slot)
        if self._requires_selection_validation(primary):
            verified_slots.add(target_slot)
        time.sleep(0.3)
        return True

    def _resolve_deferred_primaries(
        self,
        current: list[str | None],
        occupied: list[bool],
        assigned: list[ShipSelector | None],
        selectors: list[FleetSlotRule | None],
        verified_slots: set[int],
        unavailable: set[tuple[int, ShipSelector]],
        locked: dict[int, ShipSelector],
        deferred_primary_slots: set[int],
    ) -> None:
        """处理未知主选：有备选时释放回查，无备选时单次搜索。"""
        for target_slot in sorted(deferred_primary_slots):
            deferred_primary_slots.discard(target_slot)
            selector = selectors[target_slot]
            if (
                selector is None
                or selector.primary is None
                or assigned[target_slot] != selector.primary
                or not occupied[target_slot]
                or current[target_slot] is not None
            ):
                continue

            primary = selector.primary
            fallback: ShipSelector | None = None
            if selector.candidates:
                fallback = self._select_deferred_fallback(
                    target_slot,
                    selector,
                    current,
                    occupied,
                    assigned,
                    unavailable,
                )
                if fallback is None:
                    _log.warning(
                        '[准备页] 槽位 {} 没有可用备选，保留原换船流程',
                        target_slot,
                    )
                    continue
                _log.info(
                    "[准备页] 槽位 {} 已释放，重新尝试主选 '{}'",
                    target_slot,
                    primary.name,
                )
            else:
                _log.info(
                    "[准备页] 槽位 {} 身份未知且没有备选，最后搜索一次主选 '{}'",
                    target_slot,
                    primary.name,
                )

            if self._try_deferred_primary(
                target_slot,
                primary,
                current,
                verified_slots,
                locked,
            ):
                continue

            if fallback is None:
                raise _UnresolvedPrimaryError(
                    f'槽位 {target_slot} 连续 OCR 后身份仍未知，且船池未找到唯一主选 '
                    f"'{primary.name}'；无法区分主选已在编队或账号未拥有，停止本次换船",
                )

            unavailable.add((target_slot, primary))
            locked[target_slot] = fallback
            previous = list(assigned)
            replanned = self._plan_target_options(
                selectors,
                current,
                unavailable,
                locked,
            )
            if replanned is None:
                raise RuntimeError(
                    f'目标槽位 {target_slot} 的主选和已选备选无法组成有效舰队',
                )
            assigned[:] = replanned
            for slot, (old, new) in enumerate(zip(previous, replanned, strict=True)):
                if old != new:
                    verified_slots.discard(slot)
            if self._requires_selection_validation(fallback):
                verified_slots.add(target_slot)
            if self._initial_snapshot is not None:
                self._mark_snapshot_verified_slots(
                    self._initial_snapshot,
                    assigned,
                    verified_slots,
                )

    def _align_member_set(
        self,
        current: list[str | None],
        occupied: list[bool],
        assigned: list[ShipSelector | None],
        selectors: list[FleetSlotRule | None],
        verified_slots: set[int],
        unavailable: set[tuple[int, ShipSelector]],
        locked: dict[int, ShipSelector],
        deferred_primary_slots: set[int] | None = None,
    ) -> None:
        """只处理成员集合；不拖拽最终顺序，也不删除多余舰船。"""
        if deferred_primary_slots:
            self._resolve_deferred_primaries(
                current,
                occupied,
                assigned,
                selectors,
                verified_slots,
                unavailable,
                locked,
                deferred_primary_slots,
            )

        attempted: set[tuple[int, ShipSelector, int]] = set()
        for _ in range(48):
            protected, satisfied, target_positions = self._assignment_locations(
                current,
                occupied,
                assigned,
                verified_slots,
            )
            missing = [
                slot for slot in self._target_order(assigned, selectors) if slot not in satisfied
            ]
            if not missing:
                return

            target_slot = missing[0]
            option = assigned[target_slot]
            assert option is not None
            ship_slot = self._replacement_slot(
                current,
                occupied,
                option,
                protected,
                target_positions.get(target_slot),
                attempted,
                target_slot,
            )
            if ship_slot is None:
                _log.warning(
                    "[准备页] 目标槽位 {} 的规则 '{}' 不可用，重新规划备选",
                    target_slot,
                    option.name,
                )
                unavailable.add((target_slot, option))
                locked.pop(target_slot, None)
                verified_slots.discard(target_slot)
                previous = list(assigned)
                replanned = self._plan_target_options(
                    selectors,
                    current,
                    unavailable,
                    locked,
                )
                if replanned is None:
                    raise RuntimeError(
                        f'目标槽位 {target_slot} 的主选和备选均不可用',
                    )
                assigned[:] = replanned
                for slot, (old, new) in enumerate(
                    zip(previous, replanned, strict=True),
                ):
                    if old != new:
                        verified_slots.discard(slot)
                # 重规划后新分配的备选若已在队内且满足约束，直接用首次快照
                # 标记为已验证，避免已就位备选不在船池时反复进选船页重选。
                if self._initial_snapshot is not None:
                    self._mark_snapshot_verified_slots(
                        self._initial_snapshot,
                        assigned,
                        verified_slots,
                    )
                continue

            _log.info(
                "[准备页] 更换物理槽位 {} <- '{}' (逻辑槽位 {}, 原: '{}')",
                ship_slot,
                option.name,
                target_slot,
                current[ship_slot],
            )
            selection = self._try_select_option(
                ship_slot,
                option,
            )
            attempted.add((target_slot, option, ship_slot))
            if selection.name is None:
                continue
            if not self._option_matches_name(selection.name, option):
                raise RuntimeError(
                    f'选船结果 {selection.name!r} 与规则 {option.name!r} 不一致',
                )

            current[ship_slot] = selection.name
            occupied[ship_slot] = True
            locked[target_slot] = option
            verified_slots.discard(target_slot)
            if self._requires_selection_validation(option):
                verified_slots.add(target_slot)
            time.sleep(0.3)

        raise RuntimeError('成员集合调整次数超过安全上限')

    def _remove_extra_members(
        self,
        current: list[str | None],
        occupied: list[bool],
        assigned: Sequence[ShipSelector | None],
        verified_slots: set[int],
    ) -> None:
        """目标成员齐全后，从后往前删除所有多余或未知成员。"""
        protected, _, _ = self._assignment_locations(
            current,
            occupied,
            assigned,
            verified_slots,
        )
        for slot in range(5, -1, -1):
            if slot in protected or not occupied[slot]:
                continue
            _log.info("[准备页] 移除多余槽位 {} 的 '{}'", slot, current[slot])
            self._change_single_ship(slot, None, slot_occupied=True)
            current[slot] = None
            occupied[slot] = False
            time.sleep(0.3)

    def _refresh_members(
        self,
        current: list[str | None],
        occupied: list[bool],
        expected_pool: Sequence[str],
    ) -> None:
        """删除或替换后重新获取成员集合和占用状态。"""
        snapshot = self.detect_fleet_snapshot(expected_pool=expected_pool)
        current[:] = snapshot.names
        occupied[:] = snapshot.occupied

    # 首次调整时完成成员复用、缺员补充、多余成员移除和压缩后补位。
    def _full_align(
        self,
        current: list[str | None],
        occupied: list[bool],
        assigned: list[ShipSelector | None],
        selectors: list[FleetSlotRule | None],
        verified_slots: set[int],
        unavailable: set[tuple[int, ShipSelector]],
        locked: dict[int, ShipSelector],
        expected_pool: Sequence[str],
        deferred_primary_slots: set[int] | None = None,
    ) -> None:
        """首次将当前舰队调整为目标成员集合。"""
        self._align_member_set(
            current,
            occupied,
            assigned,
            selectors,
            verified_slots,
            unavailable,
            locked,
            deferred_primary_slots,
        )
        self._remove_extra_members(current, occupied, assigned, verified_slots)
        self._refresh_members(current, occupied, expected_pool)
        self._align_member_set(
            current,
            occupied,
            assigned,
            selectors,
            verified_slots,
            unavailable,
            locked,
            deferred_primary_slots,
        )

    # OCR 验证失败后，只修正成员集合，不在此阶段拖拽排序。
    def _local_fix(
        self,
        current: list[str | None],
        occupied: list[bool],
        assigned: list[ShipSelector | None],
        selectors: list[FleetSlotRule | None],
        verified_slots: set[int],
        unavailable: set[tuple[int, ShipSelector]],
        locked: dict[int, ShipSelector],
        expected_pool: Sequence[str],
    ) -> None:
        """重试时重新补齐成员，再清理多余成员。"""
        self._align_member_set(
            current,
            occupied,
            assigned,
            selectors,
            verified_slots,
            unavailable,
            locked,
        )
        self._remove_extra_members(current, occupied, assigned, verified_slots)
        self._refresh_members(current, occupied, expected_pool)

    # 从左到右拖拽舰船，使当前舰队顺序与目标槽位一致。
    def _reorder(
        self,
        current: list[str | None],
        desired: list[str | None],
    ) -> None:
        """通过拖拽调整舰船顺序，并同步更新 current。"""
        for i in range(6):
            target = desired[i]
            if target is None:
                break
            target_identity = ship_name_identity(target)
            if ship_name_identity(current[i]) == target_identity:
                continue
            try:
                src = next(
                    idx
                    for idx, current_name in enumerate(current)
                    if ship_name_identity(current_name) == target_identity
                )
            # 当前舰队中找不到目标舰船时，保留现场交给最终验证处理。
            except StopIteration:
                _log.warning(
                    "[准备页] 位置对齐: '{}' 不在当前舰队中, 跳过",
                    target,
                )
                continue
            _log.info(
                "[准备页] 位置对齐: 槽位 {} <- '{}' (从槽位 {})",
                i,
                target,
                src,
            )
            self._circular_move(src, i, current)

    # 将一艘舰船从源槽位拖到目标槽位，并模拟游戏中的循环位移。
    def _circular_move(
        self,
        src: int,
        dst: int,
        current: list[str | None],
    ) -> None:
        """执行一次拖拽，并更新内存中的舰队顺序。"""
        # 源槽位和目标槽位相同时，不需要执行拖拽。
        if src == dst:
            return
        # sx、sy 是源槽位坐标，dx、dy 是目标槽位坐标。
        sx, sy = CLICK_SHIP_SLOT[src]
        dx, dy = CLICK_SHIP_SLOT[dst]
        self._ctrl.swipe(sx, sy, dx, dy, duration=0.5)

        # ship 是从源槽位取出的舰名，用于同步游戏中的循环位移。
        ship = current.pop(src)
        current.insert(dst, ship)
        time.sleep(0.5)

    def _open_choose_page(self, slot: int) -> ChooseShipPage:
        """打开指定物理槽位的选船页面。"""
        from autowsgr.ui.choose_ship_page import ChooseShipPage
        from autowsgr.ui.utils import wait_for_page

        self.click_ship_slot(slot)
        wait_for_page(
            self._ctrl,
            ChooseShipPage.is_current_page,
            timeout=_CHOOSE_PAGE_TIMEOUT,
            source='编队',
            target='编队选船',
        )
        return ChooseShipPage(self._ctx)

    def _cancel_choose_page(self) -> None:
        """规则未命中时退出选船页，恢复到编队准备页。"""
        from autowsgr.ui.utils import wait_for_page

        self._ctrl.click(*CLICK_BACK)
        wait_for_page(
            self._ctrl,
            self.is_current_page,
            timeout=_CHOOSE_PAGE_TIMEOUT,
            source='编队选船',
            target='编队',
        )

    def _try_select_option(
        self,
        slot: int,
        option: ShipSelector,
    ) -> _ShipSelection:
        """尝试一条精确规则；未命中返回 None，技术异常直接上抛。"""
        if self._ctx.ocr is None:
            raise RuntimeError('智能换船需要 OCR 引擎')

        choose_page = self._open_choose_page(slot)
        selected = choose_page.change_single_ship(
            option,
            use_search=self._use_search,
        )
        if selected is None:
            self._cancel_choose_page()
        return _ShipSelection(name=selected, option=option)

    # 打开指定槽位的选船页面，完成单艘舰船的选择或移除。
    def _change_single_ship(
        self,
        slot: int,
        name: str | None,
        *,
        selector: Sequence[ShipSelector] | None = None,
        slot_occupied: bool = True,
    ) -> str | None:
        """返回选船页面实际选中的舰名。"""
        # 目标为空且当前槽位也为空时，不需要打开选船页面。
        if name is None and not slot_occupied:
            return None

        # FleetChange 决定候选顺序，页面每次只执行一条明确规则。
        choose_page = self._open_choose_page(slot)
        if name is None:
            return choose_page.change_single_ship(None, use_search=self._use_search)

        options = tuple(selector) if selector is not None else (ShipSelector(name=name),)
        for option in options:
            selected = choose_page.change_single_ship(
                option,
                use_search=self._use_search,
            )
            if selected is not None:
                return selected

        candidates = [option.name for option in options]
        self._cancel_choose_page()
        _log.error('[准备页] 未在选船列表中找到满足规则的候选: {}', candidates)
        raise RuntimeError(f'未找到满足条件的目标舰船: {candidates}')
