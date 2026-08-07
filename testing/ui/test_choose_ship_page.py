"""测试选船页的舰名比较逻辑。"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np

from autowsgr.combat.fleet import ShipSelector
from autowsgr.types import ShipType
from autowsgr.ui.choose_ship_page import ChooseShipPage
from autowsgr.ui.utils.ship_list import LevelOCRRetryNeededError
from autowsgr.vision import OCRResult
from autowsgr.vision.ocr import set_ship_name_match_confidence
from autowsgr.vision.ocr_rules import set_user_ship_name_aliases


class TestShipNameMatching:
    def setup_method(self):
        set_ship_name_match_confidence(0.65)
        set_user_ship_name_aliases({})

    def teardown_method(self):
        set_ship_name_match_confidence(0.0)
        set_user_ship_name_aliases({})

    def test_exact_name_matches(self):
        assert ChooseShipPage._matches_ship_name('岛风', '岛风')

    def test_custom_name_matches_pool_name(self):
        assert ChooseShipPage._matches_ship_name('胡德·荣耀', '胡德')
        assert ChooseShipPage._matches_ship_name('巴尔的摩·英魂', '巴尔的摩')

    def test_custom_name_rejected_above_confidence(self):
        set_ship_name_match_confidence(0.81)
        assert not ChooseShipPage._matches_ship_name('巴尔的摩·英魂', '巴尔的摩')

    def test_bidirectional_prefix_ambiguity_is_rejected(self):
        assert not ChooseShipPage._matches_ship_name('安东尼奥', '安东尼')

    def test_user_alias_is_used_for_search_and_matching(self):
        set_user_ship_name_aliases({'契卡洛夫': '85工程'})

        assert ChooseShipPage._normalize_search_keyword('契卡洛夫') == '契卡洛夫'
        assert ChooseShipPage._matches_ship_name('契卡洛夫', '85工程')
        assert ChooseShipPage._matches_ship_name('85工程', '契卡洛夫')


class TestShipTypeProbeRoutes:
    @staticmethod
    def _build_page() -> tuple[ChooseShipPage, MagicMock]:
        ocr = MagicMock()
        ctx = SimpleNamespace(ctrl=MagicMock(), ocr=ocr)
        return ChooseShipPage(ctx), ocr

    def test_legacy_entry_keeps_original_probe(self):
        page, ocr = self._build_page()
        ocr.recognize.return_value = [OCRResult(text='航母', confidence=0.99)]
        screen = np.zeros((720, 1280, 3), dtype=np.uint8)

        ship_type = page._detect_ship_type_near_hit(
            screen,
            cx=403 / 1280,
            cy=650 / 720,
            row_key=648 / 720,
        )

        assert ship_type is ShipType.CV
        assert ocr.recognize.call_count == 1
        assert ocr.recognize.call_args.args[0].shape == (108, 220, 3)

    def test_uses_single_card_roi_at_720p(self):
        page, ocr = self._build_page()
        ocr.recognize.return_value = [OCRResult(text='航母', confidence=0.99)]
        screen = np.zeros((720, 1280, 3), dtype=np.uint8)

        ship_type = page._detect_ship_type_in_single_card(
            screen,
            cx=403 / 1280,
            cy=650 / 720,
            row_key=648 / 720,
        )

        assert ship_type is ShipType.CV
        assert ocr.recognize.call_count == 1
        assert ocr.recognize.call_args.args[0].shape == (96, 272, 3)

    def test_scales_single_card_roi_with_screen_resolution(self):
        page, ocr = self._build_page()
        ocr.recognize.return_value = [OCRResult(text='轻母', confidence=0.99)]
        screen = np.zeros((1080, 1920, 3), dtype=np.uint8)

        ship_type = page._detect_ship_type_in_single_card(
            screen,
            cx=403 / 1280,
            cy=650 / 720,
            row_key=648 / 720,
        )

        assert ship_type is ShipType.CVL
        assert ocr.recognize.call_args.args[0].shape == (144, 408, 3)

    def test_retries_by_upscaling_the_same_card_roi(self):
        page, ocr = self._build_page()
        ocr.recognize.side_effect = [
            [],
            [OCRResult(text='轻母', confidence=0.99)],
        ]
        screen = np.zeros((720, 1280, 3), dtype=np.uint8)

        ship_type = page._detect_ship_type_in_single_card(
            screen,
            cx=403 / 1280,
            cy=650 / 720,
            row_key=648 / 720,
        )

        assert ship_type is ShipType.CVL
        assert ocr.recognize.call_count == 2
        first_image = ocr.recognize.call_args_list[0].args[0]
        retry_image = ocr.recognize.call_args_list[1].args[0]
        assert first_image.shape == (96, 272, 3)
        assert retry_image.shape == (144, 408, 3)

    def test_rejects_multiple_ship_types_without_guessing(self):
        page, ocr = self._build_page()
        ocr.recognize.return_value = [
            OCRResult(text='航母', confidence=0.99),
            OCRResult(text='轻母', confidence=0.99),
        ]
        screen = np.zeros((720, 1280, 3), dtype=np.uint8)

        ship_type = page._detect_ship_type_in_single_card(
            screen,
            cx=403 / 1280,
            cy=650 / 720,
            row_key=648 / 720,
        )

        assert ship_type is None
        assert ocr.recognize.call_count == 1

    def test_ignores_faction_parens_in_ship_type_text(self):
        page, ocr = self._build_page()
        ocr.recognize.return_value = [OCRResult(text='轻巡(J国)', confidence=0.99)]
        screen = np.zeros((720, 1280, 3), dtype=np.uint8)

        ship_type = page._detect_ship_type_in_single_card(
            screen,
            cx=403 / 1280,
            cy=650 / 720,
            row_key=648 / 720,
        )

        assert ship_type is ShipType.CL

    def test_extract_ship_type_strips_faction_parens(self):
        assert ChooseShipPage._extract_ship_type_from_text('轻巡(J国)') is ShipType.CL
        assert ChooseShipPage._extract_ship_type_from_text('(E国)战列') is ShipType.BB
        assert ChooseShipPage._extract_ship_type_from_text('潜艇 G国') is ShipType.SS
        assert ChooseShipPage._extract_ship_type_from_text('(J国)') is None


class TestIndependentShipRules:
    def test_single_rule_uses_its_own_constraints(self):
        ctx = SimpleNamespace(ctrl=MagicMock(), ocr=object())
        page = ChooseShipPage(ctx)
        selector = ShipSelector(
            name='U-47',
            search_name='U47',
            ship_types=(ShipType.SS, ShipType.SSG),
            min_level=100,
            max_level=110,
        )

        with (
            patch.object(page, 'ensure_search_box'),
            patch.object(page, 'ensure_dismiss_keyboard'),
            patch.object(page, 'input_ship_name') as input_name,
            patch.object(
                page,
                '_click_ship_in_list',
                return_value='U-47',
            ) as click_ship,
            patch.object(page, '_wait_leave_current_page'),
        ):
            assert page.change_single_ship(selector) == 'U-47'

        input_name.assert_called_once_with('U47')
        click_ship.assert_called_once_with(
            'U-47',
            ship_type=(ShipType.SS, ShipType.SSG),
            min_level=100,
            max_level=110,
            relaxed_constraints=False,
        )

    def test_multiple_ship_types_are_supported(self):
        expected = (ShipType.SS, ShipType.SSG)
        assert ChooseShipPage._is_ship_type_in_rule(ShipType.SS, expected)
        assert ChooseShipPage._is_ship_type_in_rule(ShipType.SSG, expected)
        assert not ChooseShipPage._is_ship_type_in_rule(ShipType.BB, expected)

    def test_primary_rejects_failed_level_constraint(self):
        ctx = SimpleNamespace(ctrl=MagicMock(), ocr=object())
        page = ChooseShipPage(ctx)

        with (
            patch('autowsgr.ui.choose_ship_page._OCR_MAX_ATTEMPTS', 1),
            patch(
                'autowsgr.ui.choose_ship_page.locate_ship_rows',
                return_value=[('U-47', 0.2, 0.3, 0.4)],
            ),
            patch(
                'autowsgr.ui.choose_ship_page.read_ship_levels',
                return_value=[('U-47', 90, 0.4)],
            ),
        ):
            matched = page._click_ship_in_list(
                'U-47',
                min_level=100,
            )

        assert matched is None
        ctx.ctrl.click.assert_not_called()

    def test_same_name_cards_pair_levels_by_card_position(self):
        ctx = SimpleNamespace(ctrl=MagicMock(), ocr=object())
        page = ChooseShipPage(ctx)

        with (
            patch(
                'autowsgr.ui.choose_ship_page.locate_ship_rows',
                return_value=[
                    ('昆西', 0.4, 0.3, 0.4),
                    ('昆西', 0.2, 0.3, 0.4),
                ],
            ),
            patch(
                'autowsgr.ui.choose_ship_page.read_ship_levels',
                return_value=[
                    ('昆西', 110, 0.2, 0.4),
                    ('昆西', 1, 0.4, 0.4),
                ],
            ),
            patch('autowsgr.ui.choose_ship_page.time.sleep'),
        ):
            matched = page._click_ship_in_list(
                '昆西',
                min_level=100,
            )

        assert matched == '昆西'
        ctx.ctrl.click.assert_called_once_with(0.2, 0.3)

    def test_relaxed_candidate_accepts_failed_level_constraint(self):
        ctx = SimpleNamespace(ctrl=MagicMock(), ocr=object())
        page = ChooseShipPage(ctx)

        with (
            patch(
                'autowsgr.ui.choose_ship_page.locate_ship_rows',
                return_value=[('U-96', 0.2, 0.3, 0.4)],
            ),
            patch(
                'autowsgr.ui.choose_ship_page.read_ship_levels',
                return_value=[('U-96', 90, 0.4)],
            ),
            patch('autowsgr.ui.choose_ship_page.time.sleep'),
        ):
            matched = page._click_ship_in_list(
                'U-96',
                min_level=100,
                relaxed_constraints=True,
            )

        assert matched == 'U-96'
        ctx.ctrl.click.assert_called_once_with(0.2, 0.3)

    def test_relaxed_candidate_accepts_failed_ship_type_constraint(self):
        ctx = SimpleNamespace(ctrl=MagicMock(), ocr=object())
        page = ChooseShipPage(ctx)

        with (
            patch(
                'autowsgr.ui.choose_ship_page.locate_ship_rows',
                return_value=[('U-96', 0.2, 0.3)],
            ),
            patch.object(
                page,
                '_detect_ship_type_near_hit',
                return_value=ShipType.BB,
            ) as detect_ship_type,
            patch('autowsgr.ui.choose_ship_page.time.sleep'),
        ):
            matched = page._click_ship_in_list(
                'U-96',
                ship_type=(ShipType.SS,),
                relaxed_constraints=True,
            )

        assert matched == 'U-96'
        detect_ship_type.assert_called_once()
        ctx.ctrl.click.assert_called_once_with(0.2, 0.3)

    def test_relaxed_candidate_accepts_level_ocr_error(self):
        ctx = SimpleNamespace(ctrl=MagicMock(), ocr=object())
        page = ChooseShipPage(ctx)

        with (
            patch(
                'autowsgr.ui.choose_ship_page.locate_ship_rows',
                return_value=[('U-96', 0.2, 0.3, 0.4)],
            ),
            patch(
                'autowsgr.ui.choose_ship_page.read_ship_levels',
                side_effect=LevelOCRRetryNeededError,
            ) as read_levels,
            patch('autowsgr.ui.choose_ship_page.time.sleep'),
        ):
            matched = page._click_ship_in_list(
                'U-96',
                min_level=100,
                relaxed_constraints=True,
            )

        assert matched == 'U-96'
        read_levels.assert_called_once()
        ctx.ctrl.click.assert_called_once_with(0.2, 0.3)

    def test_relaxed_candidate_still_rejects_wrong_name(self):
        ctx = SimpleNamespace(ctrl=MagicMock(), ocr=object())
        page = ChooseShipPage(ctx)

        with (
            patch('autowsgr.ui.choose_ship_page._OCR_MAX_ATTEMPTS', 1),
            patch(
                'autowsgr.ui.choose_ship_page.locate_ship_rows',
                return_value=[('U-47', 0.2, 0.3)],
            ),
        ):
            matched = page._click_ship_in_list(
                'U-96',
                relaxed_constraints=True,
            )

        assert matched is None
        ctx.ctrl.click.assert_not_called()
