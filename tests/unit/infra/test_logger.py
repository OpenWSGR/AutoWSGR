"""测试 autowsgr.infra.logger。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

from autowsgr.infra.logger import (
    _make_channel_filter,
    _resolve_channel_level,
    caller_info,
    get_logger,
    save_image,
    setup_logger,
)


def test_get_logger_returns_bound_logger() -> None:
    """get_logger 应返回绑定了 ch 的 logger。"""
    log = get_logger('test.channel')
    assert log is not None


def _helper_for_caller_info() -> str:
    """辅助函数，用于验证 caller_info 能正确追踪调用者。"""
    return caller_info()


def test_caller_info_returns_string() -> None:
    """caller_info 应返回包含文件名与函数名的字符串。"""
    info = _helper_for_caller_info()
    assert isinstance(info, str)
    assert 'test_logger.py' in info
    assert 'test_caller_info_returns_string' in info


def test_resolve_channel_level_empty() -> None:
    """无配置时应返回默认 None。"""
    assert _resolve_channel_level('combat') is None


def test_resolve_channel_level_exact() -> None:
    """精确匹配应返回对应级别。"""
    with patch('autowsgr.infra.logger._channel_levels', {'combat': 20}):
        assert _resolve_channel_level('combat') == 20


def test_resolve_channel_level_prefix() -> None:
    """前缀匹配应返回最长前缀对应的级别。"""
    with patch(
        'autowsgr.infra.logger._channel_levels',
        {'vision': 10, 'vision.ocr': 30},
    ):
        assert _resolve_channel_level('vision.ocr') == 30
        assert _resolve_channel_level('vision.pixel') == 10


def test_make_channel_filter_level() -> None:
    """filter 应阻止低于 sink 级别的消息。"""
    f = _make_channel_filter(20)
    record = {'level': MagicMock(no=10), 'extra': {}}
    assert f(record) is False
    record['level'].no = 20
    assert f(record) is True


def test_make_channel_filter_channel() -> None:
    """filter 应阻止低于通道级别的消息。"""
    with patch(
        'autowsgr.infra.logger._channel_levels',
        {'combat': 30},
    ):
        f = _make_channel_filter(10)
        record = {'level': MagicMock(no=20), 'extra': {'ch': 'combat'}}
        assert f(record) is False
        record['level'].no = 30
        assert f(record) is True


def test_setup_logger_no_crash() -> None:
    """setup_logger 应能正常完成初始化。"""
    setup_logger(log_dir=None, level='INFO')
    # loguru 全局状态已变更，后续测试仍可正常工作


def test_save_image_with_mock_cv2() -> None:
    """save_image 应在 cv2 成功编码时返回路径。"""
    img = np.zeros((10, 10, 3), dtype=np.uint8)
    target = Path('/tmp/test_images')
    mock_buf = MagicMock()
    mock_buf.tobytes.return_value = b'PNG'
    with (
        patch(
            'autowsgr.infra.logger.cv2.cvtColor',
            return_value=img,
        ),
        patch('autowsgr.infra.logger.cv2.imencode', return_value=(True, mock_buf)),
    ):
        path = save_image(img, tag='test', img_dir=target)
        assert path is not None
        assert path.name.startswith('test_')
        assert path.suffix == '.png'
