"""选船列表 DLL 行定位 + OCR 识别。

从 ``autowsgr.ui.decisive.fleet_ocr`` 中提取的公用函数，
普通出征换船和决战换船均可使用。
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import cv2

from autowsgr.constants import SHIPNAMES
from autowsgr.infra.logger import get_logger
from autowsgr.types import ShipType
from autowsgr.vision import apply_ship_patches, get_api_dll
from autowsgr.vision.ocr import OCRResult, _fuzzy_match
from autowsgr.vision.ocr_rules import (
    LEVEL_NOISY_PATTERN as _LEVEL_NOISY_PATTERN,
)
from autowsgr.vision.ocr_rules import (
    LEVEL_PATTERN as _LEVEL_PATTERN,
)
from autowsgr.vision.ocr_rules import (
    is_valid_ship_level,
    normalize_level_digits,
)


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

    m = _LEVEL_PATTERN.search(compact)
    if m:
        raw_digits = m.group(1)
        if _noise_char_count(raw_digits) > _MAX_LEVEL_NOISE_CHARS:
            return None, True
        level = _coerce_level_digits(raw_digits)
        if level is not None:
            return level, False

    m2 = _LEVEL_NOISY_PATTERN.search(compact)
    if m2:
        raw_digits = m2.group(1)
        if _noise_char_count(raw_digits) > _MAX_LEVEL_NOISE_CHARS:
            return None, True
        level = _coerce_level_digits(raw_digits)
        if level is not None:
            return level, False

    return None, False


def _noise_char_count(raw_digits: str) -> int:
    return sum(1 for ch in raw_digits if ch in 'ILilOo')


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


def _center_x(bbox: tuple[int, int, int, int] | None, width: int) -> float:
    if bbox is None:
        return width / 2
    x1, _, x2, _ = bbox
    return (x1 + x2) / 2


def _probe_level_near_name(
    ocr: OCREngine,
    screen: np.ndarray,
    *,
    y_start: int,
    y_end: int,
    name_x: float,
    max_x: int,
) -> int | None:
    """在同一 y 行按舰名 x 位置裁剪区域，二次识别等级。"""
    h, w = screen.shape[:2]
    row_h = max(1, y_end - y_start)

    x_pad = max(70, int(w * 0.045))
    x0 = max(0, int(name_x - x_pad))
    x1 = min(max_x, int(name_x + x_pad))

    y0 = max(0, y_start - int(row_h * 1.6))
    y1 = min(h, y_end + int(row_h * 0.4))

    if x1 <= x0 or y1 <= y0:
        return None

    roi = screen[y0:y1, x0:x1]
    if roi.size == 0:
        return None

    parsed_levels: list[int] = []
    noisy_level_hits = 0

    def collect_levels(img: np.ndarray) -> None:
        nonlocal noisy_level_hits
        results = ocr.recognize(img, allowlist='LlVvIiYy0Oo1.:-/0123456789')
        split_level_hits: list[int] = []
        for r in results:
            text = r.text.strip()
            split_level = _parse_bare_level(text, r.confidence)
            if not text:
                continue
            level, need_retry = _parse_level_with_status(text)
            if need_retry:
                noisy_level_hits += 1
                continue
            if level is not None:
                parsed_levels.append(level)
            elif split_level is not None:
                split_level_hits.append(split_level)

        # 当前 ROI 只覆盖一艘船的紧凑等级区域，高置信度数字不强制带 Lv.。
        parsed_levels.extend(split_level_hits)

    collect_levels(roi)

    gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
    up = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    norm = cv2.normalize(up, None, 0, 255, cv2.NORM_MINMAX)
    binary = cv2.threshold(norm, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    binary_rgb = cv2.cvtColor(binary, cv2.COLOR_GRAY2RGB)
    collect_levels(binary_rgb)

    if not parsed_levels and noisy_level_hits > _MAX_NOISY_LEVEL_HITS_BEFORE_RETRY:
        raise LevelOCRRetryNeededError(
            f'等级 OCR 噪声过高: {noisy_level_hits} 条异常等级文本 (阈值 {_MAX_NOISY_LEVEL_HITS_BEFORE_RETRY})',
        )

    if not parsed_levels:
        return None

    return max(parsed_levels)


def read_ship_levels(  # noqa: PLR0912
    ocr: OCREngine,
    screen: np.ndarray,
    *,
    deduplicate_by_name: bool = True,
    include_row_key: bool = False,
) -> list[tuple[str, int | None] | tuple[str, int | None, float]]:
    """在选船列表页识别各舰船的名称及等级。

    使用与 :func:`locate_ship_rows` 相同的 DLL 行定位 + OCR 流程,
    额外解析每行中的 ``Lv.XX`` 等级文本。

    参考 legacy ``Fleet.check_level`` 的思路, 但适配选船列表的
    动态行布局 (由 DLL 定位) 而非固定槽位坐标。

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
    list[tuple[str, int | None] | tuple[str, int | None, float]]
        默认返回 ``(ship_name, level)`` 列表, 按行顺序排列。
        当 ``include_row_key=True`` 时返回
        ``(ship_name, level, row_key)``。
        ``level`` 为 ``None`` 表示未识别到等级。
    """
    h, w = screen.shape[:2]

    bgr_720p, scale_y, _scale_x = to_legacy_format(screen)
    list_720p = bgr_720p[:, :LEGACY_LIST_WIDTH]

    dll = get_api_dll()
    rows = dll.locate(list_720p)
    _log.debug('[选船列表] DLL 定位到 {} 行候选项 (等级识别)', len(rows))

    list_w_native = int(w * LEGACY_LIST_WIDTH / LEGACY_WIDTH)
    list_area_native = screen[:, :list_w_native]

    found: list[tuple[str, int | None] | tuple[str, int | None, float]] = []
    seen: set[str] = set()
    for y_start_720, y_end_720 in rows:
        y_start = max(0, int((y_start_720 - 1) * scale_y))
        y_end = min(h, int((y_end_720 + 1) * scale_y))
        row_key = round((y_start + y_end) / 2 / h, 4)

        row_img = list_area_native[y_start:y_end]
        results = ocr.recognize(row_img)

        name_hits = [
            (name, _center_x(result.bbox, row_img.shape[1]))
            for result, name in _match_ship_results(results)
        ]
        local_level_hits: list[tuple[int, float]] = []

        for r in results:
            text = r.text.strip()
            if not text:
                continue

            x_center = _center_x(r.bbox, row_img.shape[1])

            level = _parse_level(text)
            if level is not None:
                local_level_hits.append((level, x_center))

        # 等级约束路径也仅在原图舰名失败时执行一次 2x 放大。
        if not name_hits:
            upscaled = cv2.resize(
                row_img,
                None,
                fx=2,
                fy=2,
                interpolation=cv2.INTER_CUBIC,
            )
            upscaled_results = ocr.recognize(upscaled)
            name_hits = [
                (name, _center_x(result.bbox, upscaled.shape[1]) / 2)
                for result, name in _match_ship_results(upscaled_results)
            ]
            if not name_hits:
                continue

        name_hits.sort(key=lambda item: item[1])
        local_level_hits.sort(key=lambda item: item[1])
        max_pair_dist = max(80.0, row_img.shape[1] * 0.12)

        for row_name, name_x in name_hits:
            if deduplicate_by_name and row_name in seen:
                continue

            row_level: int | None = None

            best_level: int | None = None
            best_dist = float('inf')
            for candidate_level, candidate_x in local_level_hits:
                dist = abs(candidate_x - name_x)
                if dist < best_dist:
                    best_dist = dist
                    best_level = candidate_level

            if best_level is not None and best_dist <= max_pair_dist:
                row_level = best_level

            if row_level is None:
                probe_level = _probe_level_near_name(
                    ocr,
                    screen,
                    y_start=y_start,
                    y_end=y_end,
                    name_x=name_x,
                    max_x=list_w_native,
                )
                if probe_level is not None:
                    row_level = probe_level

            if deduplicate_by_name:
                seen.add(row_name)
            _log.debug(
                '[选船列表] 等级识别命中: name={} level={} row_key={}',
                row_name,
                row_level if row_level is not None else 'None',
                row_key,
            )
            if include_row_key:
                found.append((row_name, row_level, row_key))
            else:
                found.append((row_name, row_level))

    _log.debug(
        '[选船列表] 等级识别: {}',
        [(entry[0], entry[1]) for entry in found],
    )
    return found
