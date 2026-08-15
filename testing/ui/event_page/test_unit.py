"""活动地图页面控制器的无设备单元测试 (mock, 不连真机)。

覆盖三个关键路径:
  - ``is_current_page``: 三层锚点 (出击按钮浮层态 / 难度图标干净页 / 标题兜底)
  - ``_enter_node``: 出击按钮出现确认节点选择成功 (单帧, 替代旧双帧浮层检测)
  - ``go_back``: 纯模板驱动 (出击按钮可见 = 浮层在 → 点红色 X; 否则点返回)
  - ``ensure_no_overlay``: 出击按钮可见 = 浮层在 → 点 X → 按钮消失确认
"""

from __future__ import annotations

from unittest.mock import MagicMock, call

import numpy as np
import pytest

from autowsgr.infra.exceptions import ActionFailedError
from autowsgr.types import PageName
from autowsgr.ui.event.event_page import (
    CLICK_BACK,
    CLICK_CLOSE_NODE_OVERLAY,
    NODE_POSITIONS_BY_EVENT,
    BaseEventPage,
)
from autowsgr.vision import ImageMatchDetail


def _gradient_screen(lo: int = 80, hi: int = 180) -> np.ndarray:
    """连续渐变图 (模拟真实 UI 背景)。"""
    xs = np.tile(np.linspace(0, 1, 960), (540, 1))
    return ((lo + xs * (hi - lo))[:, :, None].repeat(3, 2)).astype(np.uint8)


def _button_detail(confidence: float = 0.9) -> ImageMatchDetail:
    """构造出击按钮匹配结果。"""
    return ImageMatchDetail(
        template_name='fight_button',
        confidence=confidence,
        center=(0.83, 0.84),
        top_left=(0.78, 0.80),
        bottom_right=(0.88, 0.88),
    )


def _make_page() -> tuple[BaseEventPage, MagicMock]:
    """构造一个绑定 mock 控制器的 BaseEventPage。"""
    ctx = MagicMock()
    page = BaseEventPage(ctx, event_name='20260730')
    return page, ctx.ctrl


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """屏蔽真实 sleep, 加速 _enter_node/go_back 的等待循环。"""
    monkeypatch.setattr('autowsgr.ui.event.event_page.time.sleep', lambda *_: None)


def _mock_fight_button(
    monkeypatch: pytest.MonkeyPatch, details: list[ImageMatchDetail | None]
) -> None:
    """按帧序列 mock 出击按钮匹配 (None = 按钮不可见/浮层未开)。"""
    monkeypatch.setattr(
        BaseEventPage,
        '_fight_button_detail',
        staticmethod(MagicMock(side_effect=details)),
    )


# ─────────────────────────────────────────────
# is_current_page (三层锚点)
# ─────────────────────────────────────────────


class TestIsCurrentPage:
    """背景 (实机 2026-08-15 日志): 战后活动页落浮层态, 标题仍命中 (0.928)
    但难度图标被遮挡, 无法区分干净页/浮层页 → 误判连锁。"""

    def test_fight_button_means_overlay_state(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """出击按钮可见 → 浮层态也算活动页 (战后 goto_page(EVENT_MAP) 不失败)。"""
        _mock_fight_button(monkeypatch, [_button_detail()])
        result = BaseEventPage.is_current_page(_gradient_screen())
        assert result.matched
        assert result.score == pytest.approx(0.9)

    def test_difficulty_icon_means_clean_page(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """难度图标可见 (无出击按钮) → 干净活动页。"""
        _mock_fight_button(monkeypatch, [None])
        monkeypatch.setattr(
            BaseEventPage,
            '_difficulty_icon_state',
            staticmethod(MagicMock(return_value='H')),
        )
        result = BaseEventPage.is_current_page(_gradient_screen())
        assert result.matched

    def test_title_fallback_below_anchors(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """按钮/图标都不可见, 标题命中 → 兜底 matched, 但 score 低于锚点层。"""
        _mock_fight_button(monkeypatch, [None])
        monkeypatch.setattr(
            BaseEventPage,
            '_difficulty_icon_state',
            staticmethod(MagicMock(return_value=None)),
        )
        from autowsgr.ui.event import event_page as ep

        monkeypatch.setattr(
            ep,
            '_get_event_title_templates',
            list,
        )
        # 标题模板为空 → find_any 返回 None → 不匹配 (新活动未截标题图的场景)
        result = BaseEventPage.is_current_page(_gradient_screen())
        assert not result.matched

    def test_no_anchor_no_match(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """三层锚点全不命中 → 不是活动页。"""
        _mock_fight_button(monkeypatch, [None])
        monkeypatch.setattr(
            BaseEventPage,
            '_difficulty_icon_state',
            staticmethod(MagicMock(return_value=None)),
        )
        result = BaseEventPage.is_current_page(_gradient_screen())
        assert not result.matched
        assert result.name == str(PageName.EVENT_MAP)


# ─────────────────────────────────────────────
# _enter_node (出击按钮出现 = 浮层弹出)
# ─────────────────────────────────────────────


class TestEnterNode:
    def test_success_detects_fight_button(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """点击节点后出击按钮出现 → 选择成功, 第 1 次复查即停。"""
        page, ctrl = _make_page()
        _mock_fight_button(monkeypatch, [_button_detail()])

        page._enter_node(1)

        x, y = NODE_POSITIONS_BY_EVENT['20260730'][1]
        ctrl.click.assert_called_once_with(x, y)
        assert ctrl.screenshot.call_count == 1

    def test_failure_raises_when_button_never_appears(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """按钮始终不出现 (浮层未弹出) → 循环耗尽 → ActionFailedError。"""
        page, ctrl = _make_page()
        _mock_fight_button(monkeypatch, [None] * 10)

        with pytest.raises(ActionFailedError):
            page._enter_node(1)
        assert ctrl.screenshot.call_count == 10


# ─────────────────────────────────────────────
# go_back (纯模板驱动)
# ─────────────────────────────────────────────


class TestGoBack:
    def test_already_at_main_returns(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """已在主页面 → 直接返回, 不点击。"""
        page, ctrl = _make_page()
        monkeypatch.setattr(
            'autowsgr.ui.main_page.MainPage.is_current_page', MagicMock(return_value=True)
        )

        page.go_back()

        ctrl.click.assert_not_called()

    def test_overlay_visible_closes_first(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """出击按钮可见 (关卡浮层在) → 点红色 X 而非点返回, 下轮到达主页。"""
        page, ctrl = _make_page()
        frame = _gradient_screen()
        main_frame = _gradient_screen(lo=200, hi=210)
        # 第一帧按钮可见 (浮层在) → 点 X; 第二帧干净 → 点返回; 轮询帧到主页
        ctrl.screenshot.side_effect = [frame, frame, main_frame]
        _mock_fight_button(monkeypatch, [_button_detail(), None])
        monkeypatch.setattr(
            'autowsgr.ui.main_page.MainPage.is_current_page',
            MagicMock(side_effect=[False, False, True]),
        )

        page.go_back()

        assert ctrl.click.call_args_list == [
            call(*CLICK_CLOSE_NODE_OVERLAY),
            call(*CLICK_BACK),
        ]

    def test_back_effective_single_click(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """干净页点返回生效, 轮询窗口内到主页 → 只点一次返回 (防连点过冲)。"""
        page, ctrl = _make_page()
        frame = _gradient_screen()
        main_frame = _gradient_screen(lo=200, hi=210)
        # 第一帧干净 → 点返回; 轮询帧到主页 → 返回
        ctrl.screenshot.side_effect = [frame, main_frame]
        _mock_fight_button(monkeypatch, [None])
        monkeypatch.setattr(
            'autowsgr.ui.main_page.MainPage.is_current_page',
            MagicMock(side_effect=[False, True]),
        )

        page.go_back()

        assert ctrl.click.call_args_list == [call(*CLICK_BACK)]

    def test_timeout_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """始终不在主页且无浮层 → 15s 超时 → NavigationError。"""
        from itertools import count

        from autowsgr.ui.utils import NavigationError

        page, ctrl = _make_page()
        ctrl.screenshot.return_value = _gradient_screen()
        monkeypatch.setattr(
            'autowsgr.ui.main_page.MainPage.is_current_page', MagicMock(return_value=False)
        )
        monkeypatch.setattr(
            BaseEventPage, '_fight_button_detail', staticmethod(MagicMock(return_value=None))
        )
        # time.sleep 已被 _no_sleep 屏蔽; mock monotonic 递增驱动超时
        monkeypatch.setattr(
            'autowsgr.ui.event.event_page.time.monotonic',
            MagicMock(side_effect=count(0, 1)),
        )

        with pytest.raises(NavigationError):
            page.go_back()


# ─────────────────────────────────────────────
# ensure_no_overlay (战后浮层清理: 出击按钮锚点)
# ─────────────────────────────────────────────


class TestEnsureNoOverlay:
    """背景 (实机 2026-08-15 日志): H5 打完一场回港, 活动页直接落在关卡详情
    浮层态 (战后 UI 流转跳过出征准备页), 模态浮层拦截一切点击 → 死循环。"""

    def test_clean_page_noop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """出击按钮不可见 → 已是干净页, 不点击。"""
        page, ctrl = _make_page()
        ctrl.screenshot.return_value = _gradient_screen()
        _mock_fight_button(monkeypatch, [None])

        page.ensure_no_overlay()

        ctrl.click.assert_not_called()

    def test_overlay_closed_then_button_gone(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """按钮可见 (浮层在) → 点 X 后按钮消失 → 关闭成功, 只点一次。"""
        page, ctrl = _make_page()
        _mock_fight_button(monkeypatch, [_button_detail(), None])

        page.ensure_no_overlay()

        assert ctrl.click.call_args_list == [call(*CLICK_CLOSE_NODE_OVERLAY)]

    def test_gives_up_after_three_rounds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """按钮一直可见 (点 X 无效) → 3 轮后放弃。"""
        page, ctrl = _make_page()
        _mock_fight_button(monkeypatch, [_button_detail()] * 4)

        page.ensure_no_overlay()

        assert ctrl.click.call_count == 3
