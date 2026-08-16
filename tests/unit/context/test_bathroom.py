"""BathRoom 浴室槽位状态机单元测试 (无设备)。

验证空位判定 / 占用 / 释放 / mark_unknown 的状态转移。
通过 monkeypatch 控制 ``time.time()``, 实现确定性断言。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.context.bathroom import BathRoom


if TYPE_CHECKING:
    import pytest


def test_unknown_state_is_available():
    """初始 ``available_time=None`` 视为有空位 (允许尝试派修以重建状态)。"""
    bath = BathRoom()
    assert bath.available_time is None
    assert bath.is_available() is True
    assert bath.get_waiting_time() == 0.0


def test_occupy_fills_then_blocks(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr('autowsgr.context.bathroom.time.time', lambda: 1000.0)
    bath = BathRoom(slot_count=2)

    assert bath.is_available() is True  # 两槽全空
    bath.occupy(500)  # 槽 0 → 释放于 1500
    assert bath.is_available() is True  # 槽 1 仍空
    bath.occupy(500)  # 槽 1 → 释放于 1500
    assert bath.is_available() is False  # 两槽全忙
    assert bath.get_waiting_time() == 500.0


def test_slot_releases_over_time(monkeypatch: pytest.MonkeyPatch):
    """释放时间到期后, 槽位自动回收为空闲。"""
    t_box = [1000.0]
    monkeypatch.setattr('autowsgr.context.bathroom.time.time', lambda: t_box[0])

    bath = BathRoom(slot_count=1)
    bath.occupy(300)  # 释放于 1300
    assert bath.is_available() is False
    assert bath.get_waiting_time() == 300.0

    t_box[0] = 1300.0  # 到点
    assert bath.is_available() is True
    assert bath.get_waiting_time() == 0.0


def test_occupy_non_positive_is_noop(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr('autowsgr.context.bathroom.time.time', lambda: 1000.0)
    bath = BathRoom(slot_count=1)

    bath.occupy(0)
    bath.occupy(-5)
    assert bath.is_available() is True  # 未占用


def test_mark_unknown_forces_retry(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr('autowsgr.context.bathroom.time.time', lambda: 1000.0)
    bath = BathRoom(slot_count=1)
    bath.occupy(999)
    assert bath.is_available() is False

    bath.mark_unknown()
    assert bath.available_time is None
    assert bath.is_available() is True  # 下次触发可重试


def test_slot_count_clamped_to_minimum(monkeypatch: pytest.MonkeyPatch):
    """``slot_count <= 0`` 初始化时夹到 1, 避免空槽列表。"""
    monkeypatch.setattr('autowsgr.context.bathroom.time.time', lambda: 1000.0)
    bath = BathRoom(slot_count=0)
    bath.occupy(100)  # 触发 _ensure_initialized
    assert bath.available_time is not None
    assert len(bath.available_time) == 1


def test_occupy_reuses_earliest_freed_slot(monkeypatch: pytest.MonkeyPatch):
    """有多个忙槽时, 优先占用最早释放的那个。"""
    t_box = [1000.0]
    monkeypatch.setattr('autowsgr.context.bathroom.time.time', lambda: t_box[0])
    bath = BathRoom(slot_count=2)
    bath.occupy(500)  # 槽 0 → 1500
    bath.occupy(800)  # 槽 1 → 1800
    assert bath.get_waiting_time() == 500.0  # 取最早

    t_box[0] = 1500.0  # 仅槽 0 到期
    assert bath.is_available() is True
    bath.occupy(100)  # 复用槽 0 → 1600; 槽 1 仍 1800

    # 复用后两槽皆忙 (1600 / 1800), 最近释放还需 100s
    assert bath.is_available() is False
    assert bath.get_waiting_time() == 100.0
