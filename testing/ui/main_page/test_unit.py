"""测试 主页面 UI 控制器。"""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from autowsgr.emulator import AndroidController
from autowsgr.ui.main_page import (
    CLICK_NAV,
    PAGE_SIGNATURE,
    MainPage,
    MainPageTarget,
)
from autowsgr.ui.tabbed_page import TabbedPageType


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

_W, _H = 960, 540

# 需要 mock identify_page_type 的导航目标
_NAVIGATE_PATCHES: dict[MainPageTarget, tuple[str, TabbedPageType]] = {
    MainPageTarget.SORTIE: (
        "autowsgr.ui.map.page.identify_page_type",
        TabbedPageType.MAP,
    ),
    MainPageTarget.TASK: (
        "autowsgr.ui.mission_page.identify_page_type",
        TabbedPageType.MISSION,
    ),
}


def _set_pixel(
    screen: np.ndarray, rx: float, ry: float, rgb: tuple[int, int, int]
) -> None:
    """在相对坐标处设置像素颜色。"""
    h, w = screen.shape[:2]
    px, py = int(rx * w), int(ry * h)
    screen[py, px] = rgb


def _make_main_screen() -> np.ndarray:
    """生成主页面合成截图 (特征点全部正确)。"""
    screen = np.zeros((_H, _W, 3), dtype=np.uint8)
    for rule in PAGE_SIGNATURE.rules:
        _set_pixel(screen, rule.x, rule.y, rule.color.as_rgb_tuple())
    return screen


def _make_non_main_screen() -> np.ndarray:
    return np.zeros((_H, _W, 3), dtype=np.uint8)


def _make_target_screen(target: MainPageTarget) -> np.ndarray:
    """生成匹配导航目标页面签名的合成截图。"""
    screen = np.zeros((_H, _W, 3), dtype=np.uint8)
    if target in (MainPageTarget.SORTIE, MainPageTarget.TASK):
        from autowsgr.ui.tabbed_page import TAB_BLUE, TAB_DARK, TAB_PROBES
        for i, (x, y) in enumerate(TAB_PROBES):
            if i == 0:
                _set_pixel(screen, x, y, TAB_BLUE.as_rgb_tuple())
            else:
                _set_pixel(screen, x, y, TAB_DARK)
    elif target == MainPageTarget.SIDEBAR:
        from autowsgr.ui.sidebar_page import MENU_PROBES, _MENU_GRAY
        for mx, my in MENU_PROBES:
            _set_pixel(screen, mx, my, _MENU_GRAY.as_rgb_tuple())
    elif target == MainPageTarget.HOME:
        from autowsgr.ui.backyard_page import PAGE_SIGNATURE as BACKYARD_SIG
        for rule in BACKYARD_SIG.rules:
            _set_pixel(screen, rule.x, rule.y, rule.color.as_rgb_tuple())
    return screen


# ─────────────────────────────────────────────
# 页面识别
# ─────────────────────────────────────────────


class TestIsCurrentPage:
    def test_main_page_detected(self):
        screen = _make_main_screen()
        assert MainPage.is_current_page(screen) is True

    def test_blank_screen_not_detected(self):
        screen = np.zeros((_H, _W, 3), dtype=np.uint8)
        assert MainPage.is_current_page(screen) is False

    def test_non_main_page_not_detected(self):
        screen = _make_non_main_screen()
        assert MainPage.is_current_page(screen) is False

    def test_one_pixel_wrong_not_detected(self):
        """ALL 策略下，任一像素不匹配即失败。"""
        screen = _make_main_screen()
        first_rule = PAGE_SIGNATURE.rules[0]
        _set_pixel(screen, first_rule.x, first_rule.y, (0, 0, 0))
        assert MainPage.is_current_page(screen) is False

    def test_slight_color_deviation_accepted(self):
        """容差范围内的颜色偏差仍可匹配。"""
        screen = _make_main_screen()
        first_rule = PAGE_SIGNATURE.rules[0]
        r, g, b = first_rule.color.as_rgb_tuple()
        _set_pixel(
            screen,
            first_rule.x,
            first_rule.y,
            (min(r + 10, 255), max(g - 10, 0), min(b + 5, 255)),
        )
        assert MainPage.is_current_page(screen) is True


# ─────────────────────────────────────────────
# 导航
# ─────────────────────────────────────────────


class TestNavigateTo:
    @pytest.fixture()
    def page(self):
        ctrl = MagicMock(spec=AndroidController)
        return MainPage(ctrl), ctrl

    @pytest.mark.parametrize("target", list(MainPageTarget))
    def test_navigate_calls_click(self, page, target: MainPageTarget):
        pg, ctrl = page
        ctrl.screenshot.return_value = _make_target_screen(target)
        with ExitStack() as stack:
            if target in _NAVIGATE_PATCHES:
                mod, rv = _NAVIGATE_PATCHES[target]
                stack.enter_context(patch(mod, return_value=rv))
            pg.navigate_to(target)
        ctrl.click.assert_called_with(*CLICK_NAV[target])

    def test_go_to_sortie(self, page):
        pg, ctrl = page
        ctrl.screenshot.return_value = _make_target_screen(MainPageTarget.SORTIE)
        with patch("autowsgr.ui.map.page.identify_page_type",
                   return_value=TabbedPageType.MAP):
            pg.go_to_sortie()
        ctrl.click.assert_called_with(*CLICK_NAV[MainPageTarget.SORTIE])

    def test_go_to_task(self, page):
        pg, ctrl = page
        ctrl.screenshot.return_value = _make_target_screen(MainPageTarget.TASK)
        with patch("autowsgr.ui.mission_page.identify_page_type",
                   return_value=TabbedPageType.MISSION):
            pg.go_to_task()
        ctrl.click.assert_called_with(*CLICK_NAV[MainPageTarget.TASK])

    def test_open_sidebar(self, page):
        pg, ctrl = page
        ctrl.screenshot.return_value = _make_target_screen(MainPageTarget.SIDEBAR)
        pg.open_sidebar()
        ctrl.click.assert_called_with(*CLICK_NAV[MainPageTarget.SIDEBAR])

    def test_go_home(self, page):
        pg, ctrl = page
        ctrl.screenshot.return_value = _make_target_screen(MainPageTarget.HOME)
        pg.go_home()
        ctrl.click.assert_called_with(*CLICK_NAV[MainPageTarget.HOME])


# ─────────────────────────────────────────────
# 返回
# ─────────────────────────────────────────────


# ─────────────────────────────────────────────
# 常量一致性
# ─────────────────────────────────────────────


class TestConstants:
    def test_all_targets_have_nav(self):
        """每个目标都有导航坐标。"""
        for target in MainPageTarget:
            assert target in CLICK_NAV

    def test_nav_coords_in_range(self):
        """导航坐标在 [0, 1] 范围内。"""
        for target, (x, y) in CLICK_NAV.items():
            assert 0.0 <= x <= 1.0, f"{target}: x={x}"
            assert 0.0 <= y <= 1.0, f"{target}: y={y}"


