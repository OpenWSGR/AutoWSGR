"""Launcher OCR 路由单元测试（无设备）。"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from autowsgr.scheduler.launcher import Launcher
from autowsgr.types import GameAPP


def _launcher_with_enhanced_ship_ocr(enabled: bool) -> Launcher:
    launcher = Launcher()
    launcher.set_config(
        SimpleNamespace(
            ocr=SimpleNamespace(enhanced_ship_ocr=enabled),
        ),
    )
    return launcher


def test_create_ship_ocr_disabled_uses_default_easyocr():
    launcher = _launcher_with_enhanced_ship_ocr(False)

    with patch('autowsgr.scheduler.launcher.OCREngine.create') as create:
        assert launcher.create_ship_ocr() is None

    create.assert_not_called()


def test_create_ship_ocr_enabled_uses_fastocr():
    launcher = _launcher_with_enhanced_ship_ocr(True)
    fastocr = MagicMock()

    with patch(
        'autowsgr.scheduler.launcher.OCREngine.create',
        return_value=fastocr,
    ) as create:
        assert launcher.create_ship_ocr() is fastocr

    create.assert_called_once_with(engine='fastocr', gpu=False)


def test_connect_passes_configured_game_package_for_display_detection():
    """连接时即传入所选渠道服包名，避免在独立显示屏布局下默认抓取桌面。"""
    emulator = SimpleNamespace(serial='test-device')
    config = SimpleNamespace(
        emulator=emulator,
        account=SimpleNamespace(game_app=GameAPP.official),
    )
    launcher = Launcher()
    launcher.set_config(config)
    with patch('autowsgr.scheduler.launcher.ScrcpyController') as controller:
        assert launcher.connect() is controller.return_value

    controller.assert_called_once_with(
        serial='test-device',
        config=emulator,
        package_name=GameAPP.official.package_name,
    )
    controller.return_value.connect.assert_called_once_with()


def test_launch_disconnects_when_ocr_initialization_fails():
    """OCR 构建失败时不留下已经连接的 scrcpy 视频和控制通道。"""
    launcher = Launcher()
    controller = MagicMock()
    failure = RuntimeError('OCR initialization failed')
    with (
        patch.object(launcher, 'load_config'),
        patch.object(launcher, 'connect', return_value=controller),
        patch.object(launcher, 'create_ocr', side_effect=failure),
        pytest.raises(RuntimeError) as raised,
    ):
        launcher.launch()

    assert raised.value is failure
    controller.disconnect.assert_called_once_with()


@pytest.mark.parametrize('cleanup_fails', [False, True])
def test_launch_disconnects_when_game_readiness_fails(*, cleanup_fails: bool):
    """登录超时时关闭连接；即使清理再失败，调用者仍收到原来的启动故障。"""
    launcher = Launcher()
    controller = MagicMock()
    if cleanup_fails:
        controller.disconnect.side_effect = OSError('disconnect failed')
    ctx = MagicMock()
    failure = TimeoutError('Game readiness timed out')
    with (
        patch.object(launcher, 'load_config'),
        patch.object(launcher, 'connect', return_value=controller),
        patch.object(launcher, 'build_context', return_value=ctx),
        patch.object(launcher, 'ensure_ready', side_effect=failure),
        pytest.raises(TimeoutError) as raised,
    ):
        launcher.launch()

    assert raised.value is failure
    controller.disconnect.assert_called_once_with()
