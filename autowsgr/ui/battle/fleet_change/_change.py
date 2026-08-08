"""智能换船算法。

1. 保留所有可用主选，并为 candidate-only 槽位分配唯一备选。
2. 使用全部主选和备选作为全局 OCR 补救上下文。
3. 结合血条探针区分空槽和有舰船但舰名未识别的槽位。
4. OCR 当前舰队，candidate-only 优先复用未被主选占用的已有舰船。
5. 保留已有目标成员，优先补齐主选，再处理 fallback 和 candidate-only。
6. 主选失败后重新执行全局唯一分配，不能局部抢占其他主选。
7. 先替换目标舰船，再删除多余舰船，避免一队为空。
8. 删除多余舰船时在内存中同步槽位压缩，保留已确认的成员信息。
9. 成员集合完整后拖拽舰船，将现有成员调整到目标槽位。
10. OCR 再次验证舰名、顺序和空槽，漏识别时保留已确认的槽位舰名。
11. 验证失败后只修正错误槽位，最多修正两次。
一个 YAML 只执行一套舰队，不会切换其他 preset。
常规出征使用搜索框，决战可通过开关选择是否使用本算法。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from autowsgr.constants import ship_name_identity
from autowsgr.infra.logger import get_logger

from ._alignment import (
    FleetAlignmentMixin,
    _UnresolvedPrimaryError,
)
from ._detect import FleetSnapshot
from ._selection import _ShipSelection as _SelectionResult


_ShipSelection = _SelectionResult


# 仅在类型检查时导入 Sequence，运行时不产生额外依赖。
if TYPE_CHECKING:
    from collections.abc import Sequence

    from autowsgr.combat.fleet import FleetSlotRule, ShipSelector


# 记录智能换船过程中的关键步骤和失败原因。
_log = get_logger('ui.preparation')

# 首次完整对齐失败后，最多执行两次局部修正
_MAX_SET_RETRIES: int = 2


# 为普通出征和决战准备页提供同一套智能换船流程。
class FleetChangeMixin(FleetAlignmentMixin):
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

    @staticmethod
    def _merge_position_snapshot(
        current: Sequence[str | None],
        snapshot: FleetSnapshot,
    ) -> tuple[list[str | None], list[bool]]:
        """合并最终位置 OCR，并保留有船槽位中已经确认的舰名。"""
        names: list[str | None] = []
        for confirmed_name, detected_name, is_occupied in zip(
            current,
            snapshot.names,
            snapshot.occupied,
            strict=True,
        ):
            if not is_occupied:
                names.append(None)
            elif detected_name is not None:
                names.append(detected_name)
            else:
                names.append(confirmed_name)
        return names, list(snapshot.occupied)

    @classmethod
    def _snapshot_option_match_result(
        cls,
        snapshot: FleetSnapshot,
        slot: int,
        option: ShipSelector,
    ) -> str:
        """说明已匹配舰名的舰种、等级是否满足一条规则。"""
        if option.relaxed_constraints:
            result = '通过: relaxed仅校验舰名'
        else:
            ship_type = snapshot.ship_types[slot] if snapshot.ship_types else None
            ship_level = snapshot.ship_levels[slot] if snapshot.ship_levels else None
            if option.ship_types and ship_type is None:
                result = '不通过: 舰种未识别'
            elif option.ship_types and ship_type not in option.ship_types:
                result = f'不通过: 舰种{ship_type.value}不满足规则'
            elif (
                option.min_level is not None or option.max_level is not None
            ) and ship_level is None:
                result = '不通过: 等级未识别'
            elif option.min_level is not None and ship_level < option.min_level:
                result = f'不通过: 等级{ship_level}低于{option.min_level}'
            elif option.max_level is not None and ship_level > option.max_level:
                result = f'不通过: 等级{ship_level}高于{option.max_level}'
            else:
                result = '通过'
        return result

    @classmethod
    def _snapshot_slot_match_result(
        cls,
        snapshot: FleetSnapshot,
        slot: int,
        selector: FleetSlotRule | None,
    ) -> str:
        """说明一个 OCR 槽位与同位置 YAML 规则的匹配结果。"""
        name = snapshot.names[slot]
        occupied = snapshot.occupied[slot]
        if selector is None:
            result = '通过' if not occupied and name is None else '不通过: YAML要求空槽'
        elif not occupied:
            result = '不通过: 槽位为空'
        elif name is None:
            result = '不通过: 舰名未识别'
        else:
            option = next(
                (
                    candidate
                    for candidate in selector.options
                    if cls._option_matches_name(name, candidate)
                ),
                None,
            )
            result = (
                '不通过: 舰名不匹配'
                if option is None
                else cls._snapshot_option_match_result(snapshot, slot, option)
            )
        return result

    @classmethod
    def _log_snapshot_debug(
        cls,
        stage: str,
        snapshot: FleetSnapshot,
        selectors: Sequence[FleetSlotRule | None],
    ) -> None:
        """记录一轮 OCR 合并后的六槽结果、规则与匹配结论。"""
        ship_types = snapshot.ship_types or [None] * 6
        ship_levels = snapshot.ship_levels or [None] * 6
        for slot, selector in enumerate(selectors):
            ship_type = ship_types[slot]
            _log.debug(
                '[准备页] {} OCR后处理: 物理槽位={} occupied={} name={} type={} '
                'level={} rule={} match={}',
                stage,
                slot + 1,
                snapshot.occupied[slot],
                snapshot.names[slot],
                ship_type.value if ship_type is not None else None,
                ship_levels[slot],
                selector,
                cls._snapshot_slot_match_result(snapshot, slot, selector),
            )

    @classmethod
    def _assignment_failure_reason(
        cls,
        current: Sequence[str | None],
        occupied: Sequence[bool],
        assigned: Sequence[ShipSelector | None],
        verified_slots: set[int] | frozenset[int],
    ) -> str:
        """返回最终舰队未满足 YAML 的逐槽原因。"""
        reasons: list[str] = []
        identities = [
            identity for name in current if (identity := ship_name_identity(name)) is not None
        ]
        if len(identities) != len(set(identities)):
            reasons.append('舰队中存在同名舰船')

        for slot, option in enumerate(assigned):
            name = current[slot]
            if option is None:
                if occupied[slot] or name is not None:
                    reasons.append(f'槽位{slot + 1}应为空，实际为{name or "未知舰船"}')
                continue
            if not occupied[slot]:
                reasons.append(f"槽位{slot + 1}为空，目标为'{option.name}'")
            elif name is None:
                reasons.append(f"槽位{slot + 1}舰名未识别，目标为'{option.name}'")
            elif not cls._option_matches_name(name, option):
                reasons.append(
                    f"槽位{slot + 1}当前为'{name}'，目标为'{option.name}'",
                )
            elif cls._requires_selection_validation(option) and slot not in verified_slots:
                reasons.append(
                    f"槽位{slot + 1}的'{name}'未通过 strict 舰种或等级校验",
                )
        return '；'.join(reasons) or '最终校验未通过'

    @classmethod
    def _log_final_result(
        cls,
        current: Sequence[str | None],
        occupied: Sequence[bool],
        assigned: Sequence[ShipSelector | None],
        verified_slots: set[int] | frozenset[int],
        *,
        passed: bool,
    ) -> None:
        """统一输出最终编队和 YAML 校验结论。"""
        _log.info('[准备页] 最终编队: {}', list(current))
        if passed:
            _log.info('[准备页] YAML校验: 通过')
            return
        _log.error(
            '[准备页] YAML校验: 不通过，{}',
            cls._assignment_failure_reason(
                current,
                occupied,
                assigned,
                verified_slots,
            ),
        )

    def _detect_position_snapshot(
        self,
        current: Sequence[str | None],
        names: Sequence[str | None],
        *,
        stage: str,
        round_number: int,
    ) -> tuple[list[str | None], list[bool]]:
        """记录并执行一轮最终位置 OCR，合并已确认的舰名。"""
        _log.debug(
            '[准备页] {}OCR开始: 轮次={}/{}',
            stage,
            round_number,
            _MAX_SET_RETRIES + 1,
        )
        snapshot = self.detect_fleet_snapshot(expected_names=names)
        merged, occupied = self._merge_position_snapshot(current, snapshot)
        _log.debug(
            '[准备页] {}OCR后处理: 轮次={} current={} occupied={} target={}',
            stage,
            round_number,
            merged,
            occupied,
            names,
        )
        return merged, occupied

    def _prepare_members_for_reorder(
        self,
        attempt: int,
        current: list[str | None],
        occupied: list[bool],
        assigned: list[ShipSelector | None],
        selectors: list[FleetSlotRule | None],
        verified_slots: set[int],
        unavailable: set[tuple[int, ShipSelector]],
        locked: dict[int, ShipSelector],
        deferred_primary_slots: set[int],
    ) -> tuple[list[str | None], list[bool]]:
        """确保目标成员齐全，并保留已经确认的成员信息。"""
        if self._member_set_satisfied(
            current,
            occupied,
            assigned,
            verified_slots,
        ):
            _log.debug('[准备页] 目标成员已齐全, 直接调整舰船顺序')
            return current, occupied

        # 第一轮执行完整对齐，重试轮只处理错误槽位。
        if attempt == 0:
            self._full_align(
                current,
                occupied,
                assigned,
                selectors,
                verified_slots,
                unavailable,
                locked,
                deferred_primary_slots,
            )
        else:
            _log.debug('[准备页] 第 {} 次重试: 局部修正', attempt)
            self._local_fix(
                current,
                occupied,
                assigned,
                selectors,
                verified_slots,
                unavailable,
                locked,
            )

        return current, occupied

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
            _log.error('[准备页] YAML校验: 不通过，目标编队无法满足主选和同舰唯一约束')
            return False
        # 第一舰队最后一艘舰船不能移除，但第一舰队本身允许更换编成。
        if fleet_id == 1 and assigned[0] is None:
            raise ValueError('1 队槽位 0 不能为空')

        expected_pool = self._ocr_target_pool(selectors)
        snapshot = self._detect_initial_snapshot(expected_pool, selectors)
        current = snapshot.names
        occupied = snapshot.occupied
        _log.info('[准备页] 当前编队: {}', current)
        assigned = self._plan_target_options(
            selectors,
            current,
        )
        if assigned is None:
            _log.info('[准备页] 最终编队: {}', current)
            _log.error(
                '[准备页] YAML校验: 不通过，当前舰队无法分配为主选优先的不重名编成',
            )
            return False
        _log.info(
            '[准备页] YAML目标编队: {}',
            self._target_names(assigned),
        )

        # Step 4：首次完整调整，后续最多进行两次局部修正。
        # verified_slots 记录本轮已通过选船页 (或首次快照) 校验舰种和等级的逻辑目标槽位。
        verified_slots: set[int] = set()
        self._initial_snapshot = snapshot
        self._mark_snapshot_verified_slots(snapshot, assigned, verified_slots)
        initial_valid = self._validate_assignment(
            current,
            occupied,
            assigned,
            verified_slots,
        )
        _log.info(
            '[准备页] OCR校验: {}',
            '通过' if initial_valid else '不通过，进入换船流程',
        )
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
                self._log_final_result(
                    current,
                    occupied,
                    assigned,
                    verified_slots,
                    passed=True,
                )
                self._last_changed_fleet = list(current)
                return True

            # Step 5：成员齐全时直接排序，否则先执行完整或局部调整。
            try:
                current, occupied = self._prepare_members_for_reorder(
                    attempt,
                    current,
                    occupied,
                    assigned,
                    selectors,
                    verified_slots,
                    unavailable,
                    locked,
                    deferred_primary_slots,
                )
            except _UnresolvedPrimaryError as error:
                _log.error('[准备页] 换船失败: {}', error)
                self._log_final_result(
                    current,
                    occupied,
                    assigned,
                    verified_slots,
                    passed=False,
                )
                return False
            except RuntimeError as error:
                _log.error('[准备页] 换船失败: {}', error)
                self._log_final_result(
                    current,
                    occupied,
                    assigned,
                    verified_slots,
                    passed=False,
                )
                raise

            # Step 6：通过拖拽调整舰船顺序。
            names = self._target_names(assigned)
            self._reorder(current, names)

            # Step 7：最终 OCR 验证位置；有船但漏识别舰名时保留已确认信息。
            current, occupied = self._detect_position_snapshot(
                current,
                names,
                stage='最终位置',
                round_number=attempt + 1,
            )
            # 最终舰队符合目标时，返回成功。
            if self._validate_assignment(
                current,
                occupied,
                assigned,
                verified_slots,
            ):
                self._log_final_result(
                    current,
                    occupied,
                    assigned,
                    verified_slots,
                    passed=True,
                )
                self._last_changed_fleet = list(current)
                return True

            # 仍有重试次数时，等待页面稳定后进入下一轮局部修正。
            if attempt < _MAX_SET_RETRIES:
                _log.debug(
                    '[准备页] YAML校验第 {}/{} 次未通过，重新截图并局部修正',
                    attempt + 1,
                    _MAX_SET_RETRIES + 1,
                )
                time.sleep(0.5)
                current, occupied = self._detect_position_snapshot(
                    current,
                    names,
                    stage='局部修正前',
                    round_number=attempt + 2,
                )

            # 所有重试都失败时，记录当前舰队并退出。
            else:
                _log.error('[准备页] 换船失败: 已达到 {} 次尝试上限', _MAX_SET_RETRIES + 1)
                self._log_final_result(
                    current,
                    occupied,
                    assigned,
                    verified_slots,
                    passed=False,
                )

        return False

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
                _log.debug(
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
                _log.debug(
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
        _log.debug('[准备页] LEVEL1 开始: 全局识别舰名并检测槽位占用')
        snapshot = self.detect_fleet_snapshot(
            expected_pool=expected_pool,
        )
        self._log_snapshot_debug('LEVEL1', snapshot, selectors)

        _log.debug('[准备页] LEVEL2 开始: 新截图补识别舰名、舰种和等级')
        snapshot = self.fill_missing_fleet_snapshot(
            snapshot,
            expected_pool=expected_pool,
        )
        snapshot = self._retry_invalid_strict_details(
            snapshot,
            selectors,
            level='LEVEL2',
        )
        self._log_snapshot_debug('LEVEL2', snapshot, selectors)

        if snapshot.has_unknown_details:
            _log.debug(
                '[准备页] LEVEL3 开始: 舰名槽位={}, 舰种槽位={}, 等级槽位={}',
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
            self._log_snapshot_debug('LEVEL3', snapshot, selectors)
        else:
            _log.debug('[准备页] LEVEL3 跳过: LEVEL2 已取得全部字段')

        _log.debug(
            '[准备页] LEVEL4 开始: 最后补识别舰名槽位={}',
            snapshot.unknown_slots,
        )
        snapshot = self.fill_missing_fleet_snapshot(
            snapshot,
            expected_pool=expected_pool,
            detail_requirements=self._level4_detail_requirements(selectors),
        )
        self._log_snapshot_debug('LEVEL4', snapshot, selectors)
        return snapshot
