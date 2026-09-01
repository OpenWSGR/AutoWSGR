from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from autowsgr.types import ShipType
from autowsgr.ui.material_inventory_scanner import (
    AdbLosslessMaterialDevice,
    AdbScrollbarStepper,
    CapturedMaterialViewport,
    MaterialInventoryScanError,
    MaterialInventoryScanner,
    MaterialViewportReader,
    merge_viewport_identities,
    merge_viewport_names,
    scan_material_inventory_from_main,
)
from autowsgr.vision.ship_card_recognizer import ShipCardIdentity


_LIVE_FIXTURE_ROOT = Path(
    os.environ.get('AUTOWSGR_LIVE_FIXTURE_ROOT', 'testing/fixtures/live-intensify')
)
_FIXTURE_ROOT = _LIVE_FIXTURE_ROOT / 'live-material-rebuild'


def _fixture(name: str) -> np.ndarray:
    path = _FIXTURE_ROOT / name
    if not path.exists():
        pytest.skip(f'local lossless material fixture not available: {path}')
    return cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)


def _material_screen(*, row_columns: tuple[int, ...] = (7, 7)) -> np.ndarray:
    screen = np.zeros((1080, 1920, 3), dtype=np.uint8)
    name_color = (18, 98, 162)
    frame_color = (0, 170, 235)
    row_tops = (520, 952)
    for row, columns in enumerate(row_columns):
        for column in range(columns):
            left = 86 + column * 211
            screen[row_tops[row] : row_tops[row] + 42, left : left + 192] = name_color
            card_top = row_tops[row] + 41 - 405
            screen[card_top : card_top + 4, left : left + 192] = frame_color
    return screen


def _identity(name: str, ship_id: int) -> ShipCardIdentity:
    return ShipCardIdentity(ship_id, name, ShipType.DD, 0.9, f'gallery/{ship_id}.png')


def test_viewport_reader_uses_native_bands_and_one_identity_call() -> None:
    identities = MagicMock()
    identities.recognize.return_value = [
        _identity('霞飞', 1),
        _identity('企业', 2),
        _identity('U-96', 3),
    ]
    locate = MagicMock(return_value=[[346, 374], [634, 662], [663, 664]])
    reader = MaterialViewportReader(identities, locate=locate)

    viewport = reader.read(_material_screen(row_columns=(2, 1)))

    assert viewport.names == ('霞飞', '企业', 'U-96')
    assert viewport.ship_ids == (1, 2, 3)
    assert viewport.row_lengths == (2, 1)
    assert [position[:2] for position in viewport.positions] == [(0, 0), (0, 1), (1, 0)]
    expected_centers = ((0.0948, 0.3319), (0.2047, 0.3319), (0.0948, 0.7319))
    for position, expected in zip(viewport.positions, expected_centers, strict=True):
        assert position[2] == pytest.approx(expected[0], abs=0.0001)
        assert position[3] == pytest.approx(expected[1], abs=0.0001)
    locate.assert_called_once()
    assert locate.call_args.args[0].shape == (720, 1048, 3)
    assert identities.recognize.call_count == 1
    assert [image.shape for image in identities.recognize.call_args.args[0]] == [
        (405, 192, 3),
        (405, 192, 3),
        (405, 192, 3),
    ]


def test_capture_excludes_rows_whose_text_is_clipped_at_vertical_edge() -> None:
    screen = _material_screen(row_columns=(2, 2))
    screen[519:526, 120:170] = 255
    screen[519:526, 331:381] = 255
    screen[970:976, 120:170] = 255
    screen[970:976, 331:381] = 255
    reader = MaterialViewportReader(
        MagicMock(),
        locate=lambda _image: [[346, 374], [634, 662]],
    )

    capture = reader.capture(screen)

    assert capture.row_lengths == (2,)
    assert capture.bands == ((951, 993),)
    assert len(capture.crops) == 2


def test_capture_excludes_top_row_without_a_complete_card_height() -> None:
    screen = np.zeros((1080, 1920, 3), dtype=np.uint8)
    name_color = (18, 98, 162)
    frame_color = (0, 170, 235)
    screen[190:232, 86:278] = name_color
    screen[708:750, 86:278] = name_color
    screen[345:348, 86:278] = frame_color
    reader = MaterialViewportReader(
        MagicMock(),
        locate=lambda _image: [[127, 155], [472, 500]],
    )

    capture = reader.capture(screen)

    assert capture.row_lengths == (1,)
    assert capture.bands == ((708, 750),)
    assert [crop.shape for crop in capture.crops] == [(405, 192, 3)]


def test_capture_excludes_row_without_complete_cyan_card_top() -> None:
    clipped_path = _LIVE_FIXTURE_ROOT / 'intensify-material-identity-failure' / 'crop-57.png'
    complete_path = _LIVE_FIXTURE_ROOT / 'material-selected.png'
    if not clipped_path.exists() or not complete_path.exists():
        pytest.skip('live clipped/complete material fixtures unavailable')
    clipped = cv2.cvtColor(cv2.imread(str(clipped_path)), cv2.COLOR_BGR2RGB)
    complete_screen = cv2.cvtColor(cv2.imread(str(complete_path)), cv2.COLOR_BGR2RGB)
    complete = complete_screen[282:687, 86:278]

    assert not MaterialViewportReader._has_complete_card_top(clipped)
    assert MaterialViewportReader._has_complete_card_top(complete)


def test_viewport_reader_rejects_unrecognized_present_card() -> None:
    identities = MagicMock()
    identities.recognize.return_value = [None]
    reader = MaterialViewportReader(identities, locate=lambda _image: [[346, 374]])

    with pytest.raises(MaterialInventoryScanError, match='拒绝宣称素材库存完整'):
        reader.read(_material_screen(row_columns=(1,)))
    assert len(identities.recognize.call_args.args[0]) == 1


def test_viewport_reader_rejects_empty_identity_among_other_candidates() -> None:
    identities = MagicMock()
    identities.recognize.return_value = [_identity('企业', 1), None, _identity('U-96', 2)]
    reader = MaterialViewportReader(
        identities,
        locate=lambda _image: [[346, 374], [634, 662]],
    )

    with pytest.raises(MaterialInventoryScanError, match='拒绝宣称素材库存完整'):
        reader.read(_material_screen(row_columns=(2, 1)))
    assert identities.recognize.call_count == 1
    assert len(identities.recognize.call_args.args[0]) == 3


def test_real_fixture_native_bands_filter_one_pixel_noise() -> None:
    screen = _fixture('rebuild-top-03.png')
    reader = MaterialViewportReader(MagicMock())

    assert reader.locate_name_bands(screen) == ((276, 316), (708, 748))


def test_native_band_geometry_rejects_overlap_or_excessive_height() -> None:
    screen = _material_screen(row_columns=(1,))
    with pytest.raises(MaterialInventoryScanError, match='几何异常'):
        MaterialViewportReader(MagicMock(), locate=lambda _image: [[100, 150]]).locate_name_bands(
            screen
        )
    with pytest.raises(MaterialInventoryScanError, match='几何异常'):
        MaterialViewportReader(
            MagicMock(),
            locate=lambda _image: [[100, 130], [120, 150]],
        ).locate_name_bands(screen)


def test_overlap_merge_preserves_duplicate_occurrences() -> None:
    accumulated = ('A', 'A', 'B', 'C')
    current = ('B', 'C', 'C', 'D')

    merged, overlap = merge_viewport_names(accumulated, current, minimum_overlap=2)

    assert overlap == 2
    assert merged == ('A', 'A', 'B', 'C', 'C', 'D')


def test_overlap_merge_uses_unique_sorted_name_boundary() -> None:
    merged, overlap = merge_viewport_names(
        ('A', 'A', 'B', 'B'),
        ('A', 'B', 'B', 'C', 'C'),
        minimum_overlap=2,
    )

    assert overlap == 3
    assert merged == ('A', 'A', 'B', 'B', 'C', 'C')


def test_overlap_merge_coalesces_sorted_same_name_group() -> None:
    merged, overlap = merge_viewport_names(
        ('A', 'A', 'A'),
        ('A', 'A', 'B'),
        minimum_overlap=1,
    )

    assert overlap == 2
    assert merged == ('A', 'A', 'A', 'B')


def test_overlap_merge_rejects_name_reappearing_after_merge() -> None:
    with pytest.raises(MaterialInventoryScanError, match='连续分组'):
        merge_viewport_names(('A', 'B'), ('A', 'B', 'A'), minimum_overlap=2)


def test_overlap_merge_appends_disconnected_next_sorted_groups() -> None:
    merged, overlap = merge_viewport_names(('A', 'B'), ('C', 'D'), minimum_overlap=2)

    assert overlap == 0
    assert merged == ('A', 'B', 'C', 'D')


@pytest.mark.parametrize(
    ('thumb_bounds', 'expected_start', 'expected_end'),
    [
        ((130, 420), 275, 286),
        ((400, 620), 510, 521),
        ((850, 1034), 942, 953),
        ((1024, 1034), 1029, 1033),
    ],
)
def test_adb_stepper_only_drags_inside_observed_scrollbar_thumb(
    thumb_bounds: tuple[int, int],
    expected_start: int,
    expected_end: int,
) -> None:
    ctrl = MagicMock()
    ctrl.resolution = (1920, 1080)
    stepper = AdbScrollbarStepper(ctrl, x=1580, step_pixels=11)

    stepper.advance(thumb_bounds=thumb_bounds, screen_height=1080)

    ctrl.shell.assert_called_once_with(f'input swipe 1580 {expected_start} 1580 {expected_end} 300')
    assert thumb_bounds[0] <= expected_start < expected_end < thumb_bounds[1]


def test_adb_stepper_top_and_bottom_detection_do_not_depend_on_thumb_length() -> None:
    stepper = AdbScrollbarStepper(MagicMock())
    screen = np.zeros((1080, 1920, 3), dtype=np.uint8)
    stepper.thumb_bounds = MagicMock(side_effect=[(130, 420), (130, 300), (750, 1034), (900, 1034)])

    assert stepper.is_top(screen)
    assert stepper.is_top(screen)
    assert stepper.is_bottom(screen)
    assert stepper.is_bottom(screen)


@pytest.mark.parametrize('thumb_bounds', [(130, 170), (200, 1000)])
def test_adb_stepper_detects_inventory_sized_synthetic_thumbs(
    thumb_bounds: tuple[int, int],
) -> None:
    screen = np.full((1080, 1920, 3), 70, dtype=np.uint8)
    screen[thumb_bounds[0] : thumb_bounds[1], 1580] = (185, 186, 187)

    assert AdbScrollbarStepper(MagicMock()).thumb_bounds(screen) == thumb_bounds


@pytest.mark.parametrize('screen_size', [(540, 960), (1080, 1920), (2160, 3840)])
def test_adb_stepper_ignores_scale_safe_isolated_track_noise(
    screen_size: tuple[int, int],
) -> None:
    height, width = screen_size
    x = round(1580 * width / 1920)
    thumb_bounds = (round(350 * height / 1080), round(430 * height / 1080))
    noise_y = round(600 * height / 1080)
    screen = np.full((height, width, 3), 70, dtype=np.uint8)
    screen[thumb_bounds[0] : thumb_bounds[1], x] = (185, 186, 187)
    screen[noise_y, x] = (185, 186, 187)

    assert AdbScrollbarStepper(MagicMock()).thumb_bounds(screen) == thumb_bounds


def test_adb_stepper_rejects_multiple_neutral_light_runs_as_ambiguous() -> None:
    screen = np.full((1080, 1920, 3), 70, dtype=np.uint8)
    screen[250:290, 1580] = (185, 186, 187)
    screen[700:750, 1580] = (185, 186, 187)

    with pytest.raises(MaterialInventoryScanError, match='定位不唯一') as error:
        AdbScrollbarStepper(MagicMock()).thumb_bounds(screen)

    assert '(250, 290)' in str(error.value)
    assert '(700, 750)' in str(error.value)


def test_adb_device_accepts_explicit_serial_and_verifies_cetus_identity() -> None:
    adb_device = MagicMock()
    adb_device.shell.side_effect = ['Cetus', 'CET-AL00']
    device = AdbLosslessMaterialDevice('127.0.0.1:16449', adb_device=adb_device)

    device.verify_cetus()

    assert adb_device.shell.call_args_list[0].args == ('getprop ro.product.name',)
    assert adb_device.shell.call_args_list[1].args == ('getprop ro.product.model',)


def test_adb_device_requires_explicit_serial() -> None:
    with pytest.raises(MaterialInventoryScanError, match='显式指定'):
        AdbLosslessMaterialDevice('', adb_device=MagicMock())


@pytest.mark.parametrize(
    ('fixture', 'expected_bottom'),
    [
        ('rebuild-top-04.png', 420),
        ('rebuild-top-03.png', 571),
        ('rebuild-top-02.png', 722),
        ('rebuild-top-01.png', 874),
        ('rebuild-top-00.png', 1025),
        ('rebuild-bottom-scrollbar.png', 1034),
    ],
)
def test_adb_stepper_locates_real_scrollbar_thumb_bottom(
    fixture: str,
    expected_bottom: int,
) -> None:
    screen = _fixture(fixture)

    assert AdbScrollbarStepper(MagicMock()).thumb_bottom(screen) == expected_bottom


def test_scanner_merges_views_and_stops_after_stagnation() -> None:
    ctrl = MagicMock()
    ctrl.screenshot.side_effect = [np.zeros((10, 10, 3), dtype=np.uint8)] * 3
    reader = MagicMock()
    reader.capture.side_effect = [MagicMock(), MagicMock(), MagicMock()]
    reader.recognize_captures.side_effect = lambda captures: [
        MagicMock(
            names=('A', 'B', 'C'),
            ship_ids=(1, 2, 3),
            row_lengths=(3,),
            positions=((0, 0, 0.1, 0.3), (0, 1, 0.2, 0.3), (0, 2, 0.3, 0.3)),
        ),
        MagicMock(
            names=('B', 'C', 'D'),
            ship_ids=(2, 3, 4),
            row_lengths=(2,),
            positions=((0, 0, 0.1, 0.3), (0, 1, 0.2, 0.3), (0, 2, 0.3, 0.3)),
        ),
    ][: len(captures)]
    stepper = MagicMock()
    stepper.thumb_bounds.side_effect = [(10, 100), (110, 200), (110, 200)]
    stepper.is_top.return_value = True
    stepper.is_bottom.side_effect = [False, True, True]
    scanner = MaterialInventoryScanner(
        ctrl,
        reader,
        stepper,
        is_material_screen=lambda _screen: True,
        stagnant_limit=1,
        settle_seconds=0,
    )

    snapshot = scanner.scan(max_viewports=5)

    assert snapshot.names == ('A', 'B', 'C', 'D')
    assert snapshot.total == 4
    assert snapshot.ship_ids == (1, 2, 3, 4)
    assert snapshot.viewport_count == 2
    assert len(snapshot.refs) == snapshot.total
    assert ctrl.screenshot.call_count == 3
    assert reader.capture.call_count == 2
    assert stepper.advance.call_count == 2
    reader.recognize_captures.assert_called_once()


def test_scanner_rejects_same_name_different_id_boundary_as_ambiguous() -> None:
    ctrl = MagicMock()
    ctrl.screenshot.side_effect = [np.zeros((10, 10, 3), dtype=np.uint8)] * 3
    reader = MagicMock()
    reader.capture.side_effect = [MagicMock(), MagicMock(), MagicMock()]
    reader.recognize_captures.return_value = [
        MagicMock(names=('同名',), ship_ids=(1,), positions=((0, 0, 0.1, 0.3),)),
        MagicMock(names=('同名',), ship_ids=(2,), positions=((0, 0, 0.2, 0.3),)),
    ]
    stepper = MagicMock()
    stepper.thumb_bounds.side_effect = [(10, 100), (110, 200), (110, 200)]
    stepper.is_top.return_value = True
    stepper.is_bottom.side_effect = [False, True, True]
    scanner = MaterialInventoryScanner(
        ctrl,
        reader,
        stepper,
        is_material_screen=lambda _screen: True,
        stagnant_limit=1,
        settle_seconds=0,
    )

    with pytest.raises(MaterialInventoryScanError, match='规范身份'):
        scanner.scan(max_viewports=5)


def test_scanner_captures_one_settled_frame_per_viewport() -> None:
    ctrl = MagicMock()
    ctrl.screenshot.return_value = np.zeros((10, 10, 3), dtype=np.uint8)
    reader = MagicMock()
    reader.capture.return_value = MagicMock()
    reader.recognize_captures.return_value = [
        MagicMock(
            names=('A', 'B'),
            ship_ids=(1, 2),
            row_lengths=(2,),
            positions=((0, 0, 0.1, 0.3), (0, 1, 0.2, 0.3)),
        )
    ]
    stepper = MagicMock()
    stepper.thumb_bounds.return_value = (10, 20)
    stepper.is_top.return_value = True
    stepper.is_bottom.return_value = True
    scanner = MaterialInventoryScanner(
        ctrl,
        reader,
        stepper,
        is_material_screen=lambda _screen: True,
        stagnant_limit=1,
        settle_seconds=0,
    )

    scanner.scan(max_viewports=2)

    assert ctrl.screenshot.call_count == 2
    assert reader.capture.call_count == 1


def test_all_captured_viewports_use_one_inventory_identity_call() -> None:
    identities = MagicMock()
    identities.recognize.return_value = [
        _identity('霞飞', 1),
        _identity('企业', 2),
        _identity('企业', 2),
        _identity('U-96', 3),
    ]
    reader = MaterialViewportReader(identities, locate=MagicMock())
    crop = np.zeros((405, 192, 3), dtype=np.uint8)
    captures = (
        CapturedMaterialViewport((crop, crop), (2,), ((1, 2),)),
        CapturedMaterialViewport((crop, crop), (2,), ((3, 4),)),
    )

    viewports = reader.recognize_captures(captures)

    assert [viewport.names for viewport in viewports] == [
        ('霞飞', '企业'),
        ('企业', 'U-96'),
    ]
    assert [viewport.ship_ids for viewport in viewports] == [(1, 2), (2, 3)]
    identities.recognize.assert_called_once()
    assert len(identities.recognize.call_args.args[0]) == 4


def test_material_reference_center_scales_with_capture_height() -> None:
    identities = MagicMock()
    identities.recognize.return_value = [_identity('霞飞', 1)]
    reader = MaterialViewportReader(identities, locate=MagicMock())
    crop = np.zeros((270, 128, 3), dtype=np.uint8)

    viewport = reader.recognize_captures(
        (CapturedMaterialViewport((crop,), (1,), ((346, 374),), screen_height=720),)
    )[0]

    assert viewport.positions[0][3] == pytest.approx((374 - 270 / 2) / 720)


def test_scanner_fails_before_input_when_page_is_unknown() -> None:
    ctrl = MagicMock()
    ctrl.screenshot.return_value = np.zeros((10, 10, 3), dtype=np.uint8)
    stepper = MagicMock()
    scanner = MaterialInventoryScanner(
        ctrl,
        MagicMock(),
        stepper,
        is_material_screen=lambda _screen: False,
    )

    with pytest.raises(MaterialInventoryScanError, match='素材页面状态不安全'):
        scanner.scan()

    stepper.advance.assert_not_called()


def test_scanner_rejects_non_top_initial_viewport() -> None:
    ctrl = MagicMock()
    ctrl.screenshot.return_value = np.zeros((10, 10, 3), dtype=np.uint8)
    stepper = MagicMock()
    stepper.is_top.return_value = False
    scanner = MaterialInventoryScanner(
        ctrl,
        MagicMock(),
        stepper,
        is_material_screen=lambda _screen: True,
        settle_seconds=0,
    )

    with pytest.raises(MaterialInventoryScanError, match='顶部开始'):
        scanner.scan()

    stepper.advance.assert_not_called()


def test_scanner_rejects_stuck_scrollbar_before_bottom() -> None:
    ctrl = MagicMock()
    ctrl.screenshot.return_value = np.zeros((10, 10, 3), dtype=np.uint8)
    reader = MagicMock()
    reader.capture.side_effect = [MagicMock(), MagicMock()]
    reader.recognize_captures.return_value = [
        MagicMock(names=('A', 'B', 'C'), row_lengths=(3,)),
        MagicMock(names=('B', 'C', 'D'), row_lengths=(2,)),
    ]
    stepper = MagicMock()
    stepper.is_top.return_value = True
    stepper.is_bottom.return_value = False
    stepper.thumb_bounds.return_value = (10, 100)
    scanner = MaterialInventoryScanner(
        ctrl,
        reader,
        stepper,
        is_material_screen=lambda _screen: True,
        settle_seconds=0,
    )

    with pytest.raises(MaterialInventoryScanError, match='未到底时没有移动'):
        scanner.scan()


def test_single_name_overlap_coalesces_sorted_boundary_group() -> None:
    merged, overlap = merge_viewport_names(('A', 'B', 'B'), ('B', 'C'), minimum_overlap=1)

    assert overlap == 1
    assert merged == ('A', 'B', 'B', 'C')


def test_authoritative_overlap_rejects_same_name_with_different_ship_id() -> None:
    with pytest.raises(MaterialInventoryScanError, match='无法建立'):
        merge_viewport_identities(
            ((1, '同名舰'), (2, '同名舰')),
            ((3, '同名舰'), (4, '新舰')),
            minimum_overlap=1,
        )


@pytest.mark.parametrize(
    'fixture',
    [
        'rebuild-top-04.png',
        'rebuild-top-03.png',
        'rebuild-bottom-scrollbar.png',
        '../material-live-single-ocr-final.png',
    ],
)
def test_unselected_real_fixtures_are_not_selected(fixture: str) -> None:
    from autowsgr.ui.material_inventory_scanner import has_selected_material

    assert not has_selected_material(_fixture(fixture))


def test_selected_material_badge_is_detected() -> None:
    from autowsgr.ui.material_inventory_scanner import has_selected_material

    screen = _material_screen(row_columns=(1,))
    screen[220:290, 145:215] = (20, 145, 235)

    assert has_selected_material(screen)


def test_large_live_selected_material_badge_is_detected() -> None:
    from autowsgr.ui.material_inventory_scanner import has_selected_material

    assert has_selected_material(_fixture('../live-explicit-dayodo-selected.png'))


def test_live_unselected_material_card_decoration_is_not_a_sequence_badge() -> None:
    from autowsgr.ui.material_inventory_scanner import has_selected_material

    path = _LIVE_FIXTURE_ROOT / 'material-unselected-after-toggle.png'
    if not path.exists():
        pytest.skip(f'live unselected material fixture not available: {path}')
    screen = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)

    assert not has_selected_material(screen)


def test_material_scanner_has_no_sift_or_ship_name_ocr_path() -> None:
    source = (
        Path(__file__).parents[2] / 'autowsgr' / 'ui' / 'material_inventory_scanner.py'
    ).read_text(encoding='utf-8')

    for forbidden in (
        'ShipPortraitLibrary',
        'ship_portrait_matcher',
        'SIFT',
        'SURF',
        'ORB_create',
        'recognize_batch',
        '_normalize_ocr_name',
    ):
        assert forbidden not in source


def test_adb_lossless_device_returns_rgb_and_forwards_shell() -> None:
    adb_device = MagicMock()
    adb_device.screenshot.return_value = MagicMock()
    adb_device.screenshot.return_value.convert.return_value = MagicMock()
    rgb = np.zeros((2, 3, 3), dtype=np.uint8)
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            'autowsgr.ui.material_inventory_scanner.np.asarray',
            lambda _image, dtype: rgb.astype(dtype),
        )
        device = AdbLosslessMaterialDevice('127.0.0.1:16416', adb_device=adb_device)

        assert np.array_equal(device.screenshot(), rgb)
        device.shell('input swipe 1580 200 1580 211 300')

    adb_device.screenshot.assert_called_once_with(error_ok=False)
    adb_device.shell.assert_called_once_with('input swipe 1580 200 1580 211 300')


def test_adb_lossless_device_click_uses_exact_shell_pixels() -> None:
    adb_device = MagicMock()
    adb_device.window_size.return_value = (1920, 1080)
    device = AdbLosslessMaterialDevice('127.0.0.1:16416', adb_device=adb_device)

    device.click(0.5, 0.25, delay=False)

    adb_device.shell.assert_called_once_with('input tap 960 270')


def test_adb_lossless_device_key_event_uses_exact_shell_command() -> None:
    adb_device = MagicMock()
    device = AdbLosslessMaterialDevice('127.0.0.1:16416', adb_device=adb_device)

    device.key_event(4, delay=False)

    adb_device.shell.assert_called_once_with('input keyevent 4')


def test_complete_entry_navigates_then_scans(monkeypatch: pytest.MonkeyPatch) -> None:
    device = MagicMock()
    identities = MagicMock()
    navigation = MagicMock()
    scanner = MagicMock()
    expected = MagicMock()
    scanner.scan.return_value = expected
    monkeypatch.setattr(
        'autowsgr.ui.material_inventory_scanner.MaterialFirstIntensifyController',
        MagicMock(return_value=navigation),
    )
    monkeypatch.setattr(
        'autowsgr.ui.material_inventory_scanner.MaterialViewportReader',
        MagicMock(),
    )
    monkeypatch.setattr(
        'autowsgr.ui.material_inventory_scanner.AdbScrollbarStepper',
        MagicMock(),
    )
    monkeypatch.setattr(
        'autowsgr.ui.material_inventory_scanner.MaterialInventoryScanner',
        MagicMock(return_value=scanner),
    )

    result = scan_material_inventory_from_main(device, identities, max_viewports=12)

    navigation.enter_material_selector_from_main.assert_called_once_with()
    scanner.scan.assert_called_once_with(max_viewports=12)
    assert result is expected
