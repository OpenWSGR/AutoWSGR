"""决战舰队 OCR 识别模块。

提供决战战备舰队获取界面的 OCR 识别功能，包括：

- 可用分数与费用识别
- 舰船名称识别
- 副官技能使用与舰船扫描

这些函数由 :class:`DecisiveMapController` 委托调用。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import cv2

from autowsgr.infra.logger import get_logger
from autowsgr.types import FleetSelection
from autowsgr.ui.decisive.overlay import (
    COST_AREA,
    FLEET_CARD_CLICK_Y,
    FLEET_CARD_X_POSITIONS,
    RESOURCE_AREA,
    SHIP_NAME_X_RANGES,
    SHIP_NAME_Y_RANGE,
)
from autowsgr.vision import ROI, OCREngine


if TYPE_CHECKING:
    import numpy as np

    from autowsgr.emulator import AndroidController


_log = get_logger('ui.decisive')


def recognize_fleet_options(
    ocr: OCREngine,
    config: DecisiveConfig,
    screen: np.ndarray,
) -> tuple[int, dict[str, FleetSelection]]:
    """OCR 识别战备舰队获取界面的可选项。

    Returns
    -------
    tuple[int, dict[str, FleetSelection]]
        ``(score, selections)`` — 当前可用分数与可购买项字典。
    """
    # 1. 识别可用分数
    res_roi = ROI(
        x1=RESOURCE_AREA[0][0],
        y1=RESOURCE_AREA[1][1],
        x2=RESOURCE_AREA[1][0],
        y2=RESOURCE_AREA[0][1],
    )
    score_img = res_roi.crop(screen)
    score_val = ocr.recognize_number(score_img)
    score = score_val if score_val is not None else 0
    # TODO: 分数 OCR 需要改进
    if score_val is not None:
        _log.debug('[舰队OCR] 可用分数: {}', score_val)
    else:
        _log.warning('[舰队OCR] 分数 OCR 失败')

    # 2. 识别费用整行
    cost_roi = ROI(
        x1=COST_AREA[0][0],
        y1=COST_AREA[1][1],
        x2=COST_AREA[1][0],
        y2=COST_AREA[0][1],
    )
    cost_img = cost_roi.crop(screen)
    cost_results = ocr.recognize(cost_img, allowlist='0123456789x')

    costs: list[int] = []
    for r in cost_results:
        text = r.text.strip().lstrip('xX')
        try:
            costs.append(int(text))
        except (ValueError, TypeError):
            _log.debug("[舰队OCR] 费用解析跳过: '{}'", r.text)
    _log.debug('[舰队OCR] 识别到 {} 项费用: {}', len(costs), costs)

    # 3. 对可负担的卡识别舰船名
    selections: dict[str, FleetSelection] = {}
    for i, cost in enumerate(costs):
        if cost > score:
            continue
        if i >= len(SHIP_NAME_X_RANGES):
            break

        x_range = SHIP_NAME_X_RANGES[i]
        y_range = SHIP_NAME_Y_RANGE
        name_roi = ROI(x1=x_range[0], y1=y_range[0], x2=x_range[1], y2=y_range[1])
        name_img = name_roi.crop(screen)

        name = ocr.recognize_ship_name(name_img)
        if name is None:
            raw = ocr.recognize_single(name_img)
            name = raw.text.strip() if raw.text.strip() else f'未识别_{i}'
            _log.debug("[舰队OCR] 舰船名模糊匹配失败, 原文: '{}'", name)

        click_x = FLEET_CARD_X_POSITIONS[i] if i < len(FLEET_CARD_X_POSITIONS) else 0.5
        click_y = FLEET_CARD_CLICK_Y

        selections[name] = FleetSelection(
            name=name,
            cost=cost,
            click_position=(click_x, click_y),
        )

    _log.info('[舰队OCR] 舰队选项: {}', {k: v.cost for k, v in selections.items()})
    return (score, selections)


def detect_last_offer_name(
    ocr: OCREngine,
    config: DecisiveConfig,
    screen: np.ndarray,
) -> str | None:
    """读取战备舰队最后一张卡的名称，用于首节点判定修正。"""
    x_range = SHIP_NAME_X_RANGES[4]
    y_range = SHIP_NAME_Y_RANGE
    name_roi = ROI(x1=x_range[0], y1=y_range[0], x2=x_range[1], y2=y_range[1])
    name_img = name_roi.crop(screen)
    return ocr.recognize_ship_name(name_img)


def use_skill(
    ctrl: AndroidController,
    ocr: OCREngine,
    config: DecisiveConfig,
) -> list[str]:
    """在地图页使用一次副官技能并返回识别到的舰船。"""
    skill_pos = (0.2143, 0.894)
    ship_area = ROI(x1=0.26, y1=0.685, x2=0.74, y2=0.715)

    ctrl.click(*skill_pos)
    time.sleep(0.5)

    screen = ctrl.screenshot()
    crop = ship_area.crop(screen)
    result = ocr.recognize_ship_name(crop)
    acquired: list[str] = []
    if result is not None:
        acquired.append(result)

    ctrl.click(*skill_pos)  # 快进一下
    return acquired


# ═══════════════════════════════════════════════════════════════════════════════
# 选船列表 DLL 行定位 + OCR（共享基础函数）
# ═══════════════════════════════════════════════════════════════════════════════

#: Legacy 标准分辨率（DLL 校准基准）
_LEGACY_WIDTH: int = 1280
_LEGACY_HEIGHT: int = 720

#: Legacy 选船列表左侧裁剪宽度 (px@1280)
_LEGACY_LIST_WIDTH: int = 1048


def _to_legacy_format(screen: np.ndarray) -> tuple[np.ndarray, float, float]:
    """将 V2 截图转为 DLL 所需的 legacy 格式。

    DLL 内部基于 1280×720 BGR 图像校准，V2 ``screenshot()``
    返回模拟器原生分辨率的 RGB 图像，需做两步转换。

    Returns
    -------
    tuple[np.ndarray, float, float]
        ``(bgr_720p, scale_y, scale_x)``
        —— bgr_720p: 1280×720 BGR 图像
        —— scale_y / scale_x: legacy 坐标 → 原始坐标的缩放比
    """
    h, w = screen.shape[:2]
    scale_y = h / _LEGACY_HEIGHT
    scale_x = w / _LEGACY_WIDTH
    resized = cv2.resize(screen, (_LEGACY_WIDTH, _LEGACY_HEIGHT))
    bgr = cv2.cvtColor(resized, cv2.COLOR_RGB2BGR)
    return bgr, scale_y, scale_x


def locate_ship_rows(
    ocr: OCREngine,
    screen: np.ndarray,
) -> list[tuple[str, float, float]]:
    """在选船列表页用 DLL 定位舰船名行，再逐行 OCR 识别。

    其他场景（如 ``_click_ship_in_list``、``recognize_ships_in_list``）
    应复用此函数而非重复实现 OCR 逻辑。

    对齐 legacy ``recognize_ship``:

    1. resize + RGB→BGR 转为 1280×720 BGR（DLL 校准基准）
    2. 裁剪左侧 1048px（与 legacy `screen[:, :1048]` 一致）
    3. ``dll.locate()`` 定位行区域
    4. 将行坐标映射回原始分辨率，在原图上裁剪并 OCR

    Parameters
    ----------
    ocr:
        OCR 引擎实例。
    screen:
        选船列表页面的 V2 截图 (RGB, 任意分辨率)。

    Returns
    -------
    list[tuple[str, float, float]]
        ``(ship_name, cx_rel, cy_rel)`` 列表——舰船名及其行中心
        相对于 **完整截图** 的归一化坐标。
    """
    from autowsgr.constants import SHIPNAMES
    from autowsgr.vision import get_api_dll
    from autowsgr.vision.ocr import _fuzzy_match

    h, w = screen.shape[:2]

    # 转为 legacy 格式 (1280×720, BGR)
    bgr_720p, scale_y, scale_x = _to_legacy_format(screen)
    list_720p = bgr_720p[:, :_LEGACY_LIST_WIDTH]  # legacy 裁剪宽度

    dll = get_api_dll()
    rows = dll.locate(list_720p)
    _log.debug('[舰队OCR] DLL 定位到 {} 行候选项', len(rows))

    # 在原始分辨率上裁剪并 OCR（用原图的左 82% 区域）
    list_w_native = int(w * _LEGACY_LIST_WIDTH / _LEGACY_WIDTH)
    list_area_native = screen[:, :list_w_native]

    found: list[tuple[str, float, float]] = []
    seen: set[str] = set()
    for y_start_720, y_end_720 in rows:
        # 将 720p 坐标映射回原始分辨率
        y_start = max(0, int((y_start_720 - 1) * scale_y))
        y_end = min(h, int((y_end_720 + 1) * scale_y))

        row_img = list_area_native[y_start:y_end]

        # 对齐 legacy: recognize(multiple=True) — 同一 DLL 行可含多个舰船名
        results = ocr.recognize(row_img)
        for r in results:
            text = r.text.strip()
            if not text:
                continue
            name = _fuzzy_match(text, SHIPNAMES)
            if name is None or name in seen:
                continue
            seen.add(name)
            # 从 bbox 计算精确位置（bbox 相对于 row_img）
            if r.bbox is not None:
                x1, y1, x2, y2 = r.bbox
                cx = (x1 + x2) / 2 / w
                cy = (y_start + (y1 + y2) / 2) / h
            else:
                cx = list_w_native / 2 / w
                cy = (y_start + y_end) / 2 / h
            found.append((name, cx, cy))

    _log.debug(
        '[舰队OCR] 选船列表识别: {} (共 {} 行)',
        sorted({n for n, _, _ in found}),
        len(rows),
    )
    return found


def recognize_ships_in_list(
    ocr: OCREngine,
    screen: np.ndarray,
) -> set[str]:
    """识别选船列表页面中的所有可见舰船名（去重集合）。

    基于 :func:`locate_ship_rows` 的薄封装。
    """
    return {name for name, _, _ in locate_ship_rows(ocr, screen)}
