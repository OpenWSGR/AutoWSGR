"""测试 autowsgr.ops.destroy。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from autowsgr.ops.destroy import destroy_ships
from autowsgr.types import PageName, ShipType


class TestDestroyShips:
    """destroy_ships 测试。"""

    @patch('autowsgr.ops.destroy.goto_page')
    @patch('autowsgr.ui.build_page.BuildPage')
    def test_destroy_all(
        self,
        mock_page_cls: MagicMock,
        mock_goto: MagicMock,
    ) -> None:
        ctx = MagicMock()
        mock_page = mock_page_cls.return_value

        destroy_ships(ctx)

        mock_goto.assert_any_call(ctx, PageName.BUILD)
        mock_page.switch_tab.assert_called_once()
        mock_page.destroy_ships.assert_called_once_with(None, remove_equipment=True)

    @patch('autowsgr.ops.destroy.goto_page')
    @patch('autowsgr.ui.build_page.BuildPage')
    def test_destroy_specific_types(
        self,
        mock_page_cls: MagicMock,
        mock_goto: MagicMock,
    ) -> None:
        ctx = MagicMock()
        mock_page = mock_page_cls.return_value
        ship_types = [ShipType.DD, ShipType.CL]

        destroy_ships(ctx, ship_types=ship_types, remove_equipment=False)

        mock_goto.assert_any_call(ctx, PageName.BUILD)
        mock_page.destroy_ships.assert_called_once_with(
            ship_types,
            remove_equipment=False,
        )
