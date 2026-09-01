"""Process-owned dependencies for authoritative read-only intensify previews."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from autowsgr.server.intensify_preview_service import IntensifyPreviewService
from autowsgr.server.intensify_snapshot_scan_service import IntensifySnapshotScanService
from autowsgr.server.intensify_snapshot_store import IntensifySnapshotStore


if TYPE_CHECKING:
    from autowsgr.ui.material_inventory_scanner import MaterialInventorySnapshot
    from autowsgr.ui.target_inventory_scanner import TargetInventorySnapshot


_STRENGTHEN_DATA_ENV = 'AUTOWSGR_STRENGTHEN_DATA'
_SHIP_LIBRARY_ENV = 'AUTOWSGR_SHIP_LIBRARY'


class IntensifyPreviewConfigurationError(RuntimeError):
    """Raised when required trusted process configuration is unavailable."""


_snapshot_store = IntensifySnapshotStore()


def get_intensify_snapshot_store() -> IntensifySnapshotStore:
    """Return the process-wide owner of short-lived authoritative snapshots."""
    return _snapshot_store


def get_intensify_preview_service() -> IntensifyPreviewService:
    """Compose the preview service lazily from trusted process environment paths."""
    strengthen_value = os.getenv(_STRENGTHEN_DATA_ENV, '').strip()
    if not strengthen_value:
        raise IntensifyPreviewConfigurationError(f'未设置 {_STRENGTHEN_DATA_ENV}')
    library_value = os.getenv(_SHIP_LIBRARY_ENV, '').strip()
    if not library_value:
        raise IntensifyPreviewConfigurationError(f'未设置 {_SHIP_LIBRARY_ENV}')
    return IntensifyPreviewService(
        get_intensify_snapshot_store(),
        Path(strengthen_value),
        Path(library_value) / 'manifest.json',
    )


def get_intensify_snapshot_scan_service(context: object) -> IntensifySnapshotScanService:
    """Compose the device-reading scan service only from process and context-owned inputs."""
    strengthen_value = os.getenv(_STRENGTHEN_DATA_ENV, '').strip()
    if not strengthen_value:
        raise IntensifyPreviewConfigurationError(f'未设置 {_STRENGTHEN_DATA_ENV}')
    library_value = os.getenv(_SHIP_LIBRARY_ENV, '').strip()
    if not library_value:
        raise IntensifyPreviewConfigurationError(f'未设置 {_SHIP_LIBRARY_ENV}')

    config = getattr(context, 'config', None)
    emulator = getattr(config, 'emulator', None)
    serial = getattr(emulator, 'serial', None)
    ctrl = getattr(context, 'ctrl', None)
    if not isinstance(serial, str) or not serial.strip():
        if ctrl is not None and hasattr(ctrl, 'serial') and isinstance(ctrl.serial, str) and ctrl.serial.strip():
            serial = ctrl.serial
        else:
            raise IntensifyPreviewConfigurationError('强化库存扫描要求配置明确的 emulator.serial')
    if ctrl is None:
        raise IntensifyPreviewConfigurationError('系统上下文缺少设备控制器')

    def scan() -> tuple[TargetInventorySnapshot, MaterialInventorySnapshot]:
        from autowsgr.ui.intensify_snapshot_scan import scan_intensify_inventory_pair
        from autowsgr.ui.material_inventory_scanner import AdbLosslessMaterialDevice
        from autowsgr.ui.target_strengthen_max import TargetStrengthenMaxResolver
        from autowsgr.vision.ship_card_recognizer import load_default_ship_card_recognizer

        device = AdbLosslessMaterialDevice(serial.strip())
        identities = load_default_ship_card_recognizer()
        max_resolver = TargetStrengthenMaxResolver.from_source(Path(strengthen_value))
        return scan_intensify_inventory_pair(
            device,
            identities,
            scroll_input=ctrl,
            ocr=getattr(context, 'ocr', None),
            max_resolver=max_resolver,
            ctx=context,
        )

    return IntensifySnapshotScanService(get_intensify_snapshot_store(), scan)
