"""测试 出征准备页面 UI 控制器。"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, call, patch

import cv2
import numpy as np
import pytest

from autowsgr.combat.fleet import (
    FleetSlotRule,
    ShipSelector,
    exact_fleet_rules,
    fleet_slot_from_api,
)
from autowsgr.constants import normalize_ship_name, ship_name_identity
from autowsgr.context import GameContext
from autowsgr.emulator import AndroidController
from autowsgr.infra import DecisiveConfig
from autowsgr.server.schemas import FleetRuleRequest
from autowsgr.types import ShipDamageState, ShipType
from autowsgr.ui.battle.constants import (
    AUTO_SUPPLY_PROBE,
    CLICK_AUTO_SUPPLY,
    CLICK_BACK,
    CLICK_FLEET,
    CLICK_START_BATTLE,
    CLICK_SUPPORT,
    FLEET_PROBE,
    SHIP_LEVEL_CROP,
)
from autowsgr.ui.battle.fleet_change._change import _ShipSelection
from autowsgr.ui.battle.fleet_change._detect import FleetSnapshot
from autowsgr.ui.battle.preparation import (
    CLICK_PANEL,
    PANEL_PROBE,
    BattlePreparationPage,
    Panel,
)
from autowsgr.ui.decisive.legacy_fleet_change import change_fleet_legacy
from autowsgr.ui.decisive.preparation import DecisiveBattlePreparationPage
from autowsgr.vision import OCRResult
from autowsgr.vision.ocr_rules import (
    EasyOCRProfile,
    set_user_ship_name_aliases,
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


@pytest.fixture(autouse=True)
def _reset_ship_name_aliases():
    set_user_ship_name_aliases({})
    yield
    set_user_ship_name_aliases({})


def _make_ctx(
    ctrl: AndroidController,
    ocr: OCREngine | None = None,
    ship_ocr: OCREngine | None = None,
) -> GameContext:
    """构造 GameContext，用于 BattlePreparationPage 初始化。"""
    return GameContext(
        ctrl=ctrl,
        config=MagicMock(),
        ocr=ocr,
        ship_ocr=ship_ocr,
    )


def _rule(raw: dict[str, object]) -> FleetSlotRule:
    """把 API 规则转换成 UI 实际接收的 canonical model。"""
    dto = FleetRuleRequest.model_validate(raw)
    return fleet_slot_from_api(dto.model_dump(exclude_none=True))


def _candidate_rule(
    *names: str,
    min_level: int | None = None,
) -> FleetSlotRule:
    """构造保持原顺序的宽泛备选规则。"""
    return FleetSlotRule(
        candidates=tuple(
            ShipSelector(
                name=name,
                min_level=min_level,
                relaxed_constraints=True,
            )
            for name in names
        ),
    )


def _snapshot(
    names: list[str | None],
    occupied: list[bool] | None = None,
) -> FleetSnapshot:
    """构造不会与测试输入共享列表的舰队快照。"""
    return FleetSnapshot(
        names=list(names),
        occupied=list(occupied) if occupied is not None else [name is not None for name in names],
    )


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

    # 出征准备页面模板 (使 is_current_page 模板匹配命中)。
    # 贴到右上角空白区, 避开舰队/面板/补给探测点 (均在中下及左侧)。
    from autowsgr.image_resources._lazy import load_template

    tmpl = load_template('page/fight_prepare_540p.png')
    th, tw = tmpl.image.shape[:2]
    screen[0:th, _W - tw : _W] = tmpl.image

    return screen


# ─────────────────────────────────────────────
# 等级 OCR 坐标
# ─────────────────────────────────────────────


def test_ship_level_crop_uses_calibrated_regions():
    assert SHIP_LEVEL_CROP == {
        0: (0.0508, 0.5667, 0.0953, 0.5875),
        1: (0.1672, 0.5667, 0.2117, 0.5875),
        2: (0.2836, 0.5667, 0.3281, 0.5875),
        3: (0.3992, 0.5667, 0.4438, 0.5875),
        4: (0.5164, 0.5667, 0.5609, 0.5875),
        5: (0.6328, 0.5667, 0.6773, 0.5875),
    }


# ─────────────────────────────────────────────
# 等级 OCR 路由
# ─────────────────────────────────────────────


class TestLevelOCRRouting:
    @staticmethod
    def _single_ship_damage() -> dict[int, ShipDamageState]:
        return {
            0: ShipDamageState.NORMAL,
            **dict.fromkeys(range(1, 6), ShipDamageState.NO_SHIP),
        }

    def test_easyocr_path_applies_otsu_and_shared_rules(self):
        ctrl = MagicMock(spec=AndroidController)
        ocr = MagicMock()
        ocr.recognize_line.return_value = [
            OCRResult(text='LV.1D3', confidence=0.99),
        ]
        page = BattlePreparationPage(_make_ctx(ctrl, ocr))
        screen = np.zeros((720, 1280, 3), dtype=np.uint8)

        with (
            patch.object(
                page,
                'detect_ship_damage',
                return_value=self._single_ship_damage(),
            ),
            patch(
                'autowsgr.ui.battle.detection.cv2.threshold',
                wraps=cv2.threshold,
            ) as threshold,
        ):
            levels = page._recognize_fleet_levels(screen)

        assert levels[0] == 103
        threshold.assert_called_once()
        assert threshold.call_args.args[3] == cv2.THRESH_BINARY + cv2.THRESH_OTSU
        assert ocr.recognize_line.call_args.kwargs == {
            'easyocr_profile': EasyOCRProfile.FLEET_SHIP_LEVEL,
        }
        assert ocr.recognize_line.call_args.args[0].shape == (30, 112, 3)

    def test_fastocr_path_keeps_original_roi_and_shared_rules(self):
        ctrl = MagicMock(spec=AndroidController)
        easyocr = MagicMock()
        fastocr = MagicMock()
        fastocr.recognize_line.return_value = [
            OCRResult(text='LV.S', confidence=0.99),
        ]
        page = BattlePreparationPage(
            _make_ctx(
                ctrl,
                easyocr,
                ship_ocr=fastocr,
            ),
        )
        screen = np.zeros((720, 1280, 3), dtype=np.uint8)

        with (
            patch.object(
                page,
                'detect_ship_damage',
                return_value=self._single_ship_damage(),
            ),
            patch('autowsgr.ui.battle.detection.cv2.threshold') as threshold,
        ):
            levels = page._recognize_fleet_levels(screen)

        assert levels[0] == 5
        threshold.assert_not_called()
        fastocr.recognize_line.assert_called_once()
        assert fastocr.recognize_line.call_args.kwargs == {
            'easyocr_profile': EasyOCRProfile.FLEET_SHIP_LEVEL,
        }
        assert fastocr.recognize_line.call_args.args[0].shape == (15, 56, 3)
        easyocr.recognize_line.assert_not_called()

    def test_requested_level_slots_skip_damage_detection(self):
        ctrl = MagicMock(spec=AndroidController)
        ocr = MagicMock()
        ocr.recognize_line.return_value = [
            OCRResult(text='LV.103', confidence=0.99),
        ]
        page = BattlePreparationPage(_make_ctx(ctrl, ocr))
        screen = np.zeros((720, 1280, 3), dtype=np.uint8)

        with patch.object(page, 'detect_ship_damage') as detect_damage:
            levels = page._recognize_fleet_levels(screen, [2])

        assert levels == {2: 103}
        detect_damage.assert_not_called()
        ocr.recognize_line.assert_called_once()

    @pytest.mark.parametrize(
        ('text', 'expected'),
        [
            ('LV.1D3', 103),
            ('LV.S', 5),
            ('LV.B', 8),
            ('L.1', 1),
            ('L.3', 3),
            ('L.1I0', 110),
            ('L1.110', 110),
            ('LV.110', 110),
            ('LV.111', None),
        ],
    )
    def test_level_parser_uses_shared_rules(
        self,
        text: str,
        expected: int | None,
    ):
        assert BattlePreparationPage._parse_level(text) == expected


# ─────────────────────────────────────────────
# 页面识别
# ─────────────────────────────────────────────


class TestIsCurrentPage:
    """is_current_page 用页面模板匹配, 不校验舰队/面板状态。

    合成截图 _make_screen 已嵌入出征准备模板 (贴右上角), 故各状态变化下
    is_current_page 仍命中; 状态查询 (get_selected_fleet / get_active_panel)
    由专门的 Test 类覆盖。
    """

    def test_default_state_detected(self):
        screen = _make_screen()
        assert BattlePreparationPage.is_current_page(screen).matched

    def test_fleet_2_selected(self):
        screen = _make_screen(selected_fleet=2)
        assert BattlePreparationPage.is_current_page(screen).matched

    def test_fleet_4_quick_repair(self):
        screen = _make_screen(selected_fleet=4, active_panel=Panel.QUICK_REPAIR)
        assert BattlePreparationPage.is_current_page(screen).matched

    def test_blank_screen_not_detected(self):
        # 缺少模板的屏幕不应被识别为出征准备页
        screen = np.zeros((_H, _W, 3), dtype=np.uint8)
        assert not BattlePreparationPage.is_current_page(screen).matched

    def test_two_fleets_selected_still_detected(self):
        """is_current_page 仅验证页面模板，不校验状态合法性。"""
        screen = _make_screen(selected_fleet=1)
        _set_pixel(screen, *FLEET_PROBE[2], _FLEET_SELECTED)
        assert BattlePreparationPage.is_current_page(screen).matched

    def test_no_panel_selected_still_detected(self):
        """is_current_page 仅验证页面模板，不校验面板状态。"""
        screen = _make_screen()
        # 把唯一选中的面板清掉，模板仍在
        _set_pixel(screen, *PANEL_PROBE[Panel.STATS], _PANEL_UNSELECTED)
        assert BattlePreparationPage.is_current_page(screen).matched


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

    def test_go_back(
        self,
        page: tuple[BattlePreparationPage, MagicMock],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pg, ctrl = page
        # go_back 用到达验证 (click_and_wait_for_page): 点击后需识别为 MAP 才算成功。
        # MapPage 识别走 tabbed 模板匹配, 构造假帧太重, 直接 mock checker 命中。
        from autowsgr.ui.map.page import MapPage
        from autowsgr.ui.page import PageMatch

        monkeypatch.setattr(
            MapPage,
            'is_current_page',
            staticmethod(lambda _s: PageMatch(name='map', matched=True, score=0.9)),
        )
        ctrl.screenshot.return_value = np.zeros((540, 960, 3), dtype=np.uint8)

        with patch('autowsgr.ui.utils.navigation.time.sleep'):
            pg.go_back()
        ctrl.click.assert_called_with(*CLICK_BACK)

    def test_go_back_raises_when_map_not_reached(
        self,
        page: tuple[BattlePreparationPage, MagicMock],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """到达验证: 点击后画面仍在准备页 (MAP 不命中) → NavigationError, 不再假成功。"""
        pg, ctrl = page
        from autowsgr.ui.map.page import MapPage
        from autowsgr.ui.page import PageMatch
        from autowsgr.ui.utils import NavigationError

        monkeypatch.setattr(
            MapPage,
            'is_current_page',
            staticmethod(lambda _s: PageMatch(name='map', matched=False, score=0.0)),
        )
        ctrl.screenshot.return_value = np.zeros((540, 960, 3), dtype=np.uint8)

        with (
            patch('autowsgr.ui.utils.navigation.time.sleep'),
            pytest.raises(NavigationError),
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


# ─────────────────────────────────────────────
# 准备页目标上下文匹配
# ─────────────────────────────────────────────


class TestContextShipNameMatch:
    def test_unique_nearest_target_matches(self):
        expected = ['Z1', 'Z16', 'Z17', 'Z21', '克劳塞维茨', '契卡洛夫']
        assert BattlePreparationPage._match_context_ship_name('71', expected) == 'Z1'

    def test_equal_distance_targets_are_rejected(self):
        assert BattlePreparationPage._match_context_ship_name('71', ['K1', 'Z1']) is None

    def test_target_context_keeps_yaml_slot_positions(self):
        ctrl = MagicMock(spec=AndroidController)
        ocr = MagicMock()
        ocr.recognize.return_value = [
            OCRResult(text='可怖', confidence=0.8, bbox=(127, 3, 167, 23)),
            OCRResult(text='鳟盹', confidence=0.8, bbox=(273, 3, 313, 23)),
            OCRResult(text='霄风', confidence=0.8, bbox=(420, 3, 460, 23)),
        ]
        page = BattlePreparationPage(_make_ctx(ctrl, ocr))
        expected = [None, None, None, '晓', '可畏', '胡德']
        pool_matches = {
            '可怖': '可怖',
            '鳞鲀': '胡德',
            '霄风': '雪风',
        }

        with patch(
            'autowsgr.ui.battle.fleet_change._detect._fuzzy_match',
            side_effect=lambda text, *_args: pool_matches[text],
        ):
            detected = page.detect_fleet(
                np.zeros((720, 1280, 3), dtype=np.uint8),
                expected_names=expected,
            )

        assert detected == ['可怖', '胡德', '雪风', None, None, None]

    def test_clear_pool_match_is_not_overwritten_by_context_target(self):
        ctrl = MagicMock(spec=AndroidController)
        ocr = MagicMock()
        expected = ['峰风', 'Z16', 'Z17', 'Z21', '克劳塞维茨', '契卡洛夫']
        texts = ['蜂风', *expected[1:]]
        centers = [147, 293, 440, 587, 733, 880]
        ocr.recognize.return_value = [
            OCRResult(text=text, confidence=0.8, bbox=(x - 20, 2, x + 20, 24))
            for text, x in zip(texts, centers, strict=True)
        ]
        page = BattlePreparationPage(_make_ctx(ctrl, ocr))

        detected = page.detect_fleet(
            np.zeros((720, 1280, 3), dtype=np.uint8),
            expected_names=expected,
        )

        assert detected[0:5] == ['峰风', 'Z16', 'Z17', 'Z21', '克劳塞维茨']
        assert detected[5] is not None
        assert detected[5] != expected[5]

    def test_swapped_close_names_keep_clear_pool_matches(self):
        ctrl = MagicMock(spec=AndroidController)
        ocr = MagicMock()
        centers = [147, 293]
        ocr.recognize.return_value = [
            OCRResult(text=text, confidence=0.95, bbox=(x - 20, 2, x + 20, 24))
            for text, x in zip(['峰风', '雪风'], centers, strict=True)
        ]
        page = BattlePreparationPage(_make_ctx(ctrl, ocr))

        detected = page.detect_fleet(
            np.zeros((720, 1280, 3), dtype=np.uint8),
            expected_names=['雪风', '峰风', None, None, None, None],
        )

        assert detected[:2] == ['峰风', '雪风']

    def test_unrelated_ocr_does_not_force_slot_target(self):
        ctrl = MagicMock(spec=AndroidController)
        ocr = MagicMock()
        ocr.recognize.return_value = [
            OCRResult(text='71', confidence=0.14, bbox=(117, 3, 139, 21)),
        ]
        page = BattlePreparationPage(_make_ctx(ctrl, ocr))

        detected = page.detect_fleet(
            np.zeros((720, 1280, 3), dtype=np.uint8),
            expected_names=['U-47·狼群', 'U-81', 'U-1206'],
        )

        assert detected == [None] * 6

    def test_global_target_pool_only_rescues_unmatched_text(self):
        ctrl = MagicMock(spec=AndroidController)
        ocr = MagicMock()
        ocr.recognize.return_value = [
            OCRResult(text='雪凤', confidence=0.8, bbox=(127, 3, 167, 23)),
        ]
        page = BattlePreparationPage(_make_ctx(ctrl, ocr))

        with patch(
            'autowsgr.ui.battle.fleet_change._detect._fuzzy_match',
            side_effect=[None, '雪风'],
        ):
            detected = page.detect_fleet(
                np.zeros((720, 1280, 3), dtype=np.uint8),
                expected_pool=['雪风'],
            )

        assert detected == ['雪风', None, None, None, None, None]

    def test_global_target_pool_does_not_override_pool_match(self):
        ctrl = MagicMock(spec=AndroidController)
        ocr = MagicMock()
        ocr.recognize.return_value = [
            OCRResult(text='岛风', confidence=0.8, bbox=(127, 3, 167, 23)),
        ]
        page = BattlePreparationPage(_make_ctx(ctrl, ocr))

        with patch(
            'autowsgr.ui.battle.fleet_change._detect._fuzzy_match',
            return_value='岛风',
        ):
            detected = page.detect_fleet(
                np.zeros((720, 1280, 3), dtype=np.uint8),
                expected_pool=['雪风'],
            )

        assert detected == ['岛风', None, None, None, None, None]

    def test_single_slot_name_recognition_only_crops_requested_slot(self):
        ctrl = MagicMock(spec=AndroidController)
        ocr = MagicMock()
        ocr.recognize.return_value = [
            OCRResult(text='雪风', confidence=0.99),
        ]
        page = BattlePreparationPage(_make_ctx(ctrl, ocr))
        screen = np.zeros((720, 1280, 3), dtype=np.uint8)

        with patch(
            'autowsgr.ui.battle.fleet_change._detect._fuzzy_match',
            return_value='雪风',
        ):
            names = page._recognize_fleet_names_at_slots(screen, [1])

        assert names == {1: '雪风'}
        ocr.recognize.assert_called_once()
        cropped = ocr.recognize.call_args.args[0]
        assert cropped.shape[:2] == (27, 146)

    def test_single_slot_name_stores_postprocessed_result(self):
        ctrl = MagicMock(spec=AndroidController)
        ocr = MagicMock()
        ocr.recognize.return_value = [
            OCRResult(text='OCR原文', confidence=0.99),
        ]
        page = BattlePreparationPage(_make_ctx(ctrl, ocr))
        screen = np.zeros((720, 1280, 3), dtype=np.uint8)

        with (
            patch(
                'autowsgr.ui.battle.fleet_change._detect.apply_ship_patches',
                return_value='岛风',
            ) as apply_patches,
            patch(
                'autowsgr.ui.battle.fleet_change._detect._fuzzy_match',
                return_value='岛风',
            ),
        ):
            names = page._recognize_fleet_names_at_slots(screen, [0])

        assert names == {0: '岛风'}
        apply_patches.assert_called_once_with('OCR原文')

    def test_snapshot_uses_same_screen_for_names_and_occupancy(self):
        ctrl = MagicMock(spec=AndroidController)
        ocr = MagicMock()
        screen = np.zeros((720, 1280, 3), dtype=np.uint8)
        ctrl.screenshot.return_value = screen
        page = BattlePreparationPage(_make_ctx(ctrl, ocr))
        names = ['岛风', None, None, None, None, None]
        damage = {
            0: ShipDamageState.NORMAL,
            **dict.fromkeys(range(1, 6), ShipDamageState.NO_SHIP),
        }

        with (
            patch.object(page, 'detect_fleet', return_value=names) as detect,
            patch(
                'autowsgr.ui.battle.fleet_change._detect.DetectionMixin.detect_ship_damage',
                return_value=damage,
            ) as detect_damage,
        ):
            snapshot = page.detect_fleet_snapshot(expected_pool=['岛风'])

        assert snapshot == _snapshot(names)
        assert detect.call_args.args[0] is screen
        assert detect.call_args.kwargs == {
            'expected_names': None,
            'expected_pool': ['岛风'],
        }
        assert detect_damage.call_args.args[0] is screen

    def test_snapshot_converts_detail_mappings_to_slot_value_lists(self):
        ctrl = MagicMock(spec=AndroidController)
        screen = np.zeros((720, 1280, 3), dtype=np.uint8)
        ctrl.screenshot.return_value = screen
        page = BattlePreparationPage(_make_ctx(ctrl))

        with (
            patch.object(page, 'detect_fleet', return_value=['岛风', None, None, None, None, None]),
            patch(
                'autowsgr.ui.battle.fleet_change._detect.DetectionMixin.detect_ship_damage',
                return_value={
                    0: ShipDamageState.NORMAL,
                    **dict.fromkeys(range(1, 6), ShipDamageState.NO_SHIP),
                },
            ),
            patch.object(
                page,
                '_recognize_fleet_names_at_slots',
            ) as recognize_names,
            patch.object(
                page,
                '_recognize_fleet_ship_types',
                return_value={0: ShipType.DD, **dict.fromkeys(range(1, 6))},
            ) as recognize_types,
            patch.object(
                page,
                '_recognize_fleet_levels',
                return_value={0: 110, **dict.fromkeys(range(1, 6))},
            ) as recognize_levels,
        ):
            snapshot = page.detect_fleet_snapshot(recognize_ship_details=True)

        assert snapshot.ship_types == [ShipType.DD, None, None, None, None, None]
        assert snapshot.ship_levels == [110, None, None, None, None, None]
        recognize_names.assert_not_called()
        recognize_types.assert_called_once_with(screen, [0])
        recognize_levels.assert_called_once_with(screen, [0])

    def test_snapshot_level2_recognizes_only_unknown_name_slots(self):
        ctrl = MagicMock(spec=AndroidController)
        screen = np.zeros((720, 1280, 3), dtype=np.uint8)
        ctrl.screenshot.return_value = screen
        page = BattlePreparationPage(_make_ctx(ctrl))
        names = ['岛风', None, None, None, None, None]
        damage = {
            0: ShipDamageState.NORMAL,
            1: ShipDamageState.NORMAL,
            **dict.fromkeys(range(2, 6), ShipDamageState.NO_SHIP),
        }

        with (
            patch.object(page, 'detect_fleet', return_value=names),
            patch(
                'autowsgr.ui.battle.fleet_change._detect.DetectionMixin.detect_ship_damage',
                return_value=damage,
            ),
            patch.object(
                page,
                '_recognize_fleet_names_at_slots',
                return_value={1: '雪风'},
            ) as recognize_names,
            patch.object(
                page,
                '_recognize_fleet_ship_types',
                return_value={0: ShipType.DD, 1: ShipType.DD},
            ) as recognize_types,
            patch.object(
                page,
                '_recognize_fleet_levels',
                return_value={0: 110, 1: 80},
            ) as recognize_levels,
        ):
            snapshot = page.detect_fleet_snapshot(
                expected_pool=['岛风', '雪风'],
                recognize_ship_details=True,
            )

        assert snapshot.names == ['岛风', '雪风', None, None, None, None]
        recognize_names.assert_called_once_with(
            screen,
            [1],
            expected_pool=['岛风', '雪风'],
        )
        recognize_types.assert_called_once_with(screen, [0, 1])
        recognize_levels.assert_called_once_with(screen, [0, 1])

    def test_recognized_name_keeps_slot_occupied_when_probe_misses(self):
        ctrl = MagicMock(spec=AndroidController)
        ocr = MagicMock()
        ctrl.screenshot.return_value = np.zeros((720, 1280, 3), dtype=np.uint8)
        page = BattlePreparationPage(_make_ctx(ctrl, ocr))

        with (
            patch.object(
                page,
                'detect_fleet',
                return_value=['岛风', None, None, None, None, None],
            ),
            patch(
                'autowsgr.ui.battle.fleet_change._detect.DetectionMixin.detect_ship_damage',
                return_value=dict.fromkeys(range(6), ShipDamageState.NO_SHIP),
            ),
        ):
            snapshot = page.detect_fleet_snapshot()

        assert snapshot.occupied == [True, False, False, False, False, False]

    def test_initial_snapshot_uses_four_independent_screens(self):
        ctrl = MagicMock(spec=AndroidController)
        screens = [np.full((720, 1280, 3), value, dtype=np.uint8) for value in range(4)]
        ctrl.screenshot.side_effect = screens
        page = BattlePreparationPage(_make_ctx(ctrl))
        rule = FleetSlotRule(
            primary=ShipSelector(
                name='岛风',
                ship_types=(ShipType.DD,),
                min_level=100,
            ),
        )
        selectors = [rule, None, None, None, None, None]

        with (
            patch.object(page, 'detect_fleet', return_value=[None] * 6) as detect_names,
            patch(
                'autowsgr.ui.battle.fleet_change._detect.DetectionMixin.detect_ship_damage',
                return_value={
                    0: ShipDamageState.NORMAL,
                    **dict.fromkeys(range(1, 6), ShipDamageState.NO_SHIP),
                },
            ),
            patch.object(
                page,
                '_recognize_fleet_names_at_slots',
                return_value={0: None},
            ) as recognize_names,
            patch.object(
                page,
                '_recognize_fleet_ship_types',
                return_value={0: None},
            ) as recognize_types,
            patch.object(
                page,
                '_recognize_fleet_levels',
                return_value={0: None},
            ) as recognize_levels,
        ):
            snapshot = page._detect_initial_snapshot(['岛风'], selectors)

        assert snapshot.names == [None] * 6
        assert ctrl.screenshot.call_count == 4
        detect_names.assert_called_once_with(
            screens[0],
            expected_names=None,
            expected_pool=['岛风'],
        )
        assert [item.args[0] for item in recognize_names.call_args_list] == screens[1:]
        assert [item.args[0] for item in recognize_types.call_args_list] == screens[1:3]
        assert [item.args[0] for item in recognize_levels.call_args_list] == screens[1:3]

    def test_initial_snapshot_runs_level3_once_before_level4(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        incomplete = FleetSnapshot(
            names=[None] * 6,
            occupied=[True, False, False, False, False, False],
            ship_types=[None] * 6,
            ship_levels=[None] * 6,
        )
        rule = FleetSlotRule(
            primary=ShipSelector(
                name='岛风',
                ship_types=(ShipType.DD,),
                min_level=100,
            ),
        )
        selectors = [rule, None, None, None, None, None]
        identity = ship_name_identity('岛风')
        assert identity is not None

        with (
            patch.object(page, 'detect_fleet_snapshot', return_value=incomplete),
            patch.object(
                page,
                'fill_missing_fleet_snapshot',
                return_value=incomplete,
            ) as fill_missing,
        ):
            snapshot = page._detect_initial_snapshot(['岛风'], selectors)

        assert snapshot is incomplete
        assert fill_missing.call_args_list == [
            call(incomplete, expected_pool=['岛风']),
            call(incomplete, expected_pool=['岛风']),
            call(
                incomplete,
                expected_pool=['岛风'],
                detail_requirements={identity: (True, True)},
            ),
        ]

    def test_initial_snapshot_retries_level_that_fails_strict_yaml(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        initial = FleetSnapshot(
            names=['U-96', None, None, None, None, None],
            occupied=[True, False, False, False, False, False],
        )
        wrong_level = FleetSnapshot(
            names=list(initial.names),
            occupied=list(initial.occupied),
            ship_types=[ShipType.SS, None, None, None, None, None],
            ship_levels=[11, None, None, None, None, None],
        )
        corrected = FleetSnapshot(
            names=list(initial.names),
            occupied=list(initial.occupied),
            ship_types=[ShipType.SS, None, None, None, None, None],
            ship_levels=[110, None, None, None, None, None],
        )
        rule = FleetSlotRule(
            candidates=(
                ShipSelector(
                    name='U-96',
                    ship_types=(ShipType.SS,),
                    min_level=100,
                ),
            ),
        )

        with (
            patch.object(page, 'detect_fleet_snapshot', return_value=initial),
            patch.object(
                page,
                'fill_missing_fleet_snapshot',
                side_effect=[wrong_level, corrected, corrected],
            ) as fill_missing,
        ):
            snapshot = page._detect_initial_snapshot(
                ['U-96'],
                [rule, None, None, None, None, None],
            )

        assert snapshot.ship_levels[0] == 110
        assert fill_missing.call_count == 3
        assert fill_missing.call_args_list[1].args[0].ship_levels[0] is None
        assert fill_missing.call_args_list[2].args[0].ship_levels[0] == 110

    def test_invalid_strict_ship_type_is_retried(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        snapshot = FleetSnapshot(
            names=['U-96', None, None, None, None, None],
            occupied=[True, False, False, False, False, False],
            ship_types=[ShipType.DD, None, None, None, None, None],
            ship_levels=[110, None, None, None, None, None],
        )
        rule = FleetSlotRule(
            candidates=(
                ShipSelector(
                    name='U-96',
                    ship_types=(ShipType.SS,),
                    min_level=100,
                ),
            ),
        )

        retry_snapshot = page._retry_invalid_strict_details(
            snapshot,
            [rule, None, None, None, None, None],
            level='LEVEL2',
        )

        assert retry_snapshot.ship_types[0] is None
        assert retry_snapshot.ship_levels[0] == 110

    def test_relaxed_details_are_not_retried_when_name_matches(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        snapshot = FleetSnapshot(
            names=['U-96', None, None, None, None, None],
            occupied=[True, False, False, False, False, False],
            ship_types=[ShipType.DD, None, None, None, None, None],
            ship_levels=[11, None, None, None, None, None],
        )
        rule = FleetSlotRule(
            candidates=(
                ShipSelector(
                    name='U-96',
                    ship_types=(ShipType.SS,),
                    min_level=100,
                    relaxed_constraints=True,
                ),
            ),
        )

        retry_snapshot = page._retry_invalid_strict_details(
            snapshot,
            [rule, None, None, None, None, None],
            level='LEVEL2',
        )

        assert retry_snapshot is snapshot
        assert retry_snapshot.ship_types[0] is ShipType.DD
        assert retry_snapshot.ship_levels[0] == 11

    def test_fill_missing_snapshot_only_recognizes_none_fields(self):
        ctrl = MagicMock(spec=AndroidController)
        screen = np.zeros((720, 1280, 3), dtype=np.uint8)
        ctrl.screenshot.return_value = screen
        page = BattlePreparationPage(_make_ctx(ctrl))
        snapshot = FleetSnapshot(
            names=['岛风', None, '雪风', None, None, None],
            occupied=[True, True, True, False, False, False],
            ship_types=[ShipType.DD, ShipType.CL, None, None, None, None],
            ship_levels=[110, None, 80, None, None, None],
        )

        with (
            patch.object(
                page,
                '_recognize_fleet_names_at_slots',
                return_value={1: '密苏里'},
            ) as recognize_names,
            patch.object(
                page,
                '_recognize_fleet_ship_types',
                return_value={2: ShipType.CV},
            ) as recognize_types,
            patch.object(
                page,
                '_recognize_fleet_levels',
                return_value={1: 50},
            ) as recognize_levels,
        ):
            filled = page.fill_missing_fleet_snapshot(
                snapshot,
                expected_pool=['岛风', '密苏里', '雪风'],
            )

        assert filled.names == ['岛风', '密苏里', '雪风', None, None, None]
        assert filled.ship_types == [
            ShipType.DD,
            ShipType.CL,
            ShipType.CV,
            None,
            None,
            None,
        ]
        assert filled.ship_levels == [110, 50, 80, None, None, None]
        recognize_names.assert_called_once_with(
            screen,
            [1],
            expected_pool=['岛风', '密苏里', '雪风'],
        )
        recognize_types.assert_called_once_with(screen, [2])
        recognize_levels.assert_called_once_with(screen, [1])

    def test_level4_new_primary_name_reads_required_details_from_same_screen(self):
        ctrl = MagicMock(spec=AndroidController)
        screen = np.zeros((720, 1280, 3), dtype=np.uint8)
        ctrl.screenshot.return_value = screen
        page = BattlePreparationPage(_make_ctx(ctrl))
        snapshot = FleetSnapshot(
            names=[None] * 6,
            occupied=[True, False, False, False, False, False],
            ship_types=[None] * 6,
            ship_levels=[None] * 6,
        )
        identity = ship_name_identity('岛风')
        assert identity is not None

        with (
            patch.object(
                page,
                '_recognize_fleet_names_at_slots',
                return_value={0: '岛风'},
            ),
            patch.object(
                page,
                '_recognize_fleet_ship_types',
                return_value={0: ShipType.DD},
            ) as recognize_types,
            patch.object(
                page,
                '_recognize_fleet_levels',
                return_value={0: 110},
            ) as recognize_levels,
        ):
            filled = page.fill_missing_fleet_snapshot(
                snapshot,
                expected_pool=['岛风'],
                detail_requirements={identity: (True, True)},
            )

        assert filled.names[0] == '岛风'
        assert filled.ship_types[0] is ShipType.DD
        assert filled.ship_levels[0] == 110
        recognize_types.assert_called_once_with(screen, [0])
        recognize_levels.assert_called_once_with(screen, [0])

    def test_level4_new_candidate_name_skips_details_when_primary_exists(self):
        ctrl = MagicMock(spec=AndroidController)
        ctrl.screenshot.return_value = np.zeros((720, 1280, 3), dtype=np.uint8)
        page = BattlePreparationPage(_make_ctx(ctrl))
        snapshot = FleetSnapshot(
            names=[None] * 6,
            occupied=[True, False, False, False, False, False],
            ship_types=[None] * 6,
            ship_levels=[None] * 6,
        )
        rule = FleetSlotRule(
            primary=ShipSelector(
                name='岛风',
                ship_types=(ShipType.DD,),
                min_level=100,
            ),
            candidates=(
                ShipSelector(
                    name='雪风',
                    ship_types=(ShipType.DD,),
                    min_level=100,
                ),
            ),
        )

        with (
            patch.object(
                page,
                '_recognize_fleet_names_at_slots',
                return_value={0: '雪风'},
            ),
            patch.object(page, '_recognize_fleet_ship_types') as recognize_types,
            patch.object(page, '_recognize_fleet_levels') as recognize_levels,
        ):
            filled = page.fill_missing_fleet_snapshot(
                snapshot,
                expected_pool=['岛风', '雪风'],
                detail_requirements=page._level4_detail_requirements([rule]),
            )

        assert filled.names[0] == '雪风'
        assert filled.ship_types[0] is None
        assert filled.ship_levels[0] is None
        recognize_types.assert_not_called()
        recognize_levels.assert_not_called()

    def test_level4_pure_candidate_reads_its_required_details(self):
        ctrl = MagicMock(spec=AndroidController)
        screen = np.zeros((720, 1280, 3), dtype=np.uint8)
        ctrl.screenshot.return_value = screen
        page = BattlePreparationPage(_make_ctx(ctrl))
        snapshot = FleetSnapshot(
            names=[None] * 6,
            occupied=[True, False, False, False, False, False],
            ship_types=[None] * 6,
            ship_levels=[None] * 6,
        )
        rule = FleetSlotRule(
            candidates=(
                ShipSelector(
                    name='雪风',
                    ship_types=(ShipType.DD,),
                    min_level=100,
                ),
            ),
        )

        with (
            patch.object(
                page,
                '_recognize_fleet_names_at_slots',
                return_value={0: '雪风'},
            ),
            patch.object(
                page,
                '_recognize_fleet_ship_types',
                return_value={0: ShipType.DD},
            ) as recognize_types,
            patch.object(
                page,
                '_recognize_fleet_levels',
                return_value={0: 110},
            ) as recognize_levels,
        ):
            filled = page.fill_missing_fleet_snapshot(
                snapshot,
                expected_pool=['雪风'],
                detail_requirements=page._level4_detail_requirements([rule]),
            )

        assert filled.names[0] == '雪风'
        assert filled.ship_types[0] is ShipType.DD
        assert filled.ship_levels[0] == 110
        recognize_types.assert_called_once_with(screen, [0])
        recognize_levels.assert_called_once_with(screen, [0])

    def test_recognize_fleet_ship_types_on_preparation_screen(self):
        ctrl = MagicMock(spec=AndroidController)
        ocr = MagicMock()
        ocr.recognize.return_value = [OCRResult(text='轻巡(J国)', confidence=0.99)]
        screen = np.zeros((720, 1280, 3), dtype=np.uint8)
        page = BattlePreparationPage(_make_ctx(ctrl, ocr))

        with patch(
            'autowsgr.ui.battle.fleet_change._detect.DetectionMixin.detect_ship_damage',
            return_value=dict.fromkeys(range(6), ShipDamageState.NORMAL),
        ):
            ship_types = page._recognize_fleet_ship_types(screen)

        assert ship_types[0] is ShipType.CL
        assert ocr.recognize.call_count == 6

    def test_recognize_fleet_ship_types_only_scans_requested_slots(self):
        ctrl = MagicMock(spec=AndroidController)
        ocr = MagicMock()
        ocr.recognize.return_value = [OCRResult(text='轻巡', confidence=0.99)]
        screen = np.zeros((720, 1280, 3), dtype=np.uint8)
        page = BattlePreparationPage(_make_ctx(ctrl, ocr))

        with patch.object(page, 'detect_ship_damage') as detect_damage:
            ship_types = page._recognize_fleet_ship_types(screen, [3])

        assert ship_types == {3: ShipType.CL}
        detect_damage.assert_not_called()
        ocr.recognize.assert_called_once()

    def test_best_ship_type_rejects_conflicting_results(self):
        assert (
            BattlePreparationPage._best_ship_type_from_results(
                [OCRResult(text='航母', confidence=0.99)],
            )
            is ShipType.CV
        )
        assert (
            BattlePreparationPage._best_ship_type_from_results(
                [
                    OCRResult(text='航母', confidence=0.99),
                    OCRResult(text='轻母', confidence=0.99),
                ],
            )
            is None
        )
        assert BattlePreparationPage._best_ship_type_from_results([]) is None

    def test_user_ship_name_alias_is_used_for_final_fleet_detection(self):
        ctrl = MagicMock(spec=AndroidController)
        ocr = MagicMock()
        ocr.recognize.return_value = [
            OCRResult(text='契卡洛夫', confidence=0.99, bbox=(127, 2, 167, 24)),
        ]
        page = BattlePreparationPage(_make_ctx(ctrl, ocr))
        set_user_ship_name_aliases({'契卡洛夫': '85工程'})

        try:
            with patch(
                'autowsgr.ui.battle.fleet_change._detect._log.debug',
            ) as log_debug:
                detected = page.detect_fleet(
                    np.zeros((720, 1280, 3), dtype=np.uint8),
                    expected_names=['契卡洛夫'],
                )
        finally:
            set_user_ship_name_aliases({})

        assert detected == ['85工程', None, None, None, None, None]
        log_debug.assert_any_call(
            '[准备页] 舰名OCR原始及后处理: {}',
            [
                {
                    'physical_slot': 1,
                    'raw': '契卡洛夫',
                    'patched': '契卡洛夫',
                    'matched': '85工程',
                    'confidence': 0.99,
                    'bbox': (127, 2, 167, 24),
                }
            ],
        )
        log_debug.assert_any_call(
            '[准备页] 舰名OCR后处理编队: {}',
            ['85工程', None, None, None, None, None],
        )


# ─────────────────────────────────────────────
# 决战换船算法开关
# ─────────────────────────────────────────────


class TestDecisiveFleetChangeFeatureGate:
    def test_original_flow_uses_pool_ocr_without_target_context(self):
        page = MagicMock()
        page.detect_fleet.return_value = ['A', None, None, None, None, None]
        page._validate_with_selector.return_value = True

        assert change_fleet_legacy(page, None, ['A'])

        page.detect_fleet.assert_called_once_with()

    def test_original_flow_changes_ship_and_verifies_result(self):
        page = MagicMock()
        empty_fleet = [None] * 6
        target_fleet = ['A', None, None, None, None, None]
        page.get_selected_fleet.return_value = 3
        page.detect_fleet.side_effect = [empty_fleet, target_fleet, target_fleet]
        page._validate_with_selector.side_effect = [False, True]
        page._match_existing_members.return_value = ([False] * 6, set())
        page._change_single_ship.return_value = 'A'

        with patch('autowsgr.ui.decisive.legacy_fleet_change.time.sleep'):
            assert change_fleet_legacy(page, 2, [' A '])

        page.select_fleet.assert_called_once_with(2)
        page._change_single_ship.assert_called_once_with(
            0,
            'A',
            selector=None,
            slot_occupied=False,
        )
        page._reorder.assert_called_once_with(target_fleet, target_fleet)

    def test_original_flow_changes_first_fleet_before_removing_extra_ship(self):
        page = MagicMock()
        fleet_a_b = ['A', 'B', None, None, None, None]
        fleet_c = ['C', None, None, None, None, None]
        page.get_selected_fleet.return_value = 1
        page.detect_fleet.side_effect = [fleet_a_b, fleet_c, fleet_c]
        page._validate_with_selector.side_effect = [False, True]
        page._match_existing_members.return_value = ([False] * 6, set())
        page._change_single_ship.side_effect = ['C', None]

        with patch('autowsgr.ui.decisive.legacy_fleet_change.time.sleep'):
            assert change_fleet_legacy(page, 1, ['C'])

        actions = [
            (item.args[0], item.args[1], item.kwargs['slot_occupied'])
            for item in page._change_single_ship.call_args_list
        ]
        assert actions == [(0, 'C', True), (1, None, True)]

    def test_original_flow_rejects_empty_first_fleet(self):
        page = MagicMock()

        with pytest.raises(ValueError, match='1 队槽位 0 不能为空'):
            change_fleet_legacy(page, 1, [])

        page.detect_fleet.assert_not_called()
        page.select_fleet.assert_not_called()

    def test_decisive_uses_original_flow_by_default(self):
        page = DecisiveBattlePreparationPage(
            _make_ctx(MagicMock(spec=AndroidController)),
            DecisiveConfig(),
        )

        with patch(
            'autowsgr.ui.decisive.preparation.change_fleet_legacy',
            return_value=True,
        ) as legacy_change:
            assert page.change_fleet(None, ['A'])

        legacy_change.assert_called_once_with(page, None, ['A'])

    def test_decisive_uses_new_flow_when_enabled(self):
        page = DecisiveBattlePreparationPage(
            _make_ctx(MagicMock(spec=AndroidController)),
            DecisiveConfig(use_new_fleet_change_algorithm=True),
        )

        with patch.object(
            BattlePreparationPage,
            'change_fleet',
            return_value=True,
        ) as new_change:
            assert page.change_fleet(None, ['A'])

        new_change.assert_called_once_with(None, exact_fleet_rules(['A']))


class TestFleetSelection:
    @pytest.mark.parametrize(
        'aliases',
        [
            {'别名甲': '85工程', '别名乙': '85工程'},
            {'别名乙': '85工程', '别名甲': '85工程'},
        ],
    )
    def test_try_select_option_retries_all_aliases_in_stable_order(
        self,
        aliases: dict[str, str],
    ):
        page = BattlePreparationPage(
            _make_ctx(MagicMock(spec=AndroidController), MagicMock()),
        )
        set_user_ship_name_aliases(aliases)
        option = ShipSelector(
            name='85工程',
            ship_types=(ShipType.CV,),
            min_level=100,
        )
        first_page = MagicMock()
        first_page.change_single_ship.return_value = None
        second_page = MagicMock()
        second_page.change_single_ship.return_value = '85工程'

        with (
            patch.object(
                page,
                '_open_choose_page',
                side_effect=[first_page, second_page],
            ) as open_page,
            patch.object(page, '_cancel_choose_page') as cancel_page,
        ):
            selected = page._try_select_option(2, option)

        attempted = [
            first_page.change_single_ship.call_args.args[0],
            second_page.change_single_ship.call_args.args[0],
        ]
        assert selected == _ShipSelection(name='85工程', option=option)
        assert [item.search_name for item in attempted] == sorted(aliases)
        assert all(item.ship_types == (ShipType.CV,) for item in attempted)
        assert all(item.min_level == 100 for item in attempted)
        assert open_page.call_args_list == [call(2), call(2)]
        cancel_page.assert_called_once_with()

    def test_try_select_option_falls_back_to_standard_name(self):
        page = BattlePreparationPage(
            _make_ctx(MagicMock(spec=AndroidController), MagicMock()),
        )
        aliases = {'别名甲': '85工程', '别名乙': '85工程'}
        set_user_ship_name_aliases(aliases)
        option = ShipSelector(name='85工程')
        choose_pages = [MagicMock(), MagicMock(), MagicMock()]
        for choose_page in choose_pages[:-1]:
            choose_page.change_single_ship.return_value = None
        choose_pages[-1].change_single_ship.return_value = '85工程'

        with (
            patch.object(
                page,
                '_open_choose_page',
                side_effect=choose_pages,
            ),
            patch.object(page, '_cancel_choose_page') as cancel_page,
        ):
            selected = page._try_select_option(0, option)

        attempted = [
            choose_page.change_single_ship.call_args.args[0].search_name
            for choose_page in choose_pages
        ]
        assert selected == _ShipSelection(name='85工程', option=option)
        assert attempted == [*sorted(aliases), '85工程']
        assert cancel_page.call_count == 2

    def test_explicit_search_name_is_not_expanded(self):
        page = BattlePreparationPage(
            _make_ctx(MagicMock(spec=AndroidController), MagicMock()),
        )
        set_user_ship_name_aliases({'别名甲': '85工程', '别名乙': '85工程'})
        option = ShipSelector(name='85工程', search_name='别名乙')

        assert page._search_options(option) == (option,)


# ─────────────────────────────────────────────
# 智能换船
# ─────────────────────────────────────────────


class TestSmartFleetChange:
    def test_custom_name_search_accepts_standard_name_result(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        set_user_ship_name_aliases({'契卡洛夫': '85工程'})
        old_fleet = ['岛风', None, None, None, None, None]
        target_fleet = ['85工程', None, None, None, None, None]
        snapshots = [
            _snapshot(old_fleet),
            _snapshot(target_fleet),
            _snapshot(target_fleet),
            _snapshot(target_fleet),
        ]

        with (
            patch.object(page, 'get_selected_fleet', return_value=1),
            patch.object(
                page,
                'detect_fleet_snapshot',
                side_effect=snapshots,
            ),
            patch.object(
                page,
                '_try_select_option',
                side_effect=lambda _slot, option: _ShipSelection('85工程', option),
            ) as select_option,
            patch.object(page, '_change_single_ship', return_value=None) as change_ship,
            patch('autowsgr.ui.battle.fleet_change._change.time.sleep'),
        ):
            assert page.change_fleet(
                1,
                [_rule({'candidates': [{'name': '契卡洛夫'}]})],
            )

        assert select_option.call_args == call(
            1,
            ShipSelector(name='契卡洛夫'),
        )
        change_ship.assert_called_once_with(0, None, slot_occupied=True)

    def test_existing_group_variant_is_reordered_without_reselection(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        set_user_ship_name_aliases({'契卡洛夫': '85工程'})
        old_fleet = ['岛风', '85工程', '扶桑', '长春', None, None]
        target_fleet = ['85工程', '岛风', '长春', '扶桑', None, None]

        def move_ship(src: int, dst: int, current: list[str | None]) -> None:
            current.insert(dst, current.pop(src))

        with (
            patch.object(page, 'get_selected_fleet', return_value=1),
            patch.object(
                page,
                'detect_fleet_snapshot',
                side_effect=[
                    _snapshot(old_fleet),
                    _snapshot(target_fleet),
                ],
            ) as detect,
            patch.object(
                page,
                '_try_select_option',
                return_value=None,
            ) as select_option,
            patch.object(page, '_change_single_ship') as change_ship,
            patch.object(page, '_full_align') as full_align,
            patch.object(page, '_local_fix') as local_fix,
            patch.object(page, '_circular_move', side_effect=move_ship) as circular_move,
            patch('autowsgr.ui.battle.fleet_change._change.time.sleep'),
        ):
            assert page.change_fleet(
                1,
                [
                    _rule({'candidates': [{'name': '契卡洛夫'}]}),
                    *exact_fleet_rules(['岛风', '长春', '扶桑']),
                ],
            )

        select_option.assert_not_called()
        change_ship.assert_not_called()
        full_align.assert_not_called()
        local_fix.assert_not_called()
        assert detect.call_count == 2
        assert [item.args[:2] for item in circular_move.call_args_list] == [
            (1, 0),
            (3, 2),
        ]

    def test_final_ocr_keeps_confirmed_names_after_reorder(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        old_fleet = ['B', 'A', 'D', 'C', None, None]
        target_fleet = ['A', 'B', 'C', 'D', None, None]
        final_snapshot = _snapshot(
            [None, None, None, None, None, None],
            [True, True, True, True, False, False],
        )

        def move_ship(src: int, dst: int, current: list[str | None]) -> None:
            current.insert(dst, current.pop(src))

        with (
            patch.object(
                page,
                'detect_fleet_snapshot',
                side_effect=[
                    _snapshot(old_fleet),
                    final_snapshot,
                ],
            ) as detect,
            patch.object(page, '_full_align') as full_align,
            patch.object(page, '_local_fix') as local_fix,
            patch.object(page, '_circular_move', side_effect=move_ship) as circular_move,
        ):
            assert page.change_fleet(None, exact_fleet_rules(target_fleet[:4]))

        full_align.assert_not_called()
        local_fix.assert_not_called()
        assert detect.call_count == 2
        assert [item.args[:2] for item in circular_move.call_args_list] == [
            (1, 0),
            (3, 2),
        ]
        assert page.last_changed_fleet == target_fleet

    def test_position_snapshot_only_keeps_unknown_occupied_names(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        current = ['A', 'B', 'C', None, None, None]
        snapshot = _snapshot(
            [None, 'X', None, None, None, None],
            [True, True, False, False, False, False],
        )

        names, occupied = page._merge_position_snapshot(current, snapshot)

        assert names == ['A', 'X', None, None, None, None]
        assert occupied == [True, True, False, False, False, False]

    def test_candidate_only_reuses_existing_nonpreferred_candidate(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        old_fleet = ['岛风', '扶桑', None, None, None, None]
        target_fleet = ['扶桑', '岛风', None, None, None, None]

        def move_ship(src: int, dst: int, current: list[str | None]) -> None:
            current.insert(dst, current.pop(src))

        with (
            patch.object(
                page,
                'detect_fleet_snapshot',
                side_effect=[
                    _snapshot(old_fleet),
                    _snapshot(old_fleet),
                    _snapshot(old_fleet),
                    _snapshot(target_fleet),
                ],
            ),
            patch.object(page, '_try_select_option') as select_option,
            patch.object(page, '_change_single_ship') as change_ship,
            patch.object(page, '_circular_move', side_effect=move_ship) as circular_move,
            patch('autowsgr.ui.battle.fleet_change._change.time.sleep'),
        ):
            assert page.change_fleet(
                None,
                [
                    _candidate_rule('胡德', '扶桑'),
                    *exact_fleet_rules(['岛风']),
                ],
            )

        select_option.assert_not_called()
        change_ship.assert_not_called()
        assert circular_move.call_args.args[:2] == (1, 0)
        assert page.last_changed_fleet == target_fleet

    def test_first_fleet_replaces_before_removing_extra_ship(self):
        """1 队从 AB 改为 C 时，先补入 C，再删除 A/B。"""
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        fleet_a_b = ['A', 'B', None, None, None, None]
        fleet_c = ['C', None, None, None, None, None]
        actions: list[tuple[str, int, str | None]] = []

        def select_option(slot: int, option: ShipSelector) -> _ShipSelection:
            actions.append(('select', slot, option.name))
            return _ShipSelection(option.name, option)

        def change_ship(
            slot: int,
            name: str | None,
            *,
            slot_occupied: bool,
        ) -> None:
            assert slot_occupied
            actions.append(('remove', slot, name))

        with (
            patch.object(page, 'get_selected_fleet', return_value=1),
            patch.object(
                page,
                'detect_fleet_snapshot',
                side_effect=[
                    _snapshot(fleet_a_b),
                    _snapshot(fleet_c),
                ],
            ) as detect,
            patch.object(page, '_try_select_option', side_effect=select_option),
            patch.object(page, '_change_single_ship', side_effect=change_ship),
            patch('autowsgr.ui.battle.fleet_change._change.time.sleep'),
        ):
            assert page.change_fleet(1, exact_fleet_rules(['C']))

        assert actions == [
            ('select', 2, 'C'),
            ('remove', 1, None),
            ('remove', 0, None),
        ]
        assert detect.call_args_list == [
            call(expected_pool=['C']),
            call(expected_names=fleet_c),
        ]

    def test_first_fleet_cannot_be_empty(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))

        with (
            patch.object(page, 'get_selected_fleet', return_value=1),
            patch.object(page, 'detect_fleet_snapshot') as detect,
            pytest.raises(ValueError, match='1 队槽位 0 不能为空'),
        ):
            page.change_fleet(1, ())

        detect.assert_not_called()

    def test_input_over_six_slots_is_truncated(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        target = ['A', 'B', 'C', 'D', 'E', 'F']

        with patch.object(
            page,
            'detect_fleet_snapshot',
            return_value=_snapshot(target),
        ) as detect:
            assert page.change_fleet(None, exact_fleet_rules([*target, 'G']))

        detect.assert_called_once_with(expected_pool=target)

    def test_duplicate_fixed_names_fail_before_ocr(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))

        with patch.object(page, 'detect_fleet_snapshot') as detect:
            assert not page.change_fleet(None, exact_fleet_rules(['A', 'A']))

        detect.assert_not_called()

    def test_failed_verification_uses_two_local_retries(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        wrong = ['X', None, None, None, None, None]

        with (
            patch.object(
                page,
                'detect_fleet_snapshot',
                return_value=_snapshot(wrong),
            ) as detect,
            patch.object(page, '_full_align') as full_align,
            patch.object(page, '_local_fix') as local_fix,
            patch.object(page, '_reorder'),
            patch('autowsgr.ui.battle.fleet_change._change.time.sleep'),
        ):
            assert not page.change_fleet(None, exact_fleet_rules(['A']))

        assert full_align.call_count == 1
        assert local_fix.call_count == 2
        expected_names = ['A', None, None, None, None, None]
        assert detect.call_args_list == [
            call(expected_pool=['A']),
            call(expected_names=expected_names),
            call(expected_names=expected_names),
            call(expected_names=expected_names),
            call(expected_names=expected_names),
            call(expected_names=expected_names),
        ]

    def test_snapshot_marks_in_place_strict_slot_as_verified(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        option = ShipSelector(name='A', ship_types=(ShipType.DD,), min_level=100)
        snapshot = FleetSnapshot(
            names=['A', None, None, None, None, None],
            occupied=[True, False, False, False, False, False],
            ship_types=[ShipType.DD, None, None, None, None, None],
            ship_levels=[105, None, None, None, None, None],
        )
        verified: set[int] = set()

        page._mark_snapshot_verified_slots(
            snapshot,
            [option, None, None, None, None, None],
            verified,
        )

        assert verified == {0}

    def test_snapshot_rejects_wrong_ship_type(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        option = ShipSelector(name='A', ship_types=(ShipType.DD,), min_level=100)
        snapshot = FleetSnapshot(
            names=['A', None, None, None, None, None],
            occupied=[True, False, False, False, False, False],
            ship_types=[ShipType.CL, None, None, None, None, None],
            ship_levels=[105, None, None, None, None, None],
        )
        verified: set[int] = set()

        page._mark_snapshot_verified_slots(
            snapshot,
            [option, None, None, None, None, None],
            verified,
        )

        assert verified == set()

    def test_snapshot_rejects_level_below_min(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        option = ShipSelector(name='A', ship_types=(ShipType.DD,), min_level=100)
        snapshot = FleetSnapshot(
            names=['A', None, None, None, None, None],
            occupied=[True, False, False, False, False, False],
            ship_types=[ShipType.DD, None, None, None, None, None],
            ship_levels=[95, None, None, None, None, None],
        )
        verified: set[int] = set()

        page._mark_snapshot_verified_slots(
            snapshot,
            [option, None, None, None, None, None],
            verified,
        )

        assert verified == set()

    def test_snapshot_rejects_missing_level(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        option = ShipSelector(name='A', ship_types=(ShipType.DD,), min_level=100)
        snapshot = FleetSnapshot(
            names=['A', None, None, None, None, None],
            occupied=[True, False, False, False, False, False],
            ship_types=[ShipType.DD, None, None, None, None, None],
            ship_levels=[None, None, None, None, None, None],
        )
        verified: set[int] = set()

        page._mark_snapshot_verified_slots(
            snapshot,
            [option, None, None, None, None, None],
            verified,
        )

        assert verified == set()

    def test_snapshot_ignores_relaxed_rules(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        option = ShipSelector(
            name='A',
            ship_types=(ShipType.DD,),
            min_level=100,
            relaxed_constraints=True,
        )
        snapshot = FleetSnapshot(
            names=['A', None, None, None, None, None],
            occupied=[True, False, False, False, False, False],
            ship_types=[ShipType.DD, None, None, None, None, None],
            ship_levels=[105, None, None, None, None, None],
        )
        verified: set[int] = set()

        page._mark_snapshot_verified_slots(
            snapshot,
            [option, None, None, None, None, None],
            verified,
        )

        assert verified == set()

    def test_relaxed_assignment_only_requires_matching_name(self):
        option = ShipSelector(
            name='A',
            ship_types=(ShipType.DD,),
            min_level=100,
            relaxed_constraints=True,
        )

        assert BattlePreparationPage._validate_assignment(
            ['A', None, None, None, None, None],
            [True, False, False, False, False, False],
            [option, None, None, None, None, None],
        )
        assert not BattlePreparationPage._validate_assignment(
            [None] * 6,
            [True, False, False, False, False, False],
            [option, None, None, None, None, None],
        )

    def test_strict_assignment_requires_constraint_verification(self):
        option = ShipSelector(
            name='A',
            ship_types=(ShipType.DD,),
            min_level=100,
        )
        current = ['A', None, None, None, None, None]
        occupied = [True, False, False, False, False, False]
        assigned = [option, None, None, None, None, None]

        assert not BattlePreparationPage._validate_assignment(
            current,
            occupied,
            assigned,
        )
        assert BattlePreparationPage._validate_assignment(
            current,
            occupied,
            assigned,
            {0},
        )

    def test_member_set_satisfied_ignores_order_but_rejects_extra_member(self):
        assigned: list[ShipSelector | None] = [
            ShipSelector(name='A'),
            ShipSelector(name='B'),
            None,
            None,
            None,
            None,
        ]
        current = ['B', 'A', None, None, None, None]
        occupied = [True, True, False, False, False, False]

        assert BattlePreparationPage._member_set_satisfied(
            current,
            occupied,
            assigned,
            set(),
        )
        assert not BattlePreparationPage._member_set_satisfied(
            ['B', 'A', 'X', None, None, None],
            [True, True, True, False, False, False],
            assigned,
            set(),
        )

    def test_member_set_satisfied_requires_strict_verification(self):
        assigned: list[ShipSelector | None] = [
            ShipSelector(name='A', ship_types=(ShipType.DD,), min_level=100),
            None,
            None,
            None,
            None,
            None,
        ]
        current = ['A', None, None, None, None, None]
        occupied = [True, False, False, False, False, False]

        assert not BattlePreparationPage._member_set_satisfied(
            current,
            occupied,
            assigned,
            set(),
        )
        assert BattlePreparationPage._member_set_satisfied(
            current,
            occupied,
            assigned,
            {0},
        )

    def test_snapshot_marks_mispositioned_target_as_verified(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        option = ShipSelector(name='A', ship_types=(ShipType.DD,), min_level=100)
        snapshot = FleetSnapshot(
            names=[None, None, 'A', None, None, None],
            occupied=[False, False, True, False, False, False],
            ship_types=[None, None, ShipType.DD, None, None, None],
            ship_levels=[None, None, 105, None, None, None],
        )
        verified: set[int] = set()

        page._mark_snapshot_verified_slots(
            snapshot,
            [option, None, None, None, None, None],
            verified,
        )

        assert verified == {0}

    def test_snapshot_reverifies_in_place_candidate_after_replan(self):
        """主选不在船池时重规划到已就位的备选，直接用首次快照标记为已验证。"""
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        rule = FleetSlotRule(
            primary=ShipSelector(name='A', ship_types=(ShipType.DD,), min_level=100),
            candidates=(ShipSelector(name='B', ship_types=(ShipType.DD,), min_level=100),),
        )
        selectors: list[FleetSlotRule | None] = [rule, None, None, None, None, None]
        current = ['B', None, None, None, None, None]
        occupied = [True, False, False, False, False, False]
        # 首次快照确认槽位 0 的 B 已就位且满足 DD/100 约束。
        page._initial_snapshot = FleetSnapshot(
            names=['B', None, None, None, None, None],
            occupied=[True, False, False, False, False, False],
            ship_types=[ShipType.DD, None, None, None, None, None],
            ship_levels=[100, None, None, None, None, None],
        )
        assigned = BattlePreparationPage._plan_target_options(selectors)
        assert assigned is not None
        assert assigned[0].name == 'A'
        verified: set[int] = set()
        selected: list[str] = []

        def select_option(_slot: int, option: ShipSelector) -> _ShipSelection:
            selected.append(option.name)
            # 主选 A 不在船池，选择失败；已就位的备选 B 不应再被尝试。
            return _ShipSelection(None, option)

        with (
            patch.object(page, '_try_select_option', side_effect=select_option),
            patch('autowsgr.ui.battle.fleet_change._change.time.sleep'),
        ):
            page._align_member_set(
                current,
                occupied,
                assigned,
                selectors,
                verified,
                set(),
                {},
            )

        # 主选失败后改派已就位备选 B，且直接用首次快照标记为已验证。
        assert selected == ['A']
        assert assigned[0].name == 'B'
        assert 0 in verified

    def test_unknown_primary_slot_is_deferred_when_candidate_exists(self):
        primary = ShipSelector(name='A')
        candidate = ShipSelector(name='B')
        rule = FleetSlotRule(primary=primary, candidates=(candidate,))
        snapshot = FleetSnapshot(
            names=[None, 'C', None, None, None, None],
            occupied=[True, True, False, False, False, False],
        )

        assert BattlePreparationPage._deferred_primary_slots(
            snapshot,
            [rule, None, None, None, None, None],
            [primary, None, None, None, None, None],
        ) == {0}

    def test_unknown_primary_only_slot_is_selected_once(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        primary = ShipSelector(name='A', ship_types=(ShipType.DD,))
        rule = FleetSlotRule(primary=primary)
        selectors: list[FleetSlotRule | None] = [rule, None, None, None, None, None]
        assigned: list[ShipSelector | None] = [primary, None, None, None, None, None]
        current = [None, None, None, None, None, None]
        occupied = [True, False, False, False, False, False]
        verified: set[int] = set()
        locked: dict[int, ShipSelector] = {}
        deferred = BattlePreparationPage._deferred_primary_slots(
            FleetSnapshot(names=current, occupied=occupied),
            selectors,
            assigned,
        )

        with (
            patch.object(
                page,
                '_try_select_option',
                return_value=_ShipSelection('A', primary),
            ) as select_option,
            patch('autowsgr.ui.battle.fleet_change._change.time.sleep'),
        ):
            page._resolve_deferred_primaries(
                current,
                occupied,
                assigned,
                selectors,
                verified,
                set(),
                locked,
                deferred,
            )

        select_option.assert_called_once_with(0, primary)
        assert current[0] == 'A'
        assert verified == {0}
        assert locked == {0: primary}
        assert deferred == set()

    def test_unknown_primary_only_slot_stops_when_search_is_empty(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        primary = ShipSelector(name='A')
        rule = FleetSlotRule(primary=primary)
        snapshot = FleetSnapshot(
            names=[None, None, None, None, None, None],
            occupied=[True, False, False, False, False, False],
        )

        with (
            patch.object(page, '_detect_initial_snapshot', return_value=snapshot),
            patch.object(
                page,
                '_try_select_option',
                return_value=_ShipSelection(None, primary),
            ) as select_option,
            patch.object(page, 'detect_fleet_snapshot') as detect,
            patch('autowsgr.ui.battle.fleet_change._change._log.error') as log_error,
        ):
            assert not page.change_fleet(None, [rule])

        select_option.assert_called_once_with(0, primary)
        detect.assert_not_called()
        errors = [str(item.args[1]) for item in log_error.call_args_list]
        selection_error = next(error for error in errors if "槽位 1 的主选 'A' 选择失败" in error)
        assert '主选 OCR 识别失败' in selection_error
        assert '账号不存在该舰船' in selection_error
        assert "槽位1舰名未识别，目标为'A'" in errors

    def test_unknown_slot_uses_candidate_then_rechecks_primary(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        primary = ShipSelector(name='A', ship_types=(ShipType.DD,))
        candidate = ShipSelector(name='B')
        rule = FleetSlotRule(primary=primary, candidates=(candidate,))
        selectors: list[FleetSlotRule | None] = [rule, None, None, None, None, None]
        assigned: list[ShipSelector | None] = [primary, None, None, None, None, None]
        current = [None, None, None, None, None, None]
        occupied = [True, False, False, False, False, False]
        verified: set[int] = set()
        unavailable: set[tuple[int, ShipSelector]] = set()
        locked: dict[int, ShipSelector] = {}
        deferred = {0}

        with (
            patch.object(
                page,
                '_try_select_option',
                side_effect=[
                    _ShipSelection('B', candidate),
                    _ShipSelection('A', primary),
                ],
            ) as select_option,
            patch('autowsgr.ui.battle.fleet_change._change.time.sleep'),
        ):
            page._align_member_set(
                current,
                occupied,
                assigned,
                selectors,
                verified,
                unavailable,
                locked,
                deferred,
            )

        assert select_option.call_args_list == [
            call(0, candidate),
            call(0, primary),
        ]
        assert current[0] == 'A'
        assert assigned[0] == primary
        assert verified == {0}
        assert locked == {0: primary}
        assert unavailable == set()
        assert deferred == set()

    def test_unknown_slot_keeps_candidate_when_primary_recheck_fails(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        primary = ShipSelector(name='A', ship_types=(ShipType.DD,))
        candidate = ShipSelector(name='B', ship_types=(ShipType.DD,))
        rule = FleetSlotRule(primary=primary, candidates=(candidate,))
        selectors: list[FleetSlotRule | None] = [rule, None, None, None, None, None]
        assigned: list[ShipSelector | None] = [primary, None, None, None, None, None]
        current = [None, None, None, None, None, None]
        occupied = [True, False, False, False, False, False]
        verified: set[int] = set()
        unavailable: set[tuple[int, ShipSelector]] = set()
        locked: dict[int, ShipSelector] = {}

        with (
            patch.object(
                page,
                '_try_select_option',
                side_effect=[
                    _ShipSelection('B', candidate),
                    _ShipSelection(None, primary),
                ],
            ) as select_option,
            patch('autowsgr.ui.battle.fleet_change._change.time.sleep'),
        ):
            page._align_member_set(
                current,
                occupied,
                assigned,
                selectors,
                verified,
                unavailable,
                locked,
                {0},
            )

        assert select_option.call_args_list == [
            call(0, candidate),
            call(0, primary),
        ]
        assert current[0] == 'B'
        assert assigned[0] == candidate
        assert verified == {0}
        assert locked == {0: candidate}
        assert unavailable == {(0, primary)}

    def test_deferred_primary_skips_candidate_reserved_by_another_slot(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        primary_a = ShipSelector(name='A')
        reserved_b = ShipSelector(name='B')
        fallback_c = ShipSelector(name='C')
        rule_a = FleetSlotRule(
            primary=primary_a,
            candidates=(reserved_b, fallback_c),
        )
        rule_b = FleetSlotRule(primary=reserved_b)
        selectors: list[FleetSlotRule | None] = [
            rule_a,
            rule_b,
            None,
            None,
            None,
            None,
        ]
        assigned: list[ShipSelector | None] = [
            primary_a,
            reserved_b,
            None,
            None,
            None,
            None,
        ]
        current = [None, None, None, None, None, None]
        occupied = [True, False, False, False, False, False]

        with (
            patch.object(
                page,
                '_try_select_option',
                side_effect=[
                    _ShipSelection('C', fallback_c),
                    _ShipSelection('A', primary_a),
                ],
            ) as select_option,
            patch('autowsgr.ui.battle.fleet_change._change.time.sleep'),
        ):
            page._resolve_deferred_primaries(
                current,
                occupied,
                assigned,
                selectors,
                set(),
                set(),
                {},
                {0},
            )

        assert select_option.call_args_list == [
            call(0, fallback_c),
            call(0, primary_a),
        ]
        assert current[0] == 'A'

    def test_deferred_primary_tries_candidates_in_yaml_order(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        primary = ShipSelector(name='A')
        candidate_b = ShipSelector(name='B')
        candidate_c = ShipSelector(name='C')
        rule = FleetSlotRule(
            primary=primary,
            candidates=(candidate_b, candidate_c),
        )
        selectors: list[FleetSlotRule | None] = [rule, None, None, None, None, None]
        assigned: list[ShipSelector | None] = [primary, None, None, None, None, None]
        current = [None, None, None, None, None, None]
        occupied = [True, False, False, False, False, False]
        unavailable: set[tuple[int, ShipSelector]] = set()

        with (
            patch.object(
                page,
                '_try_select_option',
                side_effect=[
                    _ShipSelection(None, candidate_b),
                    _ShipSelection('C', candidate_c),
                    _ShipSelection('A', primary),
                ],
            ) as select_option,
            patch('autowsgr.ui.battle.fleet_change._change.time.sleep'),
        ):
            page._resolve_deferred_primaries(
                current,
                occupied,
                assigned,
                selectors,
                set(),
                unavailable,
                {},
                {0},
            )

        assert select_option.call_args_list == [
            call(0, candidate_b),
            call(0, candidate_c),
            call(0, primary),
        ]
        assert unavailable == {(0, candidate_b)}
        assert current[0] == 'A'


class TestFleetSlotRules:
    @pytest.mark.parametrize(
        ('raw', 'expected'),
        [
            (None, None),
            ('  岛风  ', '岛风'),
            ('岛风·改', '岛风'),
            ('飞龙（苍青幻影）', '飞龙'),
            ('', None),
        ],
    )
    def test_normalize_ship_name(self, raw: object, expected: str | None):
        assert normalize_ship_name(raw) == expected

    def test_primary_and_candidates_keep_independent_rules(self):
        selector = _rule(
            {
                'name': '密苏里',
                'candidates': [
                    {
                        'name': '衣阿华',
                        'ship_type': ['BC'],
                        'min_level': 90,
                        'max_level': 105,
                    },
                    {
                        'name': '密苏里',
                        'ship_type': ['BB'],
                        'min_level': 80,
                        'max_level': 110,
                    },
                ],
                'ship_type': ['BB'],
                'min_level': 100,
                'max_level': 110,
            },
        )

        assert selector.primary == ShipSelector(
            name='密苏里',
            ship_types=(ShipType.BB,),
            min_level=100,
            max_level=110,
        )
        assert selector.candidates == (
            ShipSelector(
                name='衣阿华',
                ship_types=(ShipType.BC,),
                min_level=90,
                max_level=105,
            ),
            ShipSelector(
                name='密苏里',
                ship_types=(ShipType.BB,),
                min_level=80,
                max_level=110,
            ),
        )

    def test_candidate_only_rules_keep_order_and_relax_constraints(self):
        rule = _rule(
            {
                'candidates': [
                    {
                        'name': '胡德',
                        'ship_type': ['BC'],
                        'min_level': 90,
                    },
                    {
                        'name': '扶桑',
                        'ship_type': ['BB'],
                        'max_level': 110,
                    },
                ],
            },
        )

        assert rule.primary is None
        assert rule.candidates == (
            ShipSelector(
                name='胡德',
                ship_types=(ShipType.BC,),
                min_level=90,
            ),
            ShipSelector(
                name='扶桑',
                ship_types=(ShipType.BB,),
                max_level=110,
            ),
        )

    def test_existing_strict_primary_is_reselected_for_constraint_validation(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        rule = _rule(
            {
                'name': '密苏里',
                'ship_type': ['BB'],
                'min_level': 100,
                'max_level': 110,
            },
        )
        current = ['密苏里', None, None, None, None, None]
        option = rule.primary
        assert option is not None

        with (
            patch.object(
                page,
                'detect_fleet_snapshot',
                side_effect=[_snapshot(current) for _ in range(4)],
            ),
            patch.object(
                page,
                '_try_select_option',
                return_value=_ShipSelection('密苏里', option),
            ) as select_option,
            patch.object(page, '_change_single_ship') as change_ship,
            patch('autowsgr.ui.battle.fleet_change._change.time.sleep'),
        ):
            assert page.change_fleet(None, [rule])

        select_option.assert_called_once_with(
            0,
            ShipSelector(
                name='密苏里',
                ship_types=(ShipType.BB,),
                min_level=100,
                max_level=110,
            ),
        )
        change_ship.assert_not_called()

    def test_existing_candidate_only_ship_requires_its_constraints(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        rule = _rule(
            {
                'candidates': [
                    {
                        'name': '胡德',
                        'ship_type': ['BC'],
                        'min_level': 90,
                    },
                ],
            },
        )
        current = ['胡德', None, None, None, None, None]

        with (
            patch.object(
                page,
                'detect_fleet_snapshot',
                return_value=_snapshot(current),
            ),
            patch.object(
                page,
                '_try_select_option',
                return_value=_ShipSelection('胡德', rule.candidates[0]),
            ) as select_option,
            patch.object(page, '_change_single_ship') as change_ship,
        ):
            assert page.change_fleet(None, [rule])

        select_option.assert_called_once_with(0, rule.candidates[0])
        change_ship.assert_not_called()

    def test_existing_candidate_does_not_replace_available_strict_primary(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        rule = _rule(
            {
                'name': '密苏里',
                'ship_type': ['BB'],
                'min_level': 100,
                'candidates': [{'name': '衣阿华'}],
            },
        )
        current = ['衣阿华', None, None, None, None, None]
        target = ['密苏里', None, None, None, None, None]
        primary = rule.primary
        assert primary is not None

        with (
            patch.object(
                page,
                'detect_fleet_snapshot',
                side_effect=[
                    _snapshot(current),
                    _snapshot(target),
                    _snapshot(target),
                    _snapshot(target),
                ],
            ),
            patch.object(
                page,
                '_try_select_option',
                return_value=_ShipSelection('密苏里', primary),
            ) as select_option,
            patch.object(page, '_change_single_ship', return_value=None),
            patch('autowsgr.ui.battle.fleet_change._change.time.sleep'),
        ):
            assert page.change_fleet(None, [rule])

        select_option.assert_called_once_with(1, primary)
        assert page.last_changed_fleet == target

    def test_strict_primary_failure_then_reuses_existing_candidate(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        rule = _rule(
            {
                'name': '密苏里',
                'ship_type': ['BB'],
                'min_level': 100,
                'candidates': [{'name': '衣阿华'}],
            },
        )
        current = ['衣阿华', None, None, None, None, None]
        primary = rule.primary
        assert primary is not None

        with (
            patch.object(
                page,
                'detect_fleet_snapshot',
                side_effect=[_snapshot(current) for _ in range(4)],
            ),
            patch.object(
                page,
                '_try_select_option',
                return_value=_ShipSelection(None, primary),
            ) as select_option,
            patch.object(page, '_change_single_ship') as change_ship,
            patch('autowsgr.ui.battle.fleet_change._change.time.sleep'),
        ):
            assert page.change_fleet(None, [rule])

        select_option.assert_called_once_with(1, primary)
        change_ship.assert_not_called()
        assert page.last_changed_fleet == current

    def test_primary_identity_is_reserved_from_candidate_only_slot(self):
        primary_rule = FleetSlotRule(primary=ShipSelector(name='A'))
        candidate_only = _candidate_rule('A', 'B')
        assigned = BattlePreparationPage._plan_target_options(
            [candidate_only, primary_rule, None, None, None, None],
            ['A', 'B', None, None, None, None],
        )

        assert BattlePreparationPage._target_names(assigned or []) == [
            'B',
            'A',
            None,
            None,
            None,
            None,
        ]

    def test_fallback_replans_all_unlocked_candidate_slots(self):
        selectors: list[FleetSlotRule | None] = [
            FleetSlotRule(
                primary=ShipSelector(name='A'),
                candidates=(ShipSelector(name='B', relaxed_constraints=True),),
            ),
            _candidate_rule('B', 'C'),
            None,
            None,
            None,
            None,
        ]
        primary = selectors[0].primary
        assert primary is not None
        assigned = BattlePreparationPage._plan_target_options(
            selectors,
            ['B', 'C', None, None, None, None],
            {(0, primary)},
        )

        assert BattlePreparationPage._target_names(assigned or []) == [
            'B',
            'C',
            None,
            None,
            None,
            None,
        ]

    def test_same_name_fallback_keeps_exact_candidate_rule(self):
        rule = _rule(
            {
                'name': '密苏里',
                'ship_type': ['BB'],
                'min_level': 100,
                'candidates': [{'name': '密苏里'}],
            },
        )
        primary = rule.primary
        assert primary is not None
        assigned = BattlePreparationPage._plan_target_options(
            [rule, None, None, None, None, None],
            unavailable={(0, primary)},
        )

        assert assigned is not None
        assert assigned[0] == ShipSelector(
            name='密苏里',
            relaxed_constraints=False,
        )

    def test_existing_members_are_matched_only_once(self):
        current = ['炽热', '絮弗伦', '岛风', '黑潮', None, None]
        desired = ['岛风', '黑潮', '阳炎', '早春', '吹雪', '初夏']
        shared = ['岛风', '黑潮', '阳炎', '早春', '吹雪', '初夏']
        selectors: list[FleetSlotRule | None] = [
            _candidate_rule('岛风'),
            *[_candidate_rule(*shared) for _ in range(5)],
        ]

        ok, matched_slots = BattlePreparationPage._match_existing_members(
            current,
            desired,
            selectors,
        )

        assert matched_slots == {0, 1}
        assert ok == [False, False, True, True, False, False]

    def test_final_validation_rejects_duplicate_names(self):
        current = ['岛风', '岛风', None, None, None, None]

        assert not BattlePreparationPage._validate_with_selector(
            current,
            current,
            [None] * 6,
        )

    def test_strict_constraints_require_selection_verification(self):
        current = ['密苏里', None, None, None, None, None]
        selectors: list[FleetSlotRule | None] = [
            _rule(
                {
                    'name': '密苏里',
                    'ship_type': ['BB'],
                    'min_level': 100,
                },
            ),
            None,
            None,
            None,
            None,
            None,
        ]

        assert not BattlePreparationPage._validate_with_selector(
            current,
            current,
            selectors,
        )
        assert BattlePreparationPage._validate_with_selector(
            current,
            current,
            selectors,
            {0},
        )


class TestFleetAlignment:
    def test_fleet_change_tries_candidates_in_rule_order(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        primary = ShipSelector(name='U-47')
        candidate = ShipSelector(name='U-96', relaxed_constraints=True)

        with (
            patch.object(page, 'click_ship_slot'),
            patch('autowsgr.ui.utils.wait_for_page'),
            patch(
                'autowsgr.ui.choose_ship_page.ChooseShipPage.change_single_ship',
                side_effect=[None, 'U-96'],
            ) as change_single_ship,
        ):
            selected = page._change_single_ship(
                0,
                'U-47',
                selector=(primary, candidate),
            )

        assert selected == 'U-96'
        assert change_single_ship.call_args_list == [
            call(primary, use_search=True),
            call(candidate, use_search=True),
        ]

    def test_slot_failure_does_not_borrow_another_slot_candidates(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        current = [None] * 6
        occupied = [False] * 6
        selectors: list[FleetSlotRule | None] = [
            _candidate_rule('契卡洛夫', min_level=100),
            _candidate_rule('岛风', '黑潮', min_level=100),
            None,
            None,
            None,
            None,
        ]
        assigned = BattlePreparationPage._plan_target_options(selectors)
        assert assigned is not None

        with (
            patch.object(
                page,
                '_try_select_option',
                side_effect=RuntimeError('未找到契卡洛夫'),
            ) as select_option,
            pytest.raises(RuntimeError, match='契卡洛夫'),
        ):
            page._align_member_set(
                current,
                occupied,
                assigned,
                selectors,
                set(),
                set(),
                {},
            )

        select_option.assert_called_once_with(
            0,
            ShipSelector(
                name='契卡洛夫',
                min_level=100,
                relaxed_constraints=True,
            ),
        )

    def test_existing_primary_members_are_kept_until_final_reorder(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        current = ['X', 'A', 'C', 'E', 'Y', 'Z']
        occupied = [True] * 6
        selectors: list[FleetSlotRule | None] = list(
            exact_fleet_rules(['A', 'B', 'C', 'D', 'E', 'F']),
        )
        assigned = BattlePreparationPage._plan_target_options(selectors, current)
        assert assigned is not None
        selected: list[tuple[int, str]] = []

        def select_option(slot: int, option: ShipSelector) -> _ShipSelection:
            selected.append((slot, option.name))
            return _ShipSelection(option.name, option)

        with (
            patch.object(page, '_try_select_option', side_effect=select_option),
            patch('autowsgr.ui.battle.fleet_change._change.time.sleep'),
        ):
            page._align_member_set(
                current,
                occupied,
                assigned,
                selectors,
                set(),
                set(),
                {},
            )

        assert selected == [(0, 'B'), (4, 'D'), (5, 'F')]
        assert current == ['B', 'A', 'C', 'E', 'D', 'F']

        with patch('autowsgr.ui.battle.fleet_change._change.time.sleep'):
            page._reorder(current, ['A', 'B', 'C', 'D', 'E', 'F'])

        assert current == ['A', 'B', 'C', 'D', 'E', 'F']

    def test_technical_selection_error_does_not_enable_fallback(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        rule = FleetSlotRule(
            primary=ShipSelector(name='A'),
            candidates=(ShipSelector(name='B', relaxed_constraints=True),),
        )
        selectors: list[FleetSlotRule | None] = [rule, None, None, None, None, None]
        assigned = BattlePreparationPage._plan_target_options(selectors)
        assert assigned is not None
        unavailable: set[tuple[int, ShipSelector]] = set()

        with (
            patch.object(
                page,
                '_try_select_option',
                side_effect=RuntimeError('控制器断开'),
            ),
            pytest.raises(RuntimeError, match='控制器断开'),
        ):
            page._align_member_set(
                [None] * 6,
                [False] * 6,
                assigned,
                selectors,
                set(),
                unavailable,
                {},
            )

        assert unavailable == set()
        assert assigned[0] == rule.primary

    def test_local_fix_replaces_before_removing(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        current = ['A', 'X', 'C', 'D', None, None]
        occupied = [True, True, True, True, False, False]
        selectors: list[FleetSlotRule | None] = [
            *exact_fleet_rules(['A', 'B', 'C']),
            None,
            None,
            None,
        ]
        assigned = BattlePreparationPage._plan_target_options(selectors)
        assert assigned is not None
        actions: list[str] = []

        with (
            patch.object(
                page,
                '_try_select_option',
                side_effect=lambda _slot, option: (
                    actions.append('replace') or _ShipSelection(option.name, option)
                ),
            ),
            patch.object(
                page,
                '_change_single_ship',
                side_effect=lambda *_args, **_kwargs: actions.append('remove'),
            ),
            patch.object(
                page,
                'detect_fleet_snapshot',
            ) as detect,
            patch('autowsgr.ui.battle.fleet_change._change.time.sleep'),
        ):
            page._local_fix(
                current,
                occupied,
                assigned,
                selectors,
                set(),
                set(),
                {},
            )

        assert actions[0] == 'replace'
        assert actions[1:] == ['remove', 'remove']
        assert current == ['A', 'C', 'B', None, None, None]
        assert occupied == [True, True, True, False, False, False]
        detect.assert_not_called()

    def test_unknown_occupied_slot_is_not_treated_as_empty(self):
        option = ShipSelector(name='A')
        current = [None, None, None, None, None, None]
        occupied = [True, False, False, False, False, False]

        assert (
            BattlePreparationPage._replacement_slot(
                current,
                occupied,
                option,
                set(),
                None,
                set(),
                0,
            )
            == 1
        )

    def test_unknown_slot_is_used_after_normal_selection_failed(self):
        option = ShipSelector(name='A')
        current = [None, 'X', None, None, None, None]
        occupied = [True, True, False, False, False, False]
        attempted = {(0, option, 2)}

        assert (
            BattlePreparationPage._replacement_slot(
                current,
                occupied,
                option,
                set(),
                None,
                attempted,
                0,
            )
            == 0
        )

    def test_reorder_moves_existing_ship(self):
        ctrl = MagicMock(spec=AndroidController)
        page = BattlePreparationPage(_make_ctx(ctrl))
        current = ['B', 'A', None, None, None, None]

        with patch('autowsgr.ui.battle.fleet_change._change.time.sleep'):
            page._reorder(current, ['A', 'B', None, None, None, None])

        assert current == ['A', 'B', None, None, None, None]
        ctrl.swipe.assert_called_once()
