"""测试 UI 页面注册中心与导航验证工具。"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from autowsgr.emulator.controller import AndroidController
from autowsgr.ui.page import (
    DEFAULT_INTERVAL,
    DEFAULT_TIMEOUT,
    NavigationError,
    _PAGE_REGISTRY,
    get_current_page,
    get_registered_pages,
    register_page,
    wait_for_page,
    wait_leave_page,
)

_W, _H = 960, 540


def _blank() -> np.ndarray:
    return np.zeros((_H, _W, 3), dtype=np.uint8)


def _white() -> np.ndarray:
    return np.full((_H, _W, 3), 255, dtype=np.uint8)


# ─────────────────────────────────────────────
# 页面注册
# ─────────────────────────────────────────────


class TestRegisterPage:
    def setup_method(self):
        self._backup = dict(_PAGE_REGISTRY)
        _PAGE_REGISTRY.clear()

    def teardown_method(self):
        _PAGE_REGISTRY.clear()
        _PAGE_REGISTRY.update(self._backup)

    def test_register_and_list(self):
        register_page("page_a", lambda s: True)
        assert "page_a" in get_registered_pages()

    def test_register_overwrites(self):
        checker1 = lambda s: False
        checker2 = lambda s: True
        register_page("page_b", checker1)
        register_page("page_b", checker2)
        assert len([n for n in get_registered_pages() if n == "page_b"]) == 1
        # 应使用后注册的 checker
        assert get_current_page(_blank()) == "page_b"

    def test_register_multiple(self):
        register_page("p1", lambda s: False)
        register_page("p2", lambda s: False)
        register_page("p3", lambda s: False)
        assert len(get_registered_pages()) == 3


# ─────────────────────────────────────────────
# get_current_page
# ─────────────────────────────────────────────


class TestGetCurrentPage:
    def setup_method(self):
        self._backup = dict(_PAGE_REGISTRY)
        _PAGE_REGISTRY.clear()

    def teardown_method(self):
        _PAGE_REGISTRY.clear()
        _PAGE_REGISTRY.update(self._backup)

    def test_returns_first_match(self):
        register_page("always_true", lambda s: True)
        register_page("also_true", lambda s: True)
        result = get_current_page(_blank())
        assert result == "always_true"

    def test_returns_none_when_no_match(self):
        register_page("never", lambda s: False)
        assert get_current_page(_blank()) is None

    def test_empty_registry(self):
        assert get_current_page(_blank()) is None

    def test_skips_exception_checker(self):
        """识别器抛异常时跳过，不影响后续。"""

        def bad_checker(s):
            raise RuntimeError("boom")

        register_page("bad", bad_checker)
        register_page("good", lambda s: True)
        assert get_current_page(_blank()) == "good"


# ─────────────────────────────────────────────
# wait_for_page
# ─────────────────────────────────────────────


class TestWaitForPage:
    def test_immediate_success(self):
        """第一次截图即匹配 → 立即返回。"""
        ctrl = MagicMock(spec=AndroidController)
        ctrl.screenshot.return_value = _blank()

        result = wait_for_page(
            ctrl,
            lambda s: True,
            source="A",
            target="B",
        )
        assert result is not None
        ctrl.screenshot.assert_called_once()

    def test_success_after_retries(self):
        """前两次不匹配，第三次匹配。"""
        ctrl = MagicMock(spec=AndroidController)
        screens = [_blank(), _blank(), _white()]
        ctrl.screenshot.side_effect = screens

        with patch("autowsgr.ui.page.time") as mock_time:
            mock_time.monotonic.return_value = 0.0
            mock_time.sleep = MagicMock()

            result = wait_for_page(
                ctrl,
                lambda s: s.mean() > 100,  # 白色屏幕才匹配
                timeout=10.0,
                interval=0.1,
                source="A",
                target="B",
            )

        assert np.array_equal(result, _white())
        assert ctrl.screenshot.call_count == 3

    def test_timeout_raises(self):
        """超时 → 抛出 NavigationError。"""
        ctrl = MagicMock(spec=AndroidController)
        ctrl.screenshot.return_value = _blank()

        # 模拟时间: 第一次 monotonic=0, deadline=0, 立即超时
        with patch("autowsgr.ui.page.time") as mock_time:
            call_count = 0

            def advancing_time():
                nonlocal call_count
                call_count += 1
                # 第一次 (设 deadline) 返回 0, 之后返回 100 (已超时)
                return 0.0 if call_count <= 1 else 100.0

            mock_time.monotonic.side_effect = advancing_time
            mock_time.sleep = MagicMock()

            with pytest.raises(NavigationError, match="超时"):
                wait_for_page(
                    ctrl,
                    lambda s: False,
                    timeout=1.0,
                    source="A",
                    target="B",
                )

    def test_timeout_message_contains_details(self):
        """超时异常消息包含 source 和 target。"""
        ctrl = MagicMock(spec=AndroidController)
        ctrl.screenshot.return_value = _blank()

        with patch("autowsgr.ui.page.time") as mock_time:
            counts = {"n": 0}

            def advancing():
                counts["n"] += 1
                return 0.0 if counts["n"] <= 1 else 100.0

            mock_time.monotonic.side_effect = advancing
            mock_time.sleep = MagicMock()

            with pytest.raises(NavigationError) as exc_info:
                wait_for_page(
                    ctrl,
                    lambda s: False,
                    timeout=1.0,
                    source="出征准备",
                    target="地图页面",
                )

            msg = str(exc_info.value)
            assert "出征准备" in msg
            assert "地图页面" in msg

    def test_default_constants(self):
        """默认超时和间隔值合理。"""
        assert DEFAULT_TIMEOUT > 0
        assert DEFAULT_INTERVAL > 0
        assert DEFAULT_INTERVAL < DEFAULT_TIMEOUT


# ─────────────────────────────────────────────
# wait_leave_page
# ─────────────────────────────────────────────


class TestWaitLeavePage:
    def test_immediate_leave(self):
        """第一次截图即已离开 → 立即返回。"""
        ctrl = MagicMock(spec=AndroidController)
        ctrl.screenshot.return_value = _blank()

        result = wait_leave_page(
            ctrl,
            lambda s: False,  # 不在原页面
            source="A",
            target="B",
        )
        assert result is not None
        ctrl.screenshot.assert_called_once()

    def test_leave_after_retries(self):
        """前两次仍在原页面，第三次离开。"""
        ctrl = MagicMock(spec=AndroidController)
        # 前两次 checker 返回 True (仍在), 第三次提供不同屏幕
        call_count = {"n": 0}

        def checker(s):
            call_count["n"] += 1
            return call_count["n"] <= 2

        ctrl.screenshot.return_value = _blank()

        with patch("autowsgr.ui.page.time") as mock_time:
            mock_time.monotonic.return_value = 0.0
            mock_time.sleep = MagicMock()

            result = wait_leave_page(
                ctrl,
                checker,
                timeout=10.0,
                interval=0.1,
                source="A",
                target="B",
            )

        assert result is not None
        assert ctrl.screenshot.call_count == 3

    def test_timeout_raises(self):
        """超时 → 抛出 NavigationError。"""
        ctrl = MagicMock(spec=AndroidController)
        ctrl.screenshot.return_value = _blank()

        with patch("autowsgr.ui.page.time") as mock_time:
            counts = {"n": 0}

            def advancing():
                counts["n"] += 1
                return 0.0 if counts["n"] <= 1 else 100.0

            mock_time.monotonic.side_effect = advancing
            mock_time.sleep = MagicMock()

            with pytest.raises(NavigationError, match="超时"):
                wait_leave_page(
                    ctrl,
                    lambda s: True,  # 始终在原页面
                    timeout=1.0,
                    source="A",
                    target="B",
                )


# ─────────────────────────────────────────────
# NavigationError
# ─────────────────────────────────────────────


class TestNavigationError:
    def test_is_exception(self):
        assert issubclass(NavigationError, Exception)

    def test_message(self):
        err = NavigationError("test message")
        assert str(err) == "test message"
