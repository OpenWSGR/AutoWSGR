"""图像模板资源管理中心。

集中管理所有业务操作和战斗系统所需的图像模板，
替代原先分散在 ``combat/image_resources.py`` 和 ``ops/image_resources.py`` 中的实现。

核心组件
--------
- :class:`TemplateKey` — 枚举值标识每一组模板，替代硬编码字符串
- :class:`CombatTemplates` — 战斗系统专用模板
- :class:`Templates` — 业务操作模板（食堂、建造、确认弹窗等）
- :func:`get_templates` — 通过 ``TemplateKey`` 获取模板列表

Usage::

    from autowsgr.image_resources import TemplateKey, CombatTemplates, Templates

    # 枚举键查询模板列表
    templates = TemplateKey.FORMATION.templates

    # 直接属性访问
    tpl = CombatTemplates.FORMATION
    btn = Templates.Cook.COOK_BUTTON
"""

from __future__ import annotations

from autowsgr.image_resources._lazy import LazyTemplate
from autowsgr.image_resources.combat import CombatTemplates
from autowsgr.image_resources.keys import TemplateKey, get_templates
from autowsgr.image_resources.ops import Templates

__all__ = [
    "CombatTemplates",
    "LazyTemplate",
    "Templates",
    "TemplateKey",
    "get_templates",
]
