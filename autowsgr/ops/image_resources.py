"""图像模板资源 — 兼容垫片。

.. deprecated::
    本模块已迁移至 :mod:`autowsgr.image_resources`。
    请直接使用::

        from autowsgr.image_resources import Templates
"""

from __future__ import annotations

from autowsgr.image_resources.ops import Templates  # noqa: F401  re-export

__all__ = ["Templates"]
