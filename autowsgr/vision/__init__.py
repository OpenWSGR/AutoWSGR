"""视觉层 — 像素特征检测 + 模板图像匹配 + OCR。

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

    # 图像模板匹配
    from autowsgr.vision import (
        ROI,
        ImageTemplate,
        ImageRule,
        ImageSignature,
        ImageChecker,
        ImageMatchResult,
        ImageMatchDetail,
    )

    # OCR
    from autowsgr.vision import OCREngine, OCRResult
"""

from autowsgr.vision.image_matcher import ImageChecker
from autowsgr.vision.image_template import (
    ImageMatchDetail,
    ImageMatchResult,
    ImageRule,
    ImageSignature,
    ImageTemplate,
)
from autowsgr.vision.pixel import (
    Color,
    MatchStrategy,
    PixelDetail,
    PixelMatchResult,
    PixelRule,
    PixelSignature,
)
from autowsgr.vision.matcher import PixelChecker
from autowsgr.vision.ocr import OCREngine, OCRResult
from autowsgr.vision.roi import ROI

__all__ = [
    # matcher (pixel)
    "Color",
    "MatchStrategy",
    "PixelChecker",
    "PixelDetail",
    "PixelMatchResult",
    "PixelRule",
    "PixelSignature",
    # image_matcher (template)
    "ROI",
    "ImageTemplate",
    "ImageRule",
    "ImageSignature",
    "ImageChecker",
    "ImageMatchResult",
    "ImageMatchDetail",
    # ocr
    "OCREngine",
    "OCRResult",
]
