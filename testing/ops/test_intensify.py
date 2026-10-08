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

        def ensure_intensify_home(self, ctx: object | None = None) -> None:  # noqa: ARG002
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
    monkeypatch.setattr(
        intensify_snapshot_scan, 'IntensifySnapshotNavigator', FakeSnapshotNavigator
    )
    recognized_gpu_modes: list[bool] = []

    def load_recognizer(*, use_gpu: bool) -> object:
        recognized_gpu_modes.append(use_gpu)
        return object()

    monkeypatch.setattr(intensify, 'load_default_ship_card_recognizer', load_recognizer)
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
    monkeypatch.setattr(
        intensify, 'is_intensify_home_screen', lambda _screen: next(target_selectable)
    )
    monkeypatch.setattr(intensify, 'read_intensify_home_panel', lambda *_args: next(panel_results))
    monkeypatch.setattr(intensify, 'is_intensify_confirmation', lambda _screen: False)
    monkeypatch.setattr(intensify, 'goto_page', lambda *_args: None)
    monkeypatch.setattr(intensify.time, 'sleep', lambda _seconds: None)

    context = SimpleNamespace(
        config=SimpleNamespace(
            emulator=SimpleNamespace(serial='emulator-5554'),
            ocr=SimpleNamespace(gpu=True),
            intensify=SimpleNamespace(
                material_ship_types=['dd'],
                max_materials=4,
                protected_ships=[],
            ),
        ),
        ctrl=SimpleNamespace(),
        ocr=object(),
    )
    context._recognized_gpu_modes = recognized_gpu_modes
    return context


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
    monkeypatch.setenv('AUTOWSGR_OCR_GPU_MODE', 'cpu')
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
    assert ctx._recognized_gpu_modes == [False]


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


def test_is_expedition_slot_detects_orange_banner() -> None:
    screen = np.zeros((1080, 1920, 3), dtype=np.uint8)
    assert not intensify.is_expedition_slot(screen, 0, 0)

    # 填充 slot 0, 0 的橙黄色横条区域 (y: 340..375, x: 182-80..182+80)
    screen[340:375, 102:262] = (80, 180, 240)  # BGR 橙黄色
    assert intensify.is_expedition_slot(screen, 0, 0)
    assert not intensify.is_expedition_slot(screen, 0, 1)


def test_auto_intensify_native_workflow_switches_target_when_no_material(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clicks: list[tuple[float, float]] = []

    class FakeNativeDevice:
        def __init__(self) -> None:
            self.step = 0

        def click(self, x: float, y: float) -> None:
            clicks.append((round(x, 4), round(y, 4)))

        def shell(self, _cmd: str) -> None:
            pass

        def screenshot(self) -> np.ndarray:
            return np.zeros((1080, 1920, 3), dtype=np.uint8)

    monkeypatch.setattr(
        'autowsgr.ui.material_first_intensify.is_intensify_home_screen', lambda _s: True
    )
    monkeypatch.setattr('autowsgr.ui.live_intensify.is_target_selector', lambda _s: True)
    monkeypatch.setattr(
        'autowsgr.ui.material_first_intensify.is_material_selector_screen', lambda _s: True
    )
    monkeypatch.setattr(intensify, 'is_expedition_slot', lambda _s, _r, _c: False)

    # 模拟第一次目标缺对空 (无素材)，第二次目标缺火力 (有素材，强化后变满)
    needed_results = iter([{'anti_air'}, {'firepower'}, set()])
    monkeypatch.setattr(
        intensify,
        'get_home_target_needed_stats',
        lambda _s: next(needed_results, set()),
    )
    has_mat_results = iter([False, True])
    monkeypatch.setattr(
        'autowsgr.ui.material_inventory_scanner.has_selected_material',
        lambda _s: next(has_mat_results),
    )
    monkeypatch.setattr('autowsgr.ui.live_intensify.is_intensify_confirmation', lambda _s: False)
    monkeypatch.setattr(intensify, 'goto_page', lambda *_args: None)
    monkeypatch.setattr(intensify.time, 'sleep', lambda _s: None)

    class FakeNavController:
        def __init__(self, _device: object) -> None:
            pass

        def ensure_intensify_home(self, _ctx: object | None = None) -> None:
            pass

    monkeypatch.setattr(intensify, 'MaterialFirstIntensifyController', FakeNavController)

    device = FakeNativeDevice()
    ctx = SimpleNamespace(
        config=SimpleNamespace(emulator=SimpleNamespace(serial='emulator-5558')),
        ctrl=SimpleNamespace(),
    )

    result = intensify.auto_intensify_native(device, ctx, max_batches=1)

    assert result.success is True
    assert result.total_batches == 1
    # 验证确实发生了换目标返回操作 (_CLICK_SELECTOR_BACK = (0.048, 0.088))
    assert (0.048, 0.088) in clicks


def test_auto_intensify_native_skips_target_when_stats_already_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clicks: list[tuple[float, float]] = []

    class FakeNativeDevice:
        def click(self, x: float, y: float) -> None:
            clicks.append((round(x, 4), round(y, 4)))

        def shell(self, _cmd: str) -> None:
            pass

        def screenshot(self) -> np.ndarray:
            return np.zeros((1080, 1920, 3), dtype=np.uint8)

    monkeypatch.setattr(
        'autowsgr.ui.material_first_intensify.is_intensify_home_screen', lambda _s: True
    )
    monkeypatch.setattr('autowsgr.ui.live_intensify.is_target_selector', lambda _s: True)
    monkeypatch.setattr(
        'autowsgr.ui.material_first_intensify.is_material_selector_screen', lambda _s: True
    )
    monkeypatch.setattr(intensify, 'is_expedition_slot', lambda _s, _r, _c: False)

    # 目标1 缺对空 (无素材)，目标2 同样只缺对空 (直接跳过，不用进素材页)，目标3 缺装甲 (有素材，强化后变满)
    needed_results = iter([{'anti_air'}, {'anti_air'}, {'armor'}, set()])
    monkeypatch.setattr(
        intensify,
        'get_home_target_needed_stats',
        lambda _s: next(needed_results, set()),
    )
    has_mat_calls: list[int] = []

    def mock_has_mat(_s: object) -> bool:
        has_mat_calls.append(len(has_mat_calls))
        # 第一次进素材页是目标1，返回 False
        # 第二次进素材页应该是目标3，返回 True
        return len(has_mat_calls) > 1

    monkeypatch.setattr(
        'autowsgr.ui.material_inventory_scanner.has_selected_material',
        mock_has_mat,
    )
    monkeypatch.setattr('autowsgr.ui.live_intensify.is_intensify_confirmation', lambda _s: False)
    monkeypatch.setattr(intensify, 'goto_page', lambda *_args: None)
    monkeypatch.setattr(intensify.time, 'sleep', lambda _s: None)

    class FakeNavController:
        def __init__(self, _device: object) -> None:
            pass

        def ensure_intensify_home(self, _ctx: object | None = None) -> None:
            pass

    monkeypatch.setattr(intensify, 'MaterialFirstIntensifyController', FakeNavController)

    device = FakeNativeDevice()
    ctx = SimpleNamespace(
        config=SimpleNamespace(emulator=SimpleNamespace(serial='emulator-5558')),
        ctrl=SimpleNamespace(),
    )

    result = intensify.auto_intensify_native(device, ctx, max_batches=1)

    assert result.success is True
    assert result.total_batches == 1
    # 关键断言：目标2 由于缺口也是 anti_air (已耗尽)，被直接跳过，素材选择页只被调用了 2 次 (目标1 和 目标3)
    assert len(has_mat_calls) == 2
