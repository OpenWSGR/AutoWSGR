"""图像模板、匹配规则与结果的数据类定义。

本模块定义模板匹配所需的核心数据结构：

- **ImageTemplate**: 模板图片封装
- **ImageMatchDetail**: 单次匹配详情
- **ImageMatchResult**: 规则 / 签名匹配结果
- **ImageRule**: 单条匹配规则（模板列表 + ROI + 置信度）
- **ImageSignature**: 多规则组合签名

匹配引擎 :class:`~autowsgr.vision.image_matcher.ImageChecker` 在独立模块中。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from .matcher import MatchStrategy
from .roi import ROI


# ── 图像模板 ──


@dataclass(frozen=True)
class ImageTemplate:
    """模板图片封装。

    封装用于模板匹配的参考图像，支持从文件路径或 numpy 数组加载。
    所有模板内部统一转换为 RGB 格式存储。

    Parameters
    ----------
    name:
        模板名称（用于日志和调试）。
    image:
        模板图像数据 (H×W×3, RGB, uint8)。
    source:
        模板来源描述（文件路径或 "ndarray"）。
    """

    name: str
    image: np.ndarray
    source: str = ""
    source_resolution: tuple[int, int] = (960, 540)
    """模板图片采集时的屏幕分辨率 (width, height)。

    匹配引擎会根据此值与实际截图分辨率的比值动态缩放模板，
    默认 ``(960, 540)``，与全局 :data:`TEMPLATE_SOURCE_RESOLUTION` 一致。
    """

    # ── 构造 ──

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        name: str | None = None,
        source_resolution: tuple[int, int] = (960, 540),
    ) -> ImageTemplate:
        """从文件加载模板。

        Parameters
        ----------
        path:
            图片文件路径。
        name:
            模板名称，默认为文件名（不含扩展名）。
        source_resolution:
            模板采集时的屏幕分辨率 (width, height)，默认 ``(960, 540)``。

        Raises
        ------
        FileNotFoundError
            文件不存在。
        ValueError
            文件无法解码为图像。
        """
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"模板文件不存在: {p}")

        bgr = cv2.imread(str(p), cv2.IMREAD_COLOR)
        if bgr is None:
            raise ValueError(f"无法解码图像文件: {p}")

        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        template_name = name or p.stem
        return cls(
            name=template_name,
            image=rgb,
            source=str(p),
            source_resolution=source_resolution,
        )

    @classmethod
    def from_ndarray(
        cls,
        image: np.ndarray,
        name: str = "unnamed",
        *,
        is_bgr: bool = False,
        source_resolution: tuple[int, int] = (960, 540),
    ) -> ImageTemplate:
        """从 numpy 数组创建模板。

        Parameters
        ----------
        image:
            模板图像数据 (H×W×3)。
        name:
            模板名称。
        is_bgr:
            如果为 True，将自动从 BGR 转为 RGB。
        source_resolution:
            模板采集时的屏幕分辨率 (width, height)，默认 ``(960, 540)``。
        """
        if is_bgr:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        return cls(
            name=name,
            image=image.copy(),
            source="ndarray",
            source_resolution=source_resolution,
        )

    @property
    def height(self) -> int:
        return self.image.shape[0]

    @property
    def width(self) -> int:
        return self.image.shape[1]

    @property
    def shape(self) -> tuple[int, int]:
        """(height, width) 像素尺寸。"""
        return (self.image.shape[0], self.image.shape[1])

    def __repr__(self) -> str:
        h, w = self.shape
        res = self.source_resolution
        res_str = f", source_resolution={res!r}" if res != (960, 540) else ""
        return f"ImageTemplate(name='{self.name}', size={w}x{h}, source='{self.source}'{res_str})"


# ── 模板匹配结果 ──


@dataclass(frozen=True, slots=True)
class ImageMatchDetail:
    """单次模板匹配的详细结果。

    Attributes
    ----------
    template_name:
        匹配到的模板名称。
    confidence:
        最佳匹配的置信度 (0.0–1.0)。
    center:
        匹配区域中心的 **相对坐标** (x, y)，范围 [0.0, 1.0]。
        已从 ROI 局部坐标转换回全图坐标。
    top_left:
        匹配区域左上角的 **相对坐标** (x, y)。
    bottom_right:
        匹配区域右下角的 **相对坐标** (x, y)。
    """

    template_name: str
    confidence: float
    center: tuple[float, float]
    top_left: tuple[float, float]
    bottom_right: tuple[float, float]


@dataclass(frozen=True)
class ImageMatchResult:
    """图像规则匹配结果。

    可直接用作布尔值: ``if result: ...``
    """

    matched: bool
    """是否匹配成功。"""
    rule_name: str
    """规则名称。"""
    best: ImageMatchDetail | None = None
    """最佳匹配详情（未匹配时为 None）。"""
    all_details: tuple[ImageMatchDetail, ...] = field(default_factory=tuple)
    """所有超过阈值的匹配（多模板场景）。"""

    def __bool__(self) -> bool:
        return self.matched

    @property
    def center(self) -> tuple[float, float] | None:
        """最佳匹配的中心相对坐标，未匹配时为 None。"""
        return self.best.center if self.best else None

    @property
    def confidence(self) -> float:
        """最佳匹配的置信度，未匹配时为 0.0。"""
        return self.best.confidence if self.best else 0.0


# ── 图像规则 ──


@dataclass(frozen=True)
class ImageRule:
    """单条图像匹配规则。

    将一个或多个模板图片与 ROI、置信度阈值组合，定义一条完整的匹配条件。
    当提供多个模板时，任一模板匹配成功即视为规则匹配（OR 语义）。

    Parameters
    ----------
    name:
        规则名称（用于日志和调试）。
    templates:
        模板列表，任一匹配即视为规则匹配。
    roi:
        搜索区域，默认全屏。
    confidence:
        匹配置信度阈值 (0.0–1.0)。
    method:
        OpenCV 模板匹配方法，默认 ``cv2.TM_CCOEFF_NORMED``。

    Examples
    --------
    >>> rule = ImageRule(
    ...     name="确认按钮",
    ...     templates=[confirm_btn, confirm_btn_v2],
    ...     roi=ROI(0.6, 0.7, 1.0, 1.0),
    ...     confidence=0.85,
    ... )
    """

    name: str
    templates: tuple[ImageTemplate, ...] | list[ImageTemplate]
    roi: ROI = field(default_factory=ROI.full)
    confidence: float = 0.85
    method: int = cv2.TM_CCOEFF_NORMED

    def __post_init__(self) -> None:
        if isinstance(self.templates, list):
            object.__setattr__(self, "templates", tuple(self.templates))

    def __len__(self) -> int:
        return len(self.templates)


# ── 图像签名 ──


@dataclass(frozen=True)
class ImageSignature:
    """图像特征签名 — 由多条 ImageRule 组合定义一个页面 / 状态。

    与 :class:`~autowsgr.vision.matcher.PixelSignature` 类似，但基于模板图片。
    支持 ALL / ANY / COUNT 匹配策略。

    Parameters
    ----------
    name:
        签名名称（页面名 / 状态名）。
    rules:
        图像规则列表。
    strategy:
        多规则匹配策略，默认 ALL。
    threshold:
        当 strategy == COUNT 时，需匹配的最小规则数。
    """

    name: str
    rules: tuple[ImageRule, ...] | list[ImageRule]
    strategy: MatchStrategy = MatchStrategy.ALL
    threshold: int = 0

    def __post_init__(self) -> None:
        if isinstance(self.rules, list):
            object.__setattr__(self, "rules", tuple(self.rules))

    def __len__(self) -> int:
        return len(self.rules)
