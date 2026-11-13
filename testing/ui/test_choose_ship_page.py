"""测试选船页的舰名比较逻辑。"""

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from autowsgr.combat.fleet import ShipSelector
from autowsgr.emulator.frame import CapturedFrame
from autowsgr.types import ShipType
from autowsgr.ui.choose_ship_page import ChooseShipPage
from autowsgr.ui.decisive.ship_list import ShipListViewport
from autowsgr.ui.utils.ship_list import LevelOCRRetryNeededError
from autowsgr.vision import OCRResult
from autowsgr.vision.ocr import set_ship_name_match_confidence
from autowsgr.vision.ocr_rules import EasyOCRProfile, set_user_ship_name_aliases


class TestDecisiveViewportSelection:
    """选择端消费已验证视口；几何与完整性另由 walker 算法测试及独立实机验收覆盖。"""

    @staticmethod
    def _viewport(sequence: int, *hits: tuple[str, float, float, float]) -> SimpleNamespace:
        return SimpleNamespace(
            frame=CapturedFrame(
                np.zeros((720, 1280, 3), dtype=np.uint8), sequence, float(sequence)
            ),
            hits=hits,
        )

    def test_empty_viewport_returns_no_selection_without_clicking_or_leaving(self):
        """空视口是 provider 的接口输入，此处不证明空背景像素或实机识别。"""
        ctx = SimpleNamespace(ctrl=MagicMock(), ocr=object(), stop_event=threading.Event())
        page = ChooseShipPage(ctx)
        viewport = ShipListViewport(self._viewport(1).frame, (), at_top=True, at_bottom=True)
        with (
            patch('autowsgr.ui.decisive.ship_list.DecisiveShipListWalker') as walker,
            patch.object(page, '_wait_leave_current_page') as leave,
        ):
            walker.return_value.viewports.return_value = iter([viewport])
            assert page.change_single_ship(ShipSelector(name='U-96'), use_search=False) is None

        ctx.ctrl.click.assert_not_called()
        ctx.ctrl.swipe.assert_not_called()
        ctx.ctrl.screenshot.assert_not_called()
        leave.assert_not_called()

    def test_decisive_selection_uses_the_current_deep_viewport_coordinates(self):
        ctx = SimpleNamespace(ctrl=MagicMock(), ocr=object(), stop_event=threading.Event())
        page = ChooseShipPage(ctx)
        rows = [
            ('胡德', '声望', '反击', '威尔士亲王', '罗德尼', '纳尔逊', '前卫'),
            (
                '俾斯麦',
                '提尔比茨',
                '沙恩霍斯特',
                '格奈森瑙',
                '齐柏林伯爵',
                '欧根亲王',
                '舍尔海军上将',
            ),
            ('华盛顿', '北卡罗来纳', '南达科他', '马萨诸塞', '阿拉巴马', '印第安纳', '衣阿华'),
            ('新泽西', '密苏里', '威斯康星', '蒙大拿', '列克星敦', '萨拉托加', '大黄蜂'),
            ('约克城', '企业', '突击者', '埃塞克斯', '香格里拉', '无畏', '独立'),
            ('普林斯顿', '贝劳伍德', '兰利', '圣哈辛托', '卡伯特', '巴丹', 'U-96'),
        ]
        viewports = []
        for index in range(5):
            hits = [
                (
                    name,
                    (180 + column * 140) / 1280,
                    (300 + row * 280) / 720,
                    (320 + row * 280) / 720,
                )
                for row, names in enumerate(rows[index : index + 2])
                for column, name in enumerate(names)
            ]
            viewports.append(self._viewport(index + 1, *hits))
        with (
            patch('autowsgr.ui.decisive.ship_list.DecisiveShipListWalker') as walker,
            patch.object(page, '_click_ship_in_list') as ordinary,
            patch.object(page, '_wait_leave_current_page') as leave,
            patch('autowsgr.ui.choose_ship_page.time.sleep'),
        ):
            walker.return_value.viewports.return_value = iter(viewports)
            assert page.change_single_ship(ShipSelector(name='U-96'), use_search=False) == 'U-96'

        walker.assert_called_once_with(ctx, ctx.ocr)
        ordinary.assert_not_called()
        ctx.ctrl.click.assert_called_once_with(1020 / 1280, 580 / 720)
        ctx.ctrl.screenshot.assert_not_called()
        leave.assert_called_once()

    def test_decisive_selection_preserves_shared_type_constraints(self):
        ctx = SimpleNamespace(ctrl=MagicMock(), ocr=object(), stop_event=threading.Event())
        page = ChooseShipPage(ctx)
        with (
            patch('autowsgr.ui.decisive.ship_list.DecisiveShipListWalker') as walker,
            patch.object(page, '_detect_hit_ship_type', return_value=ShipType.CV),
            patch('autowsgr.ui.choose_ship_page.time.sleep'),
        ):
            walker.return_value.viewports.return_value = iter(
                [self._viewport(1, ('U-96', 0.2, 0.3, 0.4))]
            )
            assert page._click_decisive_ship_in_list('U-96', ship_type=(ShipType.SS,)) is None

        ctx.ctrl.click.assert_not_called()

    def test_decisive_selection_does_not_hide_traversal_failure(self):
        from autowsgr.ui.decisive.ship_list import DecisiveInventoryScanError

        ctx = SimpleNamespace(ctrl=MagicMock(), ocr=object(), stop_event=threading.Event())
        page = ChooseShipPage(ctx)

        def interrupted():
            yield self._viewport(1, ('U-47', 0.2, 0.3, 0.4))
            raise DecisiveInventoryScanError('unproven overlap')

        with (
            patch('autowsgr.ui.decisive.ship_list.DecisiveShipListWalker') as walker,
            patch.object(page, '_wait_leave_current_page') as leave,
            pytest.raises(DecisiveInventoryScanError, match='unproven overlap'),
        ):
            walker.return_value.viewports.return_value = interrupted()
            page.change_single_ship(ShipSelector(name='U-96'), use_search=False)

        ctx.ctrl.click.assert_not_called()
        leave.assert_not_called()

    @pytest.mark.parametrize('stop_during', ['constraints', 'delay'])
    def test_decisive_selection_stops_before_click_when_requested_during_preparation(
        self, stop_during: str
    ):
        ctx = SimpleNamespace(ctrl=MagicMock(), ocr=object(), stop_event=threading.Event())
        page = ChooseShipPage(ctx)

        def read_type(*_args) -> ShipType:
            if stop_during == 'constraints':
                ctx.stop_event.set()
            return ShipType.SS

        def delay(seconds: float) -> None:
            assert seconds == 1.0
            if stop_during == 'delay':
                ctx.stop_event.set()

        with (
            patch('autowsgr.ui.decisive.ship_list.DecisiveShipListWalker') as walker,
            patch.object(page, '_detect_hit_ship_type', side_effect=read_type),
            patch.object(page, '_wait_leave_current_page') as leave,
            patch('autowsgr.ui.choose_ship_page.time.sleep', side_effect=delay) as sleep,
        ):
            walker.return_value.viewports.return_value = iter(
                [self._viewport(1, ('U-96', 0.2, 0.3, 0.4))]
            )
            with pytest.raises(InterruptedError, match='停止'):
                page.change_single_ship(
                    ShipSelector(name='U-96', ship_types=(ShipType.SS,)), use_search=False
                )

        ctx.ctrl.click.assert_not_called()
        leave.assert_not_called()
        if stop_during == 'constraints':
            sleep.assert_not_called()
        else:
            sleep.assert_called_once_with(1.0)


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

    def test_user_alias_is_used_for_matching(self):
        set_user_ship_name_aliases({'契卡洛夫': '85工程'})

        assert ChooseShipPage._normalize_search_keyword('契卡洛夫') == '契卡洛夫'
        assert ChooseShipPage._matches_ship_name('契卡洛夫', '85工程')
        assert ChooseShipPage._matches_ship_name('85工程', '契卡洛夫')

    def test_standard_name_is_used_when_no_user_alias_exists(self):
        assert ChooseShipPage._normalize_search_keyword(' 岛风 ') == '岛风'


class TestShipTypeProbeRoutes:
    @staticmethod
    def _build_page() -> tuple[ChooseShipPage, MagicMock]:
        ocr = MagicMock()
        ctx = SimpleNamespace(ctrl=MagicMock(), ocr=ocr)
        return ChooseShipPage(ctx), ocr

    def test_default_entry_uses_single_card_roi(self):
        page, ocr = self._build_page()
        ocr.recognize_line.return_value = [OCRResult(text='航母', confidence=0.99)]
        screen = np.zeros((720, 1280, 3), dtype=np.uint8)

        ship_type = page._detect_hit_ship_type(
            screen,
            cx=403 / 1280,
            cy=650 / 720,
            row_key=648 / 720,
        )

        assert ship_type is ShipType.CV
        assert ocr.recognize_line.call_count == 1
        assert ocr.recognize_line.call_args.args[0].shape == (49, 98, 3)
        assert ocr.recognize_line.call_args.kwargs == {
            'easyocr_profile': EasyOCRProfile.SHIP_POOL_TYPE,
        }

    def test_uses_single_card_roi_at_720p(self):
        page, ocr = self._build_page()
        ocr.recognize_line.return_value = [OCRResult(text='航母', confidence=0.99)]
        screen = np.zeros((720, 1280, 3), dtype=np.uint8)

        ship_type = page._detect_ship_type_in_single_card(
            screen,
            cx=403 / 1280,
            cy=650 / 720,
            row_key=648 / 720,
        )

        assert ship_type is ShipType.CV
        assert ocr.recognize_line.call_count == 1
        assert ocr.recognize_line.call_args.args[0].shape == (49, 98, 3)

    def test_scales_single_card_roi_with_screen_resolution(self):
        page, ocr = self._build_page()
        ocr.recognize_line.return_value = [OCRResult(text='轻母', confidence=0.99)]
        screen = np.zeros((1080, 1920, 3), dtype=np.uint8)

        ship_type = page._detect_ship_type_in_single_card(
            screen,
            cx=403 / 1280,
            cy=650 / 720,
            row_key=648 / 720,
        )

        assert ship_type is ShipType.CVL
        assert ocr.recognize_line.call_args.args[0].shape == (73, 147, 3)

    def test_retries_by_upscaling_the_same_card_roi(self):
        page, ocr = self._build_page()
        ocr.recognize_line.side_effect = [
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
        assert ocr.recognize_line.call_count == 2
        first_image = ocr.recognize_line.call_args_list[0].args[0]
        retry_image = ocr.recognize_line.call_args_list[1].args[0]
        assert first_image.shape == (49, 98, 3)
        assert retry_image.shape == (74, 147, 3)

    def test_retries_ship_type_at_four_times_scale(self):
        page, ocr = self._build_page()
        ocr.recognize_line.side_effect = [
            [],
            [],
            [OCRResult(text='战巡', confidence=0.99)],
        ]
        screen = np.zeros((720, 1280, 3), dtype=np.uint8)

        ship_type = page._detect_ship_type_in_single_card(
            screen,
            cx=403 / 1280,
            cy=650 / 720,
            row_key=648 / 720,
        )

        assert ship_type is ShipType.BC
        assert ocr.recognize_line.call_count == 3
        final_image = ocr.recognize_line.call_args_list[2].args[0]
        assert final_image.shape == (98, 196, 3)

    def test_rejects_multiple_ship_types_without_guessing(self):
        page, ocr = self._build_page()
        ocr.recognize_line.return_value = [
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
        assert ocr.recognize_line.call_count == 1

    def test_ignores_faction_parens_in_ship_type_text(self):
        page, ocr = self._build_page()
        ocr.recognize_line.return_value = [OCRResult(text='轻巡(J国)', confidence=0.99)]
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
    def test_ordinary_search_keeps_three_attempts_and_original_click_delay(self):
        ctx = SimpleNamespace(ctrl=MagicMock(), ocr=object())
        page = ChooseShipPage(ctx)
        with (
            patch(
                'autowsgr.ui.choose_ship_page.locate_ship_rows',
                side_effect=[[], [], [('U-96', 0.2, 0.3, 0.4)]],
            ) as locate,
            patch('autowsgr.ui.choose_ship_page.time.sleep') as delay,
        ):
            assert page._click_ship_in_list('U-96') == 'U-96'

        assert locate.call_count == 3
        assert ctx.ctrl.screenshot.call_count == 3
        assert ctx.ctrl.swipe.call_count == 2
        assert [call.args for call in delay.call_args_list] == [(0.5,), (0.5,), (1.0,)]
        ctx.ctrl.click.assert_called_once_with(0.2, 0.3)

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
                'autowsgr.ui.choose_ship_page.read_ship_level_at_card',
                return_value=90,
            ),
        ):
            matched = page._click_ship_in_list(
                'U-47',
                min_level=100,
            )

        assert matched is None
        ctx.ctrl.click.assert_not_called()

    def test_same_name_cards_read_levels_from_each_card_position(self):
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
                'autowsgr.ui.choose_ship_page.read_ship_level_at_card',
                side_effect=[1, 110],
            ) as read_level,
            patch('autowsgr.ui.choose_ship_page.time.sleep'),
        ):
            matched = page._click_ship_in_list(
                '昆西',
                min_level=100,
            )

        assert matched == '昆西'
        ctx.ctrl.click.assert_called_once_with(0.2, 0.3)
        assert [call.kwargs['card_x'] for call in read_level.call_args_list] == [0.4, 0.2]

    def test_ship_type_filters_same_name_cards_before_level_ocr(self):
        ctx = SimpleNamespace(ctrl=MagicMock(), ocr=object())
        page = ChooseShipPage(ctx)

        with (
            patch(
                'autowsgr.ui.choose_ship_page.locate_ship_rows',
                return_value=[
                    ('密苏里', 0.2, 0.3, 0.4),
                    ('密苏里', 0.4, 0.3, 0.4),
                ],
            ) as locate_rows,
            patch.object(
                page,
                '_detect_hit_ship_type',
                side_effect=[ShipType.BB, ShipType.BG],
            ) as detect_ship_type,
            patch(
                'autowsgr.ui.choose_ship_page.read_ship_level_at_card',
                return_value=105,
            ) as read_level,
            patch('autowsgr.ui.choose_ship_page.time.sleep'),
        ):
            matched = page._click_ship_in_list(
                '密苏里',
                ship_type=(ShipType.BG,),
                min_level=100,
            )

        assert matched == '密苏里'
        locate_rows.assert_called_once_with(
            ctx.ocr,
            ctx.ctrl.screenshot.return_value,
            deduplicate_by_name=False,
            include_row_key=True,
        )
        assert detect_ship_type.call_count == 2
        read_level.assert_called_once_with(
            ctx.ocr,
            ctx.ctrl.screenshot.return_value,
            card_x=0.4,
            row_key=0.4,
        )
        ctx.ctrl.click.assert_called_once_with(0.4, 0.3)

    def test_relaxed_candidate_rejects_known_level_mismatch(self):
        ctx = SimpleNamespace(ctrl=MagicMock(), ocr=object())
        page = ChooseShipPage(ctx)

        with (
            patch('autowsgr.ui.choose_ship_page._OCR_MAX_ATTEMPTS', 1),
            patch(
                'autowsgr.ui.choose_ship_page.locate_ship_rows',
                return_value=[('U-96', 0.2, 0.3, 0.4)],
            ),
            patch(
                'autowsgr.ui.choose_ship_page.read_ship_level_at_card',
                return_value=90,
            ),
        ):
            matched = page._click_ship_in_list(
                'U-96',
                min_level=100,
                relaxed_constraints=True,
            )

        assert matched is None
        ctx.ctrl.click.assert_not_called()

    def test_relaxed_candidate_rejects_known_ship_type_mismatch(self):
        ctx = SimpleNamespace(ctrl=MagicMock(), ocr=object())
        page = ChooseShipPage(ctx)

        with (
            patch('autowsgr.ui.choose_ship_page._OCR_MAX_ATTEMPTS', 1),
            patch(
                'autowsgr.ui.choose_ship_page.locate_ship_rows',
                return_value=[('U-96', 0.2, 0.3, 0.4)],
            ),
            patch.object(
                page,
                '_detect_hit_ship_type',
                return_value=ShipType.BB,
            ) as detect_ship_type,
        ):
            matched = page._click_ship_in_list(
                'U-96',
                ship_type=(ShipType.SS,),
                relaxed_constraints=True,
            )

        assert matched is None
        detect_ship_type.assert_called_once()
        ctx.ctrl.click.assert_not_called()

    def test_relaxed_candidate_accepts_unknown_ship_type(self):
        ctx = SimpleNamespace(ctrl=MagicMock(), ocr=object())
        page = ChooseShipPage(ctx)

        with (
            patch(
                'autowsgr.ui.choose_ship_page.locate_ship_rows',
                return_value=[('U-96', 0.2, 0.3, 0.4)],
            ),
            patch.object(page, '_detect_hit_ship_type', return_value=None),
            patch('autowsgr.ui.choose_ship_page.time.sleep'),
        ):
            matched = page._click_ship_in_list(
                'U-96',
                ship_type=(ShipType.SS,),
                relaxed_constraints=True,
            )

        assert matched == 'U-96'
        ctx.ctrl.click.assert_called_once_with(0.2, 0.3)

    def test_relaxed_candidate_accepts_unknown_level(self):
        ctx = SimpleNamespace(ctrl=MagicMock(), ocr=object())
        page = ChooseShipPage(ctx)

        with (
            patch(
                'autowsgr.ui.choose_ship_page.locate_ship_rows',
                return_value=[('U-96', 0.2, 0.3, 0.4)],
            ),
            patch(
                'autowsgr.ui.choose_ship_page.read_ship_level_at_card',
                return_value=None,
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

    def test_relaxed_candidate_prefers_fully_verified_same_name_card(self):
        ctx = SimpleNamespace(ctrl=MagicMock(), ocr=object())
        page = ChooseShipPage(ctx)

        with (
            patch(
                'autowsgr.ui.choose_ship_page.locate_ship_rows',
                return_value=[
                    ('U-96', 0.2, 0.3, 0.4),
                    ('U-96', 0.4, 0.3, 0.4),
                ],
            ),
            patch.object(
                page,
                '_detect_hit_ship_type',
                side_effect=[None, ShipType.SS],
            ),
            patch('autowsgr.ui.choose_ship_page.time.sleep'),
        ):
            matched = page._click_ship_in_list(
                'U-96',
                ship_type=(ShipType.SS,),
                relaxed_constraints=True,
            )

        assert matched == 'U-96'
        ctx.ctrl.click.assert_called_once_with(0.4, 0.3)

    def test_relaxed_candidate_prefers_verified_type_when_unknown_counts_match(self):
        ctx = SimpleNamespace(ctrl=MagicMock(), ocr=object())
        page = ChooseShipPage(ctx)

        with (
            patch(
                'autowsgr.ui.choose_ship_page.locate_ship_rows',
                return_value=[
                    ('U-96', 0.2, 0.3, 0.4),
                    ('U-96', 0.4, 0.3, 0.4),
                ],
            ),
            patch.object(
                page,
                '_detect_hit_ship_type',
                side_effect=[None, ShipType.SS],
            ),
            patch(
                'autowsgr.ui.choose_ship_page.read_ship_level_at_card',
                side_effect=[105, None],
            ),
            patch('autowsgr.ui.choose_ship_page.time.sleep'),
        ):
            matched = page._click_ship_in_list(
                'U-96',
                ship_type=(ShipType.SS,),
                min_level=100,
                relaxed_constraints=True,
            )

        assert matched == 'U-96'
        ctx.ctrl.click.assert_called_once_with(0.4, 0.3)

    def test_relaxed_candidate_accepts_level_ocr_error(self):
        ctx = SimpleNamespace(ctrl=MagicMock(), ocr=object())
        page = ChooseShipPage(ctx)

        with (
            patch(
                'autowsgr.ui.choose_ship_page.locate_ship_rows',
                return_value=[('U-96', 0.2, 0.3, 0.4)],
            ),
            patch(
                'autowsgr.ui.choose_ship_page.read_ship_level_at_card',
                side_effect=LevelOCRRetryNeededError,
            ) as read_level,
            patch('autowsgr.ui.choose_ship_page.time.sleep'),
        ):
            matched = page._click_ship_in_list(
                'U-96',
                min_level=100,
                relaxed_constraints=True,
            )

        assert matched == 'U-96'
        read_level.assert_called_once()
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
