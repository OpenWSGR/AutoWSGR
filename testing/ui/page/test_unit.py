"""测试 UI 页面注册中心与导航验证工具。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from autowsgr.emulator import AndroidController
from autowsgr.ui.page import (
    _OVERLAY_PAGES,
    _PAGE_REGISTRY,
    get_current_page,
    register_page,
)
from autowsgr.ui.utils import (
    NavigationError,
    wait_for_page,
)
from autowsgr.vision import PageMatch


_W, _H = 960, 540


def _blank() -> np.ndarray:
    return np.zeros((_H, _W, 3), dtype=np.uint8)


def _white() -> np.ndarray:
    return np.full((_H, _W, 3), 255, dtype=np.uint8)


# ─────────────────────────────────────────────
# get_current_page
# ─────────────────────────────────────────────


class TestGetCurrentPage:
    def setup_method(self):
        self._backup = dict(_PAGE_REGISTRY)
        self._backup_overlay = set(_OVERLAY_PAGES)
        _PAGE_REGISTRY.clear()

    def teardown_method(self):
        _PAGE_REGISTRY.clear()
        _PAGE_REGISTRY.update(self._backup)
        _OVERLAY_PAGES.clear()
        _OVERLAY_PAGES.update(self._backup_overlay)

    def test_returns_first_match(self):
        register_page('always_true', lambda _s: True)
        register_page('also_true', lambda _s: True)
        result = get_current_page(_blank())
        assert result == 'always_true'

    def test_returns_none_when_no_match(self):
        register_page('never', lambda _s: False)
        assert get_current_page(_blank()) is None

    def test_empty_registry(self):
        assert get_current_page(_blank()) is None

    def test_skips_exception_checker(self):
        """识别器抛异常时跳过，不影响后续。"""

        def bad_checker(_s: np.ndarray):
            raise RuntimeError('boom')

        register_page('bad', bad_checker)
        register_page('good', lambda _s: True)
        assert get_current_page(_blank()) == 'good'

    def test_candidate_filtering(self):
        """candidates 限制只评估候选页:未在候选集的真页不返回。"""
        register_page('a', lambda _s: True)
        register_page('b', lambda _s: True)
        assert get_current_page(_blank(), candidates={'a'}) == 'a'
        assert get_current_page(_blank(), candidates=set()) is None

    def test_score_ranking(self):
        """命中多页时按 score 降序取最高分(而非注册顺序)。"""
        register_page('low', lambda _s: PageMatch(name='low', matched=True, score=0.5))
        register_page('high', lambda _s: PageMatch(name='high', matched=True, score=0.9))
        assert get_current_page(_blank()) == 'high'

    def test_register_order_tiebreak(self):
        """同分时按注册顺序(稳定排序)决胜。"""
        register_page('first', lambda _s: PageMatch(name='first', matched=True, score=0.8))
        register_page('second', lambda _s: PageMatch(name='second', matched=True, score=0.8))
        assert get_current_page(_blank()) == 'first'

    def test_bool_checker_normalized(self):
        """旧式 bool checker 归一化:True→score=1.0,胜过低分 PageMatch。"""
        register_page('bool_true', lambda _s: True)
        register_page('low_score', lambda _s: PageMatch(name='low_score', matched=True, score=0.7))
        assert get_current_page(_blank()) == 'bool_true'

    def test_unregistered_candidate_ignored(self):
        """候选集中未注册的名称被静默跳过。"""
        register_page('only', lambda _s: True)
        assert get_current_page(_blank(), candidates={'only', 'ghost'}) == 'only'

    def test_overlay_page_wins_over_higher_score_base(self):
        """覆盖型页面命中时优先于更高分的底页 (z-order 优先于分数)。

        实机场景: 侧边栏抽屉打开时不遮挡主页面识别元素, 主页面 0.988 与
        侧边栏 ~0.86 同时命中 — 纯分数排序误判为主页面, 导航反复点切换
        按钮把侧边栏开了又关 (2026-08-16 解装导航死循环)。
        """
        register_page('base', lambda _s: PageMatch(name='base', matched=True, score=0.988))
        register_page(
            'drawer', lambda _s: PageMatch(name='drawer', matched=True, score=0.86), overlay=True
        )
        assert get_current_page(_blank()) == 'drawer'

    def test_overlay_page_absent_falls_back_to_base(self):
        """覆盖型页面未命中时正常回退底页最高分。"""
        register_page('base', lambda _s: PageMatch(name='base', matched=True, score=0.988))
        register_page(
            'drawer', lambda _s: PageMatch(name='drawer', matched=False, score=0.0), overlay=True
        )
        assert get_current_page(_blank()) == 'base'

    def test_overlay_pages_ranked_by_score(self):
        """多个覆盖型同时命中时, 覆盖集内按分数降序。"""
        register_page(
            'drawer_low',
            lambda _s: PageMatch(name='drawer_low', matched=True, score=0.82),
            overlay=True,
        )
        register_page(
            'drawer_high',
            lambda _s: PageMatch(name='drawer_high', matched=True, score=0.86),
            overlay=True,
        )
        assert get_current_page(_blank()) == 'drawer_high'

    def test_overlay_flag_reregistration_updates(self):
        """重注册同名页面时 overlay 标记同步更新 (先 overlay 后普通则移出集合)。"""
        register_page('page', lambda _s: True, overlay=True)
        assert 'page' in _OVERLAY_PAGES
        register_page('page', lambda _s: True)
        assert 'page' not in _OVERLAY_PAGES


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
            lambda _s: True,
            source='A',
            target='B',
        )
        assert result is not None
        ctrl.screenshot.assert_called_once()

    def test_success_after_retries(self):
        """前两次不匹配，第三次匹配。"""
        ctrl = MagicMock(spec=AndroidController)
        screens = [_blank(), _blank(), _white()]
        ctrl.screenshot.side_effect = screens

        with patch('autowsgr.ui.utils.navigation.time') as mock_time:
            mock_time.monotonic.return_value = 0.0
            mock_time.sleep = MagicMock()

            result = wait_for_page(
                ctrl,
                lambda s: s.mean() > 100,  # 白色屏幕才匹配
                timeout=10.0,
                interval=0.1,
                handle_overlays=False,  # 白屏会误匹配 NEWS 浮层签名
                source='A',
                target='B',
            )

        assert np.array_equal(result, _white())
        assert ctrl.screenshot.call_count == 3

    def test_timeout_raises(self):
        """超时 → 抛出 NavigationError。"""
        ctrl = MagicMock(spec=AndroidController)
        ctrl.screenshot.return_value = _blank()

        # 模拟时间: 第一次 monotonic=0, deadline=0, 立即超时
        with patch('autowsgr.ui.utils.navigation.time') as mock_time:
            call_count = 0

            def advancing_time() -> float:
                nonlocal call_count
                call_count += 1
                # 第一次 (设 deadline) 返回 0, 之后返回 100 (已超时)
                return 0.0 if call_count <= 1 else 100.0

            mock_time.monotonic.side_effect = advancing_time
            mock_time.sleep = MagicMock()

            with pytest.raises(NavigationError, match='超时'):
                wait_for_page(
                    ctrl,
                    lambda _s: False,
                    timeout=1.0,
                    source='A',
                    target='B',
                )
