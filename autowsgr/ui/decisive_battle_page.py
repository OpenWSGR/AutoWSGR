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

入口:
    从地图页「决战」面板进入由 :meth:`~autowsgr.ui.map.page.MapPage.enter_decisive`
    完成 (属于 map_page 的职责)。

章节导航坐标说明:
    参考旧代码 ``_move_chapter``：
    ``timer.click(788, 507)`` → 向前一章 (◁)
    ``timer.click(900, 507)`` → 向后一章 (▷)

使用方式::

    from autowsgr.ui.decisive_battle_page import DecisiveBattlePage
    from autowsgr.ui.map.page import MapPage

    map_page = MapPage(ctrl, ocr=ocr)
    decisive_page = DecisiveBattlePage(ctrl, ocr=ocr)

    # 从地图进入决战页面 (由 map_page 负责)
    map_page.enter_decisive()

    # 导航到指定章节
    decisive_page.navigate_to_chapter(6)

    # 购买磁盘
    decisive_page.buy_ticket(use='steel', times=3)

    # 退出
    decisive_page.go_back()
"""

from __future__ import annotations

import re
import time

import numpy as np
from loguru import logger

from autowsgr.emulator import AndroidController
from autowsgr.ui.page import click_and_wait_for_page, wait_for_page
from autowsgr.vision import MatchStrategy, PixelChecker, PixelRule, PixelSignature


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

# ── 磁盘购买 ──

CLICK_BUY_TICKET_OPEN: tuple[float, float] = (458 * 0.75 / 960, 665 * 0.75 / 540)
"""打开磁盘购买面板 (⊕ 按钮)。

坐标换算自旧代码 ``buy_ticket`` → ``timer.click(458*0.75, 665*0.75)``。
"""

CLICK_BUY_RESOURCE: dict[str, tuple[float, float]] = {
    "oil":      (638 / 960, 184 / 540),
    "ammo":     (638 / 960, 235 / 540),
    "steel":    (638 / 960, 279 / 540),
    "aluminum": (638 / 960, 321 / 540),
}
"""磁盘购买面板中各资源类型的点击位置。

坐标换算自旧代码 ``buy_ticket`` 中的 position 字典。
"""

CLICK_BUY_CONFIRM: tuple[float, float] = (488 / 960, 405 / 540)
"""磁盘购买确认按钮。

坐标换算自旧代码 ``buy_ticket`` → ``timer.click(488, 405)``。
"""

# ── 杂项 ──

_CHAPTER_SWITCH_DELAY: float = 0.8
"""章节切换后等待动画的延迟 (秒)。"""

_CHAPTER_NAV_MAX_ATTEMPTS: int = 8
"""章节导航最大尝试次数。"""

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
    ocr:
        OCR 引擎实例 (可选，章节导航时需要)。
    """

    def __init__(
        self,
        ctrl: AndroidController,
        ocr: "OCREngine | None" = None,
    ) -> None:
        self._ctrl = ctrl
        self._ocr = ocr

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

    # ── 章节 OCR 识别 ────────────────────────────────────────────────────

    def _read_chapter(self, screen: np.ndarray | None = None) -> int | None:
        """通过 OCR 读取当前决战章节编号。

        裁切 ``CHAPTER_NUM_AREA`` 区域，识别 ``Ex-N`` 文本并提取数字。

        Parameters
        ----------
        screen:
            截图；为 ``None`` 时自动截取。

        Returns
        -------
        int | None
            当前章节编号 (4–6)，识别失败返回 ``None``。
        """
        if self._ocr is None:
            return None

        if screen is None:
            screen = self._ctrl.screenshot()

        x1, y1, x2, y2 = CHAPTER_NUM_AREA
        cropped = PixelChecker.crop(screen, x1, y1, x2, y2)
        result = self._ocr.recognize_single(cropped)
        if not result.text:
            logger.debug("[UI] 决战章节 OCR 无结果")
            return None

        # 提取最后一个数字 (如 "Ex-6" → 6)
        m = re.search(r"(\d)", result.text[::-1])
        if m:
            chapter = int(m.group(1))
            logger.debug("[UI] 决战章节 OCR: '{}' → Ex-{}", result.text, chapter)
            return chapter

        logger.debug("[UI] 决战章节 OCR 解析失败: '{}'", result.text)
        return None

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
        参照旧代码 ``DecisiveBattle._move_chapter`` 的递归逻辑。

        Parameters
        ----------
        target:
            目标章节编号 (MIN_CHAPTER – MAX_CHAPTER)。

        Raises
        ------
        ValueError
            章节号超出范围。
        RuntimeError
            需要 OCR 引擎但未传入。
        NavigationError
            超过最大尝试次数仍未到达。
        """
        from autowsgr.ui.page import NavigationError

        if not MIN_CHAPTER <= target <= MAX_CHAPTER:
            raise ValueError(
                f"决战章节编号必须为 {MIN_CHAPTER}–{MAX_CHAPTER}，收到: {target}"
            )
        if self._ocr is None:
            raise RuntimeError("navigate_to_chapter 需要 OCR 引擎")

        for attempt in range(_CHAPTER_NAV_MAX_ATTEMPTS):
            current = self._read_chapter()
            if current is None:
                logger.warning(
                    "[UI] 决战章节导航: OCR 识别失败 (第 {} 次尝试)",
                    attempt + 1,
                )
                time.sleep(_CHAPTER_SWITCH_DELAY)
                continue

            if current == target:
                logger.info("[UI] 决战章节导航: 已到达 Ex-{}", target)
                return

            logger.info(
                "[UI] 决战章节导航: Ex-{} → Ex-{}",
                current,
                target,
            )

            if current > target:
                self.go_prev_chapter()
            else:
                self.go_next_chapter()

        raise NavigationError(
            f"决战章节导航失败: 超过 {_CHAPTER_NAV_MAX_ATTEMPTS} 次尝试, "
            f"目标 Ex-{target}"
        )

    # ── 磁盘购买 ─────────────────────────────────────────────────────────

    def buy_ticket(
        self,
        use: str = "steel",
        times: int = 3,
    ) -> None:
        """购买决战磁盘 (入场券)。

        在决战页面打开磁盘购买面板，选择资源类型，点击指定次数后确认。
        参照旧代码 ``DecisiveBattle.buy_ticket``。

        Parameters
        ----------
        use:
            使用的资源类型: ``"oil"`` / ``"ammo"`` / ``"steel"`` / ``"aluminum"``。
        times:
            单次资源点击次数 (每次消耗一定数量的资源换取磁盘)。

        Raises
        ------
        ValueError
            资源类型无效。
        """
        if use not in CLICK_BUY_RESOURCE:
            raise ValueError(
                f"资源类型必须为 oil/ammo/steel/aluminum，收到: {use}"
            )

        logger.info("[UI] 决战页面 → 购买磁盘 (资源: {}, 次数: {})", use, times)

        # 打开购买面板
        self._ctrl.click(*CLICK_BUY_TICKET_OPEN)
        time.sleep(1.5)

        # 点击资源类型 (多次)
        resource_pos = CLICK_BUY_RESOURCE[use]
        for _ in range(times):
            self._ctrl.click(*resource_pos)
            time.sleep(1.0)

        # 确认购买
        self._ctrl.click(*CLICK_BUY_CONFIRM)
        time.sleep(1.0)

        logger.info("[UI] 决战磁盘购买完成")
