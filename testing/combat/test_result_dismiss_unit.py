"""战果类页面验证式关闭 (_click_result_until_closed) 的无设备单元测试。

背景 (实机 2026-08-15 日志, 两轮迭代):
  1. 结算页连点可能被模拟器吞掉, 引擎在页面未退出时即返回 → NavError。
  2. 修复一版用"原页面签名消失"当成功判据, 但点击 RESULT 后游戏先进入
     **经验结算子页** (无对应 CombatPhase 状态): 复检在该页误判成功提前
     返回, 引擎等待 PROCEED/GET_SHIP 等状态 7.5s 全落空 → 恢复失败 →
     强制重启游戏。
现行判据是**到达验证**: 在 ``[phase] + 后继状态`` 集合上识别,
命中后继才算成功, 识别不到任何状态 (中间页) 则继续点击推进。
"""

from __future__ import annotations

from unittest.mock import MagicMock, call

import numpy as np
import pytest

from autowsgr.combat.handlers import PhaseHandlersMixin
from autowsgr.combat.state import CombatPhase


class _Host(PhaseHandlersMixin):
    """最小宿主: 只提供 _click_result_until_closed 用到的属性。"""

    def __init__(
        self, device: MagicMock, recognizer: MagicMock, end_phase: CombatPhase | None
    ) -> None:
        self._device = device
        self._recognizer = recognizer
        plan = MagicMock()
        plan.end_phase = end_phase
        self._plan = plan


def _make_host(
    phase_results: list[CombatPhase | None],
    end_phase: CombatPhase | None = None,
) -> tuple[_Host, MagicMock, MagicMock]:
    """构造宿主; *phase_results* 为每次点击后复检的返回序列 (None=中间页)。"""
    device = MagicMock()
    device.screenshot.return_value = np.zeros((540, 960, 3), dtype=np.uint8)
    recognizer = MagicMock()
    recognizer.identify_current.side_effect = phase_results
    return _Host(device, recognizer, end_phase), device, recognizer


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr('autowsgr.combat.handlers.time.sleep', lambda *_: None)


class TestClickResultUntilClosed:
    def test_reaches_successor(self):
        """点击一次即识别到后继 (PROCEED) → 成功, 只点一次。"""
        host, device, recognizer = _make_host([CombatPhase.PROCEED])
        host._click_result_until_closed(CombatPhase.RESULT)
        assert device.click.call_count == 1
        recognizer.identify_current.assert_called_once()

    def test_intermediate_page_keeps_clicking(self):
        """复检识别不到任何状态 (经验结算中间页) → 继续点击直到后继出现。

        这是问题2的核心回归: 旧判据 (签名消失即成功) 在这里会提前返回。
        """
        host, device, _ = _make_host([None, None, CombatPhase.GET_SHIP])
        host._click_result_until_closed(CombatPhase.RESULT)
        assert device.click.call_count == 3

    def test_retries_while_signature_remains(self):
        """前两次点击被吞 (签名仍在) → 第三次到后继, 共点 3 次。"""
        host, device, _ = _make_host([CombatPhase.RESULT, CombatPhase.RESULT, CombatPhase.PROCEED])
        host._click_result_until_closed(CombatPhase.RESULT)
        assert device.click.call_count == 3

    def test_gives_up_after_attempts(self):
        """持续停在原页面 → 达到 attempts 上限后停止, 不抛异常 (交上层处理)。"""
        host, device, _ = _make_host([CombatPhase.RESULT] * 10)
        host._click_result_until_closed(CombatPhase.RESULT, attempts=4)
        assert device.click.call_count == 4

    def test_clicks_result_coordinate(self):
        """点击坐标走 Coords.CLICK_RESULT (与 combat/actions.click_result 一致)。"""
        from autowsgr.combat.actions import Coords

        host, device, _ = _make_host([CombatPhase.PROCEED])
        host._click_result_until_closed(CombatPhase.GET_SHIP)
        assert device.click.call_args == call(*Coords.CLICK_RESULT)


class TestResultSuccessors:
    def test_event_result_includes_end_phase(self):
        """活动战斗 (end_phase=EVENT_MAP_PAGE): RESULT 后继含终态页。"""
        host, _, _ = _make_host([], end_phase=CombatPhase.EVENT_MAP_PAGE)
        assert set(host._result_successors(CombatPhase.RESULT)) == {
            CombatPhase.PROCEED,
            CombatPhase.FLAGSHIP_SEVERE_DAMAGE,
            CombatPhase.EVENT_MAP_PAGE,
            CombatPhase.GET_SHIP,
        }

    def test_campaign_result_no_end_phase(self):
        """战役 (end_phase=None): RESULT 后继不含终态页, 与转移图一致。"""
        host, _, _ = _make_host([], end_phase=None)
        assert set(host._result_successors(CombatPhase.RESULT)) == {
            CombatPhase.PROCEED,
            CombatPhase.FLAGSHIP_SEVERE_DAMAGE,
            CombatPhase.GET_SHIP,
        }

    def test_get_ship_excludes_self(self):
        """GET_SHIP 后继不含 GET_SHIP 自身。"""
        host, _, _ = _make_host([], end_phase=CombatPhase.MAP_PAGE)
        successors = host._result_successors(CombatPhase.GET_SHIP)
        assert CombatPhase.GET_SHIP not in successors
        assert CombatPhase.MAP_PAGE in successors
