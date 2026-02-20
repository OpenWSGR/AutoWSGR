"""决战页面 UI 控制器。

对应游戏 **决战地图总览页** — 从地图页「决战」面板点击对应章节后进入，
呈现当前章节的地图布局、进攻方向、重置状态以及章节切换控件。

页面布局::

    ┌──────────────────────────────────────────────────────────────┐
    │ ◁  沉默战士 (章节标题)       [显示]  [奖励]  [说明]         │
    │                                                              │
    │  (角色立绘)      ┌──────────────────────────────┐           │
    │                  │  地图图标 + 路径              │           │
    │                  │  进度:  0/30                  │           │
    │                  └──────────────────────────────┘           │
    │                                                              │
    │ 🎟 12/12 ⊕        [已重置]    ◁ Ex-6 进攻方向 ▷   [上一关] │
    └──────────────────────────────────────────────────────────────┘

导航关系::

    地图页面 (决战 panel)
        └──[点击进入]──▶  决战页面  (本页)
                               ├── ◁ 左上角 ─▶ 主页面  (跨级直通)
                               └── ◁/▷ 章节导航 ─▶ 停留本页

入口坐标说明:
    从地图页「决战」面板进入由 :meth:`DecisiveBattlePage.enter_from_map_panel`
    完成。坐标参考旧代码 ``enter_decisive_battle`` → ``timer.click(115, 113)``，
    以 960×540 为参考分辨率换算为相对坐标。

章节导航坐标说明:
    参考旧代码 ``_move_chapter``：
    ``timer.click(788, 507)`` → 向前一章 (◁)
    ``timer.click(900, 507)`` → 向后一章 (▷)

使用方式::

    from autowsgr.ui.decisive_battle_page import DecisiveBattlePage
    from autowsgr.ui.map_page import MapPage, MapPanel

    map_page = MapPage(ctrl)
    decisive_page = DecisiveBattlePage(ctrl)

    # 进入决战页面
    map_page.switch_panel(MapPanel.DECISIVE)
    decisive_page.enter_from_map_panel()

    # 切换章节
    decisive_page.go_prev_chapter()  # ◁ 到 Ex-5
    decisive_page.go_next_chapter()  # ▷ 到 Ex-6

    # 退出
    decisive_page.go_back()          # ◁ 返回主页面
"""

from __future__ import annotations

import time

import numpy as np
from loguru import logger

from autowsgr.emulator.controller import AndroidController
from autowsgr.ui.page import click_and_wait_for_page, wait_for_page
from autowsgr.vision.matcher import MatchStrategy, PixelChecker, PixelRule, PixelSignature


# ═══════════════════════════════════════════════════════════════════════════════
# 页面识别签名
# ═══════════════════════════════════════════════════════════════════════════════

PAGE_SIGNATURE = PixelSignature(
    name="决战页面",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.8016, 0.8458, (20, 44, 78),  tolerance=30.0),
        PixelRule.of(0.9695, 0.8500, (15, 31, 56),  tolerance=30.0),
        PixelRule.of(0.7641, 0.8611, (22, 46, 84),  tolerance=30.0),
        PixelRule.of(0.0453, 0.0667, (38, 39, 43),  tolerance=30.0),
    ],
)
"""决战页面像素签名。

特征点分布:
    - (0.8016, 0.8458), (0.9695, 0.8500), (0.7641, 0.8611) —
      底部章节导航/按钮栏深蓝色背景
    - (0.0453, 0.0667) — 左上角回退区域深色背景
"""


# ═══════════════════════════════════════════════════════════════════════════════
# 坐标常量
# ═══════════════════════════════════════════════════════════════════════════════

# ── 通用导航 ──

CLICK_BACK: tuple[float, float] = (0.022, 0.058)
"""左上角回退按钮 ◁ — 直接返回主页面。"""

# ── 从地图决战面板进入 ──

CLICK_ENTER_CHAPTER: tuple[float, float] = (115 / 960, 113 / 540)
"""从地图页「决战」面板点击进入决战总览页。

坐标换算自旧代码 ``enter_decisive_battle`` → ``timer.click(115, 113)``，
参考分辨率 960×540。
"""

# ── 底部章节导航箭头 ──

CLICK_PREV_CHAPTER: tuple[float, float] = (788 / 960, 507 / 540)
"""向前一章 ◁ — 切换到编号较小的章节 (如 Ex-6 → Ex-5)。

坐标换算自旧代码 ``_move_chapter`` → ``timer.click(788, 507)``，
参考分辨率 960×540。
"""

CLICK_NEXT_CHAPTER: tuple[float, float] = (900 / 960, 507 / 540)
"""向后一章 ▷ — 切换到编号较大的章节 (如 Ex-5 → Ex-6)。

坐标换算自旧代码 ``_move_chapter`` → ``timer.click(900, 507)``，
参考分辨率 960×540。
"""

# ── 章节编号 OCR 区域 ──

CHAPTER_NUM_AREA: tuple[float, float, float, float] = (0.818, 0.810, 0.875, 0.867)
"""章节编号文字裁切区域 (x1, y1, x2, y2)，用于 OCR 读取「Ex-N」文本。"""

# ── 杂项 ──

_CHAPTER_SWITCH_DELAY: float = 0.8
"""章节切换后等待动画的延迟 (秒)。"""

MAX_CHAPTER: int = 6
"""决战最大章节数。"""

MIN_CHAPTER: int = 4
"""决战最小可用章节数。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 页面控制器
# ═══════════════════════════════════════════════════════════════════════════════


class DecisiveBattlePage:
    """决战地图总览页控制器。

    **状态查询** 为 ``staticmethod``，只需截图即可调用。
    **操作动作** 为实例方法，通过注入的控制器执行。

    Parameters
    ----------
    ctrl:
        Android 设备控制器实例。
    """

    def __init__(self, ctrl: AndroidController) -> None:
        self._ctrl = ctrl

    # ── 页面识别 ──────────────────────────────────────────────────────────

    @staticmethod
    def is_current_page(screen: np.ndarray) -> bool:
        """判断截图是否为决战总览页。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。
        """
        result = PixelChecker.check_signature(screen, PAGE_SIGNATURE)
        return result.matched

    # ── 进入 ──────────────────────────────────────────────────────────────

    def enter_from_map_panel(self) -> None:
        """从地图页「决战」面板点击进入决战总览页。

        调用前需确保当前页面已是地图页且已切换到「决战」面板，
        例如先调用 :meth:`~autowsgr.ui.map_page.MapPage.switch_panel`
        ``(MapPanel.DECISIVE)``。

        点击后等待并验证已到达决战总览页。

        Raises
        ------
        NavigationError
            超时未到达决战页面。
        """
        logger.info("[UI] 地图决战面板 → 决战页面")
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_ENTER_CHAPTER,
            checker=DecisiveBattlePage.is_current_page,
            source="地图-决战面板",
            target="决战页面",
        )

    # ── 回退 ──────────────────────────────────────────────────────────────

    def go_back(self) -> None:
        """点击左上角 ◁，直接返回主页面。

        决战页面的回退按钮越过地图页面，直接跳转至主页面。

        Raises
        ------
        NavigationError
            超时未到达主页面。
        """
        from autowsgr.ui.main_page import MainPage

        logger.info("[UI] 决战页面 ◁ → 主页面")
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_BACK,
            checker=MainPage.is_current_page,
            source="决战页面",
            target="主页面",
        )

    # ── 章节导航 ──────────────────────────────────────────────────────────

    def go_prev_chapter(self) -> None:
        """点击 ◁ 切换到前一章节 (如 Ex-6 → Ex-5)。

        仅点击，不等待页面验证。调用后建议等待动画完成。
        """
        logger.info("[UI] 决战页面 → 前一章节 ◁")
        self._ctrl.click(*CLICK_PREV_CHAPTER)
        time.sleep(_CHAPTER_SWITCH_DELAY)

    def go_next_chapter(self) -> None:
        """点击 ▷ 切换到后一章节 (如 Ex-5 → Ex-6)。

        仅点击，不等待页面验证。调用后建议等待动画完成。
        """
        logger.info("[UI] 决战页面 → 后一章节 ▷")
        self._ctrl.click(*CLICK_NEXT_CHAPTER)
        time.sleep(_CHAPTER_SWITCH_DELAY)

    def navigate_to_chapter(self, target: int) -> None:
        """导航到指定决战章节。

        通过 OCR 读取当前章节编号，反复点击 ◁/▷ 直到到达目标。

        Parameters
        ----------
        target:
            目标章节编号 (MIN_CHAPTER – MAX_CHAPTER)。

        Raises
        ------
        ValueError
            章节号超出范围。
        RuntimeError
            需要 OCR 引擎但未传入（预留接口，当前直接抛出）。
        """
        if not MIN_CHAPTER <= target <= MAX_CHAPTER:
            raise ValueError(
                f"决战章节编号必须为 {MIN_CHAPTER}–{MAX_CHAPTER}，收到: {target}"
            )
        # OCR 支持预留 —— 当前通过简单循环 + 固定判断实现
        # 完整 OCR 集成见 map_page.navigate_to_chapter 的实现思路
        raise RuntimeError(
            "navigate_to_chapter 需要 OCR 支持，请使用 go_prev_chapter / go_next_chapter "
            "配合外部章节识别逻辑。"
        )
