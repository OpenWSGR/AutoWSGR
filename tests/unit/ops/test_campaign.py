"""测试 autowsgr.ops.campaign。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from autowsgr.ops.campaign import CampaignRunner, parse_campaign_name
from autowsgr.types import Formation, RepairMode


class TestParseCampaignName:
    """parse_campaign_name 测试。"""

    def test_easy_destroyer(self) -> None:
        assert parse_campaign_name('简单驱逐') == (1, 'easy')

    def test_hard_carrier(self) -> None:
        assert parse_campaign_name('困难航母') == (4, 'hard')

    def test_hard_submarine(self) -> None:
        assert parse_campaign_name('困难潜艇') == (5, 'hard')

    def test_invalid_name_raises(self) -> None:
        with pytest.raises(ValueError, match='无法识别'):
            parse_campaign_name('不存在的战役')


class TestCampaignRunner:
    """CampaignRunner 初始化与解析测试。"""

    def test_init_parses_name(self) -> None:
        with patch('autowsgr.ops.campaign.CombatEngine'):
            ctx = MagicMock()
            runner = CampaignRunner(ctx, '困难战列')
            assert runner._map_index == 3
            assert runner._difficulty == 'hard'

    def test_init_defaults(self) -> None:
        with patch('autowsgr.ops.campaign.CombatEngine'):
            ctx = MagicMock()
            runner = CampaignRunner(ctx, '简单驱逐')
            assert runner._times == 3
            assert runner._formation == Formation.double_column
            assert runner._night is True
            assert runner._repair_mode == RepairMode.moderate_damage

    def test_init_custom_params(self) -> None:
        with patch('autowsgr.ops.campaign.CombatEngine'):
            ctx = MagicMock()
            runner = CampaignRunner(
                ctx,
                '困难航母',
                times=5,
                formation=Formation.single_column,
                night=False,
                repair_mode=RepairMode.severe_damage,
            )
            assert runner._times == 5
            assert runner._formation == Formation.single_column
            assert runner._night is False
            assert runner._repair_mode == RepairMode.severe_damage
