"""Shared card geometry and scrollbar evidence for the seven-column ship list.

These primitives only describe visible pixels. They do not identify ships,
decide that an inventory is complete, or navigate between business pages.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

import cv2
import numpy as np

from autowsgr.ui.utils.ship_list import LEGACY_LIST_WIDTH, to_legacy_format
from autowsgr.vision import get_api_dll


if TYPE_CHECKING:
    from collections.abc import Sequence

    from autowsgr.emulator.controller import Controller


COLUMN_LEFTS_1920 = (86, 297, 508, 719, 930, 1141, 1352)
CARD_WIDTH_1920 = 192
CARD_HEIGHT_1080 = 405
_NAME_BAND_MIN_HEIGHT_720 = 12
_NAME_COLOR_BGR = np.asarray(((162, 98, 18), (173, 103, 17), (196, 116, 16)), dtype=np.int16)
_NAME_COLOR_DISTANCE = 20.0
_MIN_SLOT_BLUE_PIXELS = 80
_PACK_ROW_GAP = 8


class ShipListGeometryError(RuntimeError):
    """Visible list geometry cannot be established unambiguously."""


class NativeLocate(Protocol):
    def __call__(self, image: np.ndarray) -> list[list[int]]: ...


@dataclass(frozen=True, slots=True)
class CapturedShipListViewport:
    """Complete visible card crops and any excluded partial name bands."""

    crops: tuple[np.ndarray, ...]
    row_lengths: tuple[int, ...]
    bands: tuple[tuple[int, int], ...]
    screen_height: int = 1080
    clipped_bands: tuple[tuple[int, int], ...] = ()
    has_trailing_partial: bool = False
    row_columns: tuple[tuple[int, ...], ...] = ()
    has_leading_partial: bool = False


def name_blue_mask(image_rgb: np.ndarray) -> np.ndarray:
    bgr = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR).astype(np.int16)
    distances = np.linalg.norm(bgr[:, :, None, :] - _NAME_COLOR_BGR[None, None, :, :], axis=3)
    return np.min(distances, axis=2) < _NAME_COLOR_DISTANCE


class ShipListGeometryReader:
    """Locate ordered complete cards without depending on an OCR or identity model."""

    def __init__(
        self,
        locate: NativeLocate | None = None,
        *,
        error_type: type[ShipListGeometryError] = ShipListGeometryError,
    ) -> None:
        self._locate = locate or get_api_dll().locate
        self._error_type = error_type

    def locate_name_bands(self, screen: np.ndarray) -> tuple[tuple[int, int], ...]:
        """Return native-resolution y bands, filtering thin native-locator noise."""
        bgr_720p, scale_y, _scale_x = to_legacy_format(screen)
        raw = self._locate(bgr_720p[:, :LEGACY_LIST_WIDTH])
        bands: list[tuple[int, int]] = []
        previous_bottom = -1
        for top, bottom in raw:
            if bottom - top < _NAME_BAND_MIN_HEIGHT_720:
                continue
            if bottom - top > 45 or top < previous_bottom:
                raise self._error_type(f'native 舰名蓝条几何异常: {raw}')
            native_top = max(0, round(top * scale_y))
            native_bottom = min(screen.shape[0], round(bottom * scale_y))
            if native_bottom > native_top:
                bands.append((native_top, native_bottom))
                previous_bottom = bottom
        return tuple(bands)

    @staticmethod
    def column_bounds(width: int) -> tuple[tuple[int, int], ...]:
        scale = width / 1920
        return tuple(
            (round(left * scale), round((left + CARD_WIDTH_1920) * scale))
            for left in COLUMN_LEFTS_1920
        )

    _column_bounds = column_bounds

    @staticmethod
    def _has_complete_card_top(crop: np.ndarray) -> bool:
        if crop.shape[0] < 8 or crop.shape[1] < 2:
            return False
        hsv = cv2.cvtColor(crop[:8], cv2.COLOR_RGB2HSV)
        cyan = cv2.inRange(
            hsv,
            np.array((85, 100, 80), dtype=np.uint8),
            np.array((120, 255, 255), dtype=np.uint8),
        )
        full_rows = sum(np.count_nonzero(row) >= round(crop.shape[1] * 0.90) for row in cyan)
        return full_rows >= 2

    def _present_slots(
        self,
        screen: np.ndarray,
        bands: Sequence[tuple[int, int]],
        *,
        leading_control: bool = False,
    ) -> tuple[list[tuple[int, int, int, int, int, int]], tuple[int, ...]]:
        columns = self.column_bounds(screen.shape[1])
        blue = name_blue_mask(screen)
        slots: list[tuple[int, int, int, int, int, int]] = []
        row_lengths: list[int] = []
        pixel_scale = screen.shape[0] * screen.shape[1] / (1080 * 1920)
        threshold = max(20, round(_MIN_SLOT_BLUE_PIXELS * pixel_scale))
        for row, (top, bottom) in enumerate(bands):
            present = 0
            saw_empty = False
            for column, (left, right) in enumerate(columns):
                # Only a caller that has positively identified the leading
                # control may exclude it. Its blue border is not a ship name.
                if leading_control and row == 0 and column == 0:
                    continue
                exists = int(np.count_nonzero(blue[top:bottom, left:right])) >= threshold
                if not exists:
                    saw_empty = True
                    continue
                if saw_empty:
                    raise self._error_type('同一舰名行出现非连续卡位，无法证明几何顺序')
                slots.append((row, column, left, top, right, bottom))
                present += 1
            if present:
                row_lengths.append(present)
            else:
                raise self._error_type(f'native 舰名蓝条 {row} 没有固定列卡位证据')
        return slots, tuple(row_lengths)

    @staticmethod
    def _pack_rows(
        screen: np.ndarray,
        bands: Sequence[tuple[int, int]],
    ) -> tuple[np.ndarray, tuple[tuple[int, int], ...]]:
        if not bands:
            return np.zeros((1, 1, 3), dtype=np.uint8), ()
        list_width = round(screen.shape[1] * LEGACY_LIST_WIDTH / 1280)
        heights = [bottom - top for top, bottom in bands]
        canvas_height = sum(heights) + _PACK_ROW_GAP * (len(bands) - 1)
        canvas = np.zeros((canvas_height, list_width, 3), dtype=np.uint8)
        packed: list[tuple[int, int]] = []
        cursor = 0
        for top, bottom in bands:
            height = bottom - top
            canvas[cursor : cursor + height] = screen[top:bottom, :list_width]
            packed.append((cursor, cursor + height))
            cursor += height + _PACK_ROW_GAP
        return canvas, tuple(packed)

    def capture(
        self, screen: np.ndarray, *, leading_control: bool = False, allow_empty: bool = False
    ) -> CapturedShipListViewport:
        bands = self.locate_name_bands(screen)
        if not bands:
            if allow_empty:
                # This is only an explicit zero-geometry observation. The
                # business caller must separately prove the page is empty.
                return CapturedShipListViewport((), (), (), screen.shape[0])
            raise self._error_type('当前视口未定位到任何舰名蓝条')
        slots, _row_lengths = self._present_slots(screen, bands, leading_control=leading_control)
        if not slots:
            raise self._error_type('舰名蓝条中没有固定列卡位证据')

        row_crops: list[list[np.ndarray]] = [[] for _band in bands]
        row_columns: list[list[int]] = [[] for _band in bands]
        clipped_rows: set[int] = set()
        card_height = round(CARD_HEIGHT_1080 * screen.shape[0] / 1080)
        for row, column, left, top, right, bottom in slots:
            if bottom < card_height:
                clipped_rows.add(row)
            name_band = cv2.cvtColor(screen[top:bottom, left:right], cv2.COLOR_RGB2GRAY)
            edge_margin = max(1, round(3 * screen.shape[0] / 1080))
            if np.any(name_band[:edge_margin] > 240) or np.any(name_band[-edge_margin:] > 240):
                clipped_rows.add(row)
            card_top = max(0, bottom - card_height)
            crop = screen[card_top:bottom, left:right].copy()
            if not self._has_complete_card_top(crop):
                clipped_rows.add(row)
            row_crops[row].append(crop)
            row_columns[row].append(column)

        complete_crops: list[np.ndarray] = []
        complete_lengths: list[int] = []
        complete_bands: list[tuple[int, int]] = []
        complete_columns: list[tuple[int, ...]] = []
        for row, (band, crops) in enumerate(zip(bands, row_crops, strict=True)):
            if row in clipped_rows or not crops:
                continue
            complete_crops.extend(crops)
            complete_lengths.append(len(crops))
            complete_bands.append(band)
            complete_columns.append(tuple(row_columns[row]))
        if not complete_crops:
            raise self._error_type('当前视口没有完整可见舰名蓝条')
        return CapturedShipListViewport(
            tuple(complete_crops),
            tuple(complete_lengths),
            tuple(complete_bands),
            screen.shape[0],
            tuple(bands[row] for row in sorted(clipped_rows)),
            self._has_trailing_partial(screen, complete_bands[-1][1]),
            tuple(complete_columns),
            self._has_bright_card_rows(
                screen,
                round(90 * screen.shape[0] / 720),
                complete_bands[0][1] - card_height - max(1, round(3 * screen.shape[0] / 720)),
                leading_control=leading_control,
            ),
        )

    def _has_trailing_partial(self, screen: np.ndarray, last_complete_bottom: int) -> bool:
        """A card top below the last complete name band must later be covered in full.

        The scrollbar can already reach its bottom while the final row is still
        settling. Thin clipped name bands alone are filtered by native geometry,
        so retain the independently visible cyan card-top evidence as well.
        """
        height = screen.shape[0]
        top = last_complete_bottom + max(1, round(3 * height / 720))
        bottom = min(height, round(674 * height / 720))
        return self._has_bright_card_rows(screen, top, bottom)

    def _has_bright_card_rows(
        self,
        screen: np.ndarray,
        top: int,
        bottom: int,
        *,
        leading_control: bool = False,
    ) -> bool:
        if bottom <= top:
            return False
        for column, (left, right) in enumerate(self.column_bounds(screen.shape[1])):
            if leading_control and column == 0:
                continue
            hsv = cv2.cvtColor(screen[top:bottom, left:right], cv2.COLOR_RGB2HSV)
            # A dark blue list background also falls in the broad cyan hue
            # range; only the bright frame is independent trailing-card proof.
            cyan = cv2.inRange(
                hsv,
                np.array((85, 150, 150), dtype=np.uint8),
                np.array((120, 255, 255), dtype=np.uint8),
            )
            full_rows = np.count_nonzero(cyan, axis=1) >= round((right - left) * 0.90)
            if np.any(full_rows[:-1] & full_rows[1:]):
                return True
        return False


class ShipListScrollbar:
    """Read scrollbar endpoints and drag only inside the observed thumb."""

    def __init__(
        self,
        ctrl: Controller,
        *,
        x: int = 1580,
        step_pixels: int = 11,
        error_type: type[ShipListGeometryError] = ShipListGeometryError,
    ) -> None:
        self._ctrl = ctrl
        self._x = x
        self._step_pixels = step_pixels
        self._error_type = error_type

    @staticmethod
    def _track_bounds(screen_height: int) -> tuple[int, int]:
        return round(0.12 * screen_height), round(1034 * screen_height / 1080)

    def thumb_bounds(self, screen: np.ndarray) -> tuple[int, int]:
        """Locate one neutral light-grey thumb on the fixed vertical track."""
        height, width = screen.shape[:2]
        x = min(width - 1, round(self._x * width / 1920))
        stripe_width = max(2, round(3 * width / 1280))
        # Lossy Scrcpy frames color the outside column and quantize the two
        # interior columns (observed RGB spread <= 16). Accept only adjacent
        # bright, low-chroma columns that also agree with each other inside
        # this fixed narrow track; the dark background remains below 160.
        track = screen[:, x : min(width, x + stripe_width)].astype(np.int16)
        low_chroma = np.max(track, axis=2) - np.min(track, axis=2) <= 18
        light = np.min(track, axis=2) >= 160
        plausible = low_chroma & light
        agreement = np.max(np.abs(track[:, :-1] - track[:, 1:]), axis=2) <= 20
        track_top, track_bottom = self._track_bounds(height)
        mask = np.any(plausible[:, :-1] & plausible[:, 1:] & agreement, axis=1)
        mask[:track_top] = False
        mask[track_bottom:] = False
        runs: list[tuple[int, int]] = []
        start: int | None = None
        minimum_run = max(2, round(3 * height / 1080))
        for y, present in enumerate(mask):
            if present and start is None:
                start = y
            elif not present and start is not None:
                if y - start >= minimum_run:
                    runs.append((start, y))
                start = None
        if start is not None and track_bottom - start >= minimum_run:
            runs.append((start, track_bottom))
        if len(runs) != 1:
            raise self._error_type(f'滚动条滑块定位不唯一: {runs}')
        return runs[0]

    def thumb_bottom(self, screen: np.ndarray) -> int:
        return self.thumb_bounds(screen)[1]

    def is_top(self, screen: np.ndarray) -> bool:
        top, _bottom = self.thumb_bounds(screen)
        track_top, _track_bottom = self._track_bounds(screen.shape[0])
        return top <= track_top + round(10 * screen.shape[0] / 1080)

    def is_bottom(self, screen: np.ndarray) -> bool:
        _top, bottom = self.thumb_bounds(screen)
        _track_top, track_bottom = self._track_bounds(screen.shape[0])
        return bottom >= track_bottom - round(10 * screen.shape[0] / 1080)

    def advance(self, *, thumb_bounds: tuple[int, int], screen_height: int) -> None:
        track_top, track_bottom = self._track_bounds(screen_height)
        thumb_top, thumb_bottom = thumb_bounds
        usable_top = max(track_top, thumb_top)
        usable_bottom = min(track_bottom, thumb_bottom)
        if usable_bottom - usable_top < 2:
            raise self._error_type(f'滚动条滑块边界异常: {thumb_bounds}')
        start_y = min(usable_bottom - 2, max(usable_top, (thumb_top + thumb_bottom) // 2))
        x = round(self._x * self._ctrl.resolution[0] / 1920)
        step = max(1, round(self._step_pixels * screen_height / 1080))
        end_y = min(usable_bottom - 1, start_y + step)
        self._ctrl.shell(f'input swipe {x} {start_y} {x} {end_y} 300')
