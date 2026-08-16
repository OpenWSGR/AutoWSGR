"""测试 autowsgr.emulator.controller.scrcpy."""

from __future__ import annotations


def test_module_importable() -> None:
    """验证模块可被导入。"""
    import autowsgr.emulator.controller.scrcpy as _mod

    assert _mod is not None
