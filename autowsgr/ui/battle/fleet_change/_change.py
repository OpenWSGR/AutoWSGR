"""智能换船算法。

1. 读取 YAML 传入的前六个舰队槽位。
2. 整理每个槽位的优选、备选和筛选条件。
3. 使用回溯算法为六个槽位分配不同舰名。
4. OCR 识别当前舰队，已经正确时直接结束。
5. 首次调整时保留可复用舰船并补齐缺少舰船。
6. 先替换目标舰船，再删除多余舰船，避免一队为空。
7. 删除舰船造成槽位压缩后，再检查并补齐缺员。
8. 拖拽舰船，将现有成员调整到目标槽位。
9. OCR 再次验证舰名、顺序和空槽。
10. 验证失败后只修正错误槽位，最多修正两次。
一个 YAML 只执行一套舰队，不会切换其他 preset。
常规出征使用搜索框，决战可通过开关选择是否使用本算法。
"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

from autowsgr.combat.fleet import FleetSlotRule, ShipSelector
from autowsgr.constants import ship_name_identity
from autowsgr.infra.logger import get_logger
from autowsgr.ui.battle.constants import CLICK_SHIP_SLOT

from ._detect import FleetDetectMixin


# 仅在类型检查时导入 Sequence，运行时不产生额外依赖。
if TYPE_CHECKING:
    from collections.abc import Sequence


# 记录智能换船过程中的关键步骤和失败原因。
_log = get_logger('ui.preparation')

# 首次完整对齐失败后，最多执行两次局部修正
_MAX_SET_RETRIES: int = 2

# 等待选船页面出现的超时 (秒)
_CHOOSE_PAGE_TIMEOUT: float = 5.0

# 舰名尾部别名后缀，如“(苍青幻影)”
_SHIP_ALIAS_SUFFIX_RE = re.compile(r'\s*[（(][^（）()]*[)）]\s*$')


# 为普通出征和决战准备页提供同一套智能换船流程。
class FleetChangeMixin(FleetDetectMixin):
    """准备页换船逻辑。"""

    # True 使用搜索框选船，False 直接通过 OCR 列表选船。
    _use_search: bool = True

    # 执行一套六槽舰队的完整换船、排序和验证流程。
    def change_fleet(
        self,
        fleet_id: int | None,
        ship_names: Sequence[FleetSlotRule],
    ) -> bool:
        """返回最终舰队是否符合六个目标槽位。"""
        # Step 1：切换到 YAML 指定的舰队。
        # 当前舰队已经正确时，不重复点击舰队按钮。
        if fleet_id and self.get_selected_fleet(self._ctrl.screenshot()) != fleet_id:
            self.select_fleet(fleet_id)
            time.sleep(0.5)

        # Step 2：分别保存六个槽位的目标舰名和选船规则。
        names: list[str | None] = []
        selectors: list[FleetSlotRule | None] = []
        for slot_rule in list(ship_names)[:6]:
            selectors.append(slot_rule)
            names.append(self._normalize_ship_name(slot_rule.preferred_name))

        # Step 3：不足六槽时补空，并为所有槽位分配互不重复的舰名。
        names += [None] * (6 - len(names))
        selectors += [None] * (6 - len(selectors))
        # unique_names 是处理候选冲突后的最终目标舰名。
        unique_names = self._assign_unique_targets(names, selectors)
        # 无法找到不重名组合时，停止换船，避免组成非法舰队。
        if unique_names is None:
            _log.error('[准备页] 目标编成无法满足同名舰唯一约束: {}', names)
            return False
        names = unique_names
        # 第一舰队最后一艘舰船不能移除，但第一舰队本身允许更换编成。
        if fleet_id == 1 and names[0] is None:
            raise ValueError('1 队槽位 0 不能为空')
        _log.info('[准备页] 目标编成: {}', names)

        # Step 4：首次完整调整，后续最多进行两次局部修正。
        for attempt in range(_MAX_SET_RETRIES + 1):
            # current 保存本轮开始时 OCR 识别到的六个槽位。
            current = self.detect_fleet()

            # 当前舰队已经满足目标时，直接结束本次换船。
            if self._validate_with_selector(current, names, selectors):
                _log.info('[准备页] 舰队已满足目标, 跳过换船')
                return True

            # Step 5：第一轮执行完整对齐，重试轮只处理错误槽位。
            # 第一次调整需要补船、删船并处理槽位压缩。
            if attempt == 0:
                self._full_align(current, names, selectors)
            # 后续调整只修正 OCR 验证失败的槽位。
            else:
                _log.info('[准备页] 第 {} 次重试: 局部修正', attempt)
                self._local_fix(current, names, selectors)

            # Step 6：重新识别成员，再通过拖拽调整舰船顺序。
            current = self.detect_fleet(expected_names=names)
            self._reorder(current, names)

            # Step 7：最终 OCR 验证舰名、顺序、空槽和重名情况。
            current = self.detect_fleet(expected_names=names)
            # 最终舰队符合目标时，返回成功。
            if self._validate_with_selector(current, names, selectors):
                _log.info('[准备页] 编成更换完成: {}', current)
                return True

            # 仍有重试次数时，等待页面稳定后进入下一轮局部修正。
            if attempt < _MAX_SET_RETRIES:
                _log.warning(
                    '[准备页] 第 {}/{} 次验证失败, 重试...',
                    attempt + 1,
                    _MAX_SET_RETRIES + 1,
                )
                time.sleep(0.5)

            # 所有重试都失败时，记录当前舰队并退出。
            else:
                _log.error(
                    '[准备页] 舰队设置在 {} 次尝试后仍然失败, 当前: {}',
                    _MAX_SET_RETRIES + 1,
                    current,
                )

        return False

    # 清理 OCR、YAML 和选船结果中的明确后缀，保留用户自定义舰名。
    @staticmethod
    def _normalize_ship_name(value: object) -> str | None:
        if value is None:
            return None

        # normalized 依次去掉空格、“·改”和尾部括号别名。
        normalized = str(value).strip()
        normalized = normalized.removesuffix('·改')
        normalized = _SHIP_ALIAS_SUFFIX_RE.sub('', normalized)
        normalized = normalized.strip()
        return normalized or None

    # 将同一 No.xxx 舰船组中的标准名和用户自定义名统一为同一身份。
    @classmethod
    def _ship_identity(cls, value: object) -> str | None:
        normalized = cls._normalize_ship_name(value)
        return ship_name_identity(normalized) if normalized is not None else None

    # 按“已分配舰名优先、其余规则随后”的顺序生成本槽完整规则。
    @classmethod
    def _slot_options(
        cls,
        name: str | None,
        selector: FleetSlotRule | None,
    ) -> list[ShipSelector]:
        normalized_name = cls._normalize_ship_name(name)
        if selector is None:
            return [ShipSelector(name=normalized_name)] if normalized_name else []

        options = list(selector.options)
        target_identity = cls._ship_identity(normalized_name)
        options.sort(
            key=lambda option: cls._ship_identity(option.name) != target_identity,
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
            normalized = cls._normalize_ship_name(option.name)
            identity = cls._ship_identity(normalized)
            if normalized is not None and identity is not None and identity not in seen:
                candidates.append(normalized)
                seen.add(identity)
        return candidates

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
                identity = cls._ship_identity(candidate)
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

        return cls._ship_identity(current_name) == cls._ship_identity(search_name)

    @classmethod
    def _option_for_name(
        cls,
        name: str | None,
        selector: FleetSlotRule | None,
    ) -> ShipSelector | None:
        """返回与实际舰名对应的独立规则。"""
        identity = cls._ship_identity(name)
        return next(
            (
                option
                for option in cls._slot_options(name, selector)
                if cls._ship_identity(option.name) == identity
            ),
            None,
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
            cls._ship_identity(ship)
            for idx, ship in enumerate(current)
            if ship is not None and idx != slot_to_replace
        }
        # available 保留当前舰队中尚未占用的完整规则。
        available = [
            option for option in options if cls._ship_identity(option.name) not in occupied
        ]

        if len(available) == 0:
            return None, None

        chosen = cls._normalize_ship_name(available[0].name)
        # 选船页面按顺序尝试未占用规则，各备选使用自己的约束。
        return chosen, tuple(available)

    # 将当前舰队成员与目标槽位一对一匹配，找出可以直接保留的舰船。
    @classmethod
    def _match_existing_members(
        cls,
        current: list[str | None],
        desired: list[str | None],
        selectors: list[FleetSlotRule | None],
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
            return cls._ship_identity(ship) == cls._ship_identity(desired[slot]) and (
                option is None or cls._matches_search_name(ship, option.search_name)
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
    ) -> bool:
        # 目标为空时，只有当前槽也为空才算匹配。
        if target is None:
            return current_name is None
        if selector is None:
            return cls._ship_identity(current_name) == cls._ship_identity(target)
        option = cls._option_for_name(current_name, selector)
        if option is None:
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
    ) -> bool:
        members = [cls._ship_identity(name) for name in current if name is not None]
        if len(members) != len(set(members)):
            return False

        return all(cls._slot_matches(current[i], desired[i], selectors[i]) for i in range(6))

    # 找出当前舰队中需要替换、补充或移除的槽位。
    @classmethod
    def _find_wrong_slots(
        cls,
        current: list[str | None],
        names: list[str | None],
        selectors: list[FleetSlotRule | None],
    ) -> list[int]:
        """返回所有不符合目标规则的槽位下标。"""
        return [i for i in range(6) if not cls._slot_matches(current[i], names[i], selectors[i])]

    # 为一个目标槽位选择舰船，并同步更新当前舰队和目标舰名。
    def _replace_target(
        self,
        current: list[str | None],
        names: list[str | None],
        selectors: list[FleetSlotRule | None],
        target_slot: int,
        ship_slot: int | None = None,
    ) -> None:
        """选择目标舰船，并更新当前舰队和目标舰名。"""
        target = names[target_slot]
        assert target is not None
        slot = target_slot if ship_slot is None else ship_slot
        selected_name, selected_selector = self._select_available_candidate(
            current,
            target,
            selectors[target_slot],
            slot_to_replace=slot,
        )
        # 本槽所有候选都被占用时，无法组成目标舰队。
        if selected_name is None:
            raise RuntimeError(f'目标槽位 {target_slot} 没有未被占用的候选舰船')

        _log.info(
            "[准备页] 更换槽位 {} <- '{}' (原: '{}')",
            slot,
            selected_name,
            current[slot],
        )
        selected = self._change_single_ship(
            slot,
            selected_name,
            selector=selected_selector,
            slot_occupied=current[slot] is not None,
        )
        actual = selected if selected is not None else selected_name
        current[slot] = actual
        names[target_slot] = actual
        time.sleep(0.3)

    # 首次调整时完成成员复用、缺员补充、多余成员移除和压缩后补位。
    def _full_align(
        self,
        current: list[str | None],
        names: list[str | None],
        selectors: list[FleetSlotRule | None],
    ) -> None:
        """首次将当前成员调整成目标成员集合。"""
        # ok 标记当前可保留位置，matched_slots 标记已满足的目标槽位。
        ok, matched_slots = self._match_existing_members(current, names, selectors)

        # Step 1：把尚未满足的目标舰船放入可替换槽位。
        for i, name in enumerate(names):
            if name is None:
                continue
            if i in matched_slots:
                continue
            # slot 是当前舰队中第一个不能保留、可以用于替换的位置。
            slot = next((idx for idx in range(6) if not ok[idx]), None)
            if slot is None:
                raise RuntimeError(f"无可用槽位放置目标舰船 '{name}'")
            self._replace_target(current, names, selectors, i, slot)
            ok[slot] = True
            matched_slots.add(i)

        # Step 2：从后往前移除剩余多余舰船，减少槽位压缩影响。
        for i in range(5, -1, -1):
            # 当前位置不能保留且仍有舰船时，将该舰船移除。
            if not ok[i] and current[i] is not None:
                _log.info("[准备页] 移除槽位 {} 的 '{}'", i, current[i])
                self._change_single_ship(i, None, slot_occupied=True)
                current[i] = None
                time.sleep(0.3)

        # Step 3：重新 OCR，检查删除舰船造成的槽位压缩和缺员。
        current[:] = self.detect_fleet(expected_names=names)
        target_count = sum(1 for v in names if v is not None)
        current_count = sum(1 for v in current if v is not None)
        # 实际舰船少于目标数量时，逐槽补齐缺少成员。
        if current_count < target_count:
            for i, name in enumerate(names):
                if name is None:
                    continue
                if current[i] is not None:
                    continue
                self._replace_target(current, names, selectors, i)

                current_count = sum(1 for v in current if v is not None)
                if current_count >= target_count:
                    break

    # OCR 验证失败后，只替换或移除不符合目标的槽位。
    def _local_fix(
        self,
        current: list[str | None],
        names: list[str | None],
        selectors: list[FleetSlotRule | None],
    ) -> None:
        """只修正本轮识别出的错误槽位。"""
        # wrong 保存所有需要替换、补充或移除的槽位。
        wrong = self._find_wrong_slots(current, names, selectors)
        if not wrong:
            return

        _log.info('[准备页] 局部修正: 错误槽位 {}', wrong)

        # 先完成替换/补员，再移除多余舰船。1 队只剩最后一艘时，
        # 这能保证槽位 0 直接替换，不会先进入空队状态。
        replacement_slots = [i for i in wrong if names[i] is not None]
        removal_slots = [i for i in wrong if names[i] is None]

        # Step 1：先替换和补船，避免一队在移除时变成空队。
        for i in replacement_slots:
            self._replace_target(current, names, selectors, i)

        # Step 2：再从后往前移除目标为空的多余舰船。
        for i in reversed(removal_slots):
            # 当前槽位已经为空时，不重复进入选船页面。
            if current[i] is None:
                continue
            _log.info("[准备页] 局部修正: 移除槽位 {} 的 '{}'", i, current[i])
            self._change_single_ship(i, None, slot_occupied=True)
            current[i] = None
            time.sleep(0.3)

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
            target_identity = self._ship_identity(target)
            if self._ship_identity(current[i]) == target_identity:
                continue
            try:
                src = next(
                    idx
                    for idx, current_name in enumerate(current)
                    if self._ship_identity(current_name) == target_identity
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
        from autowsgr.ui.choose_ship_page import ChooseShipPage
        from autowsgr.ui.utils import wait_for_page

        # 目标为空且当前槽位也为空时，不需要打开选船页面。
        if name is None and not slot_occupied:
            return None

        # 点击目标槽位并等待选船页面加载完成。
        self.click_ship_slot(slot)
        wait_for_page(
            self._ctrl,
            ChooseShipPage.is_current_page,
            timeout=_CHOOSE_PAGE_TIMEOUT,
            source='编队',
            target='编队选船',
        )
        # FleetChange 决定候选顺序，页面每次只执行一条明确规则。
        choose_page = ChooseShipPage(self._ctx)
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
        _log.error('[准备页] 未在选船列表中找到满足规则的候选: {}', candidates)
        raise RuntimeError(f'未找到满足条件的目标舰船: {candidates}')
