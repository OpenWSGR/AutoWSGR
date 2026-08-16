"""测试 autowsgr.ops.cook。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from autowsgr.ops.cook import cook


class TestCook:
    """cook 测试。"""

    @patch('autowsgr.ops.cook.CanteenPage')
    def test_cook_success(self, mock_page_cls: MagicMock) -> None:
        ctx = MagicMock()
        mock_page = mock_page_cls.return_value
        mock_page.cook.return_value = True

        with patch('autowsgr.ops.cook.goto_page') as mock_goto:
            result = cook(ctx, position=2, force_cook=True)

        mock_goto.assert_called_once()
        mock_page.cook.assert_called_once_with(2, force_cook=True)
        assert result is True

    @patch('autowsgr.ops.cook.CanteenPage')
    def test_cook_failure(self, mock_page_cls: MagicMock) -> None:
        ctx = MagicMock()
        mock_page = mock_page_cls.return_value
        mock_page.cook.return_value = False

        with patch('autowsgr.ops.cook.goto_page'):
            result = cook(ctx)

        mock_page.cook.assert_called_once_with(1, force_cook=False)
        assert result is False
