"""OCR 引擎抽象层。

提供统一的文字识别接口，支持 EasyOCR 和 PaddleOCR 后端。

使用方式::

    from autowsgr.vision import OCREngine

    engine = OCREngine.create("easyocr", gpu=False)
    results = engine.recognize(cropped_image)
    number = engine.recognize_number(resource_area)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import easyocr

from autowsgr.constants import SHIPNAMES
from autowsgr.infra.logger import get_logger


if TYPE_CHECKING:
    import numpy as np


_log = get_logger('vision.ocr')


# ── 结果数据类 ──

REPLACE_RULE: dict[str, str] = {'鲍鱼': '鲃鱼', '296': 'M-296', '维内托': '维托里奥·维内托'}


# ── 舰船名文本补丁管线 ──


def _patch_replace_rule(text: str) -> str:
    """替换已知 OCR 误识别（包含匹配）。"""
    for old, new in REPLACE_RULE.items():
        if old in text:
            return new
    return text


def _patch_submarine_prefix(text: str) -> str:
    """修正潜艇名首字符误识别: 以 0 开头且含 3+ 位数字 -> 首字符改为 U。

    常见误读: U-96 -> 096, U-1206 -> 01206 等。
    """
    if text.startswith('0') and sum(c.isdigit() for c in text) >= 3:
        return 'U' + text[1:]
    return text


SHIP_TEXT_PATCHES = [
    _patch_replace_rule,
    _patch_submarine_prefix,
]
"""舰船名 OCR 文本补丁列表, 按序执行。每个补丁签名: str -> str。"""


def apply_ship_patches(text: str) -> str:
    """依次执行所有舰船名文本补丁。"""
    for patch in SHIP_TEXT_PATCHES:
        text = patch(text)
    return text


@dataclass(frozen=True, slots=True)
class OCRResult:
    """OCR 识别结果。

    Attributes
    ----------
    text:
        识别出的文本。
    confidence:
        置信度 (0.0-1.0)。
    bbox:
        文本区域边界框 (x1, y1, x2, y2)，可能为 None。
    """

    text: str
    confidence: float
    bbox: tuple[int, int, int, int] | None = None


# ── 自定义异常 ──


class ShipNameMismatchError(ValueError):
    """当 OCR 识别到文本但编辑距离超过最大阈值时抛出。

    Attributes
    ----------
    text:
        OCR 识别出的原始文本。
    best_candidate:
        编辑距离最近的候选舰船名。
    distance:
        与 best_candidate 的 Levenshtein 距离。
    max_threshold:
        触发异常的最大编辑距离阈值。
    """

    def __init__(
        self,
        text: str,
        best_candidate: str,
        distance: int,
        max_threshold: int,
    ) -> None:
        self.text = text
        self.best_candidate = best_candidate
        self.distance = distance
        self.max_threshold = max_threshold
        super().__init__(
            f"OCR 识别到 '{text}'，与最近候选 '{best_candidate}' 编辑距离={distance} "
            f'超过最大阈值 {max_threshold}，拒绝匹配'
        )


# ── 抽象基类 ──


class OCREngine(ABC):
    """OCR 引擎抽象基类。

    子类只需实现 :meth:`recognize` 方法。
    高层便捷方法 (recognize_single, recognize_number, recognize_ship_name)
    基于 recognize 构建，无需子类重写。

    Parameters
    ----------
    verbose:
        是否在 DEBUG 级别打印每次识别的细节日志。
        为 False 时改用 TRACE 级别，减少日志噪音。
    """

    verbose: bool = True
    """控制 OCR 详情日志级别 (True → DEBUG, False → TRACE)。"""

    @abstractmethod
    def recognize(
        self,
        image: np.ndarray,
        allowlist: str = '',
    ) -> list[OCRResult]:
        """识别图像中的文字。

        Parameters
        ----------
        image:
            输入图像 (RGB, uint8)。
        allowlist:
            仅允许识别的字符集（空字符串表示不限制）。

        Returns
        -------
        list[OCRResult]
            识别结果列表，按位置排列。
        """
        ...

    # ── 便捷方法 ──

    def recognize_single(
        self,
        image: np.ndarray,
        allowlist: str = '',
    ) -> OCRResult:
        """识别单个文本区域，返回置信度最高的结果。

        无结果时返回空文本、零置信度的 OCRResult。
        """
        results = self.recognize(image, allowlist)
        _log_fn = _log.debug if self.verbose else _log.trace
        if not results:
            _log_fn('[OCR] recognize_single: 无结果')
            return OCRResult(text='', confidence=0.0)
        best = max(results, key=lambda r: r.confidence)
        _log_fn("[OCR] recognize_single: '{}' (conf={:.2f})", best.text, best.confidence)
        return best

    def recognize_number(
        self,
        image: np.ndarray,
        extra_chars: str = '',
    ) -> int | None:
        """识别数字，支持 K/M 后缀。
        不依赖位置信息
        Parameters
        ----------
        image:
            包含数字的图像区域。
        extra_chars:
            除数字外允许的额外字符。

        Returns
        -------
        int | None
            识别出的数字，无法解析时返回 None。
        """
        result = self.recognize_single(image, allowlist='0123456789' + extra_chars)
        text = result.text.strip()
        if not text:
            return None

        # 处理 K / M 后缀
        multiplier = 1
        if text.upper().endswith('K'):
            multiplier = 1000
            text = text[:-1]
        elif text.upper().endswith('M'):
            multiplier = 1_000_000
            text = text[:-1]

        _log_fn = _log.debug if self.verbose else _log.trace
        try:
            value = int(float(text) * multiplier)
            _log_fn("[OCR] recognize_number: '{}' → {}", result.text.strip(), value)
            return value
        except (ValueError, TypeError):
            _log_fn("[OCR] recognize_number: '{}' 解析失败", result.text.strip())
            return None

    def recognize_ship_name(
        self,
        image: np.ndarray,
        candidates: list[str] | None = None,
        threshold: int = 3,
    ) -> str | None:
        """识别舰船名称，模糊匹配到候选列表。
        不依赖位置信息
        Parameters
        ----------
        image:
            舰船名称区域图像。
        candidates:
            候选舰船名列表。为 ``None`` 时使用全局 :data:`SHIPNAMES`。
        threshold:
            编辑距离阈值，超过则不匹配。

        Returns
        -------
        str | None
            匹配到的舰船名，或 None。
        """
        if candidates is None:
            candidates = SHIPNAMES
        result = self.recognize_single(image)
        _log_fn = _log.debug if self.verbose else _log.trace
        if not result.text:
            _log_fn('[OCR] recognize_ship_name: 无文本')
            return None
        raw_text = result.text
        corrected = apply_ship_patches(raw_text)
        if corrected != raw_text:
            _log_fn(
                "[OCR] recognize_ship_name: raw='{}' -> patched='{}'",
                raw_text,
                corrected,
            )
        else:
            _log_fn("[OCR] recognize_ship_name: raw='{}'", raw_text)
        matched = _fuzzy_match(corrected, candidates, threshold)
        _log_fn(
            "[OCR] recognize_ship_name: '{}' -> '{}'",
            raw_text,
            matched or '未匹配',
        )
        return matched

    def recognize_ship_names(
        self,
        image: np.ndarray,
        candidates: list[str] | None = None,
        threshold: int = 3,
        max_threshold: int | None = None,
    ) -> list[str]:
        """识别图像中的多个舰船名，对每个文本区域做模糊匹配与自动校正。
        不依赖位置信息
        与 :meth:`recognize_ship_name` 的区别：本方法调用 :meth:`recognize` 获取
        图像中所有文本区域，再逐一与候选列表做模糊匹配，适合一张图中包
        含多个舰船名的场景。

        Parameters
        ----------
        image:
            包含舰船名的图像。
        candidates:
            候选舰船名列表。为 ``None`` 时使用全局 :data:`SHIPNAMES`。
        threshold:
            编辑距离软阈值：distance ≤ threshold 时接受自动校正后的名称。
        max_threshold:
            最大编辑距离硬阈值：若某段识别文本与所有候选的最小编辑距离
            超过此值，则抛出 :exc:`ShipNameMismatchError`。
            为 ``None`` 时禁用此检查，超阈值的文本仅被静默跳过。

        Returns
        -------
        list[str]
            识别并自动校正后的舰船名列表，按图像中的出现顺序，已去重。

        Raises
        ------
        ShipNameMismatchError
            当某段识别文本与所有候选的编辑距离均超过 max_threshold 时。
        """
        if candidates is None:
            candidates = SHIPNAMES
        results = self.recognize(image)
        _log_fn = _log.debug if self.verbose else _log.trace
        seen: set[str] = set()
        matched: list[str] = []
        for r in results:
            text = r.text.strip()
            if not text:
                continue
            raw_text = text
            text = apply_ship_patches(text)
            if text != raw_text:
                _log_fn(
                    "[OCR] recognize_ship_names: raw='{}' -> patched='{}'",
                    raw_text,
                    text,
                )
            best = _fuzzy_match(text, candidates, threshold)
            if best is not None:
                _log_fn(
                    "[OCR] recognize_ship_names: '{}' -> '{}'",
                    raw_text,
                    best,
                )
                if best not in seen:
                    seen.add(best)
                    matched.append(best)
            else:
                if max_threshold is not None and candidates:
                    best_candidate = min(candidates, key=lambda c: _edit_distance(text, c))
                    dist = _edit_distance(text, best_candidate)
                    if dist > max_threshold:
                        raise ShipNameMismatchError(text, best_candidate, dist, max_threshold)
                _log_fn("[OCR] recognize_ship_names: '{}' 无匹配 (阈值={})，跳过", text, threshold)
        _log_fn('[OCR] recognize_ship_names: 共识别 {} 艘: {}', len(matched), matched)
        return matched

    # ── 工厂方法 ──

    _instances: ClassVar[dict[str, OCREngine]] = {}
    """已创建的引擎单例缓存，key 为 ``"<engine>:<gpu>"``。"""

    @classmethod
    def create(cls, engine: str = 'easyocr', gpu: bool = False) -> OCREngine:
        """创建或获取 OCR 引擎实例（单例）。

        首次调用时创建引擎实例并缓存，后续相同参数的调用直接返回缓存实例。

        Parameters
        ----------
        engine:
            引擎名称: ``"easyocr"`` 或 ``"paddleocr"``。
        gpu:
            是否使用 GPU 加速。

        Returns
        -------
        OCREngine
        """
        cache_key = f'{engine}:{gpu}'
        if cache_key in cls._instances:
            _log.debug('[OCR] 复用已有 {} 实例（gpu={}）', engine, gpu)
            return cls._instances[cache_key]

        if engine == 'easyocr':
            _log.info('[OCR] 初始化 EasyOCR（gpu={}）', gpu)
            instance = EasyOCREngine(gpu=gpu)
            cls._instances[cache_key] = instance
            return instance
        raise ValueError(f'不支持的 OCR 引擎: {engine}，可选: easyocr, paddleocr')


# ── 具体实现 ──


class EasyOCREngine(OCREngine):
    """基于 EasyOCR 的识别引擎。"""

    def __init__(self, gpu: bool = False) -> None:
        self._reader = easyocr.Reader(['ch_sim', 'en'], gpu=gpu)

    def recognize(
        self,
        image: np.ndarray,
        allowlist: str = '',
    ) -> list[OCRResult]:
        kwargs: dict = {}
        if allowlist:
            kwargs['allowlist'] = allowlist
        raw = self._reader.readtext(image, **kwargs)
        return [
            OCRResult(
                text=text,
                confidence=float(conf),
                bbox=(
                    int(box[0][0]),
                    int(box[0][1]),
                    int(box[2][0]),
                    int(box[2][1]),
                ),
            )
            for box, text, conf in raw
        ]


# ── 辅助函数 ──


def _fuzzy_match(text: str, candidates: list[str], threshold: int = 3) -> str | None:
    """基于编辑距离的模糊匹配。"""
    best_name: str | None = None
    best_dist = threshold + 1
    for name in candidates:
        dist = _edit_distance(text, name)
        if dist < best_dist:
            best_dist = dist
            best_name = name
    if best_name is not None and best_dist <= threshold:
        _log.debug(
            "[OCR] fuzzy_match: '{}' -> '{}' (distance={})",
            text,
            best_name,
            best_dist,
        )
        return best_name
    _log.debug(
        "[OCR] fuzzy_match: '{}' -> 无匹配 (best='{}', distance={}, threshold={})",
        text,
        best_name,
        best_dist,
        threshold,
    )
    return None


def _edit_distance(a: str, b: str) -> int:
    """Levenshtein 编辑距离。"""
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev, dp[0] = dp[0], i
        for j in range(1, n + 1):
            temp = dp[j]
            dp[j] = min(
                dp[j] + 1,
                dp[j - 1] + 1,
                prev + (0 if a[i - 1] == b[j - 1] else 1),
            )
            prev = temp
    return dp[n]
