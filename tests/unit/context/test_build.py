"""测试 autowsgr.context.build。"""

from __future__ import annotations

from autowsgr.context.build import BuildQueue, BuildSlot


def test_build_slot_defaults() -> None:
    """BuildSlot 默认值应为空闲。"""
    slot = BuildSlot()
    assert slot.occupied is False
    assert slot.remaining_seconds == 0
    assert slot.is_idle is True
    assert slot.is_complete is False


def test_build_slot_complete() -> None:
    """occupied 且 remaining_seconds <= 0 时应为完成。"""
    slot = BuildSlot(occupied=True, remaining_seconds=0)
    assert slot.is_complete is True
    assert slot.is_idle is False


def test_build_slot_in_progress() -> None:
    """occupied 且 remaining_seconds > 0 时不应完成。"""
    slot = BuildSlot(occupied=True, remaining_seconds=120)
    assert slot.is_complete is False
    assert slot.is_idle is False


def test_build_queue_defaults() -> None:
    """BuildQueue 默认应有 4 个空闲槽位。"""
    queue = BuildQueue()
    assert len(queue.slots) == 4
    assert queue.idle_count == 4
    assert queue.complete_count == 0


def test_build_queue_mixed_state() -> None:
    """混合状态槽位统计应正确。"""
    queue = BuildQueue(
        slots=[
            BuildSlot(occupied=True, remaining_seconds=0),
            BuildSlot(occupied=True, remaining_seconds=60),
            BuildSlot(),
            BuildSlot(),
        ],
    )
    assert queue.idle_count == 2
    assert queue.complete_count == 1
