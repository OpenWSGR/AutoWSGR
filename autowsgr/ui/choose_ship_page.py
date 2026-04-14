"""选船页面 UI 控制器。

已完成，需测试

使用方式::

    from autowsgr.ui.choose_ship_page import ChooseShipPage

    page = ChooseShipPage(ctrl)
    page.click_search_box()
    page.click_first_result()
"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

from autowsgr.infra.logger import get_logger
from autowsgr.vision import (
    MatchStrategy,
    PixelChecker,
    PixelRule,
    PixelSignature,
)

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

CLICK_DISMISS_KEYBOARD: tuple[float, float] = (50 / 960, 50 / 540)
"""点击空白区域关闭键盘。"""

CLICK_REMOVE_SHIP: tuple[float, float] = (83 / 960, 167 / 540)
"""「移除」按钮 — 将当前槽位舰船移除。"""

CLICK_FIRST_RESULT: tuple[float, float] = (183 / 960, 167 / 540)
"""搜索结果列表中的第一个结果。"""

#: 选船列表滚动参数
_SCROLL_FROM_Y: float = 0.55
_SCROLL_TO_Y: float = 0.30
_OCR_MAX_ATTEMPTS: int = 3
_SHIP_ALIAS_SUFFIX_RE = re.compile(r'\s*[（(][^（）()]*[)）]\s*$')

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
        wait_leave_page(self._ctrl, self.is_current_page, timeout=timeout)

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

    def ensure_dismiss_keyboard(self) -> None:
        """点击空白区域关闭软键盘。"""
        _log.debug('[UI] 选船 → 关闭键盘')
        self._ctrl.click(*CLICK_DISMISS_KEYBOARD)
        wait_leave_page(
            self._ctrl,
            lambda screen: PixelChecker.check_signature(screen, INPUT_SIGNATURE).matched,
            timeout=5.0,
        )

    def click_first_result(self) -> None:
        """点击搜索结果中的第一个舰船。"""
        _log.debug('[UI] 选船 → 点击第一个结果')
        self._ctrl.click(*CLICK_FIRST_RESULT)

    def click_remove(self) -> None:
        """点击「移除」按钮，移除当前槽位的舰船。"""
        _log.debug('[UI] 选船 → 移除舰船')
        self._ctrl.click(*CLICK_REMOVE_SHIP)

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
            可选规则，支持 ``candidates`` / ``search_name`` /
            ``min_level`` / ``max_level``。
            其中 ``search_name`` 用于指定搜索框关键字（仅在
            ``use_search=True`` 且界面存在搜索框时生效），
            ``candidates`` 用于限定允许点击的舰船名集合，
            ``min_level`` / ``max_level`` 用于按等级范围筛选。

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

        candidates = [name]
        search_name: str | None = None
        min_level: int | None = None
        max_level: int | None = None

        if isinstance(selector, dict):
            raw_candidates = selector.get('candidates')
            if isinstance(raw_candidates, list):
                parsed = [str(v).strip() for v in raw_candidates if str(v).strip()]
                if parsed:
                    candidates = parsed
            raw_min = selector.get('min_level')
            raw_max = selector.get('max_level')
            raw_search = selector.get('search_name')
            if isinstance(raw_search, str) and raw_search.strip():
                search_name = raw_search.strip()
            if isinstance(raw_min, int) and raw_min > 0:
                min_level = raw_min
            if isinstance(raw_max, int) and raw_max > 0:
                max_level = raw_max

        if use_search and search_name:
            self.ensure_search_box()
            self.input_ship_name(search_name)
            self.ensure_dismiss_keyboard()
            matched = self._click_ship_in_list(
                name,
                min_level=min_level,
                max_level=max_level,
            )
            if matched is not None:
                self._wait_leave_current_page()
                return matched

        for candidate in candidates:
            if use_search:
                self.ensure_search_box()
                self.input_ship_name(candidate)
                self.ensure_dismiss_keyboard()
            matched = self._click_ship_in_list(
                candidate,
                min_level=min_level,
                max_level=max_level,
            )
            if matched is not None:
                self._wait_leave_current_page()
                return matched

        level_hint = ''
        if min_level is not None or max_level is not None:
            if min_level is not None and max_level is not None:
                level_hint = f' (等级限制: {min_level}-{max_level})'
            elif min_level is not None:
                level_hint = f' (等级限制: >= {min_level})'
            else:
                level_hint = f' (等级限制: <= {max_level})'
        _log.error('[UI] 未在选船列表中找到可用候选: {}{}', candidates, level_hint)
        raise RuntimeError(f'未找到满足条件的目标舰船: {candidates}{level_hint}')

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
        if max_level is not None and level > max_level:
            return False
        return True

    def _click_ship_in_list(
        self,
        name: str,
        *,
        min_level: int | None = None,
        max_level: int | None = None,
    ) -> str | None:
        """在选船列表页使用 DLL 定位 + OCR 识别舰船名并点击目标。

        最多重试 ``_OCR_MAX_ATTEMPTS`` 次, 每次失败后向上滚动列表。

        Parameters
        ----------
        name:
            目标舰船名。
            匹配时会先做舰名归一化（如去除“·改”与尾部括号别名）后再比较。

        Returns
        -------
        str | None
            匹配并点击成功时返回舰船名；失败返回 ``None``。
        """
        assert self._ctx.ocr is not None
        normalized_target = self._normalize_ship_name(name)

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
                except LevelOCRRetryNeededError as exc:
                    _log.warning(
                        '[UI] 等级 OCR 噪声过高，触发重新识别 (第 {}/{} 次)',
                        attempt + 1,
                        _OCR_MAX_ATTEMPTS,
                    )
                    if attempt >= _OCR_MAX_ATTEMPTS - 1:
                        raise RuntimeError('等级 OCR 噪声过高，重试后仍失败') from exc
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
                if normalized_matched != normalized_target:
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

    @staticmethod
    def _normalize_ship_name(name: str) -> str:
        normalized = name.strip()
        normalized = normalized.removesuffix('·改')
        normalized = _SHIP_ALIAS_SUFFIX_RE.sub('', normalized)
        return normalized.strip()
