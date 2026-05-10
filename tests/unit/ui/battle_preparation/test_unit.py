"""测试 出征准备页面 UI 控制器。"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from autowsgr.context import GameContext
from autowsgr.emulator import AndroidController
from autowsgr.ui.battle.base import PAGE_SIGNATURE
from autowsgr.ui.battle.constants import (
    AUTO_SUPPLY_PROBE,
    CLICK_AUTO_SUPPLY,
    CLICK_BACK,
    CLICK_FLEET,
    CLICK_START_BATTLE,
    CLICK_SUPPORT,
    FLEET_PROBE,
)
from autowsgr.ui.battle.preparation import (
    CLICK_PANEL,
    PANEL_PROBE,
    BattlePreparationPage,
    Panel,
)


if TYPE_CHECKING:
    from autowsgr.vision.ocr import OCREngine


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


def _make_ctx(ctrl: AndroidController, ocr: OCREngine | None = None) -> GameContext:
    if ocr is None:
        ocr = MagicMock()
    """构造 GameContext，用于 BattlePreparationPage 初始化。"""
    return GameContext(ctrl=ctrl, config=MagicMock(), ocr=ocr)


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

    # 页面签名像素（使 is_current_page 返回 True）
    for rule in PAGE_SIGNATURE.rules:
        _set_pixel(screen, rule.x, rule.y, rule.color.as_rgb_tuple())

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
        # 缺少签名的屏幕不应被识别为出征准备页
        screen = np.zeros((_H, _W, 3), dtype=np.uint8)
        assert BattlePreparationPage.is_current_page(screen) is False

    def test_two_fleets_selected_still_detected(self):
        """is_current_page 仅验证页面签名，不校验状态合法性。"""
        screen = _make_screen(selected_fleet=1)
        _set_pixel(screen, *FLEET_PROBE[2], _FLEET_SELECTED)
        assert BattlePreparationPage.is_current_page(screen) is True

    def test_no_panel_selected_still_detected(self):
        """is_current_page 仅验证页面签名，不校验面板状态。"""
        screen = _make_screen()
        # 把唯一选中的面板清掉，签名仍在
        _set_pixel(screen, *PANEL_PROBE[Panel.STATS], _PANEL_UNSELECTED)
        assert BattlePreparationPage.is_current_page(screen) is True


# ─────────────────────────────────────────────
# 舰队选中检测
# ─────────────────────────────────────────────


class TestGetSelectedFleet:
    @pytest.mark.parametrize('fleet', [1, 2, 3, 4])
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
    @pytest.mark.parametrize('panel', list(Panel))
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
    def page(self) -> tuple[BattlePreparationPage, MagicMock]:
        ctrl = MagicMock(spec=AndroidController)
        return BattlePreparationPage(_make_ctx(ctrl)), ctrl

    def test_go_back(self, page: tuple[BattlePreparationPage, MagicMock]):
        pg, ctrl = page
        # go_back 调用 click_and_wait_leave_page，会截图验证是否离开当前页
        # mock screenshot 先返回当前页，再返回地图页
        from autowsgr.ui.battle.base import PAGE_SIGNATURE as BATTLE_PREP_SIG

        # 第一次：BATTLE_PREP（带签名）
        screen_prep = np.zeros((540, 960, 3), dtype=np.uint8)
        for rule in BATTLE_PREP_SIG.rules:
            _set_pixel(screen_prep, rule.x, rule.y, rule.color.as_rgb_tuple())
        # 第二次：空白页（无签名）
        screen_blank = np.zeros((540, 960, 3), dtype=np.uint8)
        ctrl.screenshot.side_effect = [screen_prep, screen_blank]

        with patch(
            'autowsgr.ui.utils.navigation.time.sleep',
        ):
            pg.go_back()
        ctrl.click.assert_called_with(*CLICK_BACK)

    def test_start_battle(self, page: tuple[BattlePreparationPage, MagicMock]):
        pg, ctrl = page
        pg.start_battle()
        ctrl.click.assert_called_once_with(*CLICK_START_BATTLE)


# ─────────────────────────────────────────────
# 动作 — 舰队选择
# ─────────────────────────────────────────────


class TestSelectFleet:
    @pytest.fixture
    def page(self) -> tuple[BattlePreparationPage, MagicMock]:
        ctrl = MagicMock(spec=AndroidController)
        return BattlePreparationPage(_make_ctx(ctrl)), ctrl

    @pytest.mark.parametrize('fleet', [1, 2, 3, 4])
    def test_valid_fleet(self, page: tuple[BattlePreparationPage, MagicMock], fleet: int):
        pg, ctrl = page
        pg.select_fleet(fleet)
        ctrl.click.assert_called_once_with(*CLICK_FLEET[fleet])

    def test_invalid_fleet_raises(self, page: tuple[BattlePreparationPage, MagicMock]):
        pg, _ctrl = page
        with pytest.raises(ValueError, match='1-4'):
            pg.select_fleet(5)

    def test_fleet_zero_raises(self, page: tuple[BattlePreparationPage, MagicMock]):
        pg, _ctrl = page
        with pytest.raises(ValueError, match='舰队编号'):
            pg.select_fleet(0)


# ─────────────────────────────────────────────
# 动作 — 面板切换
# ─────────────────────────────────────────────


class TestSelectPanel:
    @pytest.fixture
    def page(self) -> tuple[BattlePreparationPage, MagicMock]:
        ctrl = MagicMock(spec=AndroidController)
        return BattlePreparationPage(_make_ctx(ctrl)), ctrl

    @pytest.mark.parametrize('panel', list(Panel))
    def test_each_panel(self, page: tuple[BattlePreparationPage, MagicMock], panel: Panel):
        pg, ctrl = page
        pg.select_panel(panel)
        ctrl.click.assert_called_once_with(*CLICK_PANEL[panel])

    def test_quick_supply(self, page: tuple[BattlePreparationPage, MagicMock]):
        pg, ctrl = page
        pg.quick_supply()
        ctrl.click.assert_called_once_with(*CLICK_PANEL[Panel.QUICK_SUPPLY])

    def test_quick_repair(self, page: tuple[BattlePreparationPage, MagicMock]):
        pg, ctrl = page
        pg.quick_repair()
        ctrl.click.assert_called_once_with(*CLICK_PANEL[Panel.QUICK_REPAIR])


# ─────────────────────────────────────────────
# 动作 — 开关
# ─────────────────────────────────────────────


class TestToggles:
    @pytest.fixture
    def page(self) -> tuple[BattlePreparationPage, MagicMock]:
        ctrl = MagicMock(spec=AndroidController)
        return BattlePreparationPage(_make_ctx(ctrl)), ctrl

    def test_toggle_battle_support(self, page: tuple[BattlePreparationPage, MagicMock]):
        pg, ctrl = page
        pg.toggle_battle_support()
        ctrl.click.assert_called_once_with(*CLICK_SUPPORT)

    def test_toggle_auto_supply(self, page: tuple[BattlePreparationPage, MagicMock]):
        pg, ctrl = page
        pg.toggle_auto_supply()
        ctrl.click.assert_called_once_with(*CLICK_AUTO_SUPPLY)
