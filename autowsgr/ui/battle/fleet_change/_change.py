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
