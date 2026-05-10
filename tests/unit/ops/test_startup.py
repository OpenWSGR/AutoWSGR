"""测试 autowsgr.ops.startup。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from autowsgr.ops.startup import (
    ensure_game_ready,
    go_main_page,
    is_game_running,
    is_on_main_page,
    recover_to_main_or_restart,
    restart_game,
    start_game,
    wait_for_game_ui,
)
from autowsgr.types import PageName
from autowsgr.ui.utils import NavigationError


class TestIsGameRunning:
    """is_game_running 测试。"""

    def test_running(self) -> None:
        ctrl = MagicMock()
        ctrl.is_app_running.return_value = True
        assert is_game_running(ctrl) is True

    def test_not_running(self) -> None:
        ctrl = MagicMock()
        ctrl.is_app_running.return_value = False
        assert is_game_running(ctrl) is False


class TestIsOnMainPage:
    """is_on_main_page 测试。"""

    @patch('autowsgr.ops.startup.MainPage')
    def test_on_main_page(self, mock_main_cls: MagicMock) -> None:
        ctrl = MagicMock()
        mock_main_cls.is_current_page.return_value = True
        assert is_on_main_page(ctrl) is True

    @patch('autowsgr.ops.startup.MainPage')
    def test_not_on_main_page(self, mock_main_cls: MagicMock) -> None:
        ctrl = MagicMock()
        mock_main_cls.is_current_page.return_value = False
        assert is_on_main_page(ctrl) is False


class TestWaitForGameUI:
    """wait_for_game_ui 测试。"""

    @patch('autowsgr.ops.startup.StartScreenPage')
    def test_detects_start_screen(self, mock_screen_cls: MagicMock) -> None:
        ctrl = MagicMock()
        mock_screen_cls.is_current_page.return_value = True

        with patch('time.sleep'):
            result = wait_for_game_ui(ctrl, timeout=1.0, interval=0.1)

        assert result is True

    @patch('autowsgr.ops.startup.StartScreenPage')
    def test_timeout(self, mock_screen_cls: MagicMock) -> None:
        ctrl = MagicMock()
        mock_screen_cls.is_current_page.return_value = False

        with patch('time.sleep'):
            result = wait_for_game_ui(ctrl, timeout=0.1, interval=0.1)

        assert result is False


class TestStartGame:
    """start_game 测试。"""

    @patch('autowsgr.ops.startup.wait_for_game_ui')
    @patch('autowsgr.ops.startup.StartScreenPage')
    def test_cold_start_no_start_screen(
        self,
        mock_screen_cls: MagicMock,
        mock_wait: MagicMock,
    ) -> None:
        ctrl = MagicMock()
        mock_wait.return_value = True
        mock_screen_cls.is_current_page.return_value = False

        start_game(ctrl)

        ctrl.start_app.assert_called_once()
        mock_wait.assert_called_once()

    @patch('autowsgr.ops.startup.wait_for_game_ui')
    @patch('autowsgr.ops.startup.StartScreenPage')
    def test_cold_start_with_start_screen(
        self,
        mock_screen_cls: MagicMock,
        mock_wait: MagicMock,
    ) -> None:
        ctrl = MagicMock()
        mock_wait.return_value = True
        mock_screen_cls.is_current_page.return_value = True

        start_game(ctrl)

        mock_screen_cls.return_value.click_enter.assert_called_once()

    @patch('autowsgr.ops.startup.wait_for_game_ui')
    def test_timeout_raises(self, mock_wait: MagicMock) -> None:
        ctrl = MagicMock()
        mock_wait.return_value = False

        with pytest.raises(TimeoutError, match='游戏启动超时'):
            start_game(ctrl)


class TestRestartGame:
    """restart_game 测试。"""

    @patch('autowsgr.ops.startup.start_game')
    def test_restart(self, mock_start: MagicMock) -> None:
        ctrl = MagicMock()

        with patch('time.sleep'):
            restart_game(ctrl)

        ctrl.stop_app.assert_called_once()
        mock_start.assert_called_once_with(ctrl, 'com.huanmeng.zhanjian2', startup_timeout=120.0)


class TestGoMainPage:
    """go_main_page 测试。"""

    @patch('autowsgr.ops.startup.goto_page')
    def test_navigates(self, mock_goto: MagicMock) -> None:
        ctx = MagicMock()
        go_main_page(ctx)
        mock_goto.assert_called_once_with(ctx, PageName.MAIN)


class TestRecoverToMainOrRestart:
    """recover_to_main_or_restart 测试。"""

    @patch('autowsgr.ops.navigate.identify_current_page')
    @patch('autowsgr.ops.startup.restart_game')
    def test_page_identified_early_return(
        self,
        mock_restart: MagicMock,
        mock_identify: MagicMock,
    ) -> None:
        ctx = MagicMock()
        mock_identify.return_value = 'main_page'

        with patch('time.sleep'):
            recover_to_main_or_restart(ctx)

        mock_identify.assert_called_once_with(ctx)
        mock_restart.assert_not_called()

    @patch('autowsgr.ops.navigate.identify_current_page')
    @patch('autowsgr.ops.startup.goto_page')
    @patch('autowsgr.ops.startup.restart_game')
    def test_recover_success(
        self,
        mock_restart: MagicMock,
        mock_goto: MagicMock,
        mock_identify: MagicMock,
    ) -> None:
        ctx = MagicMock()
        mock_identify.side_effect = [None, None, 'main_page']
        mock_goto.side_effect = [None, None]

        with patch('time.sleep'):
            recover_to_main_or_restart(ctx, timeout=0.3)

        assert mock_goto.call_count >= 1
        mock_restart.assert_not_called()

    @patch('autowsgr.ops.navigate.identify_current_page')
    @patch('autowsgr.ops.startup.goto_page')
    @patch('autowsgr.ops.startup.restart_game')
    def test_recover_timeout_restarts(
        self,
        mock_restart: MagicMock,
        mock_goto: MagicMock,
        mock_identify: MagicMock,
    ) -> None:
        ctx = MagicMock()
        mock_identify.return_value = None
        mock_goto.side_effect = NavigationError('nav fail')

        with patch('time.sleep'):
            recover_to_main_or_restart(ctx, timeout=0.1)

        mock_restart.assert_called_once()
        assert mock_goto.call_count >= 1


class TestEnsureGameReady:
    """ensure_game_ready 测试。"""

    @patch('autowsgr.ops.startup.is_game_running')
    @patch('autowsgr.ops.startup.start_game')
    def test_not_running_starts(
        self,
        mock_start: MagicMock,
        mock_is_running: MagicMock,
    ) -> None:
        ctx = MagicMock()
        mock_is_running.return_value = False

        ensure_game_ready(ctx)

        mock_start.assert_called_once()

    @patch('autowsgr.ops.startup.is_game_running')
    @patch('autowsgr.ops.startup.recover_to_main_or_restart')
    def test_running_recover(
        self,
        mock_recover: MagicMock,
        mock_is_running: MagicMock,
    ) -> None:
        ctx = MagicMock()
        mock_is_running.return_value = True

        ensure_game_ready(ctx)

        mock_recover.assert_called_once()

    def test_app_str_package(self) -> None:
        ctx = MagicMock()
        with (
            patch('autowsgr.ops.startup.is_game_running', return_value=True),
            patch('autowsgr.ops.startup.recover_to_main_or_restart') as mock_recover,
        ):
            ensure_game_ready(ctx, app='com.test.package')
            mock_recover.assert_called_once()
