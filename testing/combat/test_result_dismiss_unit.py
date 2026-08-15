"""战果类页面验证式关闭 (_click_result_until_closed) 的无设备单元测试。

背景 (实机 2026-08-15 日志): 结算页两次连点 (间隔 0.25s) 可能被模拟器吞掉,
引擎在页面未退出时即返回, 上层导航对未注册的战果页全量识别失败 → NavError
死循环。修复后每次点击复检页面签名, 未关闭则延迟重点。
"""

from __future__ import annotations

from unittest.mock import MagicMock, call

import numpy as np
import pytest

from autowsgr.combat.handlers import PhaseHandlersMixin
from autowsgr.combat.state import CombatPhase


class _Host(PhaseHandlersMixin):
    """最小宿主: 只提供 _click_result_until_closed 用到的两个属性。"""

    def __init__(self, device: MagicMock, recognizer: MagicMock) -> None:
        self._device = device
        self._recognizer = recognizer


def _make_host(phase_results: list[CombatPhase | None]) -> tuple[_Host, MagicMock, MagicMock]:
    """构造宿主; *phase_results* 为每次点击后复检的返回序列 (None=已关闭)。"""
    device = MagicMock()
    device.screenshot.return_value = np.zeros((540, 960, 3), dtype=np.uint8)
    recognizer = MagicMock()
    recognizer.identify_current.side_effect = phase_results
    return _Host(device, recognizer), device, recognizer


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr('autowsgr.combat.handlers.time.sleep', lambda *_: None)


class TestClickResultUntilClosed:
    def test_first_click_closes(self):
        """点击一次页面即关闭 → 只点一次。"""
        host, device, recognizer = _make_host([None])
        host._click_result_until_closed(CombatPhase.RESULT)
        assert device.click.call_count == 1
        recognizer.identify_current.assert_called_once()

    def test_retries_until_closed(self):
        """前两次点击被吞 (签名仍在) → 第三次关闭, 共点 3 次。"""
        host, device, _ = _make_host([CombatPhase.RESULT, CombatPhase.RESULT, None])
        host._click_result_until_closed(CombatPhase.RESULT)
        assert device.click.call_count == 3

    def test_gives_up_after_attempts(self):
        """持续未关闭 → 达到 attempts 上限后停止, 不抛异常 (交上层导航处理)。"""
        host, device, _ = _make_host([CombatPhase.RESULT] * 10)
        host._click_result_until_closed(CombatPhase.RESULT, attempts=4)
        assert device.click.call_count == 4

    def test_clicks_result_coordinate(self):
        """点击坐标走 Coords.CLICK_RESULT (与 combat/actions.click_result 一致)。"""
        from autowsgr.combat.actions import Coords

        host, device, _ = _make_host([None])
        host._click_result_until_closed(CombatPhase.GET_SHIP)
        assert device.click.call_args == call(*Coords.CLICK_RESULT)
