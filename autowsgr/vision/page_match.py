"""页面识别统一结果类型 PageMatch。

页面识别(判断当前处于哪个 UI 页面)横跨三种引擎:

- 像素签名 :class:`~autowsgr.vision.matcher.PixelChecker`(输出 matched_count/total_count → ratio)
- 模板匹配 :class:`~autowsgr.vision.image_matcher.ImageChecker`(输出 confidence)
- 标签页覆盖度 :mod:`autowsgr.ui.tabbed_page`(输出覆盖度)

PageMatch 把三者归一化为统一的 ``score`` (0.0-1.0),让页面注册中心
:func:`autowsgr.ui.page.get_current_page` 能在候选集内按分数排序、取最高分,
替代旧的"首次匹配即胜 + 布尔"逻辑。

本模块为纯数据模型,不含检测逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PageMatch:
    """单个页面的识别结果。

    Attributes
    ----------
    name:
        页面名称 (PageName 字符串)。
    matched:
        是否达到该页面的匹配门槛
        (像素签名 ALL 命中 / 模板 ≥ 置信度阈值 / tabbed 覆盖度超阈)。
    score:
        匹配强度,范围 0.0-1.0。像素=matched/total,模板=confidence,tabbed=覆盖度。
        即使 ``matched=False`` 也可能携带部分分数(如像素签名 3/4 命中得 0.75),
        供候选集排序消歧使用。
    """

    name: str
    matched: bool
    score: float

    def __bool__(self) -> bool:
        """``matched=True`` 视为真,兼容 ``if checker(screen):`` 写法。"""
        return self.matched
