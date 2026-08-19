"""页面 / 浮层识别模板子包 — 按 UI 独立组织, 经 ``Templates`` 统一入口导出。

分类:

- :class:`CommonPage` — 通用页面 (后院 / 食堂 / 出征准备 / 侧边栏)
- :class:`MainPage` — 主页面 (基础页面 + 登录/操作浮层)
- :class:`Decisive` — 决战 (入口状态 + 地图页 + 浮层)
- :class:`Bath` — 浴室 (页面 + 选择修理浮层)
"""

from __future__ import annotations

from autowsgr.image_resources.pages.bath import Bath
from autowsgr.image_resources.pages.common import CommonPage
from autowsgr.image_resources.pages.decisive import Decisive
from autowsgr.image_resources.pages.main_page import MainPage


__all__ = ['Bath', 'CommonPage', 'Decisive', 'MainPage']
