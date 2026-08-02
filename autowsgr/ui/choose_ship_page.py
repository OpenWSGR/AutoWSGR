"""选船页面 UI 控制器。

已完成，需测试

使用方式::

    from autowsgr.ui.choose_ship_page import ChooseShipPage

    page = ChooseShipPage(ctrl)
    page.click_search_box()
    page.click_first_result()
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from autowsgr.constants import SHIPNAMES
from autowsgr.infra.logger import get_logger
from autowsgr.vision import (
    MatchStrategy,
    PixelChecker,
    PixelRule,
    PixelSignature,
)
from autowsgr.vision.ocr import _fuzzy_match
from autowsgr.vision.ocr_rules import normalize_ship_name_suffix

from .utils import wait_for_page, wait_leave_page
from .utils.ship_list import LevelOCRRetryNeededError, locate_ship_rows, read_ship_levels


if TYPE_CHECKING:
    import numpy as np

    from autowsgr.context import GameContext


_log = get_logger('ui')

# ═══════════════════════════════════════════════════════════════════════════════
# 点击坐标 (960x540 基准)
# ═══════════════════════════════════════════════════════════════════════════════

CLICK_SEARCH_BOX: tuple[float, float] = (700 / 960, 30 / 540)
"""搜索框。"""

CLICK_DISMISS_KEYBOARD: tuple[float, float] = (500 / 960, 50 / 540)
"""点击空白区域关闭键盘。"""

CLICK_REMOVE_SHIP: tuple[float, float] = (83 / 960, 167 / 540)
"""「移除」按钮 — 将当前槽位舰船移除。"""

CLICK_FIRST_RESULT: tuple[float, float] = (183 / 960, 167 / 540)
"""搜索结果列表中的第一个结果。"""

#: 选船列表滚动参数
_SCROLL_FROM_Y: float = 0.55
_SCROLL_TO_Y: float = 0.30
_OCR_MAX_ATTEMPTS: int = 3

_SHIP_TYPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    'dd': ('驱逐',),
    'cl': ('轻巡',),
    'ca': ('重巡',),
    'cav': ('航巡',),
    'clt': ('雷巡',),
    'bb': ('战列',),
    'bc': ('战巡',),
    'bbv': ('航战',),
    'cv': ('航母',),
    'cvl': ('轻母',),
    'av': ('装母',),
    'ss': ('潜艇',),
    'ssg': ('导潜',),
    'cg': ('导巡',),
    'cgaa': ('防巡',),
    'ddg': ('导驱',),
    'ddgaa': ('防驱',),
    'bm': ('重炮',),
    'cbg': ('大巡',),
    'cf': ('旗舰',),
}

PAGE_SIGNATURE = PixelSignature(
    name='choose_ship_page',
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.8594, 0.1514, (31, 46, 69), tolerance=30.0),
        PixelRule.of(0.8602, 0.3167, (31, 139, 238), tolerance=30.0),
        PixelRule.of(0.8578, 0.5306, (57, 57, 57), tolerance=30.0),
        PixelRule.of(0.8594, 0.6736, (54, 54, 54), tolerance=30.0),
        PixelRule.of(0.8656, 0.8014, (35, 57, 81), tolerance=30.0),
    ],
)

INPUT_SIGNATURE = PixelSignature(
    name='choose_ship_input',
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.3109, 0.9417, (253, 253, 253), tolerance=30.0),
        PixelRule.of(0.4437, 0.9417, (253, 253, 253), tolerance=30.0),
        PixelRule.of(0.5883, 0.9347, (253, 253, 253), tolerance=30.0),
    ],
)

# ═══════════════════════════════════════════════════════════════════════════════
# 页面控制器
# ═══════════════════════════════════════════════════════════════════════════════


class ChooseShipPage:
    """选船页面控制器。

    从出征准备页面点击舰船槽位后进入此页面。
    提供搜索、选择、移除舰船等原子操作。

    Parameters
    ----------
    ctrl:
        Android 设备控制器实例。
    """

    def __init__(self, ctx: GameContext) -> None:
        self._ctx = ctx
        self._ctrl = ctx.ctrl

    # ── 页面识别 ──────────────────────────────────────────────────────────

    @staticmethod
    def is_current_page(screen: np.ndarray) -> bool:
        """判断截图是否为选船页面。

        .. warning::
            尚未实现像素签名采集，当前始终返回 False。
            选船页面识别由 ops 层通过图像模板匹配完成。

        Parameters
        ----------
        screen:
            截图 (HxWx3, RGB)。
        """
        result = PixelChecker.check_signature(screen, PAGE_SIGNATURE)
        return result.matched

    def _wait_leave_current_page(self, timeout: float = 5.0):
        wait_leave_page(
            self._ctrl, self.is_current_page, timeout=timeout, source='编队选船', target='编队'
        )

    # ── 操作 ──────────────────────────────────────────────────────────────
    def ensure_search_box(self) -> None:
        """点击搜索框，准备输入舰船名。"""
        _log.info('[UI] 选船 → 打开搜索框')
        self._ctrl.click(*CLICK_SEARCH_BOX)
        wait_for_page(
            self._ctrl,
            lambda screen: PixelChecker.check_signature(screen, INPUT_SIGNATURE).matched,
            timeout=5.0,
        )

    def input_ship_name(self, name: str) -> None:
        """在搜索框中输入舰船名。

        调用前应先 :meth:`click_search_box`。

        Parameters
        ----------
        name:
            舰船名 (中文)。
        """
        _log.debug("[UI] 选船 → 输入舰船名 '{}'", name)
        self._ctrl.text(name)
        # 等待输入同步
        time.sleep(0.1)

    def ensure_dismiss_keyboard(self) -> None:
        """点击空白区域关闭软键盘。"""
        _log.debug('[UI] 选船 → 关闭键盘')
        self._ctrl.click(*CLICK_DISMISS_KEYBOARD)
        wait_leave_page(
            self._ctrl,
            lambda screen: PixelChecker.check_signature(screen, INPUT_SIGNATURE).matched,
            timeout=5.0,
        )
        # 等待键盘关闭
        time.sleep(0.2)

    def click_first_result(self) -> None:
        """点击搜索结果中的第一个舰船。"""
        _log.debug('[UI] 选船 → 点击第一个结果')
        self._ctrl.click(*CLICK_FIRST_RESULT)

    def click_remove(self) -> None:
        """点击「移除」按钮，移除当前槽位的舰船。"""
        _log.debug('[UI] 选船 → 移除舰船')
        self._ctrl.click(*CLICK_REMOVE_SHIP)

    @classmethod
    def _selection_options(  # noqa: PLR0912
        cls,
        name: str,
        selector: dict | None,
    ) -> list[dict[str, object]]:
        """整理智能换船传入的独立主选和备选规则。"""
        if selector is None:
            return [{'name': name}]

        raw_options = selector.get('options')
        if not isinstance(raw_options, list):
            raw_candidates = selector.get('candidates')
            raw_options = raw_candidates if isinstance(raw_candidates, list) else [name]

        target_identity = cls._normalize_ship_name(name)
        options: list[dict[str, object]] = []
        for raw_option in raw_options:
            if isinstance(raw_option, str):
                option: dict[str, object] = {'name': raw_option.strip()}
                source = selector
            elif isinstance(raw_option, dict):
                raw_name = raw_option.get('name')
                if not isinstance(raw_name, str):
                    continue
                option = {'name': raw_name.strip()}
                source = raw_option
            else:
                continue

            if not option['name']:
                continue

            if (
                not isinstance(raw_option, str)
                or cls._normalize_ship_name(raw_option) == target_identity
            ):
                raw_search = source.get('search_name')
                if isinstance(raw_search, str) and raw_search.strip():
                    option['search_name'] = raw_search.strip()

            raw_ship_types = source.get('ship_type')
            values = [raw_ship_types] if isinstance(raw_ship_types, str) else raw_ship_types
            if isinstance(values, list):
                ship_types = list(
                    dict.fromkeys(
                        value.strip().lower()
                        for value in values
                        if isinstance(value, str) and value.strip()
                    ),
                )
                if ship_types:
                    option['ship_type'] = ship_types

            for field in ('min_level', 'max_level'):
                value = source.get(field)
                if isinstance(value, int) and value > 0:
                    option[field] = value
            if source.get('relaxed_constraints') is True:
                option['relaxed_constraints'] = True
            options.append(option)

        options.sort(
            key=lambda option: cls._normalize_ship_name(str(option['name'])) != target_identity,
        )
        return options or [{'name': name}]

    def change_single_ship(
        self,
        name: str | None,
        *,
        use_search: bool = True,
        selector: dict | None = None,
    ) -> str | None:
        """更换/移除当前槽位的舰船。

        使用 DLL 行定位 + OCR 在选船列表中查找目标舰船并点击。
        最多重试 ``_OCR_MAX_ATTEMPTS`` 次, 每次失败后向上滚动列表。

        Parameters
        ----------
        name:
            目标舰船名; ``None`` 表示移除当前槽位舰船。
        use_search:
            是否使用搜索框输入舰船名来过滤列表。
            常规出征为 ``True`` (默认), 决战为 ``False``
            (决战选船界面没有搜索框)。
        selector:
            智能换船内部规则。``options`` 中每一项分别保存舰名、
            搜索名、允许舰种和等级范围；旧 ``candidates`` 字符串
            列表仍兼容读取。

        Returns
        -------
        str | None
            实际选中的舰船名；移除操作返回 ``None``。
        """
        if name is None:
            self.click_remove()
            self._wait_leave_current_page()
            return None

        if self._ctx.ocr is None:
            _log.warning('[UI] 未提供 OCR 引擎, 无法识别选船列表')
            return None

        options = self._selection_options(name, selector)
        for option in options:
            candidate = str(option['name'])
            raw_search_name = option.get('search_name', candidate)
            search_name = self._normalize_search_keyword(str(raw_search_name))
            ship_types = option.get('ship_type')
            min_level = option.get('min_level')
            max_level = option.get('max_level')
            relaxed_constraints = option.get('relaxed_constraints') is True
            if use_search:
                self.ensure_search_box()
                self.input_ship_name(search_name)
                self.ensure_dismiss_keyboard()
            matched = self._click_ship_in_list(
                candidate,
                ship_type=ship_types if isinstance(ship_types, list) else None,
                min_level=min_level if isinstance(min_level, int) else None,
                max_level=max_level if isinstance(max_level, int) else None,
                relaxed_constraints=relaxed_constraints,
            )
            if matched is not None:
                self._wait_leave_current_page()
                return matched

        candidates = [option['name'] for option in options]
        _log.error(
            '[UI] 未在选船列表中找到满足独立规则的候选: {}',
            candidates,
        )
        raise RuntimeError(f'未找到满足条件的目标舰船: {candidates}')

    @staticmethod
    def _normalize_hit_entry(hit: object) -> tuple[str, float, float, float]:
        """归一化 locate_ship_rows 的返回为 (name, cx, cy, row_key)。"""
        if not isinstance(hit, (tuple, list)):
            raise TypeError(f'unsupported hit entry: {hit!r}')

        if len(hit) < 3:
            raise ValueError(f'unsupported hit entry length: {hit!r}')

        matched = str(hit[0]).strip()
        cx = float(hit[1])
        cy = float(hit[2])

        if len(hit) >= 4 and isinstance(hit[3], (int, float)):
            row_key = round(float(hit[3]), 4)
        else:
            row_key = round(cy, 4)
        return matched, cx, cy, row_key

    @staticmethod
    def _normalize_level_entry(entry: object) -> tuple[str, int | None, float]:
        """归一化 read_ship_levels 的返回为 (name, level, row_key)。"""
        if not isinstance(entry, (tuple, list)):
            raise TypeError(f'unsupported level entry: {entry!r}')

        if len(entry) < 2:
            raise ValueError(f'unsupported level entry length: {entry!r}')

        matched = str(entry[0]).strip()
        level = entry[1] if isinstance(entry[1], int) else None
        row_key = (
            round(float(entry[2]), 4)
            if len(entry) >= 3 and isinstance(entry[2], (int, float))
            else -1.0
        )
        return matched, level, row_key

    @staticmethod
    def _is_level_in_range(level: int | None, min_level: int | None, max_level: int | None) -> bool:
        if min_level is None and max_level is None:
            return True
        if level is None:
            return False
        if min_level is not None and level < min_level:
            return False
        return not (max_level is not None and level > max_level)

    def _click_ship_in_list(  # noqa: C901, PLR0912
        self,
        name: str,
        *,
        ship_type: list[str] | None = None,
        min_level: int | None = None,
        max_level: int | None = None,
        relaxed_constraints: bool = False,
    ) -> str | None:
        """在选船列表页使用 DLL 定位 + OCR 识别舰船名并点击目标。

        最多重试 ``_OCR_MAX_ATTEMPTS`` 次, 每次失败后向上滚动列表。

        Parameters
        ----------
        name:
            目标舰船名。
            匹配时会先做舰名归一化（如去除“·改”与尾部括号别名）后再比较。
        relaxed_constraints:
            备选舰船使用。舰名命中后只尝试一次等级和舰种校验，
            约束识别失败或不匹配时仍按舰名选择。

        Returns
        -------
        str | None
            匹配并点击成功时返回舰船名；失败返回 ``None``。
        """
        assert self._ctx.ocr is not None

        for attempt in range(_OCR_MAX_ATTEMPTS):
            screen = self._ctrl.screenshot()
            use_level_filter = min_level is not None or max_level is not None
            if use_level_filter:
                raw_hits = locate_ship_rows(
                    self._ctx.ocr,
                    screen,
                    deduplicate_by_name=False,
                    include_row_key=True,
                )
                try:
                    raw_levels = read_ship_levels(
                        self._ctx.ocr,
                        screen,
                        deduplicate_by_name=False,
                        include_row_key=True,
                    )
                except LevelOCRRetryNeededError:
                    if relaxed_constraints:
                        _log.warning(
                            '[UI] 备选舰等级 OCR 失败，继续按舰名校验',
                        )
                        raw_levels = []
                    else:
                        _log.warning(
                            '[UI] 等级 OCR 噪声过高，触发重新识别 (第 {}/{} 次)',
                            attempt + 1,
                            _OCR_MAX_ATTEMPTS,
                        )
                        if attempt >= _OCR_MAX_ATTEMPTS - 1:
                            _log.error(
                                '[UI] 等级 OCR 噪声过高，本规则校验失败',
                            )
                            return None
                        time.sleep(0.3)
                        continue
            else:
                raw_hits = locate_ship_rows(self._ctx.ocr, screen)
                raw_levels = []

            hits = [self._normalize_hit_entry(hit) for hit in raw_hits]
            level_map: dict[float, dict[str, list[int | None]]] = {}
            for entry in raw_levels:
                level_name, level, row_key = self._normalize_level_entry(entry)
                normalized_level_name = self._normalize_ship_name(level_name)
                row_levels = level_map.setdefault(row_key, {})
                row_levels.setdefault(normalized_level_name, []).append(level)

            for matched, cx, cy, row_key in hits:
                normalized_matched = self._normalize_ship_name(matched)
                if not self._matches_ship_name(name, matched):
                    continue

                level = None
                if use_level_filter:
                    row_levels = level_map.get(row_key)
                    if row_levels:
                        name_levels = row_levels.get(normalized_matched)
                        if name_levels:
                            level = name_levels.pop(0)
                if not self._is_level_in_range(level, min_level, max_level):
                    _log.warning(
                        "[UI] 命中 '{}', 但等级 {} 不满足范围 [{}, {}]",
                        matched,
                        level if level is not None else '未知',
                        min_level if min_level is not None else '-',
                        max_level if max_level is not None else '-',
                    )
                    if not relaxed_constraints:
                        continue

                if ship_type is not None:
                    detected_ship_type = self._detect_ship_type_near_hit(
                        screen,
                        cx,
                        cy,
                        row_key,
                    )
                    if not self._is_ship_type_in_rule(detected_ship_type, ship_type):
                        _log.warning(
                            "[UI] 命中 '{}' 舰种 '{}' 不满足要求 '{}'",
                            matched,
                            detected_ship_type if detected_ship_type is not None else '未知',
                            ship_type,
                        )
                        if not relaxed_constraints:
                            continue

                _log.info(
                    "[UI] 选船 DLL+OCR -> '{}' (第 {}/{} 次), 点击 ({:.3f}, {:.3f})",
                    name,
                    attempt + 1,
                    _OCR_MAX_ATTEMPTS,
                    cx,
                    cy,
                )
                time.sleep(1.0)
                self._ctrl.click(cx, cy)
                return matched

            _log.warning(
                "[UI] 选船列表未匹配到 '{}' (第 {}/{} 次), 向上滚动",
                name,
                attempt + 1,
                _OCR_MAX_ATTEMPTS,
            )
            if attempt < _OCR_MAX_ATTEMPTS - 1:
                self._ctrl.swipe(0.4, _SCROLL_FROM_Y, 0.4, _SCROLL_TO_Y, duration=0.4)
                time.sleep(0.5)

        return None

    def _detect_ship_type_near_hit(
        self,
        screen: np.ndarray,
        cx: float,
        cy: float,
        row_key: float,
    ) -> str | None:
        """在命中卡片附近 OCR 识别舰种。"""
        assert self._ctx.ocr is not None

        h, w = screen.shape[:2]
        x_px = int(max(0, min(w - 1, cx * w)))
        y_px = int(max(0, min(h - 1, cy * h)))
        row_y = int(max(0, min(h - 1, row_key * h))) if row_key >= 0 else y_px

        probes: list[tuple[int, int, int, int]] = [
            (max(0, x_px - 110), max(0, row_y - 120), min(w, x_px + 110), max(0, row_y - 12)),
            (max(0, x_px - 130), max(0, y_px - 150), min(w, x_px + 130), max(0, y_px - 18)),
            (max(0, x_px - 140), max(0, y_px - 170), min(w, x_px + 140), min(h, y_px + 20)),
        ]

        for x1, y1, x2, y2 in probes:
            if x2 - x1 < 16 or y2 - y1 < 16:
                continue
            crop = screen[y1:y2, x1:x2]
            results = self._ctx.ocr.recognize(crop)
            for result in results:
                text = str(getattr(result, 'text', '')).strip()
                ship_type = self._extract_ship_type_from_text(text)
                if ship_type is not None:
                    return ship_type
        return None

    @staticmethod
    def _extract_ship_type_from_text(text: str) -> str | None:
        if not text:
            return None
        normalized = text.replace(' ', '')
        for ship_type, keywords in _SHIP_TYPE_KEYWORDS.items():
            if any(keyword in normalized for keyword in keywords):
                return ship_type
        return None

    @staticmethod
    def _is_ship_type_in_rule(
        detected: str | None,
        expected: str | list[str],
    ) -> bool:
        if detected is None:
            return False
        rules = [expected] if isinstance(expected, str) else expected
        normalized = {rule.strip().lower() for rule in rules}
        return detected in normalized or (
            'ss_or_ssg' in normalized
            and detected in {'ss', 'ssg'}
        )

    @staticmethod
    def _normalize_search_keyword(name: str) -> str:
        """保留用户在游戏内使用的自定义舰名作为搜索条件。"""
        return name.strip()

    @staticmethod
    def _normalize_ship_name(name: str) -> str:
        return normalize_ship_name_suffix(name)

    @classmethod
    def _matches_ship_name(cls, target: str, matched: str) -> bool:
        """比较目标名与 OCR 船池结果，不修改任一原始文本。"""
        normalized_target = cls._normalize_ship_name(target)
        normalized_matched = cls._normalize_ship_name(matched)
        if normalized_target == normalized_matched:
            return True

        pool_target = _fuzzy_match(target, SHIPNAMES, threshold=0)
        return (
            pool_target is not None and cls._normalize_ship_name(pool_target) == normalized_matched
        )
