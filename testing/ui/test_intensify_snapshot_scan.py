from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from autowsgr.ui import intensify_snapshot_scan
from autowsgr.ui.intensify_snapshot_scan import (
    IntensifySnapshotNavigationError,
    IntensifySnapshotNavigator,
    scan_intensify_inventory_pair,
)
from autowsgr.ui.intensify_workflow import IntensifyUiState


def test_navigator_verifies_each_read_only_selector_transition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    device = MagicMock()
    recognition = MagicMock()
    recognition.state.side_effect = [
        IntensifyUiState.HOME,
        IntensifyUiState.TARGET_SELECTOR,
        IntensifyUiState.TARGET_SELECTOR,
        IntensifyUiState.HOME,
        IntensifyUiState.HOME,
        IntensifyUiState.MATERIAL_SELECTOR,
        IntensifyUiState.MATERIAL_SELECTOR,
        IntensifyUiState.HOME,
    ]
    monkeypatch.setattr(
        intensify_snapshot_scan,
        'LiveIntensifyStateRecognition',
        MagicMock(return_value=recognition),
    )
    navigator = IntensifySnapshotNavigator(device, stable_frames=1, interval=0)

    navigator.open_target_selector()
    navigator.close_target_selector()
    navigator.open_material_selector()
    navigator.close_material_selector()

    assert device.click.call_args_list == [
        call(0.1070, 0.5093),
        call(0.022, 0.058),
        call(0.2630, 0.3380),
        call(0.022, 0.058),
    ]
    device.key_event.assert_not_called()


def test_navigator_fails_before_input_when_starting_state_is_wrong(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    device = MagicMock()
    recognition = MagicMock()
    recognition.state.return_value = IntensifyUiState.MATERIAL_SELECTOR
    monkeypatch.setattr(
        intensify_snapshot_scan,
        'LiveIntensifyStateRecognition',
        MagicMock(return_value=recognition),
    )

    with pytest.raises(IntensifySnapshotNavigationError, match='home'):
        IntensifySnapshotNavigator(device).open_target_selector()

    device.click.assert_not_called()
    device.key_event.assert_not_called()


def test_pair_scan_verifies_device_before_constructing_navigator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    device = MagicMock()
    navigator_type = MagicMock()
    monkeypatch.setattr(intensify_snapshot_scan, 'IntensifySnapshotNavigator', navigator_type)

    device.verify_cetus.side_effect = RuntimeError('wrong device')
    with pytest.raises(RuntimeError, match='wrong device'):
        scan_intensify_inventory_pair(
            device,
            MagicMock(),
            scroll_input=MagicMock(),
            ocr=MagicMock(),
            max_resolver=MagicMock(),
        )

    navigator_type.assert_not_called()
    device.click.assert_not_called()
    device.key_event.assert_not_called()


def test_pair_scan_publishes_nothing_and_orders_both_complete_scans(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    navigator = MagicMock()
    navigator.ensure_home.side_effect = lambda *_args, **_kwargs: events.append('home')
    navigator.open_target_selector.side_effect = lambda *_args, **_kwargs: events.append(
        'open-target'
    )
    navigator.close_target_selector.side_effect = lambda *_args, **_kwargs: events.append(
        'close-target'
    )
    navigator.open_material_selector.side_effect = lambda *_args, **_kwargs: events.append(
        'open-material'
    )
    navigator.close_material_selector.side_effect = lambda *_args, **_kwargs: events.append(
        'close-material'
    )
    targets = MagicMock()
    materials = MagicMock()
    monkeypatch.setattr(
        intensify_snapshot_scan,
        'IntensifySnapshotNavigator',
        MagicMock(return_value=navigator),
    )
    monkeypatch.setattr(
        intensify_snapshot_scan,
        'scan_live_target_inventory',
        MagicMock(side_effect=lambda *_args, **_kwargs: events.append('scan-target') or targets),
    )
    monkeypatch.setattr(
        intensify_snapshot_scan,
        'scan_material_inventory_from_selector',
        MagicMock(
            side_effect=lambda *_args, **_kwargs: events.append('scan-material') or materials
        ),
    )

    result = scan_intensify_inventory_pair(
        MagicMock(),
        MagicMock(),
        scroll_input=MagicMock(),
        ocr=MagicMock(),
        max_resolver=MagicMock(),
    )

    assert result == (targets, materials)
    assert events == [
        'home',
        'open-material',
        'scan-material',
        'close-material',
        'open-target',
        'scan-target',
        'close-target',
    ]
    navigator.ensure_home.assert_called_once_with(ctx=None)


def test_pair_scan_closes_target_selector_after_target_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    navigator = MagicMock()
    monkeypatch.setattr(
        intensify_snapshot_scan,
        'IntensifySnapshotNavigator',
        MagicMock(return_value=navigator),
    )
    monkeypatch.setattr(
        intensify_snapshot_scan,
        'scan_live_target_inventory',
        MagicMock(side_effect=RuntimeError('target failed')),
    )
    monkeypatch.setattr(
        intensify_snapshot_scan,
        'scan_material_inventory_from_selector',
        MagicMock(return_value=MagicMock()),
    )

    with pytest.raises(RuntimeError, match='target failed'):
        scan_intensify_inventory_pair(
            MagicMock(),
            MagicMock(),
            scroll_input=MagicMock(),
            ocr=MagicMock(),
            max_resolver=MagicMock(),
        )

    navigator.close_material_selector.assert_called_once_with()
    navigator.close_target_selector.assert_called_once_with()


def test_pair_scan_preserves_target_failure_when_target_cleanup_also_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    navigator = MagicMock()
    navigator.close_target_selector.side_effect = RuntimeError('target cleanup failed')
    monkeypatch.setattr(
        intensify_snapshot_scan,
        'IntensifySnapshotNavigator',
        MagicMock(return_value=navigator),
    )
    monkeypatch.setattr(
        intensify_snapshot_scan,
        'scan_live_target_inventory',
        MagicMock(side_effect=RuntimeError('target recognition failed')),
    )
    monkeypatch.setattr(
        intensify_snapshot_scan,
        'scan_material_inventory_from_selector',
        MagicMock(return_value=MagicMock()),
    )

    with pytest.raises(RuntimeError, match='target recognition failed') as caught:
        scan_intensify_inventory_pair(
            MagicMock(),
            MagicMock(),
            scroll_input=MagicMock(),
            ocr=MagicMock(),
            max_resolver=MagicMock(),
        )

    assert caught.value.__notes__ == ['目标库存扫描失败后的页面清理也失败: target cleanup failed']
    navigator.close_material_selector.assert_called_once_with()


def test_pair_scan_closes_material_selector_after_material_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    navigator = MagicMock()
    monkeypatch.setattr(
        intensify_snapshot_scan,
        'IntensifySnapshotNavigator',
        MagicMock(return_value=navigator),
    )
    target_scan = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(intensify_snapshot_scan, 'scan_live_target_inventory', target_scan)
    monkeypatch.setattr(
        intensify_snapshot_scan,
        'scan_material_inventory_from_selector',
        MagicMock(side_effect=RuntimeError('material failed')),
    )

    with pytest.raises(RuntimeError, match='material failed'):
        scan_intensify_inventory_pair(
            MagicMock(),
            MagicMock(),
            scroll_input=MagicMock(),
            ocr=MagicMock(),
            max_resolver=MagicMock(),
        )

    navigator.close_material_selector.assert_called_once_with()
    navigator.open_target_selector.assert_not_called()
    target_scan.assert_not_called()


def test_pair_scan_preserves_material_failure_when_material_cleanup_also_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    navigator = MagicMock()
    navigator.close_material_selector.side_effect = RuntimeError('material cleanup failed')
    monkeypatch.setattr(
        intensify_snapshot_scan,
        'IntensifySnapshotNavigator',
        MagicMock(return_value=navigator),
    )
    target_scan = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(intensify_snapshot_scan, 'scan_live_target_inventory', target_scan)
    monkeypatch.setattr(
        intensify_snapshot_scan,
        'scan_material_inventory_from_selector',
        MagicMock(side_effect=RuntimeError('material recognition failed')),
    )

    with pytest.raises(RuntimeError, match='material recognition failed') as caught:
        scan_intensify_inventory_pair(
            MagicMock(),
            MagicMock(),
            scroll_input=MagicMock(),
            ocr=MagicMock(),
            max_resolver=MagicMock(),
        )

    assert caught.value.__notes__ == ['素材库存扫描失败后的页面清理也失败: material cleanup failed']
    navigator.open_target_selector.assert_not_called()
    target_scan.assert_not_called()
