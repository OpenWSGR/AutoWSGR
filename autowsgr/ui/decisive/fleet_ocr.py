"""决战舰队 OCR 识别模块。

提供决战战备舰队获取界面的 OCR 识别功能，包括：

- 可用分数与费用识别
- 舰船名称识别
- 副官技能使用与舰船扫描

这些函数由 :class:`DecisiveMapController` 委托调用。
"""

from __future__ import annotations

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
from autowsgr.ui.utils.navigation import check_stop
from autowsgr.vision import ROI, OCREngine


if TYPE_CHECKING:
    import numpy as np

    from autowsgr.context import GameContext


_log = get_logger('ui.decisive')


def _parse_offer_cost_text(text: str) -> int | None:
    """解析战备舰队购买界面的费用文本，兼容 x4 / X4 格式。"""
    cleaned = text.strip().replace(' ', '')
    cleaned = cleaned.lstrip('xX')
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def _prepare_text_roi(image: np.ndarray, *, scale: int = 4) -> np.ndarray:
    """对小块文字区域做放大 + 提升对比度，改善 EasyOCR 无结果问题。"""
    if image.size == 0:
        return image

    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    norm = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
    binary = cv2.threshold(norm, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    return cv2.cvtColor(binary, cv2.COLOR_GRAY2RGB)


def _prepare_name_roi(image: np.ndarray) -> np.ndarray:
    """舰名区域做温和增强，保留字形细节。"""
    if image.size == 0:
        return image

    enlarged = cv2.resize(image, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    lab = cv2.cvtColor(enlarged, cv2.COLOR_RGB2LAB)
    lightness_channel, a, b = cv2.split(lab)
    lightness_channel = cv2.equalizeHist(lightness_channel)
    enhanced = cv2.merge((lightness_channel, a, b))
    return cv2.cvtColor(enhanced, cv2.COLOR_LAB2RGB)


def recognize_fleet_options(
    ocr: OCREngine,
    screen: np.ndarray,
    fallback_score: int | None = None,
) -> tuple[int, dict[str, FleetSelection]]:
    """OCR 识别战备舰队获取界面的可选项。

    保留原版识别思路：
    - 分数仍按单块数字识别
    - 费用恢复为整行 OCR + 本地解析 x4/x5 文本
    - 舰名恢复为仅对可购买项识别，避免受调试增强链路影响

    Returns
    -------
    tuple[int, dict[str, FleetSelection]]
        ``(score, selections)`` — 当前可用分数与可购买项字典。
        当右上角分数 OCR 失败时，若提供 ``fallback_score``，则回退为该值。
    """
    _log.debug('[舰队OCR] 开始识别战备舰队可选项')

    # 1. 识别可用分数
    res_roi = ROI(
        x1=RESOURCE_AREA[0][0],
        y1=RESOURCE_AREA[1][1],
        x2=RESOURCE_AREA[1][0],
        y2=RESOURCE_AREA[0][1],
    )
    score_img = _prepare_text_roi(res_roi.crop(screen))
    score_val = ocr.recognize_number(score_img)
    if score_val is not None:
        score = score_val
        _log.debug('[舰队OCR] 可用分数: {}', score_val)
    elif fallback_score is not None:
        score = fallback_score
        _log.warning('[舰队OCR] 分数 OCR 失败，回退使用状态分数: {}', fallback_score)
    else:
        score = 0
        _log.warning('[舰队OCR] 分数 OCR 失败')

    # 2. 恢复原版费用识别：整行 OCR + 本地解析 x4/x5
    cost_roi = ROI(
        x1=COST_AREA[0][0],
        y1=COST_AREA[1][1],
        x2=COST_AREA[1][0],
        y2=COST_AREA[0][1],
    )
    cost_img = cost_roi.crop(screen)
    cost_results = ocr.recognize(cost_img, allowlist='0123456789xX')
    # OCR 漏掉一张卡的费用时，其余费用仍按画面位置归属。
    costs: dict[int, list[int]] = {}
    width = screen.shape[1]
    for result in cost_results:
        cost = _parse_offer_cost_text(result.text)
        if result.bbox is None or cost is None or cost < 0:
            continue
        center = (int(cost_roi.x1 * width) + (result.bbox[0] + result.bbox[2]) / 2) / width
        for slot, (left, right) in enumerate(SHIP_NAME_X_RANGES):
            if left <= center <= right:
                costs.setdefault(slot, []).append(cost)
                break

    selections: dict[str, FleetSelection] = {}
    for i, values in sorted(costs.items()):
        if len(values) != 1 or values[0] > score:
            continue
        cost = values[0]
        x_range = SHIP_NAME_X_RANGES[i]
        y_range = SHIP_NAME_Y_RANGE
        name_roi = ROI(x1=x_range[0], y1=y_range[0], x2=x_range[1], y2=y_range[1])
        name_img = name_roi.crop(screen)

        name = ocr.recognize_ship_name(name_img)
        if name is None:
            _log.debug('[舰队OCR] 卡位 {} 未识别，不作为可购买项', i)
            continue

        click_x = FLEET_CARD_X_POSITIONS[i] if i < len(FLEET_CARD_X_POSITIONS) else 0.5
        click_y = FLEET_CARD_CLICK_Y

        if name in selections and selections[name].cost <= cost:
            continue
        selections[name] = FleetSelection(
            name=name,
            cost=cost,
            click_position=(click_x, click_y),
        )

    _log.info('[舰队OCR] 舰队选项: {}', {k: v.cost for k, v in selections.items()})
    return (score, selections)


def detect_last_offer_name(
    ocr: OCREngine,
    screen: np.ndarray,
) -> str | None:
    """读取战备舰队最后一张卡的名称，用于首节点判定修正。"""
    x_range = SHIP_NAME_X_RANGES[4]
    y_range = SHIP_NAME_Y_RANGE
    name_roi = ROI(x1=x_range[0], y1=y_range[0], x2=x_range[1], y2=y_range[1])
    name_img = name_roi.crop(screen)
    return ocr.recognize_ship_name(name_img)


def use_skill(
    ctx: GameContext,
    ocr: OCREngine,
) -> list[str]:
    """在地图页使用一次副官技能并返回识别到的舰船。"""
    skill_pos = (0.2143, 0.894)
    ship_area = ROI(x1=0.26, y1=0.685, x2=0.74, y2=0.715)

    check_stop(ctx.stop_event)
    ctx.ctrl.click(*skill_pos)
    ctx.stop_event.wait(1.0)
    check_stop(ctx.stop_event)

    screen = ctx.ctrl.screenshot()
    crop = ship_area.crop(screen)
    result = ocr.recognize_ship_names(crop)
    acquired: list[str] = []
    if result is not None:
        acquired.extend(result)

    check_stop(ctx.stop_event)
    ctx.ctrl.click(*skill_pos)  # 快进一下
    return acquired


# ═══════════════════════════════════════════════════════════════════════════════
# 选船列表 DLL 行定位 + OCR — 委托给公用模块
# ═══════════════════════════════════════════════════════════════════════════════
# 保持向后兼容：从公用模块重新导出，决战内部原有调用者无需改动。
