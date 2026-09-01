"""Cetus-calibrated intensify controls and fixed-grid occurrence selection.

Semantic identity remains external. This module only resolves already-authorized
opaque references to calibrated target/material grid positions and verifies every
page transition before another input.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from autowsgr.ui.intensify_workflow import (
    ConfirmationCoordinates,
    IntensifyUiState,
    IntensifyWorkflowError,
    SelectionRef,
    ShipStats,
    VerifiedIntensifyControl,
)
from autowsgr.ui.material_first_intensify import (
    is_intensify_home_screen,
    is_material_selector_screen,
)
from autowsgr.ui.material_inventory_scanner import (
    AdbLosslessMaterialDevice,
    AdbScrollbarStepper,
    has_selected_material,
)


if TYPE_CHECKING:
    import numpy as np

    from autowsgr.ui.target_inventory_scanner import TargetCardReader
    from autowsgr.vision.ocr import OCREngine


_COLUMN_CENTERS = (0.0948, 0.2047, 0.3146, 0.4250, 0.5349, 0.6448, 0.7547)
_ROW_CENTERS = (0.3343, 0.7352)
_HOME_STAT_CROPS = (
    (0.865, 0.145, 0.945, 0.215),
    (0.865, 0.265, 0.945, 0.335),
    (0.865, 0.385, 0.945, 0.455),
    (0.855, 0.505, 0.945, 0.575),
)
_HOME_STAT_PANEL_CROPS = (
    (0.75, 0.140, 0.98, 0.250),  # 火力
    (0.75, 0.260, 0.98, 0.370),  # 鱼雷
    (0.75, 0.380, 0.98, 0.490),  # 装甲
    (0.75, 0.500, 0.98, 0.610),  # 对空
)
_HOME_INTENSIFY_BUTTON_CROP = (0.810, 0.760, 0.940, 0.880)


def is_home_target_fully_maxed(
    screen: np.ndarray,
    max_stats: ShipStats,
    ocr: OCREngine | None = None,
) -> bool:
    """Verify on intensify home screen whether all strengthenable stats are MAX."""
    import cv2
    import numpy as np

    if not is_intensify_home_screen(screen):
        return False
    height, width = screen.shape[:2]
    max_values = (
        max_stats.firepower,
        max_stats.torpedo,
        max_stats.armor,
        max_stats.anti_air,
    )
    for bounds, max_val in zip(_HOME_STAT_PANEL_CROPS, max_values, strict=True):
        if max_val <= 0:
            continue
        x1, y1, x2, y2 = bounds
        crop = screen[int(height * y1) : int(height * y2), int(width * x1) : int(width * x2)]
        hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
        orange = cv2.inRange(hsv, np.array((10, 150, 150)), np.array((30, 255, 255)))
        orange_ratio = (orange > 0).mean()
        if orange_ratio >= 0.08:
            continue
        if ocr is not None:
            results = ocr.recognize(crop)
            text_joined = ' '.join(r.text.upper() for r in results)
            if 'MAX' in text_joined:
                continue
        return False
    return True
_HOME_CURRENT_RE = re.compile(r'^\d{1,3}$')
_HOME_GAIN_RE = re.compile(r'^\+\d{1,3}$')
_HOME_OCR_MIN_CONFIDENCE = 0.50


@dataclass(frozen=True, slots=True)
class IntensifyHomePanelObservation:
    current: ShipStats
    gains: ShipStats
    can_intensify: bool


def _normalized_crop(
    screen: np.ndarray,
    bounds: tuple[float, float, float, float],
) -> np.ndarray:
    x1, y1, x2, y2 = bounds
    height, width = screen.shape[:2]
    return screen[
        round(height * y1) : round(height * y2),
        round(width * x1) : round(width * x2),
    ]


def read_intensify_home_panel(
    screen: np.ndarray,
    ocr: OCREngine,
) -> IntensifyHomePanelObservation:
    """Read the four current-stat and ``+N`` pairs from a verified home screenshot."""
    import cv2
    import numpy as np

    if not is_intensify_home_screen(screen):
        raise IntensifyWorkflowError('当前不是可验证的强化首页')
    rows = [_normalized_crop(screen, bounds) for bounds in _HOME_STAT_CROPS]
    crops = []
    for row in rows:
        current_right = round(row.shape[1] * 0.52)
        gain_left = round(row.shape[1] * 0.48)
        crops.extend((row[:, :current_right], row[:, gain_left:]))
    prepared = [cv2.resize(crop, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC) for crop in crops]
    batches = ocr.recognize_batch(prepared, allowlist='0123456789+')
    if len(batches) != len(prepared):
        raise IntensifyWorkflowError('强化主页属性面板 OCR 返回数量异常')
    pairs: list[tuple[int, int]] = []
    for index, row in enumerate(rows):
        current_results = batches[index * 2]
        gain_results = batches[index * 2 + 1]
        current_text = [result for result in current_results if result.text.strip()]
        gain_text = [result for result in gain_results if result.text.strip()]
        current = [
            result
            for result in current_text
            if _HOME_CURRENT_RE.fullmatch(result.text.strip())
            and result.confidence >= _HOME_OCR_MIN_CONFIDENCE
        ]
        gains = [
            result
            for result in gain_text
            if _HOME_GAIN_RE.fullmatch(result.text.strip())
            and result.confidence >= _HOME_OCR_MIN_CONFIDENCE
        ]
        if len(current) == 1 and len(gains) == 1:
            pairs.append((int(current[0].text), int(gains[0].text[1:])))
            continue
        if len(current) == 1 and not gains:
            pairs.append((int(current[0].text), 0))
            continue
        if current_text and _HOME_CURRENT_RE.fullmatch(current_text[0].text.strip()):
            pairs.append((int(current_text[0].text.strip()), 0))
            continue
        hsv = cv2.cvtColor(row, cv2.COLOR_RGB2HSV)
        blue = cv2.inRange(hsv, np.array((90, 150, 70)), np.array((125, 255, 255)))
        if not current_text and not gain_text and float(np.mean(blue > 0)) < 0.01:
            pairs.append((0, 0))
            continue
        digits = re.findall(r'\d+', ' '.join(r.text for r in current_results))
        if digits:
            pairs.append((int(digits[0]), 0))
            continue
        raise IntensifyWorkflowError('强化主页属性面板存在无法可靠识别的数值')
    current = ShipStats(*(pair[0] for pair in pairs))
    gains = ShipStats(*(pair[1] for pair in pairs))
    button = _normalized_crop(screen, _HOME_INTENSIFY_BUTTON_CROP)
    button_hsv = cv2.cvtColor(button, cv2.COLOR_RGB2HSV)
    blue_button = cv2.inRange(
        button_hsv,
        np.array((90, 100, 100)),
        np.array((125, 255, 255)),
    )
    can_intensify = (
        float(np.mean(blue_button > 0)) >= 0.05
        or float(np.mean(button > 150)) >= 0.08
        or gains != ShipStats()
    )
    return IntensifyHomePanelObservation(current, gains, can_intensify)


class LiveSemanticLedger(Protocol):
    """Recognition library hook for the currently selected semantic transaction."""

    def state(self) -> IntensifyUiState: ...


@dataclass(frozen=True, slots=True)
class GridSelectionRef:
    revision: str
    viewport_steps: int
    row: int
    column: int
    x: float | None = None
    y: float | None = None

    def encode(self, kind: str) -> SelectionRef:
        x = _COLUMN_CENTERS[self.column] if self.x is None else self.x
        y = _ROW_CENTERS[self.row] if self.y is None else self.y
        return SelectionRef(
            f'{kind}:{self.revision}:{self.viewport_steps}:{self.row}:{self.column}:{x:.4f}:{y:.4f}'
        )

    @classmethod
    def parse(cls, ref: SelectionRef, kind: str) -> GridSelectionRef:
        parts = ref.value.split(':')
        if len(parts) != 7 or parts[0] != kind:
            raise IntensifyWorkflowError(f'{kind} 引用格式错误: {ref.value}')
        try:
            result = cls(
                parts[1],
                int(parts[2]),
                int(parts[3]),
                int(parts[4]),
                float(parts[5]),
                float(parts[6]),
            )
        except ValueError as error:
            raise IntensifyWorkflowError(f'{kind} 引用包含无效数字: {ref.value}') from error
        if result.viewport_steps < 0 or result.row not in (0, 1) or not 0 <= result.column < 7:
            raise IntensifyWorkflowError(f'{kind} 引用超出固定网格范围: {ref.value}')
        if (
            result.x is None
            or result.y is None
            or not 0 < result.x < 0.81
            or not 0 < result.y < 0.90
        ):
            raise IntensifyWorkflowError(f'{kind} 引用坐标超出安全卡片区域: {ref.value}')
        return result


class LiveIntensifyStateRecognition:
    """Visual state recognition for the calibrated pages and modal dialog."""

    def __init__(self, device: AdbLosslessMaterialDevice) -> None:
        self._device = device

    def state(self) -> IntensifyUiState:
        screen = self._device.screenshot()
        if is_material_selector_screen(screen):
            return IntensifyUiState.MATERIAL_SELECTOR
        if is_intensify_confirmation(screen):
            return IntensifyUiState.CONFIRMATION
        if is_target_selector(screen):
            return IntensifyUiState.TARGET_SELECTOR
        if is_intensify_home_screen(screen):
            return IntensifyUiState.HOME
        raise IntensifyWorkflowError('无法识别当前强化页面状态')


class FixedTargetOperator:
    """Reach and select one revision-bound target occurrence."""

    def __init__(
        self,
        device: AdbLosslessMaterialDevice,
        revision: str,
        scroll_input: object,
        reader: TargetCardReader,
    ) -> None:
        self._device = device
        self._revision = revision
        from autowsgr.ui.live_target_inventory import CetusTargetScanDevice
        from autowsgr.ui.target_inventory_scanner import TargetInventoryScanner

        self._scanner = TargetInventoryScanner(
            CetusTargetScanDevice(device, scroll_input=scroll_input),
            reader,
        )

    def select(self, ref: SelectionRef) -> None:
        parsed = GridSelectionRef.parse(ref, 'target')
        if parsed.revision != self._revision:
            raise IntensifyWorkflowError('目标引用 revision 已过期')
        if not is_target_selector(self._device.screenshot()):
            raise IntensifyWorkflowError('当前不是目标选择页')
        self._scanner.navigate_to_viewport(parsed.viewport_steps)
        assert parsed.x is not None
        assert parsed.y is not None
        self._device.click(parsed.x, parsed.y)


class FixedMaterialOperator:
    """Reach one recorded material viewport through scrollbar-only safe movement."""

    def __init__(self, device: AdbLosslessMaterialDevice, revision: str) -> None:
        self._device = device
        self._revision = revision
        self._stepper = AdbScrollbarStepper(device)

    def select(self, ref: SelectionRef) -> None:
        parsed = GridSelectionRef.parse(ref, 'material')
        if parsed.revision != self._revision:
            raise IntensifyWorkflowError('素材引用 revision 已过期')
        screen = self._device.screenshot()
        if not is_material_selector_screen(screen) or has_selected_material(screen):
            raise IntensifyWorkflowError('素材选择前页面不安全或已有选择')
        if not self._stepper.is_top(screen):
            raise IntensifyWorkflowError('素材 occurrence 选择必须从列表顶部开始')
        for _step in range(parsed.viewport_steps):
            screen = self._device.screenshot()
            thumb = self._stepper.thumb_bounds(screen)
            self._stepper.advance(thumb_bounds=thumb, screen_height=screen.shape[0])
            time.sleep(0.8)
            moved = self._device.screenshot()
            if not is_material_selector_screen(moved) or has_selected_material(moved):
                raise IntensifyWorkflowError('素材滚动后页面状态不安全')
            if self._stepper.thumb_bounds(moved) == thumb:
                raise IntensifyWorkflowError('素材滚动条没有推进')
        assert parsed.x is not None
        assert parsed.y is not None
        self._device.click(parsed.x, parsed.y)
        time.sleep(0.5)
        if not has_selected_material(self._device.screenshot()):
            raise IntensifyWorkflowError('点击后无法证明素材 occurrence 已选中')


def create_live_intensify_control(
    device: AdbLosslessMaterialDevice,
    recognition: LiveSemanticLedger,
    *,
    scroll_input: object,
    target_reader: TargetCardReader,
    target_revision: str,
    material_revision: str,
) -> VerifiedIntensifyControl:
    """Create the calibrated single-material Cetus UI action adapter."""
    device.verify_cetus()
    return VerifiedIntensifyControl(
        device,
        recognition,
        FixedTargetOperator(device, target_revision, scroll_input, target_reader),
        FixedMaterialOperator(device, material_revision),
        ConfirmationCoordinates(cancel=(0.620, 0.568), confirm=(0.380, 0.568)),
    )


def is_target_selector(screen: object) -> bool:
    """Recognize a target selector with both its controls and card structure."""
    import cv2
    import numpy as np

    image = np.asarray(screen)
    if image.ndim != 3:
        return False
    hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
    height, width = image.shape[:2]
    switch = hsv[
        round(height * 0.17) : round(height * 0.36),
        round(width * 0.84) : round(width * 0.98),
    ]
    bottom_confirm = hsv[
        round(height * 0.84) : round(height * 0.97),
        round(width * 0.84) : round(width * 0.98),
    ]
    blue_switch = cv2.inRange(switch, np.array((90, 100, 100)), np.array((120, 255, 255)))
    blue_confirm = cv2.inRange(
        bottom_confirm,
        np.array((90, 100, 100)),
        np.array((120, 255, 255)),
    )
    controls_match = (
        float(np.mean(blue_switch > 0)) > 0.20 and float(np.mean(blue_confirm > 0)) < 0.20
    )
    if not controls_match:
        return False
    from autowsgr.ui.target_inventory_scanner import detect_complete_target_cards

    return bool(detect_complete_target_cards(image))


def is_intensify_confirmation(screen: object) -> bool:
    """Recognize the calibrated four-star intensify confirmation modal."""
    import cv2
    import numpy as np

    image = np.asarray(screen)
    if image.ndim != 3:
        return False
    hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
    height, width = image.shape[:2]
    header = hsv[
        round(height * 0.24) : round(height * 0.33),
        round(width * 0.29) : round(width * 0.71),
    ]
    confirm = hsv[
        round(height * 0.53) : round(height * 0.61),
        round(width * 0.32) : round(width * 0.44),
    ]
    cancel = hsv[
        round(height * 0.53) : round(height * 0.61),
        round(width * 0.56) : round(width * 0.68),
    ]
    blue_header = cv2.inRange(header, np.array((90, 100, 100)), np.array((120, 255, 255)))
    blue_confirm = cv2.inRange(confirm, np.array((90, 100, 100)), np.array((120, 255, 255)))
    red_cancel = cv2.inRange(cancel, np.array((0, 100, 80)), np.array((10, 255, 255)))
    return (
        float(np.mean(blue_header > 0)) > 0.30
        and float(np.mean(blue_confirm > 0)) > 0.30
        and float(np.mean(red_cancel > 0)) > 0.30
    )
