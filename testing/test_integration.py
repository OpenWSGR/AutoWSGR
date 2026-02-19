"""对增强测试数据集进行全面页面检测测试。

基于 ``logs/testing/`` 中由 ``tools/build_test_dataset.py`` 生成的数据集，
读取 ``manifest.json`` 获取每张图的页面标签与子标签，自动推导预期值并测试:

- ``get_current_page()`` 页面识别
- ``is_tabbed_page()`` 标签页判定
- ``identify_page_type()`` 标签页类型识别
- ``get_active_tab_index()`` 激活标签索引

数据集包含原始截图、多分辨率缩放 (1600×900, 1366×768) 及 ±1px 像素偏移增强。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pytest

from autowsgr.ui.page import get_current_page
from autowsgr.ui.tabbed_page import (
    TabbedPageType,
    get_active_tab_index,
    identify_page_type,
    is_tabbed_page,
)

# 触发页面注册
import autowsgr.ui  # noqa: F401


# ═══════════════════════════════════════════════════════════════════════════════
# 数据集目录
# ═══════════════════════════════════════════════════════════════════════════════

_DATASET_DIR = Path(__file__).resolve().parent.parent / "logs" / "testing"
_MANIFEST_PATH = _DATASET_DIR / "manifest.json"


# ═══════════════════════════════════════════════════════════════════════════════
# 标签定义与推导
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Label:
    """单张截图的预期标签。"""

    page_name: str
    """get_current_page 应返回的页面名称。"""

    tabbed: bool
    """是否为标签页。"""

    tabbed_type: TabbedPageType | None = None
    """标签页类型 (非标签页为 None)。"""

    tab_index: int | None = None
    """激活标签索引 (非标签页为 None)。"""


# ── 页面 → TabbedPageType 映射 ──

_PAGE_TO_TABBED_TYPE: dict[str, TabbedPageType] = {
    "地图页面": TabbedPageType.MAP,
    "建造页面": TabbedPageType.BUILD,
    "强化页面": TabbedPageType.INTENSIFY,
    "任务页面": TabbedPageType.MISSION,
    "好友页面": TabbedPageType.FRIEND,
}

# ── 子标签 → tab_index 映射 ──
# 地图面板: 出征=0, 演习=1, 远征=2, 战役=3, 决战=4
# 建造标签: 建造=0, 解体=1, 开发=2, 废弃=3
# 强化标签: 强化=0, 改修=1, 技能=2

_SUB_LABEL_TO_TAB_INDEX: dict[str, dict[str, int]] = {
    "地图页面": {
        "": 0,           # 无子标签 = 默认出征面板
        "出征": 2,       # 从主页面"出征"按钮进入, 游戏记忆上次面板(远征)
        "面板_出征": 0,
        "面板_演习": 1,
        "面板_远征": 2,
        "面板_战役": 3,
        "面板_决战": 4,
    },
    "建造页面": {
        "": 0,           # 默认建造标签
        "标签_建造": 0,
        "标签_解体": 1,
        "标签_开发": 2,
        "标签_废弃": 3,
    },
    "强化页面": {
        "": 0,           # 默认强化标签
        "标签_强化": 0,
        "标签_改修": 1,
        "标签_技能": 2,
    },
    "任务页面": {
        "": 0,
    },
    "好友页面": {
        "": 0,
    },
}


def _derive_label(page: str, sub_label: str) -> Label:
    """从 manifest 条目的 page + sub_label 推导完整 Label。"""
    tabbed_type = _PAGE_TO_TABBED_TYPE.get(page)
    if tabbed_type is None:
        return Label(page_name=page, tabbed=False)

    index_map = _SUB_LABEL_TO_TAB_INDEX.get(page, {})
    tab_index = index_map.get(sub_label, 0)
    return Label(
        page_name=page,
        tabbed=True,
        tabbed_type=tabbed_type,
        tab_index=tab_index,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 图像加载
# ═══════════════════════════════════════════════════════════════════════════════


def _load_image(path: Path) -> np.ndarray:
    """加载图片为 RGB ndarray (兼容 CJK 路径)。"""
    buf = np.frombuffer(path.read_bytes(), np.uint8)
    bgr = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    assert bgr is not None, f"无法加载: {path}"
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


# ═══════════════════════════════════════════════════════════════════════════════
# 从 manifest.json 收集测试用例
# ═══════════════════════════════════════════════════════════════════════════════


def _collect_test_cases() -> list[tuple[str, Path, Label]]:
    """从 manifest.json 读取所有条目，推导标签，返回测试用例列表。"""
    if not _MANIFEST_PATH.exists():
        return []

    data = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    cases: list[tuple[str, Path, Label]] = []

    for item in data["items"]:
        rel_path = item["file"]          # e.g. "地图页面/orig_00.png"
        page = item["page"]
        sub_label = item["sub_label"]
        aug = item["augmentation"]
        resolution = item["resolution"]
        shift = item["shift"]

        img_path = _DATASET_DIR / rel_path
        label = _derive_label(page, sub_label)

        # 构造可读 test_id
        parts = [page]
        if sub_label:
            parts.append(sub_label)
        parts.append(aug)
        if aug == "shift":
            parts.append(f"{shift[0]:+d}{shift[1]:+d}")
        parts.append(resolution)
        parts.append(Path(rel_path).stem)
        test_id = "|".join(parts)

        cases.append((test_id, img_path, label))

    return cases


_ALL_CASES = _collect_test_cases()
_TABBED_CASES = [(tid, p, l) for tid, p, l in _ALL_CASES if l.tabbed]

# 跳过条件
_skip_no_dataset = pytest.mark.skipif(
    not _ALL_CASES,
    reason="logs/testing/manifest.json 不存在或无数据",
)


# ═══════════════════════════════════════════════════════════════════════════════
# 测试
# ═══════════════════════════════════════════════════════════════════════════════


@_skip_no_dataset
class TestGetCurrentPage:
    """测试 get_current_page 对每张截图的页面识别。"""

    @pytest.mark.parametrize(
        "test_id, img_path, label",
        _ALL_CASES,
        ids=[c[0] for c in _ALL_CASES],
    )
    def test_page_name(self, test_id: str, img_path: Path, label: Label):
        screen = _load_image(img_path)
        actual = get_current_page(screen)
        assert actual == label.page_name, (
            f"{test_id}: expected={label.page_name!r}, actual={actual!r}"
        )


@_skip_no_dataset
class TestIsTabbedPage:
    """测试 is_tabbed_page 判定。"""

    @pytest.mark.parametrize(
        "test_id, img_path, label",
        _ALL_CASES,
        ids=[c[0] for c in _ALL_CASES],
    )
    def test_tabbed_flag(self, test_id: str, img_path: Path, label: Label):
        screen = _load_image(img_path)
        actual = is_tabbed_page(screen)
        assert actual == label.tabbed, (
            f"{test_id}: expected tabbed={label.tabbed}, actual={actual}"
        )


@_skip_no_dataset
class TestIdentifyPageType:
    """测试 identify_page_type 类型识别 (仅标签页截图)。"""

    @pytest.mark.parametrize(
        "test_id, img_path, label",
        _TABBED_CASES,
        ids=[c[0] for c in _TABBED_CASES],
    )
    def test_page_type(self, test_id: str, img_path: Path, label: Label):
        screen = _load_image(img_path)
        actual = identify_page_type(screen)
        assert actual == label.tabbed_type, (
            f"{test_id}: expected={label.tabbed_type}, actual={actual}"
        )


@_skip_no_dataset
class TestGetActiveTabIndex:
    """测试 get_active_tab_index 激活标签 (仅标签页截图)。"""

    @pytest.mark.parametrize(
        "test_id, img_path, label",
        _TABBED_CASES,
        ids=[c[0] for c in _TABBED_CASES],
    )
    def test_tab_index(self, test_id: str, img_path: Path, label: Label):
        screen = _load_image(img_path)
        actual = get_active_tab_index(screen)
        assert actual == label.tab_index, (
            f"{test_id}: expected tab={label.tab_index}, actual={actual}"
        )
