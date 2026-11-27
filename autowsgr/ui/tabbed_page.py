"""标签页面统一检测层。

地图、建造、强化、任务、好友 五种页面共享同一种顶部标签栏布局::

    ┌──────────────────────────────────────────────────────────────┐
    │ ◁   [标签1]  标签2   标签3   ...                            │
    ├──────────────────────────────────────────────────────────────┤
    │                      内容区域                                │
    └──────────────────────────────────────────────────────────────┘

检测体系
--------

1. **标签栏探测** — 5 个固定位置，恰好 1 个蓝色 + 其余暗色
   → 确认为标签页，蓝色索引 = 激活标签 (0-4)

2. **模板匹配** — 对标签栏区域 (顶部 7.5%) 进行自适应二值化，
   与 5 个参考模板逐一比较覆盖度 (coverage)，取最高者为页面类型。
   候选默认共用同一条条带: 统一裁到左侧 76.5% (729 像素宽，含第 5 个
   标签「决战」)，600 像素宽的模板右侧补齐空白后再比较；任务页例外，
   按自身 63% 裁剪计分 (见 ``_SELF_STRIP_PAGES``)。

模板匹配原理
------------

**二值化**: ``cv2.adaptiveThreshold`` (高斯, blockSize=21, C=-5)
在局部邻域做亮度对比，能同时提取高亮激活标签文字与灰色非激活标签文字，
同时抑制暗色背景。

**覆盖度 (coverage)**: 测试图像白色像素中有多少在参考模板中也是白色::

    coverage = |test ∩ template| / |test|

覆盖度越高，说明测试图像的亮区域越接近该模板。
参考模板由多张截图 OR 合成，覆盖了各标签激活状态。

**统一条带**: 覆盖度的分母是「条带内的白像素总数」，所以各候选应在
同一条条带上比较。若按候选各裁一个宽度，同一块屏幕区域在不同候选里
占分母的比例不同——分母小的候选遇到叠加物 (活动徽章、资源计数器等)
时会涨得更快，分数失去可比性。见 :func:`score_all_pages`。
任务页按自身条带计分 (``_SELF_STRIP_PAGES``)，其分母与共用条带不同，
分数与其他候选不是严格可比。

标签与页面对应::

    索引  地图(5标签)  建造(4标签)  强化(3标签)  任务(5标签)  好友(4标签)
      0    出征         建造         强化         任务         好友
      1    演习         解体         改修          —           访问
      2    远征         开发         技能          —           搜索
      3    战役         废弃          —            —           申请
      4    决战          —            —            —            —

使用方式::

    from autowsgr.ui.tabbed_page import (
        TabbedPageType,
        is_tabbed_page,
        get_active_tab_index,
        identify_page_type,
        make_tab_checker,
    )

    screen = ctrl.screenshot()

    if is_tabbed_page(screen):
        idx = get_active_tab_index(screen)        # 0-4
        page = identify_page_type(screen)          # MAP / BUILD / FRIEND / ...

    # 用于 click_and_wait_for_page 的 checker
    checker = make_tab_checker(TabbedPageType.MAP, tab_index=2)
"""

from __future__ import annotations

import enum
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
import numpy as np

from autowsgr.types import PageName
from autowsgr.vision import Color, PageMatch, PixelChecker


# from autowsgr.infra.logger import get_logger

# _log = get_logger('ui.tabbed')


if TYPE_CHECKING:
    from collections.abc import Callable


# ═══════════════════════════════════════════════════════════════════════════════
# 枚举
# ═══════════════════════════════════════════════════════════════════════════════


class TabbedPageType(enum.Enum):
    """标签页面类型。"""

    MAP = PageName.MAP
    BUILD = PageName.BUILD
    INTENSIFY = PageName.INTENSIFY
    MISSION = PageName.MISSION
    FRIEND = PageName.FRIEND


# ═══════════════════════════════════════════════════════════════════════════════
# 标签栏探测常量
# ═══════════════════════════════════════════════════════════════════════════════

TAB_PROBES: list[tuple[float, float]] = [
    (0.1539, 0.0472),
    (0.2719, 0.0625),
    (0.4039, 0.0528),
    (0.5359, 0.0500),
    (0.6641, 0.0500),
]
"""5 个固定标签栏探测点 (相对坐标)。

激活标签处显示蓝色 ≈ (15, 132, 228)，其余为深色 (max < 80)。
"""

TAB_BLUE = Color.of(15, 132, 228)
"""激活标签参考颜色 (RGB)。"""

TAB_BLUE_TOLERANCE: float = 35.0
"""蓝色探测容差 (欧几里得距离)。"""

TAB_DARK_MAX: int = 80
"""非激活探测点最大通道阈值 — 超过此值不算 "暗色"。"""


# ── 非激活标签参考暗色 ──

TAB_DARK = (22, 37, 62)
"""非激活标签探测点的参考暗色 (RGB)，用于测试截图构造。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 模板匹配常量与加载
# ═══════════════════════════════════════════════════════════════════════════════

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / 'data' / 'images' / 'ui'
"""参考模板目录 (autowsgr/ui/templates/)。"""

_CROP_Y: float = 0.075
"""标签栏裁剪高度比例 (顶部 7.5%)。"""

_CROP_X: float = 0.63
"""标签栏默认裁剪宽度比例 (左侧 63%) — 建造/强化/任务/好友页。"""

_CROP_X_MAP: float = 0.765
"""地图页裁剪宽度比例 — 需含第 5 个标签「决战」(文字 0.641~0.762)。

上界取 0.765 而非 0.78: 决战文字右缘之外 0.769 起是右侧资源计数器方框，
方框边框随游戏状态出现/消失，切进条带会带来不属于任何模板的白像素。
"""

_STRIP_CROP_X: dict[TabbedPageType, float] = {
    TabbedPageType.MAP: _CROP_X_MAP,
    TabbedPageType.BUILD: _CROP_X,
    TabbedPageType.INTENSIFY: _CROP_X,
    TabbedPageType.MISSION: _CROP_X,
    TabbedPageType.FRIEND: _CROP_X,
}
"""各页面类型模板自身的宽度 (屏幕宽度比例)。

只用于加载时确定模板 PNG 的标准宽度; 匹配阶段除 :data:`_SELF_STRIP_PAGES`
外的页面统一裁到 ``_CROP_X_MAP`` 再补齐比较, 见 :func:`score_all_pages`。
"""

_SELF_STRIP_PAGES: frozenset[TabbedPageType] = frozenset({TabbedPageType.MISSION})
"""按自身裁剪宽度 (``_STRIP_CROP_X``) 单独计分的页面。

其余页面共用 ``_CROP_X_MAP`` 的一条条带, 分母一致, 分数可直接互比;
任务页保留改动前的独立条带: 其模板只含 1 个标签「任务」, 按 0.63 裁切
计分即与原行为一致。

注意: 这些页面的覆盖度分母与共用条带不同, 分数与其他候选不是严格可比。
"""

_REF_W: int = 600
"""基准标准宽度 (像素) — 对应裁剪宽度 ``_CROP_X`` (0.63)。"""


def _ref_width(x_end: float) -> int:
    """裁剪宽度 *x_end* 对应的标准宽度 (像素)。

    与基准保持同一线性比例: 0.63 → 600, 0.765 → 729。
    """
    return round(_REF_W * x_end / _CROP_X)


_REF_H: int = 40
"""模板标准高度 (像素)。"""

_ADAPTIVE_BLOCK: int = 21
"""自适应二值化块大小。"""

_ADAPTIVE_C: int = -5
"""自适应二值化常数 C (负值使更多像素变白)。"""


def _load_templates() -> dict[TabbedPageType, np.ndarray]:
    """从 ``autowsgr/ui/templates/`` 加载 5 个参考模板。

    模板为二值 PNG (0/255)，按页面类型的裁剪宽度裁到标准宽度
    ``_ref_width``: 地图页 729x40 (含决战 tab，模板文件比该宽度多出的
    列直接丢弃)，其余 600x40。

    Returns
    -------
    dict[TabbedPageType, np.ndarray]
        布尔数组 (True = 白色像素)。
    """
    mapping = {
        TabbedPageType.MAP: 'map.png',
        TabbedPageType.BUILD: 'build.png',
        TabbedPageType.INTENSIFY: 'intensify.png',
        TabbedPageType.MISSION: 'mission.png',
        TabbedPageType.FRIEND: 'friend.png',
    }
    result: dict[TabbedPageType, np.ndarray] = {}
    for page_type, filename in mapping.items():
        path = _TEMPLATE_DIR / filename
        buf = np.frombuffer(path.read_bytes(), np.uint8)
        img = cv2.imdecode(buf, cv2.IMREAD_UNCHANGED)
        result[page_type] = img[:, : _ref_width(_STRIP_CROP_X[page_type])] > 0
    return result


# 模块级缓存 — 首次调用时加载
@lru_cache(maxsize=1)
def _get_templates() -> dict[TabbedPageType, np.ndarray]:
    """获取参考模板 (懒加载 + 缓存)。"""
    return _load_templates()


def _binarize_tabbar(screen: np.ndarray, x_end: float = _CROP_X) -> np.ndarray:
    """将截图标签栏区域二值化并缩放到标准尺寸。

    步骤:

    1. 裁剪顶部 7.5%、左侧 *x_end* 比例 (标签栏区域)
    2. 转灰度
    3. 自适应阈值二值化 (高斯, blockSize=21, C=-5)
    4. 缩放到 ``_ref_width(x_end)`` x 40 (最近邻插值)

    Parameters
    ----------
    screen:
        截图 (HxWx3, RGB 或 BGR 均可用于灰度转换)。
    x_end:
        裁剪宽度 (屏幕宽度比例)。地图页需传 ``_CROP_X_MAP`` (0.765)
        以包含决战 tab。

    Returns
    -------
    np.ndarray
        布尔数组 (宽 ``_ref_width(x_end)`` x 40)，True = 白色像素。
    """
    h, w = screen.shape[:2]
    crop = screen[0 : int(h * _CROP_Y), 0 : int(w * x_end)]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    binary = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        _ADAPTIVE_BLOCK,
        _ADAPTIVE_C,
    )
    resized = cv2.resize(binary, (_ref_width(x_end), _REF_H), interpolation=cv2.INTER_NEAREST)
    return resized > 0


def _coverage(test: np.ndarray, template: np.ndarray) -> float:
    """计算覆盖度: 测试图像白色像素中有多少在模板中也是白色。

    ``coverage = |test ∩ template| / |test|``

    Parameters
    ----------
    test:
        测试图像布尔数组。
    template:
        参考模板布尔数组, 宽度需与 *test* 一致。

    Returns
    -------
    float
        覆盖度 [0.0, 1.0]。
    """
    test_sum = int(test.sum())
    if test_sum == 0:
        return 0.0
    return float((test & template).sum()) / test_sum


def _pad_template(template: np.ndarray, width: int) -> np.ndarray:
    """把模板右侧补齐到 *width* 列 (补 False)。

    补入的空白列永远匹配不上, 不改变模板自身的命中数; 作用是让所有候选
    与同一条带对齐, 使覆盖度的分母变成同一个数。

    Parameters
    ----------
    template:
        参考模板布尔数组 (宽 <= *width*)。
    width:
        目标宽度 (像素)。

    Returns
    -------
    np.ndarray
        宽度为 *width* 的布尔数组。
    """
    if template.shape[1] >= width:
        return template[:, :width]
    pad = width - template.shape[1]
    return np.pad(template, ((0, 0), (0, pad)), constant_values=False)


def score_all_pages(screen: np.ndarray) -> dict[TabbedPageType, float]:
    """对全部 5 个标签页面类型给出覆盖度分数。

    除 :data:`_SELF_STRIP_PAGES` 外, 候选共用一条按 ``_CROP_X_MAP`` 裁切的
    条带 (只二值化一次), 600 像素宽的模板补齐到同宽后比较 —— 分母一致,
    分数可直接互比。:data:`_SELF_STRIP_PAGES` 里的页面按自身裁剪宽度单独
    计分, 与原行为一致。

    Parameters
    ----------
    screen:
        截图 (HxWx3)。

    Returns
    -------
    dict[TabbedPageType, float]
        页面类型 → 覆盖度 [0.0, 1.0];无模板时返回空字典。
    """
    templates = _get_templates()
    if not templates:
        return {}

    shared: np.ndarray | None = None
    scores: dict[TabbedPageType, float] = {}
    for page_type, tmpl in templates.items():
        if page_type in _SELF_STRIP_PAGES:
            strip = _binarize_tabbar(screen, _STRIP_CROP_X[page_type])
            scores[page_type] = _coverage(strip, tmpl)
            continue
        if shared is None:
            shared = _binarize_tabbar(screen, _CROP_X_MAP)
        scores[page_type] = _coverage(shared, _pad_template(tmpl, shared.shape[1]))
    return scores


def _match_page_type(screen: np.ndarray) -> tuple[TabbedPageType, float] | None:
    """通过模板匹配识别标签页面类型。

    与 5 个参考模板逐一比较覆盖度, 取最高者。共用条带的页面分母相同;
    :data:`_SELF_STRIP_PAGES` 里的页面按自身条带计分(见 :func:`score_all_pages`)。

    Parameters
    ----------
    screen:
        截图 (HxWx3)。

    Returns
    -------
    tuple[TabbedPageType, float] | None
        ``(页面类型, 覆盖度)``;覆盖度需 > 0.6 才视为命中。
        无模板或无命中时返回 ``None``。
    """
    scores = score_all_pages(screen)
    if not scores:
        return None
    best_type = max(scores, key=lambda page_type: scores[page_type])
    best_score = scores[best_type]
    if best_score <= 0.6:
        return None
    return best_type, best_score


# ═══════════════════════════════════════════════════════════════════════════════
# 检测函数
# ═══════════════════════════════════════════════════════════════════════════════


def is_tabbed_page(screen: np.ndarray) -> bool:
    """判断截图是否为标签页面 (地图/建造/强化/任务 之一)。

    检测逻辑: 5 个标签栏探测点中恰好 1 个蓝色 + 其余全部暗色。

    Parameters
    ----------
    screen:
        截图 (HxWx3, RGB)。
    """
    blue_count = 0
    dark_count = 0
    for _i, (x, y) in enumerate(TAB_PROBES):
        pixel = PixelChecker.get_pixel(screen, x, y)
        is_blue = pixel.near(TAB_BLUE, TAB_BLUE_TOLERANCE)
        is_dark = max(pixel.r, pixel.g, pixel.b) < TAB_DARK_MAX
        # _log.debug(
        #     '[TabCheck] probe[{}] ({:.4f},{:.4f}) → ({},{},{}) blue={} dark={}',
        #     i, x, y, pixel.r, pixel.g, pixel.b, is_blue, is_dark,
        # )
        if is_blue:
            blue_count += 1
        elif is_dark:
            dark_count += 1
    result = blue_count == 1 and dark_count == len(TAB_PROBES) - 1
    # _log.debug('[TabCheck] blue={} dark={} → is_tabbed={}', blue_count, dark_count, result)
    return result


def get_active_tab_index(screen: np.ndarray) -> int | None:
    """获取当前激活标签的索引 (0-4)。

    Parameters
    ----------
    screen:
        截图 (HxWx3, RGB)。

    Returns
    -------
    int | None
        蓝色探测点的索引 (0-4)，未找到返回 ``None``。
    """
    for i, (x, y) in enumerate(TAB_PROBES):
        if PixelChecker.get_pixel(screen, x, y).near(TAB_BLUE, TAB_BLUE_TOLERANCE):
            return i
    return None


def identify_page_type(screen: np.ndarray) -> TabbedPageType | None:
    """识别截图对应的标签页面类型。

    两层检测:

    1. 标签栏验证 — 确认为标签页 (1 蓝 + 4 暗)
    2. 模板匹配 — 对标签栏区域二值化，与 5 个参考模板比较覆盖度

    Parameters
    ----------
    screen:
        截图 (HxWx3, RGB)。

    Returns
    -------
    TabbedPageType | None
        页面类型，非标签页返回 ``None``。
    """
    if not is_tabbed_page(screen):
        return None

    matched = _match_page_type(screen)
    return matched[0] if matched else None


def make_tab_checker(
    page_type: TabbedPageType,
    tab_index: int,
) -> Callable[[np.ndarray], bool]:
    """创建用于 :func:`click_and_wait_for_page` 的标签页验证函数。

    返回的函数检查:
    1. 页面类型匹配
    2. 激活标签索引匹配

    Parameters
    ----------
    page_type:
        期望的页面类型。
    tab_index:
        期望的激活标签索引 (0-4)。
    """

    def _check(screen: np.ndarray) -> bool:
        return identify_page_type(screen) == page_type and get_active_tab_index(screen) == tab_index

    return _check


def make_page_checker(
    page_type: TabbedPageType,
) -> Callable[[np.ndarray], bool]:
    """创建仅检查页面类型的验证函数 (不限定具体标签)。

    Parameters
    ----------
    page_type:
        期望的页面类型。
    """

    def _check(screen: np.ndarray) -> bool:
        return identify_page_type(screen) == page_type

    return _check


def check_tabbed_page(screen: np.ndarray, page_type: TabbedPageType) -> PageMatch:
    """识别截图是否为指定标签页面类型,返回带覆盖度分数的 :class:`PageMatch`。

    供 5 个标签页面 (地图/建造/强化/任务/好友) 的 ``is_current_page`` 注册到
    :func:`~autowsgr.ui.page.register_page` 使用:把两层检测
    (标签栏验证 + 模板覆盖度) 的结果统一为 ``score``,让页面注册中心
    能在候选集内按分数排序、消歧。

    Parameters
    ----------
    screen:
        截图 (HxWx3, RGB)。
    page_type:
        期望的页面类型。

    Returns
    -------
    PageMatch
        ``matched=True`` 时 ``score`` 为该页面的模板覆盖度 (0.6, 1.0]。
    """
    page_name = str(page_type.value)
    if not is_tabbed_page(screen):
        return PageMatch(name=page_name, matched=False, score=0.0)
    matched = _match_page_type(screen)
    if matched is None or matched[0] != page_type:
        return PageMatch(name=page_name, matched=False, score=0.0)
    return PageMatch(name=page_name, matched=True, score=matched[1])
