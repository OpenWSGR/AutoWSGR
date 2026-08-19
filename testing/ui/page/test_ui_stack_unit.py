"""UIStack 导航栈的无设备单元测试。

拓扑断言依赖真实 NAV_GRAPH:
    MAIN 邻居 = {MAP, MISSION, BACKYARD, SIDEBAR, EVENT_MAP}
    BACKYARD 邻居 = {MAIN, BATH, CANTEEN}
    BATH 邻居 = {BACKYARD}
    MAP 邻居 = {MAIN, DECISIVE_BATTLE}
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from autowsgr.types import PageName as P
from autowsgr.ui import stack as stack_mod
from autowsgr.ui.stack import UIStack


if TYPE_CHECKING:
    import pytest


def _frame(marker: int) -> np.ndarray:
    """构造可区分的假截图。"""
    return np.full((2, 2, 3), marker, dtype=np.uint8)


# ═══════════════════════════════════════════════════════════════════════════════
# 栈操作
# ═══════════════════════════════════════════════════════════════════════════════


def test_empty_stack_query() -> None:
    """空栈:current/parent 为 None,pop 返回 None,候选集为空。"""
    s = UIStack()
    assert s.current is None
    assert s.parent is None
    assert s.pop() is None
    assert s.candidates() == set()
    assert s.candidates(P.BATH) == {P.BATH.value, P.BACKYARD.value}


def test_push_updates_current_parent() -> None:
    s = UIStack()
    s.push(P.MAIN)
    assert (s.current, s.parent, s.depth) == (P.MAIN.value, None, 1)
    s.push(P.BACKYARD)
    assert (s.current, s.parent, s.depth) == (P.BACKYARD.value, P.MAIN.value, 2)


def test_push_same_page_refreshes_not_duplicates() -> None:
    """同页重入 (如浮层开合) 不叠重复帧。"""
    s = UIStack()
    s.push(P.MAIN, screen=_frame(1))
    s.push(P.MAIN, screen=_frame(2))
    assert s.depth == 1
    assert s.snapshot(P.MAIN) is not None


def test_pop_returns_top_and_shrinks() -> None:
    s = UIStack()
    s.push(P.MAIN)
    s.push(P.BACKYARD)
    assert s.pop() == P.BACKYARD.value
    assert s.current == P.MAIN.value


def test_max_depth_trims_oldest() -> None:
    """超过 max_depth 时丢弃最老帧。"""
    s = UIStack(max_depth=3)
    for page in (P.MAIN, P.BACKYARD, P.BATH, P.MAIN, P.BACKYARD):
        s.push(page)
    assert s.pages() == (P.BATH.value, P.MAIN.value, P.BACKYARD.value)


# ═══════════════════════════════════════════════════════════════════════════════
# 候选集
# ═══════════════════════════════════════════════════════════════════════════════


def test_candidates_formula() -> None:
    """candidates = {current} + neighbors(current) + {parent} + {target} + neighbors(target)。"""
    s = UIStack()
    s.push(P.MAIN)
    s.push(P.BACKYARD)
    # current=BACKYARD 邻居 {MAIN,BATH,CANTEEN};parent=MAIN;target=BATH 邻居 {BACKYARD}
    expected = (
        {P.BACKYARD.value, P.MAIN.value, P.BATH.value, P.CANTEEN.value}
        | {P.MAIN.value}
        | {P.BATH.value, P.BACKYARD.value}
    )
    assert s.candidates(P.BATH) == expected


def test_candidates_includes_parent_for_leaf_pages() -> None:
    """无入边叶子页 (BATTLE_PREP) 的来路只在栈中:parent 必须进候选。"""
    s = UIStack()
    s.push(P.MAP)
    s.push(P.BATTLE_PREP)
    assert s.parent == P.MAP.value
    assert P.MAP.value in s.candidates()


def test_candidates_accepts_page_name_and_str() -> None:
    s = UIStack()
    s.push(P.MAIN)
    assert s.candidates(P.MAP) == s.candidates(P.MAP.value)


# ═══════════════════════════════════════════════════════════════════════════════
# observe 对账四分支
# ═══════════════════════════════════════════════════════════════════════════════


def test_observe_empty_stack_pushes_root() -> None:
    s = UIStack()
    assert s.observe(P.BACKYARD) == P.BACKYARD.value
    assert s.pages() == (P.BACKYARD.value,)


def test_observe_same_page_refreshes_frame() -> None:
    s = UIStack()
    s.push(P.BACKYARD, screen=_frame(1))
    assert s.observe(P.BACKYARD, screen=_frame(2)) == P.BACKYARD.value
    assert s.depth == 1
    assert s.snapshot(P.BACKYARD) is not None


def test_observe_parent_pops() -> None:
    """识别为父页 → 自然回退,pop 回收来路。"""
    s = UIStack()
    s.push(P.MAIN)
    s.push(P.BACKYARD)
    s.push(P.BATH)
    assert s.observe(P.BACKYARD) == P.BACKYARD.value
    assert s.pages() == (P.MAIN.value, P.BACKYARD.value)


def test_observe_parent_branch_wins_over_neighbor() -> None:
    """父页同时在 neighbors(current) 中 (双向边 MAP↔MAIN) 时,优先 pop 而非 push。"""
    s = UIStack()
    s.push(P.MAIN)
    s.push(P.MAP)  # MAIN ∈ neighbors(MAP) (双向边 MAP→MAIN)
    assert s.observe(P.MAIN) == P.MAIN.value
    assert s.pages() == (P.MAIN.value,)  # pop 而非 [MAIN, MAP, MAIN]


def test_observe_neighbor_pushes() -> None:
    s = UIStack()
    s.push(P.MAIN)
    assert s.observe(P.BACKYARD) == P.BACKYARD.value
    assert s.pages() == (P.MAIN.value, P.BACKYARD.value)


def test_observe_drift_marks_and_keeps_stack() -> None:
    """识别结果既非当前/父页也非邻居 → drifted,栈不动。"""
    s = UIStack()
    s.push(P.MAIN)
    s.push(P.BACKYARD)  # neighbors = {MAIN, BATH, CANTEEN}
    assert s.observe(P.MAP) == P.BACKYARD.value
    assert s.pages() == (P.MAIN.value, P.BACKYARD.value)
    assert s.drifted is True


def test_drifted_cleared_by_reset_and_replace() -> None:
    s = UIStack()
    s.push(P.MAIN)
    s.push(P.BACKYARD)
    s.observe(P.MAP)  # drift
    assert s.drifted
    s.replace(P.BACKYARD)
    assert not s.drifted
    s.observe(P.MAP)
    assert s.drifted
    s.reset(P.MAIN)
    assert not s.drifted
    assert s.pages() == (P.MAIN.value,)


def test_replace_swaps_top() -> None:
    """replace 用于同层 tab 切换 / 人工校正。"""
    s = UIStack()
    s.push(P.MAIN)
    s.push(P.BACKYARD)
    s.replace(P.CANTEEN)
    assert s.pages() == (P.MAIN.value, P.CANTEEN.value)


# ═══════════════════════════════════════════════════════════════════════════════
# resync / 留存帧
# ═══════════════════════════════════════════════════════════════════════════════


def test_resync_rebuilds_single_frame_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """resync:全量识别 → 单帧根重建,不猜祖先链。"""
    s = UIStack()
    s.push(P.MAIN)
    s.push(P.BACKYARD)
    s.observe(P.MAP)
    assert s.drifted
    monkeypatch.setattr('autowsgr.ui.page.get_current_page', lambda _screen: P.CANTEEN.value)
    screen = _frame(9)
    assert s.resync(screen) == P.CANTEEN.value
    assert s.pages() == (P.CANTEEN.value,)
    assert not s.drifted
    assert s.snapshot(P.CANTEEN) is screen


def test_resync_unidentified_clears_stack(monkeypatch: pytest.MonkeyPatch) -> None:
    s = UIStack()
    s.push(P.MAIN)
    s.push(P.BACKYARD)
    monkeypatch.setattr('autowsgr.ui.page.get_current_page', lambda _screen: None)
    assert s.resync(_frame(0)) is None
    assert s.pages() == ()
    assert not s.drifted


def test_snapshot_keeps_only_recent_frames() -> None:
    """留存帧上限:仅最近 keep_frames 帧保留截图,更早帧只留页面名。"""
    s = UIStack(keep_frames=2)
    f1, f2, f3 = _frame(1), _frame(2), _frame(3)
    s.push(P.MAIN, screen=f1)
    s.push(P.BACKYARD, screen=f2)
    s.push(P.BATH, screen=f3)
    assert s.snapshot(P.BATH) is f3
    assert s.snapshot(P.BACKYARD) is f2
    assert s.snapshot(P.MAIN) is None  # 超出 keep_frames 被淘汰


def test_snapshot_returns_most_recent_frame_of_page() -> None:
    s = UIStack()
    f1, f2 = _frame(1), _frame(2)
    s.push(P.MAIN, screen=f1)
    s.push(P.BACKYARD)
    s.push(P.MAIN, screen=f2)  # 重入 MAIN
    assert s.snapshot(P.MAIN) is f2


def test_overlay_candidates_extend_formula(monkeypatch: pytest.MonkeyPatch) -> None:
    """OVERLAY_CANDIDATES (当前为空) 若有内容应并入候选集。"""
    s = UIStack()
    s.push(P.MAIN)
    monkeypatch.setattr(stack_mod, 'OVERLAY_CANDIDATES', {'network_error'})
    assert 'network_error' in s.candidates()
