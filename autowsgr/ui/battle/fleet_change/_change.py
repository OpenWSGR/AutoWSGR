"""智能换船算法。

1. 保留所有可用主选，并为 candidate-only 槽位分配唯一备选。
2. 使用全部主选和备选作为全局 OCR 补救上下文。
3. 结合血条探针区分空槽和有舰船但舰名未识别的槽位。
4. OCR 当前舰队，candidate-only 优先复用未被主选占用的已有舰船。
5. 保留已有目标成员，优先补齐主选，再处理 fallback 和 candidate-only。
6. 主选失败后重新执行全局唯一分配，不能局部抢占其他主选。
7. 先替换目标舰船，再删除多余舰船，避免一队为空。
8. 删除舰船造成槽位压缩后，再检查并补齐缺员。
9. 成员集合完整后拖拽舰船，将现有成员调整到目标槽位。
10. OCR 再次验证舰名、顺序、空槽和同舰唯一性。
11. 验证失败后只修正错误槽位，最多修正两次。
一个 YAML 只执行一套舰队，不会切换其他 preset。
常规出征使用搜索框，决战可通过开关选择是否使用本算法。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from functools import cache
from typing import TYPE_CHECKING

from autowsgr.combat.fleet import FleetSlotRule, ShipSelector
from autowsgr.constants import normalize_ship_name, ship_name_identity
from autowsgr.infra.logger import get_logger
from autowsgr.ui.battle.constants import CLICK_BACK, CLICK_SHIP_SLOT

from ._detect import FleetDetectMixin, FleetSnapshot


# 仅在类型检查时导入 Sequence，运行时不产生额外依赖。
if TYPE_CHECKING:
    from collections.abc import Sequence

    from autowsgr.ui.choose_ship_page import ChooseShipPage


# 记录智能换船过程中的关键步骤和失败原因。
_log = get_logger('ui.preparation')

# 首次完整对齐失败后，最多执行两次局部修正
_MAX_SET_RETRIES: int = 2

# 等待选船页面出现的超时 (秒)
_CHOOSE_PAGE_TIMEOUT: float = 5.0


@dataclass(frozen=True, slots=True)
class _ShipSelection:
    """选船页实际命中的舰名和精确规则。"""

    name: str | None
    option: ShipSelector | None


class _UnresolvedPrimaryError(RuntimeError):
    """连续 OCR 后仍无法确认唯一主选时终止本次换船。"""


# 为普通出征和决战准备页提供同一套智能换船流程。
class FleetChangeMixin(FleetDetectMixin):
    """准备页换船逻辑。"""

    # True 使用搜索框选船，False 直接通过 OCR 列表选船。
    _use_search: bool = True
    _last_changed_fleet: list[str | None] | None = None
    # 首次快照 (含舰种/等级)，供重规划备选后重新标记已验证槽位。
    _initial_snapshot: FleetSnapshot | None = None

    @property
    def last_changed_fleet(self) -> list[str | None] | None:
        """返回最近一次换船成功时已验证的实际舰队。"""
        if self._last_changed_fleet is None:
            return None
        return list(self._last_changed_fleet)

    # 执行一套六槽舰队的完整换船、排序和验证流程。
    def change_fleet(
        self,
        fleet_id: int | None,
        ship_names: Sequence[FleetSlotRule],
    ) -> bool:
        """返回最终舰队是否符合六个目标槽位。"""
        self._last_changed_fleet = None
        # Step 1：切换到 YAML 指定的舰队。
        # 当前舰队已经正确时，不重复点击舰队按钮。
        if fleet_id and self.get_selected_fleet(self._ctrl.screenshot()) != fleet_id:
            self.select_fleet(fleet_id)
            time.sleep(0.5)

        # Step 2：保存六个槽位的规则，不足六槽时补空。
        selectors: list[FleetSlotRule | None] = list(ship_names[:6])
        selectors += [None] * (6 - len(selectors))

        # Step 3：主选全部保留，candidate-only 通过全局回溯分配唯一备选。
        assigned = self._plan_target_options(selectors)
        if assigned is None:
            _log.error('[准备页] 目标编成无法满足主选和同舰唯一约束')
            return False
        # 第一舰队最后一艘舰船不能移除，但第一舰队本身允许更换编成。
        if fleet_id == 1 and assigned[0] is None:
            raise ValueError('1 队槽位 0 不能为空')

        expected_pool = self._ocr_target_pool(selectors)
        snapshot = self._detect_initial_snapshot(expected_pool, selectors)
        current = snapshot.names
        occupied = snapshot.occupied
        assigned = self._plan_target_options(
            selectors,
            current,
        )
        if assigned is None:
            _log.error('[准备页] 当前舰队无法分配为主选优先的不重名编成')
            return False
        _log.info(
            '[准备页] 根据主选优先规则确定目标编成: {}',
            self._target_names(assigned),
        )

        # Step 4：首次完整调整，后续最多进行两次局部修正。
        # verified_slots 记录本轮已通过选船页 (或首次快照) 校验舰种和等级的逻辑目标槽位。
        verified_slots: set[int] = set()
        self._initial_snapshot = snapshot
        self._mark_snapshot_verified_slots(snapshot, assigned, verified_slots)
        deferred_primary_slots = self._deferred_primary_slots(
            snapshot,
            selectors,
            assigned,
        )
        unavailable: set[tuple[int, ShipSelector]] = set()
        locked: dict[int, ShipSelector] = {}
        for attempt in range(_MAX_SET_RETRIES + 1):
            names = self._target_names(assigned)
            # 当前舰队已经满足目标时，直接结束本次换船。
            if self._validate_assignment(
                current,
                occupied,
                assigned,
                verified_slots,
            ):
                _log.info('[准备页] 舰队已满足目标, 跳过换船')
                self._last_changed_fleet = list(current)
                return True

            # Step 5：第一轮执行完整对齐，重试轮只处理错误槽位。
            # 第一次调整需要补船、删船并处理槽位压缩。
            if attempt == 0:
                try:
                    self._full_align(
                        current,
                        occupied,
                        assigned,
                        selectors,
                        verified_slots,
                        unavailable,
                        locked,
                        expected_pool,
                        deferred_primary_slots,
                    )
                except _UnresolvedPrimaryError as error:
                    _log.error('[准备页] {}', error)
                    return False
            # 后续调整只修正 OCR 验证失败的槽位。
            else:
                _log.info('[准备页] 第 {} 次重试: 局部修正', attempt)
                self._local_fix(
                    current,
                    occupied,
                    assigned,
                    selectors,
                    verified_slots,
                    unavailable,
                    locked,
                    expected_pool,
                )

            # Step 6：重新识别成员，再通过拖拽调整舰船顺序。
            names = self._target_names(assigned)
            snapshot = self.detect_fleet_snapshot(expected_pool=expected_pool)
            current = snapshot.names
            occupied = snapshot.occupied
            self._reorder(current, names)

            # Step 7：最终 OCR 验证舰名、顺序、空槽和重名情况。
            snapshot = self.detect_fleet_snapshot(expected_names=names)
            current = snapshot.names
            occupied = snapshot.occupied
            # 最终舰队符合目标时，返回成功。
            if self._validate_assignment(
                current,
                occupied,
                assigned,
                verified_slots,
            ):
                _log.info('[准备页] 编成更换完成: {}', current)
                self._last_changed_fleet = list(current)
                return True

            # 仍有重试次数时，等待页面稳定后进入下一轮局部修正。
            if attempt < _MAX_SET_RETRIES:
                _log.warning(
                    '[准备页] 第 {}/{} 次验证失败, 重试...',
                    attempt + 1,
                    _MAX_SET_RETRIES + 1,
                )
                time.sleep(0.5)
                snapshot = self.detect_fleet_snapshot(expected_names=names)
                current = snapshot.names
                occupied = snapshot.occupied

            # 所有重试都失败时，记录当前舰队并退出。
            else:
                _log.error(
                    '[准备页] 舰队设置在 {} 次尝试后仍然失败, 当前: {}',
                    _MAX_SET_RETRIES + 1,
                    current,
                )

        return False

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

    @staticmethod
    def _level4_detail_requirements(
        selectors: Sequence[FleetSlotRule | None],
    ) -> dict[str, tuple[bool, bool]]:
        """返回 LEVEL4 需要继续补充舰种、等级的舰名。

        有主选的槽位只保留主选；识别为备选后必然进入换船，不再补充细节。
        纯备选槽没有主选，仍需按被选中的备选自身约束完成校验。
        """
        requirements: dict[str, tuple[bool, bool]] = {}
        for selector in selectors:
            if selector is None:
                continue
            options = (selector.primary,) if selector.primary is not None else selector.candidates
            for option in options:
                identity = ship_name_identity(option.name)
                if identity is None:
                    continue
                needs_type = bool(option.ship_types)
                needs_level = option.min_level is not None or option.max_level is not None
                previous = requirements.get(identity, (False, False))
                requirements[identity] = (
                    previous[0] or needs_type,
                    previous[1] or needs_level,
                )
        return requirements

    @staticmethod
    def _retry_invalid_strict_details(
        snapshot: FleetSnapshot,
        selectors: Sequence[FleetSlotRule | None],
        *,
        level: str,
    ) -> FleetSnapshot:
        """将不符合 strict YAML 的舰种、等级标记为未确认，留给下一阶段重识别。"""
        requirements: dict[str, list[ShipSelector]] = {}
        for selector in selectors:
            if selector is None:
                continue
            options = (selector.primary,) if selector.primary is not None else selector.candidates
            for option in options:
                if option.relaxed_constraints:
                    continue
                identity = ship_name_identity(option.name)
                if identity is not None:
                    requirements.setdefault(identity, []).append(option)

        ship_types = list(snapshot.ship_types or [None] * 6)
        ship_levels = list(snapshot.ship_levels or [None] * 6)
        changed = False
        for slot, name in enumerate(snapshot.names):
            options = requirements.get(ship_name_identity(name) or '')
            if not options:
                continue

            type_options = [option for option in options if option.ship_types]
            ship_type = ship_types[slot]
            if (
                ship_type is not None
                and type_options
                and not any(ship_type in option.ship_types for option in type_options)
            ):
                _log.info(
                    '[准备页] {} 槽位 {} 舰种 {} 不符合 strict YAML，下一阶段重识别',
                    level,
                    slot + 1,
                    ship_type,
                )
                ship_types[slot] = None
                changed = True

            level_options = [
                option
                for option in options
                if option.min_level is not None or option.max_level is not None
            ]
            ship_level = ship_levels[slot]
            if (
                ship_level is not None
                and level_options
                and not any(
                    (option.min_level is None or ship_level >= option.min_level)
                    and (option.max_level is None or ship_level <= option.max_level)
                    for option in level_options
                )
            ):
                _log.info(
                    '[准备页] {} 槽位 {} 等级 {} 不符合 strict YAML，下一阶段重识别',
                    level,
                    slot + 1,
                    ship_level,
                )
                ship_levels[slot] = None
                changed = True

        if not changed:
            return snapshot
        return FleetSnapshot(
            names=list(snapshot.names),
            occupied=list(snapshot.occupied),
            ship_types=ship_types,
            ship_levels=ship_levels,
        )

    def _detect_initial_snapshot(
        self,
        expected_pool: Sequence[str],
        selectors: Sequence[FleetSlotRule | None],
    ) -> FleetSnapshot:
        """通过四次独立截图累计舰队信息，只补仍未确认的字段。

        LEVEL1 全局识别舰名并检测血条；LEVEL2 使用新截图补舰名并首次识别
        全部有船槽位的舰种、等级；strict 约束不符的字段视为未确认；
        LEVEL3 再补充一次；LEVEL4 最后补舰名，并只补主选或纯备选规则实际
        需要的舰种、等级。
        """
        snapshot = self.detect_fleet_snapshot(
            expected_pool=expected_pool,
        )
        _log.info('[准备页] LEVEL1 完成: 舰名未知槽位={}', snapshot.unknown_slots)

        _log.info('[准备页] LEVEL2 使用新截图首次识别舰名、舰种和等级')
        snapshot = self.fill_missing_fleet_snapshot(
            snapshot,
            expected_pool=expected_pool,
        )
        snapshot = self._retry_invalid_strict_details(
            snapshot,
            selectors,
            level='LEVEL2',
        )

        if snapshot.has_unknown_details:
            _log.info(
                '[准备页] LEVEL3 执行一次补识别: 舰名槽位={}, 舰种槽位={}, 等级槽位={}',
                snapshot.unknown_slots,
                snapshot.unknown_type_slots,
                snapshot.unknown_level_slots,
            )
            snapshot = self.fill_missing_fleet_snapshot(
                snapshot,
                expected_pool=expected_pool,
            )
            snapshot = self._retry_invalid_strict_details(
                snapshot,
                selectors,
                level='LEVEL3',
            )

        _log.info(
            '[准备页] LEVEL4 最后补识别: 舰名槽位={}',
            snapshot.unknown_slots,
        )
        snapshot = self.fill_missing_fleet_snapshot(
            snapshot,
            expected_pool=expected_pool,
            detail_requirements=self._level4_detail_requirements(selectors),
        )
        return snapshot

    @classmethod
    def _option_matches_name(
        cls,
        current_name: str | None,
        option: ShipSelector,
    ) -> bool:
        """判断准备页舰名是否与一条精确规则属于同一舰船身份。"""
        return ship_name_identity(current_name) == ship_name_identity(
            option.name
        ) and cls._matches_search_name(current_name, option.search_name)

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

    # 按“已分配舰名优先、其余规则随后”的顺序生成本槽完整规则。
    @classmethod
    def _slot_options(
        cls,
        name: str | None,
        selector: FleetSlotRule | None,
    ) -> list[ShipSelector]:
        normalized_name = normalize_ship_name(name)
        if selector is None:
            return [ShipSelector(name=normalized_name)] if normalized_name else []

        options = list(selector.options)
        target_identity = ship_name_identity(normalized_name)
        options.sort(
            key=lambda option: ship_name_identity(option.name) != target_identity,
        )
        return options

    @classmethod
    def _slot_candidates(
        cls,
        name: str | None,
        selector: FleetSlotRule | None,
    ) -> list[str]:
        """返回本槽按尝试顺序排列的标准舰名。"""
        candidates: list[str] = []
        seen: set[str] = set()
        for option in cls._slot_options(name, selector):
            normalized = normalize_ship_name(option.name)
            identity = ship_name_identity(normalized)
            if normalized is not None and identity is not None and identity not in seen:
                candidates.append(normalized)
                seen.add(identity)
        return candidates

    @classmethod
    def _prefer_existing_targets(
        cls,
        names: list[str | None],
        selectors: list[FleetSlotRule | None],
        current: list[str | None],
    ) -> list[str | None]:
        """从每个槽位的候选集合中优先选择当前舰队已有成员。"""
        preferred = list(names)
        reused: set[str] = set()

        for slot, selector in enumerate(selectors):
            if selector is None or names[slot] is None:
                continue

            for option in selector.options:
                identity = ship_name_identity(option.name)
                if identity is None or identity in reused:
                    continue
                # strict 舰种/等级条件不能仅凭准备页舰名 OCR 判定满足。
                if cls._requires_selection_validation(option):
                    continue
                if not any(
                    ship_name_identity(ship) == identity
                    and cls._matches_search_name(ship, option.search_name)
                    for ship in current
                ):
                    continue

                preferred[slot] = normalize_ship_name(option.name)
                reused.add(identity)
                break

        return preferred

    # 为六个槽位挑选互不重复的目标舰名，冲突时自动尝试备选。
    @classmethod
    def _assign_unique_targets(
        cls,
        names: list[str | None],
        selectors: list[FleetSlotRule | None],
    ) -> list[str | None] | None:
        """为每个非空槽位分配唯一舰名，候选重叠时按优先级回溯。"""
        # options 保存六个槽位各自按优先级排列的候选舰名。
        options = [
            cls._slot_candidates(names[i], selectors[i]) if names[i] is not None else []
            for i in range(6)
        ]
        # assigned 保存回溯算法当前得到的六槽分配结果。
        assigned: list[str | None] = [None] * 6

        # 从左到右递归分配槽位，后续无解时回退并尝试当前槽位的下一个候选。
        def assign(slot: int, used: set[str]) -> bool:
            if slot >= 6:
                return True
            if names[slot] is None:
                return assign(slot + 1, used)
            for candidate in options[slot]:
                identity = ship_name_identity(candidate)
                if identity is None or identity in used:
                    continue
                assigned[slot] = candidate
                used.add(identity)
                if assign(slot + 1, used):
                    return True
                used.remove(identity)
                assigned[slot] = None
            return False

        return assigned if assign(0, set()) else None

    # 判断当前标准舰名是否符合 selector 指定的搜索名称。
    @classmethod
    def _matches_search_name(cls, current_name: str | None, raw_search_name: str | None) -> bool:
        if current_name is None:
            return False
        if raw_search_name is None:
            return True
        if not raw_search_name.strip():
            return True

        search_name = raw_search_name.strip()
        # 当前舰名与搜索名完全相同时直接通过。
        if current_name == search_name:
            return True

        return ship_name_identity(current_name) == ship_name_identity(search_name)

    @classmethod
    def _option_for_name(
        cls,
        name: str | None,
        selector: FleetSlotRule | None,
    ) -> ShipSelector | None:
        """返回与实际舰名对应的独立规则。"""
        identity = ship_name_identity(name)
        return next(
            (
                option
                for option in cls._slot_options(name, selector)
                if ship_name_identity(option.name) == identity
            ),
            None,
        )

    @staticmethod
    def _requires_selection_validation(option: ShipSelector | None) -> bool:
        """返回规则是否必须通过选船页校验舰种或等级。"""
        return bool(
            option is not None
            and not option.relaxed_constraints
            and (option.ship_types or option.min_level is not None or option.max_level is not None)
        )

    @classmethod
    def _snapshot_satisfies_option(
        cls,
        snapshot: FleetSnapshot,
        slot: int,
        option: ShipSelector,
    ) -> bool:
        """强校验: 首次快照是否已从舰种/等级确认该槽位满足规则。

        名称匹配由调用方保证；这里只做约束校验。relaxed (弱校验) 规则
        不要求选船校验，无需调用本函数，名称匹配即视为放行。
        """
        ship_type = snapshot.ship_types[slot] if snapshot.ship_types else None
        ship_level = snapshot.ship_levels[slot] if snapshot.ship_levels else None

        if option.ship_types and ship_type not in option.ship_types:
            return False
        if option.min_level is not None or option.max_level is not None:
            if ship_level is None:
                return False
            if option.min_level is not None and ship_level < option.min_level:
                return False
            if option.max_level is not None and ship_level > option.max_level:
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

    # 从本槽候选中排除队内同名舰，并返回实际可用于选船的规则。
    @classmethod
    def _select_available_candidate(
        cls,
        current: list[str | None],
        name: str | None,
        selector: FleetSlotRule | None,
        *,
        slot_to_replace: int | None = None,
    ) -> tuple[str | None, tuple[ShipSelector, ...] | None]:
        """返回第一个未被其他槽位占用的候选舰名。"""
        # 目标舰名为空时，本槽不需要选船。
        if name is None:
            return None, None

        # options 是本槽位按优先级排列的完整选船规则。
        options = cls._slot_options(name, selector)
        # occupied 保存队内其他槽位已经占用的舰船组身份。
        occupied = {
            ship_name_identity(ship)
            for idx, ship in enumerate(current)
            if ship is not None and idx != slot_to_replace
        }
        # available 保留当前舰队中尚未占用的完整规则。
        available = [
            option for option in options if ship_name_identity(option.name) not in occupied
        ]

        if len(available) == 0:
            return None, None

        chosen = normalize_ship_name(available[0].name)
        # 选船页面按顺序尝试未占用规则，各备选使用自己的约束。
        return chosen, tuple(available)

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

    # 判断一个当前槽位是否满足对应的目标舰名和搜索规则。
    @classmethod
    def _slot_matches(
        cls,
        current_name: str | None,
        target: str | None,
        selector: FleetSlotRule | None,
        *,
        selection_verified: bool = False,
    ) -> bool:
        # 目标为空时，只有当前槽也为空才算匹配。
        if target is None:
            return current_name is None
        if selector is None:
            return ship_name_identity(current_name) == ship_name_identity(target)
        option = cls._option_for_name(current_name, selector)
        if option is None:
            return False
        if cls._requires_selection_validation(option) and not selection_verified:
            return False
        return cls._matches_search_name(
            current_name,
            option.search_name,
        )

    # 验证当前六个槽位是否完整满足目标，并拒绝队内同名舰。
    @classmethod
    def _validate_with_selector(
        cls,
        current: list[str | None],
        desired: list[str | None],
        selectors: list[FleetSlotRule | None],
        verified_slots: set[int] | frozenset[int] = frozenset(),
    ) -> bool:
        members = [ship_name_identity(name) for name in current if name is not None]
        if len(members) != len(set(members)):
            return False

        return all(
            cls._slot_matches(
                current[i],
                desired[i],
                selectors[i],
                selection_verified=i in verified_slots,
            )
            for i in range(6)
        )

    # 找出当前舰队中需要替换、补充或移除的槽位。
    @classmethod
    def _find_wrong_slots(
        cls,
        current: list[str | None],
        names: list[str | None],
        selectors: list[FleetSlotRule | None],
        verified_slots: set[int] | frozenset[int] = frozenset(),
    ) -> list[int]:
        """返回所有不符合目标规则的槽位下标。"""
        return [
            i
            for i in range(6)
            if not cls._slot_matches(
                current[i],
                names[i],
                selectors[i],
                selection_verified=i in verified_slots,
            )
        ]

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
