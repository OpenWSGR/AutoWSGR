"""测试 autowsgr.scheduler.launcher。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autowsgr.scheduler.launcher import Launcher


def test_launcher_init_with_path() -> None:
    """构造时应正确存储配置路径。"""
    launcher = Launcher(config_path='settings.yaml')
    assert launcher._config_path == Path('settings.yaml')


def test_launcher_init_without_path() -> None:
    """未传入路径时 _config_path 应为 None。"""
    launcher = Launcher()
    assert launcher._config_path is None


def test_config_not_loaded_raises() -> None:
    """未加载配置时访问 config 应抛出 RuntimeError。"""
    launcher = Launcher()
    with pytest.raises(RuntimeError, match='配置未加载'):
        _ = launcher.config


def test_set_config() -> None:
    """set_config 应允许手动注入配置。"""
    launcher = Launcher()
    cfg = MagicMock()
    launcher.set_config(cfg)
    assert launcher.config is cfg


def test_load_config_patches() -> None:
    """load_config 应调用 ConfigManager.load 并初始化日志。"""
    launcher = Launcher(config_path='dummy.yaml')
    cfg = MagicMock()
    cfg.log.dir = Path('/tmp/log')
    cfg.log.level = 'INFO'
    cfg.log.effective_channels = None

    with (
        patch(
            'autowsgr.scheduler.launcher.ConfigManager.load',
            return_value=cfg,
        ),
        patch('autowsgr.scheduler.launcher.setup_logger') as mock_setup,
    ):
        result = launcher.load_config()
        assert result is cfg
        mock_setup.assert_called_once_with(
            Path('/tmp/log'),
            'INFO',
            save_images=False,
            channels=None,
        )


def test_ctrl_not_connected_raises() -> None:
    """未连接设备时访问 ctrl 应抛出 RuntimeError。"""
    launcher = Launcher()
    with pytest.raises(RuntimeError, match='设备未连接'):
        _ = launcher.ctrl


def test_build_context_creates_game_context() -> None:
    """build_context 应构造 GameContext 并注入依赖。"""
    launcher = Launcher()
    cfg = MagicMock()
    ctrl = MagicMock()
    ocr = MagicMock()
    launcher.set_config(cfg)
    launcher._ctrl = ctrl
    launcher._ocr = ocr

    ctx = launcher.build_context()
    assert ctx.ctrl is ctrl
    assert ctx.config is cfg
    assert ctx.ocr is ocr


def test_launch_sequence() -> None:
    """launch 应按正确顺序调用各步骤。"""
    launcher = Launcher(config_path='dummy.yaml')
    with (
        patch.object(launcher, 'load_config') as mock_load,
        patch.object(launcher, 'connect') as mock_connect,
        patch.object(launcher, 'build_context') as mock_build,
        patch.object(launcher, 'ensure_ready'),
    ):
        mock_build.return_value = MagicMock()
        launcher.launch(ensure_game=True)
        mock_load.assert_called_once()
        mock_connect.assert_called_once()
        mock_build.assert_called_once()
