"""测试 地图页面 UI 控制器。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from autowsgr.emulator.controller import AndroidController
from autowsgr.ui.map_page import (
    CHAPTER_NAV_DELAY,
    CHAPTER_SPACING,
    CLICK_BACK,
    CLICK_PANEL,
    EXPEDITION_NOTIF_PROBE,
    PANEL_PROBE,
    SIDEBAR_BRIGHTNESS_THRESHOLD,
    SIDEBAR_CLICK_X,
    SIDEBAR_SCAN_X,
    SIDEBAR_SCAN_Y_RANGE,
    TOTAL_CHAPTERS,
    MapIdentity,
    MapPage,
    MapPanel,
    parse_map_title,
)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

# 参考颜色 (RGB)
_PANEL_SELECTED = (15, 128, 220)
_PANEL_UNSELECTED = (24, 40, 65)
_EXPEDITION_NOTIF = (245, 88, 47)
_EXPEDITION_NO_NOTIF = (21, 37, 63)
_CHAPTER_BRIGHT = (252, 227, 47)  # 选中章节 (黄色岛屿)
_CHAPTER_DARK = (24, 40, 65)  # 未选中章节

# 屏幕尺寸
_W, _H = 960, 540


def _set_pixel(
    screen: np.ndarray, rx: float, ry: float, rgb: tuple[int, int, int]
) -> None:
    """在相对坐标处设置像素颜色。"""
    h, w = screen.shape[:2]
    px, py = int(rx * w), int(ry * h)
    screen[py, px] = rgb


def _make_screen(
    active_panel: MapPanel = MapPanel.SORTIE,
    expedition_notification: bool = False,
    selected_chapter_y: float | None = 0.55,
) -> np.ndarray:
    """生成地图页面的合成截图。

    Parameters
    ----------
    active_panel:
        当前选中的面板。
    expedition_notification:
        是否有远征通知。
    selected_chapter_y:
        选中章节在侧边栏的中心 y 坐标 (None 表示无选中)。
    """
    screen = np.zeros((_H, _W, 3), dtype=np.uint8)

    # 面板标签
    for panel, (x, y) in PANEL_PROBE.items():
        color = _PANEL_SELECTED if panel == active_panel else _PANEL_UNSELECTED
        _set_pixel(screen, x, y, color)

    # 远征通知
    ex, ey = EXPEDITION_NOTIF_PROBE
    _set_pixel(
        screen,
        ex,
        ey,
        _EXPEDITION_NOTIF if expedition_notification else _EXPEDITION_NO_NOTIF,
    )

    # 侧边栏选中章节 (在中心 y 附近 ±0.03 范围绘制亮色)
    if selected_chapter_y is not None:
        for dy in range(-3, 4):
            y = selected_chapter_y + dy * 0.01
            if 0 < y < 1:
                _set_pixel(screen, SIDEBAR_SCAN_X, y, _CHAPTER_BRIGHT)

    return screen


# ─────────────────────────────────────────────
# 页面识别
# ─────────────────────────────────────────────


class TestIsCurrentPage:
    def test_default_state_detected(self):
        screen = _make_screen()
        assert MapPage.is_current_page(screen) is True

    def test_each_panel(self):
        for panel in MapPanel:
            screen = _make_screen(active_panel=panel)
            assert MapPage.is_current_page(screen) is True

    def test_blank_screen_not_detected(self):
        screen = np.zeros((_H, _W, 3), dtype=np.uint8)
        assert MapPage.is_current_page(screen) is False

    def test_two_panels_active_not_detected(self):
        """两个面板同时为选中蓝色 → 不是合法状态。"""
        screen = _make_screen(active_panel=MapPanel.SORTIE)
        _set_pixel(screen, *PANEL_PROBE[MapPanel.EXERCISE], _PANEL_SELECTED)
        assert MapPage.is_current_page(screen) is False

    def test_no_panel_selected_not_detected(self):
        """没有面板选中 → 不是合法状态。"""
        screen = _make_screen(active_panel=MapPanel.SORTIE)
        _set_pixel(
            screen, *PANEL_PROBE[MapPanel.SORTIE], _PANEL_UNSELECTED
        )
        assert MapPage.is_current_page(screen) is False


# ─────────────────────────────────────────────
# 面板检测
# ─────────────────────────────────────────────


class TestGetActivePanel:
    @pytest.mark.parametrize("panel", list(MapPanel))
    def test_each_panel(self, panel: MapPanel):
        screen = _make_screen(active_panel=panel)
        assert MapPage.get_active_panel(screen) == panel

    def test_none_active(self):
        screen = np.zeros((_H, _W, 3), dtype=np.uint8)
        assert MapPage.get_active_panel(screen) is None


# ─────────────────────────────────────────────
# 远征通知
# ─────────────────────────────────────────────


class TestExpeditionNotification:
    def test_has_notification(self):
        screen = _make_screen(expedition_notification=True)
        assert MapPage.has_expedition_notification(screen) is True

    def test_no_notification(self):
        screen = _make_screen(expedition_notification=False)
        assert MapPage.has_expedition_notification(screen) is False


# ─────────────────────────────────────────────
# 侧边栏章节位置检测
# ─────────────────────────────────────────────


class TestFindSelectedChapterY:
    def test_chapter_at_055(self):
        screen = _make_screen(selected_chapter_y=0.55)
        y = MapPage.find_selected_chapter_y(screen)
        assert y is not None
        assert abs(y - 0.55) < 0.02

    def test_chapter_at_040(self):
        screen = _make_screen(selected_chapter_y=0.40)
        y = MapPage.find_selected_chapter_y(screen)
        assert y is not None
        assert abs(y - 0.40) < 0.02

    def test_no_bright_region(self):
        screen = _make_screen(selected_chapter_y=None)
        assert MapPage.find_selected_chapter_y(screen) is None


# ─────────────────────────────────────────────
# 地图标题解析
# ─────────────────────────────────────────────


class TestParseMapTitle:
    def test_standard_format(self):
        info = parse_map_title("9-5南大洋群岛")
        assert info is not None
        assert info.chapter == 9
        assert info.map_num == 5
        assert info.name == "南大洋群岛"

    def test_with_slash(self):
        info = parse_map_title("9-5/南大洋群岛")
        assert info is not None
        assert info.chapter == 9
        assert info.map_num == 5
        assert info.name == "南大洋群岛"

    def test_with_spaces(self):
        info = parse_map_title("3 - 4 北大西洋")
        assert info is not None
        assert info.chapter == 3
        assert info.map_num == 4
        assert info.name == "北大西洋"

    def test_numbers_only(self):
        info = parse_map_title("1-1")
        assert info is not None
        assert info.chapter == 1
        assert info.map_num == 1
        assert info.name == ""

    def test_with_full_width_slash(self):
        info = parse_map_title("5-3／铁底湾")
        assert info is not None
        assert info.chapter == 5
        assert info.map_num == 3
        assert info.name == "铁底湾"

    def test_em_dash(self):
        info = parse_map_title("7—2珊瑚海")
        assert info is not None
        assert info.chapter == 7
        assert info.map_num == 2

    def test_invalid_text(self):
        assert parse_map_title("无效文本") is None
        assert parse_map_title("") is None
        assert parse_map_title("abc") is None

    def test_raw_text_preserved(self):
        raw = "9-5/南大洋群岛"
        info = parse_map_title(raw)
        assert info is not None
        assert info.raw_text == raw


# ─────────────────────────────────────────────
# 动作 — 回退
# ─────────────────────────────────────────────


class TestGoBack:
    def test_go_back(self):
        ctrl = MagicMock(spec=AndroidController)
        page = MapPage(ctrl)
        page.go_back()
        ctrl.click.assert_called_once_with(*CLICK_BACK)


# ─────────────────────────────────────────────
# 动作 — 面板切换
# ─────────────────────────────────────────────


class TestSwitchPanel:
    @pytest.fixture()
    def page(self):
        ctrl = MagicMock(spec=AndroidController)
        return MapPage(ctrl), ctrl

    @pytest.mark.parametrize("panel", list(MapPanel))
    def test_each_panel(self, page, panel: MapPanel):
        pg, ctrl = page
        pg.switch_panel(panel)
        ctrl.click.assert_called_once_with(*CLICK_PANEL[panel])


# ─────────────────────────────────────────────
# 动作 — 章节点击
# ─────────────────────────────────────────────


class TestClickChapter:
    @pytest.fixture()
    def page(self):
        ctrl = MagicMock(spec=AndroidController)
        return MapPage(ctrl), ctrl

    def test_click_prev_chapter(self, page):
        pg, ctrl = page
        screen = _make_screen(selected_chapter_y=0.55)
        result = pg.click_prev_chapter(screen)
        assert result is True
        ctrl.click.assert_called_once()
        args = ctrl.click.call_args[0]
        assert args[0] == pytest.approx(SIDEBAR_CLICK_X)
        assert args[1] == pytest.approx(0.55 - CHAPTER_SPACING, abs=0.02)

    def test_click_next_chapter(self, page):
        pg, ctrl = page
        screen = _make_screen(selected_chapter_y=0.55)
        result = pg.click_next_chapter(screen)
        assert result is True
        ctrl.click.assert_called_once()
        args = ctrl.click.call_args[0]
        assert args[0] == pytest.approx(SIDEBAR_CLICK_X)
        assert args[1] == pytest.approx(0.55 + CHAPTER_SPACING, abs=0.02)

    def test_click_prev_no_bright_region(self, page):
        pg, ctrl = page
        screen = _make_screen(selected_chapter_y=None)
        result = pg.click_prev_chapter(screen)
        assert result is False
        ctrl.click.assert_not_called()

    def test_click_next_no_bright_region(self, page):
        pg, ctrl = page
        screen = _make_screen(selected_chapter_y=None)
        result = pg.click_next_chapter(screen)
        assert result is False
        ctrl.click.assert_not_called()

    def test_click_prev_at_top_boundary(self, page):
        """选中章节在顶部时，向前切换应失败。"""
        pg, ctrl = page
        screen = _make_screen(selected_chapter_y=0.15)
        result = pg.click_prev_chapter(screen)
        assert result is False
        ctrl.click.assert_not_called()

    def test_click_next_at_bottom_boundary(self, page):
        """选中章节在底部时，向后切换应失败。"""
        pg, ctrl = page
        screen = _make_screen(selected_chapter_y=0.85)
        result = pg.click_next_chapter(screen)
        assert result is False
        ctrl.click.assert_not_called()

    def test_auto_screenshot(self, page):
        """不传 screen 时自动截图。"""
        pg, ctrl = page
        screen = _make_screen(selected_chapter_y=0.55)
        ctrl.screenshot.return_value = screen
        result = pg.click_prev_chapter()
        assert result is True
        ctrl.screenshot.assert_called_once()


# ─────────────────────────────────────────────
# 动作 — 章节导航
# ─────────────────────────────────────────────


class TestNavigateToChapter:
    def test_invalid_chapter_raises(self):
        ctrl = MagicMock(spec=AndroidController)
        ocr = MagicMock()
        pg = MapPage(ctrl, ocr=ocr)
        with pytest.raises(ValueError, match="1–9"):
            pg.navigate_to_chapter(0)
        with pytest.raises(ValueError, match="1–9"):
            pg.navigate_to_chapter(10)

    def test_no_ocr_raises(self):
        ctrl = MagicMock(spec=AndroidController)
        pg = MapPage(ctrl, ocr=None)
        with pytest.raises(RuntimeError, match="OCR"):
            pg.navigate_to_chapter(5)

    @patch("autowsgr.ui.map_page.time")
    def test_already_at_target(self, mock_time):
        """已在目标章节时直接返回。"""
        ctrl = MagicMock(spec=AndroidController)
        ocr = MagicMock()
        pg = MapPage(ctrl, ocr=ocr)

        screen = _make_screen(selected_chapter_y=0.55)
        ctrl.screenshot.return_value = screen

        # OCR 返回当前在第 5 章
        with patch.object(
            MapPage,
            "recognize_map",
            return_value=MapIdentity(5, 3, "铁底湾", "5-3铁底湾"),
        ):
            result = pg.navigate_to_chapter(5)

        assert result == 5
        # 不需要点击
        ctrl.click.assert_not_called()

    @patch("autowsgr.ui.map_page.time")
    def test_navigate_forward(self, mock_time):
        """从第 5 章导航到第 7 章。"""
        ctrl = MagicMock(spec=AndroidController)
        ocr = MagicMock()
        pg = MapPage(ctrl, ocr=ocr)

        screen = _make_screen(selected_chapter_y=0.55)
        ctrl.screenshot.return_value = screen

        # 模拟 OCR 依次返回 ch5, ch6, ch7
        chapters = [5, 6, 7]
        call_count = [0]

        def mock_recognize(s, o):
            ch = chapters[min(call_count[0], len(chapters) - 1)]
            call_count[0] += 1
            return MapIdentity(ch, 1, "test", f"{ch}-1test")

        with patch.object(MapPage, "recognize_map", side_effect=mock_recognize):
            result = pg.navigate_to_chapter(7)

        assert result == 7
        # 应该点击了 2 次 (5→6, 6→7)
        assert ctrl.click.call_count == 2

    @patch("autowsgr.ui.map_page.time")
    def test_navigate_backward(self, mock_time):
        """从第 7 章导航到第 5 章。"""
        ctrl = MagicMock(spec=AndroidController)
        ocr = MagicMock()
        pg = MapPage(ctrl, ocr=ocr)

        screen = _make_screen(selected_chapter_y=0.55)
        ctrl.screenshot.return_value = screen

        chapters = [7, 6, 5]
        call_count = [0]

        def mock_recognize(s, o):
            ch = chapters[min(call_count[0], len(chapters) - 1)]
            call_count[0] += 1
            return MapIdentity(ch, 1, "test", f"{ch}-1test")

        with patch.object(MapPage, "recognize_map", side_effect=mock_recognize):
            result = pg.navigate_to_chapter(5)

        assert result == 5
        assert ctrl.click.call_count == 2

    @patch("autowsgr.ui.map_page.time")
    def test_ocr_failure_returns_none(self, mock_time):
        """OCR 识别失败时返回 None。"""
        ctrl = MagicMock(spec=AndroidController)
        ocr = MagicMock()
        pg = MapPage(ctrl, ocr=ocr)

        screen = _make_screen(selected_chapter_y=0.55)
        ctrl.screenshot.return_value = screen

        with patch.object(MapPage, "recognize_map", return_value=None):
            result = pg.navigate_to_chapter(5)

        assert result is None


# ─────────────────────────────────────────────
# MapPanel 枚举
# ─────────────────────────────────────────────


class TestMapPanel:
    def test_values(self):
        assert MapPanel.SORTIE.value == "出征"
        assert MapPanel.EXERCISE.value == "演习"
        assert MapPanel.EXPEDITION.value == "远征"
        assert MapPanel.BATTLE.value == "战役"
        assert MapPanel.DECISIVE.value == "决战"

    def test_count(self):
        assert len(MapPanel) == 5


# ─────────────────────────────────────────────
# MapIdentity 数据类
# ─────────────────────────────────────────────


class TestMapIdentity:
    def test_frozen(self):
        info = MapIdentity(chapter=9, map_num=5, name="南大洋群岛", raw_text="9-5")
        with pytest.raises(AttributeError):
            info.chapter = 1  # type: ignore[misc]

    def test_equality(self):
        a = MapIdentity(9, 5, "南大洋群岛", "9-5")
        b = MapIdentity(9, 5, "南大洋群岛", "9-5")
        assert a == b

    def test_slots(self):
        info = MapIdentity(9, 5, "南大洋群岛", "9-5")
        assert not hasattr(info, "__dict__")
