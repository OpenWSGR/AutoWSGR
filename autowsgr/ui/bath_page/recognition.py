"""修理页面舰船卡片识别。

从选择修理 overlay 截图中提取所有完整可见的舰船卡片，
通过 OCR 识别舰船名称和修理时间。

核心流程:

1. 灰度 + 二值化提取明亮边框
2. 轮廓检测找到卡片矩形
3. ``is_fully_visible`` 过滤边缘截断/不完整卡片
4. 对每张有效卡片的下半部分做 OCR，按 y 位置区分名称和时间
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import cv2

from autowsgr.constants import SHIPNAMES
from autowsgr.infra.logger import get_logger
from autowsgr.ui.bath_page.page import RepairShipInfo
from autowsgr.vision.ocr import _fuzzy_match


if TYPE_CHECKING:
    import numpy as np

    from autowsgr.vision.ocr import OCREngine

_log = get_logger('ui.bath_page.recognition')

# ── 卡片检测参数 ──────────────────────────────────────────────────────

_CARD_MIN_W = 150
"""卡片最小宽度 (像素)。"""

_CARD_MAX_W = 250
"""卡片最大宽度 (像素)。"""

_CARD_MIN_H = 400
"""卡片最小高度 (像素)。"""

_CARD_MAX_H = 600
"""卡片最大高度 (像素)。"""

_FULL_CARD_WIDTH = 174
"""标准完整卡片宽度 (像素, 1280x720 分辨率下)。"""

_FULL_CARD_WIDTH_RATIO = 0.9
"""卡片宽度低于标准宽度的此比例时视为截断。"""

_BORDER_THRESHOLD = 220
"""灰度二值化阈值，用于提取明亮卡片边框。"""

_EDGE_MARGIN = 5
"""卡片左/右边缘距图片边界的最小像素距离。"""

# ── OCR 位置参数 (相对于卡片下半部分的 y 坐标) ────────────────────────

_NAME_Y_MIN = 118
"""名称文本 y 坐标下限 (相对于卡片下半部分)。

实测名称 mid_y 约 134, 属性数值 mid_y 约 110, 此下限排除属性数值行。
"""

_NAME_Y_MAX = 150
"""名称文本 y 坐标上限 (相对于卡片下半部分)。

名称 mid_y 约 134，级别描述 mid_y 约 155，此上限排除级别描述。
"""

_NAME_CONF_MIN = 0.1
"""名称 OCR 置信度下限。低于此值的识别结果不可信。"""

_TIME_Y_MIN = 200
"""时间文本 y 坐标下限 (相对于卡片下半部分)。"""

_TIME_CROP_Y = 195
"""时间区域裁剪起始 y 坐标 (相对于卡片下半部分)。"""

_TIME_SCALE = 2
"""时间区域 OCR 前的放大倍数，提升数字识别精度。"""

_TIME_PATTERN = re.compile(r'\d{2}:\d{2}:\d{2}')
"""修理时间格式: HH:MM:SS。"""


def is_fully_visible(
    x: int,
    w: int,
    img_width: int,
    *,
    min_width: int = _FULL_CARD_WIDTH,
    width_ratio: float = _FULL_CARD_WIDTH_RATIO,
    edge_margin: int = _EDGE_MARGIN,
) -> bool:
    """判断卡片矩形是否完全可见 (未被图片边缘截断)。

    Parameters
    ----------
    x:
        卡片左边缘 x 坐标。
    w:
        卡片宽度。
    img_width:
        图片总宽度。
    min_width:
        标准完整卡片宽度参考值。
    width_ratio:
        宽度低于 ``min_width * width_ratio`` 时视为截断。
    edge_margin:
        左/右边缘距图片边界的最小像素距离。
    """
    if x < edge_margin:
        return False
    if x + w > img_width - edge_margin:
        return False
    return w >= min_width * width_ratio


def _detect_card_rects(image: np.ndarray) -> list[tuple[int, int, int, int]]:
    """从截图中检测所有卡片矩形区域。

    Returns
    -------
    list[tuple[int, int, int, int]]
        按 x 坐标排序的 ``(x, y, w, h)`` 列表。
    """
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    _, thresh = cv2.threshold(gray, _BORDER_THRESHOLD, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    cards: list[tuple[int, int, int, int]] = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if _CARD_MIN_W < w < _CARD_MAX_W and _CARD_MIN_H < h < _CARD_MAX_H:
            cards.append((x, y, w, h))

    cards.sort(key=lambda r: r[0])
    return cards


def _normalize_time(raw: str) -> str:
    """将 OCR 原始时间文本标准化为 HH:MM:SS 格式。

    EasyOCR 常将 ``:`` 识别为 ``;`` 、 ``,`` 或 ``.``，需统一替换。
    """
    t = raw.replace('耗时', '').replace(' ', '')
    t = t.replace(';', ':').replace(',', ':').replace('.', ':')
    t = t.strip(':')
    # 去除非数字和冒号字符
    t = ''.join(c for c in t if c.isdigit() or c == ':')
    # 合并连续冒号
    while '::' in t:
        t = t.replace('::', ':')
    m = _TIME_PATTERN.search(t)
    if m:
        return m.group(0)
    # 补救: OCR 可能丢失冒号，如 "005609" -> "00:56:09"
    digits = ''.join(c for c in t if c.isdigit())
    if len(digits) == 6:
        return f'{digits[0:2]}:{digits[2:4]}:{digits[4:6]}'
    return t


def _ocr_card(
    card_img: np.ndarray,
    ocr: OCREngine,
    card_x: float,
    card_w: float,
    img_width: int,
) -> RepairShipInfo | None:
    """对单张卡片做 OCR，提取名称和修理时间。

    Parameters
    ----------
    card_img:
        卡片区域图像 (RGB)。
    ocr:
        OCR 引擎实例。
    card_x:
        卡片在原图中的 x 坐标 (用于计算点击位置)。
    card_w:
        卡片宽度。
    img_width:
        原图宽度。

    Returns
    -------
    RepairShipInfo | None
        识别到的舰船信息，OCR 完全失败时返回 None。
    """
    ch = card_img.shape[0]
    half_y = ch // 2
    bottom = card_img[half_y:, :]

    # ── 名称识别: 在原始图像上进行 ──
    results = ocr.recognize(bottom)

    name: str | None = None

    for r in results:
        if r.bbox is None:
            continue
        mid_y = (r.bbox[1] + r.bbox[3]) / 2

        # 名称区域: 直接对已识别文本做模糊匹配
        if _NAME_Y_MIN < mid_y < _NAME_Y_MAX:
            text = r.text.strip()
            if text and name is None and r.confidence >= _NAME_CONF_MIN:
                matched = _fuzzy_match(text, SHIPNAMES, threshold=3)
                if matched:
                    name = matched

    # ── 时间识别: 裁剪时间区域并 2x 放大 ──
    time_roi = bottom[_TIME_CROP_Y:, :]
    trh, trw = time_roi.shape[:2]
    scaled = cv2.resize(
        time_roi,
        (trw * _TIME_SCALE, trh * _TIME_SCALE),
        interpolation=cv2.INTER_CUBIC,
    )
    time_results = ocr.recognize(scaled)

    time_text: str = ''
    for r in time_results:
        if r.bbox is None:
            continue
        txt = r.text
        if '耗时' in txt or ':' in txt or ';' in txt or '.' in txt:
            normalized = _normalize_time(txt)
            if _TIME_PATTERN.match(normalized):
                time_text = normalized
                break

    if name is None and time_text == '':
        return None

    # 计算卡片中心点的相对坐标 (用于点击)
    rel_x = (card_x + card_w / 2) / img_width
    rel_y = 0.5  # 点击卡片中心

    return RepairShipInfo(
        name=name or '',
        position=(rel_x, rel_y),
        repair_time=time_text,
    )


def recognize_repair_cards(
    screen: np.ndarray,
    ocr: OCREngine,
) -> list[RepairShipInfo]:
    """从选择修理 overlay 截图中识别所有完整可见的舰船卡片。

    Parameters
    ----------
    screen:
        截图 (HxWx3, RGB)。
    ocr:
        OCR 引擎实例。

    Returns
    -------
    list[RepairShipInfo]
        按从左到右顺序排列的舰船信息列表，仅包含完整可见的卡片。
    """
    _h, w = screen.shape[:2]
    # 检测时使用 BGR (cv2 默认)，但输入是 RGB
    bgr = cv2.cvtColor(screen, cv2.COLOR_RGB2BGR)
    cards = _detect_card_rects(bgr)

    _log.debug('[修理识别] 检测到 {} 张卡片矩形', len(cards))

    result: list[RepairShipInfo] = []
    for x, y, cw, ch in cards:
        if not is_fully_visible(x, cw, w):
            _log.debug('[修理识别] 跳过截断卡片: x={} w={}', x, cw)
            continue

        card_img = screen[y : y + ch, x : x + cw]
        try:
            info = _ocr_card(card_img, ocr, x, cw, w)
        except Exception:
            _log.opt(exception=True).warning('[修理识别] OCR 失败: 卡片 x={} w={}', x, cw)
            continue

        if info is not None:
            result.append(info)
            _log.debug(
                '[修理识别] 识别成功: name={} time={}',
                info.name,
                info.repair_time,
            )

    _log.info('[修理识别] 共识别 {}/{} 张有效卡片', len(result), len(cards))
    return result
