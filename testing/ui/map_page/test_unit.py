"""测试 地图页面 UI 控制器。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from autowsgr.emulator import AndroidController
from autowsgr.ui.map.data import (
    CHAPTER_MAP_COUNTS,
    CHAPTER_NAV_DELAY,
    CHAPTER_SPACING,
    CLICK_BACK,
    EXPEDITION_NOTIF_PROBE,
    MAP_DATABASE,
    SIDEBAR_BRIGHTNESS_THRESHOLD,
    SIDEBAR_CLICK_X,
    SIDEBAR_SCAN_X,
    SIDEBAR_SCAN_Y_RANGE,
    TOTAL_CHAPTERS,
    MapIdentity,
    parse_map_title,
)
from autowsgr.ui.map.data import CLICK_PANEL, MapPanel
from autowsgr.ui.map.page import MapPage
from autowsgr.ui.tabbed_page import (
    TAB_BLUE,
    TAB_DARK,
    TAB_PROBES,
    TabbedPageType,
)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────



class TestParseMapTitle:
    def test_standard_format(self):
        info = parse_map_title("9-5南大洋群岛")
        assert info is not None
        assert info.chapter == 9
        assert info.map_num == 5
        assert info.name == "南大洋群岛"

    def test_with_slash(self):
        info = parse_map_title("9-5/南大洋群岛")
        assert info is not None
        assert info.chapter == 9
        assert info.map_num == 5
        assert info.name == "南大洋群岛"

    def test_with_spaces(self):
        info = parse_map_title("3 - 4 星洲海峡")
        assert info is not None
        assert info.chapter == 3
        assert info.map_num == 4
        # DB name takes precedence
        assert info.name == "星洲海峡"

    def test_numbers_only(self):
        info = parse_map_title("1-1")
        assert info is not None
        assert info.chapter == 1
        assert info.map_num == 1
        # 数据库中有 (1,1) → "母港附近海域"
        assert info.name == "母港附近海域"

    def test_numbers_only_unknown(self):
        """未在数据库中的编号保持空名称。"""
        info = parse_map_title("1-9")
        assert info is not None
        assert info.chapter == 1
        assert info.map_num == 9
        assert info.name == ""

    def test_with_full_width_slash(self):
        info = parse_map_title("5-3／马耳他附近海域")
        assert info is not None
        assert info.chapter == 5
        assert info.map_num == 3
        assert info.name == "马耳他附近海域"

    def test_em_dash(self):
        info = parse_map_title("7—2珊瑚海")
        assert info is not None
        assert info.chapter == 7
        assert info.map_num == 2

    def test_invalid_text(self):
        assert parse_map_title("无效文本") is None
        assert parse_map_title("") is None
        assert parse_map_title("abc") is None

    def test_raw_text_preserved(self):
        raw = "9-5/南大洋群岛"
        info = parse_map_title(raw)
        assert info is not None
        assert info.raw_text == raw

    # ── OCR 校正测试 ──

    def test_ocr_correction_951(self):
        """OCR 读出 "9-51南大洋群岛" → 应校正为 9-5 南大洋群岛。"""
        info = parse_map_title("9-51南大洋群岛")
        assert info is not None
        assert info.chapter == 9
        assert info.map_num == 5
        assert info.name == "南大洋群岛"

    def test_ocr_correction_911(self):
        """OCR 读出 "9-11地峡外海" → 应校正为 9-1 地峡外海。"""
        info = parse_map_title("9-11地峡外海")
        assert info is not None
        assert info.chapter == 9
        assert info.map_num == 1
        assert info.name == "地峡外海"

    def test_ocr_correction_uses_db_name(self):
        """OCR 校正后使用数据库名称。"""
        info = parse_map_title("9-51大洋群岛")
        assert info is not None
        assert info.chapter == 9
        assert info.map_num == 5
        # 使用数据库名称而非 OCR 残余
        assert info.name == "南大洋群岛"

    def test_single_digit_preferred(self):
        """单位数匹配优先于多位数 (如 "1-1" 不被拆成 "1-1")。"""
        info = parse_map_title("1-1母港附近海域")
        assert info is not None
        assert info.chapter == 1
        assert info.map_num == 1
        assert info.name == "母港附近海域"

    def test_ocr_correction_81(self):
        """OCR 读出 "8-11百慕大中心海域" → 应校正为 8-1。"""
        info = parse_map_title("8-11百慕大中心海域")
        assert info is not None
        assert info.chapter == 8
        assert info.map_num == 1
        assert info.name == "百慕大中心海域"


# ─────────────────────────────────────────────
# MAP_DATABASE 完整性
# ─────────────────────────────────────────────


class TestMapDatabase:
    def test_all_chapters_present(self):
        """数据库包含 1–9 章。"""
        chapters = {ch for ch, _ in MAP_DATABASE}
        assert chapters == set(range(1, 10))

    def test_chapter_map_counts(self):
        """每章至少 4 张地图。"""
        for ch in range(1, 10):
            assert ch in CHAPTER_MAP_COUNTS
            assert CHAPTER_MAP_COUNTS[ch] >= 4

    def test_known_maps(self):
        """抽检几个已知地图。"""
        assert MAP_DATABASE[(1, 1)] == "母港附近海域"
        assert MAP_DATABASE[(9, 5)] == "南大洋群岛"
        assert MAP_DATABASE[(5, 5)] == "直布罗陀要塞"
        assert MAP_DATABASE[(8, 5)] == "地峡海湾"

    def test_total_map_count(self):
        """总地图数量检查 (9章, 共 ~40+ 张)。"""
        assert len(MAP_DATABASE) >= 40


# ─────────────────────────────────────────────
# 动作 — 章节导航
# ─────────────────────────────────────────────


class TestNavigateToChapter:
    def test_invalid_chapter_raises(self):
        ctrl = MagicMock(spec=AndroidController)
        ocr = MagicMock()
        pg = MapPage(ctrl, ocr=ocr)
        with pytest.raises(ValueError, match="1–9"):
            pg.navigate_to_chapter(0)
        with pytest.raises(ValueError, match="1–9"):
            pg.navigate_to_chapter(10)

    def test_no_ocr_raises(self):
        ctrl = MagicMock(spec=AndroidController)
        pg = MapPage(ctrl, ocr=None)
        with pytest.raises(RuntimeError, match="OCR"):
            pg.navigate_to_chapter(5)
