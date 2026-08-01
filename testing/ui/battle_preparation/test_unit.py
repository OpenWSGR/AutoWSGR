"""测试 出征准备页面 UI 控制器。"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from autowsgr.context import GameContext
from autowsgr.emulator import AndroidController
from autowsgr.infra import DecisiveConfig
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
from autowsgr.ui.decisive.legacy_fleet_change import change_fleet_legacy
from autowsgr.ui.decisive.preparation import DecisiveBattlePreparationPage
from autowsgr.vision import OCRResult
from autowsgr.vision.ocr_rules import set_user_ship_name_aliases


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


def _make_ctx(ctrl: AndroidController, ocr: OCREngine | None = None) -> GameContext:
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

    def test_unexpected_pool_match_uses_context_target(self):
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

        assert detected == expected

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

    def test_user_ship_name_alias_is_used_for_final_fleet_detection(self):
        ctrl = MagicMock(spec=AndroidController)
        ocr = MagicMock()
        ocr.recognize.return_value = [
            OCRResult(text='契卡洛夫', confidence=0.99, bbox=(127, 2, 167, 24)),
        ]
        page = BattlePreparationPage(_make_ctx(ctrl, ocr))
        set_user_ship_name_aliases({'契卡洛夫': '85工程'})

        try:
            detected = page.detect_fleet(
                np.zeros((720, 1280, 3), dtype=np.uint8),
                expected_names=['契卡洛夫'],
            )
        finally:
            set_user_ship_name_aliases({})

        assert detected == ['85工程', None, None, None, None, None]


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

        new_change.assert_called_once_with(None, ['A'])


# ─────────────────────────────────────────────
# 智能换船
# ─────────────────────────────────────────────


class TestSmartFleetChange:
    def test_custom_name_search_accepts_standard_name_result(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        set_user_ship_name_aliases({'契卡洛夫': '85工程'})
        old_fleet = ['岛风', None, None, None, None, None]
        target_fleet = ['85工程', None, None, None, None, None]

        with (
            patch.object(page, 'get_selected_fleet', return_value=1),
            patch.object(
                page,
                'detect_fleet',
                side_effect=[old_fleet, target_fleet, target_fleet, target_fleet],
            ),
            patch.object(page, '_change_single_ship', return_value='85工程') as change_ship,
            patch('autowsgr.ui.battle.fleet_change._change.time.sleep'),
        ):
            assert page.change_fleet(1, [{'candidates': ['契卡洛夫']}])

        assert change_ship.call_args.args[:2] == (0, '契卡洛夫')
        assert change_ship.call_args.kwargs['selector']['candidates'] == ['契卡洛夫']

    def test_existing_group_variant_is_reordered_without_reselection(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        set_user_ship_name_aliases({'契卡洛夫': '85工程'})
        old_fleet = ['岛风', '85工程', None, None, None, None]
        target_fleet = ['85工程', '岛风', None, None, None, None]

        def move_ship(src: int, dst: int, current: list[str | None]) -> None:
            current.insert(dst, current.pop(src))

        with (
            patch.object(page, 'get_selected_fleet', return_value=1),
            patch.object(
                page,
                'detect_fleet',
                side_effect=[old_fleet, old_fleet, old_fleet, target_fleet],
            ),
            patch.object(page, '_change_single_ship') as change_ship,
            patch.object(page, '_circular_move', side_effect=move_ship) as circular_move,
            patch('autowsgr.ui.battle.fleet_change._change.time.sleep'),
        ):
            assert page.change_fleet(1, [{'candidates': ['契卡洛夫']}, '岛风'])

        change_ship.assert_not_called()
        assert circular_move.call_args.args[:2] == (1, 0)

    def test_first_fleet_replaces_before_removing_extra_ship(self):
        """1 队从 AB 改为 C 时，先替换槽位 0，再移除 B。"""
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        fleet_a_b = ['A', 'B', None, None, None, None]
        fleet_c = ['C', None, None, None, None, None]

        with (
            patch.object(page, 'get_selected_fleet', return_value=1),
            patch.object(
                page,
                'detect_fleet',
                side_effect=[fleet_a_b, fleet_c, fleet_c, fleet_c],
            ) as detect,
            patch.object(
                page,
                '_change_single_ship',
                side_effect=['C', None],
            ) as change_ship,
            patch('autowsgr.ui.battle.fleet_change._change.time.sleep'),
        ):
            assert page.change_fleet(1, ['C'])

        actions = [
            (item.args[0], item.args[1], item.kwargs['slot_occupied'])
            for item in change_ship.call_args_list
        ]
        assert actions == [(0, 'C', True), (1, None, True)]
        assert all(not item.args and not item.kwargs for item in detect.call_args_list)

    def test_first_fleet_slot_zero_cannot_be_empty(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))

        with (
            patch.object(page, 'get_selected_fleet', return_value=1),
            pytest.raises(ValueError, match='1 队槽位 0 不能为空'),
        ):
            page.change_fleet(1, [None, 'B'])

    def test_first_fleet_cannot_be_empty(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))

        with (
            patch.object(page, 'get_selected_fleet', return_value=1),
            patch.object(page, 'detect_fleet') as detect,
            pytest.raises(ValueError, match='1 队槽位 0 不能为空'),
        ):
            page.change_fleet(1, [])

        detect.assert_not_called()

    def test_input_over_six_slots_is_truncated(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        target = ['A', 'B', 'C', 'D', 'E', 'F']

        with patch.object(page, 'detect_fleet', return_value=target) as detect:
            assert page.change_fleet(None, [*target, 'G'])

        detect.assert_called_once_with()

    def test_duplicate_fixed_names_fail_before_ocr(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))

        with patch.object(page, 'detect_fleet') as detect:
            assert not page.change_fleet(None, ['A', 'A'])

        detect.assert_not_called()

    def test_failed_verification_uses_two_local_retries(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        wrong = ['X', None, None, None, None, None]

        with (
            patch.object(page, 'detect_fleet', return_value=wrong),
            patch.object(page, '_full_align') as full_align,
            patch.object(page, '_local_fix') as local_fix,
            patch.object(page, '_reorder'),
            patch('autowsgr.ui.battle.fleet_change._change.time.sleep'),
        ):
            assert not page.change_fleet(None, ['A'])

        assert full_align.call_count == 1
        assert local_fix.call_count == 2


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
        assert BattlePreparationPage._normalize_ship_name(raw) == expected

    def test_name_and_candidates_form_one_slot_rule(self):
        selector = BattlePreparationPage._extract_selector(
            {
                'name': '密苏里',
                'candidates': ['衣阿华', '密苏里'],
                'ship_type': 'BB',
                'min_level': 100,
                'max_level': 110,
            },
        )

        assert selector == {
            'candidates': ['密苏里', '衣阿华'],
            'ship_type': 'bb',
            'min_level': 100,
            'max_level': 110,
        }

    def test_overlapping_priorities_use_backtracking(self):
        names = ['A', 'A', None, None, None, None]
        selectors: list[dict | None] = [
            {'candidates': ['A', 'B']},
            {'candidates': ['A']},
            None,
            None,
            None,
            None,
        ]

        assert BattlePreparationPage._assign_unique_targets(names, selectors) == [
            'B',
            'A',
            None,
            None,
            None,
            None,
        ]

    def test_same_candidate_in_two_slots_is_impossible(self):
        names = ['岛风', '岛风', None, None, None, None]
        selectors: list[dict | None] = [
            {'candidates': ['岛风']},
            {'candidates': ['岛风']},
            None,
            None,
            None,
            None,
        ]

        assert BattlePreparationPage._assign_unique_targets(names, selectors) is None

    def test_same_ship_group_names_cannot_use_two_slots(self):
        set_user_ship_name_aliases({'契卡洛夫': '85工程'})
        names = ['85工程', '契卡洛夫', None, None, None, None]

        assert BattlePreparationPage._assign_unique_targets(names, [None] * 6) is None

    def test_occupied_name_is_removed_from_slot_candidates(self):
        selected, selector = BattlePreparationPage._select_available_candidate(
            ['岛风', None, None, None, None, None],
            '岛风',
            {'candidates': ['岛风', '雪风']},
        )

        assert selected == '雪风'
        assert selector is not None
        assert selector['candidates'] == ['雪风']

    def test_replacing_same_slot_may_keep_current_name(self):
        selected, _selector = BattlePreparationPage._select_available_candidate(
            ['岛风', None, None, None, None, None],
            '岛风',
            {'candidates': ['岛风', '雪风']},
            slot_to_replace=0,
        )

        assert selected == '岛风'

    def test_existing_members_are_matched_only_once(self):
        current = ['炽热', '絮弗伦', '岛风', '黑潮', None, None]
        desired = ['岛风', '黑潮', '阳炎', '早春', '吹雪', '初夏']
        shared = ['岛风', '黑潮', '阳炎', '早春', '吹雪', '初夏']
        selectors: list[dict | None] = [
            {'candidates': ['岛风']},
            *[{'candidates': shared} for _ in range(5)],
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

    def test_find_wrong_slots(self):
        current = ['X', 'B', 'Y', None, 'E', None]
        desired = ['A', 'B', 'C', None, None, None]

        assert BattlePreparationPage._find_wrong_slots(
            current,
            desired,
            [None] * 6,
        ) == [0, 2, 4]


class TestFleetAlignment:
    def test_slot_failure_does_not_borrow_another_slot_candidates(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        current = [None] * 6
        names = ['契卡洛夫', '岛风', None, None, None, None]
        selectors: list[dict | None] = [
            {'candidates': ['契卡洛夫'], 'min_level': 100},
            {'candidates': ['岛风', '黑潮'], 'min_level': 100},
            None,
            None,
            None,
            None,
        ]

        with (
            patch.object(
                page,
                '_change_single_ship',
                side_effect=RuntimeError('未找到契卡洛夫'),
            ) as change_ship,
            pytest.raises(RuntimeError, match='契卡洛夫'),
        ):
            page._full_align(current, names, selectors)

        assert change_ship.call_count == 1
        assert change_ship.call_args.args == (0, '契卡洛夫')
        assert change_ship.call_args.kwargs['selector']['candidates'] == ['契卡洛夫']

    def test_local_fix_replaces_before_removing(self):
        page = BattlePreparationPage(_make_ctx(MagicMock(spec=AndroidController)))
        current = ['A', 'X', 'C', 'D', None, None]
        desired = ['A', 'B', 'C', None, None, None]
        actions: list[str] = []

        with (
            patch.object(
                page,
                '_replace_target',
                side_effect=lambda *_args: actions.append('replace'),
            ),
            patch.object(
                page,
                '_change_single_ship',
                side_effect=lambda *_args, **_kwargs: actions.append('remove'),
            ),
            patch('autowsgr.ui.battle.fleet_change._change.time.sleep'),
        ):
            page._local_fix(current, desired, [None] * 6)

        assert actions == ['replace', 'remove']

    def test_reorder_moves_existing_ship(self):
        ctrl = MagicMock(spec=AndroidController)
        page = BattlePreparationPage(_make_ctx(ctrl))
        current = ['B', 'A', None, None, None, None]

        with patch('autowsgr.ui.battle.fleet_change._change.time.sleep'):
            page._reorder(current, ['A', 'B', None, None, None, None])

        assert current == ['A', 'B', None, None, None, None]
        ctrl.swipe.assert_called_once()
