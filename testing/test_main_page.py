"""测试 主页面 UI 控制器。"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from autowsgr.emulator.controller import AndroidController
from autowsgr.ui.main_page import (
    CLICK_EXIT,
    CLICK_NAV,
    EXIT_SIDEBAR,
    EXIT_TOP_LEFT,
    PAGE_SIGNATURE,
    MainPage,
    MainPageTarget,
)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

_W, _H = 960, 540


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
    """生成一个不匹配主页面的截图。"""
    return np.zeros((_H, _W, 3), dtype=np.uint8)


def _make_target_screen(target: MainPageTarget) -> np.ndarray:
    """生成匹配导航目标页面签名的合成截图。

    navigate_to 现在使用 click_and_wait_for_page 进行正向验证，
    需要截图匹配目标页面的签名。
    """
    screen = np.zeros((_H, _W, 3), dtype=np.uint8)

    if target == MainPageTarget.SORTIE:
        # MapPage: 5个面板探测点中恰好1个为选中蓝色
        from autowsgr.ui.map_page import PANEL_PROBE, MapPanel
        sx, sy = PANEL_PROBE[MapPanel.SORTIE]
        _set_pixel(screen, sx, sy, (15, 128, 220))
    elif target == MainPageTarget.TASK:
        from autowsgr.ui.mission_page import PAGE_SIGNATURE as MISSION_SIG
        for rule in MISSION_SIG.rules:
            _set_pixel(screen, rule.x, rule.y, rule.color.as_rgb_tuple())
    elif target == MainPageTarget.SIDEBAR:
        from autowsgr.ui.sidebar_page import PAGE_SIGNATURE as SIDEBAR_SIG
        for rule in SIDEBAR_SIG.rules:
            _set_pixel(screen, rule.x, rule.y, rule.color.as_rgb_tuple())
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
        """其他页面不应被识别为主页面。"""
        screen = _make_non_main_screen()
        assert MainPage.is_current_page(screen) is False

    def test_one_pixel_wrong_not_detected(self):
        """ALL 策略下，任一像素不匹配即失败。"""
        screen = _make_main_screen()
        # 破坏第一个特征点
        first_rule = PAGE_SIGNATURE.rules[0]
        _set_pixel(screen, first_rule.x, first_rule.y, (0, 0, 0))
        assert MainPage.is_current_page(screen) is False

    def test_slight_color_deviation_accepted(self):
        """容差范围内的颜色偏差仍可匹配。"""
        screen = _make_main_screen()
        first_rule = PAGE_SIGNATURE.rules[0]
        r, g, b = first_rule.color.as_rgb_tuple()
        # 偏移 10 (在 tolerance=30 内), clamp to uint8 范围
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
        # navigate_to 使用 click_and_wait_for_page 正向验证目标页面
        ctrl.screenshot.return_value = _make_target_screen(target)
        pg.navigate_to(target)
        ctrl.click.assert_called_with(*CLICK_NAV[target])

    @pytest.mark.parametrize("target", list(MainPageTarget))
    def test_navigate_verifies_screenshot(self, page, target: MainPageTarget):
        """导航后调用 screenshot 进行验证。"""
        pg, ctrl = page
        ctrl.screenshot.return_value = _make_target_screen(target)
        pg.navigate_to(target)
        ctrl.screenshot.assert_called()

    def test_go_to_sortie(self, page):
        pg, ctrl = page
        ctrl.screenshot.return_value = _make_target_screen(MainPageTarget.SORTIE)
        pg.go_to_sortie()
        ctrl.click.assert_called_with(*CLICK_NAV[MainPageTarget.SORTIE])

    def test_go_to_task(self, page):
        pg, ctrl = page
        ctrl.screenshot.return_value = _make_target_screen(MainPageTarget.TASK)
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


class TestReturnFrom:
    @pytest.fixture()
    def page(self):
        ctrl = MagicMock(spec=AndroidController)
        # return_from 验证回到主页面
        ctrl.screenshot.return_value = _make_main_screen()
        return MainPage(ctrl), ctrl

    @pytest.mark.parametrize("target", list(MainPageTarget))
    def test_return_calls_exit(self, page, target: MainPageTarget):
        pg, ctrl = page
        pg.return_from(target)
        ctrl.click.assert_called_with(*CLICK_EXIT[target])

    @pytest.mark.parametrize("target", list(MainPageTarget))
    def test_return_verifies_screenshot(self, page, target: MainPageTarget):
        """返回后调用 screenshot 验证回到主页面。"""
        pg, ctrl = page
        pg.return_from(target)
        ctrl.screenshot.assert_called()

    def test_sortie_exits_top_left(self, page):
        pg, ctrl = page
        pg.return_from(MainPageTarget.SORTIE)
        ctrl.click.assert_called_with(*EXIT_TOP_LEFT)

    def test_task_exits_top_left(self, page):
        pg, ctrl = page
        pg.return_from(MainPageTarget.TASK)
        ctrl.click.assert_called_with(*EXIT_TOP_LEFT)

    def test_home_exits_top_left(self, page):
        pg, ctrl = page
        pg.return_from(MainPageTarget.HOME)
        ctrl.click.assert_called_with(*EXIT_TOP_LEFT)

    def test_sidebar_exits_bottom_left(self, page):
        pg, ctrl = page
        pg.return_from(MainPageTarget.SIDEBAR)
        ctrl.click.assert_called_with(*EXIT_SIDEBAR)


# ─────────────────────────────────────────────
# 枚举
# ─────────────────────────────────────────────


class TestMainPageTarget:
    def test_values(self):
        assert MainPageTarget.SORTIE.value == "出征"
        assert MainPageTarget.TASK.value == "任务"
        assert MainPageTarget.SIDEBAR.value == "侧边栏"
        assert MainPageTarget.HOME.value == "主页"

    def test_count(self):
        assert len(MainPageTarget) == 4


# ─────────────────────────────────────────────
# 常量一致性
# ─────────────────────────────────────────────


class TestConstants:
    def test_all_targets_have_nav(self):
        """每个目标都有导航坐标。"""
        for target in MainPageTarget:
            assert target in CLICK_NAV

    def test_all_targets_have_exit(self):
        """每个目标都有退出坐标。"""
        for target in MainPageTarget:
            assert target in CLICK_EXIT

    def test_page_signature_has_rules(self):
        assert len(PAGE_SIGNATURE.rules) == 7

    def test_nav_coords_in_range(self):
        """导航坐标在 [0, 1] 范围内。"""
        for target, (x, y) in CLICK_NAV.items():
            assert 0.0 <= x <= 1.0, f"{target}: x={x}"
            assert 0.0 <= y <= 1.0, f"{target}: y={y}"

    def test_exit_coords_in_range(self):
        for target, (x, y) in CLICK_EXIT.items():
            assert 0.0 <= x <= 1.0, f"{target}: x={x}"
            assert 0.0 <= y <= 1.0, f"{target}: y={y}"

    def test_sidebar_exit_matches_nav(self):
        """侧边栏退出坐标与导航坐标相同 (同一切换按钮)。"""
        assert CLICK_EXIT[MainPageTarget.SIDEBAR] == CLICK_NAV[MainPageTarget.SIDEBAR]
