"""测试 autowsgr.ui.map.data."""

from __future__ import annotations

import pytest

from autowsgr.ui.map.data import (
    CHAPTER_MAP_COUNTS,
    CLICK_PANEL,
    PANEL_LIST,
    PANEL_TO_INDEX,
    TOTAL_CHAPTERS,
    MapIdentity,
    MapPanel,
    parse_map_title,
)


# ── MapIdentity ──


def test_map_identity_construction() -> None:
    """MapIdentity 应正确保存字段值。"""
    identity = MapIdentity(chapter=9, map_num=5, name='南大洋群岛', raw_text='9-5南大洋群岛')
    assert identity.chapter == 9
    assert identity.map_num == 5
    assert identity.name == '南大洋群岛'
    assert identity.raw_text == '9-5南大洋群岛'


# ── CHAPTER_MAP_COUNTS / TOTAL_CHAPTERS ──


def test_chapter_map_counts_derived() -> None:
    """CHAPTER_MAP_COUNTS 应从 MAP_DATABASE 正确推算。"""
    assert CHAPTER_MAP_COUNTS[1] == 5
    assert CHAPTER_MAP_COUNTS[2] == 6
    assert CHAPTER_MAP_COUNTS[9] == 5
    assert CHAPTER_MAP_COUNTS[10] == 1


def test_total_chapters_matches_counts() -> None:
    """TOTAL_CHAPTERS 应等于 CHAPTER_MAP_COUNTS 的长度。"""
    assert len(CHAPTER_MAP_COUNTS) == TOTAL_CHAPTERS


# ── parse_map_title ──


def test_parse_map_title_basic() -> None:
    """解析常规格式 ``章节-关卡名称``。"""
    result = parse_map_title('9-5南大洋群岛')
    assert result is not None
    assert result.chapter == 9
    assert result.map_num == 5
    assert result.name == '南大洋群岛'


def test_parse_map_title_with_slash() -> None:
    """解析带 ``/`` 分隔符的格式。"""
    result = parse_map_title('9-5/南大洋群岛')
    assert result is not None
    assert result.chapter == 9
    assert result.map_num == 5
    assert result.name == '南大洋群岛'


def test_parse_map_title_with_spaces() -> None:
    """解析带空格的格式。"""
    result = parse_map_title('9 - 5 南大洋群岛')
    assert result is not None
    assert result.chapter == 9
    assert result.map_num == 5
    assert result.name == '南大洋群岛'


def test_parse_map_title_chapter_ten() -> None:
    """解析两位数章节号。"""
    result = parse_map_title('10-1极地海峡')
    assert result is not None
    assert result.chapter == 10
    assert result.map_num == 1
    assert result.name == '极地海峡'


@pytest.mark.parametrize(
    'text',
    [
        '',
        'abc',
        '无数字',
        '--',
    ],
)
def test_parse_map_title_invalid(text: str) -> None:
    """无效文本应返回 None。"""
    assert parse_map_title(text) is None


# ── MapPanel enum ──


def test_map_panel_members_exist() -> None:
    """MapPanel 应包含预期成员。"""
    assert MapPanel.SORTIE.value == '出征'
    assert MapPanel.EXERCISE.value == '演习'
    assert MapPanel.EXPEDITION.value == '远征'
    assert MapPanel.BATTLE.value == '战役'
    assert MapPanel.DECISIVE.value == '决战'


def test_panel_list_length() -> None:
    """PANEL_LIST 长度应与 MapPanel 成员数一致。"""
    assert len(PANEL_LIST) == len(MapPanel)


def test_panel_to_index_is_bijection() -> None:
    """PANEL_TO_INDEX 应为每个 MapPanel 成员分配唯一且连续的索引。"""
    assert set(PANEL_TO_INDEX.keys()) == set(MapPanel)
    indices = list(PANEL_TO_INDEX.values())
    assert sorted(indices) == list(range(len(MapPanel)))
    assert len(set(indices)) == len(indices)


def test_click_panel_keys_match_map_panel() -> None:
    """CLICK_PANEL 的键应恰好覆盖所有 MapPanel 成员。"""
    assert set(CLICK_PANEL.keys()) == set(MapPanel)
