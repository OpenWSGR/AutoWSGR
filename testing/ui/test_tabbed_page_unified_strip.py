"""回归覆盖：所有候选必须共用同一条标签栏条带。

背景: 覆盖度 ``|test ∩ template| / |test|`` 的分母是「条带里的白像素总数」。
若地图页裁到 76.5% (729 px) 而其余页面裁到 63% (600 px)，同一块屏幕区域在
两个候选里占分母的比例不同 —— 分母小的候选遇到叠加物 (活动徽章、资源计
数器) 时涨得更快，分数失去可比性, 地图页会被判成建造页。

修复后 :func:`score_all_pages` 只生成一条条带 (统一裁到 ``_CROP_X_MAP``),
600 宽的模板右侧补齐空白后再比较。
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from autowsgr.ui import tabbed_page as tp


_BG = (22, 37, 62)
_WHITE = (255, 255, 255)
_RESOLUTIONS = [(960, 540), (1280, 720), (1600, 896)]


def _render_frame(page_type: tp.TabbedPageType, width: int, height: int) -> np.ndarray:
    """按参考模板的白色像素布局渲染一帧标签栏。"""
    tmpl = tp._get_templates()[page_type]
    x_end = tp._STRIP_CROP_X[page_type]
    screen = np.full((height, width, 3), _BG, dtype=np.uint8)
    crop_h, crop_w = int(height * tp._CROP_Y), int(width * x_end)
    layout = (
        cv2.resize(tmpl.astype(np.uint8), (crop_w, crop_h), interpolation=cv2.INTER_NEAREST) > 0
    )
    screen[:crop_h, :crop_w][layout] = _WHITE
    return screen


@pytest.mark.parametrize(('width', 'height'), _RESOLUTIONS)
def test_matching_binarizes_one_strip_only(
    monkeypatch: pytest.MonkeyPatch, width: int, height: int
) -> None:
    """匹配过程只生成一条条带, 且宽度为地图页裁剪宽度。"""
    calls: list[float] = []
    original = tp._binarize_tabbar

    def _spy(screen: np.ndarray, x_end: float = tp._CROP_X) -> np.ndarray:
        calls.append(x_end)
        return original(screen, x_end)

    monkeypatch.setattr(tp, '_binarize_tabbar', _spy)
    tp._match_page_type(_render_frame(tp.TabbedPageType.MAP, width, height))

    assert calls == [tp._CROP_X_MAP]


@pytest.mark.parametrize(('width', 'height'), _RESOLUTIONS)
def test_all_scores_share_the_same_denominator(width: int, height: int) -> None:
    """每个分数都等于「同一条带上」的命中比例。"""
    screen = _render_frame(tp.TabbedPageType.MAP, width, height)
    strip = tp._binarize_tabbar(screen, tp._CROP_X_MAP)
    scores = tp.score_all_pages(screen)

    assert set(scores) == set(tp.TabbedPageType)
    for page_type, score in scores.items():
        padded = tp._pad_template(tp._get_templates()[page_type], strip.shape[1])
        expected = float((strip & padded).sum()) / int(strip.sum())
        assert score == pytest.approx(expected, abs=1e-12), page_type


def test_pad_template_preserves_hits() -> None:
    """补空不改变命中数, 只补右侧空白列。"""
    tmpl = tp._get_templates()[tp.TabbedPageType.BUILD]
    test = tmpl.copy()
    strip_width = tp._ref_width(tp._CROP_X_MAP)
    pad = strip_width - tmpl.shape[1]

    padded = tp._pad_template(tmpl, strip_width)

    assert padded.shape == (tmpl.shape[0], strip_width)
    assert pad > 0
    assert not padded[:, tmpl.shape[1] :].any()
    overlap = int((test & padded[:, : test.shape[1]]).sum())
    assert overlap == int((test & tmpl).sum())


def test_pad_template_crops_when_wider() -> None:
    """目标宽度小于模板时按左侧截断。"""
    tmpl = tp._get_templates()[tp.TabbedPageType.MAP]
    narrower = tp._pad_template(tmpl, tp._REF_W)

    assert narrower.shape == (tmpl.shape[0], tp._REF_W)
    assert np.array_equal(narrower, tmpl[:, : tp._REF_W])


@pytest.mark.parametrize(('width', 'height'), _RESOLUTIONS)
def test_map_frame_beats_build_by_clear_margin(width: int, height: int) -> None:
    """地图帧上建造模板必须明显落后 (统一分母后不再靠窄分母占便宜)。"""
    scores = tp.score_all_pages(_render_frame(tp.TabbedPageType.MAP, width, height))

    assert scores[tp.TabbedPageType.MAP] - scores[tp.TabbedPageType.BUILD] > 0.1


@pytest.mark.parametrize(('width', 'height'), _RESOLUTIONS)
@pytest.mark.parametrize(
    'page_type', [p for p in tp.TabbedPageType if p is not tp.TabbedPageType.MAP]
)
def test_other_pages_are_not_read_as_map(
    width: int, height: int, page_type: tp.TabbedPageType
) -> None:
    """其他页面帧的第一名不得是地图模板。

    注: 合成的好友帧目前排第一的是建造模板 (0.65 对自身 0.61), 属于
    「模板越大越容易吸收别人」的既有问题, 与本文件的统一条带无关。
    """
    scores = tp.score_all_pages(_render_frame(page_type, width, height))
    winner = max(scores, key=lambda key: scores[key])

    assert winner is not tp.TabbedPageType.MAP


def test_scores_are_bounded() -> None:
    """覆盖度必落在 [0, 1]。"""
    scores = tp.score_all_pages(_render_frame(tp.TabbedPageType.MAP, 1600, 896))

    assert all(0.0 <= score <= 1.0 for score in scores.values())
