"""Fail-closed full inventory scanning for the intensify target selector."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Protocol

import cv2
import numpy as np

from autowsgr.infra.logger import get_logger
from autowsgr.ui.intensify_workflow import SelectionRef, ShipStats

_log = get_logger('ops.intensify')


if TYPE_CHECKING:
    from autowsgr.types import ShipType


class TargetInventoryScanError(RuntimeError):
    """Raised when the complete target inventory cannot be proven."""


TARGET_LOGICAL_VIEWPORT_MAX_PHYSICAL_INPUTS = 240


@dataclass(frozen=True, slots=True)
class CardRect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def center(self) -> tuple[float, float]:
        return ((self.left + self.right) / 2, (self.top + self.bottom) / 2)


@dataclass(frozen=True, slots=True)
class TargetCardIdentity:
    ship_id: int
    name: str
    ship_type: ShipType
    visual_hash: int
    identity_confidence: float
    identity_match_key: str
    masked: bool = False


@dataclass(frozen=True, slots=True)
class TargetShipSnapshot:
    ref: SelectionRef
    ship_id: int
    name: str
    ship_type: ShipType
    levels: ShipStats
    card: CardRect
    visual_hash: int
    identity_confidence: float
    identity_match_key: str
    scan_step: int = 0
    global_index: int = -1
    occurrence: int = -1
    masked: bool = False


@dataclass(frozen=True, slots=True)
class TargetInventorySnapshot:
    """A proven-complete, revision-bound target inventory."""

    targets: tuple[TargetShipSnapshot, ...]
    total: int
    complete: bool
    revision: str
    acquisition_method: str = 'complete-card-geometry+wsg-ncc+scrcpy-scroll'

    def __post_init__(self) -> None:
        if not self.complete:
            raise ValueError('部分目标库存不能构造完整快照')
        if not self.revision:
            raise ValueError('目标库存 revision 不能为空')
        if not self.targets:
            raise ValueError('目标库存快照不能为空')
        if self.total != len(self.targets):
            raise ValueError('目标库存总数与 occurrence 数量不一致')
        if tuple(item.global_index for item in self.targets) != tuple(range(self.total)):
            raise ValueError('目标库存 global_index 必须连续')
        refs = tuple(item.ref.value for item in self.targets)
        if len(set(refs)) != len(refs):
            raise ValueError('目标库存引用必须唯一')
        revisions: set[str] = set()
        occurrences: dict[int, int] = {}
        for item in self.targets:
            parts = item.ref.value.split(':')
            if len(parts) != 7 or parts[0] != 'target':
                raise ValueError(f'目标库存引用格式错误: {item.ref.value}')
            revisions.add(parts[1])
            expected_occurrence = occurrences.get(item.ship_id, 0)
            if item.occurrence != expected_occurrence:
                raise ValueError('目标库存 occurrence 索引必须连续')
            occurrences[item.ship_id] = expected_occurrence + 1
        if revisions != {self.revision}:
            raise ValueError('目标库存包含多个 revision 或与聚合 revision 不一致')


class TargetCardReader(Protocol):
    def identify_all(
        self,
        screen: np.ndarray,
        cards: tuple[CardRect, ...],
    ) -> tuple[TargetCardIdentity, ...]: ...

    def read_levels(
        self,
        screen: np.ndarray,
        card: CardRect,
        identity: TargetCardIdentity,
    ) -> ShipStats | None: ...


class TargetScanDevice(Protocol):
    def screenshot(self) -> np.ndarray: ...

    def rewind_target_list(self) -> None: ...

    def advance_target_list(self) -> np.ndarray: ...

    def target_list_at_bottom(self, screen: np.ndarray) -> bool: ...


def visual_hash_distance(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def same_target_card(
    left: TargetShipSnapshot,
    right: TargetShipSnapshot,
    *,
    max_hash_distance: int = 6,
) -> bool:
    return (
        left.ship_id == right.ship_id
        and visual_hash_distance(left.visual_hash, right.visual_hash) <= max_hash_distance
    )


def target_page_overlap_size(
    accumulated: list[TargetShipSnapshot],
    current: list[TargetShipSnapshot],
    *,
    max_hash_distance: int = 6,
) -> int:
    """Return the unique longest suffix/prefix overlap between two observations."""
    if not accumulated or not current:
        return 0
    overlaps = [
        size
        for size in range(1, min(len(accumulated), len(current)) + 1)
        if all(
            same_target_card(left, right, max_hash_distance=max_hash_distance)
            for left, right in zip(accumulated[-size:], current[:size], strict=True)
        )
    ]
    if not overlaps:
        raise TargetInventoryScanError('目标舰列表滚动后无法建立可靠重叠')
    longest = max(overlaps)
    # A shorter valid suffix is expected whenever a longer one exists. Ambiguity
    # means the longest sequence itself occurs at more than one accumulated offset.
    signature = current[:longest]
    starts = [
        start
        for start in range(len(accumulated) - longest + 1)
        if all(
            same_target_card(left, right, max_hash_distance=max_hash_distance)
            for left, right in zip(accumulated[start : start + longest], signature, strict=True)
        )
    ]
    if starts != [len(accumulated) - longest]:
        raise TargetInventoryScanError(f'目标舰列表滚动重叠存在歧义: {starts}')
    return longest


def merge_overlapping_target_pages(
    accumulated: list[TargetShipSnapshot],
    current: list[TargetShipSnapshot],
    *,
    max_hash_distance: int = 6,
) -> list[TargetShipSnapshot]:
    """Append only after finding one unique longest suffix/prefix alignment."""
    if not accumulated:
        return list(current)
    overlap = target_page_overlap_size(
        accumulated,
        current,
        max_hash_distance=max_hash_distance,
    )
    return [*accumulated, *current[overlap:]]


def target_viewport_rows(
    viewport: list[TargetShipSnapshot],
) -> tuple[tuple[TargetShipSnapshot, ...], ...]:
    """Group one row-major complete-card viewport without assuming seven columns."""
    if not viewport:
        return ()
    tolerance = max(
        1,
        round(max(item.card.bottom - item.card.top for item in viewport) * 0.08),
    )
    rows: list[list[TargetShipSnapshot]] = []
    row_top: int | None = None
    for item in viewport:
        if row_top is None or abs(item.card.top - row_top) > tolerance:
            rows.append([item])
            row_top = item.card.top
        else:
            rows[-1].append(item)
    return tuple(tuple(row) for row in rows)


def target_card_rows(cards: tuple[CardRect, ...]) -> tuple[tuple[CardRect, ...], ...]:
    """Group complete card rectangles without performing identity recognition."""
    if not cards:
        return ()
    tolerance = max(1, round(max(card.bottom - card.top for card in cards) * 0.08))
    rows: list[list[CardRect]] = []
    row_top: int | None = None
    for card in cards:
        if row_top is None or abs(card.top - row_top) > tolerance:
            rows.append([card])
            row_top = card.top
        else:
            rows[-1].append(card)
    return tuple(tuple(row) for row in rows)


def matching_target_row_index(
    rows: tuple[tuple[TargetShipSnapshot, ...], ...],
    anchor: tuple[TargetShipSnapshot, ...],
) -> int | None:
    """Locate one ordered identity row, rejecting duplicate anchor matches."""
    matches = [
        index
        for index, row in enumerate(rows)
        if len(row) == len(anchor)
        and all(same_target_card(left, right) for left, right in zip(anchor, row, strict=True))
    ]
    if len(matches) > 1:
        raise TargetInventoryScanError(f'目标舰列表完整锚点行存在歧义: {matches}')
    return matches[0] if matches else None


def assign_target_occurrences(
    cards: list[TargetShipSnapshot],
    *,
    screen_width: int = 1920,
    screen_height: int = 1080,
) -> list[TargetShipSnapshot]:
    if screen_width < 1 or screen_height < 1:
        raise ValueError('目标舰截图尺寸必须大于 0')
    revision_payload = '|'.join(
        f'{card.scan_step}:{card.ship_id}:{card.visual_hash}' for card in cards
    )
    revision = hashlib.sha256(revision_payload.encode()).hexdigest()[:16]
    occurrences: dict[int, int] = {}
    result: list[TargetShipSnapshot] = []
    for index, card in enumerate(cards):
        occurrence = occurrences.get(card.ship_id, 0)
        occurrences[card.ship_id] = occurrence + 1
        center_x, center_y = card.card.center
        row = 0 if center_y < screen_height / 2 else 1
        viewport_rows = target_viewport_rows(
            [item for item in cards if item.scan_step == card.scan_step]
        )
        column = next(
            column_index
            for viewport_row in viewport_rows
            for column_index, item in enumerate(viewport_row)
            if item is card
        )
        result.append(
            replace(
                card,
                ref=SelectionRef(
                    f'target:{revision}:{card.scan_step}:{row}:{column}:'
                    f'{center_x / screen_width:.4f}:{center_y / screen_height:.4f}'
                ),
                global_index=index,
                occurrence=occurrence,
            )
        )
    return result


def detect_complete_target_cards(screen: np.ndarray) -> tuple[CardRect, ...]:
    """Detect complete cyan-framed cards in row-major order."""
    height, width = screen.shape[:2]
    hsv = cv2.cvtColor(screen, cv2.COLOR_RGB2HSV)
    cyan = cv2.inRange(
        hsv,
        np.array((96, 170, 120), dtype=np.uint8),
        np.array((112, 255, 255), dtype=np.uint8),
    )
    contours, _ = cv2.findContours(cyan, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    expected_width = width * 0.10
    expected_height = height * 0.374
    boxes: list[CardRect] = []
    for contour in contours:
        left, top, box_width, box_height = cv2.boundingRect(contour)
        if not (expected_width * 0.82 <= box_width <= expected_width * 1.18):
            continue
        if not (expected_height * 0.97 <= box_height <= expected_height * 1.18):
            continue
        right = left + box_width
        bottom = top + box_height
        min_top = round(135 * height / 1080) if height >= 1080 else round(80 * height / 1000)
        max_bottom = round(1008 * height / 1080) if height >= 1080 else round(940 * height / 1000)
        if left <= 0 or top < min_top or right >= width - 1 or bottom > max_bottom:
            continue
        boxes.append(CardRect(left, top, right, bottom))
    boxes.sort(key=lambda box: (round(box.top / max(1, height * 0.03)), box.left))
    return tuple(boxes)


class TargetInventoryScanner:
    def __init__(
        self,
        device: TargetScanDevice,
        reader: TargetCardReader,
        *,
        settle_seconds: float = 1.5,
    ) -> None:
        self._device = device
        self._reader = reader
        self._settle_seconds = settle_seconds

    @staticmethod
    def detect_complete_cards(screen: np.ndarray) -> tuple[CardRect, ...]:
        """Return only cards whose full frame is visible; this never invokes identity work."""
        return detect_complete_target_cards(screen)

    def observe_viewport(
        self,
        screen: np.ndarray,
        *,
        scan_step: int,
        cards: tuple[CardRect, ...] | None = None,
    ) -> list[TargetShipSnapshot]:
        """Read geometry and WSG-NCC identities without invoking strengthen OCR."""
        cards = self.detect_complete_cards(screen) if cards is None else cards
        if not cards:
            raise TargetInventoryScanError('无法定位目标舰完整卡片')
        identities = self._reader.identify_all(screen, cards)
        if len(identities) != len(cards):
            raise TargetInventoryScanError('目标舰页面存在未识别完整卡片，拒绝宣称扫描完成')
        snapshots: list[TargetShipSnapshot] = []
        for card, identity in zip(cards, identities, strict=True):
            snapshots.append(
                TargetShipSnapshot(
                    ref=SelectionRef('unassigned'),
                    ship_id=identity.ship_id,
                    name=identity.name,
                    ship_type=identity.ship_type,
                    levels=ShipStats(),
                    card=card,
                    visual_hash=identity.visual_hash,
                    identity_confidence=identity.identity_confidence,
                    identity_match_key=identity.identity_match_key,
                    scan_step=scan_step,
                )
            )
        return snapshots

    def complete_viewport(
        self,
        screen: np.ndarray,
        observed: list[TargetShipSnapshot],
        *,
        inherited_prefix: list[TargetShipSnapshot] | None = None,
    ) -> list[TargetShipSnapshot]:
        """Read levels once for new cards after one logical viewport is accepted."""
        inherited = inherited_prefix or []
        if len(inherited) > len(observed):
            raise TargetInventoryScanError('目标舰继承重叠长度超过当前视口')
        completed: list[TargetShipSnapshot] = []
        for index, item in enumerate(observed):
            if index < len(inherited):
                previous = inherited[index]
                if not same_target_card(previous, item):
                    raise TargetInventoryScanError('目标舰继承重叠身份不一致')
                completed.append(replace(item, levels=previous.levels))
                continue
            identity = TargetCardIdentity(
                item.ship_id,
                item.name,
                item.ship_type,
                item.visual_hash,
                item.identity_confidence,
                item.identity_match_key,
            )
            levels = self._reader.read_levels(screen, item.card, identity)
            if levels is None:
                raise TargetInventoryScanError(
                    '目标舰页面完整卡片强化属性读取失败，'
                    f'拒绝宣称扫描完成: {item.ship_id}/{item.name}/'
                    f'{item.identity_match_key}'
                )
            completed.append(replace(item, levels=levels))
        return completed

    def observe_new_complete_cards(
        self,
        screen: np.ndarray,
        previous: list[TargetShipSnapshot],
        cards: tuple[CardRect, ...],
        *,
        scan_step: int,
    ) -> tuple[list[TargetShipSnapshot], int]:
        """Reuse the previous anchor row and identify only newly complete cards."""
        previous_rows = target_viewport_rows(previous)
        card_rows = target_card_rows(cards)
        if not previous_rows or not card_rows:
            raise TargetInventoryScanError('目标舰视口缺少可继承的完整行')
        anchor = previous_rows[-1]
        inherited_cards = card_rows[0]
        if len(inherited_cards) != len(anchor):
            raise TargetInventoryScanError('目标舰新视口首行与上一完整锚点行列数不一致')
        horizontal_tolerance = max(
            1,
            round(max(card.right - card.left for card in inherited_cards) * 0.12),
        )
        if any(
            abs(old.card.center[0] - new.center[0]) > horizontal_tolerance
            for old, new in zip(anchor, inherited_cards, strict=True)
        ):
            raise TargetInventoryScanError('目标舰新视口首行与上一完整锚点行横向位置不一致')
        inherited = [replace(old, card=new, scan_step=scan_step) for old, new in zip(anchor, inherited_cards, strict=True)]
        new_cards = tuple(card for row in card_rows[1:] for card in row)
        if not new_cards:
            return inherited, len(inherited)
        newly_identified = self.observe_viewport(screen, scan_step=scan_step, cards=new_cards)
        return [*inherited, *newly_identified], len(inherited)

    def read_viewport(self, screen: np.ndarray, *, scan_step: int) -> list[TargetShipSnapshot]:
        """Read one accepted viewport, including strengthen levels."""
        observed = self.observe_viewport(screen, scan_step=scan_step)
        return self.complete_viewport(screen, observed)

    def advance_overlapping_viewport(
        self,
        previous: list[TargetShipSnapshot],
        *,
        scan_step: int,
        max_attempts: int = TARGET_LOGICAL_VIEWPORT_MAX_PHYSICAL_INPUTS,
    ) -> tuple[list[TargetShipSnapshot], np.ndarray]:
        """Advance within a bounded physical-input budget to one logical viewport."""
        if max_attempts < 1:
            raise ValueError('目标舰物理滚动尝试次数必须大于 0')
        previous_rows = target_viewport_rows(previous)
        if not previous_rows:
            raise TargetInventoryScanError('目标舰视口没有完整锚点行')
        anchor = previous_rows[-1]
        last_anchor_index = len(previous_rows) - 1
        last_anchor_top = anchor[0].card.top
        observed_progress = False
        last_complete_count = len(previous)
        consecutive_same_count = 0
        recognition_interval = 8  # 连续若干次相同完整卡片数时触发一次 WSG-NCC 识别

        for _attempt in range(max_attempts):
            screen = self._device.advance_target_list()
            cards = self.detect_complete_cards(screen)
            at_bottom = self._device.target_list_at_bottom(screen)
            if not cards:
                if at_bottom:
                    raise TargetInventoryScanError('目标舰列表到底前没有完整卡片')
                continue

            complete_count = len(cards)
            should_recognize = False

            if complete_count > last_complete_count or at_bottom:
                should_recognize = True
                consecutive_same_count = 0
            else:
                consecutive_same_count += 1
                if consecutive_same_count >= recognition_interval:
                    should_recognize = True
                    consecutive_same_count = 0

            if not should_recognize:
                last_complete_count = complete_count
                continue

            current, overlap = self.observe_new_complete_cards(
                screen,
                previous,
                cards,
                scan_step=scan_step,
            )
            last_complete_count = complete_count
            current_rows = target_viewport_rows(current)
            anchor_index = matching_target_row_index(current_rows, anchor)
            if anchor_index is None:
                if len(current_rows) >= 2:
                    raise TargetInventoryScanError('目标舰列表滚动丢失完整锚点行')
                continue
            current_anchor_top = current_rows[anchor_index][0].card.top
            progressed = anchor_index < last_anchor_index or current_anchor_top < last_anchor_top
            if not progressed:
                continue
            observed_progress = True
            if anchor_index == 0 and len(current) > overlap:
                return self.complete_viewport(
                    screen,
                    current,
                    inherited_prefix=previous[-overlap:],
                ), screen
            if at_bottom:
                if len(current) > overlap:
                    return self.complete_viewport(
                        screen,
                        current,
                        inherited_prefix=previous[-overlap:],
                    ), screen
                return current, screen
            last_anchor_index = anchor_index
            last_anchor_top = current_anchor_top
        if not observed_progress:
            raise TargetInventoryScanError(
                f'目标舰列表滚动没有产生可观测进度，物理滚动尝试次数: {max_attempts}'
            )
        raise TargetInventoryScanError(f'目标舰逻辑视口超过物理滚动尝试次数: {max_attempts}')

    def navigate_to_viewport(self, viewport_steps: int) -> list[TargetShipSnapshot]:
        """Replay identity-gated logical target rows from the list top."""
        if viewport_steps < 0:
            raise ValueError('目标舰视口步数不能为负数')
        self._device.rewind_target_list()
        time.sleep(self._settle_seconds)
        previous = self.observe_viewport(self._device.screenshot(), scan_step=0)
        for scan_step in range(1, viewport_steps + 1):
            previous, _screen = self.advance_overlapping_viewport(
                previous,
                scan_step=scan_step,
            )
        return previous

    @staticmethod
    def _content_digest(screen: np.ndarray) -> bytes:
        """Hash list content area without trusting transient header/scrollbar animations."""
        body = np.ascontiguousarray(screen[135:1008, : round(screen.shape[1] * 0.82)])
        return hashlib.blake2b(body, digest_size=16).digest()

    def scan_all(self, *, max_scrolls: int = 300) -> list[TargetShipSnapshot]:
        if max_scrolls < 1:
            raise ValueError('目标舰最大滚动次数必须大于 0')
        self._device.rewind_target_list()
        time.sleep(self._settle_seconds)

        accumulated_targets: list[TargetShipSnapshot] = []
        seen_row_signatures: set[tuple[int, ...]] = set()
        stagnant_at_bottom = 0
        prev_digest: bytes | None = None
        last_screen: np.ndarray | None = None

        for step in range(max_scrolls):
            screen = self._device.screenshot()
            last_screen = screen
            digest = self._content_digest(screen)

            if prev_digest is not None and digest == prev_digest:
                stagnant_at_bottom += 1
                if stagnant_at_bottom >= 3:
                    break
            else:
                stagnant_at_bottom = 0
            prev_digest = digest

            cards = self.detect_complete_cards(screen)
            raw_rows = target_card_rows(cards)

            for r in raw_rows:
                idents = self._reader.identify_all(screen, r)
                sig = tuple(c.ship_id for c in idents)
                if sig not in seen_row_signatures:
                    seen_row_signatures.add(sig)
                    for card, ident in zip(r, idents, strict=True):
                        levels = self._reader.read_levels(screen, card, ident)
                        accumulated_targets.append(
                            TargetShipSnapshot(
                                ref=SelectionRef('unassigned'),
                                ship_id=ident.ship_id,
                                name=ident.name,
                                ship_type=ident.ship_type,
                                levels=levels or ShipStats(),
                                card=card,
                                visual_hash=ident.visual_hash,
                                identity_confidence=ident.identity_confidence,
                                identity_match_key=ident.identity_match_key,
                                scan_step=step,
                                masked=ident.masked,
                            )
                        )

            if step % 3 == 0 or stagnant_at_bottom > 0:
                _log.info('[OPS] 扫描目标库存: 滚动第 {} 步, 已识别 {} 艘目标', step + 1, len(accumulated_targets))

            self._device.advance_target_list()

        if not accumulated_targets:
            raise TargetInventoryScanError('完整目标库存不能为空')

        screen_width = last_screen.shape[1] if last_screen is not None else 1920
        screen_height = last_screen.shape[0] if last_screen is not None else 1080
        return assign_target_occurrences(
            accumulated_targets,
            screen_width=screen_width,
            screen_height=screen_height,
        )

    def scan_snapshot(self, *, max_scrolls: int = 80) -> TargetInventorySnapshot:
        """Return the immutable aggregate only after ``scan_all`` proves completion."""
        targets = tuple(self.scan_all(max_scrolls=max_scrolls))
        if not targets:
            raise TargetInventoryScanError('完整目标库存不能为空')
        revision = targets[0].ref.value.split(':')[1]
        return TargetInventorySnapshot(
            targets=targets,
            total=len(targets),
            complete=True,
            revision=revision,
        )
