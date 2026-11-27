"""回归覆盖：活动徽章「战利品↑」不得导致地图页识别失败。

徽章是活动期间的临时叠加物，挂在出征 tab 上方、位置固定。它不进参考模板，
而是在匹配前用色探针探测、命中时把徽章区从测试条带抹掉。

测试全部使用合成帧（深色底 + 按参考模板布局的白色文字 + 按实测几何画的
橙色徽章），不依赖真实截图。
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from autowsgr.ui import tabbed_page as tp


_BG = (22, 37, 62)
"""标签栏背景色 (RGB)。"""

_WHITE = (255, 255, 255)

_BADGE_ORANGE = (246, 93, 56)
"""徽章底色 (实测 RGB) — 独立于被测常量，避免自证。"""

_BADGE_BOX = (0.2213, 0.2769, 0.0133, 0.047)
"""徽章 bbox ``(x0, x1, y0, y1)`` (实测相对坐标)。"""

_RESOLUTIONS = [(960, 540), (1280, 720), (1600, 896)]


def _render_frame(page_type: tp.TabbedPageType, width: int, height: int) -> np.ndarray:
    """按参考模板的白色像素布局渲染一帧标签栏（无徽章）。"""
    tmpl = tp._get_templates()[page_type]
    x_end = tp._STRIP_CROP_X[page_type]
    screen = np.full((height, width, 3), _BG, dtype=np.uint8)
    crop_h, crop_w = int(height * tp._CROP_Y), int(width * x_end)
    layout = (
        cv2.resize(tmpl.astype(np.uint8), (crop_w, crop_h), interpolation=cv2.INTER_NEAREST) > 0
    )
    screen[:crop_h, :crop_w][layout] = _WHITE
    return screen


def _add_loot_badge(screen: np.ndarray) -> np.ndarray:
    """在帧上叠加橙色徽章（含「战利品↑」四个字的白色实底）。

    白色文字只占徽章中段，左右各留 20% 橙色边缘 —— 与实测一致，
    探测点正落在这两条橙色边缘上。
    """
    out = screen.copy()
    height, width = out.shape[:2]
    x0, x1, y0, y1 = _BADGE_BOX
    left, right = int(x0 * width), int(x1 * width)
    top, bottom = int(y0 * height), int(y1 * height)
    cv2.rectangle(out, (left, top), (right, bottom), _BADGE_ORANGE, -1)
    text_left, text_right = left + int((right - left) * 0.2), right - int((right - left) * 0.2)
    slot = (text_right - text_left) / 4
    for i in range(4):
        char_left = int(text_left + slot * i + slot * 0.15)
        char_right = int(text_left + slot * (i + 1) - slot * 0.15)
        cv2.rectangle(out, (char_left, top + 6), (char_right, bottom - 8), _WHITE, -1)
    return out


def _map_score(screen: np.ndarray) -> float:
    """未经排除逻辑的 MAP 覆盖度基线。"""
    tmpl = tp._get_templates()[tp.TabbedPageType.MAP]
    return tp._coverage(tp._binarize_tabbar(screen, tp._CROP_X_MAP), tmpl)


@pytest.mark.parametrize(('width', 'height'), _RESOLUTIONS)
def test_badge_present_still_identifies_map(width: int, height: int) -> None:
    """徽章在场时地图页仍被识别（覆盖度需 > 0.6 阈值）。"""
    screen = _add_loot_badge(_render_frame(tp.TabbedPageType.MAP, width, height))

    assert tp._loot_badge_visible(screen) is True
    matched = tp._match_page_type(screen)
    assert matched is not None
    assert matched[0] is tp.TabbedPageType.MAP
    assert matched[1] > 0.6


@pytest.mark.parametrize(('width', 'height'), _RESOLUTIONS)
def test_badge_exclusion_lifts_score(width: int, height: int) -> None:
    """排除徽章区必须抬高覆盖度（含徽章帧的分数高于未抹除的基线）。"""
    screen = _add_loot_badge(_render_frame(tp.TabbedPageType.MAP, width, height))

    masked = tp._match_page_type(screen)
    assert masked is not None
    assert masked[1] - _map_score(screen) > 0.005


@pytest.mark.parametrize(('width', 'height'), _RESOLUTIONS)
def test_badge_does_not_degrade_clean_score(width: int, height: int) -> None:
    """叠加徽章再排除后，分数不低于同帧无徽章时的分数。"""
    clean = _render_frame(tp.TabbedPageType.MAP, width, height)
    badged = _add_loot_badge(clean)

    clean_matched = tp._match_page_type(clean)
    badged_matched = tp._match_page_type(badged)
    assert clean_matched is not None
    assert badged_matched is not None
    assert badged_matched[1] >= clean_matched[1] - 0.01


@pytest.mark.parametrize(('width', 'height'), _RESOLUTIONS)
def test_clean_frame_is_never_masked(width: int, height: int) -> None:
    """探针未命中时匹配路径与修复前完全一致（不抹任何像素）。"""
    screen = _render_frame(tp.TabbedPageType.MAP, width, height)

    assert tp._loot_badge_visible(screen) is False
    matched = tp._match_page_type(screen)
    assert matched is not None
    assert matched[0] is tp.TabbedPageType.MAP
    # 分数与「未经过排除逻辑」的覆盖度逐值一致 → 条带未被改动
    assert matched[1] == pytest.approx(_map_score(screen), abs=1e-12)


@pytest.mark.parametrize(('width', 'height'), _RESOLUTIONS)
@pytest.mark.parametrize(
    'page_type', [p for p in tp.TabbedPageType if p is not tp.TabbedPageType.MAP]
)
def test_badge_never_turns_other_pages_into_map(
    width: int, height: int, page_type: tp.TabbedPageType
) -> None:
    """其他页面的帧叠加徽章后不得被误判成地图页。"""
    screen = _add_loot_badge(_render_frame(page_type, width, height))

    matched = tp._match_page_type(screen)
    assert matched is None or matched[0] is not tp.TabbedPageType.MAP


def _paint(screen: np.ndarray, x: float, y: float, color: tuple[int, int, int]) -> None:
    """把相对坐标所在的像素刷成 *color*（覆盖取整误差）。"""
    height, width = screen.shape[:2]
    px, py = int(x * width), int(y * height)
    screen[py - 2 : py + 3, px - 2 : px + 3] = color


def _blank_frame() -> np.ndarray:
    return np.full((90, 160, 3), _BG, dtype=np.uint8)


def test_probes_inside_exclusion_region() -> None:
    """两个探测点必须落在排除区内。"""
    x0, x1, y0, y1 = tp.LOOT_BADGE_MASK_REL
    for x, y in tp.LOOT_BADGE_PROBES:
        assert x0 < x < x1
        assert y0 < y < y1


def test_probe_hits_badge_body() -> None:
    """探针落在徽章橙底上 → 命中。"""
    screen = _blank_frame()
    for x, y in tp.LOOT_BADGE_PROBES:
        _paint(screen, x, y, _BADGE_ORANGE)

    assert tp._loot_badge_visible(screen) is True


def test_probe_requires_both_points() -> None:
    """单个探测点命中不算徽章在场。"""
    screen = _blank_frame()
    _paint(screen, *tp.LOOT_BADGE_PROBES[0], _BADGE_ORANGE)

    assert tp._loot_badge_visible(screen) is False


@pytest.mark.parametrize(
    'color',
    [
        (22, 37, 62),  # 标签栏深色底
        (15, 132, 228),  # 蓝色激活标签
        (255, 255, 255),  # 徽章内的白色文字
        (255, 140, 60),  # 其他橙色 UI（超出容差）
    ],
)
def test_probe_rejects_non_badge_colors(color: tuple[int, int, int]) -> None:
    """深色底 / 蓝色标签 / 白字 / 其他橙色 UI 均不命中。"""
    screen = _blank_frame()
    for x, y in tp.LOOT_BADGE_PROBES:
        _paint(screen, x, y, color)

    assert tp._loot_badge_visible(screen) is False
