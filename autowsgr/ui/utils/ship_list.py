"""选船列表 DLL 行定位 + OCR 识别。

从 ``autowsgr.ui.decisive.fleet_ocr`` 中提取的公用函数，
普通出征换船和决战换船均可使用。
"""

from __future__ import annotations

import math
import re
from typing import TYPE_CHECKING

import cv2

from autowsgr.constants import SHIPNAMES
from autowsgr.infra.logger import get_logger
from autowsgr.types import ShipType
from autowsgr.vision import apply_ship_patches, get_api_dll
from autowsgr.vision.ocr import EasyOCREngine, OCRResult, _fuzzy_match
from autowsgr.vision.ocr_rules import (
    LEVEL_DIGIT_CONFUSABLES,
    EasyOCRProfile,
    is_valid_ship_level,
    normalize_level_digits,
)
from autowsgr.vision.ocr_rules import (
    LEVEL_NOISY_PATTERN as _LEVEL_NOISY_PATTERN,
)
from autowsgr.vision.ocr_rules import LEVEL_PATTERN as _LEVEL_PATTERN
from autowsgr.vision.ocr_rules import LEVEL_SHORT_PATTERN as _LEVEL_SHORT_PATTERN


if TYPE_CHECKING:
    import numpy as np

    from autowsgr.vision import OCREngine


_log = get_logger('ui')

LEGACY_WIDTH: int = 1280
LEGACY_HEIGHT: int = 720

#: Legacy 选船列表左侧裁剪宽度 (px@1280)
LEGACY_LIST_WIDTH: int = 1048

# 110 在 720p 下常被识别为 ``Il0`` / ``ll0``，其中两个 1 都会成为易混淆字符。
_MAX_LEVEL_NOISE_CHARS = 2
_MAX_NOISY_LEVEL_HITS_BEFORE_RETRY = 5
_MIN_SPLIT_LEVEL_CONFIDENCE = 0.85
_SHIP_LEVEL_CROP_OFFSETS = (-62, -38, -2, -20)
_SHIP_LEVEL_OCR_SCALES = (2, 3, 4)


def extract_ship_type_from_text(text: str) -> ShipType | None:
    """从 OCR 文本中提取舰种。

    游戏内舰种文字常带阵营括号，如 ``轻巡(J国)`` / ``潜艇(G国)``，
    先剔除括号及括号内内容 (国家缩写) 再匹配，避免干扰。
    准备页快照与选船页单卡识别共用此函数。
    """
    if not text:
        return None
    normalized = re.sub(r'[（(][^（()）]*[)）]', '', text).replace(' ', '')
    for ship_type in ShipType:
        if ship_type is not ShipType.Other and ship_type.value in normalized:
            return ship_type
    return None


class LevelOCRRetryNeededError(RuntimeError):
    """等级 OCR 噪声过高，需要重新截图识别。"""


def to_legacy_format(screen: np.ndarray) -> tuple[np.ndarray, float, float]:
    """将 V2 截图转为 DLL 所需的 legacy 格式。

    DLL 内部基于 1280x720 BGR 图像校准，V2 ``screenshot()``
    返回模拟器原生分辨率的 RGB 图像，需做两步转换。

    Returns
    -------
    tuple[np.ndarray, float, float]
        ``(bgr_720p, scale_y, scale_x)``
        -- bgr_720p: 1280x720 BGR 图像
        -- scale_y / scale_x: legacy 坐标 -> 原始坐标的缩放比
    """
    h, w = screen.shape[:2]
    scale_y = h / LEGACY_HEIGHT
    scale_x = w / LEGACY_WIDTH
    resized = cv2.resize(screen, (LEGACY_WIDTH, LEGACY_HEIGHT))
    bgr = cv2.cvtColor(resized, cv2.COLOR_RGB2BGR)
    return bgr, scale_y, scale_x


def _match_ship_results(results: list[OCRResult]) -> list[tuple[OCRResult, str]]:
    """返回 OCR 结果中能够安全映射到唯一标准舰名的项目。"""
    matches: list[tuple[OCRResult, str]] = []
    for result in results:
        text = result.text.strip()
        if not text:
            continue
        name = _fuzzy_match(apply_ship_patches(text), SHIPNAMES)
        if name is not None:
            matches.append((result, name))
    return matches


def locate_ship_rows(
    ocr: OCREngine,
    screen: np.ndarray,
    *,
    deduplicate_by_name: bool = True,
    include_row_key: bool = False,
) -> list[tuple[str, float, float] | tuple[str, float, float, float]]:
    """在选船列表页用 DLL 定位舰船名行，再逐行 OCR 识别。

    其他场景 (如 ``_click_ship_in_list``, ``recognize_ships_in_list``)
    应复用此函数而非重复实现 OCR 逻辑。

    对齐 legacy ``recognize_ship``:

    1. resize + RGB->BGR 转为 1280x720 BGR (DLL 校准基准)
    2. 裁剪左侧 1048px (与 legacy ``screen[:, :1048]`` 一致)
    3. ``dll.locate()`` 定位行区域
    4. 将行坐标映射回原始分辨率, 在原图上裁剪并 OCR

    Parameters
    ----------
    ocr:
        OCR 引擎实例。
    screen:
        选船列表页面的 V2 截图 (RGB, 任意分辨率)。
    deduplicate_by_name:
        是否按舰船名去重。默认 ``True`` 以保持兼容。
        在同名多行场景下可设为 ``False`` 保留全部命中。
    include_row_key:
        是否在返回值中附带行标识 (row_key)。默认 ``False``。

    Returns
    -------
    list[tuple[str, float, float] | tuple[str, float, float, float]]
        默认返回 ``(ship_name, cx_rel, cy_rel)``。
        当 ``include_row_key=True`` 时返回
        ``(ship_name, cx_rel, cy_rel, row_key)``。
        ``row_key`` 用于与等级识别结果做行级关联。
    """
    h, w = screen.shape[:2]

    # 转为 legacy 格式 (1280x720, BGR)
    bgr_720p, scale_y, _scale_x = to_legacy_format(screen)
    list_720p = bgr_720p[:, :LEGACY_LIST_WIDTH]  # legacy 裁剪宽度

    dll = get_api_dll()
    rows = dll.locate(list_720p)
    _log.debug('[选船列表] DLL 定位到 {} 行候选项', len(rows))

    # 在原始分辨率上裁剪并 OCR (用原图的左 82% 区域)
    list_w_native = int(w * LEGACY_LIST_WIDTH / LEGACY_WIDTH)
    list_area_native = screen[:, :list_w_native]

    found: list[tuple[str, float, float] | tuple[str, float, float, float]] = []
    seen: set[str] = set()
    for y_start_720, y_end_720 in rows:
        # 将 720p 坐标映射回原始分辨率
        y_start = max(0, int((y_start_720 - 1) * scale_y))
        y_end = min(h, int((y_end_720 + 1) * scale_y))

        row_img = list_area_native[y_start:y_end]

        # 对齐 legacy: recognize(multiple=True) -- 同一 DLL 行可含多个舰船名
        results = ocr.recognize(row_img)
        matched_results = _match_ship_results(results)
        upscaled_results: list[OCRResult] = []
        result_scale = 1.0

        # 原图没有可靠舰名时才放大重试，避免增加正常识别路径的耗时。
        if not matched_results:
            upscaled = cv2.resize(
                row_img,
                None,
                fx=2,
                fy=2,
                interpolation=cv2.INTER_CUBIC,
            )
            upscaled_results = ocr.recognize(upscaled)
            matched_results = _match_ship_results(upscaled_results)
            result_scale = 2.0

        _log.debug(
            '[选船列表] 舰名OCR原始及后处理: row={} raw={} upscaled={} matched={}',
            (y_start_720, y_end_720),
            results,
            upscaled_results,
            [name for _, name in matched_results],
        )
        for r, name in matched_results:
            if deduplicate_by_name and name in seen:
                continue
            if deduplicate_by_name:
                seen.add(name)
            # 从 bbox 计算精确位置 (bbox 相对于 row_img)
            if r.bbox is not None:
                x1, y1, x2, y2 = r.bbox
                cx = (x1 + x2) / 2 / result_scale / w
                cy = (y_start + (y1 + y2) / 2 / result_scale) / h
            else:
                cx = list_w_native / 2 / w
                cy = (y_start + y_end) / 2 / h
            row_key = round((y_start + y_end) / 2 / h, 4)
            if include_row_key:
                found.append((name, cx, cy, row_key))
            else:
                found.append((name, cx, cy))

    _log.debug(
        '[选船列表] 识别: {} (共 {} 行)',
        sorted({entry[0] for entry in found}),
        len(rows),
    )
    return found


def recognize_ships_in_list(
    ocr: OCREngine,
    screen: np.ndarray,
) -> set[str]:
    """识别选船列表页面中的所有可见舰船名 (去重集合)。

    基于 :func:`locate_ship_rows` 的薄封装。
    """
    return {entry[0] for entry in locate_ship_rows(ocr, screen)}


def _parse_level(text: str) -> int | None:
    """从 OCR 文本中提取 ``Lv.XX`` 格式等级数字。"""
    level, _need_retry = _parse_level_with_status(text)
    return level


def _parse_level_with_status(text: str) -> tuple[int | None, bool]:
    """解析等级并返回是否应触发重识别。"""
    compact = text.strip().replace(' ', '')

    for pattern in (_LEVEL_PATTERN, _LEVEL_NOISY_PATTERN, _LEVEL_SHORT_PATTERN):
        match = pattern.search(compact)
        if match is None:
            continue
        raw_digits = match.group(1)
        if _noise_char_count(raw_digits) > _MAX_LEVEL_NOISE_CHARS:
            return None, True
        level = _coerce_level_digits(raw_digits)
        if level is not None:
            return level, False

    return None, False


def _noise_char_count(raw_digits: str) -> int:
    return sum(1 for ch in raw_digits if ch in LEVEL_DIGIT_CONFUSABLES)


def _coerce_level_digits(raw_digits: str) -> int | None:
    """将 OCR 提取出的数字串映射为合法等级值。"""
    digits = normalize_level_digits(raw_digits)
    if digits is None:
        return None

    # 兼容前导 0 的场景（如 051 -> 51）
    if digits.startswith('0') and len(digits) >= 3:
        value = int(digits[1:3])
        return value if is_valid_ship_level(value) else None

    # 三位以上只读取前三位；超过 110 时不再降级猜成两位等级。
    value = int(digits[:3] if len(digits) >= 3 else digits)
    return value if is_valid_ship_level(value) else None


def _parse_bare_level(text: str, confidence: float) -> int | None:
    """解析等级 ROI 中与 ``Lv.`` 标签分离的高置信度纯数字。"""
    candidate = text.removeprefix('.')
    if confidence < _MIN_SPLIT_LEVEL_CONFIDENCE:
        return None
    digits = normalize_level_digits(candidate)
    if digits is None:
        return None
    value = int(digits)
    return value if is_valid_ship_level(value) else None


def _probe_level_near_name(
    ocr: OCREngine,
    screen: np.ndarray,
    *,
    y_start: int,
    y_end: int,
    name_x: float,
    max_x: int,
) -> int | None:
    """以舰名和 DLL 行中心为锚点，顺序识别同一卡片的等级。"""
    h, w = screen.shape[:2]
    row_y = (y_start + y_end) / 2
    left, top, right, bottom = _SHIP_LEVEL_CROP_OFFSETS
    x1 = max(0.0, min(float(max_x), name_x + left * w / LEGACY_WIDTH))
    x2 = max(0.0, min(float(max_x), name_x + right * w / LEGACY_WIDTH))
    y1 = max(0.0, min(float(h), row_y + top * h / LEGACY_HEIGHT))
    y2 = max(0.0, min(float(h), row_y + bottom * h / LEGACY_HEIGHT))
    if x2 <= x1 or y2 <= y1:
        return None

    source_x1 = math.floor(x1)
    source_x2 = math.ceil(x2)
    source_y1 = math.floor(y1)
    source_y2 = math.ceil(y2)
    source_crop = screen[source_y1:source_y2, source_x1:source_x2]
    if source_crop.size == 0:
        return None

    noisy_level_hits = 0
    use_otsu = isinstance(ocr, EasyOCREngine)

    for scale in _SHIP_LEVEL_OCR_SCALES:
        enlarged_source = cv2.resize(
            source_crop,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC,
        )
        crop_x1 = round((x1 - source_x1) * scale)
        crop_x2 = round((x2 - source_x1) * scale)
        crop_y1 = round((y1 - source_y1) * scale)
        crop_y2 = round((y2 - source_y1) * scale)
        enlarged = enlarged_source[crop_y1:crop_y2, crop_x1:crop_x2]
        if enlarged.size == 0:
            continue

        prepared = enlarged
        if use_otsu:
            gray = cv2.cvtColor(enlarged, cv2.COLOR_RGB2GRAY)
            binary = cv2.threshold(
                gray,
                0,
                255,
                cv2.THRESH_BINARY + cv2.THRESH_OTSU,
            )[1]
            prepared = cv2.cvtColor(binary, cv2.COLOR_GRAY2RGB)

        results = ocr.recognize_line(
            prepared,
            easyocr_profile=EasyOCRProfile.SHIP_POOL_LEVEL,
        )
        parsed_levels: list[int] = []
        split_level_hits: list[int] = []
        for result in results:
            text = result.text.strip()
            if not text:
                continue
            split_level = _parse_bare_level(text, result.confidence)
            level, need_retry = _parse_level_with_status(text)
            if need_retry:
                noisy_level_hits += 1
                continue
            if level is not None:
                parsed_levels.append(level)
            elif split_level is not None:
                split_level_hits.append(split_level)

        parsed_levels.extend(split_level_hits)
        raw_results = [
            {
                'text': result.text,
                'confidence': result.confidence,
                'bbox': result.bbox,
            }
            for result in results
        ]
        _log.debug(
            '[选船列表] 等级OCR原始及后处理: scale={} name_x={} raw={} parsed={} noisy_hits={}',
            scale,
            name_x,
            raw_results,
            parsed_levels,
            noisy_level_hits,
        )
        if parsed_levels:
            return max(parsed_levels)

    if noisy_level_hits > _MAX_NOISY_LEVEL_HITS_BEFORE_RETRY:
        raise LevelOCRRetryNeededError(
            f'等级 OCR 噪声过高: {noisy_level_hits} 条异常等级文本 (阈值 {_MAX_NOISY_LEVEL_HITS_BEFORE_RETRY})',
        )

    return None


def read_ship_level_at_card(
    ocr: OCREngine,
    screen: np.ndarray,
    *,
    card_x: float,
    row_key: float,
) -> int | None:
    """根据已定位船卡的舰名中心和行中心识别等级。"""
    h, w = screen.shape[:2]
    row_y = round(row_key * h)
    list_w_native = int(w * LEGACY_LIST_WIDTH / LEGACY_WIDTH)
    return _probe_level_near_name(
        ocr,
        screen,
        y_start=row_y,
        y_end=row_y,
        name_x=card_x * w,
        max_x=list_w_native,
    )
