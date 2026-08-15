"""Tests for OverlayChecker — 均匀蒙版浮层检测 (双帧, 操作驱动)。"""

from __future__ import annotations

import numpy as np
import pytest

from autowsgr.vision import OverlayChecker, OverlayDetectResult


# ─────────────────────────────────────────────
# 合成图 helpers
# ─────────────────────────────────────────────


def _gradient_screen(h: int = 540, w: int = 960, lo: int = 80, hi: int = 180) -> np.ndarray:
    """连续渐变图 (横向亮度渐变), 模拟真实 UI 大块连续背景。

    连续区域使 ``after/before`` 比值聚集于单一众数 (均匀蒙版浮层的物理特征);
    纯随机噪声会令比值分散, 不符合浮层模型, 故正样本用渐变、负样本用噪声。
    """
    xs = np.tile(np.linspace(0, 1, w), (h, 1))
    g = (lo + xs * (hi - lo))[:, :, None].repeat(3, 2)
    return g.astype(np.uint8)


def _darken(img: np.ndarray, factor: float) -> np.ndarray:
    """按 *factor* 乘性压暗 (模拟半透明黑罩), uint8 量化。"""
    return np.clip(img.astype(np.float32) * factor, 0, 255).astype(np.uint8)


# ─────────────────────────────────────────────
# OverlayChecker.detect_uniform_mask
# ─────────────────────────────────────────────


class TestDetectUniformMask:
    def test_pure_darken_matched(self):
        """纯乘性压暗 (无面板) → 检测为均匀蒙版, t 接近压暗系数。"""
        before = _gradient_screen()
        after = _darken(before, 0.30)
        result = OverlayChecker.detect_uniform_mask(before, after)
        assert result.matched is True
        assert result.darken_factor == pytest.approx(0.30, abs=0.025)
        assert result.outer_frac > 0.10

    def test_darken_with_panel_matched(self):
        """压暗 + 中心亮面板 (浮层几何) → 仍检测为均匀蒙版, 外围匹配 > 中心。"""
        before = _gradient_screen()
        after = _darken(before, 0.30)
        after[100:440, 200:760] = [220, 230, 240]  # 中心面板不被压暗
        result = OverlayChecker.detect_uniform_mask(before, after)
        assert result.matched is True
        assert result.edge_frac > result.center_frac

    def test_confirm_dialog_factor_matched(self):
        """较高压暗系数 (确认弹窗 ~0.425) + 小面板 → 检测为均匀蒙版。"""
        before = _gradient_screen()
        after = _darken(before, 0.425)
        after[150:390, 300:660] = [200, 200, 200]
        result = OverlayChecker.detect_uniform_mask(before, after)
        assert result.matched is True
        assert result.darken_factor == pytest.approx(0.425, abs=0.025)

    def test_page_jump_not_matched(self):
        """完全不同的画面 (页跳转, 内容无关) → 非浮层。"""
        before = _gradient_screen()
        after = np.random.RandomState(1).randint(40, 200, (540, 960, 3)).astype(np.uint8)
        result = OverlayChecker.detect_uniform_mask(before, after)
        assert result.matched is False

    def test_close_overlay_not_matched(self):
        """反向 (before=压暗态, after=亮态, 关闭浮层) → 非浮层。"""
        before = _gradient_screen()
        darkened = _darken(before, 0.30)
        # 关闭浮层: 原本压暗的帧变回亮帧, 与"打开浮层"拓扑相反
        result = OverlayChecker.detect_uniform_mask(darkened, before)
        assert result.matched is False

    def test_no_change_not_matched(self):
        """前后相同 → 非浮层 (raw_diff≈0)。"""
        before = _gradient_screen()
        result = OverlayChecker.detect_uniform_mask(before, before)
        assert result.matched is False
        assert result.raw_diff == pytest.approx(0.0)

    def test_result_is_dataclass_with_fields(self):
        """返回 OverlayDetectResult 且字段齐备。"""
        before = _gradient_screen()
        after = _darken(before, 0.30)
        result = OverlayChecker.detect_uniform_mask(before, after)
        assert isinstance(result, OverlayDetectResult)
        for field in (
            'matched',
            'darken_factor',
            'outer_frac',
            'edge_frac',
            'center_frac',
            'raw_diff',
        ):
            assert hasattr(result, field)


# ─────────────────────────────────────────────
# OverlayChecker.page_changed
# ─────────────────────────────────────────────


class TestPageChanged:
    def test_detects_change(self):
        """两帧明显不同 → True。"""
        before = _gradient_screen()
        after = _darken(before, 0.30)
        assert OverlayChecker.page_changed(before, after) is True

    def test_detects_no_change(self):
        """两帧相同 → False。"""
        before = _gradient_screen()
        assert OverlayChecker.page_changed(before, before) is False

    def test_custom_threshold(self):
        """自定义阈值生效 (极高阈值 → 即使有变化也判为未变)。"""
        before = _gradient_screen()
        after = _darken(before, 0.30)
        assert OverlayChecker.page_changed(before, after, threshold=1e9) is False
