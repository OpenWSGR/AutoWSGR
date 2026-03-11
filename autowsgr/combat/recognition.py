"""战斗识别 — DLL 舰类识别 + OCR 阵型/掉落识别。

包含核心识别函数:

- :func:`recognize_enemy_ships` — 6 张缩略图 → DLL → 舰类计数
- :func:`recognize_enemy_formation` — OCR 识别阵型文字
- :func:`recognize_ship_drop` — OCR 识别掉落舰船名称和类型

这些函数由 :mod:`~autowsgr.combat.actions` 中的高级接口调用。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image

from autowsgr.infra.logger import get_logger
from autowsgr.vision import ROI, ApiDll, PixelChecker, get_api_dll
from autowsgr.vision.pixel import MatchStrategy, PixelRule, PixelSignature


_log = get_logger('combat.recognition')

if TYPE_CHECKING:
    from autowsgr.vision import OCREngine


# ═══════════════════════════════════════════════════════════════════════════════
# 常量 — 扫描区域 (960x540 绝对像素, L/T/R/B)
# ═══════════════════════════════════════════════════════════════════════════════

# 移植自 autowsgr_legacy/constants/positions.py TYPE_SCAN_AREA
_SCAN_AREA_EXERCISE: list[tuple[int, int, int, int]] = [
    (277, 312, 309, 328),
    (380, 312, 412, 328),
    (483, 312, 515, 328),
    (587, 312, 619, 328),
    (690, 312, 722, 328),
    (793, 312, 825, 328),
]
"""演习界面的 6 个舰类图标扫描区域 (960x540)。"""

_SCAN_AREA_FIGHT: list[tuple[int, int, int, int]] = [
    (39, 156, 71, 172),
    (322, 156, 354, 172),
    (39, 245, 71, 261),
    (322, 245, 354, 261),
    (39, 334, 71, 350),
    (322, 334, 354, 350),
]
"""索敌成功界面的 6 个舰类图标扫描区域 (960x540, 2 列x3 行)。"""

_SCAN_AREAS: dict[str, list[tuple[int, int, int, int]]] = {
    'exercise': _SCAN_AREA_EXERCISE,
    'fight': _SCAN_AREA_FIGHT,
}

# 阵型 OCR 区域 (相对坐标)
_FORMATION_ROI = ROI(x1=0.11, y1=0.05, x2=0.20, y2=0.15)
"""敌方阵型文字区域 — 索敌成功页面左上方。"""

# OCR 阵型识别用的字符白名单
_FORMATION_ALLOWLIST = '单纵复轮型梯形横阵'

# 阵型名称映射 (OCR 结果 → 标准名)
_FORMATION_NAMES: dict[str, str] = {
    '单纵': '单纵阵',
    '复纵': '复纵阵',
    '轮型': '轮型阵',
    '梯形': '梯形阵',
    '单横': '单横阵',
}

# 无舰船（空位）的 DLL 返回值
_NO_SHIP = 'NO'


# ═══════════════════════════════════════════════════════════════════════════════
# 战斗结算页血量探测坐标
# ═══════════════════════════════════════════════════════════════════════════════

RESULT_BLOOD_BAR_PROBE: dict[int, tuple[float, float]] = {
    0: (60 / 960, 142 / 540),
    1: (60 / 960, 217 / 540),
    2: (60 / 960, 292 / 540),
    3: (60 / 960, 367 / 540),
    4: (60 / 960, 442 / 540),
    5: (60 / 960, 517 / 540),
}
"""战斗结算页 6 个舰船血条探测点 (0-indexed)。归一化坐标：原始绝对坐标 (60, y) 基于 960x540。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 敌方舰类识别
# ═══════════════════════════════════════════════════════════════════════════════


def recognize_enemy_ships(
    screen: np.ndarray,
    mode: str = 'fight',
    *,
    dll: ApiDll | None = None,
) -> dict[str, int]:
    """识别敌方舰船类型，返回舰类计数字典。

    复用旧代码稳定的 C++ DLL 方案:

    1. 将截图缩放到 960x540 并转灰度
    2. 按 ``TYPE_SCAN_AREA`` 裁切 6 张舰类图标缩略图
    3. 送入 ``ApiDll.recognize_enemy()`` 获得类型字符串
    4. 统计各类型数量

    Parameters
    ----------
    screen:
        当前截图 (HxWx3, RGB/BGR)。
    mode:
        识别模式: ``"fight"`` (索敌成功, 默认) 或 ``"exercise"`` (演习)。
    dll:
        DLL 实例，为 None 则使用单例。

    Returns
    -------
    dict[str, int]
        舰类缩写 → 数量，如 ``{"BB": 2, "CV": 1, "DD": 3, "ALL": 6}``。
        仅包含数量 > 0 的条目。
    """
    if dll is None:
        dll = get_api_dll()

    areas = _SCAN_AREAS.get(mode)
    if areas is None:
        raise ValueError(f'不支持的模式: {mode!r}，可选: {list(_SCAN_AREAS)}')

    # 转换为 960x540 灰度
    img = Image.fromarray(screen).convert('L')
    img = img.resize((960, 540))
    img_arr = np.array(img)

    # 裁切 6 张缩略图
    crops: list[np.ndarray] = []
    for left, top, right, bottom in areas:
        crops.append(img_arr[top:bottom, left:right])

    # DLL 识别
    result_str = dll.recognize_enemy(crops)
    types = result_str.split()
    _log.debug('[识别] DLL 返回: {}', result_str)

    # 统计
    counts: dict[str, int] = {}
    total = 0
    for t in types:
        if t == _NO_SHIP:
            continue
        counts[t] = counts.get(t, 0) + 1
        total += 1
    counts['ALL'] = total

    _log.debug('[识别] 敌方编成: {}', counts)
    return counts


# ═══════════════════════════════════════════════════════════════════════════════
# 敌方阵型识别
# ═══════════════════════════════════════════════════════════════════════════════


def recognize_enemy_formation(
    screen: np.ndarray,
    ocr: OCREngine,
) -> str:
    """OCR 识别敌方阵型名称。

    从索敌成功页面左上方裁切阵型文字区域，用 OCR 识别。

    Parameters
    ----------
    screen:
        当前截图 (HxWx3)。
    ocr:
        OCR 引擎实例。

    Returns
    -------
    str
        阵型名称（如 ``"单纵阵"``），识别失败时返回空字符串。
    """
    cropped = _FORMATION_ROI.crop(screen)

    result = ocr.recognize_single(cropped, allowlist=_FORMATION_ALLOWLIST)
    text = result.text.strip()

    if not text:
        _log.debug('[识别] 阵型 OCR 无结果')
        return ''

    # 尝试精确匹配
    for key, name in _FORMATION_NAMES.items():
        if key in text:
            _log.info('[识别] 敌方阵型: {}', name)
            return name

    # 模糊返回原文
    _log.info('[识别] 敌方阵型 (原文): {}', text)
    return text


# ═══════════════════════════════════════════════════════════════════════════════
# 舰船掉落识别
# ═══════════════════════════════════════════════════════════════════════════════

SHIP_DROP_PAGE_SIGNATURE = PixelSignature(
    name='ship_drop_page',
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.0500, 0.9500, (20, 40, 68), tolerance=15.0),
        PixelRule.of(0.9500, 0.9500, (12, 35, 60), tolerance=15.0),
        PixelRule.of(0.9070, 0.1569, (16, 26, 46), tolerance=15.0),
        PixelRule.of(0.8906, 0.0972, (20, 26, 45), tolerance=15.0),
        PixelRule.of(0.8016, 0.2361, (33, 82, 125), tolerance=30.0),
        PixelRule.of(0.8300, 0.3000, (253, 236, 166), tolerance=15.0),
        PixelRule.of(0.8719, 0.2333, (23, 41, 67), tolerance=15.0),
        PixelRule.of(0.8109, 0.2681, (36, 58, 72), tolerance=30.0),
    ],
)
"""舰船掉落页面像素签名。"""

# 旋转裁切区域 (左下角, 右上角, 旋转角度)
_SHIP_NAME_CROP = (0.754, 0.268, 0.983, 0.009, 25)
"""舰名 OCR 裁切参数 (bl_x, bl_y, tr_x, tr_y, angle)。"""

_SHIP_TYPE_CROP = (0.79, 0.29, 0.95, 0.1, 25)
"""舰种 OCR 裁切参数 (bl_x, bl_y, tr_x, tr_y, angle)。"""

# 画面中显示的舰种全称 -> 标准中文短名
_SHIP_TYPE_DISPLAY_MAP: dict[str, str] = {
    '航空母舰': '航母',
    '轻型航母': '轻母',
    '装甲航母': '装母',
    '战列舰': '战列',
    '航空战列舰': '航战',
    '战列巡洋舰': '战巡',
    '重巡洋舰': '重巡',
    '航空巡洋舰': '航巡',
    '雷击巡洋舰': '雷巡',
    '轻巡洋舰': '轻巡',
    '重炮舰': '重炮',
    '驱逐舰': '驱逐',
    '导弹潜艇': '导潜',
    '潜艇': '潜艇',
    '炮击潜艇': '炮潜',
    '补给舰': '补给',
    '导弹驱逐舰': '导驱',
    '防空驱逐舰': '防驱',
    '导弹巡洋舰': '导巡',
    '防空巡洋舰': '防巡',
    '大型巡洋舰': '大巡',
    '导弹战列舰': '导战',
}


@dataclass(frozen=True, slots=True)
class ShipDropResult:
    """舰船掉落识别结果。"""

    ship_name: str | None
    """匹配到的舰船名，识别失败时为 None。"""
    ship_type: str | None
    """舰种显示名称 (如 '驱逐舰')，识别失败时为 None。"""


def recognize_ship_drop(
    screen: np.ndarray,
    ocr: OCREngine,
) -> ShipDropResult:
    """识别舰船掉落页面的舰名和舰种。

    对截图中斜置的舰名和舰种文字区域进行旋转裁切后 OCR 识别。
    舰名通过模糊匹配校正，舰种直接读取。

    Parameters
    ----------
    screen:
        舰船掉落页面截图 (HxWx3, RGB)。
    ocr:
        OCR 引擎实例。

    Returns
    -------
    ShipDropResult
        包含舰名和舰种的识别结果。
    """
    # 裁切舰名区域
    name_img = PixelChecker.crop_rotated(screen, *_SHIP_NAME_CROP)
    ship_name = ocr.recognize_ship_name(name_img)
    _log.debug('[识别] 掉落舰名: {}', ship_name or '未识别')

    # 裁切舰种区域
    type_img = PixelChecker.crop_rotated(screen, *_SHIP_TYPE_CROP)
    type_result = ocr.recognize_single(type_img)
    ship_type = type_result.text.strip() or None
    _log.debug('[识别] 掉落舰种: {}', ship_type or '未识别')

    return ShipDropResult(ship_name=ship_name, ship_type=ship_type)


# ═══════════════════════════════════════════════════════════════════════════════
# MVP 识别
# ═══════════════════════════════════════════════════════════════════════════════

# 结算页 6 个舰船 y 中心坐标 (960x540 归一化)
_SHIP_SLOT_Y = [
    142 / 540,  # slot 1
    217 / 540,  # slot 2
    292 / 540,  # slot 3
    367 / 540,  # slot 4
    442 / 540,  # slot 5
    517 / 540,  # slot 6
]


def detect_mvp(
    screen: np.ndarray,
    confidence: float = 0.8,
) -> int | None:
    """从战斗结算截图中识别 MVP 位置。

    通过模板匹配定位 MVP 徽章，然后根据 y 坐标确定对应的舰船槽位。

    Parameters
    ----------
    screen:
        战斗结算页面截图 (HxWx3, RGB)。
    confidence:
        模板匹配最低置信度。

    Returns
    -------
    int | None
        MVP 舰船的位置 (1-6, 1-indexed)，未识别到返回 None。
    """
    from autowsgr.image_resources.combat import CombatTemplates
    from autowsgr.vision import ImageChecker

    tmpl = CombatTemplates.MVP_BADGE
    detail = ImageChecker.find_template(screen, tmpl, confidence=confidence)
    if detail is None:
        _log.debug('[识别] 未检测到 MVP 徽章')
        return None

    mvp_cy = detail.center[1]

    # 找到 y 坐标最近的舰船槽位
    best_slot = 0
    best_dist = abs(mvp_cy - _SHIP_SLOT_Y[0])
    for i in range(1, len(_SHIP_SLOT_Y)):
        dist = abs(mvp_cy - _SHIP_SLOT_Y[i])
        if dist < best_dist:
            best_dist = dist
            best_slot = i

    slot = best_slot + 1  # 1-indexed
    _log.info('[识别] MVP 位置: {} (conf={:.3f})', slot, detail.confidence)
    return slot


# ═══════════════════════════════════════════════════════════════════════════════
# 回调工厂
# ═══════════════════════════════════════════════════════════════════════════════
