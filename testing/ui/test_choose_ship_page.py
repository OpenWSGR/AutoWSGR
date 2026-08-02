"""测试选船页的舰名比较逻辑。"""

from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from autowsgr.ui.choose_ship_page import ChooseShipPage
from autowsgr.ui.utils.ship_list import LevelOCRRetryNeededError
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


class TestIndependentShipRules:
    def test_each_option_uses_its_own_constraints(self):
        ctx = SimpleNamespace(ctrl=MagicMock(), ocr=object())
        page = ChooseShipPage(ctx)
        selector = {
            'options': [
                {
                    'name': 'U-47',
                    'search_name': 'U47',
                    'ship_type': ['ss', 'ssg'],
                    'min_level': 100,
                    'max_level': 110,
                },
                {
                    'name': 'U-96',
                    'search_name': 'U96',
                    'ship_type': ['ss'],
                    'min_level': 90,
                    'max_level': 105,
                    'relaxed_constraints': True,
                },
            ],
        }

        with (
            patch.object(page, 'ensure_search_box'),
            patch.object(page, 'ensure_dismiss_keyboard'),
            patch.object(page, 'input_ship_name') as input_name,
            patch.object(
                page,
                '_click_ship_in_list',
                side_effect=[None, 'U-96'],
            ) as click_ship,
            patch.object(page, '_wait_leave_current_page'),
        ):
            assert page.change_single_ship('U-47', selector=selector) == 'U-96'

        assert input_name.call_args_list == [call('U47'), call('U96')]
        assert click_ship.call_args_list == [
            call(
                'U-47',
                ship_type=['ss', 'ssg'],
                min_level=100,
                max_level=110,
                relaxed_constraints=False,
            ),
            call(
                'U-96',
                ship_type=['ss'],
                min_level=90,
                max_level=105,
                relaxed_constraints=True,
            ),
        ]

    def test_multiple_ship_types_are_supported(self):
        assert ChooseShipPage._is_ship_type_in_rule('ss', ['ss', 'ssg'])
        assert ChooseShipPage._is_ship_type_in_rule('ssg', ['ss_or_ssg'])
        assert not ChooseShipPage._is_ship_type_in_rule('bb', ['ss', 'ssg'])

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
                return_value='bb',
            ) as detect_ship_type,
            patch('autowsgr.ui.choose_ship_page.time.sleep'),
        ):
            matched = page._click_ship_in_list(
                'U-96',
                ship_type=['ss'],
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
