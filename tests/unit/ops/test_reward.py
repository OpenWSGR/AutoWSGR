"""测试 autowsgr.ops.reward。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from autowsgr.ops.reward import collect_rewards
from autowsgr.types import PageName


class TestCollectRewards:
    """collect_rewards 测试。"""

    @patch('autowsgr.ops.reward.MainPage')
    @patch('autowsgr.ops.reward.MissionPage')
    def test_no_rewards(
        self,
        mock_mission_cls: MagicMock,
        mock_main_cls: MagicMock,
    ) -> None:
        ctx = MagicMock()
        mock_main_cls.has_task_ready.return_value = False

        with patch('autowsgr.ops.reward.goto_page') as mock_goto:
            result = collect_rewards(ctx)

        assert result is False
        mock_goto.assert_called_once_with(ctx, PageName.MAIN)
        mock_mission_cls.assert_not_called()

    @patch('autowsgr.ops.reward.MainPage')
    @patch('autowsgr.ops.reward.MissionPage')
    def test_collect_success(
        self,
        mock_mission_cls: MagicMock,
        mock_main_cls: MagicMock,
    ) -> None:
        ctx = MagicMock()
        mock_main_cls.has_task_ready.return_value = True
        mock_mission = mock_mission_cls.return_value
        mock_mission.collect_rewards.return_value = True

        with patch('autowsgr.ops.reward.goto_page') as mock_goto:
            result = collect_rewards(ctx)

        assert mock_goto.call_count == 3
        mock_goto.assert_any_call(ctx, PageName.MAIN)
        mock_goto.assert_any_call(ctx, PageName.MISSION)
        assert result is True
        mock_mission.collect_rewards.assert_called_once()

    @patch('autowsgr.ops.reward.MainPage')
    @patch('autowsgr.ops.reward.MissionPage')
    def test_collect_failure(
        self,
        mock_mission_cls: MagicMock,
        mock_main_cls: MagicMock,
    ) -> None:
        ctx = MagicMock()
        mock_main_cls.has_task_ready.return_value = True
        mock_mission = mock_mission_cls.return_value
        mock_mission.collect_rewards.return_value = False

        with patch('autowsgr.ops.reward.goto_page'):
            result = collect_rewards(ctx)

        assert result is False
