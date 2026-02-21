"""基于像素特征的图像识别引擎。

``PixelChecker`` 对截图执行像素签名匹配，判定当前页面/状态。

数据类型见 :mod:`autowsgr.vision.pixel`:
  - :class:`Color` / :class:`PixelRule` / :class:`PixelSignature`
  - :class:`MatchStrategy` / :class:`PixelDetail` / :class:`PixelMatchResult`

使用方式::

    from autowsgr.vision import Color, PixelRule, PixelSignature, PixelChecker

    main_page = PixelSignature(
        name="main_page",
        rules=[
            PixelRule(0.50, 0.85, Color.of(54, 129, 201)),
            PixelRule(0.20, 0.60, Color.of(226, 253, 47)),
        ],
    )
    result = PixelChecker.check_signature(screen, main_page)
    if result:
        print("当前在主页")
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
from loguru import logger

# 从 pixel.py 导入所有数据类型 (保持向后兼容)
from .pixel import (
    Color,
    MatchStrategy,
    PixelDetail,
    PixelMatchResult,
    PixelRule,
    PixelSignature,
)

# ── 模块级配置 ──

_show_pixel_detail: bool = False
"""是否输出逐像素规则的 DEBUG 日志。由 :func:`configure` 或 ``setup_logger`` 设置。"""


def configure(*, show_pixel_detail: bool = False) -> None:
    """配置 PixelChecker 的日志行为。

    TODO: 这个实现太 TM 恶心了，必须换掉
    通常由 ``setup_logger`` 在应用启动时根据 ``LogConfig.show_pixel_detail`` 调用，
    也可在测试或调试时手动调用。

    Parameters
    ----------
    show_pixel_detail:
        是否输出每条像素规则的期望/实际/距离 DEBUG 日志。
        默认 ``False``，仅显示签名级别的匹配结果。
    """
    global _show_pixel_detail
    _show_pixel_detail = show_pixel_detail

class PixelChecker:
    """像素特征检测引擎 — 视觉层核心 API。

    所有方法接收 numpy 数组形式的截图 (H×W×3, RGB uint8)，
    坐标一律使用相对值（左上角为 0.0，右下角趋近 1.0），
    内部自动转换为像素索引，与截图分辨率无关。
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
        """检查单个像素是否与期望颜色匹配。"""
        actual = PixelChecker.get_pixel(screen, x, y)
        return actual.near(color, tolerance)

    # ── 多像素批量 ──

    @staticmethod
    def get_pixels(
        screen: np.ndarray,
        positions: Sequence[tuple[float, float]],
    ) -> list[Color]:
        """批量获取多个坐标的像素颜色。"""
        return [PixelChecker.get_pixel(screen, x, y) for x, y in positions]

    @staticmethod
    def check_pixels(
        screen: np.ndarray,
        rules: Sequence[PixelRule],
    ) -> list[bool]:
        """批量检查多条像素规则。"""
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
                    PixelDetail(
                        rule=rule, actual=actual, distance=dist, matched=is_match
                    )
                )

            if _show_pixel_detail:
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
                if not with_details:
                    if _show_pixel_detail:
                        logger.debug(
                            "[Matcher] '{}' ✗ 短路退出 — ALL 首次失败于 [{:.4f},{:.4f}]",
                            signature.name,
                            rule.x,
                            rule.y,
                        )
                    return PixelMatchResult(
                        matched=False,
                        signature_name=signature.name,
                        matched_count=matched_count,
                        total_count=len(signature),
                    )
            elif signature.strategy == MatchStrategy.ANY and is_match:
                if not with_details:
                    if _show_pixel_detail:
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
        """从多个签名中识别当前页面/状态（首次匹配）。"""
        for sig in signatures:
            result = PixelChecker.check_signature(
                screen, sig, with_details=with_details
            )
            if result:
                logger.debug("[Matcher] identify() → '{}'", result.signature_name)
                return result
        logger.debug(
            "[Matcher] identify() → None（共 {} 个签名均未匹配）", len(signatures)
        )
        return None

    @staticmethod
    def identify_all(
        screen: np.ndarray,
        signatures: Sequence[PixelSignature],
        *,
        with_details: bool = False,
    ) -> list[PixelMatchResult]:
        """检查所有签名，返回所有匹配的结果。"""
        results: list[PixelMatchResult] = []
        for sig in signatures:
            result = PixelChecker.check_signature(
                screen, sig, with_details=with_details
            )
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
            像素的相对坐标。
        color_map:
            命名颜色映射 ``{"name": Color(...), ...}``。
        tolerance:
            最大容差，超过则返回 None。
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
            x,
            y,
            result_name,
            best_dist if result_name else -1,
        )
        return result_name

    # ── 图像裁切 ──

    @staticmethod
    def crop(
        screen: np.ndarray,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
    ) -> np.ndarray:
        """裁切矩形区域（相对坐标）。"""
        h, w = screen.shape[:2]
        px1, py1 = int(x1 * w), int(y1 * h)
        px2, py2 = int(x2 * w), int(y2 * h)
        return screen[py1:py2, px1:px2].copy()
