"""测试 autowsgr.context.expedition。"""

from __future__ import annotations

from autowsgr.context.expedition import Expedition, ExpeditionQueue
from autowsgr.context.fleet import Fleet


def test_expedition_defaults() -> None:
    """Expedition 默认值应为非激活状态。"""
    exp = Expedition()
    assert exp.chapter == 0
    assert exp.node == 0
    assert exp.fleet is None
    assert exp.is_active is False


def test_expedition_active_with_fleet() -> None:
    """绑定舰队后应为激活状态。"""
    fleet = Fleet(fleet_id=2)
    exp = Expedition(chapter=3, node=2, fleet=fleet)
    assert exp.is_active is True
    assert exp.fleet is not None
    assert exp.fleet.fleet_id == 2


def test_expedition_queue_defaults() -> None:
    """ExpeditionQueue 默认应有 4 个空闲槽位。"""
    queue = ExpeditionQueue()
    assert len(queue.expeditions) == 4
    assert queue.active_count == 0
    assert queue.idle_count == 4


def test_expedition_queue_mixed_state() -> None:
    """混合状态远征统计应正确。"""
    queue = ExpeditionQueue(
        expeditions=[
            Expedition(fleet=Fleet(fleet_id=1)),
            Expedition(),
            Expedition(fleet=Fleet(fleet_id=3)),
            Expedition(),
        ],
    )
    assert queue.active_count == 2
    assert queue.idle_count == 2
