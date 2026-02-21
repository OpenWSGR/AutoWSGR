"""Tests for ImageChecker engine — find/match/identify/crop operations."""
from __future__ import annotations

import pytest

from autowsgr.vision import (
    ROI,
    ImageChecker,
    ImageRule,
    ImageSignature,
    MatchStrategy,
)

from ._helpers import embed_template_in_screen, make_template, solid_screen


# ─────────────────────────────────────────────
# ImageChecker — find_template (单模板匹配)
# ─────────────────────────────────────────────


class TestFindTemplate:
    def test_exact_match(self):
        """模板完全嵌入截图中，应能精确匹配。"""
        screen = solid_screen(200, 200, 200)
        tmpl = make_template(seed=1, h=30, w=40)
        screen = embed_template_in_screen(screen, tmpl, x=100, y=200)

        detail = ImageChecker.find_template(screen, tmpl, confidence=0.9)
        assert detail is not None
        assert detail.confidence > 0.9
        # 中心应大致在 (100+20)/960, (200+15)/540
        cx, cy = detail.center
        assert cx == pytest.approx(120 / 960, abs=0.02)
        assert cy == pytest.approx(215 / 540, abs=0.02)

    def test_no_match_when_absent(self):
        """模板未嵌入截图，不应匹配。"""
        screen = solid_screen(200, 200, 200)
        tmpl = make_template(seed=2, name="absent")
        detail = ImageChecker.find_template(screen, tmpl, confidence=0.9)
        assert detail is None

    def test_match_with_roi(self):
        """仅在 ROI 内搜索。"""
        screen = solid_screen(200, 200, 200)
        tmpl = make_template(seed=3, h=20, w=30)
        # 模板放在左上角
        screen = embed_template_in_screen(screen, tmpl, x=10, y=10)

        # ROI 在右半边 → 不应匹配
        detail = ImageChecker.find_template(
            screen, tmpl, roi=ROI(0.5, 0.0, 1.0, 1.0), confidence=0.9,
        )
        assert detail is None

        # ROI 包含左上角 → 应匹配
        detail = ImageChecker.find_template(
            screen, tmpl, roi=ROI(0.0, 0.0, 0.5, 0.5), confidence=0.9,
        )
        assert detail is not None

    def test_template_larger_than_roi(self):
        """模板大于搜索区域时应返回 None。"""
        screen = solid_screen(200, 200, 200)
        tmpl = make_template(seed=4, h=300, w=500)
        detail = ImageChecker.find_template(
            screen, tmpl, roi=ROI(0.0, 0.0, 0.1, 0.1), confidence=0.5,
        )
        assert detail is None


# ─────────────────────────────────────────────
# ImageChecker — find_any / find_best / find_all
# ─────────────────────────────────────────────


class TestFindMultiple:
    def test_find_any_returns_first_match(self):
        screen = solid_screen(200, 200, 200)
        t1 = make_template(seed=10, name="t1")
        t2 = make_template(seed=20, name="t2")
        screen = embed_template_in_screen(screen, t1, x=100, y=100)
        screen = embed_template_in_screen(screen, t2, x=500, y=300)

        detail = ImageChecker.find_any(screen, [t1, t2], confidence=0.9)
        assert detail is not None
        assert detail.template_name == "t1"

    def test_find_any_none_when_no_match(self):
        screen = solid_screen(200, 200, 200)
        t1 = make_template(seed=30, name="absent")
        detail = ImageChecker.find_any(screen, [t1], confidence=0.9)
        assert detail is None

    def test_find_all(self):
        screen = solid_screen(200, 200, 200)
        t1 = make_template(seed=10, name="t1")
        t2 = make_template(seed=20, name="t2")
        screen = embed_template_in_screen(screen, t1, x=100, y=100)
        screen = embed_template_in_screen(screen, t2, x=500, y=300)

        results = ImageChecker.find_all(screen, [t1, t2], confidence=0.9)
        assert len(results) == 2


# ─────────────────────────────────────────────
# ImageChecker — template_exists
# ─────────────────────────────────────────────


class TestTemplateExists:
    def test_exists_single(self):
        screen = solid_screen(200, 200, 200)
        tmpl = make_template(seed=40)
        screen = embed_template_in_screen(screen, tmpl, x=100, y=100)
        assert ImageChecker.template_exists(screen, tmpl, confidence=0.9)

    def test_exists_list(self):
        screen = solid_screen(200, 200, 200)
        t1 = make_template(seed=41, name="t1")
        screen = embed_template_in_screen(screen, t1, x=100, y=100)
        assert ImageChecker.template_exists(screen, [t1], confidence=0.9)

    def test_not_exists_with_roi(self):
        screen = solid_screen(200, 200, 200)
        tmpl = make_template(seed=42)
        screen = embed_template_in_screen(screen, tmpl, x=10, y=10)
        # ROI 在右半边
        assert not ImageChecker.template_exists(
            screen, tmpl, roi=ROI(0.5, 0.0, 1.0, 1.0), confidence=0.9,
        )


# ─────────────────────────────────────────────
# ImageRule + ImageSignature
# ─────────────────────────────────────────────


class TestImageRuleAndSignature:
    def test_match_rule(self):
        screen = solid_screen(200, 200, 200)
        tmpl = make_template(seed=50, name="btn")
        screen = embed_template_in_screen(screen, tmpl, x=100, y=100)

        rule = ImageRule(name="test_rule", templates=[tmpl], confidence=0.85)
        result = ImageChecker.match_rule(screen, rule)
        assert result.matched
        assert result.best is not None
        assert result.best.template_name == "btn"

    def test_match_rule_with_roi(self):
        screen = solid_screen(200, 200, 200)
        tmpl = make_template(seed=51, name="btn")
        screen = embed_template_in_screen(screen, tmpl, x=100, y=100)

        # ROI 排除模板位置
        rule = ImageRule(
            name="test_rule",
            templates=[tmpl],
            roi=ROI(0.5, 0.5, 1.0, 1.0),
            confidence=0.85,
        )
        result = ImageChecker.match_rule(screen, rule)
        assert not result.matched

    def test_match_rule_multiple_templates(self):
        """多模板规则：任一匹配即可。"""
        screen = solid_screen(200, 200, 200)
        t1 = make_template(seed=52, name="v1")  # 不嵌入 → 不匹配
        t2 = make_template(seed=53, name="v2")
        screen = embed_template_in_screen(screen, t2, x=300, y=200)

        rule = ImageRule(name="confirm", templates=[t1, t2], confidence=0.85)
        result = ImageChecker.match_rule(screen, rule)
        assert result.matched
        assert result.best is not None
        assert result.best.template_name == "v2"

    def test_image_signature_all(self):
        screen = solid_screen(200, 200, 200)
        t1 = make_template(seed=54, name="a")
        t2 = make_template(seed=55, name="b")
        screen = embed_template_in_screen(screen, t1, x=100, y=100)
        screen = embed_template_in_screen(screen, t2, x=500, y=300)

        sig = ImageSignature(
            name="test_page",
            rules=[
                ImageRule(name="r1", templates=[t1], confidence=0.85),
                ImageRule(name="r2", templates=[t2], confidence=0.85),
            ],
            strategy=MatchStrategy.ALL,
        )
        result = ImageChecker.check_signature(screen, sig)
        assert result.matched

    def test_image_signature_any(self):
        screen = solid_screen(200, 200, 200)
        t1 = make_template(seed=56, name="a")
        screen = embed_template_in_screen(screen, t1, x=100, y=100)
        t_miss = make_template(seed=57, name="miss")  # 不嵌入

        sig = ImageSignature(
            name="test_page",
            rules=[
                ImageRule(name="r1", templates=[t1], confidence=0.85),
                ImageRule(name="r2", templates=[t_miss], confidence=0.99),
            ],
            strategy=MatchStrategy.ANY,
        )
        result = ImageChecker.check_signature(screen, sig)
        assert result.matched

    def test_image_signature_all_fails_on_missing(self):
        screen = solid_screen(200, 200, 200)
        t1 = make_template(seed=58, name="a")
        screen = embed_template_in_screen(screen, t1, x=100, y=100)
        t_miss = make_template(seed=59, name="miss")  # 不嵌入

        sig = ImageSignature(
            name="test_page",
            rules=[
                ImageRule(name="r1", templates=[t1], confidence=0.85),
                ImageRule(name="r2", templates=[t_miss], confidence=0.99),
            ],
            strategy=MatchStrategy.ALL,
        )
        result = ImageChecker.check_signature(screen, sig)
        assert not result.matched


# ─────────────────────────────────────────────
# ImageChecker — find_all_occurrences
# ─────────────────────────────────────────────


class TestFindAllOccurrences:
    def test_multiple_occurrences(self):
        """在截图中放置同一模板的多个副本。"""
        screen = solid_screen(200, 200, 200)
        tmpl = make_template(seed=60, h=20, w=30, name="icon")
        # 放两个足够远的副本
        screen = embed_template_in_screen(screen, tmpl, x=100, y=100)
        screen = embed_template_in_screen(screen, tmpl, x=500, y=400)

        results = ImageChecker.find_all_occurrences(
            screen, tmpl, confidence=0.9, min_distance=20,
        )
        assert len(results) >= 2

    def test_with_roi_restriction(self):
        """ROI 限制应排除区域外的副本。"""
        screen = solid_screen(200, 200, 200)
        tmpl = make_template(seed=61, h=20, w=30, name="icon")
        screen = embed_template_in_screen(screen, tmpl, x=100, y=100)
        screen = embed_template_in_screen(screen, tmpl, x=500, y=400)

        # ROI 仅包含左半边
        results = ImageChecker.find_all_occurrences(
            screen, tmpl, roi=ROI(0.0, 0.0, 0.4, 0.5), confidence=0.9,
        )
        assert len(results) == 1


# ─────────────────────────────────────────────
# ImageChecker — identify
# ─────────────────────────────────────────────


class TestIdentify:
    def test_identify_first_match(self):
        screen = solid_screen(200, 200, 200)
        t1 = make_template(seed=70, name="a")
        screen = embed_template_in_screen(screen, t1, x=100, y=100)
        t_miss = make_template(seed=71, name="miss")

        sig1 = ImageSignature(
            name="page_a",
            rules=[ImageRule(name="r1", templates=[t1], confidence=0.85)],
        )
        sig2 = ImageSignature(
            name="page_b",
            rules=[ImageRule(name="r2", templates=[t_miss], confidence=0.99)],
        )
        result = ImageChecker.identify(screen, [sig1, sig2])
        assert result is not None
        assert result.rule_name == "page_a"

    def test_identify_none_when_no_match(self):
        screen = solid_screen(200, 200, 200)
        t_miss = make_template(seed=72, name="miss")
        sig = ImageSignature(
            name="page_x",
            rules=[ImageRule(name="r", templates=[t_miss], confidence=0.99)],
        )
        result = ImageChecker.identify(screen, [sig])
        assert result is None


# ─────────────────────────────────────────────
# ImageChecker.crop
# ─────────────────────────────────────────────


class TestCrop:
    def test_crop_returns_copy(self):
        screen = solid_screen(100, 100, 100)
        roi = ROI(0.0, 0.0, 0.5, 0.5)
        cropped = ImageChecker.crop(screen, roi)
        assert cropped.shape[1] == 480
        assert cropped.shape[0] == 270
        # 修改裁切结果不影响原图
        cropped[0, 0] = [255, 0, 0]
        assert screen[0, 0, 0] == 100


# ─────────────────────────────────────────────
# 多分辨率模板适配
# ─────────────────────────────────────────────


class TestMultiResolutionScaling:
    """测试 per-template source_resolution 适配逻辑。"""

    def test_default_resolution_no_scaling_on_960x540(self):
        """默认 source_resolution=(960,540) 在 960×540 截图上不缩放。"""
        screen = solid_screen(200, 200, 200)  # 960×540
        tmpl = make_template(seed=80, h=30, w=40, name="default_res")
        screen = embed_template_in_screen(screen, tmpl, x=100, y=100)

        detail = ImageChecker.find_template(screen, tmpl, confidence=0.9)
        assert detail is not None
        assert detail.confidence > 0.9

    def test_1080p_template_scaled_to_540p_screen(self):
        """source_resolution=(1920,1080) 的模板在 960×540 截图上应自动缩小。"""
        import numpy as np

        # 创建 960×540 截图
        screen = solid_screen(200, 200, 200, h=540, w=960)

        # 模板采集自 1080p: 60×80 像素 → 在 540p 下应缩放为 30×40
        rng = np.random.RandomState(81)
        big_img = rng.randint(0, 256, (60, 80, 3), dtype=np.uint8)
        from autowsgr.vision import ImageTemplate
        tmpl_1080 = ImageTemplate(
            name="hd_tmpl", image=big_img, source="test",
            source_resolution=(1920, 1080),
        )

        # 手动缩小模板并嵌入截图 (模拟实际匹配场景)
        import cv2
        scaled = cv2.resize(big_img, (40, 30), interpolation=cv2.INTER_AREA)
        tmpl_display = ImageTemplate(name="ld_tmpl", image=scaled, source="test")
        screen = embed_template_in_screen(screen, tmpl_display, x=200, y=150)

        # 1080p 模板应能匹配 540p 截图（引擎自动缩放）
        detail = ImageChecker.find_template(screen, tmpl_1080, confidence=0.85)
        assert detail is not None
        assert detail.confidence > 0.85

    def test_540p_template_scaled_to_1080p_screen(self):
        """source_resolution=(960,540) 的模板在 1920×1080 截图上应自动放大。"""
        import numpy as np

        # 创建 1920×1080 截图
        screen = solid_screen(200, 200, 200, h=1080, w=1920)

        # 模板采集自 540p: 30×40 像素 → 在 1080p 下应缩放为 60×80
        rng = np.random.RandomState(82)
        small_img = rng.randint(0, 256, (30, 40, 3), dtype=np.uint8)
        from autowsgr.vision import ImageTemplate
        tmpl_540 = ImageTemplate(
            name="ld_tmpl", image=small_img, source="test",
            source_resolution=(960, 540),
        )

        # 手动放大模板并嵌入截图
        import cv2
        scaled = cv2.resize(small_img, (80, 60), interpolation=cv2.INTER_LINEAR)
        screen[300:360, 400:480] = scaled

        detail = ImageChecker.find_template(screen, tmpl_540, confidence=0.85)
        assert detail is not None

    def test_mixed_resolution_templates_on_same_screen(self):
        """同一截图上同时使用不同 source_resolution 的模板。"""
        import numpy as np
        import cv2
        from autowsgr.vision import ImageTemplate

        # 1280×720 截图
        screen = solid_screen(200, 200, 200, h=720, w=1280)

        # 模板 A: 采集自 960×540 (30×40) → 在 720p 下缩放为 40×53
        rng_a = np.random.RandomState(83)
        img_a = rng_a.randint(0, 256, (30, 40, 3), dtype=np.uint8)
        tmpl_a = ImageTemplate(
            name="tmpl_a", image=img_a, source="test",
            source_resolution=(960, 540),
        )
        scale_x_a, scale_y_a = 1280 / 960, 720 / 540
        scaled_a = cv2.resize(
            img_a,
            (max(1, round(40 * scale_x_a)), max(1, round(30 * scale_y_a))),
            interpolation=cv2.INTER_LINEAR,
        )
        sa_h, sa_w = scaled_a.shape[:2]
        screen[50: 50 + sa_h, 100: 100 + sa_w] = scaled_a

        # 模板 B: 采集自 1920×1080 (60×80) → 在 720p 下缩放为 40×53
        rng_b = np.random.RandomState(84)
        img_b = rng_b.randint(0, 256, (60, 80, 3), dtype=np.uint8)
        tmpl_b = ImageTemplate(
            name="tmpl_b", image=img_b, source="test",
            source_resolution=(1920, 1080),
        )
        scale_x_b, scale_y_b = 1280 / 1920, 720 / 1080
        scaled_b = cv2.resize(
            img_b,
            (max(1, round(80 * scale_x_b)), max(1, round(60 * scale_y_b))),
            interpolation=cv2.INTER_AREA,
        )
        sb_h, sb_w = scaled_b.shape[:2]
        screen[400: 400 + sb_h, 600: 600 + sb_w] = scaled_b

        # 两个不同分辨率的模板都应能匹配
        detail_a = ImageChecker.find_template(screen, tmpl_a, confidence=0.85)
        assert detail_a is not None, "540p template should match on 720p screen"

        detail_b = ImageChecker.find_template(screen, tmpl_b, confidence=0.85)
        assert detail_b is not None, "1080p template should match on 720p screen"

    def test_source_resolution_preserved_in_template(self):
        """ImageTemplate 应保留 source_resolution 元数据。"""
        import numpy as np
        from autowsgr.vision import ImageTemplate

        # 默认
        img = np.zeros((10, 10, 3), dtype=np.uint8)
        t1 = ImageTemplate(name="t1", image=img)
        assert t1.source_resolution == (960, 540)

        # 自定义
        t2 = ImageTemplate(name="t2", image=img, source_resolution=(1920, 1080))
        assert t2.source_resolution == (1920, 1080)

        # from_ndarray
        t3 = ImageTemplate.from_ndarray(img, "t3", source_resolution=(1280, 720))
        assert t3.source_resolution == (1280, 720)

    def test_repr_shows_non_default_resolution(self):
        """非默认分辨率应在 repr 中显示。"""
        import numpy as np
        from autowsgr.vision import ImageTemplate

        img = np.zeros((10, 10, 3), dtype=np.uint8)
        t_default = ImageTemplate(name="t", image=img)
        assert "source_resolution" not in repr(t_default)

        t_custom = ImageTemplate(name="t", image=img, source_resolution=(1920, 1080))
        assert "source_resolution=(1920, 1080)" in repr(t_custom)

    def test_scale_template_if_needed_with_source_resolution(self):
        """_scale_template_if_needed 应使用传入的 source_resolution。"""
        import numpy as np

        tmpl_img = np.zeros((60, 80, 3), dtype=np.uint8)

        # source_resolution=(1920,1080), screen=960×540 → 缩放到 40×30
        scaled = ImageChecker._scale_template_if_needed(
            tmpl_img, 960, 540, source_resolution=(1920, 1080),
        )
        assert scaled.shape == (30, 40, 3)

        # source_resolution=(960,540), screen=960×540 → 不缩放
        same = ImageChecker._scale_template_if_needed(
            tmpl_img, 960, 540, source_resolution=(960, 540),
        )
        assert same is tmpl_img  # 应返回原对象

        # source_resolution=None → fallback to global (960,540)
        same2 = ImageChecker._scale_template_if_needed(tmpl_img, 960, 540)
        assert same2 is tmpl_img
