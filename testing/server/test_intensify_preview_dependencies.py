from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from autowsgr.server import intensify_preview_dependencies
from autowsgr.server.intensify_preview_dependencies import (
    IntensifyPreviewConfigurationError,
    get_intensify_preview_service,
    get_intensify_snapshot_scan_service,
    get_intensify_snapshot_store,
)


if TYPE_CHECKING:
    from pathlib import Path


def test_snapshot_store_is_process_shared() -> None:
    assert get_intensify_snapshot_store() is get_intensify_snapshot_store()


@pytest.mark.parametrize(
    ('missing_name', 'configured_name'),
    [
        ('AUTOWSGR_STRENGTHEN_DATA', 'AUTOWSGR_SHIP_LIBRARY'),
        ('AUTOWSGR_SHIP_LIBRARY', 'AUTOWSGR_STRENGTHEN_DATA'),
    ],
)
def test_preview_service_requires_both_trusted_environment_paths(
    monkeypatch: pytest.MonkeyPatch,
    missing_name: str,
    configured_name: str,
) -> None:
    monkeypatch.delenv(missing_name, raising=False)
    monkeypatch.setenv(configured_name, 'configured')

    with pytest.raises(IntensifyPreviewConfigurationError, match=missing_name):
        get_intensify_preview_service()


def test_preview_service_uses_exact_strengthen_path_and_library_manifest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    strengthen_path = tmp_path / 'strengthen.json'
    library_root = tmp_path / 'ship-library'
    captured: dict[str, object] = {}

    class FakePreviewService:
        def __init__(self, store: object, strengthen: Path, manifest: Path) -> None:
            captured.update(store=store, strengthen=strengthen, manifest=manifest)

    monkeypatch.setenv('AUTOWSGR_STRENGTHEN_DATA', str(strengthen_path))
    monkeypatch.setenv('AUTOWSGR_SHIP_LIBRARY', str(library_root))
    monkeypatch.setattr(
        intensify_preview_dependencies,
        'IntensifyPreviewService',
        FakePreviewService,
    )

    service = get_intensify_preview_service()

    assert isinstance(service, FakePreviewService)
    assert captured == {
        'store': get_intensify_snapshot_store(),
        'strengthen': strengthen_path,
        'manifest': library_root / 'manifest.json',
    }


def test_preview_service_provider_does_not_read_resources_eagerly(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv('AUTOWSGR_STRENGTHEN_DATA', str(tmp_path / 'missing-strengthen.json'))
    monkeypatch.setenv('AUTOWSGR_SHIP_LIBRARY', str(tmp_path / 'missing-library'))

    service = get_intensify_preview_service()

    assert service is not None


def test_scan_service_requires_context_owned_explicit_serial(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv('AUTOWSGR_STRENGTHEN_DATA', str(tmp_path / 'strengthen.json'))
    monkeypatch.setenv('AUTOWSGR_SHIP_LIBRARY', str(tmp_path / 'ship-library'))
    context = SimpleNamespace(
        config=SimpleNamespace(emulator=SimpleNamespace(serial=None)),
        ctrl=MagicMock(),
        ocr=MagicMock(),
    )

    with pytest.raises(IntensifyPreviewConfigurationError, match=r'emulator\.serial'):
        get_intensify_snapshot_scan_service(context)


def test_scan_service_composes_only_trusted_context_and_environment_inputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    strengthen = tmp_path / 'strengthen.json'
    strengthen.write_text('[]', encoding='utf-8')
    context = SimpleNamespace(
        config=SimpleNamespace(emulator=SimpleNamespace(serial='127.0.0.1:16448')),
        ctrl=MagicMock(),
        ocr=MagicMock(),
    )
    device = MagicMock()
    identities = MagicMock()
    resolver = MagicMock()
    scan_pair = MagicMock(return_value=(MagicMock(), MagicMock()))
    monkeypatch.setenv('AUTOWSGR_STRENGTHEN_DATA', str(strengthen))
    monkeypatch.setenv('AUTOWSGR_SHIP_LIBRARY', str(tmp_path / 'ship-library'))
    monkeypatch.setattr(
        'autowsgr.ui.material_inventory_scanner.AdbLosslessMaterialDevice',
        MagicMock(return_value=device),
    )
    monkeypatch.setattr(
        'autowsgr.vision.ship_card_recognizer.load_default_ship_card_recognizer',
        MagicMock(return_value=identities),
    )
    monkeypatch.setattr(
        'autowsgr.ui.target_strengthen_max.TargetStrengthenMaxResolver.from_source',
        MagicMock(return_value=resolver),
    )
    monkeypatch.setattr(
        'autowsgr.ui.intensify_snapshot_scan.scan_intensify_inventory_pair', scan_pair
    )

    service = get_intensify_snapshot_scan_service(context)
    assert scan_pair.call_count == 0
    service.scan_inventory_pair()

    scan_pair.assert_called_once_with(
        device,
        identities,
        scroll_input=context.ctrl,
        ocr=context.ocr,
        max_resolver=resolver,
    )
