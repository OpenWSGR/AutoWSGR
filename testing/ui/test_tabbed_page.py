"""测试 标签页面统一检测层。"""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pytest

from autowsgr.ui.tabbed_page import (
    TAB_BLUE,
    TAB_BLUE_TOLERANCE,
    TAB_DARK,
    TAB_DARK_MAX,
    TAB_PROBES,
    TabbedPageType,
    get_active_tab_index,
    identify_page_type,
    is_tabbed_page,
    make_page_checker,
    make_tab_checker,
)
from autowsgr.vision.matcher import Color


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

_W, _H = 960, 540

_MATCH = "autowsgr.ui.tabbed_page._match_page_type"
"""mock 目标: 模板匹配函数。"""


def _set_pixel(
    screen: np.ndarray, rx: float, ry: float, rgb: tuple[int, int, int]
) -> None:
    """在相对坐标处设置像素颜色。"""
    h, w = screen.shape[:2]
    px, py = int(rx * w), int(ry * h)
    screen[py, px] = rgb


def _make_tabbed_screen(
    active_tab: int = 0,
    width: int = _W,
    height: int = _H,
) -> np.ndarray:
    """生成通过 is_tabbed_page 检测的合成截图。

    仅设置标签栏探测点 (1 蓝 + 4 暗)。
    不含真实标签栏纹理，需配合 mock _match_page_type 使用。

    Parameters
    ----------
    active_tab:
        激活标签索引 (0–4)。
    width, height:
        截图尺寸。
    """
    screen = np.zeros((height, width, 3), dtype=np.uint8)
    for i, (cx, cy) in enumerate(TAB_PROBES):
        if i == active_tab:
            _set_pixel(screen, cx, cy, TAB_BLUE.as_rgb_tuple())
        else:
            _set_pixel(screen, cx, cy, TAB_DARK)
    return screen


# ─────────────────────────────────────────────
# is_tabbed_page
# ─────────────────────────────────────────────


class TestIsTabbedPage:
    def test_valid_screen(self):
        screen = _make_tabbed_screen(active_tab=0)
        assert is_tabbed_page(screen) is True

    def test_blank_screen(self):
        screen = np.zeros((_H, _W, 3), dtype=np.uint8)
        assert is_tabbed_page(screen) is False

    def test_two_blue_probes(self):
        """两个探测点同时蓝色 → 不是标签页。"""
        screen = _make_tabbed_screen(active_tab=0)
        _set_pixel(screen, *TAB_PROBES[1], TAB_BLUE.as_rgb_tuple())
        assert is_tabbed_page(screen) is False

    def test_no_blue_probe(self):
        """所有探测点都暗色 → 不是标签页。"""
        screen = np.zeros((_H, _W, 3), dtype=np.uint8)
        for x, y in TAB_PROBES:
            _set_pixel(screen, x, y, TAB_DARK)
        assert is_tabbed_page(screen) is False

    def test_one_non_dark_non_blue(self):
        """一个蓝色 + 一个非暗非蓝 → 不是标签页。"""
        screen = _make_tabbed_screen(active_tab=0)
        _set_pixel(screen, *TAB_PROBES[1], (200, 200, 200))
        assert is_tabbed_page(screen) is False

    @pytest.mark.parametrize("tab_idx", range(5))
    def test_each_tab_index(self, tab_idx: int):
        """每个标签位置都能触发检测。"""
        screen = _make_tabbed_screen(active_tab=tab_idx)
        assert is_tabbed_page(screen) is True

    def test_different_resolution(self):
        """1920×1080 分辨率下也能检测。"""
        screen = _make_tabbed_screen(active_tab=2, width=1920, height=1080)
        assert is_tabbed_page(screen) is True


# ─────────────────────────────────────────────
# get_active_tab_index
# ─────────────────────────────────────────────


class TestGetActiveTabIndex:
    @pytest.mark.parametrize("idx", range(5))
    def test_each_index(self, idx: int):
        screen = _make_tabbed_screen(active_tab=idx)
        assert get_active_tab_index(screen) == idx

    def test_no_blue(self):
        screen = np.zeros((_H, _W, 3), dtype=np.uint8)
        assert get_active_tab_index(screen) is None


# ─────────────────────────────────────────────
# identify_page_type (模板匹配 via mock)
# ─────────────────────────────────────────────


class TestIdentifyPageType:
    @pytest.mark.parametrize("page_type", list(TabbedPageType))
    def test_each_page_type(self, page_type: TabbedPageType):
        """模板匹配返回正确类型 → identify_page_type 转发结果。"""
        screen = _make_tabbed_screen(active_tab=0)
        with patch(_MATCH, return_value=page_type):
            assert identify_page_type(screen) == page_type

    def test_blank_screen(self):
        """空白屏幕不通过 is_tabbed_page → 直接返回 None。"""
        assert identify_page_type(np.zeros((_H, _W, 3), dtype=np.uint8)) is None

    def test_non_tabbed_skips_match(self):
        """非标签页不会调用 _match_page_type。"""
        screen = np.zeros((_H, _W, 3), dtype=np.uint8)
        with patch(_MATCH) as mock_match:
            identify_page_type(screen)
            mock_match.assert_not_called()

    def test_tabbed_calls_match(self):
        """标签页调用 _match_page_type。"""
        screen = _make_tabbed_screen(active_tab=0)
        with patch(_MATCH, return_value=TabbedPageType.MAP) as mock_match:
            identify_page_type(screen)
            mock_match.assert_called_once()

    def test_match_returns_none(self):
        """模板匹配无结果 → identify_page_type 返回 None。"""
        screen = _make_tabbed_screen(active_tab=0)
        with patch(_MATCH, return_value=None):
            assert identify_page_type(screen) is None


# ─────────────────────────────────────────────
# make_tab_checker / make_page_checker
# ─────────────────────────────────────────────


class TestMakeCheckers:
    def test_tab_checker_matches(self):
        checker = make_tab_checker(TabbedPageType.BUILD, tab_index=2)
        screen = _make_tabbed_screen(active_tab=2)
        with patch(_MATCH, return_value=TabbedPageType.BUILD):
            assert checker(screen) is True

    def test_tab_checker_wrong_tab(self):
        checker = make_tab_checker(TabbedPageType.BUILD, tab_index=2)
        screen = _make_tabbed_screen(active_tab=0)
        with patch(_MATCH, return_value=TabbedPageType.BUILD):
            assert checker(screen) is False

    def test_tab_checker_wrong_page(self):
        checker = make_tab_checker(TabbedPageType.BUILD, tab_index=0)
        screen = _make_tabbed_screen(active_tab=0)
        with patch(_MATCH, return_value=TabbedPageType.INTENSIFY):
            assert checker(screen) is False

    def test_page_checker_matches(self):
        checker = make_page_checker(TabbedPageType.MAP)
        screen = _make_tabbed_screen(active_tab=3)
        with patch(_MATCH, return_value=TabbedPageType.MAP):
            assert checker(screen) is True

    def test_page_checker_wrong_page(self):
        checker = make_page_checker(TabbedPageType.MAP)
        screen = _make_tabbed_screen(active_tab=0)
        with patch(_MATCH, return_value=TabbedPageType.BUILD):
            assert checker(screen) is False

    def test_page_checker_any_tab(self):
        """page_checker 不限定标签。"""
        checker = make_page_checker(TabbedPageType.MAP)
        for idx in range(5):
            screen = _make_tabbed_screen(active_tab=idx)
            with patch(_MATCH, return_value=TabbedPageType.MAP):
                assert checker(screen) is True


# ─────────────────────────────────────────────
# 边界条件
# ─────────────────────────────────────────────


class TestEdgeCases:
    def test_near_blue_but_out_of_tolerance(self):
        """颜色接近蓝色但超出容差 → 不检测为蓝色。"""
        screen = np.zeros((_H, _W, 3), dtype=np.uint8)
        for x, y in TAB_PROBES:
            _set_pixel(screen, x, y, TAB_DARK)
        # 设置一个偏差较大的 "蓝色"
        far_blue = (15 + 30, 132 + 30, 228 - 30)  # 距离 ≈ 51.9 > 35
        _set_pixel(screen, *TAB_PROBES[0], far_blue)
        assert is_tabbed_page(screen) is False

    def test_pages_mutually_exclusive(self):
        """每种页面类型不会被误识别为其他类型 (mock 确保正确路由)。"""
        for page_type in TabbedPageType:
            screen = _make_tabbed_screen(active_tab=0)
            with patch(_MATCH, return_value=page_type):
                result = identify_page_type(screen)
            assert result == page_type
            for other in TabbedPageType:
                if other != page_type:
                    assert result != other

    def test_map_page_from_build_page(self):
        """地图页面和建造页面不会互相混淆 (mock 层面)。"""
        from autowsgr.ui.build_page import BuildPage
        from autowsgr.ui.map_page import MapPage

        screen = _make_tabbed_screen(active_tab=0)
        with patch(_MATCH, return_value=TabbedPageType.MAP):
            assert MapPage.is_current_page(screen) is True
            assert BuildPage.is_current_page(screen) is False
        with patch(_MATCH, return_value=TabbedPageType.BUILD):
            assert BuildPage.is_current_page(screen) is True
            assert MapPage.is_current_page(screen) is False

    def test_build_not_confused_with_friend(self):
        """建造页面和好友页面不会混淆 (mock 层面)。"""
        from autowsgr.ui.build_page import BuildPage
        from autowsgr.ui.friend_page import FriendPage

        screen = _make_tabbed_screen(active_tab=0)
        with patch(_MATCH, return_value=TabbedPageType.BUILD):
            assert BuildPage.is_current_page(screen) is True
            assert FriendPage.is_current_page(screen) is False
        with patch(_MATCH, return_value=TabbedPageType.FRIEND):
            assert FriendPage.is_current_page(screen) is True
            assert BuildPage.is_current_page(screen) is False

    def test_intensify_not_confused_with_build(self):
        """强化页面和建造页面不会混淆 (mock 层面)。"""
        from autowsgr.ui.build_page import BuildPage
        from autowsgr.ui.intensify_page import IntensifyPage

        screen = _make_tabbed_screen(active_tab=0)
        with patch(_MATCH, return_value=TabbedPageType.INTENSIFY):
            assert IntensifyPage.is_current_page(screen) is True
            assert BuildPage.is_current_page(screen) is False
        with patch(_MATCH, return_value=TabbedPageType.BUILD):
            assert BuildPage.is_current_page(screen) is True
            assert IntensifyPage.is_current_page(screen) is False
