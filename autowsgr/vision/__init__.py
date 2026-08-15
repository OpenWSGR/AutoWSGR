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
from .image_matcher import TEMPLATE_SOURCE_RESOLUTION, ImageChecker
from .image_template import (
    ImageMatchDetail,
    ImageMatchResult,
    ImageRule,
    ImageSignature,
    ImageTemplate,
)
from .matcher import PixelChecker
from .ocr import (
    EasyOCREngine,
    FastOCREngine,
    OCREngine,
    OCRResult,
    ShipNameMismatchError,
    apply_ship_patches,
)
from .page_match import PageMatch
from .pixel import (
    Color,
    CompositePixelSignature,
    MatchStrategy,
    PixelDetail,
    PixelMatchResult,
    PixelRule,
    PixelSignature,
)
from .roi import ROI


__all__ = [
    # image_matcher (template)
    'ROI',
    'TEMPLATE_SOURCE_RESOLUTION',
    # api_dll
    'ApiDll',
    # matcher (pixel)
    'Color',
    'CompositePixelSignature',
    'EasyOCREngine',
    'FastOCREngine',
    'ImageChecker',
    'ImageMatchDetail',
    'ImageMatchResult',
    'ImageRule',
    'ImageSignature',
    'ImageTemplate',
    'MatchStrategy',
    # ocr
    'OCREngine',
    'OCRResult',
    'PageMatch',
    'PixelChecker',
    'PixelDetail',
    'PixelMatchResult',
    'PixelRule',
    'PixelSignature',
    'ShipNameMismatchError',
    'apply_ship_patches',
    'get_api_dll',
]
