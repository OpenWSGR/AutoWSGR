"""Launcher OCR 路由单元测试（无设备）。"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from autowsgr.scheduler.launcher import Launcher


def test_launch_disconnects_controller_after_connect_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A partially connected controller is released when launch fails."""
    launcher = Launcher()
    ctrl = MagicMock()

    def fail_connect() -> None:
        launcher._ctrl = ctrl
        raise RuntimeError('connect failed')

    monkeypatch.setattr(launcher, 'load_config', lambda: None)
    monkeypatch.setattr(launcher, 'connect', fail_connect)

    with pytest.raises(RuntimeError, match='connect failed'):
        launcher.launch()

    ctrl.disconnect.assert_called_once_with()


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
    """enhanced_ship_ocr=True 时默认 OCR 已是 FastOCR, ship_ocr 返回 None。"""
    launcher = _launcher_with_enhanced_ship_ocr(True)
    assert launcher.create_ship_ocr() is None


def test_create_ocr_missing_enhanced_ship_ocr_attr_no_throw():
    """cfg.ocr 没有 enhanced_ship_ocr 属性时，向后兼容回退到 EasyOCR，不抛 AttributeError。

    这是 GUI 运行契约探针 (backendContractProbe.ts) 的核心兼容场景：
    探针构造的 SimpleNamespace 仅包含 gpu / mirror / ship_name_match_* 字段，
    故意不含 enhanced_ship_ocr，因此 ShiinaKuroko 的全局 FastOCR 开关必须用
    getattr 默认值，避免探针抛异常导致 GUI 错误地把后端判定为 "缺少
    autowsgr-runtime-contract 包" → 反复重装 → 死循环。
    """
    # 完全复刻 GUI 探针构造的字段集合：缺 enhanced_ship_ocr
    ocr_cfg = SimpleNamespace(
        gpu=False,
        mirror='modelscope',
        ship_name_match_confidence=0.0,
        ship_name_corrections={},
        ship_name_aliases={},
    )
    launcher = Launcher()
    launcher.set_config(SimpleNamespace(ocr=ocr_cfg))

    seen_gpu = []

    def _capture_easy_ocr(*args, **kwargs):
        seen_gpu.append(kwargs.get('gpu'))
        return MagicMock()

    with patch(
        'autowsgr.scheduler.launcher.EasyOCREngine.create',
        side_effect=_capture_easy_ocr,
    ) as easy_create, patch(
        'autowsgr.scheduler.launcher.OCREngine.create',
    ) as fastocr_create, patch.dict(
        'os.environ', {'AUTOWSGR_OCR_GPU_MODE': 'cuda'},
        clear=False,
    ):
        launcher.create_ocr()

    fastocr_create.assert_not_called()
    easy_create.assert_called_once()
    assert seen_gpu == [True], (
        'AUTOWSGR_OCR_GPU_MODE=cuda 应覆盖 cfg.ocr.gpu=False，'
        f'但 EasyOCREngine.create 收到 gpu={seen_gpu}'
    )

    # create_ship_ocr 也必须不抛 AttributeError
    with patch('autowsgr.scheduler.launcher.OCREngine.create'):
        assert launcher.create_ship_ocr() is None


def test_gui_runtime_contract_probe_compatible():
    """端到端复刻 GUI backendContractProbe.ts 定义的 _verify_gui_runtime_contract()。

    通过则意味着 GUI 的 envCheck 不会把 runtime_contract 标记为 False，
    也就不会出现日志里反复触发 "强制更新当前通道 autowsgr → 装伪包
    autowsgr-runtime-contract → 阿里云源断流 IncompleteRead" 的死循环。
    """
    import os

    log_cfg = SimpleNamespace(
        dir='.',
        level='INFO',
        effective_channels=[],
    )
    ocr_cfg = SimpleNamespace(
        gpu=False,
        mirror='modelscope',
        ship_name_match_confidence=0.0,
        ship_name_corrections={},
        ship_name_aliases={},
    )
    fake_config = SimpleNamespace(log=log_cfg, ocr=ocr_cfg)

    save_images_calls = []

    def _capture_setup_logger(*args, **kwargs):
        save_images_calls.append(kwargs.get('save_images'))

    ocr_gpu_calls = []

    def _capture_easy_create(*args, **kwargs):
        ocr_gpu_calls.append(kwargs.get('gpu'))
        return MagicMock()

    save_key = 'AUTOWSGR_SAVE_IMAGES'
    gpu_key = 'AUTOWSGR_OCR_GPU_MODE'
    previous_save = os.environ.get(save_key)
    previous_gpu = os.environ.get(gpu_key)
    try:
        with patch(
            'autowsgr.scheduler.launcher.ConfigManager.load',
            return_value=fake_config,
        ), patch(
            'autowsgr.scheduler.launcher.setup_logger',
            side_effect=_capture_setup_logger,
        ):
            os.environ[save_key] = 'true'
            Launcher().load_config()
            os.environ[save_key] = 'false'
            Launcher().load_config()
        assert save_images_calls == [True, False], (
            'AUTOWSGR_SAVE_IMAGES 行为不兼容 (GUI probe step 1 fail) '
            f'actual={save_images_calls}'
        )

        launcher = Launcher()
        launcher.set_config(fake_config)
        with patch(
            'autowsgr.scheduler.launcher.EasyOCREngine.create',
            side_effect=_capture_easy_create,
        ):
            os.environ[gpu_key] = 'cuda'
            launcher.create_ocr()
            os.environ[gpu_key] = 'cpu'
            launcher.create_ocr()
        assert ocr_gpu_calls == [True, False], (
            'AUTOWSGR_OCR_GPU_MODE 行为不兼容 (GUI probe step 2 fail) '
            f'actual={ocr_gpu_calls}'
        )
    finally:
        if previous_save is None:
            os.environ.pop(save_key, None)
        else:
            os.environ[save_key] = previous_save
        if previous_gpu is None:
            os.environ.pop(gpu_key, None)
        else:
            os.environ[gpu_key] = previous_gpu
