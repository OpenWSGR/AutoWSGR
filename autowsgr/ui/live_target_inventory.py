"""Cetus adapters for read-only target inventory scanning."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

import cv2
import numpy as np

from autowsgr.types import ShipType
from autowsgr.ui.intensify_workflow import ShipStats
from autowsgr.ui.live_intensify import is_target_selector
from autowsgr.ui.target_inventory_scanner import (
    CardRect,
    TargetCardIdentity,
    TargetInventoryScanError,
    TargetInventoryScanner,
    TargetInventorySnapshot,
)


if TYPE_CHECKING:
    from autowsgr.ui.material_inventory_scanner import AdbLosslessMaterialDevice
    from autowsgr.vision.ocr import OCREngine
    from autowsgr.vision.ship_card_recognizer import ShipCardRecognizer


_STRENGTHEN_CROPS = (
    (0.09, 0.58, 0.28, 0.82),
    (0.33, 0.58, 0.52, 0.82),
    (0.57, 0.58, 0.76, 0.82),
    (0.81, 0.58, 0.99, 0.82),
)
_NAME_CROP = (0.0, 0.88, 1.0, 1.0)
_TRACK_X_1920 = 1580
_TRACK_TOP_1080 = 130
_TRACK_BOTTOM_1080 = 1034


class TargetStatFallback(Protocol):
    def __call__(self, image: np.ndarray) -> int | None: ...


class TargetMaxResolver(Protocol):
    def __call__(self, ship_id: int) -> ShipStats | None: ...


class TargetScrollInput(Protocol):
    def scroll(
        self,
        x: float,
        y: float,
        *,
        horizontal: float = 0.0,
        vertical: float = 0.0,
        delay: bool = True,
    ) -> None: ...


def _relative_crop(
    screen: np.ndarray,
    card: CardRect,
    bounds: tuple[float, float, float, float],
) -> np.ndarray:
    x1, y1, x2, y2 = bounds
    width = card.right - card.left
    height = card.bottom - card.top
    return screen[
        card.top + round(height * y1) : card.top + round(height * y2),
        card.left + round(width * x1) : card.left + round(width * x2),
    ]


def _average_hash(image: np.ndarray, size: int = 16) -> int:
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    resized = cv2.resize(gray, (size, size), interpolation=cv2.INTER_AREA)
    bits = resized >= float(resized.mean())
    value = 0
    for bit in bits.flat:
        value = (value << 1) | int(bit)
    return value


def _stable_card_hash(card_image: np.ndarray) -> int:
    """Hash the static card body while excluding the scrolling name ticker."""
    stable_bottom = max(1, round(card_image.shape[0] * _NAME_CROP[1]))
    return _average_hash(card_image[:stable_bottom])


def target_thumb_bounds(screen: np.ndarray) -> tuple[int, int]:
    """Locate the shorter target-list thumb on the shared right-side track."""
    height, width = screen.shape[:2]
    x = min(width - 1, round(_TRACK_X_1920 * width / 1920))
    column = screen[:, x].astype(np.int16)
    neutral = np.max(column, axis=1) - np.min(column, axis=1) <= 12
    light = np.min(column, axis=1) >= 150
    track_top = round(_TRACK_TOP_1080 * height / 1080)
    track_bottom = round(_TRACK_BOTTOM_1080 * height / 1080)
    mask = neutral & light
    mask[:track_top] = False
    mask[track_bottom:] = False
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for y, present in enumerate(mask):
        if present and start is None:
            start = y
        elif not present and start is not None:
            if y - start >= round(60 * height / 1080):
                runs.append((start, y))
            start = None
    if start is not None and track_bottom - start >= round(60 * height / 1080):
        runs.append((start, track_bottom))
    if len(runs) != 1:
        raise TargetInventoryScanError(f'目标滚动条滑块定位不唯一: {runs}')
    return runs[0]


def _is_cross(crop: np.ndarray) -> bool:
    hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, np.array((90, 120, 60)), np.array((130, 255, 255)))
    height, width = mask.shape
    center = mask[
        round(height * 0.10) : round(height * 0.85),
        round(width * 0.15) : round(width * 0.95),
    ]
    count, _labels, stats, _centers = cv2.connectedComponentsWithStats(center)
    diagonals = [
        index
        for index in range(1, count)
        if 7 <= stats[index, cv2.CC_STAT_HEIGHT] <= round(height * 0.45)
        and 4 <= stats[index, cv2.CC_STAT_WIDTH] <= round(width * 0.35)
        and 20 <= stats[index, cv2.CC_STAT_AREA] <= 90
    ]
    if len(diagonals) >= 2:
        return True
    if count <= 1:
        return False
    dominant = max((stats[index] for index in range(1, count)), key=lambda item: item[4])
    width = int(dominant[cv2.CC_STAT_WIDTH])
    height = int(dominant[cv2.CC_STAT_HEIGHT])
    area = int(dominant[cv2.CC_STAT_AREA])
    return (
        width >= round(center.shape[1] * 0.85)
        and height >= round(center.shape[0] * 0.50)
        and area / (width * height) >= 0.65
    )


def _topology_digit(crop: np.ndarray) -> int | None:
    """Recognize reliable zero/one topology; leave other digits to a fallback."""
    hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, np.array((90, 150, 70)), np.array((125, 255, 255)))
    mask[: round(mask.shape[0] * 0.18), :] = 0
    mask[round(mask.shape[0] * 0.88) :, :] = 0
    mask[:, : round(mask.shape[1] * 0.12)] = 0
    mask[:, round(mask.shape[1] * 0.94) :] = 0
    count, labels, stats, _centers = cv2.connectedComponentsWithStats(mask)
    accepted = [
        label
        for label in range(1, count)
        if 7 <= stats[label, cv2.CC_STAT_HEIGHT] <= round(mask.shape[0] * 0.55)
        and 2 <= stats[label, cv2.CC_STAT_WIDTH] <= round(mask.shape[1] * 0.50)
        and stats[label, cv2.CC_STAT_AREA] >= 8
    ]
    if len(accepted) != 1:
        return None
    cleaned = np.zeros_like(mask)
    for label in accepted:
        cleaned[labels == label] = 255
    points = cv2.findNonZero(cleaned)
    if points is None:
        return None
    x, y, width, height = cv2.boundingRect(points)
    glyph = cleaned[y : y + height, x : x + width]
    _contours, hierarchy = cv2.findContours(glyph, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    holes = 0 if hierarchy is None else sum(1 for item in hierarchy[0] if item[3] >= 0)
    if holes in (1, 2):
        return 0 if holes == 1 else 8
    column_ink = (glyph > 0).sum(axis=0)
    if height >= 14 and int((column_ink >= height - 2).sum()) >= 3:
        return 1
    return None


def _extract_digit_glyph(crop: np.ndarray) -> np.ndarray | None:
    """Extract and enlarge only the blue glyph, excluding borders and icons."""
    hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, np.array((90, 150, 70)), np.array((125, 255, 255)))
    mask[: round(mask.shape[0] * 0.18), :] = 0
    mask[round(mask.shape[0] * 0.88) :, :] = 0
    mask[:, : round(mask.shape[1] * 0.12)] = 0
    mask[:, round(mask.shape[1] * 0.94) :] = 0
    count, labels, stats, _centers = cv2.connectedComponentsWithStats(mask)
    accepted = [
        label
        for label in range(1, count)
        if 7 <= stats[label, cv2.CC_STAT_HEIGHT] <= round(mask.shape[0] * 0.55)
        and 2 <= stats[label, cv2.CC_STAT_WIDTH] <= round(mask.shape[1] * 0.50)
        and stats[label, cv2.CC_STAT_AREA] >= 8
    ]
    if not accepted:
        return None
    cleaned = np.zeros_like(mask)
    for label in accepted:
        cleaned[labels == label] = 255
    points = cv2.findNonZero(cleaned)
    if points is None:
        return None
    x, y, width, height = cv2.boundingRect(points)
    glyph = cleaned[y : y + height, x : x + width]
    enlarged = cv2.resize(
        glyph,
        (max(1, width * 8), max(1, height * 8)),
        interpolation=cv2.INTER_NEAREST,
    )
    enlarged_rgb = cv2.cvtColor(enlarged, cv2.COLOR_GRAY2RGB)
    return cv2.copyMakeBorder(
        enlarged_rgb,
        24,
        24,
        24,
        24,
        cv2.BORDER_CONSTANT,
        value=(0, 0, 0),
    )


def _extract_digit_color(crop: np.ndarray) -> np.ndarray | None:
    """Locate the blue glyphs but preserve their original antialiased RGB pixels."""
    hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, np.array((90, 150, 70)), np.array((125, 255, 255)))
    mask[: round(mask.shape[0] * 0.18), :] = 0
    mask[round(mask.shape[0] * 0.88) :, :] = 0
    mask[:, : round(mask.shape[1] * 0.12)] = 0
    mask[:, round(mask.shape[1] * 0.94) :] = 0
    count, labels, stats, _centers = cv2.connectedComponentsWithStats(mask)
    accepted = [
        label
        for label in range(1, count)
        if 7 <= stats[label, cv2.CC_STAT_HEIGHT] <= round(mask.shape[0] * 0.55)
        and 2 <= stats[label, cv2.CC_STAT_WIDTH] <= round(mask.shape[1] * 0.50)
        and stats[label, cv2.CC_STAT_AREA] >= 8
    ]
    if not accepted:
        return None
    cleaned = np.zeros_like(mask)
    for label in accepted:
        cleaned[labels == label] = 255
    points = cv2.findNonZero(cleaned)
    if points is None:
        return None
    x, y, width, height = cv2.boundingRect(points)
    glyph = crop[y : y + height, x : x + width]
    enlarged = cv2.resize(
        glyph,
        (max(1, width * 6), max(1, height * 6)),
        interpolation=cv2.INTER_CUBIC,
    )
    return cv2.copyMakeBorder(
        enlarged,
        24,
        24,
        24,
        24,
        cv2.BORDER_CONSTANT,
        value=(0, 0, 0),
    )


def _is_max(crop: np.ndarray) -> bool:
    hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
    orange = cv2.inRange(hsv, np.array((5, 150, 140)), np.array((35, 255, 255)))
    orange[:, : round(orange.shape[1] * 0.12)] = 0
    orange[:, round(orange.shape[1] * 0.92) :] = 0
    orange[: round(orange.shape[0] * 0.12), :] = 0
    orange[round(orange.shape[0] * 0.90) :, :] = 0
    return int((orange > 0).sum()) >= max(12, crop.shape[0] * crop.shape[1] // 20)


@dataclass(slots=True)
class CetusTargetCardReader:
    identities: ShipCardRecognizer
    ocr: OCREngine | None = None
    max_resolver: TargetMaxResolver | None = None
    allow_unknown: bool = False

    def identify_all(
        self,
        screen: np.ndarray,
        cards: tuple[CardRect, ...],
    ) -> tuple[TargetCardIdentity, ...]:
        card_images = [screen[card.top : card.bottom, card.left : card.right] for card in cards]
        identities = self.identities.recognize(card_images)
        if len(identities) != len(card_images):
            raise TargetInventoryScanError('目标舰页面存在未识别完整卡片，拒绝宣称扫描完成')
        if not self.allow_unknown and any(identity is None for identity in identities):
            raise TargetInventoryScanError('目标舰页面存在未识别完整卡片，拒绝宣称扫描完成')
        return tuple(
            TargetCardIdentity(
                ship_id=identity.ship_id if identity is not None else 0,
                name=identity.name if identity is not None else '未知舰船',
                ship_type=identity.ship_type if identity is not None else ShipType.Other,
                visual_hash=_stable_card_hash(card_image),
                identity_confidence=identity.confidence if identity is not None else 0.0,
                identity_match_key=identity.match_key if identity is not None else 'unknown',
                masked=getattr(identity, 'masked', False) if identity is not None else False,
            )
            for identity, card_image in zip(identities, card_images, strict=True)
        )

    def _read_stat(self, crop: np.ndarray, maximum: int) -> int | None:
        if maximum == 0 or _is_cross(crop):
            return 0
        if _is_max(crop):
            return maximum
        topology = _topology_digit(crop)
        if topology is not None:
            return topology
        if self.ocr is None:
            return None
        color_glyph = _extract_digit_color(crop)
        value = None if color_glyph is None else self.ocr.recognize_number(color_glyph)
        if value is None:
            binary_glyph = _extract_digit_glyph(crop)
            value = None if binary_glyph is None else self.ocr.recognize_number(binary_glyph)
        return value if value is not None and 0 <= value <= 999 else None

    def read_levels(
        self,
        screen: np.ndarray,
        card: CardRect,
        identity: TargetCardIdentity,
    ) -> ShipStats | None:
        if identity.ship_id == 0:
            return ShipStats(0, 0, 0, 0)
        maximum = None if self.max_resolver is None else self.max_resolver(identity.ship_id)
        if maximum is None:
            return ShipStats(0, 0, 0, 0)
        maximum_values = (
            maximum.firepower,
            maximum.torpedo,
            maximum.armor,
            maximum.anti_air,
        )
        values = [
            self._read_stat(_relative_crop(screen, card, bounds), field_maximum)
            for bounds, field_maximum in zip(
                _STRENGTHEN_CROPS,
                maximum_values,
                strict=True,
            )
        ]
        if any(value is None for value in values):
            return None
        firepower, torpedo, armor, anti_air = values
        assert firepower is not None
        assert torpedo is not None
        assert armor is not None
        assert anti_air is not None
        return ShipStats(firepower, torpedo, armor, anti_air)


class CetusTargetScanDevice:
    def __init__(
        self,
        device: AdbLosslessMaterialDevice,
        *,
        scroll_input: TargetScrollInput,
        scroll_amount: float = -0.25,
    ) -> None:
        self._device = device
        self._scroll_input = scroll_input
        self._scroll_amount = scroll_amount

    def screenshot(self) -> np.ndarray:
        screen = self._device.screenshot()
        if not is_target_selector(screen):
            raise TargetInventoryScanError('当前不是安全目标选择页')
        target_thumb_bounds(screen)
        return screen

    def _swipe_track(self, start_y: int, end_y: int, screen_height: int) -> None:
        width, device_height = self._device.resolution
        x = round(_TRACK_X_1920 * width / 1920)
        scale = device_height / screen_height
        self._device.shell(
            f'input swipe {x} {round(start_y * scale)} {x} {round(end_y * scale)} 300'
        )

    def rewind_target_list(self) -> None:
        for _attempt in range(15):
            screen = self.screenshot()
            try:
                top, bottom = target_thumb_bounds(screen)
                target_top = round(_TRACK_TOP_1080 * screen.shape[0] / 1080)
                if top <= target_top + round(10 * screen.shape[0] / 1080):
                    return
            except Exception:
                pass

            if hasattr(self._device, 'shell'):
                x = round(500 * self._device.resolution[0] / 1920)
                y1 = round(200 * self._device.resolution[1] / 1080)
                y2 = round(900 * self._device.resolution[1] / 1080)
                self._device.shell(f'input swipe {x} {y1} {x} {y2} 250')
                time.sleep(0.35)
            else:
                top, bottom = target_thumb_bounds(screen)
                target_top = round(_TRACK_TOP_1080 * screen.shape[0] / 1080)
                self._swipe_track((top + bottom) // 2, target_top, screen.shape[0])
        raise TargetInventoryScanError('目标列表回顶超过最大尝试次数')

    @staticmethod
    def _frame_digest(screen: np.ndarray) -> bytes:
        """Hash the target list body without trusting one transient animation frame."""
        body = np.ascontiguousarray(screen[:, : round(screen.shape[1] * 0.82)])
        return hashlib.blake2b(body, digest_size=16).digest()

    def advance_target_list(self) -> np.ndarray:
        baseline = self._frame_digest(self.screenshot())
        deadline = time.monotonic() + 3.0
        previous_digest: bytes | None = None
        stable = 0
        swiped = False

        while time.monotonic() < deadline:
            if hasattr(self._scroll_input, 'scroll'):
                self._scroll_input.scroll(0.5, 0.5, vertical=self._scroll_amount, delay=False)
            if not swiped and hasattr(self._device, 'shell'):
                try:
                    x = round(500 * self._device.resolution[0] / 1920)
                    y1 = round(650 * self._device.resolution[1] / 1080)
                    y2 = round(580 * self._device.resolution[1] / 1080)
                    self._device.shell(f'input swipe {x} {y1} {x} {y2} 150')
                    swiped = True
                except Exception:
                    pass
            time.sleep(0.04)

            screen = self.screenshot()
            digest = self._frame_digest(screen)

            if digest == baseline:
                previous_digest = None
                stable = 0
                continue

            if digest == previous_digest:
                stable += 1
                if stable >= 2:
                    return screen
            else:
                previous_digest = digest
                stable = 1

        return self.screenshot()

    @staticmethod
    def _target_list_at_bottom(screen: np.ndarray) -> bool:
        _top, bottom = target_thumb_bounds(screen)
        return bottom >= round(1032 * screen.shape[0] / 1080)

    def target_list_at_bottom(self, screen: np.ndarray) -> bool:
        return self._target_list_at_bottom(screen)


def scan_live_target_inventory(
    device: AdbLosslessMaterialDevice,
    identities: ShipCardRecognizer,
    *,
    scroll_input: TargetScrollInput,
    ocr: OCREngine | None = None,
    max_resolver: TargetMaxResolver | None = None,
    max_scrolls: int = 80,
    allow_unknown: bool = True,
) -> TargetInventorySnapshot:
    """Run a target-only, scrollbar-only scan on the verified Cetus device."""
    device.verify_cetus()
    adapter = CetusTargetScanDevice(device, scroll_input=scroll_input)
    reader = CetusTargetCardReader(identities, ocr, max_resolver, allow_unknown=allow_unknown)
    result = TargetInventoryScanner(adapter, reader).scan_snapshot(max_scrolls=max_scrolls)
    device.verify_cetus()
    return result
