"""测试 autowsgr.ui.event.event_page."""

from __future__ import annotations


def test_module_importable() -> None:
    """验证模块可被导入。"""
    import autowsgr.ui.event.event_page as _mod

    assert _mod is not None
