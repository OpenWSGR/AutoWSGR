"""视觉层 — 基于像素特征的图像识别 + OCR。

公开 API::

    # 像素检测
    from autowsgr.vision import (
        Color,
        PixelRule,
        PixelSignature,
        MatchStrategy,
        PixelChecker,
        PixelMatchResult,
        PixelDetail,
    )

    # OCR
    from autowsgr.vision import OCREngine, OCRResult
"""

from autowsgr.vision.matcher import (
    Color,
    MatchStrategy,
    PixelChecker,
    PixelDetail,
    PixelMatchResult,
    PixelRule,
    PixelSignature,
)
from autowsgr.vision.ocr import OCREngine, OCRResult

__all__ = [
    # matcher
    "Color",
    "MatchStrategy",
    "PixelChecker",
    "PixelDetail",
    "PixelMatchResult",
    "PixelRule",
    "PixelSignature",
    # ocr
    "OCREngine",
    "OCRResult",
]
