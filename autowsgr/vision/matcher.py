"""基于像素特征的图像识别引擎。

这是 AutoWSGR 视觉层的核心模块。采用 **像素特征检测** 方案替代传统模板匹配：

- 每个页面 / 状态用若干 **特征像素点** (PixelRule) 描述
- 多个 PixelRule 组成一个 **像素签名** (PixelSignature)
- PixelChecker 对截图执行签名匹配，判定当前页面 / 状态

优势:
    1. 无需维护大量模板图片，减少存储和加载开销
    2. 匹配速度极快（纯数组索引 + 距离计算，无卷积）
    3. 签名可数据化（YAML / dict），便于版本管理和热更新
    4. 支持 AND / ANY / COUNT 等灵活匹配策略

使用方式::

    from autowsgr.vision.matcher import Color, PixelRule, PixelSignature, PixelChecker

    # 定义签名（坐标为相对值，左上角 (0,0)，右下角趋近 (1,1)）
    main_page = PixelSignature(
        name="main_page",
        rules=[
            PixelRule(0.50, 0.85, Color.of(54, 129, 201)),
            PixelRule(0.20, 0.60, Color.of(226, 253, 47)),
        ],
    )

    checker = PixelChecker()
    result = checker.check_signature(screen, main_page)
    if result:
        print("当前在主页")
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np
from loguru import logger


# ── 颜色 ──


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


# ── 像素规则 ──


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
        return cls(x=float(d["x"]), y=float(d["y"]), color=c, tolerance=d.get("tolerance", 30.0))

    def to_dict(self) -> dict:
        """序列化为字典（color 为 RGB 顺序 ``[R, G, B]``）。"""
        return {
            "x": self.x,
            "y": self.y,
            "color": list(self.color.as_rgb_tuple()),
            "tolerance": self.tolerance,
        }


# ── 匹配策略 ──


class MatchStrategy(enum.Enum):
    """多像素点匹配策略。"""

    ALL = "all"
    """所有规则都必须匹配。"""

    ANY = "any"
    """至少一条规则匹配即可。"""

    COUNT = "count"
    """匹配数量 ≥ threshold 即可（需配合 PixelSignature.threshold）。"""


# ── 像素签名 ──


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
        # 规范化为 tuple
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

        其中 color 为 RGB 顺序 ``[R, G, B]``。
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


# ── 单条规则检测结果 ──


@dataclass(frozen=True, slots=True)
class PixelDetail:
    """单条像素规则的检测详情。"""

    rule: PixelRule
    actual: Color
    distance: float
    matched: bool


# ── 签名检测结果 ──


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


# ── 像素检测器 ──


class PixelChecker:
    """像素特征检测引擎 — 视觉层核心 API。

    所有方法接收 numpy 数组形式的截图 (H×W×3, RGB uint8)，
    坐标一律使用相对值（左上角为 0.0，右下角趋近 1.0），
    内部自动转换为像素索引，与截图分辨率无关。
    不执行任何设备操作（截图由上层提供）。
    """

    # ── 单像素 ──

    @staticmethod
    def get_pixel(screen: np.ndarray, x: float, y: float) -> Color:
        """获取截图中指定坐标的像素颜色。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。
        x, y:
            像素的相对坐标（左上角为 0.0，右下角趋近 1.0）。

        Returns
        -------
        Color
            该像素的 RGB 颜色。
        """
        h, w = screen.shape[:2]
        px, py = int(x * w), int(y * h)
        rgb = screen[py, px]
        return Color(r=int(rgb[0]), g=int(rgb[1]), b=int(rgb[2]))

    @staticmethod
    def check_pixel(
        screen: np.ndarray,
        x: float,
        y: float,
        color: Color,
        tolerance: float = 30.0,
    ) -> bool:
        """检查单个像素是否与期望颜色匹配。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。
        x, y:
            像素的相对坐标（左上角为 0.0，右下角趋近 1.0）。
        color:
            期望的 RGB 颜色。
        tolerance:
            允许的最大色彩距离。

        Returns
        -------
        bool
        """
        actual = PixelChecker.get_pixel(screen, x, y)
        return actual.near(color, tolerance)

    # ── 多像素批量 ──

    @staticmethod
    def get_pixels(
        screen: np.ndarray,
        positions: Sequence[tuple[float, float]],
    ) -> list[Color]:
        """批量获取多个坐标的像素颜色。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。
        positions:
            相对坐标列表 [(x1, y1), (x2, y2), ...]（取值范围 0.0–1.0）。

        Returns
        -------
        list[Color]
        """
        return [PixelChecker.get_pixel(screen, x, y) for x, y in positions]

    @staticmethod
    def check_pixels(
        screen: np.ndarray,
        rules: Sequence[PixelRule],
    ) -> list[bool]:
        """批量检查多条像素规则。

        Returns
        -------
        list[bool]
            每条规则的匹配结果。
        """
        return [
            PixelChecker.check_pixel(screen, r.x, r.y, r.color, r.tolerance)
            for r in rules
        ]

    # ── 签名匹配 ──

    @staticmethod
    def check_signature(
        screen: np.ndarray,
        signature: PixelSignature,
        *,
        with_details: bool = False,
    ) -> PixelMatchResult:
        """检查截图是否匹配一个像素签名。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。
        signature:
            要检查的像素签名。
        with_details:
            是否在结果中包含每条规则的详情（影响性能，调试用）。

        Returns
        -------
        PixelMatchResult
        """
        details: list[PixelDetail] = []
        matched_count = 0

        for rule in signature.rules:
            actual = PixelChecker.get_pixel(screen, rule.x, rule.y)
            dist = actual.distance(rule.color)
            is_match = dist <= rule.tolerance

            if is_match:
                matched_count += 1

            if with_details:
                details.append(
                    PixelDetail(rule=rule, actual=actual, distance=dist, matched=is_match)
                )

            logger.debug(
                "[Matcher] '{}' [{:.4f},{:.4f}] 期望{} 实际{} 距离={:.1f} {}",
                signature.name,
                rule.x,
                rule.y,
                rule.color.as_rgb_tuple(),
                actual.as_rgb_tuple(),
                dist,
                "✓" if is_match else f"✗(容差={rule.tolerance})",
            )

            # 短路优化
            if signature.strategy == MatchStrategy.ALL and not is_match:
                # ALL 模式下一旦失败可提前退出
                if not with_details:
                    logger.debug(
                        "[Matcher] '{}' ✗ 短路退出 — ALL 首次失败于 [{:.4f},{:.4f}] ({}/{} 通过)",
                        signature.name,
                        rule.x,
                        rule.y,
                        matched_count,
                        len(signature),
                    )
                    return PixelMatchResult(
                        matched=False,
                        signature_name=signature.name,
                        matched_count=matched_count,
                        total_count=len(signature),
                    )
            elif signature.strategy == MatchStrategy.ANY and is_match:
                # ANY 模式下一旦成功可提前退出
                if not with_details:
                    logger.debug(
                        "[Matcher] '{}' ✓ 短路退出 — ANY 首次成功于 [{:.4f},{:.4f}]",
                        signature.name,
                        rule.x,
                        rule.y,
                    )
                    return PixelMatchResult(
                        matched=True,
                        signature_name=signature.name,
                        matched_count=matched_count,
                        total_count=len(signature),
                    )

        # 根据策略判定最终结果
        total = len(signature)
        match signature.strategy:
            case MatchStrategy.ALL:
                matched = matched_count == total
            case MatchStrategy.ANY:
                matched = matched_count > 0
            case MatchStrategy.COUNT:
                matched = matched_count >= signature.threshold

        logger.debug(
            "[Matcher] '{}' {} ({}/{} 规则匹配, 策略={})",
            signature.name,
            "✓" if matched else "✗",
            matched_count,
            total,
            signature.strategy.value,
        )
        return PixelMatchResult(
            matched=matched,
            signature_name=signature.name,
            matched_count=matched_count,
            total_count=total,
            details=tuple(details) if with_details else (),
        )

    @staticmethod
    def identify(
        screen: np.ndarray,
        signatures: Sequence[PixelSignature],
        *,
        with_details: bool = False,
    ) -> PixelMatchResult | None:
        """从多个签名中识别当前页面 / 状态。

        按顺序检查，返回第一个匹配的结果。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。
        signatures:
            候选签名列表。
        with_details:
            是否包含详情。

        Returns
        -------
        PixelMatchResult | None
            匹配的结果，全部未匹配时返回 ``None``。
        """
        for sig in signatures:
            result = PixelChecker.check_signature(screen, sig, with_details=with_details)
            if result:
                logger.debug("[Matcher] identify() → '{}'", result.signature_name)
                return result
        logger.debug("[Matcher] identify() → None（共 {} 个签名均未匹配）", len(signatures))
        return None

    @staticmethod
    def identify_all(
        screen: np.ndarray,
        signatures: Sequence[PixelSignature],
        *,
        with_details: bool = False,
    ) -> list[PixelMatchResult]:
        """检查所有签名，返回所有匹配的结果。

        与 :meth:`identify` 不同，不会短路，适用于需要知道所有匹配状态的场景。

        Returns
        -------
        list[PixelMatchResult]
            所有匹配的结果列表（可能为空）。
        """
        results: list[PixelMatchResult] = []
        for sig in signatures:
            result = PixelChecker.check_signature(screen, sig, with_details=with_details)
            if result:
                results.append(result)
        logger.debug(
            "[Matcher] identify_all() → {} / {} 匹配: [{}]",
            len(results),
            len(signatures),
            ", ".join(r.signature_name for r in results),
        )
        return results

    # ── 颜色分类 ──

    @staticmethod
    def classify_color(
        screen: np.ndarray,
        x: float,
        y: float,
        color_map: dict[str, Color],
        tolerance: float = 30.0,
    ) -> str | None:
        """将像素颜色分类到最近的命名颜色。

        Parameters
        ----------
        screen:
            截图。
        x, y:
            像素的相对坐标（左上角为 0.0，右下角趋近 1.0）。
        color_map:
            命名颜色映射 ``{"name": Color(...), ...}``。
        tolerance:
            最大容差，超过则返回 None。

        Returns
        -------
        str | None
            最近的颜色名，或 None（超出容差）。
        """
        actual = PixelChecker.get_pixel(screen, x, y)
        best_name: str | None = None
        best_dist = tolerance + 1.0
        for name, color in color_map.items():
            dist = actual.distance(color)
            if dist < best_dist:
                best_dist = dist
                best_name = name
        result_name = best_name if best_dist <= tolerance else None
        logger.debug(
            "[Matcher] classify_color({:.3f},{:.3f}) → {} (dist={:.1f})",
            x, y, result_name, best_dist if result_name else -1,
        )
        return result_name

    # ── 图像裁切（保留的通用工具） ──

    @staticmethod
    def crop(
        screen: np.ndarray,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
    ) -> np.ndarray:
        """裁切矩形区域。

        Parameters
        ----------
        screen:
            原始图像。
        x1, y1:
            左上角相对坐标 (0.0–1.0)。
        x2, y2:
            右下角相对坐标 (0.0–1.0)。

        Returns
        -------
        np.ndarray
            裁切后的图像副本。
        """
        h, w = screen.shape[:2]
        px1, py1 = int(x1 * w), int(y1 * h)
        px2, py2 = int(x2 * w), int(y2 * h)
        return screen[py1:py2, px1:px2].copy()
