"""测试 autowsgr.image_resources._lazy。"""

from __future__ import annotations

from pathlib import Path

import pytest

from autowsgr.image_resources._lazy import IMG_ROOT, LazyTemplate, load_template
from autowsgr.vision import ImageTemplate


# ── IMG_ROOT ──


def test_img_root_is_path() -> None:
    """IMG_ROOT 应为 Path 实例。"""
    assert isinstance(IMG_ROOT, Path)


def test_img_root_exists_and_is_dir() -> None:
    """IMG_ROOT 应存在且为目录。"""
    assert IMG_ROOT.exists()
    assert IMG_ROOT.is_dir()


def test_img_root_ends_with_data_images() -> None:
    """IMG_ROOT 路径应以 data/images 结尾。"""
    parts = IMG_ROOT.parts
    assert parts[-2:] == ('data', 'images')


# ── load_template ──


def test_load_template_with_real_png() -> None:
    """使用真实 PNG 文件调用 load_template 应返回 ImageTemplate。"""
    template = load_template('common/confirm_1_540p.png')
    assert isinstance(template, ImageTemplate)
    assert template.name == 'confirm_1_540p'


def test_load_template_with_custom_name() -> None:
    """load_template 应支持显式传入 name。"""
    template = load_template('common/confirm_1_540p.png', name='custom_name')
    assert isinstance(template, ImageTemplate)
    assert template.name == 'custom_name'


def test_load_template_nonexistent_raises() -> None:
    """load_template 对不存在的路径应抛出 FileNotFoundError。"""
    with pytest.raises(FileNotFoundError):
        load_template('common/nonexistent_file_12345.png')


# ── LazyTemplate descriptor ──


class _TestTemplateContainer:
    """用于测试 LazyTemplate 描述符行为的容器类。"""

    auto_name = LazyTemplate('common/confirm_1_540p.png')
    explicit_name = LazyTemplate('common/confirm_1_540p.png', name='explicit')
    custom_resolution = LazyTemplate(
        'common/confirm_1_540p.png',
        name='hd',
        source_resolution=(1920, 1080),
    )


def test_lazy_template_first_access_returns_image_template() -> None:
    """首次访问 LazyTemplate 应返回 ImageTemplate。"""
    container = _TestTemplateContainer()
    result = container.auto_name
    assert isinstance(result, ImageTemplate)


def test_lazy_template_second_access_returns_cached_object() -> None:
    """再次访问 LazyTemplate 应返回同一缓存对象。"""
    container = _TestTemplateContainer()
    first = container.auto_name
    second = container.auto_name
    assert first is second


def test_lazy_template_set_name_auto_derives() -> None:
    """未显式指定 name 时，__set_name__ 应从属性名自动推导。"""
    container = _TestTemplateContainer()
    template = container.auto_name
    assert template.name == 'auto_name'


def test_lazy_template_explicit_name_overrides() -> None:
    """显式指定的 name 应覆盖自动推导的名称。"""
    container = _TestTemplateContainer()
    template = container.explicit_name
    assert template.name == 'explicit'


def test_lazy_template_custom_source_resolution() -> None:
    """自定义 source_resolution 应体现在返回的模板中。"""
    container = _TestTemplateContainer()
    template = container.custom_resolution
    assert template.source_resolution == (1920, 1080)


def test_lazy_template_default_source_resolution() -> None:
    """默认 source_resolution 应为 (960, 540)。"""
    container = _TestTemplateContainer()
    template = container.auto_name
    assert template.source_resolution == (960, 540)


# ── LazyTemplate.__repr__ ──


def test_lazy_template_repr_default_resolution() -> None:
    """默认分辨率时 repr 不应包含 source_resolution。"""
    descriptor = LazyTemplate('common/confirm_1_540p.png', name='btn')
    assert repr(descriptor) == "LazyTemplate('common/confirm_1_540p.png', name='btn')"


def test_lazy_template_repr_custom_resolution() -> None:
    """自定义分辨率时 repr 应包含 source_resolution。"""
    descriptor = LazyTemplate(
        'common/confirm_1_540p.png',
        name='btn_hd',
        source_resolution=(1920, 1080),
    )
    assert (
        repr(descriptor)
        == "LazyTemplate('common/confirm_1_540p.png', name='btn_hd', source_resolution=(1920, 1080))"
    )
