"""Verified read-only navigation and paired inventory scanning for intensify snapshots."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, TypeVar

from autowsgr.ui.intensify_workflow import IntensifyUiState, IntensifyWorkflowError
from autowsgr.ui.live_intensify import LiveIntensifyStateRecognition
from autowsgr.ui.live_target_inventory import scan_live_target_inventory
from autowsgr.ui.material_first_intensify import MaterialFirstIntensifyController
from autowsgr.ui.material_inventory_scanner import scan_material_inventory_from_selector


if TYPE_CHECKING:
    from collections.abc import Callable

    from autowsgr.ui.live_target_inventory import TargetMaxResolver, TargetScrollInput
    from autowsgr.ui.material_inventory_scanner import (
        AdbLosslessMaterialDevice,
        MaterialInventorySnapshot,
    )
    from autowsgr.ui.target_inventory_scanner import TargetInventorySnapshot
    from autowsgr.vision.ocr import OCREngine
    from autowsgr.vision.ship_card_recognizer import ShipCardRecognizer


_ScanResult = TypeVar('_ScanResult')


class IntensifySnapshotNavigationError(RuntimeError):
    """Raised when a read-only selector transition cannot be positively verified."""


class IntensifySnapshotNavigator:
    """Own the minimal HOME/selector transitions used only by paired read-only scans."""

    _TARGET_SLOT = (0.1070, 0.5093)
    _MATERIAL_SLOT = (0.2630, 0.3380)
    _SELECTOR_BACK = (0.022, 0.058)

    def __init__(
        self,
        device: AdbLosslessMaterialDevice,
        *,
        timeout: float = 6.0,
        interval: float = 0.25,
        stable_frames: int = 2,
    ) -> None:
        self._device = device
        self._recognition = LiveIntensifyStateRecognition(device)
        self._timeout = timeout
        self._interval = interval
        self._stable_frames = stable_frames

    def ensure_home(self, ctx: object | None = None) -> None:
        MaterialFirstIntensifyController(
            self._device,
            timeout=self._timeout,
            interval=self._interval,
            stable_frames=self._stable_frames,
        ).ensure_intensify_home(ctx=ctx)

    def open_target_selector(self) -> None:
        self._transition_from_home(self._TARGET_SLOT, IntensifyUiState.TARGET_SELECTOR)

    def close_target_selector(self) -> None:
        self._close_selector(IntensifyUiState.TARGET_SELECTOR)

    def open_material_selector(self) -> None:
        self._transition_from_home(self._MATERIAL_SLOT, IntensifyUiState.MATERIAL_SELECTOR)

    def close_material_selector(self) -> None:
        self._close_selector(IntensifyUiState.MATERIAL_SELECTOR)

    def _transition_from_home(
        self,
        coordinate: tuple[float, float],
        expected: IntensifyUiState,
    ) -> None:
        self._require(IntensifyUiState.HOME)
        self._device.click(*coordinate)
        self._wait(expected)

    def _close_selector(self, expected: IntensifyUiState) -> None:
        self._require(expected)
        self._device.click(*self._SELECTOR_BACK)
        self._wait(IntensifyUiState.HOME)

    def _require(self, expected: IntensifyUiState) -> None:
        try:
            self._wait(expected)
        except IntensifySnapshotNavigationError as error:
            raise IntensifySnapshotNavigationError(f'强化扫描页面状态不是 {expected}') from error

    def _wait(self, expected: IntensifyUiState) -> None:
        deadline = time.monotonic() + self._timeout
        stable = 0
        while time.monotonic() < deadline:
            try:
                actual = self._recognition.state()
            except IntensifyWorkflowError:
                actual = None
            if actual == expected:
                stable += 1
                if stable >= self._stable_frames:
                    return
            else:
                stable = 0
            time.sleep(self._interval)
        raise IntensifySnapshotNavigationError(f'强化扫描未稳定到达页面: {expected}')


def _scan_and_close_selector(
    scan: Callable[[], _ScanResult],
    close: Callable[[], None],
    *,
    label: str,
) -> _ScanResult:
    """Preserve the scan failure while still reporting a secondary cleanup failure."""
    try:
        result = scan()
    except Exception as scan_error:
        try:
            close()
        except Exception as cleanup_error:
            scan_error.add_note(f'{label}扫描失败后的页面清理也失败: {cleanup_error}')
        raise
    close()
    return result


def scan_intensify_inventory_pair(
    device: AdbLosslessMaterialDevice,
    identities: ShipCardRecognizer,
    *,
    scroll_input: TargetScrollInput,
    ocr: OCREngine | None,
    max_resolver: TargetMaxResolver,
    max_target_scrolls: int = 80,
    max_material_viewports: int = 24,
    ctx: object | None = None,
) -> tuple[TargetInventorySnapshot, MaterialInventorySnapshot]:
    """Create both complete snapshots before returning either to the server store."""
    device.verify_cetus()
    navigator = IntensifySnapshotNavigator(device)
    navigator.ensure_home(ctx=ctx)
    navigator.open_material_selector()
    materials = _scan_and_close_selector(
        lambda: scan_material_inventory_from_selector(
            device,
            identities,
            max_viewports=max_material_viewports,
        ),
        navigator.close_material_selector,
        label='素材库存',
    )
    navigator.open_target_selector()
    targets = _scan_and_close_selector(
        lambda: scan_live_target_inventory(
            device,
            identities,
            scroll_input=scroll_input,
            ocr=ocr,
            max_resolver=max_resolver,
            max_scrolls=max_target_scrolls,
        ),
        navigator.close_target_selector,
        label='目标库存',
    )
    return targets, materials
