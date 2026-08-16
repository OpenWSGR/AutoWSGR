"""Launcher OCR 路由单元测试（无设备）。"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from autowsgr.scheduler.launcher import Launcher


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
