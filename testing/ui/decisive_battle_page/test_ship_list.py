"""用合成卡片布局与通用控件裁剪验证覆盖算法；实机验收独立记录。"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import numpy as np
import pytest

from autowsgr.emulator.frame import CapturedFrame
from autowsgr.image_resources._lazy import load_template
from autowsgr.ui.decisive import ship_list as module
from autowsgr.ui.decisive.ship_list import DecisiveInventoryScanError, DecisiveShipListWalker
from autowsgr.ui.utils.ship_list_geometry import ShipListGeometryReader


if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass
class _Page:
    image: np.ndarray
    hits: list[tuple[str, float, float, float]]


def _page(
    rows: tuple[tuple[str, ...], ...],
    *,
    thumb: tuple[int, int] = (90, 689),
    bands: tuple[tuple[int, int], ...] = ((346, 374), (634, 662)),
    leave: bool = False,
    trailing_partial: bool = False,
    empty_background: bool = False,
) -> _Page:
    image = np.full((720, 1280, 3), 40, dtype=np.uint8)
    if empty_background:
        image[90:690, 56:1031] = (33, 60, 90)
    for x, y, color in (
        (0.8594, 0.1514, (31, 46, 69)),
        (0.8602, 0.3167, (31, 139, 238)),
        (0.8578, 0.5306, (57, 57, 57)),
        (0.8594, 0.6736, (54, 54, 54)),
        (0.8656, 0.8014, (35, 57, 81)),
    ):
        image[int(y * 720), int(x * 1280)] = color
    for name, x, y in (
        ('ship_list_all_ships_720p.png', 1104, 139),
        ('ship_list_all_types_720p.png', 1141, 484),
        *((('ship_list_leave_720p.png', 90, 213),) if leave else ()),
    ):
        template = load_template(f'decisive/{name}', source_resolution=(1280, 720))
        height, width = template.image.shape[:2]
        image[y : y + height, x : x + width] = template.image
    image[90:690, 1053:1056] = (66, 72, 78)
    image[thumb[0] : thumb[1], 1053:1056] = (192, 193, 195)
    hits = []
    columns = ShipListGeometryReader.column_bounds(1280)
    for row, names in enumerate(rows):
        top, bottom = bands[row]
        first_column = 1 if row == 0 and leave else 0
        for column, name in enumerate(names, first_column):
            left, right = columns[column]
            if bottom >= 270:
                image[bottom - 270 : bottom, left:right] = (0, 170, 235)
                image[bottom - 266 : top, left + 2 : right - 2] = (40 + ord(name[0]) % 60, 40, 40)
            image[top:bottom, left:right] = (18, 98, 162)
            hits.append(
                (
                    name,
                    (left + right) / 2 / 1280,
                    (top + bottom) / 2 / 720,
                    (top + bottom) / 2 / 720,
                )
            )
    if trailing_partial:
        left, right = columns[0]
        image[427:674, left:right] = (0, 170, 235)
        image[431:667, left + 2 : right - 2] = 40
        image[667:674, left:right] = (18, 98, 162)
    return _Page(image, hits)


class _Device:
    def __init__(self, pages: list[_Page]) -> None:
        self.pages = pages
        self.index = 0
        self.sequence = 0
        self.swipe = MagicMock(side_effect=self._advance)

    def _advance(self, *_args: object, **_kwargs: object) -> None:
        self.index = min(self.index + 1, len(self.pages) - 1)

    def capture_frame(self) -> CapturedFrame:
        self.sequence += 1
        return CapturedFrame(self.pages[self.index].image, self.sequence, float(self.sequence))


@pytest.fixture
def walker(monkeypatch: pytest.MonkeyPatch) -> Callable[[list[_Page]], DecisiveShipListWalker]:
    elapsed = [0.0]
    monkeypatch.setattr(module.time, 'monotonic', lambda: elapsed[0])
    monkeypatch.setattr(
        module.time, 'sleep', lambda value: elapsed.__setitem__(0, elapsed[0] + value)
    )

    def make(pages: list[_Page]) -> DecisiveShipListWalker:
        ctx = SimpleNamespace(ctrl=_Device(pages), ocr=MagicMock(), stop_event=threading.Event())
        monkeypatch.setattr(
            module,
            'locate_ship_rows',
            lambda _ocr, image, **_kwargs: next(page.hits for page in pages if page.image is image),
        )
        return DecisiveShipListWalker(ctx)

    return make


@pytest.mark.parametrize('rows', [(('甲', '乙'),), (tuple('甲乙丙丁戊己庚'), tuple('辛壬癸'))])
def test_complete_single_viewport_does_not_scroll(walker: Callable, rows: tuple) -> None:
    scan = walker([_page(rows)])

    assert scan.scan() == {name for row in rows for name in row}
    scan._ctrl.swipe.assert_not_called()


@pytest.mark.parametrize('leave', [False, True])
def test_verified_empty_candidates_need_no_ocr_or_scroll(
    walker: Callable, monkeypatch: pytest.MonkeyPatch, leave: bool
) -> None:
    scan = walker([_page((), leave=leave, empty_background=True)])
    read = MagicMock(side_effect=AssertionError('Empty candidates do not need name OCR'))
    monkeypatch.setattr(module, 'locate_ship_rows', read)

    assert scan.scan() == set()
    read.assert_not_called()
    scan._ctrl.swipe.assert_not_called()


def test_missing_bands_without_positive_empty_background_are_not_empty(walker: Callable) -> None:
    scan = walker([_page(())])

    with pytest.raises(DecisiveInventoryScanError):
        scan.scan()


def test_native_missing_all_real_cards_cannot_prove_empty(walker: Callable) -> None:
    scan = walker([_page((('甲',),), empty_background=True)])
    scan._geometry._locate = lambda _image: []

    with pytest.raises(DecisiveInventoryScanError):
        scan.scan()


@pytest.mark.parametrize('top', [670, 680, 685])
def test_partial_card_pixels_in_empty_background_cannot_prove_empty(
    walker: Callable, top: int
) -> None:
    page = _page((), empty_background=True)
    page.image[top : top + 4, 480:608] = (0, 170, 235)
    scan = walker([page])

    with pytest.raises(DecisiveInventoryScanError):
        scan.scan()


def test_empty_candidates_require_a_full_height_scrollbar(walker: Callable) -> None:
    scan = walker([_page((), empty_background=True, thumb=(90, 540))])

    with pytest.raises(DecisiveInventoryScanError):
        scan.scan()
    scan._ctrl.swipe.assert_not_called()


def test_filtered_empty_candidates_are_still_rejected(walker: Callable) -> None:
    page = _page((), leave=True, empty_background=True)
    page.image[484:506, 1141:1190] = 40
    scan = walker([page])

    with pytest.raises(DecisiveInventoryScanError, match='全部舰船且类型为全部'):
        scan.scan()


def test_empty_endpoint_quantization_still_requires_two_distinct_frames(walker: Callable) -> None:
    pages = [
        _page((), empty_background=True, thumb=(90, 688)),
        _page((), empty_background=True, thumb=(90, 689)),
    ]
    scan = walker(pages)

    def capture() -> CapturedFrame:
        scan._ctrl.sequence += 1
        page = pages[min(scan._ctrl.sequence - 1, 1)]
        return CapturedFrame(page.image, scan._ctrl.sequence, float(scan._ctrl.sequence))

    scan._ctrl.capture_frame = capture
    assert scan.scan() == set()
    assert scan._ctrl.sequence == 2


def test_empty_cached_frame_cannot_prove_complete(walker: Callable) -> None:
    page = _page((), empty_background=True)
    scan = walker([page])
    scan._ctrl.capture_frame = lambda: CapturedFrame(page.image, 1, 1.0)

    with pytest.raises(DecisiveInventoryScanError):
        scan.scan()


def test_hidden_fifteenth_card_requires_overlapping_second_viewport(walker: Callable) -> None:
    names = tuple(f'船{index}' for index in range(15))
    scan = walker(
        [
            _page((names[:7], names[7:14]), thumb=(90, 540)),
            _page((names[7:14], names[14:]), thumb=(281, 689)),
        ]
    )

    assert scan.scan() == set(names)
    scan._ctrl.swipe.assert_called_once()


def test_partial_top_hits_do_not_count_and_partial_tail_does_not_finish(walker: Callable) -> None:
    names = tuple(f'船{index}' for index in range(15))
    scan = walker(
        [
            _page((names[:7], names[7:14]), thumb=(90, 540)),
            _page(
                (names[:7], names[7:14]),
                thumb=(261, 689),
                bands=((94, 120), (380, 408)),
                trailing_partial=True,
            ),
            _page((names[7:14], names[14:]), thumb=(281, 689)),
        ]
    )

    viewports = list(scan.viewports())

    assert [len(view.hits) for view in viewports] == [14, 7, 8]
    assert [view.at_bottom for view in viewports] == [False, False, True]
    assert scan._ctrl.swipe.call_count == 2


def test_occupied_slot_leave_control_is_not_a_ship(walker: Callable) -> None:
    names = tuple(f'船{index}' for index in range(9))
    scan = walker([_page((names[:6], names[6:]), leave=True)])

    assert scan.scan() == set(names)
    scan._ctrl.swipe.assert_not_called()


@pytest.mark.parametrize('region', [(1104, 139, 1190, 165), (1141, 484, 1190, 506)])
def test_filtered_list_is_rejected_before_ocr_or_scroll(walker: Callable, region: tuple) -> None:
    page = _page((('甲',),))
    x1, y1, x2, y2 = region
    page.image[y1:y2, x1:x2] = 40
    scan = walker([page])

    with pytest.raises(DecisiveInventoryScanError, match='全部舰船且类型为全部'):
        scan.scan()
    scan._ctrl.swipe.assert_not_called()


def test_missing_card_name_fails_after_three_fresh_attempts(walker: Callable) -> None:
    page = _page((('甲', '乙'),))
    page.hits.pop()
    scan = walker([page])

    with pytest.raises(DecisiveInventoryScanError, match='三次后仍不完整'):
        scan.scan()
    scan._ctrl.swipe.assert_not_called()
    assert scan._ctrl.sequence >= 6


def test_native_and_ocr_omitting_first_row_cannot_publish_only_second_row(walker: Callable) -> None:
    page = _page((tuple('甲乙丙丁戊己庚'), tuple('辛壬癸子丑寅卯')))
    page.hits = page.hits[7:]
    scan = walker([page])
    scan._geometry._locate = lambda _image: [[634, 662]]

    with pytest.raises(DecisiveInventoryScanError, match='未覆盖卡片'):
        scan.scan()
    scan._ctrl.swipe.assert_not_called()


def test_two_names_in_one_card_cannot_hide_a_missing_card(walker: Callable) -> None:
    page = _page((('甲', '乙'),))
    page.hits[1] = ('乙', *page.hits[0][1:])
    scan = walker([page])

    with pytest.raises(DecisiveInventoryScanError, match='一一绑定'):
        scan.scan()


def test_lost_overlap_fails_instead_of_returning_partial_inventory(walker: Callable) -> None:
    scan = walker(
        [
            _page((tuple('甲乙丙丁戊己庚'), tuple('辛壬癸子丑寅卯')), thumb=(90, 540)),
            _page((tuple('辰巳午未申酉戌'),), thumb=(281, 689)),
        ]
    )

    with pytest.raises(DecisiveInventoryScanError, match='丢失完整重叠行'):
        scan.scan()


def test_duplicate_row_identity_cannot_prove_overlap(walker: Callable) -> None:
    repeated = tuple('甲乙丙丁戊己庚')
    scan = walker(
        [
            _page((repeated, repeated), thumb=(90, 540)),
            _page((repeated, ('辛',)), thumb=(281, 689)),
        ]
    )

    with pytest.raises(DecisiveInventoryScanError, match='重复身份歧义'):
        scan.scan()


def test_stuck_non_bottom_list_is_an_error(walker: Callable) -> None:
    scan = walker([_page((('甲',),), thumb=(90, 540))])

    with pytest.raises(DecisiveInventoryScanError, match='滚动没有可观测进度'):
        scan.scan()


def test_scan_rewinds_before_publishing_first_viewport(walker: Callable) -> None:
    names = tuple(f'船{index}' for index in range(15))
    top = _page((names[:7], names[7:14]), thumb=(90, 540))
    bottom = _page((names[7:14], names[14:]), thumb=(281, 689))
    scan = walker([bottom, top, bottom])

    assert scan.scan() == set(names)
    assert scan._ctrl.swipe.call_args_list[0].args[1::2] == (410 / 720, 560 / 720)


def test_stop_before_scan_does_not_capture_or_scroll(walker: Callable) -> None:
    scan = walker([_page((('甲',),))])
    scan._ctx.stop_event.set()

    with pytest.raises(InterruptedError):
        scan.scan()
    assert scan._ctrl.sequence == 0
    scan._ctrl.swipe.assert_not_called()


def test_cached_frame_cannot_be_counted_as_two_observations(walker: Callable) -> None:
    scan = walker([_page((('甲',),))])
    scan._ctrl.capture_frame = lambda: CapturedFrame(scan._ctrl.pages[0].image, 1, 1.0)

    with pytest.raises(DecisiveInventoryScanError, match='两个稳定的独立帧'):
        scan.scan()


def test_scroll_budget_exhaustion_never_returns_partial_names(walker: Callable) -> None:
    rows = tuple(tuple(f'船{row}-{column}' for column in range(7)) for row in range(4))
    scan = walker(
        [
            _page((rows[index], rows[index + 1]), thumb=(90 + index * 20, 540 + index * 20))
            for index in range(3)
        ]
    )
    scan._MAX_SCROLLS = 2

    with pytest.raises(DecisiveInventoryScanError, match='超过 2 次滚动'):
        scan.scan()
    assert scan._ctrl.swipe.call_count == 2


def test_stop_during_final_ocr_cannot_publish_inventory(
    walker: Callable, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = _page((('甲',),))
    scan = walker([page])

    def read(*_args: object, **_kwargs: object) -> list:
        scan._ctx.stop_event.set()
        return page.hits

    monkeypatch.setattr(module, 'locate_ship_rows', read)
    with pytest.raises(InterruptedError):
        scan.scan()
