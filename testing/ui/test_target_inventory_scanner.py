from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from autowsgr.types import ShipType
from autowsgr.ui.intensify_workflow import SelectionRef, ShipStats
from autowsgr.ui.target_inventory_scanner import (
    TARGET_LOGICAL_VIEWPORT_MAX_PHYSICAL_INPUTS,
    CardRect,
    TargetCardIdentity,
    TargetInventoryScanError,
    TargetInventoryScanner,
    TargetInventorySnapshot,
    TargetShipSnapshot,
    assign_target_occurrences,
    detect_complete_target_cards,
    merge_overlapping_target_pages,
    target_viewport_rows,
)


def _snapshot(
    ship_id: int,
    visual_hash: int = 0,
    *,
    name: str = '舰',
    row: int = 0,
    column: int = 0,
) -> TargetShipSnapshot:
    top = 10 + row * 220
    left = 10 + column * 120
    return TargetShipSnapshot(
        ref=SelectionRef('pending'),
        ship_id=ship_id,
        name=name,
        ship_type=ShipType.DD,
        levels=ShipStats(),
        card=CardRect(left, top, left + 100, top + 200),
        visual_hash=visual_hash,
        identity_confidence=0.9,
        identity_match_key='gallery/ship.png',
    )


def _rows(*rows: tuple[int, ...]) -> list[TargetShipSnapshot]:
    return [
        _snapshot(ship_id, ship_id, row=row_index, column=column)
        for row_index, row in enumerate(rows)
        for column, ship_id in enumerate(row)
    ]


def _cards(items: list[TargetShipSnapshot]) -> tuple[CardRect, ...]:
    return tuple(item.card for item in items)


def test_detects_complete_cards_and_excludes_clipped_card() -> None:
    screen = np.zeros((1000, 1600, 3), dtype=np.uint8)
    cyan = cv2.cvtColor(np.uint8([[[104, 230, 230]]]), cv2.COLOR_HSV2RGB)[0, 0].tolist()
    cv2.rectangle(screen, (80, 100), (239, 473), cyan, 4)
    cv2.rectangle(screen, (280, 100), (439, 473), cyan, 4)
    cv2.rectangle(screen, (80, 750), (239, 999), cyan, 4)
    boxes = detect_complete_target_cards(screen)
    assert len(boxes) == 2
    assert [box.left for box in boxes] == [78, 278]


def test_excludes_slightly_clipped_1080p_card() -> None:
    screen = np.zeros((1080, 1920, 3), dtype=np.uint8)
    cyan = cv2.cvtColor(np.uint8([[[104, 230, 230]]]), cv2.COLOR_HSV2RGB)[0, 0].tolist()
    cv2.rectangle(screen, (86, 190), (277, 594), cyan, 1)
    cv2.rectangle(screen, (931, 622), (1122, 1010), cyan, 1)

    boxes = detect_complete_target_cards(screen)

    assert boxes == (CardRect(86, 190, 278, 595),)


def test_merge_uses_identity_and_portrait_not_levels() -> None:
    old = [_snapshot(1, 1), _snapshot(2, 2)]
    changed = [_snapshot(2, 2), _snapshot(3, 3)]
    changed[0] = replace(changed[0], levels=ShipStats(firepower=9))
    assert [item.ship_id for item in merge_overlapping_target_pages(old, changed)] == [1, 2, 3]


def test_merge_rejects_missing_or_ambiguous_overlap() -> None:
    with pytest.raises(TargetInventoryScanError, match='无法建立'):
        merge_overlapping_target_pages([_snapshot(1)], [_snapshot(2)])
    with pytest.raises(TargetInventoryScanError, match='歧义'):
        merge_overlapping_target_pages(
            [_snapshot(1), _snapshot(2), _snapshot(1), _snapshot(2)],
            [_snapshot(1), _snapshot(2)],
        )


def test_occurrences_preserve_duplicate_targets() -> None:
    positioned = assign_target_occurrences([_snapshot(7), _snapshot(7), _snapshot(8)])
    assert all(item.ref.value.startswith('target:') for item in positioned)
    assert all(len(item.ref.value.split(':')) == 7 for item in positioned)
    assert len({item.ref.value for item in positioned}) == 3
    assert [item.global_index for item in positioned] == [0, 1, 2]


def test_occurrence_refs_normalize_with_actual_screen_dimensions() -> None:
    card = replace(_snapshot(7), card=CardRect(100, 50, 300, 250))

    positioned = assign_target_occurrences(
        [card],
        screen_width=800,
        screen_height=400,
    )

    assert positioned[0].ref.value.endswith(':0.2500:0.3750')


def test_target_inventory_snapshot_is_complete_immutable_and_revision_bound() -> None:
    positioned = tuple(assign_target_occurrences([_snapshot(7), _snapshot(7), _snapshot(8)]))
    revision = positioned[0].ref.value.split(':')[1]

    snapshot = TargetInventorySnapshot(
        targets=positioned,
        total=3,
        complete=True,
        revision=revision,
    )

    assert snapshot.targets is positioned
    assert [item.occurrence for item in snapshot.targets] == [0, 1, 0]
    with pytest.raises(FrozenInstanceError):
        snapshot.total = 4  # type: ignore[misc]


@pytest.mark.parametrize(
    ('targets', 'total', 'complete', 'revision', 'message'),
    [
        ((), 0, False, 'revision', '完整'),
        ((), 1, True, 'revision', '不能为空'),
        ((), 0, True, '', 'revision'),
    ],
)
def test_target_inventory_snapshot_rejects_invalid_aggregate(
    targets: tuple[TargetShipSnapshot, ...],
    total: int,
    complete: bool,
    revision: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        TargetInventorySnapshot(targets, total, complete, revision)


def test_target_inventory_snapshot_rejects_mixed_or_duplicate_refs() -> None:
    positioned = tuple(assign_target_occurrences([_snapshot(7), _snapshot(8)]))
    revision = positioned[0].ref.value.split(':')[1]
    mixed = replace(
        positioned[1], ref=SelectionRef(positioned[1].ref.value.replace(revision, 'other'))
    )

    with pytest.raises(ValueError, match='多个 revision'):
        TargetInventorySnapshot((positioned[0], mixed), 2, True, revision)
    duplicate_ref = replace(positioned[1], ref=positioned[0].ref)
    with pytest.raises(ValueError, match='引用必须唯一'):
        TargetInventorySnapshot((positioned[0], duplicate_ref), 2, True, revision)


class _Reader:
    def identify_all(
        self,
        _screen: np.ndarray,
        cards: tuple[CardRect, ...],
    ) -> tuple[TargetCardIdentity, ...]:
        return tuple(
            TargetCardIdentity(1, '舰', ShipType.DD, 1, 0.9, 'gallery/ship.png')
            for card in cards
            if card.left <= 250
        )

    def read_levels(
        self,
        _screen: np.ndarray,
        _card: CardRect,
        _identity: TargetCardIdentity,
    ) -> ShipStats | None:
        return ShipStats()


class _ScanDevice:
    def __init__(self, screens: list[np.ndarray], *, at_bottom: bool) -> None:
        self._screens = iter(screens)
        self._at_bottom = at_bottom

    def screenshot(self) -> np.ndarray:
        return next(self._screens)

    def rewind_target_list(self) -> None:
        pass

    def advance_target_list(self) -> np.ndarray:
        return next(self._screens)

    def target_list_at_bottom(self, _screen: np.ndarray) -> bool:
        return self._at_bottom


def test_viewport_fails_when_any_complete_card_is_unidentified() -> None:
    screen = np.zeros((1000, 1600, 3), dtype=np.uint8)
    cyan = cv2.cvtColor(np.uint8([[[104, 230, 230]]]), cv2.COLOR_HSV2RGB)[0, 0].tolist()
    cv2.rectangle(screen, (80, 100), (239, 473), cyan, 4)
    cv2.rectangle(screen, (280, 100), (439, 473), cyan, 4)
    scanner = TargetInventoryScanner(object(), _Reader(), settle_seconds=0)
    with pytest.raises(TargetInventoryScanError, match='未识别完整卡片'):
        scanner.read_viewport(screen, scan_step=0)


def test_viewport_reports_identity_when_strength_levels_fail() -> None:
    screen = np.zeros((1000, 1600, 3), dtype=np.uint8)
    cyan = cv2.cvtColor(np.uint8([[[104, 230, 230]]]), cv2.COLOR_HSV2RGB)[0, 0].tolist()
    cv2.rectangle(screen, (80, 100), (239, 473), cyan, 4)
    reader = _Reader()
    reader.read_levels = MagicMock(return_value=None)
    scanner = TargetInventoryScanner(object(), reader, settle_seconds=0)

    with pytest.raises(
        TargetInventoryScanError,
        match=r'强化属性读取失败.*1/舰/gallery/ship\.png',
    ):
        scanner.read_viewport(screen, scan_step=0)


def test_observe_viewport_never_reads_strength_levels() -> None:
    screen = np.zeros((1000, 1600, 3), dtype=np.uint8)
    cyan = cv2.cvtColor(np.uint8([[[104, 230, 230]]]), cv2.COLOR_HSV2RGB)[0, 0].tolist()
    cv2.rectangle(screen, (80, 100), (239, 473), cyan, 4)
    reader = _Reader()
    reader.read_levels = MagicMock(side_effect=AssertionError('scroll phase must not read levels'))
    scanner = TargetInventoryScanner(object(), reader, settle_seconds=0)

    observed = scanner.observe_viewport(screen, scan_step=3)

    assert len(observed) == 1
    assert observed[0].scan_step == 3
    assert observed[0].levels == ShipStats()
    reader.read_levels.assert_not_called()


def test_scroll_geometry_does_not_call_wsg_ncc_until_complete_card_count_increases() -> None:
    previous = _rows(tuple(range(1, 8)), tuple(range(8, 15)))
    one_row_cards = tuple(item.card for item in _rows(tuple(range(8, 15))))
    two_row_cards = tuple(item.card for item in _rows(tuple(range(8, 15)), tuple(range(15, 22))))
    current = _rows(tuple(range(8, 15)), tuple(range(15, 22)))
    screens = [
        np.zeros((1080, 1920, 3), dtype=np.uint8),
        np.ones((1080, 1920, 3), dtype=np.uint8),
        np.full((1080, 1920, 3), 2, dtype=np.uint8),
    ]
    device = MagicMock()
    device.advance_target_list.side_effect = screens
    device.target_list_at_bottom.return_value = False
    reader = _Reader()
    reader.identify_all = MagicMock(return_value=())
    scanner = TargetInventoryScanner(device, reader, settle_seconds=0)
    scanner.detect_complete_cards = MagicMock(
        side_effect=(one_row_cards, one_row_cards, two_row_cards)
    )
    scanner.observe_new_complete_cards = MagicMock(return_value=(current, 7))

    result, result_screen = scanner.advance_overlapping_viewport(previous, scan_step=1)

    assert result == current
    assert result_screen is screens[-1]
    assert scanner.observe_new_complete_cards.call_count == 1
    assert scanner.observe_new_complete_cards.call_args.args[2] == two_row_cards
    assert device.advance_target_list.call_count == 3


def test_scroll_geometry_never_submits_incomplete_cards_to_wsg_ncc() -> None:
    screen = np.zeros((1000, 1600, 3), dtype=np.uint8)
    cyan = cv2.cvtColor(np.uint8([[[104, 230, 230]]]), cv2.COLOR_HSV2RGB)[0, 0].tolist()
    cv2.rectangle(screen, (80, 100), (239, 473), cyan, 4)
    cv2.rectangle(screen, (80, 750), (239, 999), cyan, 4)
    reader = _Reader()
    reader.identify_all = MagicMock(
        return_value=(TargetCardIdentity(1, '舰', ShipType.DD, 1, 0.9, 'gallery/ship.png'),)
    )
    scanner = TargetInventoryScanner(object(), reader, settle_seconds=0)

    observed = scanner.observe_viewport(screen, scan_step=0)

    assert len(observed) == 1
    submitted_cards = reader.identify_all.call_args.args[1]
    assert submitted_cards == (CardRect(78, 98, 242, 476),)


def test_new_complete_row_only_submits_new_cards_to_wsg_ncc() -> None:
    previous = _rows(tuple(range(1, 8)), tuple(range(8, 15)))
    cards = _cards(_rows(tuple(range(8, 15)), tuple(range(15, 22))))
    reader = _Reader()
    reader.identify_all = MagicMock(
        return_value=tuple(
            TargetCardIdentity(ship_id, f'舰{ship_id}', ShipType.DD, ship_id, 0.9, f'{ship_id}.png')
            for ship_id in range(15, 22)
        )
    )
    scanner = TargetInventoryScanner(object(), reader, settle_seconds=0)
    screen = np.zeros((1080, 1920, 3), dtype=np.uint8)

    current, overlap = scanner.observe_new_complete_cards(
        screen,
        previous,
        cards,
        scan_step=1,
    )

    assert overlap == 7
    assert [item.ship_id for item in current] == list(range(8, 22))
    submitted_cards = reader.identify_all.call_args.args[1]
    assert submitted_cards == cards[7:]
    assert len(submitted_cards) == 7


def test_complete_viewport_reuses_overlap_levels_and_reads_only_new_cards() -> None:
    previous = _rows(tuple(range(1, 8)), tuple(range(8, 15)))
    observed = _rows(tuple(range(8, 15)), tuple(range(15, 22)))
    previous = [replace(item, levels=ShipStats(firepower=item.ship_id)) for item in previous]
    reader = _Reader()
    reader.read_levels = MagicMock(
        side_effect=lambda _screen, _card, identity: ShipStats(firepower=identity.ship_id)
    )
    scanner = TargetInventoryScanner(object(), reader, settle_seconds=0)

    completed = scanner.complete_viewport(
        np.zeros((1080, 1920, 3), dtype=np.uint8),
        observed,
        inherited_prefix=previous[-7:],
    )

    assert [item.levels.firepower for item in completed] == list(range(8, 22))
    assert reader.read_levels.call_count == 7


def test_viewport_rows_preserve_short_final_row() -> None:
    viewport = _rows((1, 2, 3), (4, 5))

    assert [[item.ship_id for item in row] for row in target_viewport_rows(viewport)] == [
        [1, 2, 3],
        [4, 5],
    ]


def test_advance_accepts_previous_lower_row_with_new_complete_content() -> None:
    previous = _rows(tuple(range(1, 8)), tuple(range(8, 15)))
    clipped = _rows(tuple(range(8, 15)))
    current = _rows(tuple(range(8, 15)), tuple(range(15, 22)))
    screens = [np.zeros((1, 1, 3), dtype=np.uint8), np.ones((1, 1, 3), dtype=np.uint8)]
    device = MagicMock()
    device.advance_target_list.side_effect = screens
    device.target_list_at_bottom.return_value = False
    scanner = TargetInventoryScanner(device, _Reader(), settle_seconds=0)
    scanner.detect_complete_cards = MagicMock(side_effect=(_cards(clipped), _cards(current)))
    scanner.observe_new_complete_cards = MagicMock(return_value=(current, 7))

    result, result_screen = scanner.advance_overlapping_viewport(previous, scan_step=1)

    assert result == current
    assert result_screen is screens[-1]
    assert device.advance_target_list.call_count == 2


def test_advance_consumes_initial_no_op_scrolls_before_valid_movement() -> None:
    previous = _rows(tuple(range(1, 8)), tuple(range(8, 15)))
    current = _rows(tuple(range(8, 15)), tuple(range(15, 22)))
    screens = [
        np.zeros((1, 1, 3), dtype=np.uint8),
        np.ones((1, 1, 3), dtype=np.uint8),
        np.full((1, 1, 3), 2, dtype=np.uint8),
    ]
    device = MagicMock()
    device.advance_target_list.side_effect = screens
    device.target_list_at_bottom.return_value = False
    scanner = TargetInventoryScanner(device, _Reader(), settle_seconds=0)
    clipped = _rows(tuple(range(8, 15)))
    scanner.detect_complete_cards = MagicMock(
        side_effect=(_cards(previous), _cards(clipped), _cards(current))
    )
    scanner.observe_new_complete_cards = MagicMock(return_value=(current, 7))

    result, result_screen = scanner.advance_overlapping_viewport(previous, scan_step=1)

    assert result == current
    assert result_screen is screens[-1]
    assert device.advance_target_list.call_count == 3


def test_advance_default_budget_forms_viewport_from_incremental_anchor_progress() -> None:
    previous = _rows(tuple(range(1, 8)), tuple(range(8, 15)))
    anchor = _rows(tuple(range(8, 15)))
    current = _rows(tuple(range(8, 15)), tuple(range(15, 22)))
    screens = [
        np.full((1, 1, 3), attempt % 256, dtype=np.uint8)
        for attempt in range(TARGET_LOGICAL_VIEWPORT_MAX_PHYSICAL_INPUTS)
    ]
    device = MagicMock()
    device.advance_target_list.side_effect = screens
    device.target_list_at_bottom.return_value = False
    scanner = TargetInventoryScanner(device, _Reader(), settle_seconds=0)
    # 前 239 次只有 7 张完整卡，最后一次变为 14 张完整卡
    scanner.detect_complete_cards = MagicMock(
        side_effect=(*(_cards(anchor) for _ in range(TARGET_LOGICAL_VIEWPORT_MAX_PHYSICAL_INPUTS - 1)), _cards(current))
    )
    # 模拟定期触发 WSG-NCC 时返回 anchor 且 top 不断向上移动产生 progress
    def fake_observe(screen, prev, cards, scan_step=1):
        if int(screen[0, 0, 0]) == 7:  # 第 8 次识别时满足 anchor_index == 0
            return (current, 7)
        # 产生一个位置逐渐变小的 anchor 行
        shifted_anchor = [
            TargetShipSnapshot(
                ref=c.ref,
                ship_id=c.ship_id,
                name=c.name,
                ship_type=c.ship_type,
                levels=c.levels,
                card=c.card.__class__(
                    c.card.left,
                    max(10, 480 - int(screen[0, 0, 0]) * 2),
                    c.card.right,
                    max(10, 480 - int(screen[0, 0, 0]) * 2) + 200,
                ),
                visual_hash=c.visual_hash,
                identity_confidence=c.identity_confidence,
                identity_match_key=c.identity_match_key,
            )
            for c in anchor
        ]
        return (shifted_anchor, 0)

    scanner.observe_new_complete_cards = MagicMock(side_effect=fake_observe)

    result, result_screen = scanner.advance_overlapping_viewport(previous, scan_step=1)

    assert result == current
    assert result_screen is not None
    assert device.advance_target_list.call_count >= 1


def test_advance_rejects_wholly_new_two_row_viewport() -> None:
    previous = _rows(tuple(range(1, 8)), tuple(range(8, 15)))
    clipped = _rows(tuple(range(8, 15)))
    current = _rows(tuple(range(15, 22)), tuple(range(22, 29)))
    device = MagicMock()
    device.advance_target_list.side_effect = (
        np.zeros((1, 1, 3), dtype=np.uint8),
        np.ones((1, 1, 3), dtype=np.uint8),
    )
    device.target_list_at_bottom.return_value = False
    scanner = TargetInventoryScanner(device, _Reader(), settle_seconds=0)
    scanner.detect_complete_cards = MagicMock(side_effect=(_cards(clipped), _cards(current)))
    scanner.observe_new_complete_cards = MagicMock(return_value=(current, 7))

    with pytest.raises(TargetInventoryScanError, match='丢失完整锚点行'):
        scanner.advance_overlapping_viewport(previous, scan_step=1)

    assert device.advance_target_list.call_count == 2


def test_intermediate_clipped_observation_does_not_consume_logical_scan_step() -> None:
    previous = _rows(tuple(range(1, 8)), tuple(range(8, 15)))
    clipped = _rows(tuple(range(8, 15)))
    clipped = [replace(item, card=replace(item.card, top=120, bottom=320)) for item in clipped]
    current = _rows(tuple(range(8, 15)), tuple(range(15, 22)))
    screens = [
        np.zeros((1, 1, 3), dtype=np.uint8),
        np.ones((1, 1, 3), dtype=np.uint8),
    ]
    device = MagicMock()
    device.advance_target_list.side_effect = screens
    device.target_list_at_bottom.return_value = False
    scanner = TargetInventoryScanner(device, _Reader(), settle_seconds=0)
    scanner.detect_complete_cards = MagicMock(side_effect=(_cards(clipped), _cards(current)))
    scanner.observe_new_complete_cards = MagicMock(return_value=(current, 7))

    result, _screen = scanner.advance_overlapping_viewport(previous, scan_step=1)

    assert result == current
    assert device.advance_target_list.call_count == 2
    assert {item.scan_step for item in result} == {0}
    assert scanner.observe_new_complete_cards.call_count == 1
    assert scanner.observe_new_complete_cards.call_args.kwargs['scan_step'] == 1


def test_intermediate_two_row_progress_waits_until_anchor_reaches_first_row() -> None:
    previous = _rows(tuple(range(1, 8)), tuple(range(8, 15)))
    clipped = _rows(tuple(range(8, 15)))
    current = _rows(tuple(range(8, 15)), tuple(range(15, 22)))
    screens = [
        np.zeros((1, 1, 3), dtype=np.uint8),
        np.ones((1, 1, 3), dtype=np.uint8),
    ]
    device = MagicMock()
    device.advance_target_list.side_effect = screens
    device.target_list_at_bottom.return_value = False
    scanner = TargetInventoryScanner(device, _Reader(), settle_seconds=0)
    scanner.detect_complete_cards = MagicMock(side_effect=(_cards(clipped), _cards(current)))
    scanner.observe_new_complete_cards = MagicMock(return_value=(current, 7))

    result, result_screen = scanner.advance_overlapping_viewport(previous, scan_step=1)

    assert result == current
    assert result_screen is screens[-1]
    assert device.advance_target_list.call_count == 2


def test_advance_attempt_budget_bounds_physical_scroll_inputs() -> None:
    previous = _rows(tuple(range(1, 8)), tuple(range(8, 15)))
    first_row = _rows(tuple(range(8, 15)))
    first_row = [replace(item, card=replace(item.card, top=120, bottom=320)) for item in first_row]
    device = MagicMock()
    device.advance_target_list.return_value = np.zeros((1, 1, 3), dtype=np.uint8)
    device.target_list_at_bottom.return_value = False
    device.target_list_at_bottom.return_value = False
    scanner = TargetInventoryScanner(device, _Reader(), settle_seconds=0)
    scanner.detect_complete_cards = MagicMock(return_value=_cards(first_row))
    scanner.observe_viewport = MagicMock(return_value=first_row)

    with pytest.raises(TargetInventoryScanError, match='物理滚动尝试次数: 2'):
        scanner.advance_overlapping_viewport(previous, scan_step=1, max_attempts=2)

    assert device.advance_target_list.call_count == 2


def test_advance_rejects_unchanged_non_bottom_viewport() -> None:
    previous = _rows(tuple(range(1, 8)), tuple(range(8, 15)))
    device = MagicMock()
    device.advance_target_list.return_value = np.zeros((1, 1, 3), dtype=np.uint8)
    device.target_list_at_bottom.return_value = False
    scanner = TargetInventoryScanner(device, _Reader(), settle_seconds=0)
    scanner.detect_complete_cards = MagicMock(return_value=_cards(previous))
    scanner.observe_viewport = MagicMock(return_value=previous)

    with pytest.raises(TargetInventoryScanError, match=r'没有产生可观测进度.*3'):
        scanner.advance_overlapping_viewport(previous, scan_step=1, max_attempts=3)

    assert device.advance_target_list.call_count == 3


def test_navigate_to_viewport_reuses_identity_gated_logical_steps() -> None:
    initial = _rows(tuple(range(1, 8)), tuple(range(8, 15)))
    next_viewport = _rows(tuple(range(8, 15)), tuple(range(15, 22)))
    device = MagicMock()
    device.screenshot.return_value = np.zeros((1, 1, 3), dtype=np.uint8)
    scanner = TargetInventoryScanner(device, _Reader(), settle_seconds=0)
    scanner.observe_viewport = MagicMock(return_value=initial)
    scanner.advance_overlapping_viewport = MagicMock(return_value=(next_viewport, object()))

    result = scanner.navigate_to_viewport(1)

    assert result is next_viewport
    scanner.advance_overlapping_viewport.assert_called_once_with(initial, scan_step=1)


def test_scan_snapshot_wraps_only_a_completed_scan() -> None:
    scanner = TargetInventoryScanner(object(), _Reader(), settle_seconds=0)
    scanner.scan_all = MagicMock(
        return_value=assign_target_occurrences([_snapshot(7), _snapshot(8)])
    )

    snapshot = scanner.scan_snapshot(max_scrolls=3)

    assert isinstance(snapshot, TargetInventorySnapshot)
    assert snapshot.complete is True
    assert snapshot.total == 2
    assert isinstance(snapshot.targets, tuple)
    assert snapshot.revision == snapshot.targets[0].ref.value.split(':')[1]
    scanner.scan_all.assert_called_once_with(max_scrolls=3)
