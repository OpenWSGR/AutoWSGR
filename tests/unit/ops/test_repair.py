"""测试 autowsgr.ops.repair。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from autowsgr.ops.repair import repair_in_bath, repair_ship_by_name
from autowsgr.types import PageName


class TestRepairInBath:
    """repair_in_bath 测试。"""

    @patch('autowsgr.ops.repair.BathPage')
    def test_repair_all(self, mock_page_cls: MagicMock) -> None:
        ctx = MagicMock()
        mock_page = mock_page_cls.return_value

        with (
            patch('autowsgr.ops.repair.goto_page') as mock_goto,
            patch('time.sleep') as mock_sleep,
        ):
            repair_in_bath(ctx)

        mock_goto.assert_any_call(ctx, PageName.BATH)
        mock_goto.assert_any_call(ctx, PageName.MAIN)
        mock_page.go_to_choose_repair.assert_called_once()
        mock_page.click_repair_all.assert_called_once()
        mock_sleep.assert_called_once_with(1.0)

    def test_recovery_to_main_raises(self) -> None:
        ctx = MagicMock()

        with (
            patch('autowsgr.ops.repair.goto_page') as mock_goto,
            patch('autowsgr.ops.repair.BathPage'),
            patch('time.sleep'),
        ):
            mock_goto.side_effect = [None, Exception('transition')]
            repair_in_bath(ctx)
            assert mock_goto.call_count == 2


class TestRepairShipByName:
    """repair_ship_by_name 测试。"""

    @patch('autowsgr.ops.repair.BathPage')
    def test_repair_success(self, mock_page_cls: MagicMock) -> None:
        ctx = MagicMock()
        mock_ship = MagicMock()
        ctx.get_ship.return_value = mock_ship
        mock_page = mock_page_cls.return_value
        mock_page.repair_ship.return_value = 1800

        with patch('autowsgr.ops.repair.goto_page'):
            result = repair_ship_by_name(ctx, '岛风')

        assert result == 1800
        mock_ship.set_repair.assert_called_once_with(1800)
        ctx.get_ship.assert_called_once_with('岛风')

    @patch('autowsgr.ops.repair.BathPage')
    def test_bath_full(self, mock_page_cls: MagicMock) -> None:
        ctx = MagicMock()
        mock_page = mock_page_cls.return_value
        mock_page.repair_ship.return_value = -1

        with patch('autowsgr.ops.repair.goto_page'):
            result = repair_ship_by_name(ctx, '岛风')

        assert result == -1
