"""敌方编成识别 — DLL 舰类识别 + OCR 阵型识别。

包含核心识别函数:

- :func:`recognize_enemy_ships` — 6 张缩略图 → DLL → 舰类计数
- :func:`recognize_enemy_formation` — OCR 识别阵型文字

这些函数由 :mod:`~autowsgr.combat.actions` 中的高级接口调用。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from loguru import logger
from PIL import Image

from autowsgr.vision import ApiDll, get_api_dll, ROI

if TYPE_CHECKING:
    from autowsgr.emulator.controller import AndroidController
    from autowsgr.vision import OCREngine


# ═══════════════════════════════════════════════════════════════════════════════
# 常量 — 扫描区域 (960×540 绝对像素, L/T/R/B)
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
"""演习界面的 6 个舰类图标扫描区域 (960×540)。"""

_SCAN_AREA_FIGHT: list[tuple[int, int, int, int]] = [
    (39, 156, 71, 172),
    (322, 156, 354, 172),
    (39, 245, 71, 261),
    (322, 245, 354, 261),
    (39, 334, 71, 350),
    (322, 334, 354, 350),
]
"""索敌成功界面的 6 个舰类图标扫描区域 (960×540, 2 列×3 行)。"""

_SCAN_AREAS: dict[str, list[tuple[int, int, int, int]]] = {
    "exercise": _SCAN_AREA_EXERCISE,
    "fight": _SCAN_AREA_FIGHT,
}

# 阵型 OCR 区域 (相对坐标)
_FORMATION_ROI = ROI(x1=0.11, y1=0.05, x2=0.20, y2=0.15)
"""敌方阵型文字区域 — 索敌成功页面左上方。"""

# OCR 阵型识别用的字符白名单
_FORMATION_ALLOWLIST = "单纵复轮型梯形横阵"

# 阵型名称映射 (OCR 结果 → 标准名)
_FORMATION_NAMES: dict[str, str] = {
    "单纵": "单纵阵",
    "复纵": "复纵阵",
    "轮型": "轮型阵",
    "梯形": "梯形阵",
    "单横": "单横阵",
}

# 无舰船（空位）的 DLL 返回值
_NO_SHIP = "NO"


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
"""战斗结算页 6 个舰船血条探测点 (0-indexed)。归一化坐标：原始绝对坐标 (60, y) 基于 960×540。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 敌方舰类识别
# ═══════════════════════════════════════════════════════════════════════════════


def recognize_enemy_ships(
    screen: np.ndarray,
    mode: str = "fight",
    *,
    dll: ApiDll | None = None,
) -> dict[str, int]:
    """识别敌方舰船类型，返回舰类计数字典。

    复用旧代码稳定的 C++ DLL 方案:

    1. 将截图缩放到 960×540 并转灰度
    2. 按 ``TYPE_SCAN_AREA`` 裁切 6 张舰类图标缩略图
    3. 送入 ``ApiDll.recognize_enemy()`` 获得类型字符串
    4. 统计各类型数量

    Parameters
    ----------
    screen:
        当前截图 (H×W×3, RGB/BGR)。
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
        raise ValueError(f"不支持的模式: {mode!r}，可选: {list(_SCAN_AREAS)}")

    # 转换为 960×540 灰度
    img = Image.fromarray(screen).convert("L")
    img = img.resize((960, 540))
    img_arr = np.array(img)

    # 裁切 6 张缩略图
    crops: list[np.ndarray] = []
    for left, top, right, bottom in areas:
        crops.append(img_arr[top:bottom, left:right])

    # DLL 识别
    result_str = dll.recognize_enemy(crops)
    types = result_str.split()
    logger.debug("[识别] DLL 返回: {}", result_str)

    # 统计
    counts: dict[str, int] = {}
    total = 0
    for t in types:
        if t == _NO_SHIP:
            continue
        counts[t] = counts.get(t, 0) + 1
        total += 1
    counts["ALL"] = total

    logger.info("[识别] 敌方编成: {}", counts)
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
        当前截图 (H×W×3)。
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
        logger.debug("[识别] 阵型 OCR 无结果")
        return ""

    # 尝试精确匹配
    for key, name in _FORMATION_NAMES.items():
        if key in text:
            logger.info("[识别] 敌方阵型: {}", name)
            return name

    # 模糊返回原文
    logger.info("[识别] 敌方阵型 (原文): {}", text)
    return text


# ═══════════════════════════════════════════════════════════════════════════════
# 回调工厂
# ═══════════════════════════════════════════════════════════════════════════════

