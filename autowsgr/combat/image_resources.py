"""战斗系统图像模板资源 — 兼容垫片。

.. deprecated::
    本模块已迁移至 :mod:`autowsgr.image_resources`。
    请直接使用::

        from autowsgr.image_resources import CombatTemplates, TemplateKey
"""

from __future__ import annotations

import warnings

from autowsgr.image_resources import CombatTemplates, TemplateKey, get_templates

__all__ = ["CombatTemplates", "get_template"]


def get_template(key: str):
    """兼容旧 API：通过字符串键获取模板列表。

    .. deprecated::
        请改用 ``TemplateKey.XXX.templates`` 或 ``get_templates(TemplateKey.XXX)``。
    """
    warnings.warn(
        "get_template(str) 已弃用，请使用 TemplateKey 枚举",
        DeprecationWarning,
        stacklevel=2,
    )
    return get_templates(TemplateKey(key))


def resolve_image_matcher(image_checker_find_any):
    """兼容旧 API：创建 image_matcher 回调。

    .. deprecated::
        请改用 ``TemplateKey`` 直接查询模板。
    """
    warnings.warn(
        "resolve_image_matcher 已弃用，请使用 TemplateKey 枚举",
        DeprecationWarning,
        stacklevel=2,
    )

    def _match(screen, template_key, confidence: float) -> bool:
        if isinstance(template_key, str):
            templates = get_templates(TemplateKey(template_key))
        else:
            templates = template_key.templates
        return image_checker_find_any(screen, templates, confidence=confidence) is not None

    return _match


def resolve_image_exist(image_checker_find_any):
    """已弃用。"""
    raise NotImplementedError("resolve_image_exist 已移除，请使用 TemplateKey")
