"""Read-only material inventory scanning from native card geometry.

The scanner uses the Rust-backed blue name-bar locator only as geometry,
fixed material-grid columns, batched complete-card identity recognition, and
ADB shell taps on the right scrollbar.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

import adbutils
import cv2
import numpy as np

from autowsgr.infra.logger import get_logger
from autowsgr.ui.material_first_intensify import (
    MaterialFirstIntensifyController,
    is_material_selector_screen,
)
from autowsgr.ui.utils.ship_list import LEGACY_LIST_WIDTH, to_legacy_format
from autowsgr.vision import get_api_dll

_log = get_logger('ops.intensify')


if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from autowsgr.emulator.controller import Controller
    from autowsgr.vision.ship_card_recognizer import ShipCardRecognizer


_COLUMN_LEFTS_1920 = (86, 297, 508, 719, 930, 1141, 1352)
_CARD_WIDTH_1920 = 192
_NAME_BAND_MIN_HEIGHT_720 = 12
_NAME_COLOR_BGR = np.asarray(
    ((162, 98, 18), (173, 103, 17), (196, 116, 16)),
    dtype=np.int16,
)
_NAME_COLOR_DISTANCE = 20.0
_MIN_SLOT_BLUE_PIXELS = 80
_PACK_ROW_GAP = 8
_CARD_HEIGHT_1080 = 405


class MaterialInventoryScanError(RuntimeError):
    """Raised when a complete read-only inventory cannot be proven."""


@dataclass(frozen=True, slots=True)
class MaterialViewport:
    """One viewport's ordered ship-name occurrences."""

    names: tuple[str, ...]
    ship_ids: tuple[int, ...]
    row_lengths: tuple[int, ...]
    bands: tuple[tuple[int, int], ...]
    positions: tuple[tuple[int, int, float, float], ...] = ()


@dataclass(frozen=True, slots=True)
class CapturedMaterialViewport:
    """Geometry-only viewport captured before identity recognition."""

    crops: tuple[np.ndarray, ...]
    row_lengths: tuple[int, ...]
    bands: tuple[tuple[int, int], ...]
    screen_height: int = 1080


@dataclass(frozen=True, slots=True)
class MaterialInventorySnapshot:
    """A complete material inventory assembled from overlapping viewports."""

    names: tuple[str, ...]
    ship_ids: tuple[int, ...]
    total: int
    viewport_count: int
    refs: tuple[str, ...] = ()
    acquisition_method: str = 'native-card-geometry+wsg-ncc+adb-scrollbar'


class NativeLocate(Protocol):
    def __call__(self, image: np.ndarray) -> list[list[int]]: ...


class AdbLosslessMaterialDevice:
    """Minimal ADB-only screenshot/input adapter for material scanning."""

    def __init__(self, serial: str, *, adb_device: object | None = None) -> None:
        if not serial:
            raise MaterialInventoryScanError('素材扫描必须显式指定 ADB serial')
        self._serial = serial
        self._device = adb_device or adbutils.adb.device(serial=serial)
        self._resolution: tuple[int, int] | None = None

    def screenshot(self) -> np.ndarray:
        last_error = None
        for _ in range(3):
            try:
                image = self._device.screenshot(error_ok=False).convert('RGB')
                return np.asarray(image, dtype=np.uint8)
            except Exception as err:
                last_error = err
                time.sleep(0.1)
        raise MaterialInventoryScanError(f'ADB 截图失败: {last_error}') from last_error

    def shell(self, command: str) -> str:
        result = self._device.shell(command)
        return result if isinstance(result, str) else str(result)

    @property
    def resolution(self) -> tuple[int, int]:
        if self._resolution is None:
            size = self._device.window_size()
            self._resolution = (int(size[0]), int(size[1]))
        return self._resolution

    def click(self, x: float, y: float, *, delay: bool = True) -> None:
        width, height = self.resolution
        px = min(width - 1, max(0, round(x * width)))
        py = min(height - 1, max(0, round(y * height)))
        self._device.shell(f'input tap {px} {py}')
        if delay:
            time.sleep(0.3)

    def key_event(self, key_code: int, *, delay: bool = True) -> None:
        self._device.shell(f'input keyevent {key_code}')
        if delay:
            time.sleep(0.3)

    def verify_cetus(self) -> None:
        product = self.shell('getprop ro.product.name').strip()
        model = self.shell('getprop ro.product.model').strip()
        if product != 'Cetus' or model != 'CET-AL00':
            raise MaterialInventoryScanError(f'设备身份不匹配: product={product}, model={model}')


def _name_blue_mask(image_rgb: np.ndarray) -> np.ndarray:
    bgr = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR).astype(np.int16)
    distances = np.linalg.norm(bgr[:, :, None, :] - _NAME_COLOR_BGR[None, None, :, :], axis=3)
    return np.min(distances, axis=2) < _NAME_COLOR_DISTANCE


class MaterialViewportReader:
    """Convert material screenshots into ordered canonical identities."""

    def __init__(
        self,
        identities: ShipCardRecognizer,
        *,
        locate: NativeLocate | None = None,
    ) -> None:
        self._identities = identities
        self._locate = locate or get_api_dll().locate

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
                raise MaterialInventoryScanError(f'native 舰名蓝条几何异常: {raw}')
            native_top = max(0, round(top * scale_y))
            native_bottom = min(screen.shape[0], round(bottom * scale_y))
            if native_bottom > native_top:
                bands.append((native_top, native_bottom))
                previous_bottom = bottom
        return tuple(bands)

    @staticmethod
    def _column_bounds(width: int) -> tuple[tuple[int, int], ...]:
        scale = width / 1920
        return tuple(
            (round(left * scale), round((left + _CARD_WIDTH_1920) * scale))
            for left in _COLUMN_LEFTS_1920
        )

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
    ) -> tuple[list[tuple[int, int, int, int, int, int]], tuple[int, ...]]:
        columns = self._column_bounds(screen.shape[1])
        blue = _name_blue_mask(screen)
        slots: list[tuple[int, int, int, int, int, int]] = []
        row_lengths: list[int] = []
        pixel_scale = screen.shape[0] * screen.shape[1] / (1080 * 1920)
        threshold = max(20, round(_MIN_SLOT_BLUE_PIXELS * pixel_scale))
        for row, (top, bottom) in enumerate(bands):
            present = 0
            saw_empty = False
            for column, (left, right) in enumerate(columns):
                exists = int(np.count_nonzero(blue[top:bottom, left:right])) >= threshold
                if not exists:
                    saw_empty = True
                    continue
                if saw_empty:
                    raise MaterialInventoryScanError('同一舰名行出现非连续卡位，无法证明几何顺序')
                slots.append((row, column, left, top, right, bottom))
                present += 1
            if present:
                row_lengths.append(present)
            else:
                raise MaterialInventoryScanError(f'native 舰名蓝条 {row} 没有固定列卡位证据')
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

    def capture(self, screen: np.ndarray) -> CapturedMaterialViewport:
        bands = self.locate_name_bands(screen)
        if not bands:
            raise MaterialInventoryScanError('当前视口未定位到任何舰名蓝条')
        slots, _row_lengths = self._present_slots(screen, bands)
        if not slots:
            raise MaterialInventoryScanError('舰名蓝条中没有固定列卡位证据')

        row_crops: list[list[np.ndarray]] = [[] for _band in bands]
        clipped_rows: set[int] = set()
        card_height = round(_CARD_HEIGHT_1080 * screen.shape[0] / 1080)
        for row, _column, left, top, right, bottom in slots:
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

        complete_crops: list[np.ndarray] = []
        complete_lengths: list[int] = []
        complete_bands: list[tuple[int, int]] = []
        for row, (band, crops) in enumerate(zip(bands, row_crops, strict=True)):
            if row in clipped_rows or not crops:
                continue
            complete_crops.extend(crops)
            complete_lengths.append(len(crops))
            complete_bands.append(band)
        if not complete_crops:
            raise MaterialInventoryScanError('当前视口没有完整可见舰名蓝条')
        return CapturedMaterialViewport(
            tuple(complete_crops),
            tuple(complete_lengths),
            tuple(complete_bands),
            screen.shape[0],
        )

    def capture_best(
        self,
        screens: Sequence[np.ndarray],
    ) -> CapturedMaterialViewport:
        """Keep the sharpest complete-card crop from geometry-identical frames."""
        captures = tuple(self.capture(screen) for screen in screens)
        geometry = (captures[0].row_lengths, captures[0].bands)
        if any((capture.row_lengths, capture.bands) != geometry for capture in captures[1:]):
            raise MaterialInventoryScanError('稳定帧之间的舰名栏几何不一致')

        def detail_score(crop: np.ndarray) -> float:
            return float(cv2.Laplacian(crop, cv2.CV_32F).var())

        crops = tuple(
            max((capture.crops[index] for capture in captures), key=detail_score)
            for index in range(len(captures[0].crops))
        )
        return CapturedMaterialViewport(crops, *geometry, captures[0].screen_height)

    def recognize_captures(
        self,
        captures: Sequence[CapturedMaterialViewport],
    ) -> tuple[MaterialViewport, ...]:
        crops = [crop for capture in captures for crop in capture.crops]
        batch_results = self._identities.recognize(crops)
        if len(batch_results) != len(crops):
            raise MaterialInventoryScanError('船卡识别返回数量与船卡数量不一致')
        viewports: list[MaterialViewport] = []
        cursor = 0
        for capture in captures:
            count = len(capture.crops)
            viewport_results = batch_results[cursor : cursor + count]
            cursor += count
            names: list[str] = []
            ship_ids: list[int] = []
            recognized_row_lengths: list[int] = []
            positions: list[tuple[int, int, float, float]] = []
            row_cursor = 0
            for row, row_length in enumerate(capture.row_lengths):
                row_results = viewport_results[row_cursor : row_cursor + row_length]
                row_names = self._normalize_results(row_results)
                row_cursor += row_length
                names.extend(row_names)
                ship_ids.extend(self._ship_ids(row_results))
                recognized_row_lengths.append(len(row_names))
                _band_top, band_bottom = capture.bands[row]
                card_height = round(_CARD_HEIGHT_1080 * capture.screen_height / 1080)
                center_y = (band_bottom - card_height / 2) / capture.screen_height
                for column, identity in enumerate(row_results):
                    if identity is None:
                        continue
                    left = _COLUMN_LEFTS_1920[column]
                    positions.append(
                        (
                            row,
                            column,
                            (left + _CARD_WIDTH_1920 / 2) / 1920,
                            center_y,
                        )
                    )
            viewports.append(
                MaterialViewport(
                    tuple(names),
                    tuple(ship_ids),
                    tuple(recognized_row_lengths),
                    capture.bands,
                    tuple(positions),
                )
            )
        return tuple(viewports)

    @staticmethod
    def _normalize_results(batch_results: Sequence[object | None]) -> tuple[str, ...]:
        names: list[str] = []
        for index, identity in enumerate(batch_results):
            if identity is None:
                raise MaterialInventoryScanError(
                    f'船卡 {index} 低于识别阈值或身份未知，拒绝宣称素材库存完整'
                )
            name = getattr(identity, 'name', None)
            if not isinstance(name, str) or not name:
                raise MaterialInventoryScanError(f'船卡 {index} 缺少规范舰名')
            names.append(name)
        return tuple(names)

    @staticmethod
    def _ship_ids(batch_results: Sequence[object | None]) -> tuple[int, ...]:
        ship_ids: list[int] = []
        for index, identity in enumerate(batch_results):
            ship_id = None if identity is None else getattr(identity, 'ship_id', None)
            if isinstance(ship_id, bool) or not isinstance(ship_id, int) or ship_id < 0:
                raise MaterialInventoryScanError(f'船卡 {index} 缺少规范舰船 ID')
            ship_ids.append(ship_id)
        return tuple(ship_ids)

    def read(self, screen: np.ndarray) -> MaterialViewport:
        return self.recognize_captures((self.capture(screen),))[0]


def merge_viewport_identities(
    accumulated: Sequence[tuple[int, str]],
    current: Sequence[tuple[int, str]],
    *,
    minimum_overlap: int = 7,
) -> tuple[tuple[tuple[int, str], ...], int]:
    """Merge by canonical ID and display name, never by display name alone."""
    left = tuple(accumulated)
    right = tuple(current)
    if not left:
        return right, 0
    maximum = min(len(left), len(right))
    overlap = next(
        (size for size in range(maximum, 0, -1) if left[-size:] == right[:size]),
        0,
    )
    if 0 < overlap < minimum_overlap or (overlap == 0 and left[-1][1] == right[0][1]):
        raise MaterialInventoryScanError('相邻素材视口无法建立规范身份序列衔接')
    merged = left + right[overlap:]
    closed: set[tuple[int, str]] = set()
    previous: tuple[int, str] | None = None
    for identity in merged:
        if identity == previous:
            continue
        if identity in closed:
            raise MaterialInventoryScanError('素材规范身份未保持单一连续分组')
        if previous is not None:
            closed.add(previous)
        previous = identity
    return merged, overlap


def merge_viewport_names(
    accumulated: Sequence[str],
    current: Sequence[str],
    *,
    minimum_overlap: int = 7,
) -> tuple[tuple[str, ...], int]:
    """Compatibility helper for non-authoritative name-only callers and tests."""
    left = tuple(accumulated)
    right = tuple(current)
    if not left:
        return right, 0
    maximum = min(len(left), len(right))
    overlap = next(
        (size for size in range(maximum, 0, -1) if left[-size:] == right[:size]),
        0,
    )
    if 0 < overlap < minimum_overlap:
        raise MaterialInventoryScanError('相邻素材视口无法建立舰名序列衔接')
    merged = left + right[overlap:]
    closed: set[str] = set()
    previous: str | None = None
    for name in merged:
        if name == previous:
            continue
        if name in closed:
            raise MaterialInventoryScanError('素材舰名未保持单一连续分组')
        if previous is not None:
            closed.add(previous)
        previous = name
    return merged, overlap


class AdbScrollbarStepper:
    """Move only through an Android-side short drag inside the scrollbar thumb."""

    def __init__(self, ctrl: Controller, *, x: int = 1580, step_pixels: int = 11) -> None:
        self._ctrl = ctrl
        self._x = x
        self._step_pixels = step_pixels

    @staticmethod
    def _track_bounds(screen_height: int) -> tuple[int, int]:
        return round(0.12 * screen_height), round(1034 * screen_height / 1080)

    def thumb_bounds(self, screen: np.ndarray) -> tuple[int, int]:
        """Locate the light-grey scrollbar thumb on its fixed vertical track."""
        height, width = screen.shape[:2]
        x = min(width - 1, round(self._x * width / 1920))
        column = screen[:, x].astype(np.int16)
        # Lossless Cetus fixtures show the thumb as nearly-neutral RGB 184-187,
        # while the underlying track is dark grey around RGB 65-80.
        neutral = np.max(column, axis=1) - np.min(column, axis=1) <= 8
        light = np.min(column, axis=1) >= 160
        track_top, track_bottom = self._track_bounds(height)
        mask = neutral & light
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
            raise MaterialInventoryScanError(f'滚动条滑块定位不唯一: {runs}')
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
            raise MaterialInventoryScanError(f'滚动条滑块边界异常: {thumb_bounds}')
        start_y = min(usable_bottom - 2, max(usable_top, (thumb_top + thumb_bottom) // 2))
        x = round(self._x * self._ctrl.resolution[0] / 1920)
        step = max(1, round(self._step_pixels * screen_height / 1080))
        end_y = min(usable_bottom - 1, start_y + step)
        self._ctrl.shell(f'input swipe {x} {start_y} {x} {end_y} 300')


def has_selected_material(screen: np.ndarray) -> bool:
    """Detect the large bright-blue sequence badge drawn over a selected card."""
    hsv = cv2.cvtColor(screen, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, np.array((90, 130, 120)), np.array((115, 255, 255)))
    height, width = screen.shape[:2]
    mask[:, round(width * 0.81) :] = 0
    count, _labels, stats, _centers = cv2.connectedComponentsWithStats(mask)
    minimum_area = round(1200 * height * width / (1080 * 1920))
    maximum_area = round(16_000 * height * width / (1080 * 1920))
    candidates: list[tuple[int, int, int, int]] = []
    for index in range(1, count):
        x, y, component_width, component_height, area = map(int, stats[index])
        if (
            minimum_area <= area <= maximum_area
            and round(35 * width / 1920) <= component_width <= round(150 * width / 1920)
            and round(35 * height / 1080) <= component_height <= round(150 * height / 1080)
            and 0.55 <= component_width / component_height <= 1.8
            and area / (component_width * component_height) >= 0.35
            and y < round(0.90 * height)
        ):
            candidates.append((x, y, component_width, component_height))
    if not candidates:
        return False
    minimum_badge_width = round(60 * width / 1920)
    minimum_badge_height = round(60 * height / 1080)
    candidates = [
        candidate
        for candidate in candidates
        if candidate[2] >= minimum_badge_width and candidate[3] >= minimum_badge_height
    ]
    if not candidates:
        return False
    large_badge_area = round(6_000 * height * width / (1080 * 1920))
    if any(
        component_width * component_height >= large_badge_area
        for _x, _y, component_width, component_height in candidates
    ):
        return True
    card_pitch = round(211 * width / 1920)
    y_tolerance = round(5 * height / 1080)
    for x, y, _component_width, _component_height in candidates:
        repeated = any(
            abs(other_y - y) <= y_tolerance
            and abs(abs(other_x - x) - card_pitch) <= round(5 * width / 1920)
            for other_x, other_y, _other_width, _other_height in candidates
        )
        if not repeated:
            return True
    return False


class MaterialInventoryScanner:
    """Assemble a complete inventory from overlapping read-only viewports."""

    def __init__(
        self,
        ctrl: Controller,
        reader: MaterialViewportReader,
        stepper: AdbScrollbarStepper,
        *,
        is_material_screen: Callable[[np.ndarray], bool] = is_material_selector_screen,
        stagnant_limit: int = 2,
        settle_seconds: float = 0.8,
        sample_count: int = 8,
        sample_interval_seconds: float = 0.65,
    ) -> None:
        self._ctrl = ctrl
        self._reader = reader
        self._stepper = stepper
        self._is_material_screen = is_material_screen
        self._stagnant_limit = stagnant_limit
        self._settle_seconds = settle_seconds
        if sample_count < 2:
            raise ValueError('素材视口至少需要采样两帧')
        self._sample_count = sample_count
        self._sample_interval_seconds = sample_interval_seconds

    def _stable_screens(self) -> tuple[np.ndarray, ...]:
        screens: list[np.ndarray] = []
        thumb_bounds: tuple[int, int] | None = None
        for index in range(self._sample_count):
            screen = self._ctrl.screenshot()
            if not self._is_material_screen(screen) or has_selected_material(screen):
                raise MaterialInventoryScanError('素材页面状态不安全或已有素材被选中')
            current_thumb = self._stepper.thumb_bounds(screen)
            if thumb_bounds is None:
                thumb_bounds = current_thumb
            elif current_thumb != thumb_bounds:
                raise MaterialInventoryScanError('多帧采样期间滚动条位置发生变化')
            screens.append(screen)
            if index + 1 < self._sample_count:
                time.sleep(self._sample_interval_seconds)
        return tuple(screens)

    def scan(self, *, max_viewports: int = 24) -> MaterialInventorySnapshot:
        captures: list[CapturedMaterialViewport] = []
        previous_thumb: int | None = None
        stagnant = 0
        for viewport_count in range(1, max_viewports + 1):
            stable_screens = self._stable_screens()
            screen = stable_screens[-1]
            if viewport_count == 1 and not self._stepper.is_top(screen):
                raise MaterialInventoryScanError('素材扫描必须从滚动条顶部开始')
            captured = self._reader.capture_best(stable_screens)
            thumb_bounds = self._stepper.thumb_bounds(screen)
            thumb_bottom = thumb_bounds[1]
            no_thumb_move = previous_thumb is not None and thumb_bottom == previous_thumb
            at_bottom = self._stepper.is_bottom(screen)
            if no_thumb_move and not at_bottom:
                raise MaterialInventoryScanError('滚动条在未到底时没有移动')
            if not (at_bottom and no_thumb_move):
                captures.append(captured)
                _log.info('[OPS] 扫描素材库存: 视口第 {} 步, 已捕获 {} 组视口', viewport_count, len(captures))
            stagnant = stagnant + 1 if at_bottom and no_thumb_move else 0
            if stagnant >= self._stagnant_limit:
                if not captures:
                    raise MaterialInventoryScanError('素材库存没有权威视口证据')
                _log.info('[OPS] 正在解析素材舰船图像 (共 {} 组视口)...', len(captures))
                viewports = self._reader.recognize_captures(captures)
                revision_payload = '|'.join(
                    f'{viewport_index}:{ship_id}:{name}'
                    for viewport_index, viewport in enumerate(viewports)
                    for ship_id, name in zip(viewport.ship_ids, viewport.names, strict=True)
                )
                revision = hashlib.sha256(revision_payload.encode()).hexdigest()[:16]
                accumulated: tuple[tuple[int, str], ...] = ()
                refs: tuple[str, ...] = ()
                for viewport_index, viewport in enumerate(viewports):
                    if len(viewport.ship_ids) != len(viewport.names):
                        raise MaterialInventoryScanError('素材舰船 ID 数量与舰名数量不一致')
                    viewport_refs = tuple(
                        f'material:{revision}:{viewport_index}:{row}:{column}:{x:.4f}:{y:.4f}'
                        for row, column, x, y in viewport.positions
                    )
                    if len(viewport_refs) != len(viewport.names):
                        raise MaterialInventoryScanError('素材位置数量与舰名数量不一致')
                    merged, overlap = merge_viewport_identities(
                        accumulated,
                        tuple(zip(viewport.ship_ids, viewport.names, strict=True)),
                        minimum_overlap=1,
                    )
                    accumulated = merged
                    refs += viewport_refs[overlap:]
                ship_ids = tuple(ship_id for ship_id, _name in accumulated)
                names = tuple(name for _ship_id, name in accumulated)
                return MaterialInventorySnapshot(
                    names,
                    ship_ids,
                    len(accumulated),
                    len(viewports),
                    refs,
                )
            self._stepper.advance(thumb_bounds=thumb_bounds, screen_height=screen.shape[0])
            time.sleep(self._settle_seconds)
            previous_thumb = thumb_bottom
        raise MaterialInventoryScanError(f'超过最大视口数 {max_viewports}，无法证明素材列表到底')


def scan_material_inventory_from_main(
    device: AdbLosslessMaterialDevice,
    identities: ShipCardRecognizer,
    *,
    max_viewports: int = 24,
) -> MaterialInventorySnapshot:
    """Navigate from main to the material selector, then perform a read-only scan."""
    device.verify_cetus()
    MaterialFirstIntensifyController(device).enter_material_selector_from_main()
    return scan_material_inventory_from_selector(
        device,
        identities,
        max_viewports=max_viewports,
    )


def scan_material_inventory_from_selector(
    device: AdbLosslessMaterialDevice,
    identities: ShipCardRecognizer,
    *,
    max_viewports: int = 24,
) -> MaterialInventorySnapshot:
    """Scan an already verified, unselected material selector without navigating."""
    device.verify_cetus()
    reader = MaterialViewportReader(identities)
    stepper = AdbScrollbarStepper(device)
    scanner = MaterialInventoryScanner(device, reader, stepper)
    snapshot = scanner.scan(max_viewports=max_viewports)
    device.verify_cetus()
    return snapshot
