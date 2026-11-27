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
   缩放到标准尺寸后与 5 个参考模板逐一比较，取覆盖度 (coverage)
   最高者为页面类型。裁剪宽度按页面区分: 地图页取左侧 78%
   (含第 5 个标签「决战」)，其余页面取 63%；对应标准宽度
   743 / 600 像素 (同一线性比例)。

模板匹配原理
------------

**二值化**: ``cv2.adaptiveThreshold`` (高斯, blockSize=21, C=-5)
在局部邻域做亮度对比，能同时提取高亮激活标签文字与灰色非激活标签文字，
同时抑制暗色背景。

**覆盖度 (coverage)**: 测试图像白色像素中有多少在参考模板中也是白色::

    coverage = |test ∩ template| / |test|

覆盖度越高，说明测试图像的亮区域越接近该模板。
参考模板由多张截图 OR 合成，覆盖了各标签激活状态。

**叠加类活动元素**: 活动徽章「战利品↑」挂在出征 tab 上方，随活动出现/消失。
它不进参考模板，而是在匹配前用色探针探测，命中时把徽章固定区从测试
条带中抹掉 (只抹 test 侧)。徽章有无都不影响识别，见 :func:`_loot_badge_visible`。

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


# ── 活动徽章「战利品↑」 ──
#
# 徽章是活动期间的临时叠加物，挂在出征 tab 右上角、位置固定，
# 活动结束即消失 —— 因此不进参考模板，改为探测后在匹配期排除。

LOOT_BADGE_PROBES: tuple[tuple[float, float], ...] = (
    (0.224, 0.030),
    (0.274, 0.030),
)
"""活动徽章「战利品↑」的 2 个探测点 (相对坐标)。

落在徽章橙色实底的左右两侧 (避开中央白色文字)，两帧实测均覆盖。
两个探测点**同时**命中才判定徽章在场。
"""

LOOT_BADGE_COLOR = Color.of(246, 93, 56)
"""活动徽章底色 (RGB)。"""

LOOT_BADGE_TOLERANCE: float = 40.0
"""徽章色探测容差 (欧几里得距离)。"""

LOOT_BADGE_MASK_REL: tuple[float, float, float, float] = (0.215, 0.283, 0.0, 0.052)
"""徽章排除区 ``(x0, x1, y0, y1)`` (相对坐标) — 徽章 bbox 加余量。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 模板匹配常量与加载
# ═══════════════════════════════════════════════════════════════════════════════

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / 'data' / 'images' / 'ui'
"""参考模板目录 (autowsgr/ui/templates/)。"""

_CROP_Y: float = 0.075
"""标签栏裁剪高度比例 (顶部 7.5%)。"""

_CROP_X: float = 0.63
"""标签栏默认裁剪宽度比例 (左侧 63%) — 建造/强化/任务/好友页。"""

_CROP_X_MAP: float = 0.78
"""地图页裁剪宽度比例 — 需含第 5 个标签「决战」(中心 x≈0.698, tab 右缘 ≈0.76)。"""

_STRIP_CROP_X: dict[TabbedPageType, float] = {
    TabbedPageType.MAP: _CROP_X_MAP,
    TabbedPageType.BUILD: _CROP_X,
    TabbedPageType.INTENSIFY: _CROP_X,
    TabbedPageType.MISSION: _CROP_X,
    TabbedPageType.FRIEND: _CROP_X,
}
"""各页面类型对应的标签栏裁剪宽度 (屏幕宽度比例)。"""

_REF_W: int = 600
"""基准标准宽度 (像素) — 对应裁剪宽度 ``_CROP_X`` (0.63)。"""


def _ref_width(x_end: float) -> int:
    """裁剪宽度 *x_end* 对应的标准宽度 (像素)。

    与基准保持同一线性比例: 0.63 → 600, 0.78 → 743。
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

    模板为二值 PNG (0/255)，尺寸与页面类型的裁剪宽度对应:
    地图页 743x40 (含决战 tab)，其余 600x40。

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
        result[page_type] = img > 0
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
        裁剪宽度 (屏幕宽度比例)。地图页需传 ``_CROP_X_MAP`` (0.78)
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
        参考模板布尔数组。

    Returns
    -------
    float
        覆盖度 [0.0, 1.0]。
    """
    test_sum = int(test.sum())
    if test_sum == 0:
        return 0.0
    return float((test & template).sum()) / test_sum


def _loot_badge_visible(screen: np.ndarray) -> bool:
    """探测活动徽章「战利品↑」是否在场。

    两个固定探测点**同时**命中徽章底色才判定在场，避免其他橙色 UI 误触发。

    Parameters
    ----------
    screen:
        截图 (HxWx3, RGB)。

    Returns
    -------
    bool
        徽章在场返回 ``True``。
    """
    return all(
        PixelChecker.check_pixel(screen, x, y, LOOT_BADGE_COLOR, LOOT_BADGE_TOLERANCE)
        for x, y in LOOT_BADGE_PROBES
    )


def _mask_loot_badge(strip: np.ndarray, x_end: float) -> None:
    """把徽章区从标签栏二值化条带的 test 侧抹掉 (原地修改)。

    徽章像素几乎都不在参考模板中，抹掉后单向覆盖度的分母变干净、分数回升；
    探针未命中 (徽章不存在) 时本函数不会被调用，模板像素照常匹配。

    Parameters
    ----------
    strip:
        标签栏二值化条带 (``_binarize_tabbar`` 的返回值)，原地置 False。
    x_end:
        该条带对应的裁剪宽度 (屏幕宽度比例)，用于把相对坐标换算成列号。
    """
    x0, x1, y0, y1 = LOOT_BADGE_MASK_REL
    rows, cols = strip.shape[:2]
    tx0 = min(max(int(x0 / x_end * cols), 0), cols)
    tx1 = min(max(int(x1 / x_end * cols), 0), cols)
    ty0 = min(max(int(y0 / _CROP_Y * rows), 0), rows)
    ty1 = min(max(int(y1 / _CROP_Y * rows), 0), rows)
    strip[ty0:ty1, tx0:tx1] = False


def _match_page_type(screen: np.ndarray) -> tuple[TabbedPageType, float] | None:
    """通过模板匹配识别标签页面类型。

    对标签栏区域二值化后，与 5 个参考模板逐一比较覆盖度，
    取最高者。各页面类型使用各自的裁剪宽度 (见 ``_STRIP_CROP_X``)，
    同一裁剪宽度的二值化结果只计算一次。

    活动徽章「战利品↑」在场时 (色探针命中),二值化条带先抹掉徽章区再计分。

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
    templates = _get_templates()
    if not templates:
        return None

    badge_on = _loot_badge_visible(screen)
    test_bins: dict[float, np.ndarray] = {}
    best_type: TabbedPageType | None = None
    best_score = -1.0
    for page_type, tmpl in templates.items():
        x_end = _STRIP_CROP_X[page_type]
        if x_end not in test_bins:
            strip = _binarize_tabbar(screen, x_end)
            if badge_on:
                _mask_loot_badge(strip, x_end)
            test_bins[x_end] = strip
        score = _coverage(test_bins[x_end], tmpl)
        if score > 0.6 and score > best_score:
            best_score = score
            best_type = page_type
    if best_type is None:
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
