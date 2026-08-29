from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from autowsgr.types import ShipType
from autowsgr.ui.live_target_inventory import (
    CetusTargetCardReader,
    CetusTargetScanDevice,
    _extract_digit_color,
    _extract_digit_glyph,
    _is_cross,
    _stable_card_hash,
    _topology_digit,
    scan_live_target_inventory,
    target_thumb_bounds,
)
from autowsgr.ui.target_inventory_scanner import (
    CardRect,
    TargetInventoryScanError,
    TargetInventorySnapshot,
)
from autowsgr.vision.ship_card_recognizer import ShipCardIdentity


_ROOT = Path(os.environ.get('AUTOWSGR_LIVE_FIXTURE_ROOT', 'testing/fixtures/live-intensify'))


def test_target_thumb_supports_short_live_thumb() -> None:
    path = _ROOT / 'live-target-selector-current.png'
    if path.exists():
        screen = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
    else:
        screen = np.zeros((1080, 1920, 3), dtype=np.uint8)
        screen[135:260, 1580] = (192, 193, 195)
    assert target_thumb_bounds(screen) == (135, 260)


def test_saved_chitose_stat_glyphs_distinguish_one_cross_zero_and_other() -> None:
    paths = [_ROOT / f'target-strength-tight-{index}.png' for index in range(4)]
    if not all(path.exists() for path in paths):
        pytest.skip(f'live Chitose stat fixtures unavailable under {_ROOT}')
    crops = [cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB) for path in paths]
    assert _topology_digit(crops[0]) == 1
    assert _is_cross(crops[1])
    assert _topology_digit(crops[2]) is None
    assert _topology_digit(crops[3]) == 8
    assert _extract_digit_color(crops[0]) is not None
    assert _extract_digit_color(crops[2]) is not None
    assert _extract_digit_glyph(crops[2]) is not None
    assert _extract_digit_glyph(crops[3]) is not None


def test_saved_oyodo_armor_cross_is_recognized() -> None:
    path = _ROOT / 'intensify-target-stat-failure' / 'stat-2.png'
    if not path.exists():
        pytest.skip(f'live Oyodo armor fixture unavailable: {path}')
    crop = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)

    assert _is_cross(crop)


def test_saved_multi_digit_and_eight_glyphs_do_not_collapse_to_zero() -> None:
    paths = [_ROOT / f'target-1509-stat-{index}.png' for index in range(4)]
    if not all(path.exists() for path in paths):
        pytest.skip(f'live multi-digit fixtures unavailable under {_ROOT}')
    crops = [cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB) for path in paths]

    assert _topology_digit(crops[0]) is None
    assert _topology_digit(crops[2]) is None
    assert _topology_digit(crops[3]) == 8


def test_stable_card_hash_excludes_scrolling_name_ticker() -> None:
    paths = [_ROOT / 'target-354-top.png', _ROOT / 'target-354-bottom.png']
    if not all(path.exists() for path in paths):
        pytest.skip(f'live target hash fixtures unavailable under {_ROOT}')
    cards = [cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB) for path in paths]

    assert _stable_card_hash(cards[0]) == _stable_card_hash(cards[1])


def test_numeric_stat_may_exceed_maximum_after_overflow(monkeypatch: pytest.MonkeyPatch) -> None:
    reader = CetusTargetCardReader(SimpleNamespace(), SimpleNamespace())
    reader.ocr.recognize_number = MagicMock(return_value=31)
    monkeypatch.setattr(
        'autowsgr.ui.live_target_inventory._extract_digit_color',
        lambda _crop: np.zeros((20, 20, 3), dtype=np.uint8),
    )
    monkeypatch.setattr('autowsgr.ui.live_target_inventory._is_cross', lambda _crop: False)
    monkeypatch.setattr('autowsgr.ui.live_target_inventory._is_max', lambda _crop: False)
    monkeypatch.setattr('autowsgr.ui.live_target_inventory._topology_digit', lambda _crop: None)

    assert reader._read_stat(np.zeros((100, 40, 3), dtype=np.uint8), maximum=30) == 31


class _NoIdentities:
    def recognize(self, images: list[np.ndarray]) -> list[None]:
        return [None] * len(images)


class _RecordingIdentities:
    def __init__(self, results: list[ShipCardIdentity | None]) -> None:
        self.results = results
        self.images: list[np.ndarray] = []

    def recognize(self, images: list[np.ndarray]) -> list[ShipCardIdentity | None]:
        self.images = images
        return self.results


class _FallbackOcr:
    def __init__(self) -> None:
        self.values = iter((3, 8))
        self.ship_name_candidates: list[str] | None = None

    def recognize_number(self, _image: np.ndarray) -> int:
        return next(self.values)

    def recognize_ship_name(self, _image: np.ndarray, candidates: list[str] | None = None) -> str:
        self.ship_name_candidates = candidates
        return '约克'


class _NamedPortraits:
    def __init__(self) -> None:
        self.calls: list[tuple[np.ndarray, str]] = []
        self.search_names = ['约克', '阿尔汉格尔斯克']

    def identify(self, image: np.ndarray, name: str) -> object:
        self.calls.append((image, name))
        return SimpleNamespace(
            record=SimpleNamespace(
                ship_id=1238,
                name='约克',
                ship_type=ShipType.CA,
                portrait_path=Path('1238.webp'),
            ),
            ratio=0.03,
        )


def test_reader_recovers_saved_chitose_strength_vector() -> None:
    paths = [_ROOT / f'target-strength-tight-{index}.png' for index in range(4)]
    if not all(path.exists() for path in paths):
        pytest.skip(f'live Chitose vector fixtures unavailable under {_ROOT}')
    reader = CetusTargetCardReader(_NoIdentities(), _FallbackOcr())
    crops = [cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB) for path in paths]
    values = [
        reader._read_stat(crop, maximum)
        for crop, maximum in zip(crops, (20, 0, 20, 30), strict=True)
    ]
    assert values == [1, 0, 3, 8]


def test_reader_resolves_max_from_canonical_identity() -> None:
    crop = np.zeros((40, 40, 3), dtype=np.uint8)
    crop[10:30, 10:30] = cv2.cvtColor(
        np.uint8([[[15, 230, 230]]]),
        cv2.COLOR_HSV2RGB,
    )[0, 0]
    reader = CetusTargetCardReader(
        _NoIdentities(),
        max_resolver=lambda _ship_id: __import__(
            'autowsgr.ui.intensify_workflow', fromlist=['ShipStats']
        ).ShipStats(20, 0, 20, 30),
    )
    assert reader._read_stat(crop, 20) == 20
    assert reader._read_stat(np.zeros_like(crop), 0) == 0


def test_reader_submits_every_complete_target_card_in_one_batch() -> None:
    screen = np.arange(500 * 800 * 3, dtype=np.uint8).reshape((500, 800, 3))
    cards = (CardRect(10, 20, 202, 425), CardRect(220, 20, 412, 425))
    identities = _RecordingIdentities(
        [
            ShipCardIdentity(1, '甲', ShipType.DD, 0.8, '1.png'),
            ShipCardIdentity(2, '乙', ShipType.DD, 0.7, '2.png'),
        ]
    )

    results = CetusTargetCardReader(identities).identify_all(screen, cards)

    assert len(results) == 2
    assert len(identities.images) == 2
    assert np.array_equal(identities.images[0], screen[20:425, 10:202])
    assert np.array_equal(identities.images[1], screen[20:425, 220:412])


def test_reader_fails_closed_when_target_identity_result_is_empty() -> None:
    screen = np.zeros((500, 800, 3), dtype=np.uint8)
    cards = (CardRect(10, 20, 202, 425), CardRect(220, 20, 412, 425))
    identities = _RecordingIdentities([ShipCardIdentity(1, '甲', ShipType.DD, 0.8, '1.png'), None])

    with pytest.raises(TargetInventoryScanError, match='未识别完整卡片'):
        CetusTargetCardReader(identities).identify_all(screen, cards)

    assert len(identities.images) == 2


def test_reader_never_uses_ocr_or_portrait_for_failed_identity() -> None:
    screen = np.zeros((500, 800, 3), dtype=np.uint8)
    cards = (CardRect(10, 20, 202, 425), CardRect(220, 20, 412, 425))
    identities = _RecordingIdentities([ShipCardIdentity(1, '甲', ShipType.DD, 0.8, '1.png'), None])
    portraits = _NamedPortraits()

    ocr = _FallbackOcr()
    with pytest.raises(TargetInventoryScanError, match='未识别完整卡片'):
        CetusTargetCardReader(
            identities,
            ocr=ocr,
        ).identify_all(screen, cards)

    assert portraits.calls == []
    assert ocr.ship_name_candidates is None


def test_target_scan_device_returns_exact_frame_after_one_scroll_quantum() -> None:
    device = SimpleNamespace(
        screenshot=lambda: np.zeros((1080, 1920, 3), dtype=np.uint8),
        resolution=(1920, 1080),
    )
    scroll = SimpleNamespace(scroll=MagicMock())
    adapter = CetusTargetScanDevice(
        device,
        scroll_input=scroll,
        scroll_amount=-0.25,
    )
    baseline = np.zeros((10, 10, 3), dtype=np.uint8)
    screen = np.full((10, 10, 3), 7, dtype=np.uint8)
    adapter.screenshot = MagicMock(side_effect=(baseline, screen.copy(), screen.copy()))

    result = adapter.advance_target_list()

    assert np.array_equal(result, screen)
    assert scroll.scroll.call_count >= 1
    scroll.scroll.assert_any_call(
        0.5,
        0.5,
        vertical=-0.25,
        delay=False,
    )
    assert adapter.screenshot.call_count == 3


def test_target_scan_device_waits_for_delayed_content_movement() -> None:
    device = SimpleNamespace(
        screenshot=lambda: np.zeros((1080, 1920, 3), dtype=np.uint8),
        resolution=(1920, 1080),
    )
    scroll = SimpleNamespace(scroll=MagicMock())
    adapter = CetusTargetScanDevice(device, scroll_input=scroll, scroll_amount=-0.25)
    unchanged = np.zeros((10, 10, 3), dtype=np.uint8)
    moved = np.ones((10, 10, 3), dtype=np.uint8)
    adapter.screenshot = MagicMock(
        side_effect=(
            unchanged.copy(),
            unchanged.copy(),
            unchanged.copy(),
            moved.copy(),
            moved.copy(),
        )
    )

    result = adapter.advance_target_list()

    assert np.array_equal(result, moved)
    assert adapter.screenshot.call_count == 5


def test_live_target_scan_returns_formal_snapshot_after_reverifying_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    device = SimpleNamespace(verify_cetus=MagicMock())
    identities = SimpleNamespace()
    scroll_input = SimpleNamespace()
    snapshot = MagicMock(spec=TargetInventorySnapshot)
    scanner = MagicMock()
    scanner.scan_snapshot.return_value = snapshot
    scanner_type = MagicMock(return_value=scanner)
    monkeypatch.setattr('autowsgr.ui.live_target_inventory.CetusTargetScanDevice', MagicMock())
    monkeypatch.setattr('autowsgr.ui.live_target_inventory.CetusTargetCardReader', MagicMock())
    monkeypatch.setattr('autowsgr.ui.live_target_inventory.TargetInventoryScanner', scanner_type)

    result = scan_live_target_inventory(
        device,
        identities,
        scroll_input=scroll_input,
        max_scrolls=17,
    )

    assert result is snapshot
    assert device.verify_cetus.call_count == 2
    scanner.scan_snapshot.assert_called_once_with(max_scrolls=17)
