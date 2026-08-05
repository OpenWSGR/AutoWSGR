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

import cv2

from autowsgr.constants import SHIPNAMES, normalize_ship_name
from autowsgr.infra.logger import get_logger
from autowsgr.types import ShipType
from autowsgr.vision import (
    MatchStrategy,
    PixelChecker,
    PixelRule,
    PixelSignature,
)
from autowsgr.vision.ocr import _fuzzy_match

from .utils import wait_for_page, wait_leave_page
from .utils.ship_list import LevelOCRRetryNeededError, locate_ship_rows, read_ship_levels


if TYPE_CHECKING:
    import numpy as np

    from autowsgr.combat.fleet import ShipSelector
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

#: 船池卡片信息区域，以 1280x720 截图为校准基准。
_CARD_REFERENCE_WIDTH = 1280
_CARD_REFERENCE_HEIGHT = 720
_SHIP_TYPE_HALF_WIDTH = 68
_SHIP_TYPE_TOP_OFFSET = 72
_SHIP_TYPE_BOTTOM_OFFSET = 24
_SHIP_TYPE_OCR_SCALES = (2, 3)

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

    def change_single_ship(
        self,
        selector: ShipSelector | None,
        *,
        use_search: bool = True,
    ) -> str | None:
        """按一条明确规则更换舰船，或移除当前槽位舰船。

        使用 DLL 行定位 + OCR 在选船列表中查找目标舰船并点击。
        最多重试 ``_OCR_MAX_ATTEMPTS`` 次, 每次失败后向上滚动列表。

        Parameters
        ----------
        selector:
            FleetChange 已决定好的单条舰船选择规则；``None`` 表示移除。
        use_search:
            是否使用搜索框输入舰船名来过滤列表。
            常规出征为 ``True`` (默认), 决战为 ``False``
            (决战选船界面没有搜索框)。

        Returns
        -------
        str | None
            实际选中的舰船名；移除操作返回 ``None``。
        """
        if selector is None:
            self.click_remove()
            self._wait_leave_current_page()
            return None

        if self._ctx.ocr is None:
            _log.warning('[UI] 未提供 OCR 引擎, 无法识别选船列表')
            return None

        search_name = self._normalize_search_keyword(
            selector.search_name or selector.name,
        )
        if use_search:
            self.ensure_search_box()
            self.input_ship_name(search_name)
            self.ensure_dismiss_keyboard()
        matched = self._click_ship_in_list(
            selector.name,
            ship_type=selector.ship_types or None,
            min_level=selector.min_level,
            max_level=selector.max_level,
            relaxed_constraints=selector.relaxed_constraints,
        )
        if matched is not None:
            self._wait_leave_current_page()
        return matched

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
        ship_type: tuple[ShipType, ...] | None = None,
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
                normalized_level_name = normalize_ship_name(level_name)
                if normalized_level_name is None:
                    continue
                row_levels = level_map.setdefault(row_key, {})
                row_levels.setdefault(normalized_level_name, []).append(level)

            for matched, cx, cy, row_key in hits:
                normalized_matched = normalize_ship_name(matched)
                if normalized_matched is None:
                    continue
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
    ) -> ShipType | None:
        """使用旧 OCR 流程在命中卡片附近识别舰种。"""
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

    def detect_ship_type_in_single_card(
        self,
        screen: np.ndarray,
        cx: float,
        cy: float,
        row_key: float,
    ) -> ShipType | None:
        """新 OCR 的单卡舰种识别入口，旧 OCR 流程不会调用此方法。"""
        assert self._ctx.ocr is not None

        h, w = screen.shape[:2]
        x_px = max(0, min(w - 1, round(cx * w)))
        y_px = max(0, min(h - 1, round(cy * h)))
        row_y = max(0, min(h - 1, round(row_key * h))) if row_key >= 0 else y_px

        half_width = max(1, round(_SHIP_TYPE_HALF_WIDTH * w / _CARD_REFERENCE_WIDTH))
        top_offset = max(1, round(_SHIP_TYPE_TOP_OFFSET * h / _CARD_REFERENCE_HEIGHT))
        bottom_offset = max(1, round(_SHIP_TYPE_BOTTOM_OFFSET * h / _CARD_REFERENCE_HEIGHT))

        x1 = max(0, x_px - half_width)
        x2 = min(w, x_px + half_width)
        y1 = max(0, row_y - top_offset)
        y2 = max(0, min(h, row_y - bottom_offset))
        if x2 - x1 < 16 or y2 - y1 < 16:
            return None

        crop = screen[y1:y2, x1:x2]
        for scale in _SHIP_TYPE_OCR_SCALES:
            enlarged = cv2.resize(
                crop,
                None,
                fx=scale,
                fy=scale,
                interpolation=cv2.INTER_CUBIC,
            )
            detected_types: set[ShipType] = set()
            results = self._ctx.ocr.recognize(enlarged)
            for result in results:
                text = str(getattr(result, 'text', '')).strip()
                normalized = text.replace(' ', '')
                detected_types.update(
                    ship_type
                    for ship_type in ShipType
                    if ship_type is not ShipType.Other and ship_type.value in normalized
                )
            if len(detected_types) == 1:
                return next(iter(detected_types))
            if len(detected_types) > 1:
                _log.warning(
                    '[UI] 单卡舰种 OCR 得到多个结果: {}',
                    sorted(ship_type.value for ship_type in detected_types),
                )
                return None
        return None

    @staticmethod
    def _extract_ship_type_from_text(text: str) -> ShipType | None:
        if not text:
            return None
        normalized = text.replace(' ', '')
        for ship_type in ShipType:
            if ship_type is not ShipType.Other and ship_type.value in normalized:
                return ship_type
        return None

    @staticmethod
    def _is_ship_type_in_rule(
        detected: ShipType | None,
        expected: tuple[ShipType, ...],
    ) -> bool:
        return detected is not None and detected in expected

    @staticmethod
    def _normalize_search_keyword(name: str) -> str:
        """保留用户在游戏内使用的自定义舰名作为搜索条件。"""
        return name.strip()

    @classmethod
    def _matches_ship_name(cls, target: str, matched: str) -> bool:
        """比较目标名与 OCR 船池结果，不修改任一原始文本。"""
        normalized_target = normalize_ship_name(target)
        normalized_matched = normalize_ship_name(matched)
        if normalized_target == normalized_matched:
            return True

        pool_target = _fuzzy_match(target, SHIPNAMES, threshold=0)
        return pool_target is not None and normalize_ship_name(pool_target) == normalized_matched
