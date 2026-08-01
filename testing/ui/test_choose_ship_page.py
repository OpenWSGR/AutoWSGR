"""测试选船页的舰名比较逻辑。"""

from autowsgr.ui.choose_ship_page import ChooseShipPage
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
