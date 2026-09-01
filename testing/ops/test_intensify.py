from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import numpy as np
import pytest

from autowsgr.ops import intensify
from autowsgr.ui import intensify_snapshot_scan
from autowsgr.ui.intensify_planner import plan_ordered_intensify_batches
from autowsgr.ui.intensify_workflow import (
    MaterialInventoryObservation,
    MaterialOccurrence,
    SelectionRef,
    ShipStats,
)


if TYPE_CHECKING:
    from collections.abc import Iterator


def _material(index: int, identity: str) -> MaterialOccurrence:
    return MaterialOccurrence(
        SelectionRef(f'material:{index}'),
        identity,
        index,
        ShipStats(armor=1),
    )


def _install_auto_intensify_fakes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    target_selectable: Iterator[bool],
) -> SimpleNamespace:
    materials = tuple(_material(index, identity) for index, identity in enumerate('ABC'))
    inventory = MaterialInventoryObservation(materials, True, 'material-revision')
    targets = tuple(
        SimpleNamespace(
            ship_id=index + 1,
            name=f'目标{index}',
            ref=SelectionRef(f'target:{index}'),
            levels=ShipStats(),
        )
        for index in range(2)
    )
    target_snapshot = SimpleNamespace(targets=targets, total=len(targets))
    material_snapshot = SimpleNamespace(
        total=len(materials),
        ship_ids=tuple(range(11, 11 + len(materials))),
    )

    class FakeDevice:
        def verify_cetus(self) -> None:
            return None

        def shell(self, _command: str) -> None:
            return None

        def click(self, _x: float, _y: float) -> None:
            return None

        def screenshot(self) -> np.ndarray:
            return np.zeros((1080, 1920, 3), dtype=np.uint8)

    class FakeNavigationController:
        def __init__(self, _device: object) -> None:
            return None

        def ensure_intensify_home(self, ctx: object | None = None) -> None:
            return None

    class FakeSnapshotNavigator:
        def __init__(self, _device: object) -> None:
            return None

        def open_target_selector(self) -> None:
            return None

        def close_target_selector(self) -> None:
            return None

        def open_material_selector(self) -> None:
            return None

    def max_resolver(_ship_id: int) -> ShipStats:
        return ShipStats(armor=1)

    panel_results = iter(
        SimpleNamespace(current=stats, can_intensify=True)
        for stats in (ShipStats(), ShipStats(armor=1), ShipStats(), ShipStats(armor=1))
    )

    monkeypatch.setattr(intensify, 'AdbLosslessMaterialDevice', lambda _serial: FakeDevice())
    monkeypatch.setattr(intensify, 'MaterialFirstIntensifyController', FakeNavigationController)
    monkeypatch.setattr(intensify_snapshot_scan, 'IntensifySnapshotNavigator', FakeSnapshotNavigator)
    monkeypatch.setattr(intensify, 'load_default_ship_card_recognizer', object)
    monkeypatch.setattr(
        intensify.TargetStrengthenMaxResolver,
        'from_source',
        lambda _path: max_resolver,
    )
    monkeypatch.setattr(
        intensify.ShipStrengthenDataResolver,
        'from_source',
        lambda _path: SimpleNamespace(
            supply=lambda _sid: ShipStats(armor=1),
            experience_per_level=lambda _sid: 1,
        ),
    )
    monkeypatch.setattr(
        intensify.ShipLibraryRarityResolver,
        'from_manifest',
        lambda _path: SimpleNamespace(ship_type=lambda _ship_id: 'dd'),
    )
    monkeypatch.setattr(
        intensify,
        'scan_intensify_inventory_pair',
        lambda *_args, **_kwargs: (target_snapshot, material_snapshot),
    )
    monkeypatch.setattr(
        intensify,
        'material_inventory_observation',
        lambda *_args: inventory,
    )
    monkeypatch.setattr(intensify, 'is_intensify_home_screen', lambda _screen: next(target_selectable))
    monkeypatch.setattr(intensify, 'read_intensify_home_panel', lambda *_args: next(panel_results))
    monkeypatch.setattr(intensify, 'is_intensify_confirmation', lambda _screen: False)
    monkeypatch.setattr(intensify, 'goto_page', lambda *_args: None)
    monkeypatch.setattr(intensify.time, 'sleep', lambda _seconds: None)

    return SimpleNamespace(
        config=SimpleNamespace(
            emulator=SimpleNamespace(serial='emulator-5554'),
            intensify=SimpleNamespace(
                material_ship_types=['dd'],
                max_materials=4,
                protected_ships=[],
            ),
        ),
        ctrl=SimpleNamespace(),
        ocr=object(),
    )


def test_material_click_steps_use_incremental_scroll_offsets() -> None:
    materials = tuple(_material(index, str(index)) for index in (0, 8, 16, 22))

    assert intensify._material_click_steps(materials) == (
        (0, 0, 0),
        (0, 1, 1),
        (1, 1, 2),
        (1, 1, 1),
    )


def test_remove_consumed_materials_rejects_stale_batch_ref() -> None:
    inventory = MaterialInventoryObservation((_material(0, 'A'),), True, 'revision')
    stale = SimpleNamespace(materials=(_material(1, 'B'),))

    with pytest.raises(RuntimeError, match='revision'):
        intensify._remove_consumed_materials(inventory, stale)


def test_runtime_advancement_removes_only_each_executed_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _install_auto_intensify_fakes(monkeypatch, target_selectable=iter([True] * 6))
    planned_inventories: list[list[str]] = []

    def capture_planning(*args: object, **kwargs: object) -> object:
        inventory = args[1]
        assert isinstance(inventory, MaterialInventoryObservation)
        planned_inventories.append([item.identity for item in inventory.occurrences])
        return plan_ordered_intensify_batches(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(intensify, 'plan_ordered_intensify_batches', capture_planning)

    result = intensify.auto_intensify(ctx, max_batches=2)

    assert result.total_batches == 2
    assert [batch.materials for batch in result.batches] == [['A'], ['B']]
    assert planned_inventories == [['A', 'B', 'C'], ['B', 'C']]


def test_unselectable_target_consumes_nothing_and_next_target_can_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _install_auto_intensify_fakes(
        monkeypatch,
        target_selectable=iter([False, True, True, True]),
    )
    planned_inventories: list[list[str]] = []

    def capture_planning(*args: object, **kwargs: object) -> object:
        inventory = args[1]
        assert isinstance(inventory, MaterialInventoryObservation)
        planned_inventories.append([item.identity for item in inventory.occurrences])
        return plan_ordered_intensify_batches(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(intensify, 'plan_ordered_intensify_batches', capture_planning)

    result = intensify.auto_intensify(ctx, max_batches=1)

    assert result.total_batches == 1
    assert result.batches[0].target_name == '目标1'
    assert result.batches[0].materials == ['A']
    assert planned_inventories == [['A', 'B', 'C'], ['A', 'B', 'C']]
