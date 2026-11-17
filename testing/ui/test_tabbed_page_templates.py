"""标签页模板完整性回归测试。

背景: 决战 tab 中心 x≈0.698, 曾在地图页模板视野 (左侧 63%) 之外，
导致切到决战 tab 后页面识别全部失败 (NavigationError)。
修复后地图页模板为 743 宽 (裁剪 78%), 决战区域有内容。
若有人用旧裁剪比例重新生成 map.png, 本测试会立即失败。
"""

from autowsgr.ui.tabbed_page import (
    _CROP_X,
    _CROP_X_MAP,
    _REF_W,
    _STRIP_CROP_X,
    TabbedPageType,
    _get_templates,
    _ref_width,
)


def test_map_crop_width_covers_decisive_tab():
    """地图页裁剪比例必须覆盖决战 tab (右缘 ≈0.76)。"""
    assert _STRIP_CROP_X[TabbedPageType.MAP] == _CROP_X_MAP
    assert _CROP_X_MAP >= 0.78


def test_template_widths_match_crop_ratio():
    """每个模板的宽度必须与其页面类型的裁剪比例对应。"""
    templates = _get_templates()
    assert set(templates) == set(_STRIP_CROP_X)
    for page_type, tmpl in templates.items():
        assert tmpl.shape == (40, _ref_width(_STRIP_CROP_X[page_type])), page_type


def test_map_template_has_decisive_content():
    """地图模板超出默认 600 宽的部分 (决战 tab 区域) 必须有白色像素。"""
    map_tmpl = _get_templates()[TabbedPageType.MAP]
    assert map_tmpl.shape[1] > _REF_W
    assert map_tmpl[:, _REF_W:].any()
    # 非地图页模板仍为基准宽度
    for page_type, tmpl in _get_templates().items():
        if page_type is not TabbedPageType.MAP:
            assert tmpl.shape[1] == _ref_width(_CROP_X), page_type
