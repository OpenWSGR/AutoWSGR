"""掉落页 OCR 有限重试的无设备单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from autowsgr.combat import actions as actions_mod
from autowsgr.combat.recognition import ShipDropResult


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    sleeps: list[float] = []
    monkeypatch.setattr(actions_mod.time, 'sleep', sleeps.append)
    return sleeps


def test_get_ship_drop_retries_five_frames_before_giving_up(
    monkeypatch: pytest.MonkeyPatch,
    _no_sleep: list[float],
) -> None:
    device = MagicMock()
    device.screenshot.return_value = np.zeros((540, 960, 3), dtype=np.uint8)
    results = [ShipDropResult(ship_name=None, ship_type=None)] * 4
    results.append(ShipDropResult(ship_name='SKR6', ship_type='驱逐舰'))
    monkeypatch.setattr(actions_mod, 'recognize_ship_drop', lambda *_a: results.pop(0))

    result = actions_mod.get_ship_drop(device, object())  # type: ignore[arg-type]

    assert result == 'SKR6'
    assert device.screenshot.call_count == 5
    assert _no_sleep == [0.5, 0.5, 0.5, 0.5]


def test_get_ship_drop_returns_none_after_five_misses(
    monkeypatch: pytest.MonkeyPatch,
    _no_sleep: list[float],
) -> None:
    device = MagicMock()
    device.screenshot.return_value = np.zeros((540, 960, 3), dtype=np.uint8)
    monkeypatch.setattr(
        actions_mod,
        'recognize_ship_drop',
        lambda *_a: ShipDropResult(ship_name=None, ship_type=None),
    )

    result = actions_mod.get_ship_drop(device, object())  # type: ignore[arg-type]

    assert result is None
    assert device.screenshot.call_count == 5
    assert _no_sleep == [0.5, 0.5, 0.5, 0.5]
