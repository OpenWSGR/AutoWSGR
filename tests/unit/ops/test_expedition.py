"""测试 autowsgr.ops.expedition。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from autowsgr.ops.expedition import collect_expedition
from autowsgr.types import PageName


class TestCollectExpedition:
    """collect_expedition 测试。"""

    @patch('autowsgr.ops.expedition.MainPage')
    def test_no_expedition(self, mock_main_cls: MagicMock) -> None:
        ctx = MagicMock()
        mock_main_cls.has_expedition_ready.return_value = False

        with (
            patch('autowsgr.ops.expedition.goto_page') as mock_goto,
            patch('autowsgr.ops.expedition.recover_to_main_or_restart') as mock_recover,
        ):
            result = collect_expedition(ctx)

        assert result is False
        mock_recover.assert_called_once()
        mock_goto.assert_called_once_with(ctx, PageName.MAIN)

    @patch('autowsgr.ops.expedition.MainPage')
    @patch('autowsgr.ops.expedition.MapPage')
    def test_has_expedition(
        self,
        mock_map_cls: MagicMock,
        mock_main_cls: MagicMock,
    ) -> None:
        ctx = MagicMock()
        mock_main_cls.has_expedition_ready.return_value = True
        mock_map = mock_map_cls.return_value
        mock_map_cls.has_expedition_notification.return_value = True
        mock_map.collect_expedition.return_value = 2

        with (
            patch('autowsgr.ops.expedition.goto_page') as mock_goto,
            patch('autowsgr.ops.expedition.recover_to_main_or_restart'),
        ):
            result = collect_expedition(ctx)

        assert result is True
        mock_goto.assert_any_call(ctx, PageName.MAIN)
        mock_goto.assert_any_call(ctx, PageName.MAP)
        mock_map.switch_panel.assert_called_once()
        mock_map.collect_expedition.assert_called_once()

    @patch('autowsgr.ops.expedition.MainPage')
    @patch('autowsgr.ops.expedition.MapPage')
    def test_notification_gone(
        self,
        mock_map_cls: MagicMock,
        mock_main_cls: MagicMock,
    ) -> None:
        ctx = MagicMock()
        mock_main_cls.has_expedition_ready.return_value = True
        mock_map_cls.has_expedition_notification.return_value = False

        with (
            patch('autowsgr.ops.expedition.goto_page') as mock_goto,
            patch('autowsgr.ops.expedition.recover_to_main_or_restart'),
        ):
            result = collect_expedition(ctx)

        assert result is False
        mock_goto.assert_any_call(ctx, PageName.MAIN)
        mock_goto.assert_any_call(ctx, PageName.MAP)
