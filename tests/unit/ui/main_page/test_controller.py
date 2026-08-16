"""测试 autowsgr.ui.main_page.controller."""

from __future__ import annotations


def test_module_importable() -> None:
    """验证模块可被导入。"""
    import autowsgr.ui.main_page.controller as _mod

    assert _mod is not None
