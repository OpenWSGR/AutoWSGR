"""Tests for autowsgr.ui.navigation."""

from __future__ import annotations

import dataclasses

import pytest

from autowsgr.types import PageName
from autowsgr.ui.navigation import NAV_GRAPH, NavEdge, find_path


def test_nav_edge_is_frozen() -> None:
    """NavEdge instances should be frozen dataclass objects."""
    edge = NavEdge(
        PageName.MAIN,
        PageName.MAP,
        lambda _ctx: None,
        'test',
    )
    assert edge.__dataclass_params__.frozen is True
    with pytest.raises(dataclasses.FrozenInstanceError):
        edge.source = PageName.MAP  # ty: ignore[invalid-assignment]


def test_find_path_same_page_returns_empty_list() -> None:
    """find_path from a page to itself should return an empty list."""
    path = find_path(PageName.MAIN, PageName.MAIN)
    assert path == []


def test_find_path_main_to_map() -> None:
    """MAIN to MAP should be a single edge."""
    path = find_path(PageName.MAIN, PageName.MAP)
    assert path is not None
    assert len(path) == 1
    assert path[0].source == PageName.MAIN
    assert path[0].target == PageName.MAP


def test_find_path_map_to_main() -> None:
    """MAP to MAIN should be a single edge."""
    path = find_path(PageName.MAP, PageName.MAIN)
    assert path is not None
    assert len(path) == 1
    assert path[0].source == PageName.MAP
    assert path[0].target == PageName.MAIN


def test_find_path_main_to_bath() -> None:
    """MAIN to BATH should be MAIN -> BACKYARD -> BATH (2 edges)."""
    path = find_path(PageName.MAIN, PageName.BATH)
    assert path is not None
    assert len(path) == 2
    assert path[0].source == PageName.MAIN
    assert path[0].target == PageName.BACKYARD
    assert path[1].source == PageName.BACKYARD
    assert path[1].target == PageName.BATH


def test_find_path_main_to_build() -> None:
    """MAIN to BUILD should be MAIN -> SIDEBAR -> BUILD (2 edges)."""
    path = find_path(PageName.MAIN, PageName.BUILD)
    assert path is not None
    assert len(path) == 2
    assert path[0].source == PageName.MAIN
    assert path[0].target == PageName.SIDEBAR
    assert path[1].source == PageName.SIDEBAR
    assert path[1].target == PageName.BUILD


def test_find_path_build_to_bath() -> None:
    """BUILD to BATH should return a valid multi-hop path."""
    path = find_path(PageName.BUILD, PageName.BATH)
    assert path is not None
    assert len(path) > 1
    assert path[0].source == PageName.BUILD
    assert path[-1].target == PageName.BATH
    for i in range(len(path) - 1):
        assert path[i].target == path[i + 1].source


def test_find_path_unknown_page_raises() -> None:
    """find_path with an unknown page name should raise ValueError."""
    with pytest.raises(ValueError, match='不是合法的 PageName 取值'):
        find_path('unknown_page', PageName.MAIN)
    with pytest.raises(ValueError, match='不是合法的 PageName 取值'):
        find_path(PageName.MAIN, 'unknown_page')


def test_nav_graph_no_duplicate_edges() -> None:
    """NAV_GRAPH should not contain duplicate edges in the same direction."""
    seen: set[tuple[PageName, PageName]] = set()
    for edge in NAV_GRAPH:
        key = (edge.source, edge.target)
        assert key not in seen, f'Duplicate edge: {edge.source.value} -> {edge.target.value}'
        seen.add(key)


def test_nav_graph_edges_use_valid_page_names() -> None:
    """Every edge's source and target should be a valid PageName value."""
    for edge in NAV_GRAPH:
        assert isinstance(edge.source, PageName)
        assert isinstance(edge.target, PageName)
