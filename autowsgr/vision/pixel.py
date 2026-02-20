"""像素特征数据模型。

定义 AutoWSGR 视觉层的基本类型:

- :class:`Color` — RGB 颜色值
- :class:`PixelRule` — 单像素检测规则
- :class:`MatchStrategy` — 多像素匹配策略
- :class:`PixelSignature` — 多规则组合签名
- :class:`PixelDetail` — 单规则检测结果
- :class:`PixelMatchResult` — 签名匹配结果

这些类型是纯数据模型，不包含任何检测逻辑。
检测引擎见 :mod:`autowsgr.vision.matcher` 中的 :class:`PixelChecker`。
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

from loguru import logger


# ═══════════════════════════════════════════════════════════════════════════════
# 颜色
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class Color:
    """RGB 颜色值。

    项目统一使用 RGB 通道顺序，与截图数组一致。

    Parameters
    ----------
    r, g, b:
        红、绿、蓝通道值，范围 0–255。
    """

    r: int
    g: int
    b: int

    # ── 构造 ──

    @classmethod
    def of(cls, r: int, g: int, b: int) -> Color:
        """从 RGB 值创建。"""
        return cls(r=r, g=g, b=b)

    @classmethod
    def from_rgb(cls, r: int, g: int, b: int) -> Color:
        """从 RGB 值创建（与 :meth:`of` 等价）。"""
        return cls(r=r, g=g, b=b)

    @classmethod
    def from_bgr(cls, b: int, g: int, r: int) -> Color:
        """从 BGR 值创建（OpenCV 顺序）。"""
        return cls(r=r, g=g, b=b)

    @classmethod
    def from_rgb_tuple(cls, rgb: tuple[int, int, int]) -> Color:
        """从 (R, G, B) 元组创建。"""
        return cls(r=rgb[0], g=rgb[1], b=rgb[2])

    @classmethod
    def from_bgr_tuple(cls, bgr: tuple[int, int, int]) -> Color:
        """从 (B, G, R) 元组创建（兼容 OpenCV）。"""
        return cls(r=bgr[2], g=bgr[1], b=bgr[0])

    # ── 距离 ──

    def distance(self, other: Color) -> float:
        """欧几里得色彩距离。"""
        return (
            (self.b - other.b) ** 2
            + (self.g - other.g) ** 2
            + (self.r - other.r) ** 2
        ) ** 0.5

    def near(self, other: Color, tolerance: float = 30.0) -> bool:
        """判断两个颜色是否在容差范围内。"""
        return self.distance(other) <= tolerance

    # ── 转换 ──

    def as_rgb_tuple(self) -> tuple[int, int, int]:
        return (self.r, self.g, self.b)

    def as_bgr_tuple(self) -> tuple[int, int, int]:
        return (self.b, self.g, self.r)

    def __repr__(self) -> str:
        return f"Color(r={self.r}, g={self.g}, b={self.b})"


# ═══════════════════════════════════════════════════════════════════════════════
# 像素规则
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class PixelRule:
    """单个像素检测规则。

    Parameters
    ----------
    x, y:
        像素的相对坐标（左上角为 0.0，右下角趋近 1.0）。
    color:
        期望的 RGB 颜色。
    tolerance:
        允许的最大色彩距离（欧几里得距离）。
    """

    x: float
    y: float
    color: Color
    tolerance: float = 30.0

    @classmethod
    def of(
        cls,
        x: float,
        y: float,
        rgb: tuple[int, int, int],
        tolerance: float = 30.0,
    ) -> PixelRule:
        """便捷构造：相对坐标 + RGB 元组。"""
        return cls(x=x, y=y, color=Color.from_rgb_tuple(rgb), tolerance=tolerance)

    @classmethod
    def from_dict(cls, d: dict) -> PixelRule:
        """从字典构造（支持 YAML 数据化）。

        字典格式::

            {"x": 0.50, "y": 0.85, "color": [201, 129, 54]}
            {"x": 0.50, "y": 0.85, "color": [201, 129, 54], "tolerance": 40}

        其中 color 为 RGB 顺序 ``[R, G, B]``。
        """
        color = d["color"]
        if isinstance(color, (list, tuple)):
            c = Color.from_rgb_tuple(tuple(color))  # type: ignore[arg-type]
        elif isinstance(color, dict):
            c = Color(r=color["r"], g=color["g"], b=color["b"])
        else:
            raise ValueError(f"无法解析颜色: {color}")
        return cls(
            x=float(d["x"]),
            y=float(d["y"]),
            color=c,
            tolerance=d.get("tolerance", 30.0),
        )

    def to_dict(self) -> dict:
        """序列化为字典（color 为 RGB 顺序 ``[R, G, B]``）。"""
        return {
            "x": self.x,
            "y": self.y,
            "color": list(self.color.as_rgb_tuple()),
            "tolerance": self.tolerance,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 匹配策略
# ═══════════════════════════════════════════════════════════════════════════════


class MatchStrategy(enum.Enum):
    """多像素点匹配策略。"""

    ALL = "all"
    """所有规则都必须匹配。"""

    ANY = "any"
    """至少一条规则匹配即可。"""

    COUNT = "count"
    """匹配数量 ≥ threshold 即可（需配合 PixelSignature.threshold）。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 像素签名
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class PixelSignature:
    """像素特征签名 — 由多条 PixelRule 组合定义一个页面 / 状态。

    Parameters
    ----------
    name:
        签名名称（页面名 / 状态名）。
    rules:
        像素规则列表。
    strategy:
        多规则匹配策略，默认 ALL（全部满足）。
    threshold:
        当 strategy == COUNT 时，需匹配的最小规则数。
    """

    name: str
    rules: tuple[PixelRule, ...] | list[PixelRule]
    strategy: MatchStrategy = MatchStrategy.ALL
    threshold: int = 0

    def __post_init__(self) -> None:
        if isinstance(self.rules, list):
            object.__setattr__(self, "rules", tuple(self.rules))

    @classmethod
    def from_dict(cls, d: dict) -> PixelSignature:
        """从字典构造（支持 YAML 数据化）。

        字典格式::

            name: main_page
            strategy: all       # 可选: all / any / count
            threshold: 0        # 仅 count 策略有效
            rules:
              - {x: 70, y: 485, color: [201, 129, 54]}
              - {x: 35, y: 297, color: [47, 253, 226]}
        """
        rules = [PixelRule.from_dict(r) for r in d["rules"]]
        strategy = MatchStrategy(d.get("strategy", "all"))
        return cls(
            name=d["name"],
            rules=rules,
            strategy=strategy,
            threshold=d.get("threshold", 0),
        )

    def to_dict(self) -> dict:
        """序列化为字典。"""
        return {
            "name": self.name,
            "strategy": self.strategy.value,
            "threshold": self.threshold,
            "rules": [r.to_dict() for r in self.rules],
        }

    def __len__(self) -> int:
        return len(self.rules)


# ═══════════════════════════════════════════════════════════════════════════════
# 检测结果
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class PixelDetail:
    """单条像素规则的检测详情。"""

    rule: PixelRule
    actual: Color
    distance: float
    matched: bool


@dataclass(frozen=True)
class PixelMatchResult:
    """像素签名匹配结果。

    可直接用作布尔值: ``if result: ...``
    """

    matched: bool
    """签名是否匹配。"""
    signature_name: str
    """签名名称。"""
    matched_count: int
    """匹配的规则数。"""
    total_count: int
    """规则总数。"""
    details: tuple[PixelDetail, ...] = field(default_factory=tuple)
    """每条规则的详细结果（可用于调试）。"""

    def __bool__(self) -> bool:
        return self.matched

    @property
    def ratio(self) -> float:
        """匹配比例 (0.0 – 1.0)。"""
        return self.matched_count / self.total_count if self.total_count > 0 else 0.0
