"""舰队目标分配与槽位规划。

本模块根据 YAML 规则、OCR 快照和当前成员计算唯一目标及槽位关系，
不执行页面操作或舰队状态调整。
"""

from __future__ import annotations

from functools import cache
from typing import TYPE_CHECKING

from autowsgr.constants import normalize_ship_name, ship_name_identity
from autowsgr.infra.logger import get_logger

from ._rules import FleetRuleMixin


if TYPE_CHECKING:
    from collections.abc import Sequence

    from autowsgr.combat.fleet import FleetSlotRule, ShipSelector

    from ._detect import FleetSnapshot


_log = get_logger('ui.preparation')


class FleetPlanningMixin(FleetRuleMixin):
    """提供目标分配和槽位关系计算。"""

    @classmethod
    def _plan_target_options(
        cls,
        selectors: list[FleetSlotRule | None],
        current: Sequence[str | None] = (),
        unavailable: (
            set[tuple[int, ShipSelector]] | frozenset[tuple[int, ShipSelector]]
        ) = frozenset(),
        locked: dict[int, ShipSelector] | None = None,
    ) -> list[ShipSelector | None] | None:
        """按主选优先级规划全局唯一的精确选船规则。"""
        locked = locked or {}
        current_identities = {
            identity for name in current if (identity := ship_name_identity(name)) is not None
        }
        slot_options: list[tuple[ShipSelector | None, ...]] = []

        for slot, selector in enumerate(selectors):
            if selector is None:
                if slot in locked:
                    return None
                slot_options.append((None,))
                continue

            locked_option = locked.get(slot)
            if locked_option is not None:
                if locked_option not in selector.options or (slot, locked_option) in unavailable:
                    return None
                slot_options.append((locked_option,))
                continue

            if selector.primary is not None and (slot, selector.primary) not in unavailable:
                slot_options.append((selector.primary,))
                continue

            ranked = [
                (index, option)
                for index, option in enumerate(selector.candidates)
                if (slot, option) not in unavailable
            ]
            ranked.sort(
                key=lambda item: (
                    ship_name_identity(item[1].name) not in current_identities,
                    item[0],
                ),
            )
            slot_options.append(tuple(option for _, option in ranked))

        @cache
        def assign(
            slot: int,
            used: tuple[str, ...],
        ) -> tuple[int, tuple[int, ...], tuple[ShipSelector | None, ...]] | None:
            if slot >= len(slot_options):
                return 0, (), ()

            best: tuple[int, tuple[int, ...], tuple[ShipSelector | None, ...]] | None = None
            used_set = set(used)
            for rank, option in enumerate(slot_options[slot]):
                if option is None:
                    result = assign(slot + 1, used)
                    identity = None
                else:
                    identity = ship_name_identity(option.name)
                    if identity is None or identity in used_set:
                        continue
                    result = assign(slot + 1, tuple(sorted((*used, identity))))
                if result is None:
                    continue

                rest_cost, rest_priority, rest_assignment = result
                replacement_cost = 0 if option is None or identity in current_identities else 1
                candidate = (
                    replacement_cost + rest_cost,
                    (rank, *rest_priority),
                    (option, *rest_assignment),
                )
                if best is None or candidate[:2] < best[:2]:
                    best = candidate
            return best

        result = assign(0, ())
        return list(result[2]) if result is not None else None

    @classmethod
    def _ocr_target_pool(
        cls,
        selectors: Sequence[FleetSlotRule | None],
    ) -> list[str]:
        """返回全部主选和备选组成的位置无关 OCR 上下文池。"""
        pool: list[str] = []
        seen: set[str] = set()
        for selector in selectors:
            if selector is None:
                continue
            for option in selector.options:
                normalized = normalize_ship_name(option.name)
                identity = ship_name_identity(normalized)
                if normalized is not None and identity is not None and identity not in seen:
                    pool.append(normalized)
                    seen.add(identity)
        return pool

    @classmethod
    def _target_names(
        cls,
        assigned: Sequence[ShipSelector | None],
    ) -> list[str | None]:
        """把精确规则转换为最终逐槽 OCR 使用的标准舰名。"""
        return [
            normalize_ship_name(option.name) if option is not None else None for option in assigned
        ]

    @classmethod
    def _validate_assignment(
        cls,
        current: Sequence[str | None],
        occupied: Sequence[bool],
        assigned: Sequence[ShipSelector | None],
        verified_slots: set[int] | frozenset[int] = frozenset(),
    ) -> bool:
        """验证舰名、占用、位置、唯一性和 strict 选船记录。"""
        identities = [
            identity for name in current if (identity := ship_name_identity(name)) is not None
        ]
        if len(identities) != len(set(identities)):
            return False

        for slot, option in enumerate(assigned):
            if option is None:
                if occupied[slot] or current[slot] is not None:
                    return False
                continue
            if not occupied[slot] or not cls._option_matches_name(current[slot], option):
                return False
            if cls._requires_selection_validation(option) and slot not in verified_slots:
                return False
        return True

    def _mark_snapshot_verified_slots(
        self,
        snapshot: FleetSnapshot,
        assigned: Sequence[ShipSelector | None],
        verified_slots: set[int],
    ) -> None:
        """用首次快照标记已就位且满足规则的逻辑槽位，跳过选船二次确认。

        已确认无需更换的舰船不再进入点对点选船页更换，避免已就位舰船
        不在船池中导致选不到 → 重选 → 选不到的无限循环。
        最终舰队 check 仍由流程末尾的验证兜底。

        assigned 中既包含主选也包含备选；备选同样按自身约束参与校验，
        重规划改派备选后再次调用本函数即可覆盖备选链路。

        强校验 (strict): 名称匹配后，舰种/等级必须全部符合 YAML 规定才标记，
        任一约束因 OCR 数据缺失而无法确认时也不标记，落入选船页权威校验；
        弱校验 (relaxed): 规则本就不要求选船校验，由赋值匹配直接放行。
        """
        if snapshot.ship_types is None or snapshot.ship_levels is None:
            return
        for target_slot, option in enumerate(assigned):
            if option is None or not self._requires_selection_validation(option):
                continue
            if target_slot in verified_slots:
                continue
            # 位置无关匹配: 与 _assignment_locations 一致，先找已就位位置再校验。
            position = next(
                (
                    slot
                    for slot in range(6)
                    if snapshot.occupied[slot]
                    and self._option_matches_name(snapshot.names[slot], option)
                ),
                None,
            )
            if position is None:
                continue
            if not self._snapshot_satisfies_option(snapshot, position, option):
                _log.info(
                    '[准备页] 快照校验未通过: 逻辑槽位 {} ({}), 进入选船二次确认',
                    target_slot,
                    snapshot.names[position],
                )
                continue
            verified_slots.add(target_slot)
            _log.info(
                '[准备页] 快照确认逻辑槽位 {} 已就位 ({}), 跳过选船二次确认',
                target_slot,
                snapshot.names[position],
            )

    # 将当前舰队成员与目标槽位一对一匹配，找出可以直接保留的舰船。
    @classmethod
    def _match_existing_members(
        cls,
        current: list[str | None],
        desired: list[str | None],
        selectors: list[FleetSlotRule | None],
        verified_slots: set[int] | frozenset[int] = frozenset(),
    ) -> tuple[list[bool], set[int]]:
        """在当前舰队与目标槽位之间做一对一匹配。

        返回:
        - ok: 当前 6 个槽位中哪些槽位上的舰船可以保留
        - matched_slots: 哪些目标槽位已由当前舰队中的舰船满足
        """
        ok: list[bool] = [False] * 6
        # matched_slots 保存已经找到舰船的目标槽位。
        matched_slots: set[int] = set()
        # used_positions 防止同一艘当前舰船匹配多个目标槽位。
        used_positions: set[int] = set()

        # target_slots 只包含需要舰船的目标槽位。
        target_slots = [i for i, name in enumerate(desired) if name is not None]

        # 判断一艘当前舰船能否满足指定目标槽位。
        def matches(slot: int, ship: str | None) -> bool:
            selector = selectors[slot]
            option = cls._option_for_name(desired[slot], selector)
            return (
                ship_name_identity(ship) == ship_name_identity(desired[slot])
                and (option is None or cls._matches_search_name(ship, option.search_name))
                and (not cls._requires_selection_validation(option) or slot in verified_slots)
            )

        # 第一轮优先保留已经位于正确槽位的舰船。
        for i in target_slots:
            # 当前槽位已经符合目标时，将当前位置和目标槽位同时标记为已匹配。
            if matches(i, current[i]):
                ok[i] = True
                matched_slots.add(i)
                used_positions.add(i)

        # 第二轮在其他位置寻找目标舰船，后续再通过拖拽调整顺序。
        for i in target_slots:
            # 第一轮已经满足的目标槽位无需再次查找。
            if i in matched_slots:
                continue
            for j, ship in enumerate(current):
                # 已经匹配过的当前位置不能重复使用。
                if j in used_positions:
                    continue
                # 找到符合目标的舰船后，记录匹配并停止搜索本目标槽位。
                if matches(i, ship):
                    ok[j] = True
                    matched_slots.add(i)
                    used_positions.add(j)
                    break

        return ok, matched_slots

    @classmethod
    def _assignment_locations(
        cls,
        current: Sequence[str | None],
        occupied: Sequence[bool],
        assigned: Sequence[ShipSelector | None],
        verified_slots: set[int] | frozenset[int],
    ) -> tuple[set[int], set[int], dict[int, int]]:
        """定位当前成员对应的逻辑目标，并标记已满足目标。"""
        protected: set[int] = set()
        satisfied: set[int] = set()
        target_positions: dict[int, int] = {}

        for target_slot, option in enumerate(assigned):
            if option is None:
                continue
            positions = [target_slot, *[slot for slot in range(6) if slot != target_slot]]
            position = next(
                (
                    slot
                    for slot in positions
                    if slot not in protected
                    and occupied[slot]
                    and cls._option_matches_name(current[slot], option)
                ),
                None,
            )
            if position is None:
                continue
            protected.add(position)
            target_positions[target_slot] = position
            if not cls._requires_selection_validation(option) or target_slot in verified_slots:
                satisfied.add(target_slot)

        return protected, satisfied, target_positions

    @classmethod
    def _target_order(
        cls,
        assigned: Sequence[ShipSelector | None],
        selectors: Sequence[FleetSlotRule | None],
    ) -> list[int]:
        """主选目标优先，其余目标按逻辑槽位顺序处理。"""
        slots = [slot for slot, option in enumerate(assigned) if option is not None]
        return sorted(
            slots,
            key=lambda slot: (
                selectors[slot] is None
                or selectors[slot].primary is None
                or assigned[slot] != selectors[slot].primary,
                slot,
            ),
        )

    @classmethod
    def _replacement_slot(
        cls,
        current: Sequence[str | None],
        occupied: Sequence[bool],
        option: ShipSelector,
        protected: set[int],
        target_position: int | None,
        attempted: set[tuple[int, ShipSelector, int]],
        target_slot: int,
    ) -> int | None:
        """选择补船位置：原舰、空槽、多余舰、未知占用。"""
        if target_position is not None:
            key = (target_slot, option, target_position)
            return target_position if key not in attempted else None

        empty_slots = [slot for slot in range(6) if slot not in protected and not occupied[slot]]
        extra_slots = [
            slot
            for slot in range(6)
            if slot not in protected and occupied[slot] and current[slot] is not None
        ]
        normal_slots = [*empty_slots, *extra_slots]
        if normal_slots and not any(
            (target_slot, option, slot) in attempted for slot in normal_slots
        ):
            return normal_slots[0]

        return next(
            (
                slot
                for slot in range(6)
                if slot not in protected
                and occupied[slot]
                and current[slot] is None
                and (target_slot, option, slot) not in attempted
            ),
            None,
        )
