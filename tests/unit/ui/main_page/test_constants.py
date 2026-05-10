"""测试 autowsgr.ui.main_page.constants."""

from __future__ import annotations

from autowsgr.ui.main_page.constants import (
    _SIGNATURES,
    _TARGET_PAGES,
    DismissCoord,
    NavCoord,
    OverlayKind,
    ProbePoint,
    Sig,
    Target,
    ThemeColor,
)
from autowsgr.vision import Color, PixelSignature


def test_target_members_have_expected_values() -> None:
    """Target 各成员的值与预期一致。"""
    assert Target.SORTIE.value == '出征'
    assert Target.TASK.value == '任务'
    assert Target.SIDEBAR.value == '侧边栏'
    assert Target.HOME.value == '主页'
    assert Target.EVENT.value == '活动'


def test_every_target_has_page_name() -> None:
    """每个 Target 成员都在 _TARGET_PAGES 中有对应映射，且 page_name 返回 str。"""
    assert len(_TARGET_PAGES) == len(Target)
    for member in Target:
        assert member in _TARGET_PAGES
        page_name = member.page_name
        assert isinstance(page_name, str)
        assert page_name == _TARGET_PAGES[member]


def test_nav_coord_xy_in_range() -> None:
    """NavCoord 各成员的 xy 为两元素 float 元组，取值在 [0, 1] 内。"""
    for member in NavCoord:
        xy = member.xy
        assert isinstance(xy, tuple)
        assert len(xy) == 2
        x, y = xy
        assert isinstance(x, float)
        assert isinstance(y, float)
        assert 0.0 <= x <= 1.0
        assert 0.0 <= y <= 1.0


def test_probe_point_xy_in_range() -> None:
    """ProbePoint 各成员的 xy 为两元素 float 元组，取值在 [0, 1] 内。"""
    for member in ProbePoint:
        xy = member.xy
        assert isinstance(xy, tuple)
        assert len(xy) == 2
        x, y = xy
        assert isinstance(x, float)
        assert isinstance(y, float)
        assert 0.0 <= x <= 1.0
        assert 0.0 <= y <= 1.0


def test_dismiss_coord_xy_in_range() -> None:
    """DismissCoord 各成员的 xy 为两元素 float 元组，取值在 [0, 1] 内。"""
    for member in DismissCoord:
        xy = member.xy
        assert isinstance(xy, tuple)
        assert len(xy) == 2
        x, y = xy
        assert isinstance(x, float)
        assert isinstance(y, float)
        assert 0.0 <= x <= 1.0
        assert 0.0 <= y <= 1.0


def test_theme_color_properties() -> None:
    """ThemeColor 各成员的 color 为 Color 实例，tolerance 为 float。"""
    for member in ThemeColor:
        assert isinstance(member.color, Color)
        assert isinstance(member.tolerance, float)


def test_sig_ps_returns_pixel_signature() -> None:
    """Sig 各成员的 ps 返回 PixelSignature 实例。"""
    for member in Sig:
        assert isinstance(member.ps, PixelSignature)


def test_signatures_has_entry_for_every_sig() -> None:
    """_SIGNATURES 包含所有 Sig 成员。"""
    assert len(_SIGNATURES) == len(Sig)
    for member in Sig:
        assert member in _SIGNATURES
        assert isinstance(_SIGNATURES[member], PixelSignature)


def test_overlay_kind_members_exist() -> None:
    """OverlayKind 包含预期的成员。"""
    assert len(OverlayKind) == 3
    assert OverlayKind.NEWS.value == '新闻公告'
    assert OverlayKind.SIGN.value == '每日签到'
    assert OverlayKind.BOOKING.value == '活动预约'
