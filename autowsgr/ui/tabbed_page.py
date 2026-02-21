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
   → 确认为标签页，蓝色索引 = 激活标签 (0–4)

2. **模板匹配** — 对标签栏区域 (顶部 7.5%、左侧 63%) 进行自适应
   二值化，缩放到标准尺寸 (600×40) 后与 5 个参考模板逐一比较，
   取覆盖度 (coverage) 最高者为页面类型。

模板匹配原理
------------

**二值化**: ``cv2.adaptiveThreshold`` (高斯, blockSize=21, C=-5)
在局部邻域做亮度对比，能同时提取高亮激活标签文字与灰色非激活标签文字，
同时抑制暗色背景。

**覆盖度 (coverage)**: 测试图像白色像素中有多少在参考模板中也是白色::

    coverage = |test ∩ template| / |test|

覆盖度越高，说明测试图像的亮区域越接近该模板。
参考模板由多张截图 OR 合成，覆盖了各标签激活状态。

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
        idx = get_active_tab_index(screen)        # 0–4
        page = identify_page_type(screen)          # MAP / BUILD / FRIEND / ...

    # 用于 click_and_wait_for_page 的 checker
    checker = make_tab_checker(TabbedPageType.MAP, tab_index=2)
"""

from __future__ import annotations

import enum
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from autowsgr.types import PageName
from autowsgr.vision import Color, PixelChecker


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
    (0.1415, 0.0417),
    (0.2727, 0.0486),
    (0.4031, 0.0486),
    (0.5352, 0.0486),
    (0.6617, 0.0542),
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

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
"""参考模板目录 (autowsgr/ui/templates/)。"""

_CROP_Y: float = 0.075
"""标签栏裁剪高度比例 (顶部 7.5%)。"""

_CROP_X: float = 0.63
"""标签栏裁剪宽度比例 (左侧 63%)。"""

_REF_W: int = 600
"""模板标准宽度 (像素)。"""

_REF_H: int = 40
"""模板标准高度 (像素)。"""

_ADAPTIVE_BLOCK: int = 21
"""自适应二值化块大小。"""

_ADAPTIVE_C: int = -5
"""自适应二值化常数 C (负值使更多像素变白)。"""


def _load_templates() -> dict[TabbedPageType, np.ndarray]:
    """从 ``autowsgr/ui/templates/`` 加载 5 个参考模板。

    模板为二值 PNG (0/255)，尺寸 600×40。

    Returns
    -------
    dict[TabbedPageType, np.ndarray]
        布尔数组 (True = 白色像素)。
    """
    mapping = {
        TabbedPageType.MAP: "map.png",
        TabbedPageType.BUILD: "build.png",
        TabbedPageType.INTENSIFY: "intensify.png",
        TabbedPageType.MISSION: "mission.png",
        TabbedPageType.FRIEND: "friend.png",
    }
    result: dict[TabbedPageType, np.ndarray] = {}
    for page_type, filename in mapping.items():
        path = _TEMPLATE_DIR / filename
        buf = np.frombuffer(path.read_bytes(), np.uint8)
        img = cv2.imdecode(buf, cv2.IMREAD_UNCHANGED)
        result[page_type] = img > 0
    return result


# 模块级缓存 — 首次调用时加载
_templates: dict[TabbedPageType, np.ndarray] | None = None


def _get_templates() -> dict[TabbedPageType, np.ndarray]:
    """获取参考模板 (懒加载 + 缓存)。"""
    global _templates  # noqa: PLW0603
    if _templates is None:
        _templates = _load_templates()
    return _templates


def _binarize_tabbar(screen: np.ndarray) -> np.ndarray:
    """将截图标签栏区域二值化并缩放到标准尺寸。

    步骤:

    1. 裁剪顶部 7.5%、左侧 63% (标签栏区域)
    2. 转灰度
    3. 自适应阈值二值化 (高斯, blockSize=21, C=-5)
    4. 缩放到 600×40 (最近邻插值)

    Parameters
    ----------
    screen:
        截图 (H×W×3, RGB 或 BGR 均可用于灰度转换)。

    Returns
    -------
    np.ndarray
        布尔数组 (600×40)，True = 白色像素。
    """
    h, w = screen.shape[:2]
    crop = screen[0 : int(h * _CROP_Y), 0 : int(w * _CROP_X)]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, _ADAPTIVE_BLOCK, _ADAPTIVE_C,
    )
    resized = cv2.resize(binary, (_REF_W, _REF_H), interpolation=cv2.INTER_NEAREST)
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


def _match_page_type(screen: np.ndarray) -> TabbedPageType | None:
    """通过模板匹配识别标签页面类型。

    对标签栏区域二值化后，与 5 个参考模板逐一比较覆盖度，
    取最高者。

    Parameters
    ----------
    screen:
        截图 (H×W×3)。

    Returns
    -------
    TabbedPageType | None
        覆盖度最高的页面类型，无模板时返回 ``None``。
    """
    templates = _get_templates()
    if not templates:
        return None

    test_bin = _binarize_tabbar(screen)
    best_type: TabbedPageType | None = None
    best_score = -1.0
    for page_type, tmpl in templates.items():
        score = _coverage(test_bin, tmpl)
        if score > best_score:
            best_score = score
            best_type = page_type
    return best_type


# ═══════════════════════════════════════════════════════════════════════════════
# 检测函数
# ═══════════════════════════════════════════════════════════════════════════════


def is_tabbed_page(screen: np.ndarray) -> bool:
    """判断截图是否为标签页面 (地图/建造/强化/任务 之一)。

    检测逻辑: 5 个标签栏探测点中恰好 1 个蓝色 + 其余全部暗色。

    Parameters
    ----------
    screen:
        截图 (H×W×3, RGB)。
    """
    blue_count = 0
    dark_count = 0
    for x, y in TAB_PROBES:
        pixel = PixelChecker.get_pixel(screen, x, y)
        if pixel.near(TAB_BLUE, TAB_BLUE_TOLERANCE):
            blue_count += 1
        elif max(pixel.r, pixel.g, pixel.b) < TAB_DARK_MAX:
            dark_count += 1
    return blue_count == 1 and dark_count == len(TAB_PROBES) - 1


def get_active_tab_index(screen: np.ndarray) -> int | None:
    """获取当前激活标签的索引 (0–4)。

    Parameters
    ----------
    screen:
        截图 (H×W×3, RGB)。

    Returns
    -------
    int | None
        蓝色探测点的索引 (0–4)，未找到返回 ``None``。
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
        截图 (H×W×3, RGB)。

    Returns
    -------
    TabbedPageType | None
        页面类型，非标签页返回 ``None``。
    """
    if not is_tabbed_page(screen):
        return None

    return _match_page_type(screen)


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
        期望的激活标签索引 (0–4)。
    """

    def _check(screen: np.ndarray) -> bool:
        return (
            identify_page_type(screen) == page_type
            and get_active_tab_index(screen) == tab_index
        )

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
