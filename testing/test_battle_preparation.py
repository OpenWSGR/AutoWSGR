"""测试 出征准备页面 UI 控制器。"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from autowsgr.emulator.controller import AndroidController
from autowsgr.ui.battle_preparation import (
    AUTO_SUPPLY_PROBE,
    CLICK_AUTO_SUPPLY,
    CLICK_BACK,
    CLICK_FLEET,
    CLICK_PANEL,
    CLICK_START_BATTLE,
    CLICK_SUPPORT,
    FLEET_PROBE,
    PANEL_PROBE,
    BattlePreparationPage,
    Panel,
)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

# 参考颜色 (RGB)
_FLEET_SELECTED = (16, 133, 228)
_FLEET_UNSELECTED = (26, 43, 69)
_PANEL_SELECTED = (30, 139, 240)
_PANEL_UNSELECTED = (27, 61, 88)
_AUTO_ON = (13, 140, 233)
_AUTO_OFF = (50, 50, 50)

# 屏幕尺寸
_W, _H = 960, 540


def _set_pixel(screen: np.ndarray, rx: float, ry: float, rgb: tuple[int, int, int]) -> None:
    """在相对坐标处设置像素颜色（与 PixelChecker.get_pixel 使用相同算法）。"""
    h, w = screen.shape[:2]
    px, py = int(rx * w), int(ry * h)
    screen[py, px] = rgb


def _make_screen(
    selected_fleet: int = 1,
    active_panel: Panel = Panel.STATS,
    auto_supply: bool = True,
) -> np.ndarray:
    """生成出征准备页面的合成截图。

    仅在探测点位置写入对应状态颜色，其余区域为黑色。
    """
    screen = np.zeros((_H, _W, 3), dtype=np.uint8)

    # 舰队标签
    for fid, (x, y) in FLEET_PROBE.items():
        color = _FLEET_SELECTED if fid == selected_fleet else _FLEET_UNSELECTED
        _set_pixel(screen, x, y, color)

    # 面板标签
    for panel, (x, y) in PANEL_PROBE.items():
        color = _PANEL_SELECTED if panel == active_panel else _PANEL_UNSELECTED
        _set_pixel(screen, x, y, color)

    # 自动补给
    ax, ay = AUTO_SUPPLY_PROBE
    _set_pixel(screen, ax, ay, _AUTO_ON if auto_supply else _AUTO_OFF)

    return screen


# ─────────────────────────────────────────────
# 页面识别
# ─────────────────────────────────────────────


class TestIsCurrentPage:
    def test_default_state_detected(self):
        screen = _make_screen()
        assert BattlePreparationPage.is_current_page(screen) is True

    def test_fleet_2_selected(self):
        screen = _make_screen(selected_fleet=2)
        assert BattlePreparationPage.is_current_page(screen) is True

    def test_fleet_4_quick_repair(self):
        screen = _make_screen(selected_fleet=4, active_panel=Panel.QUICK_REPAIR)
        assert BattlePreparationPage.is_current_page(screen) is True

    def test_blank_screen_not_detected(self):
        screen = np.zeros((_H, _W, 3), dtype=np.uint8)
        assert BattlePreparationPage.is_current_page(screen) is False

    def test_two_fleets_selected_not_detected(self):
        """两个舰队同时选中 → 不是合法状态。"""
        screen = _make_screen(selected_fleet=1)
        _set_pixel(screen, *FLEET_PROBE[2], _FLEET_SELECTED)
        assert BattlePreparationPage.is_current_page(screen) is False

    def test_no_panel_selected_not_detected(self):
        """没有面板选中 → 不是合法状态。"""
        screen = _make_screen()
        # 把唯一选中的面板清掉
        _set_pixel(screen, *PANEL_PROBE[Panel.STATS], _PANEL_UNSELECTED)
        assert BattlePreparationPage.is_current_page(screen) is False


# ─────────────────────────────────────────────
# 舰队选中检测
# ─────────────────────────────────────────────


class TestGetSelectedFleet:
    @pytest.mark.parametrize("fleet", [1, 2, 3, 4])
    def test_each_fleet(self, fleet: int):
        screen = _make_screen(selected_fleet=fleet)
        assert BattlePreparationPage.get_selected_fleet(screen) == fleet

    def test_none_selected(self):
        screen = np.zeros((_H, _W, 3), dtype=np.uint8)
        assert BattlePreparationPage.get_selected_fleet(screen) is None


# ─────────────────────────────────────────────
# 面板选中检测
# ─────────────────────────────────────────────


class TestGetActivePanel:
    @pytest.mark.parametrize("panel", list(Panel))
    def test_each_panel(self, panel: Panel):
        screen = _make_screen(active_panel=panel)
        assert BattlePreparationPage.get_active_panel(screen) == panel

    def test_none_active(self):
        screen = np.zeros((_H, _W, 3), dtype=np.uint8)
        assert BattlePreparationPage.get_active_panel(screen) is None


# ─────────────────────────────────────────────
# 自动补给检测
# ─────────────────────────────────────────────


class TestAutoSupply:
    def test_enabled(self):
        screen = _make_screen(auto_supply=True)
        assert BattlePreparationPage.is_auto_supply_enabled(screen) is True

    def test_disabled(self):
        screen = _make_screen(auto_supply=False)
        assert BattlePreparationPage.is_auto_supply_enabled(screen) is False


# ─────────────────────────────────────────────
# 动作 — 回退 / 出征
# ─────────────────────────────────────────────


class TestActions:
    @pytest.fixture
    def page(self):
        ctrl = MagicMock(spec=AndroidController)
        return BattlePreparationPage(ctrl), ctrl

    def test_go_back(self, page):
        pg, ctrl = page
        # go_back 现在使用 click_and_wait_for_page 验证到达地图页面
        # 需要提供一个让 MapPage.is_current_page 返回 True 的截图
        # MapPage 检测: 5 个面板探测点中恰好 1 个为选中蓝色 (15, 128, 220)
        from autowsgr.ui.map_page import PANEL_PROBE, MapPanel

        screen = np.zeros((540, 960, 3), dtype=np.uint8)
        # 在 SORTIE 面板探测点放置选中态颜色
        # PixelChecker.get_pixel 使用 int(x * w) (截断), 此处保持一致
        sx, sy = PANEL_PROBE[MapPanel.SORTIE]
        px, py = int(sx * 960), int(sy * 540)
        screen[py, px] = [15, 128, 220]
        ctrl.screenshot.return_value = screen
        pg.go_back()
        ctrl.click.assert_called_with(*CLICK_BACK)

    def test_start_battle(self, page):
        pg, ctrl = page
        pg.start_battle()
        ctrl.click.assert_called_once_with(*CLICK_START_BATTLE)


# ─────────────────────────────────────────────
# 动作 — 舰队选择
# ─────────────────────────────────────────────


class TestSelectFleet:
    @pytest.fixture
    def page(self):
        ctrl = MagicMock(spec=AndroidController)
        return BattlePreparationPage(ctrl), ctrl

    @pytest.mark.parametrize("fleet", [1, 2, 3, 4])
    def test_valid_fleet(self, page, fleet: int):
        pg, ctrl = page
        pg.select_fleet(fleet)
        ctrl.click.assert_called_once_with(*CLICK_FLEET[fleet])

    def test_invalid_fleet_raises(self, page):
        pg, ctrl = page
        with pytest.raises(ValueError, match="1–4"):
            pg.select_fleet(5)

    def test_fleet_zero_raises(self, page):
        pg, ctrl = page
        with pytest.raises(ValueError):
            pg.select_fleet(0)


# ─────────────────────────────────────────────
# 动作 — 面板切换
# ─────────────────────────────────────────────


class TestSelectPanel:
    @pytest.fixture
    def page(self):
        ctrl = MagicMock(spec=AndroidController)
        return BattlePreparationPage(ctrl), ctrl

    @pytest.mark.parametrize("panel", list(Panel))
    def test_each_panel(self, page, panel: Panel):
        pg, ctrl = page
        pg.select_panel(panel)
        ctrl.click.assert_called_once_with(*CLICK_PANEL[panel])

    def test_quick_supply(self, page):
        pg, ctrl = page
        pg.quick_supply()
        ctrl.click.assert_called_once_with(*CLICK_PANEL[Panel.QUICK_SUPPLY])

    def test_quick_repair(self, page):
        pg, ctrl = page
        pg.quick_repair()
        ctrl.click.assert_called_once_with(*CLICK_PANEL[Panel.QUICK_REPAIR])


# ─────────────────────────────────────────────
# 动作 — 开关
# ─────────────────────────────────────────────


class TestToggles:
    @pytest.fixture
    def page(self):
        ctrl = MagicMock(spec=AndroidController)
        return BattlePreparationPage(ctrl), ctrl

    def test_toggle_battle_support(self, page):
        pg, ctrl = page
        pg.toggle_battle_support()
        ctrl.click.assert_called_once_with(*CLICK_SUPPORT)

    def test_toggle_auto_supply(self, page):
        pg, ctrl = page
        pg.toggle_auto_supply()
        ctrl.click.assert_called_once_with(*CLICK_AUTO_SUPPLY)


# ─────────────────────────────────────────────
# Panel 枚举
# ─────────────────────────────────────────────


class TestPanel:
    def test_values(self):
        assert Panel.STATS.value == "综合战力"
        assert Panel.QUICK_SUPPLY.value == "快速补给"
        assert Panel.QUICK_REPAIR.value == "快速修理"
        assert Panel.EQUIPMENT.value == "装备预览"

    def test_count(self):
        assert len(Panel) == 4
