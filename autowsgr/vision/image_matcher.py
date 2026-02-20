"""基于模板匹配的图像识别引擎。

与 :mod:`autowsgr.vision.matcher` 中的像素特征检测互补，提供基于模板图片的匹配。

数据类（``ROI``, ``ImageTemplate``, ``ImageRule`` 等）定义在
:mod:`autowsgr.vision.roi` 和 :mod:`autowsgr.vision.image_template` 中，
本模块仅包含匹配引擎 :class:`ImageChecker`。

为了向后兼容，本模块同时 re-export 所有数据类。

使用方式::

    from autowsgr.vision.image_matcher import (
        ROI, ImageTemplate, ImageRule, ImageSignature, ImageChecker,
    )
"""

from __future__ import annotations

from typing import Sequence

import cv2
import numpy as np
from loguru import logger

from autowsgr.vision.image_template import (
    ImageMatchDetail,
    ImageMatchResult,
    ImageRule,
    ImageSignature,
    ImageTemplate,
)
from autowsgr.vision.matcher import MatchStrategy
from autowsgr.vision.roi import ROI

# Re-export 数据类，保持 ``from image_matcher import X`` 兼容
__all__ = [
    "ROI",
    "ImageTemplate",
    "ImageMatchDetail",
    "ImageMatchResult",
    "ImageRule",
    "ImageSignature",
    "ImageChecker",
]


class ImageChecker:
    """基于模板匹配的图像检测引擎。

    与 :class:`~autowsgr.vision.matcher.PixelChecker` 平行的 API，
    提供模板匹配相关的所有操作。

    所有方法接收 numpy 数组形式的截图 (H×W×3, RGB uint8)，
    坐标一律使用相对值（左上角为 0.0，右下角趋近 1.0），
    不执行任何设备操作（截图由上层提供）。
    """

    # ── 核心匹配 ──

    @staticmethod
    def _match_single_template(
        screen: np.ndarray,
        template: ImageTemplate,
        roi: ROI | None = None,
        confidence: float = 0.85,
        method: int = cv2.TM_CCOEFF_NORMED,
    ) -> ImageMatchDetail | None:
        """对单个模板执行匹配（内部方法）。"""
        h, w = screen.shape[:2]
        roi = roi or ROI.full()

        cropped = roi.crop(screen)
        ch, cw = cropped.shape[:2]
        th, tw = template.shape

        if th > ch or tw > cw:
            logger.debug(
                "[ImageMatcher] 模板 '{}' ({}x{}) 大于搜索区域 ({}x{})，跳过",
                template.name, tw, th, cw, ch,
            )
            return None

        screen_gray = cv2.cvtColor(cropped, cv2.COLOR_RGB2GRAY)
        template_gray = cv2.cvtColor(template.image, cv2.COLOR_RGB2GRAY)
        result = cv2.matchTemplate(screen_gray, template_gray, method)

        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        if method in (cv2.TM_SQDIFF, cv2.TM_SQDIFF_NORMED):
            best_val = 1.0 - min_val if method == cv2.TM_SQDIFF_NORMED else min_val
            best_loc = min_loc
        else:
            best_val = max_val
            best_loc = max_loc

        if best_val < confidence:
            logger.debug(
                "[ImageMatcher] 模板 '{}' 未匹配 (confidence={:.3f} < {:.3f})",
                template.name, best_val, confidence,
            )
            return None

        local_x, local_y = best_loc
        abs_x = int(roi.x1 * w) + local_x
        abs_y = int(roi.y1 * h) + local_y
        rel_x1, rel_y1 = abs_x / w, abs_y / h
        rel_x2, rel_y2 = (abs_x + tw) / w, (abs_y + th) / h
        rel_cx, rel_cy = (rel_x1 + rel_x2) / 2, (rel_y1 + rel_y2) / 2

        logger.debug(
            "[ImageMatcher] 模板 '{}' ✓ confidence={:.3f} center=({:.4f},{:.4f})",
            template.name, best_val, rel_cx, rel_cy,
        )
        return ImageMatchDetail(
            template_name=template.name, confidence=best_val,
            center=(rel_cx, rel_cy), top_left=(rel_x1, rel_y1),
            bottom_right=(rel_x2, rel_y2),
        )

    # ── 规则匹配 ──

    @staticmethod
    def match_rule(screen: np.ndarray, rule: ImageRule) -> ImageMatchResult:
        """检查截图是否匹配一条图像规则。"""
        all_details: list[ImageMatchDetail] = []
        best: ImageMatchDetail | None = None

        for tmpl in rule.templates:
            detail = ImageChecker._match_single_template(
                screen, tmpl, roi=rule.roi,
                confidence=rule.confidence, method=rule.method,
            )
            if detail is not None:
                all_details.append(detail)
                if best is None or detail.confidence > best.confidence:
                    best = detail

        matched = len(all_details) > 0
        logger.debug(
            "[ImageMatcher] 规则 '{}' {} ({}/{} 模板匹配)",
            rule.name, "✓" if matched else "✗", len(all_details), len(rule),
        )
        return ImageMatchResult(
            matched=matched, rule_name=rule.name,
            best=best, all_details=tuple(all_details),
        )

    # ── 签名匹配 ──

    @staticmethod
    def check_signature(screen: np.ndarray, signature: ImageSignature) -> ImageMatchResult:
        """检查截图是否匹配一个图像签名。"""
        all_details: list[ImageMatchDetail] = []
        best: ImageMatchDetail | None = None
        matched_count = 0

        for rule in signature.rules:
            result = ImageChecker.match_rule(screen, rule)
            if result.matched:
                matched_count += 1
                all_details.extend(result.all_details)
                if result.best is not None and (best is None or result.best.confidence > best.confidence):
                    best = result.best
                if signature.strategy == MatchStrategy.ANY:
                    return ImageMatchResult(matched=True, rule_name=signature.name, best=best, all_details=tuple(all_details))
            elif signature.strategy == MatchStrategy.ALL:
                return ImageMatchResult(matched=False, rule_name=signature.name, best=best, all_details=tuple(all_details))

        total = len(signature)
        match signature.strategy:
            case MatchStrategy.ALL:
                sig_matched = matched_count == total
            case MatchStrategy.ANY:
                sig_matched = matched_count > 0
            case MatchStrategy.COUNT:
                sig_matched = matched_count >= signature.threshold

        return ImageMatchResult(matched=sig_matched, rule_name=signature.name, best=best, all_details=tuple(all_details))

    # ── 便捷方法 ──

    @staticmethod
    def find_template(screen: np.ndarray, template: ImageTemplate, *, roi: ROI | None = None, confidence: float = 0.85) -> ImageMatchDetail | None:
        """在截图中查找单个模板（等价于旧代码 ``locate_image_center``）。"""
        return ImageChecker._match_single_template(screen, template, roi=roi, confidence=confidence)

    @staticmethod
    def find_any(screen: np.ndarray, templates: Sequence[ImageTemplate], *, roi: ROI | None = None, confidence: float = 0.85) -> ImageMatchDetail | None:
        """查找多个模板中的任意一个（等价于旧代码 ``image_exist``）。"""
        for tmpl in templates:
            detail = ImageChecker._match_single_template(screen, tmpl, roi=roi, confidence=confidence)
            if detail is not None:
                return detail
        return None

    @staticmethod
    def find_best(screen: np.ndarray, templates: Sequence[ImageTemplate], *, roi: ROI | None = None, confidence: float = 0.85) -> ImageMatchDetail | None:
        """查找多个模板中置信度最高的一个。"""
        best: ImageMatchDetail | None = None
        for tmpl in templates:
            detail = ImageChecker._match_single_template(screen, tmpl, roi=roi, confidence=confidence)
            if detail is not None and (best is None or detail.confidence > best.confidence):
                best = detail
        return best

    @staticmethod
    def find_all(screen: np.ndarray, templates: Sequence[ImageTemplate], *, roi: ROI | None = None, confidence: float = 0.85) -> list[ImageMatchDetail]:
        """查找所有匹配的模板。"""
        return [d for tmpl in templates if (d := ImageChecker._match_single_template(screen, tmpl, roi=roi, confidence=confidence)) is not None]

    @staticmethod
    def template_exists(screen: np.ndarray, templates: ImageTemplate | Sequence[ImageTemplate], *, roi: ROI | None = None, confidence: float = 0.85) -> bool:
        """判断模板是否存在于截图中（等价于旧代码 ``image_exist``）。"""
        if isinstance(templates, ImageTemplate):
            templates = [templates]
        return ImageChecker.find_any(screen, templates, roi=roi, confidence=confidence) is not None

    @staticmethod
    def identify(screen: np.ndarray, signatures: Sequence[ImageSignature]) -> ImageMatchResult | None:
        """从多个图像签名中识别当前页面 / 状态。"""
        for sig in signatures:
            result = ImageChecker.check_signature(screen, sig)
            if result:
                return result
        return None

    @staticmethod
    def crop(screen: np.ndarray, roi: ROI) -> np.ndarray:
        """使用 ROI 裁切图像（返回副本）。"""
        return roi.crop(screen).copy()

    @staticmethod
    def find_all_occurrences(
        screen: np.ndarray, template: ImageTemplate, *,
        roi: ROI | None = None, confidence: float = 0.85,
        max_count: int = 20, min_distance: int = 10,
    ) -> list[ImageMatchDetail]:
        """查找单个模板的所有出现位置（非极大值抑制去重）。"""
        h, w = screen.shape[:2]
        roi = roi or ROI.full()
        cropped = roi.crop(screen)
        ch, cw = cropped.shape[:2]
        th, tw = template.shape

        if th > ch or tw > cw:
            return []

        screen_gray = cv2.cvtColor(cropped, cv2.COLOR_RGB2GRAY)
        template_gray = cv2.cvtColor(template.image, cv2.COLOR_RGB2GRAY)
        result = cv2.matchTemplate(screen_gray, template_gray, cv2.TM_CCOEFF_NORMED)

        locations = np.where(result >= confidence)
        scores = result[locations]
        if len(scores) == 0:
            return []

        sorted_indices = np.argsort(-scores)
        details: list[ImageMatchDetail] = []
        used: list[tuple[int, int]] = []

        for idx in sorted_indices:
            if len(details) >= max_count:
                break
            lx, ly = int(locations[1][idx]), int(locations[0][idx])
            cx, cy = lx + tw // 2, ly + th // 2
            if any(abs(cx - ux) < min_distance and abs(cy - uy) < min_distance for ux, uy in used):
                continue
            used.append((cx, cy))
            ax, ay = int(roi.x1 * w) + lx, int(roi.y1 * h) + ly
            rx1, ry1 = ax / w, ay / h
            rx2, ry2 = (ax + tw) / w, (ay + th) / h
            details.append(ImageMatchDetail(
                template_name=template.name, confidence=float(scores[idx]),
                center=((rx1 + rx2) / 2, (ry1 + ry2) / 2),
                top_left=(rx1, ry1), bottom_right=(rx2, ry2),
            ))
        return details
