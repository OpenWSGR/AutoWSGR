"""任务页面识别 - 按钮扫描、OCR 识别、模糊匹配。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.ui.mission_page.data import (
    BUTTON_SCAN_ROI,
    CLAIM_B_MAX,
    CLAIM_G_MIN,
    CLAIM_R_MIN,
    CLUSTER_GAP,
    GOTO_COLOR,
    GOTO_TOLERANCE,
    MIN_CLUSTER_SIZE,
    NAME_CROP_MIN_Y,
    NAME_ROI_X1,
    NAME_ROI_X2,
    NAME_ROI_Y_PAD,
    NAME_Y_OFFSET,
    OCR_CONFIDENCE_MIN,
    PROGRESS_RE,
    PROGRESS_ROI_X1,
    PROGRESS_ROI_X2,
    PROGRESS_ROI_Y_PAD,
    PROGRESS_Y_OFFSET,
    SCAN_X,
    SCAN_Y_STEP,
    WIDE_BTN_CHECK_X,
    ButtonType,
    MissionInfo,
)
from autowsgr.vision import PixelChecker
from autowsgr.vision.roi import ROI


if TYPE_CHECKING:
    import numpy as np

    from autowsgr.vision import OCREngine
    from autowsgr.vision.pixel import Color


# ═══════════════════════════════════════════════════════════════════════════════
# 像素扫描
# ═══════════════════════════════════════════════════════════════════════════════


def _is_goto_color(c: Color) -> bool:
    return c.near(GOTO_COLOR, GOTO_TOLERANCE)


def _is_claim_color(c: Color) -> bool:
    return c.r >= CLAIM_R_MIN and c.g >= CLAIM_G_MIN and c.b <= CLAIM_B_MAX


def find_button_rows(screen: np.ndarray) -> list[tuple[float, ButtonType]]:
    """扫描截图右侧, 定位所有 "前往"/"领取" 按钮行。

    Returns
    -------
    list[tuple[float, ButtonType]]
        每个元素为 (y_center_relative, button_type), 按 y 从上到下排列。
    """
    y_start = BUTTON_SCAN_ROI.y1
    y_end = BUTTON_SCAN_ROI.y2

    # 收集所有匹配像素的 (y, type)
    hits: list[tuple[float, ButtonType]] = []
    y = y_start
    while y <= y_end:
        c = PixelChecker.get_pixel(screen, SCAN_X, y)
        if _is_goto_color(c):
            hits.append((y, ButtonType.GOTO))
        elif _is_claim_color(c):
            hits.append((y, ButtonType.CLAIM))
        y += SCAN_Y_STEP

    if not hits:
        return []

    # 聚类: 连续同类型像素归为一组
    clusters: list[list[tuple[float, ButtonType]]] = [[hits[0]]]
    for h in hits[1:]:
        prev = clusters[-1][-1]
        if h[0] - prev[0] < CLUSTER_GAP and h[1] == prev[1]:
            clusters[-1].append(h)
        else:
            clusters.append([h])

    # 取每个簇的中心 y 和类型, 过滤过小的簇 (噪点)
    result: list[tuple[float, ButtonType]] = []
    for cluster in clusters:
        if len(cluster) < MIN_CLUSTER_SIZE:
            continue
        ys = [p[0] for p in cluster]
        y_center = (min(ys) + max(ys)) / 2
        btn_type = cluster[0][1]
        result.append((y_center, btn_type))

    # 过滤底部 "一键领取" 按钮: 它的金色区域横向延伸到 x=0.80,
    # 而任务行按钮仅在 x=0.86-0.96 范围内
    filtered: list[tuple[float, ButtonType]] = []
    for y_center, btn_type in result:
        c_wide = PixelChecker.get_pixel(screen, WIDE_BTN_CHECK_X, y_center)
        if _is_goto_color(c_wide) or _is_claim_color(c_wide):
            continue  # 宽按钮 (UI 元素), 跳过
        # 过滤部分可见行: 名称裁切区域被页面标题栏遮挡
        name_top = y_center + NAME_Y_OFFSET - NAME_ROI_Y_PAD
        if name_top < NAME_CROP_MIN_Y:
            continue
        filtered.append((y_center, btn_type))

    return filtered


# ═══════════════════════════════════════════════════════════════════════════════
# OCR + 匹配
# ═══════════════════════════════════════════════════════════════════════════════


def recognize_row(
    screen: np.ndarray,
    anchor_y: float,
    btn_type: ButtonType,
    ocr: OCREngine,
    candidates: list[str],
) -> MissionInfo | None:
    """识别单行任务。返回 None 表示无效行 (部分可见/垃圾 OCR)。"""
    name_y = anchor_y + NAME_Y_OFFSET
    prog_y = anchor_y + PROGRESS_Y_OFFSET

    # -- 裁切名称区域并 OCR --
    name_roi = ROI(
        NAME_ROI_X1,
        max(0.0, name_y - NAME_ROI_Y_PAD),
        NAME_ROI_X2,
        min(1.0, name_y + NAME_ROI_Y_PAD),
    )
    name_img = name_roi.crop(screen)
    name_result = ocr.recognize_single(name_img)
    raw_text = name_result.text.strip()
    confidence = name_result.confidence

    # -- OCR 置信度过滤: 拒绝垃圾识别 (部分可见任务行) --
    if confidence < OCR_CONFIDENCE_MIN:
        return None

    # -- 模糊匹配数据库 --
    matched_name = match_mission_name(raw_text, candidates)
    final_name = matched_name or raw_text

    # -- 裁切进度区域并 OCR --
    prog_roi = ROI(
        PROGRESS_ROI_X1,
        max(0.0, prog_y - PROGRESS_ROI_Y_PAD),
        PROGRESS_ROI_X2,
        min(1.0, prog_y + PROGRESS_ROI_Y_PAD),
    )
    prog_img = prog_roi.crop(screen)
    prog_result = ocr.recognize_single(prog_img, allowlist='0123456789%:')
    prog_text = prog_result.text.strip()
    m = PROGRESS_RE.search(prog_text)
    progress = int(m.group(1)) if m else -1

    claimable = btn_type == ButtonType.CLAIM

    return MissionInfo(
        name=final_name,
        raw_text=raw_text,
        progress=progress,
        claimable=claimable,
        confidence=confidence,
    )


def match_mission_name(
    ocr_text: str,
    candidates: list[str],
    threshold: int = 5,
) -> str | None:
    """在任务数据库中模糊匹配任务名。

    策略:
    1. 精确匹配
    2. 子串包含
    3. Levenshtein 距离 <= threshold
    """
    if not ocr_text:
        return None

    # 精确匹配
    for name in candidates:
        if ocr_text == name:
            return name

    # 子串包含: 仅当长度比 >= 70% 时视为有效匹配, 优先最长候选
    substring_hits = [
        name
        for name in candidates
        if (name in ocr_text or ocr_text in name)
        and min(len(name), len(ocr_text)) >= 0.7 * max(len(name), len(ocr_text))
    ]
    if substring_hits:
        return max(substring_hits, key=len)

    # Levenshtein 模糊匹配
    from autowsgr.vision.ocr import _edit_distance

    best_name: str | None = None
    best_dist = threshold + 1
    for name in candidates:
        dist = _edit_distance(ocr_text, name)
        if dist < best_dist:
            best_dist = dist
            best_name = name
    return best_name if best_dist <= threshold else None
