"""决战舰队 OCR 识别模块。

提供决战战备舰队获取界面的 OCR 识别功能，包括：

- 可用分数与费用识别
- 舰船名称识别
- 副官技能使用与舰船扫描

这些函数由 :class:`DecisiveMapController` 委托调用。
"""

from __future__ import annotations

import time

import numpy as np
from loguru import logger

from autowsgr.constants import SHIPNAMES
from autowsgr.emulator import AndroidController
from autowsgr.infra import DecisiveConfig, save_image
from autowsgr.types import FleetSelection
from autowsgr.ui.decisive.overlay import (
    COST_AREA,
    FLEET_CARD_CLICK_Y,
    FLEET_CARD_X_POSITIONS,
    RESOURCE_AREA,
    SHIP_NAME_X_RANGES,
    SHIP_NAME_Y_RANGE,
)
from autowsgr.vision import OCREngine, ROI


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
        x1=RESOURCE_AREA[0][0], y1=RESOURCE_AREA[1][1],
        x2=RESOURCE_AREA[1][0], y2=RESOURCE_AREA[0][1],
    )
    score_img = res_roi.crop(screen)
    score_val = ocr.recognize_number(score_img)
    score = score_val if score_val is not None else 0
    if score_val is not None:
        logger.debug("[舰队OCR] 可用分数: {}", score_val)
    else:
        logger.warning("[舰队OCR] 分数 OCR 失败")

    # 2. 识别费用整行
    cost_roi = ROI(
        x1=COST_AREA[0][0], y1=COST_AREA[1][1],
        x2=COST_AREA[1][0], y2=COST_AREA[0][1],
    )
    cost_img = cost_roi.crop(screen)
    cost_results = ocr.recognize(cost_img, allowlist="0123456789x")

    costs: list[int] = []
    for r in cost_results:
        text = r.text.strip().lstrip("xX")
        try:
            costs.append(int(text))
        except (ValueError, TypeError):
            logger.debug("[舰队OCR] 费用解析跳过: '{}'", r.text)
    logger.debug("[舰队OCR] 识别到 {} 项费用: {}", len(costs), costs)

    # 3. 对可负担的卡识别舰船名
    ship_names = config.level1 + config.level2 + [
        "长跑训练", "肌肉记忆", "黑科技",
    ] + SHIPNAMES
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

        name = ocr.recognize_ship_name(name_img, ship_names)
        if name is None:
            raw = ocr.recognize_single(name_img)
            name = raw.text.strip() if raw.text.strip() else f"未识别_{i}"
            logger.debug("[舰队OCR] 舰船名模糊匹配失败, 原文: '{}'", name)

        click_x = FLEET_CARD_X_POSITIONS[i] if i < len(FLEET_CARD_X_POSITIONS) else 0.5
        click_y = FLEET_CARD_CLICK_Y

        selections[name] = FleetSelection(
            name=name,
            cost=cost,
            click_position=(click_x, click_y),
        )

    logger.info("[舰队OCR] 舰队选项: {}", {k: v.cost for k, v in selections.items()})
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
    ship_names = config.level1 + config.level2 + [
        "长跑训练", "肌肉记忆", "黑科技",
    ] + SHIPNAMES
    return ocr.recognize_ship_name(name_img, ship_names)


def use_skill(
    ctrl: AndroidController,
    ocr: OCREngine,
    config: DecisiveConfig,
) -> list[str]:
    """在地图页使用一次副官技能并返回识别到的舰船。"""
    skill_pos = (0.2143, 0.894)
    ship_area = ROI(x1=0.26, y1=0.685, x2=0.74, y2=0.715)
    candidates = config.level1 + config.level2 + SHIPNAMES

    ctrl.click(*skill_pos)
    time.sleep(0.5)

    screen = ctrl.screenshot()
    crop = ship_area.crop(screen)
    result = ocr.recognize_ship_name(crop, candidates)
    save_image(crop, "skill_result.png")
    acquired: list[str] = []
    if result is not None:
        acquired.append(result)

    ctrl.click(*skill_pos) # 快进一下
    return acquired


def scan_available_ships(
    ctrl: AndroidController,
    ocr: OCREngine,
    config: DecisiveConfig,
) -> set[str]:
    """在出征准备页通过选船列表扫描可用舰船。"""
    from autowsgr.ui.battle.preparation import BattlePreparationPage
    from autowsgr.ui.choose_ship_page import ChooseShipPage

    page = BattlePreparationPage(ctrl, ocr)
    page.click_ship_slot(0)
    time.sleep(1.0)

    screen = ctrl.screenshot()
    h, w = screen.shape[:2]
    left = screen[:, : int(w * 0.82)]

    candidates = config.level1 + config.level2 + SHIPNAMES
    ships: set[str] = set(ocr.recognize_ship_names(left, candidates))

    choose_page = ChooseShipPage(ctrl)
    choose_page.dismiss_keyboard()
    ctrl.click(0.05, 0.05)
    time.sleep(1.0)

    return ships
