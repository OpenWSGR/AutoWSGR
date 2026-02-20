"""敌方编成识别 — DLL 舰类识别 + OCR 阵型识别。

整合 C++ DLL（``ApiDll``）和 OCR 引擎，提供完整的敌方情报识别能力，
替代旧代码中分散在 ``get_game_info.py`` 的逻辑。

主要功能:

- :func:`recognize_enemy_ships` — 6 张缩略图 → DLL → 舰类计数
- :func:`recognize_enemy_formation` — OCR 识别阵型文字
- :func:`make_enemy_callbacks` — 工厂函数，生成可直接注入 ``CombatEngine`` 的回调

使用方式::

    from autowsgr.combat.recognition import make_enemy_callbacks

    get_info, get_formation = make_enemy_callbacks(ctrl, ocr)
    engine = CombatEngine(
        device=ctrl,
        plan=plan,
        image_matcher=matcher,
        get_enemy_info=get_info,
        get_enemy_formation=get_formation,
    )
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from loguru import logger
from PIL import Image

from autowsgr.combat.callbacks import GetEnemyFormationFunc, GetEnemyInfoFunc
from autowsgr.vision.api_dll import ApiDll, get_api_dll
from autowsgr.vision.roi import ROI

if TYPE_CHECKING:
    from autowsgr.emulator.controller import AndroidController
    from autowsgr.vision.ocr import OCREngine


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


def make_enemy_callbacks(
    ctrl: AndroidController,
    ocr: OCREngine | None = None,
    *,
    mode: str = "fight",
    dll: ApiDll | None = None,
) -> tuple[GetEnemyInfoFunc, GetEnemyFormationFunc]:
    """创建可注入 ``CombatEngine`` 的敌方识别回调。

    返回的回调在被调用时自动截图并执行识别。

    Parameters
    ----------
    ctrl:
        设备控制器（提供截图能力）。
    ocr:
        OCR 引擎（阵型识别用，为 None 则跳过阵型识别）。
    mode:
        识别模式，传给 :func:`recognize_enemy_ships`。
    dll:
        DLL 实例。

    Returns
    -------
    tuple[GetEnemyInfoFunc, GetEnemyFormationFunc]
        ``(get_enemy_info, get_enemy_formation)`` 回调二元组。

    Examples
    --------
    ::

        get_info, get_formation = make_enemy_callbacks(ctrl, ocr)
        result = run_combat(
            ctrl, plan, matcher,
            get_enemy_info=get_info,
            get_enemy_formation=get_formation,
        )
    """
    if dll is None:
        dll = get_api_dll()

    def get_enemy_info() -> dict[str, int]:
        screen = ctrl.screenshot()
        return recognize_enemy_ships(screen, mode=mode, dll=dll)

    def get_enemy_formation() -> str:
        if ocr is None:
            return ""
        screen = ctrl.screenshot()
        return recognize_enemy_formation(screen, ocr)

    return get_enemy_info, get_enemy_formation
