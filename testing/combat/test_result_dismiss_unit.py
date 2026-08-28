"""战果类页面验证式关闭 (_click_result_until_closed) 的无设备单元测试。

背景 (实机 2026-08-15 日志, 两轮迭代):
  1. 结算页连点可能被模拟器吞掉, 引擎在页面未退出时即返回 → NavError。
  2. 修复一版用"原页面签名消失"当成功判据, 但点击 RESULT 后游戏先进入
     **经验结算子页** (无对应 CombatPhase 状态): 复检在该页误判成功提前
     返回, 引擎等待 PROCEED/GET_SHIP 等状态 7.5s 全落空 → 恢复失败 →
     强制重启游戏。
   现行判据是**到达验证**: 在 ``[phase] + 后继状态`` 集合上识别,
   命中后继才算成功, 识别不到任何状态 (未知中间页) 则交外层状态机确认。
经验结算子页后正式注册为 ``CombatPhase.EXP_SETTLEMENT``, 不再是盲点。
"""

from __future__ import annotations

from unittest.mock import MagicMock, call

import numpy as np
import pytest

from autowsgr.combat import handlers as handlers_mod
from autowsgr.combat.handlers import PhaseHandlersMixin
from autowsgr.combat.history import CombatEvent, CombatHistory, EventType
from autowsgr.combat.state import CombatPhase


class _Host(PhaseHandlersMixin):
    """最小宿主: 只提供 _click_result_until_closed 用到的属性。"""

    def __init__(
        self,
        device: MagicMock,
        recognizer: MagicMock,
        end_phase: CombatPhase | None,
        collect_result_info: bool = True,
    ) -> None:
        self._device = device
        self._recognizer = recognizer
        self._ocr = None
        plan = MagicMock()
        plan.end_phase = end_phase
        plan.collect_result_info = collect_result_info
        self._plan = plan
        # _handle_result 用到的其余属性
        self._ship_stats: list = [None] * 6
        self._history = MagicMock()
        self._node = 'A'


def _make_host(
    phase_results: list[CombatPhase | None],
    end_phase: CombatPhase | None = None,
    collect_result_info: bool = True,
) -> tuple[_Host, MagicMock, MagicMock]:
    """构造宿主; *phase_results* 为每次点击后复检的返回序列 (None=中间页)。"""
    device = MagicMock()
    device.screenshot.return_value = np.zeros((540, 960, 3), dtype=np.uint8)
    recognizer = MagicMock()
    recognizer.identify_current.side_effect = phase_results
    return _Host(device, recognizer, end_phase, collect_result_info), device, recognizer


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

    def test_intermediate_page_waits_for_confirmation(self):
        """过渡帧未确认时只等待, 不盲点跳过尚未识别的掉落页。"""
        host, device, recognizer = _make_host(
            [None, None, None, None, CombatPhase.GET_SHIP]
        )
        host._click_result_until_closed(CombatPhase.RESULT)
        assert device.click.call_count == 1
        assert recognizer.identify_current.call_count == 4

    def test_retries_while_signature_remains(self):
        """前两次点击被吞 (签名仍在) → 第三次到后继, 共点 3 次。"""
        host, device, _ = _make_host([CombatPhase.RESULT, CombatPhase.RESULT, CombatPhase.PROCEED])
        host._click_result_until_closed(CombatPhase.RESULT)
        assert device.click.call_count == 3

    def test_pass_through_page_keeps_clicking(self):
        """命中 pass_through 过渡页 (快速穿行的经验页) → 继续点击直到真正后继。"""
        host, device, _ = _make_host([CombatPhase.EXP_SETTLEMENT, CombatPhase.GET_SHIP])
        host._click_result_until_closed(
            CombatPhase.RESULT, pass_through=(CombatPhase.EXP_SETTLEMENT,)
        )
        assert device.click.call_count == 2

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
        """活动战斗 (慢速): RESULT 后继含终态页 + 经验页 (逐页推进)。"""
        host, _, _ = _make_host([], end_phase=CombatPhase.EVENT_MAP_PAGE)
        assert set(host._result_successors(CombatPhase.RESULT)) == {
            CombatPhase.PROCEED,
            CombatPhase.FLAGSHIP_SEVERE_DAMAGE,
            CombatPhase.EVENT_MAP_PAGE,
            CombatPhase.GET_SHIP,
            CombatPhase.EXP_SETTLEMENT,
        }

    def test_fast_result_excludes_exp(self):
        """快速穿行: 经验页是 pass_through 过渡页, 不在 RESULT 到达集合。"""
        host, _, _ = _make_host([], end_phase=CombatPhase.MAP_PAGE, collect_result_info=False)
        assert set(host._result_successors(CombatPhase.RESULT)) == {
            CombatPhase.PROCEED,
            CombatPhase.FLAGSHIP_SEVERE_DAMAGE,
            CombatPhase.MAP_PAGE,
            CombatPhase.GET_SHIP,
        }

    def test_campaign_result_no_end_phase(self):
        """战役 (end_phase=None): RESULT 后继不含终态页, 与转移图一致。"""
        host, _, _ = _make_host([], end_phase=None)
        assert set(host._result_successors(CombatPhase.RESULT)) == {
            CombatPhase.PROCEED,
            CombatPhase.FLAGSHIP_SEVERE_DAMAGE,
            CombatPhase.GET_SHIP,
            CombatPhase.EXP_SETTLEMENT,
        }

    def test_exp_settlement_excludes_self(self):
        """EXP_SETTLEMENT 后继不含自身, 仍含 GET_SHIP (掉落在经验页之后)。"""
        host, _, _ = _make_host([], end_phase=CombatPhase.MAP_PAGE)
        successors = host._result_successors(CombatPhase.EXP_SETTLEMENT)
        assert CombatPhase.EXP_SETTLEMENT not in successors
        assert CombatPhase.GET_SHIP in successors
        assert CombatPhase.MAP_PAGE in successors

    def test_get_ship_excludes_self_and_exp(self):
        """GET_SHIP 后继不含 GET_SHIP 自身与 EXP_SETTLEMENT (经验页只跟在 RESULT 后)。"""
        host, _, _ = _make_host([], end_phase=CombatPhase.MAP_PAGE)
        successors = host._result_successors(CombatPhase.GET_SHIP)
        assert CombatPhase.GET_SHIP not in successors
        assert CombatPhase.EXP_SETTLEMENT not in successors
        assert CombatPhase.MAP_PAGE in successors


class TestHandleResultModes:
    """_handle_result 快速穿行 / 慢速采集双模式。"""

    @pytest.fixture(autouse=True)
    def _stub_detectors(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(handlers_mod, 'detect_ship_stats', lambda *_a: _a[1])
        monkeypatch.setattr(handlers_mod, 'detect_result_grade', lambda *_a, **_k: 'S')
        monkeypatch.setattr(handlers_mod, 'detect_mvp', lambda *_a, **_k: '鲃鱼')

    def test_fast_passes_through_exp(self):
        """快速: 仍采集评级/MVP (始终采集), 但经验页穿行 (pass_through)。"""
        host, device, _ = _make_host(
            [CombatPhase.EXP_SETTLEMENT, CombatPhase.PROCEED],
            collect_result_info=False,
        )
        host._handle_result()
        # 经验页命中后继续点击, 直到 PROCEED 才停 → 2 次点击
        assert device.click.call_count == 2
        # 始终采集: 快速模式也记录战果事件 (计数器/触发器依赖)
        host._history.add.assert_called_once()

    def test_slow_collects_grade_mvp_and_records(self):
        """慢速: 采集评级/MVP 记入战斗历史, 经验页是到达点 (只点一次)。"""
        host, device, _ = _make_host([CombatPhase.EXP_SETTLEMENT], collect_result_info=True)
        host._handle_result()
        assert device.click.call_count == 1
        host._history.add.assert_called_once()
        event = host._history.add.call_args.args[0]
        assert event.event_type.name == 'RESULT'
        assert event.result == 'S'
        assert event.extra == {'mvp': '鲃鱼'}


class TestDropCapture:
    """掉落捕获: 幂等 + 点击穿行时兜底捕获。"""

    @pytest.fixture(autouse=True)
    def _stub_ocr(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._ocr_calls: list = []
        monkeypatch.setattr(
            handlers_mod,
            'get_ship_drop',
            lambda *_a, **_k: self._ocr_calls.append(1) or 'SKR6',
        )

    def _make_host_with_history(self, *args, **kwargs):
        host, device, recognizer = _make_host(*args, **kwargs)
        host._history = CombatHistory()
        return host, device

    def test_capture_is_idempotent(self):
        """同节点已记录掉落 → 复用历史结果, 不重复 OCR。"""
        host, _ = self._make_host_with_history([CombatPhase.PROCEED])
        host._history.add(
            CombatEvent(event_type=EventType.GET_SHIP, node='A', result='SKR6'),
        )
        result = host._capture_get_ship()
        assert result == 'SKR6'
        assert self._ocr_calls == []

    def test_capture_records_new_drop(self):
        """首次捕获: OCR 识别 + 记录历史 + 返回舰名。"""
        host, _ = self._make_host_with_history([CombatPhase.PROCEED])
        result = host._capture_get_ship()
        assert result == 'SKR6'
        assert self._ocr_calls == [1]
        event = host._history.get_event(EventType.GET_SHIP, 'A')
        assert event is not None and event.result == 'SKR6'

    def test_result_dismiss_captures_on_get_ship(self):
        """点击穿行命中 GET_SHIP → 立即幂等捕获掉落, 主循环不再重复 OCR。"""
        host, device = self._make_host_with_history(
            [CombatPhase.GET_SHIP, CombatPhase.PROCEED],
            collect_result_info=False,
        )
        host._click_result_until_closed(CombatPhase.RESULT)
        assert device.click.call_count == 1
        event = host._history.get_event(EventType.GET_SHIP, 'A')
        assert event is not None and event.result == 'SKR6'
        # 主循环重新派发 _handle_get_ship 时走幂等分支, 不重复 OCR
        host._handle_get_ship()
        assert self._ocr_calls == [1]

    def test_result_dismiss_retries_unrecognized_get_ship(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """快速捕获失败后, GET_SHIP 处理器应在稳定页面重试 OCR。"""
        results = iter([None, 'SKR6'])
        monkeypatch.setattr(
            handlers_mod,
            'get_ship_drop',
            lambda *_a, **_k: self._ocr_calls.append(1) or next(results),
        )
        host, _ = self._make_host_with_history(
            [CombatPhase.GET_SHIP, CombatPhase.PROCEED],
            collect_result_info=False,
        )

        host._click_result_until_closed(CombatPhase.RESULT)
        assert host._history.get_event(EventType.GET_SHIP, 'A') is None

        host._handle_get_ship()

        assert self._ocr_calls == [1, 1]
        event = host._history.get_event(EventType.GET_SHIP, 'A')
        assert event is not None
        assert event.result == 'SKR6'

    def test_get_ship_clicks_after_ocr_exhaustion(self, monkeypatch: pytest.MonkeyPatch):
        """掉落/上限提示页 OCR 无结果后仍应点击离开。"""
        monkeypatch.setattr(handlers_mod, 'get_ship_drop', lambda *_a, **_k: None)
        host, device = self._make_host_with_history([CombatPhase.PROCEED])

        host._handle_get_ship()

        assert device.click.call_count == 1

    def test_pixel_fallback_captures_on_transition(self):
        """模板未命中 (None 过渡帧) 但掉落页像素签名命中 → 兜底捕获。"""
        host, device = self._make_host_with_history(
            [None],
            collect_result_info=False,
        )
        host._is_get_ship_page = lambda _screen: True
        host._click_result_until_closed(CombatPhase.RESULT)
        assert device.click.call_count == 1
        event = host._history.get_event(EventType.GET_SHIP, 'A')
        assert event is not None and event.result == 'SKR6'
