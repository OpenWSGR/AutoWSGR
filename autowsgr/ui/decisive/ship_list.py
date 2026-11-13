"""决战选船列表：用完整卡位、重叠行和实际端点证明扫描覆盖范围。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import cv2
import numpy as np

from autowsgr.image_resources._lazy import load_template
from autowsgr.ui.choose_ship_page import ChooseShipPage
from autowsgr.ui.utils.ship_list import locate_ship_rows
from autowsgr.ui.utils.ship_list_geometry import (
    CapturedShipListViewport,
    ShipListGeometryError,
    ShipListGeometryReader,
    ShipListScrollbar,
    name_blue_mask,
)
from autowsgr.vision import ROI, ImageChecker


if TYPE_CHECKING:
    from collections.abc import Iterator

    from autowsgr.context import GameContext
    from autowsgr.emulator.frame import CapturedFrame
    from autowsgr.vision import OCREngine


type ShipListHit = tuple[str, float, float, float]


class DecisiveInventoryScanError(RuntimeError):
    """页面、卡片身份或连续覆盖不完整，禁止发布部分库存。"""


@dataclass(frozen=True, slots=True)
class ShipListViewport:
    """同一稳定帧内所有完整船卡的名字和坐标，不包含被裁切的卡片。"""

    frame: CapturedFrame
    hits: tuple[ShipListHit, ...]
    at_top: bool
    at_bottom: bool


@dataclass(frozen=True, slots=True)
class _GeometryFrame:
    frame: CapturedFrame
    cards: CapturedShipListViewport
    thumb: tuple[int, int]
    at_top: bool
    at_bottom: bool


class DecisiveShipListWalker:
    """只读识别列表，必要时滚动；选择舰船仍由选船页面执行。"""

    _FRAME_TIMEOUT = 5.0
    _OCR_ATTEMPTS = 3
    _MAX_SCROLLS = 80

    def __init__(self, ctx: GameContext, ocr: OCREngine | None = None) -> None:
        self._ctx = ctx
        self._ctrl = ctx.ctrl
        self._ocr = ocr or ctx.ocr
        self._geometry = ShipListGeometryReader()
        self._scrollbar = ShipListScrollbar(self._ctrl)
        self._leave_card = load_template(
            'decisive/ship_list_leave_720p.png', source_resolution=(1280, 720)
        )
        self._all_ships = load_template(
            'decisive/ship_list_all_ships_720p.png', source_resolution=(1280, 720)
        )
        self._all_types = load_template(
            'decisive/ship_list_all_types_720p.png', source_resolution=(1280, 720)
        )
        self._scrolls = 0

    def _check_stop(self) -> None:
        if self._ctx.stop_event.is_set():
            raise InterruptedError('扫描决战库存时收到停止请求')

    def _capture(self) -> CapturedFrame:
        self._check_stop()
        frame = self._ctrl.capture_frame()
        if not ChooseShipPage.is_current_page(frame.image):
            raise DecisiveInventoryScanError('未确认决战选船页面，停止库存扫描')
        if not ImageChecker.template_exists(
            frame.image, self._all_ships, roi=ROI(0.84, 0.17, 0.98, 0.26), confidence=0.95
        ) or not ImageChecker.template_exists(
            frame.image, self._all_types, roi=ROI(0.84, 0.65, 0.98, 0.72), confidence=0.95
        ):
            raise DecisiveInventoryScanError('决战库存扫描要求显示全部舰船且类型为全部')
        if frame.sequence is None:
            raise DecisiveInventoryScanError('选船扫描需要独立解码帧标识，不能将缓存截图当作新证据')
        return frame

    def _describe(self, frame: CapturedFrame) -> _GeometryFrame:
        leading_control = ImageChecker.template_exists(
            frame.image, self._leave_card, roi=ROI(0.065, 0.28, 0.13, 0.42), confidence=0.95
        )
        cards = self._geometry.capture(
            frame.image, leading_control=leading_control, allow_empty=True
        )
        thumb = self._scrollbar.thumb_bounds(frame.image)
        at_top = self._scrollbar.is_top(frame.image)
        at_bottom = self._scrollbar.is_bottom(frame.image)
        if not cards.crops and not (
            at_top and at_bottom and self._empty_background(frame.image, leading_control)
        ):
            raise ShipListGeometryError('零卡位观测未确认完整空背景及上下端点，拒绝判为空候选')
        return _GeometryFrame(frame, cards, thumb, at_top, at_bottom)

    @staticmethod
    def _empty_background(image: np.ndarray, leading_control: bool) -> bool:
        """逐像素确认已取证的深蓝空背景，不把无蓝条、黑屏或遮挡当作空列表。"""
        height, width = image.shape[:2]
        left, right = round(56 * width / 1280), round(1031 * width / 1280)
        top, bottom = round(90 * height / 720), round(690 * height / 720)
        roi = image[top:bottom, left:right]
        mask = np.ones(roi.shape[:2], dtype=bool)
        if leading_control:
            # 只有正向识别到离队卡，才排除该系统控件及压缩边缘；其余卡位全部检查。
            x1 = max(0, round(54 * width / 1280) - left)
            x2 = round(188 * width / 1280) - left
            y1 = round(102 * height / 720) - top
            y2 = round(378 * height / 720) - top
            mask[y1:y2, x1:x2] = False
        hsv = cv2.cvtColor(roi, cv2.COLOR_RGB2HSV)
        # 真实有/无离队卡的 ADB+Scrcpy 空列表连同底部分隔线覆盖
        # H97..120/S82..236/V31..130。
        # 小幅量化余量仍排除灰黑遮挡、亮蓝卡框、舰名条和卡片图像。
        background = cv2.inRange(
            hsv, np.array((90, 75, 25), dtype=np.uint8), np.array((125, 245, 145), dtype=np.uint8)
        )
        return bool(np.all(background[mask]) and not np.any(name_blue_mask(roi)[mask]))

    @staticmethod
    def _same_geometry(left: _GeometryFrame, right: _GeometryFrame) -> bool:
        if not left.cards.crops and not right.cards.crops:
            # 空背景已在每帧独立证实；H.264 可使全高亮轨端点漂移一两个像素。
            return (
                left.at_top
                and right.at_top
                and left.at_bottom
                and right.at_bottom
                and max(
                    abs(first - second)
                    for first, second in zip(left.thumb, right.thumb, strict=True)
                )
                <= 2
            )
        if (
            left.cards.row_lengths != right.cards.row_lengths
            or left.cards.row_columns != right.cards.row_columns
            or left.cards.bands != right.cards.bands
            or left.cards.clipped_bands != right.cards.clipped_bands
            or left.cards.has_trailing_partial != right.cards.has_trailing_partial
            or left.cards.has_leading_partial != right.cards.has_leading_partial
            or left.thumb != right.thumb
        ):
            return False
        for first, second in zip(left.cards.crops, right.cards.crops, strict=True):
            # 舰名可能滚动，只用卡身确认画面已停止位移或重排。
            first_body = cv2.resize(first[: -max(1, first.shape[0] // 9)], (24, 40))
            second_body = cv2.resize(second[: -max(1, second.shape[0] // 9)], (24, 40))
            if np.mean(np.abs(first_body.astype(np.int16) - second_body.astype(np.int16))) > 0.5:
                return False
        return True

    def _stable_frame(self, *, after_sequence: int | None = None) -> _GeometryFrame:
        deadline = time.monotonic() + self._FRAME_TIMEOUT
        previous: _GeometryFrame | None = None
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            frame = self._capture()
            if frame.sequence == after_sequence or (
                previous is not None and frame.sequence == previous.frame.sequence
            ):
                time.sleep(0.05)
                continue
            try:
                current = self._describe(frame)
            except ShipListGeometryError as exc:
                previous = None
                last_error = exc
                time.sleep(0.05)
                continue
            if previous is not None and self._same_geometry(previous, current):
                return current
            previous = current
            time.sleep(0.05)
        raise DecisiveInventoryScanError(
            f'决战选船列表未取得两个稳定的独立帧: {last_error or "仍在移动或没有新帧"}'
        )

    def _scroll(self, *, forward: bool) -> None:
        self._check_stop()
        if self._scrolls >= self._MAX_SCROLLS:
            raise DecisiveInventoryScanError(
                f'决战库存扫描超过 {self._MAX_SCROLLS} 次滚动，未证明列表完整'
            )
        self._scrolls += 1
        start, end = (560 / 720, 410 / 720) if forward else (410 / 720, 560 / 720)
        # 已验证的内容区小步滑动会保留一行重叠；滑块已到底仍可能有截断卡。
        self._ctrl.swipe(500 / 1280, start, 500 / 1280, end, duration=0.4)

    def _rewind(self, current: _GeometryFrame) -> _GeometryFrame:
        if current.at_top and current.cards.has_leading_partial:
            raise DecisiveInventoryScanError('列表顶部仍有未覆盖卡片，无法确认完整首行')
        while not current.at_top or any(
            top < current.cards.bands[0][0] for top, _bottom in current.cards.clipped_bands
        ):
            self._scroll(forward=False)
            following = self._stable_frame(after_sequence=current.frame.sequence)
            if self._same_geometry(current, following):
                raise DecisiveInventoryScanError('决战选船列表回顶没有可观测进度')
            current = following
            if current.at_top and current.cards.has_leading_partial:
                raise DecisiveInventoryScanError('列表顶部仍有未覆盖卡片，无法确认完整首行')
        return current

    def _bind_hits(self, current: _GeometryFrame) -> tuple[ShipListHit, ...]:
        if not current.cards.crops:
            return ()
        image = current.frame.image
        height, width = image.shape[:2]
        columns = self._geometry.column_bounds(width)
        row_columns = current.cards.row_columns or tuple(
            tuple(range(length)) for length in current.cards.row_lengths
        )
        expected = {
            (row, column)
            for row, columns_in_row in enumerate(row_columns)
            for column in columns_in_row
        }
        bound: dict[tuple[int, int], ShipListHit] = {}
        try:
            hits = locate_ship_rows(
                self._ocr, image, deduplicate_by_name=False, include_row_key=True
            )
        except Exception as exc:
            raise DecisiveInventoryScanError('决战选船舰名 OCR 失败') from exc
        for name, cx, cy, row_key in hits:
            y = row_key * height
            row = next(
                (
                    index
                    for index, (top, bottom) in enumerate(current.cards.bands)
                    if top - 3 <= y <= bottom + 3
                ),
                None,
            )
            if row is None:
                if any(top - 3 <= y <= bottom + 3 for top, bottom in current.cards.clipped_bands):
                    continue
                raise DecisiveInventoryScanError('舰名 OCR 命中无法对应完整或已确认截断的卡位')
            column = next(
                (
                    index
                    for index, (left, right) in enumerate(columns)
                    if left <= cx * width <= right
                ),
                None,
            )
            key = (row, column)
            if key not in expected or key in bound or not name:
                raise DecisiveInventoryScanError('舰名 OCR 与完整卡片无法一一绑定')
            bound[key] = (name, cx, cy, row_key)
        if bound.keys() != expected:
            raise DecisiveInventoryScanError('完整船卡存在未识别舰名，拒绝发布部分库存')
        return tuple(bound[key] for key in sorted(bound))

    def _recognize(self, current: _GeometryFrame) -> tuple[ShipListViewport, _GeometryFrame]:
        last_error: Exception | None = None
        for attempt in range(self._OCR_ATTEMPTS):
            self._check_stop()
            try:
                hits = self._bind_hits(current)
            except DecisiveInventoryScanError as exc:
                last_error = exc
                if attempt < self._OCR_ATTEMPTS - 1:
                    current = self._stable_frame(after_sequence=current.frame.sequence)
                    continue
                break
            return (
                ShipListViewport(
                    current.frame,
                    hits,
                    current.at_top,
                    current.at_bottom and not current.cards.has_trailing_partial,
                ),
                current,
            )
        raise DecisiveInventoryScanError(f'决战库存舰名识别三次后仍不完整: {last_error}')

    @staticmethod
    def _rows(viewport: ShipListViewport) -> tuple[tuple[str, ...], ...]:
        rows: dict[float, list[str]] = {}
        for name, _cx, _cy, row_key in viewport.hits:
            rows.setdefault(row_key, []).append(name)
        return tuple(tuple(names) for names in rows.values())

    @staticmethod
    def _overlap(
        accumulated: tuple[tuple[str, ...], ...], current: tuple[tuple[str, ...], ...]
    ) -> int:
        overlaps = [
            length
            for length in range(1, min(len(accumulated), len(current)) + 1)
            if accumulated[-length:] == current[:length]
        ]
        if not overlaps:
            raise DecisiveInventoryScanError('决战列表滚动丢失完整重叠行，无法证明连续覆盖')
        length = max(overlaps)
        starts = [
            start
            for start in range(len(accumulated) - length + 1)
            if accumulated[start : start + length] == current[:length]
        ]
        if starts != [len(accumulated) - length]:
            raise DecisiveInventoryScanError('决战选船重叠行存在重复身份歧义')
        return length

    def viewports(self) -> Iterator[ShipListViewport]:
        """从经确认的顶部迭代到底；中途停止迭代可供选船使用，不声称全库完成。"""
        self._scrolls = 0
        current = self._rewind(self._stable_frame())
        viewport, current = self._recognize(current)
        accumulated = self._rows(viewport)
        while True:
            self._check_stop()
            yield viewport
            if viewport.at_bottom:
                return
            self._scroll(forward=True)
            following = self._stable_frame(after_sequence=current.frame.sequence)
            if self._same_geometry(current, following):
                raise DecisiveInventoryScanError('决战选船列表尚未完整且滚动没有可观测进度')
            viewport, following = self._recognize(following)
            rows = self._rows(viewport)
            overlap = self._overlap(accumulated, rows)
            accumulated += rows[overlap:]
            current = following

    def scan(self) -> set[str]:
        """只有完整遍历成功才返回库存，异常和停止均不返回部分集合。"""
        names: list[str] = []
        for viewport in self.viewports():
            names.extend(hit[0] for hit in viewport.hits)
        self._check_stop()
        return set(names)
