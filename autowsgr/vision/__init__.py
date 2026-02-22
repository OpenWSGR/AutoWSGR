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

from .api_dll import ApiDll, get_api_dll
from .image_matcher import ImageChecker, TEMPLATE_SOURCE_RESOLUTION
from .image_template import (
    ImageMatchDetail,
    ImageMatchResult,
    ImageRule,
    ImageSignature,
    ImageTemplate,
)
from .pixel import (
    Color,
    MatchStrategy,
    PixelDetail,
    PixelMatchResult,
    PixelRule,
    PixelSignature,
)
from .matcher import PixelChecker
from .ocr import OCREngine, OCRResult, EasyOCREngine, ShipNameMismatchError
from .roi import ROI

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
    "TEMPLATE_SOURCE_RESOLUTION",
    # ocr
    "OCREngine",
    "OCRResult",
    "EasyOCREngine",
    "ShipNameMismatchError",
    # api_dll
    "ApiDll",
    "get_api_dll",
]
