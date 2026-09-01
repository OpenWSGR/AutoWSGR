"""Application service for creating authoritative read-only intensify scan sessions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol


if TYPE_CHECKING:
    from autowsgr.server.intensify_snapshot_store import (
        IntensifySnapshotSession,
        IntensifySnapshotStore,
    )
    from autowsgr.ui.material_inventory_scanner import MaterialInventorySnapshot
    from autowsgr.ui.target_inventory_scanner import TargetInventorySnapshot


class IntensifyInventoryScan(Protocol):
    def __call__(self) -> tuple[TargetInventorySnapshot, MaterialInventorySnapshot]: ...


class IntensifySnapshotScanError(RuntimeError):
    """Raised when a complete authoritative scan session cannot be created."""


@dataclass(frozen=True, slots=True)
class IntensifySnapshotScanService:
    snapshot_store: IntensifySnapshotStore
    scan_inventory_pair: IntensifyInventoryScan

    def create_session(self) -> IntensifySnapshotSession:
        try:
            targets, materials = self.scan_inventory_pair()
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            raise IntensifySnapshotScanError(
                f'强化双库存扫描失败 ({error})，未创建快照会话'
            ) from error
        try:
            return self.snapshot_store.create(targets, materials)
        except (TypeError, ValueError) as error:
            raise IntensifySnapshotScanError(
                f'强化库存快照无效 ({error})，未创建快照会话'
            ) from error
