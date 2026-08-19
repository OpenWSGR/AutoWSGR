"""wait_leave_page 探测模式 (probe=True) 的无设备单元测试。

背景 (实机 2026-08-15 日志): 战役次数用尽是预期分支, 但出征探测用的
wait_leave_page 超时走 NavigationError 路径 — 构造该异常会 ERROR 记录 +
保存 NavError 截图, 即使调用方立刻捕获, 错误现场也已被污染。probe 模式
让"超时"成为普通返回值 (None)。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from autowsgr.ui.utils.navigation import wait_leave_page


def _ctrl(stays: bool) -> MagicMock:
    """构造 mock 控制器; *stays* 为 True 时截图永远匹配原页面。"""
    ctrl = MagicMock()
    frame = np.full((540, 960, 3), 200, dtype=np.uint8)
    ctrl.screenshot.return_value = frame
    ctrl.checker = MagicMock(return_value=stays)
    return ctrl


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr('autowsgr.ui.utils.navigation.time.sleep', lambda *_: None)


class TestProbeMode:
    def test_probe_timeout_returns_none_without_raising(self):
        """probe=True 超时 → 返回 None 而非抛 NavigationError。"""
        ctrl = _ctrl(stays=True)
        result = wait_leave_page(
            ctrl,
            checker=lambda _: True,  # 永远"仍在原页"
            timeout=0,
            probe=True,
        )
        assert result is None

    def test_probe_left_returns_frame(self):
        """probe 模式下正常离开 → 仍返回到达帧 (与普通模式一致)。"""
        ctrl = _ctrl(stays=False)
        result = wait_leave_page(ctrl, checker=lambda _: False, timeout=1, probe=True)
        assert isinstance(result, np.ndarray)

    def test_default_mode_still_raises(self):
        """probe=False (默认) 超时 → 照旧抛 NavigationError。"""
        from autowsgr.ui.utils.navigation import NavigationError

        with pytest.raises(NavigationError):
            wait_leave_page(ctrl=_ctrl(stays=True), checker=lambda _: True, timeout=0)
