"""OCR 引擎抽象层。

提供统一的文字识别接口，支持 EasyOCR 和 PaddleOCR 后端。

使用方式::

    from autowsgr.vision.ocr import OCREngine

    engine = OCREngine.create("easyocr", gpu=False)
    results = engine.recognize(cropped_image)
    number = engine.recognize_number(resource_area)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np


# ── 结果数据类 ──


@dataclass(frozen=True, slots=True)
class OCRResult:
    """OCR 识别结果。

    Attributes
    ----------
    text:
        识别出的文本。
    confidence:
        置信度 (0.0–1.0)。
    bbox:
        文本区域边界框 (x1, y1, x2, y2)，可能为 None。
    """

    text: str
    confidence: float
    bbox: tuple[int, int, int, int] | None = None


# ── 抽象基类 ──


class OCREngine(ABC):
    """OCR 引擎抽象基类。

    子类只需实现 :meth:`recognize` 方法。
    高层便捷方法 (recognize_single, recognize_number, recognize_ship_name)
    基于 recognize 构建，无需子类重写。
    """

    @abstractmethod
    def recognize(
        self,
        image: np.ndarray,
        allowlist: str = "",
    ) -> list[OCRResult]:
        """识别图像中的文字。

        Parameters
        ----------
        image:
            输入图像 (BGR, uint8)。
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
        allowlist: str = "",
    ) -> OCRResult:
        """识别单个文本区域，返回置信度最高的结果。

        无结果时返回空文本、零置信度的 OCRResult。
        """
        results = self.recognize(image, allowlist)
        if not results:
            return OCRResult(text="", confidence=0.0)
        return max(results, key=lambda r: r.confidence)

    def recognize_number(
        self,
        image: np.ndarray,
        extra_chars: str = "",
    ) -> int | None:
        """识别数字，支持 K/M 后缀。

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
        result = self.recognize_single(image, allowlist="0123456789" + extra_chars)
        text = result.text.strip()
        if not text:
            return None

        # 处理 K / M 后缀
        multiplier = 1
        if text.upper().endswith("K"):
            multiplier = 1000
            text = text[:-1]
        elif text.upper().endswith("M"):
            multiplier = 1_000_000
            text = text[:-1]

        try:
            return int(float(text) * multiplier)
        except (ValueError, TypeError):
            return None

    def recognize_ship_name(
        self,
        image: np.ndarray,
        candidates: list[str],
        threshold: int = 3,
    ) -> str | None:
        """识别舰船名称，模糊匹配到候选列表。

        Parameters
        ----------
        image:
            舰船名称区域图像。
        candidates:
            候选舰船名列表。
        threshold:
            编辑距离阈值，超过则不匹配。

        Returns
        -------
        str | None
            匹配到的舰船名，或 None。
        """
        result = self.recognize_single(image)
        if not result.text:
            return None
        return _fuzzy_match(result.text, candidates, threshold)

    # ── 工厂方法 ──

    @classmethod
    def create(cls, engine: str = "easyocr", gpu: bool = False) -> OCREngine:
        """创建 OCR 引擎实例。

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
        if engine == "easyocr":
            return EasyOCREngine(gpu=gpu)
        if engine == "paddleocr":
            return PaddleOCREngine(gpu=gpu)
        raise ValueError(f"不支持的 OCR 引擎: {engine}，可选: easyocr, paddleocr")


# ── 具体实现 ──


class EasyOCREngine(OCREngine):
    """基于 EasyOCR 的识别引擎。"""

    def __init__(self, gpu: bool = False) -> None:
        import easyocr

        self._reader = easyocr.Reader(["ch_sim", "en"], gpu=gpu)

    def recognize(
        self,
        image: np.ndarray,
        allowlist: str = "",
    ) -> list[OCRResult]:
        kwargs: dict = {}
        if allowlist:
            kwargs["allowlist"] = allowlist
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


class PaddleOCREngine(OCREngine):
    """基于 PaddleOCR 的识别引擎。"""

    def __init__(self, gpu: bool = False) -> None:
        from paddleocr import PaddleOCR

        self._ocr = PaddleOCR(
            use_angle_cls=True, lang="ch", use_gpu=gpu, show_log=False
        )

    def recognize(
        self,
        image: np.ndarray,
        allowlist: str = "",
    ) -> list[OCRResult]:
        raw = self._ocr.ocr(image, cls=True)
        if not raw or not raw[0]:
            return []
        return [
            OCRResult(
                text=line[1][0],
                confidence=float(line[1][1]),
                bbox=(
                    int(line[0][0][0]),
                    int(line[0][0][1]),
                    int(line[0][2][0]),
                    int(line[0][2][1]),
                ),
            )
            for line in raw[0]
        ]


# ── 辅助函数 ──


def _fuzzy_match(
    text: str, candidates: list[str], threshold: int = 3
) -> str | None:
    """基于编辑距离的模糊匹配。"""
    best_name: str | None = None
    best_dist = threshold + 1
    for name in candidates:
        dist = _edit_distance(text, name)
        if dist < best_dist:
            best_dist = dist
            best_name = name
    return best_name if best_dist <= threshold else None


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
