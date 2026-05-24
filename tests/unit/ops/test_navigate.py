"""测试 autowsgr.ops.navigate。"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from autowsgr.ops.navigate import _goto_page, goto_page, identify_current_page
from autowsgr.ui.utils import NavigationError


if TYPE_CHECKING:
    from collections.abc import Iterator


class TestIdentifyCurrentPage:
    """identify_current_page 测试。"""

    def test_first_attempt_success(self) -> None:
        ctx = MagicMock()
        with patch(
            'autowsgr.ops.navigate.get_current_page',
            return_value='main_page',
        ):
            assert identify_current_page(ctx) == 'main_page'

    def test_retry_then_success(self) -> None:
        ctx = MagicMock()
        with (
            patch(
                'autowsgr.ops.navigate.get_current_page',
                side_effect=[None, None, 'main_page'],
            ),
            patch('autowsgr.ops.navigate.time.sleep') as mock_sleep,
        ):
            assert identify_current_page(ctx) == 'main_page'
            assert mock_sleep.call_count == 2

    def test_all_attempts_fail(self) -> None:
        ctx = MagicMock()
        with (
            patch(
                'autowsgr.ops.navigate.get_current_page',
                return_value=None,
            ),
            patch('autowsgr.ops.navigate.time.sleep'),
        ):
            assert identify_current_page(ctx) is None


class TestGotoPage:
    """_goto_page 导航逻辑测试。"""

    @pytest.fixture(autouse=True)
    def _mock_save_image(self) -> Iterator[None]:
        with patch('autowsgr.infra.logger.save_image'):
            yield

    def test_already_at_target(self) -> None:
        ctx = MagicMock()
        with (
            patch(
                'autowsgr.ops.navigate.identify_current_page',
                return_value='main_page',
            ),
            patch('autowsgr.ops.navigate.find_path') as mock_find,
        ):
            _goto_page(ctx, 'main_page')
            mock_find.assert_not_called()

    def test_normal_navigation(self) -> None:
        ctx = MagicMock()
        edge = MagicMock()
        edge.source = 'main_page'
        edge.target = 'map_page'
        edge.description = 'go_to_sortie'
        edge.action = MagicMock()

        with (
            patch(
                'autowsgr.ops.navigate.identify_current_page',
                side_effect=['main_page', 'map_page'],
            ),
            patch(
                'autowsgr.ops.navigate.find_path',
                return_value=[edge],
            ),
        ):
            _goto_page(ctx, 'map_page')
            edge.action.assert_called_once_with(ctx)

    def test_path_not_found(self) -> None:
        ctx = MagicMock()
        with (
            patch(
                'autowsgr.ops.navigate.identify_current_page',
                return_value='main_page',
            ),
            patch(
                'autowsgr.ops.navigate.find_path',
                return_value=None,
            ),
            pytest.raises(NavigationError, match='无法找到'),
        ):
            _goto_page(ctx, 'unknown_page')

    def test_step_limit_exceeded(self) -> None:
        ctx = MagicMock()
        edge = MagicMock()
        edge.action = MagicMock()

        # 每次 identify 都返回同一个页面，edge.action 不改变页面
        with (
            patch(
                'autowsgr.ops.navigate.identify_current_page',
                return_value='main_page',
            ),
            patch(
                'autowsgr.ops.navigate.find_path',
                return_value=[edge],
            ),
            pytest.raises(NavigationError, match='步数超限'),
        ):
            _goto_page(ctx, 'map_page')

    def test_cannot_identify_page(self) -> None:
        ctx = MagicMock()
        with (
            patch(
                'autowsgr.ops.navigate.identify_current_page',
                return_value=None,
            ),
            pytest.raises(NavigationError, match='无法识别'),
        ):
            _goto_page(ctx, 'map_page')


class TestGotoPageWrapper:
    """goto_page 包装器重试测试。"""

    def test_success_no_retry(self) -> None:
        ctx = MagicMock()
        with patch(
            'autowsgr.ops.navigate._goto_page',
        ) as mock_goto:
            goto_page(ctx, 'main_page')
            mock_goto.assert_called_once_with(ctx, 'main_page')

    def test_retry_on_navigation_error(self) -> None:
        ctx = MagicMock()
        with (
            patch(
                'autowsgr.ops.navigate._goto_page',
                side_effect=[NavigationError('fail'), None],
            ) as mock_goto,
            patch(
                'autowsgr.ops.navigate.identify_current_page',
                return_value='main_page',
            ),
        ):
            goto_page(ctx, 'map_page')
            assert mock_goto.call_count == 2

    def test_retry_raises_again(self) -> None:
        ctx = MagicMock()
        with (
            patch(
                'autowsgr.ops.navigate._goto_page',
                side_effect=NavigationError('fail'),
            ),
            patch(
                'autowsgr.ops.navigate.identify_current_page',
                return_value='main_page',
            ),
            pytest.raises(NavigationError),
        ):
            goto_page(ctx, 'map_page')
