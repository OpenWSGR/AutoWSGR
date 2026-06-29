"""舰队编成更换 -- 更换算法。

实现 "扫描 -> 定点更换 -> 调整次序" 的统一换船流程,
对齐 legacy ``Fleet._set_ships`` / ``Fleet.reorder`` 算法。

常规出征与决战共用此 Mixin, 通过实例属性 ``_use_search``
控制选船页面是否使用搜索框:

- ``True`` (默认): 常规出征, 使用搜索框输入舰船名
- ``False``: 决战模式, 直接 OCR 列表点击
"""

from __future__ import annotations

import re
import time
from collections import Counter
from typing import TYPE_CHECKING, TypedDict

from autowsgr.infra.logger import get_logger
from autowsgr.ui.battle.constants import CLICK_SHIP_SLOT

from ._detect import FleetDetectMixin


if TYPE_CHECKING:
    from collections.abc import Sequence


_log = get_logger('ui.preparation')

# change_fleet 最大重试次数 (对齐 legacy Fleet.set_ship 的 max_retries=2)
_MAX_SET_RETRIES: int = 2

# 等待选船页面出现的超时 (秒)
_CHOOSE_PAGE_TIMEOUT: float = 5.0

# 清空编队的最大尝试次数 (防止无限循环)
_MAX_CLEAR_ATTEMPTS: int = 12

# 舰名尾部别名后缀，如“(苍青幻影)”
_SHIP_ALIAS_SUFFIX_RE = re.compile(r'\s*[（(][^（）()]*[)）]\s*$')


class FleetSlotSelector(TypedDict, total=False):
    """编队槽位规则。"""

    candidates: list[str]
    search_name: str
    ship_type: str
    min_level: int
    max_level: int


FleetSlotInput = str | FleetSlotSelector | None


class FleetChangeMixin(FleetDetectMixin):
    """舰队编成更换 Mixin。

    实例属性 ``_use_search`` 控制选船页面是否使用搜索框:

    - ``True`` (默认): 常规出征, 使用搜索框输入舰船名
    - ``False``: 决战模式, 直接 OCR 列表点击

    依赖 :class:`~autowsgr.ui.battle.base.BaseBattlePreparation` 提供的
    ``_ctx``, ``_ctrl``, ``_ocr``, ``click_ship_slot``,
    ``get_selected_fleet``, ``select_fleet``,
    以及 :class:`._detect.FleetDetectMixin` 提供的
    ``detect_fleet``, ``_validate_fleet``。
    """

    _use_search: bool = True

    # ══════════════════════════════════════════════════════════════════════
    # 主入口
    # ══════════════════════════════════════════════════════════════════════

    def change_fleet(  # noqa: C901, PLR0912, PLR0915
        self,
        fleet_id: int | None,
        ship_names: Sequence[FleetSlotInput],
    ) -> bool:
        """更换编队全部舰船 -- 扫描 -> 定点更换 -> 调整次序。

        **三步算法** (对齐 legacy ``Fleet._set_ships`` + ``Fleet.reorder``):

        1. **扫描**: OCR 识别当前舰队, 前置短路判断是否已满足目标。
        2. **成员对齐** (``_set_ships``): 标记 ok/not-ok, 定点替换缺失舰船,
           从后往前移除多余舰船。
        3. **位置对齐** (``_reorder``): 通过滑动拖拽将每艘船移到正确槽位。

        失败时自动重试 (最多 ``_MAX_SET_RETRIES`` 次)。

        Parameters
        ----------
        fleet_id:
            舰队编号 (2-4); ``None`` 代表不指定舰队。1 队不支持更换。
        ship_names:
            目标槽位列表 (按槽位 0-5 顺序); 每个元素可为:

            - ``str``: 目标舰船名
            - ``dict``: 规则对象 (``candidates`` / ``search_name`` /
              ``ship_type`` / ``min_level`` / ``max_level``)
            - ``None``: 留空

            另外也兼容具备同名属性的 selector-like 对象。

        Returns
        -------
        bool
            ``True`` 表示最终验证通过, ``False`` 表示全部重试失败。
        """
        if fleet_id == 1:
            raise ValueError('不支持更换 1 队舰船编成')

        if fleet_id and self.get_selected_fleet(self._ctrl.screenshot()) != fleet_id:
            self.select_fleet(fleet_id)
            time.sleep(0.5)

        names: list[str | None] = []
        selectors: list[dict | None] = []
        for raw_slot in list(ship_names)[:6]:
            selector = self._extract_selector(raw_slot)
            selectors.append(selector)
            if isinstance(raw_slot, str):
                names.append(self._normalize_ship_name(raw_slot))
            elif selector is not None:
                candidates = selector.get('candidates', [])
                if isinstance(candidates, list) and len(candidates) > 0:
                    names.append(self._normalize_ship_name(candidates[0]))
                else:
                    names.append(None)
            else:
                names.append(None)

        names += [None] * (6 - len(names))
        selectors += [None] * (6 - len(selectors))
        _log.info('[准备页] 目标编成: {}', names)

        # ── 1. # ── 解析目标 ─────────────────────────────────────────────
        target_count = sum(1 for n in names if n is not None)
        _log.info('[准备页] 目标编成: {} (需 {} 艘船)', names, target_count)

        # ── 循环扫描→修复→重扫 ───────────────────────────
        max_rounds = target_count * 3
        for _round in range(max_rounds):
            current = self.detect_fleet()

            # 扫描所有槽位，收集错误
            errors: list[tuple[str, int]] = []
            used: set[str] = set()
            for i in range(target_count):
                ship = current[i]
                if ship is not None and self._ship_matches_slot(ship, names[i], selectors[i]) and ship not in used:
                    used.add(ship)
                else:
                    errors.append(("wrong", i))
            for i in range(target_count, 6):
                if current[i] is not None:
                    errors.append(("extra", i))

            if not errors:
                _log.info('[准备页] 编成更换完成: {}', current)
                return True

            kind, slot = errors[0]
            _log.info('[准备页] 扫描发现 {} 个错误, 修复: {} 槽位 {}', len(errors), kind, slot)

            if kind == 'extra':
                self._change_single_ship(slot, None, slot_occupied=True)
                continue

            # wrong: 先尝试与后面槽位互换
            tgt = names[slot]
            sel = selectors[slot]
            sw = None
            for j in range(slot + 1, 6):
                if current[j] is not None and self._ship_matches_slot(current[j], tgt, sel) and not any(current[j] == current[k] for k in range(slot)):
                    sw = j; break

            if sw is not None:
                _log.info('[准备页] 互换: 槽位 {} ↔ {}', slot, sw)
                self._ctrl.swipe(*CLICK_SHIP_SLOT[sw], *CLICK_SHIP_SLOT[slot], duration=0.5)
            else:
                # 踢掉已被前面槽位占用的候选，避免重复选同一艘
                usable = list(sel.get('candidates', [tgt])) if sel else [tgt]
                skip = set(current[k] for k in range(slot) if current[k] is not None)
                pick = next((c for c in usable if c not in skip), tgt)
                _log.info('[准备页] 更换: 槽位 {} → {} (跳过: {})', slot, pick, skip or '无')
                pick_sel = dict(sel) if sel else {}
                pick_sel['search_name'] = pick
                self._change_single_ship(slot, pick, selector=pick_sel, slot_occupied=current[slot] is not None)

        _log.error('[准备页] 舰队设置超过最大循环次数')
        return False

    @staticmethod
    def _normalize_ship_name(value: object) -> str | None:
        if value is None:
            return None
        name = str(value).strip()
        return name or None

    @staticmethod
    def _extract_selector(slot: object | None) -> dict | None:
        if slot is None or isinstance(slot, str):
            return None

        raw_candidates = None
        raw_search_name = None
        raw_ship_type = None
        raw_min = None
        raw_max = None

        if isinstance(slot, dict):
            raw_candidates = slot.get('candidates')
            raw_search_name = slot.get('search_name')
            raw_ship_type = slot.get('ship_type')
            raw_min = slot.get('min_level')
            raw_max = slot.get('max_level')
        else:
            raw_candidates = getattr(slot, 'candidates', None)
            raw_search_name = getattr(slot, 'search_name', None)
            raw_ship_type = getattr(slot, 'ship_type', None)
            raw_min = getattr(slot, 'min_level', None)
            raw_max = getattr(slot, 'max_level', None)

        if not isinstance(raw_candidates, list):
            return None

        candidates = [str(v).strip() for v in raw_candidates if str(v).strip()]
        if len(candidates) == 0:
            return None

        selector: dict[str, object] = {'candidates': candidates}
        if isinstance(raw_search_name, str) and raw_search_name.strip():
            selector['search_name'] = raw_search_name.strip()
        if isinstance(raw_ship_type, str) and raw_ship_type.strip():
            selector['ship_type'] = raw_ship_type.strip().lower()
        if isinstance(raw_min, int) and raw_min > 0:
            selector['min_level'] = raw_min
        if isinstance(raw_max, int) and raw_max > 0:
            selector['max_level'] = raw_max
        return selector

    @classmethod
    def _slot_candidates(cls, name: str | None, selector: dict | None) -> list[str]:
        out: list[str] = []
        if selector is not None:
            raw = selector.get('candidates')
            if isinstance(raw, list):
                for value in raw:
                    normalized = cls._normalize_ship_name(value)
                    if normalized and normalized not in out:
                        out.append(normalized)
        normalized_name = cls._normalize_ship_name(name)
        if normalized_name and normalized_name not in out:
            out.append(normalized_name)
        return out

    @classmethod
    def _normalize_search_name_for_compare(cls, value: str) -> str:
        normalized = value.strip()
        if normalized.endswith('·改'):
            normalized = normalized.removesuffix('·改').strip()
        normalized = _SHIP_ALIAS_SUFFIX_RE.sub('', normalized)
        return normalized.strip()

    @classmethod
    def _matches_search_name(cls, current_name: str | None, raw_search_name: object) -> bool:
        if current_name is None:
            return False
        if not isinstance(raw_search_name, str):
            return True
        if not raw_search_name.strip():
            return True

        search_name = raw_search_name.strip()
        if current_name == search_name:
            return True

        return current_name == cls._normalize_search_name_for_compare(search_name)

    @classmethod
    def _can_short_circuit(
        cls,
        current: list[str | None],
        desired: list[str | None],
        selectors: list[dict | None],
    ) -> bool:
        # 对 search_name 槽位执行精确匹配，满足时可直接短路，避免准备页重复扫描。
        return cls._validate_with_selector(current, desired, selectors)

    @classmethod
    def _select_available_candidate(
        cls,
        current: list[str | None],
        name: str | None,
        selector: dict | None,
        *,
        desired: list[str | None] | None = None,
        slot_to_replace: int | None = None,
    ) -> tuple[str | None, dict | None]:
        """为槽位挑选候选舰船。

        对同名舰船按“目标编队所需数量”控制占用：
        允许同名重复编入（当目标中有多个同名槽位）,
        但避免超过目标所需数量。
        """
        if name is None:
            return None, None

        candidates = cls._slot_candidates(name, selector)
        occupied_counts = Counter(
            ship for idx, ship in enumerate(current) if ship is not None and idx != slot_to_replace
        )

        required_counts: Counter[str]
        if desired is None:
            required_counts = Counter()
        else:
            required_counts = Counter(ship for ship in desired if ship is not None)

        available: list[str] = []
        for candidate in candidates:
            required = required_counts.get(candidate, 1)
            occupied = occupied_counts.get(candidate, 0)
            if occupied < required:
                available.append(candidate)

        if len(available) == 0:
            return None, None

        chosen = available[0]
        if selector is None:
            return chosen, None

        narrowed_selector = dict(selector)
        narrowed_selector['candidates'] = available
        return chosen, narrowed_selector

    @classmethod
    def _match_existing_members(  # noqa: PLR0912
        cls,
        current: list[str | None],
        desired: list[str | None],
        selectors: list[dict | None],
    ) -> tuple[list[bool], set[int]]:
        """在当前舰队与目标槽位之间做一对一匹配。

        返回:
        - ok: 当前 6 个槽位中哪些槽位上的舰船可以保留
        - matched_slots: 哪些目标槽位已由当前舰队中的舰船满足
        """
        ok: list[bool] = [False] * 6
        matched_slots: set[int] = set()
        used_positions: set[int] = set()

        slot_candidates: dict[int, list[str]] = {}
        for i in range(6):
            if desired[i] is None:
                continue
            slot_candidates[i] = cls._slot_candidates(desired[i], selectors[i])

        # 第一轮: 同槽位优先，尽量减少后续拖拽/换船。
        for i, candidates in slot_candidates.items():
            ship = current[i]
            if ship is None:
                continue
            if ship in candidates:
                selector = selectors[i]
                if isinstance(selector, dict):
                    raw_search_name = selector.get('search_name')
                    # 指定了搜索关键词时，不能仅凭同名判定已满足。
                    if (
                        isinstance(raw_search_name, str)
                        and raw_search_name.strip()
                        and not cls._matches_search_name(ship, raw_search_name)
                    ):
                        continue
                ok[i] = True
                matched_slots.add(i)
                used_positions.add(i)

        # 第二轮: 跨槽位补匹配，仍保持“一目标槽位只匹配一艘船”。
        for i, candidates in slot_candidates.items():
            if i in matched_slots:
                continue
            for j, ship in enumerate(current):
                if j in used_positions or ship is None:
                    continue
                if ship in candidates:
                    selector = selectors[i]
                    if isinstance(selector, dict):
                        raw_search_name = selector.get('search_name')
                        if (
                            isinstance(raw_search_name, str)
                            and raw_search_name.strip()
                            and not cls._matches_search_name(ship, raw_search_name)
                        ):
                            continue
                    ok[j] = True
                    matched_slots.add(i)
                    used_positions.add(j)
                    break

        return ok, matched_slots

    @classmethod
    def _ship_matches_slot(cls, ship_name, target_name, selector):
        if ship_name is None:
            return False
        if selector is None:
            return ship_name == target_name
        candidates = selector.get('candidates')
        if isinstance(candidates, list):
            return ship_name in candidates
        return ship_name == target_name

    @classmethod
    def _validate_with_selector(
        cls,
        current: list[str | None],
        desired: list[str | None],
        selectors: list[dict | None],
    ) -> bool:
        for i in range(6):
            target = desired[i]
            selector = selectors[i]
            current_name = current[i]
            if target is None:
                continue
            if selector is None:
                if current_name != target:
                    return False
                continue

            raw_search_name = selector.get('search_name')
            if (
                isinstance(raw_search_name, str)
                and raw_search_name.strip()
                and not cls._matches_search_name(current_name, raw_search_name)
            ):
                return False

            candidates = selector.get('candidates')
            if not isinstance(candidates, list):
                if current_name != target:
                    return False
                continue
            if current_name not in candidates:
                return False
        return True

    # ══════════════════════════════════════════════════════════════════════
    # 位置对齐
    # ══════════════════════════════════════════════════════════════════════

    def _reorder(
        self,
        current: list[str | None],
        desired: list[str | None],
    ) -> None:
        """通过滑动将舰船移至目标位置 (对齐 legacy ``Fleet.reorder``)。

        从左到右逐槽位检查, 若当前位置不是目标船则找到目标船所在
        槽位, 通过 ``_circular_move`` 滑动到正确位置。

        Parameters
        ----------
        current:
            **变参**: 当前 6 槽位舰船名, 本方法会就地修改。
        desired:
            目标 6 槽位舰船名。
        """
        for i in range(6):
            target = desired[i]
            if target is None:
                break  # 对齐 legacy: 遇到空位即停止
            if current[i] == target:
                continue
            try:
                src = current.index(target)
            except ValueError:
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

    def _circular_move(
        self,
        src: int,
        dst: int,
        current: list[str | None],
    ) -> None:
        """滑动将舰船从 *src* 槽位移至 *dst* 槽位。

        游戏行为: 拖拽 src 到 dst 后, src 与 dst 之间的舰船做循环位移。

        Parameters
        ----------
        src:
            源槽位 (0-5)。
        dst:
            目标槽位 (0-5)。
        current:
            **变参**: 当前 6 槽位舰船名, 就地更新以反映移动后状态。
        """
        if src == dst:
            return
        sx, sy = CLICK_SHIP_SLOT[src]
        dx, dy = CLICK_SHIP_SLOT[dst]
        self._ctrl.swipe(sx, sy, dx, dy, duration=0.5)

        # 更新本地追踪 (circular shift, 对齐 legacy)
        ship = current.pop(src)
        current.insert(dst, ship)
        time.sleep(0.5)

    # ══════════════════════════════════════════════════════════════════════
    # 清空编队
    # ══════════════════════════════════════════════════════════════════════

    def _clear_fleet(self) -> None:
        """清空当前编队的所有舰船。

        反复找第一个有船的槽位 → 移除。利用游戏中舰船左对齐 + 移除后
        自动左移的特性，每次移除后下一艘船自动占据更小的槽位号，
        直到全部清空。

        注意：必须 OCR 确认槽位有船才点击，否则选船页面第一项是船名
        而非「移除」，会导致错误选船。
        """
        from autowsgr.ui.choose_ship_page import (
            ChooseShipPage,
            CLICK_REMOVE_SHIP,
        )
        from autowsgr.ui.utils import wait_for_page

        for _attempt in range(_MAX_CLEAR_ATTEMPTS):
            current = self.detect_fleet()
            if all(ship is None for ship in current):
                _log.info('[准备页] 编队已清空')
                return

            # 找到第一个有船的槽位（游戏中舰船左对齐，通常就是 0）
            target_slot = next(
                (i for i in range(6) if current[i] is not None),
                None,
            )
            if target_slot is None:
                return  # 前置 all() 已判定非全空，这里不应触发

            _log.info(
                '[准备页] 清空编队: 当前 {} 艘, 移除槽位 {} 的 {}',
                sum(1 for s in current if s is not None),
                target_slot,
                current[target_slot],
            )

            self.click_ship_slot(target_slot)
            wait_for_page(
                self._ctrl,
                ChooseShipPage.is_current_page,
                timeout=_CHOOSE_PAGE_TIMEOUT,
                source='编队',
                target='编队选船',
            )
            # 槽位有船 → 点击「移除」按钮
            self._ctrl.click_delay(*CLICK_REMOVE_SHIP)
            # 等待返回准备页
            wait_for_page(
                self._ctrl,
                lambda screen: not ChooseShipPage.is_current_page(screen),
                timeout=_CHOOSE_PAGE_TIMEOUT,
                source='编队选船',
                target='编队',
            )

        remaining = sum(1 for s in self.detect_fleet() if s is not None)
        if remaining > 0:
            _log.warning(
                '[准备页] 清空编队未完全完成: 仍有 {} 艘船',
                remaining,
            )

    # ══════════════════════════════════════════════════════════════════════
    # 单船更换
    # ══════════════════════════════════════════════════════════════════════

    def _change_single_ship(
        self,
        slot: int,
        name: str | None,
        *,
        selector: dict | None = None,
        slot_occupied: bool = True,
    ) -> str | None:
        """更换/移除指定位置的单艘舰船。

        点击槽位 -> 进入选船页面 -> 委托给
        :meth:`~autowsgr.ui.choose_ship_page.ChooseShipPage.change_single_ship`
        完成实际操作 (根据 ``_use_search`` 决定是否使用搜索框)。
        """
        from autowsgr.ui.choose_ship_page import ChooseShipPage
        from autowsgr.ui.utils import wait_for_page

        if name is None and not slot_occupied:
            return None

        self.click_ship_slot(slot)
        wait_for_page(
            self._ctrl,
            ChooseShipPage.is_current_page,
            timeout=_CHOOSE_PAGE_TIMEOUT,
            source='编队',
            target='编队选船',
        )
        choose_page = ChooseShipPage(self._ctx)
        return choose_page.change_single_ship(
            name,
            use_search=self._use_search,
            selector=selector,
        )
