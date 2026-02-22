"""决战总览页 UI 控制器。

对应游戏 **决战地图总览页** — 从地图页「决战」面板进入。

使用方式::

    from autowsgr.ui.decisive import DecisiveBattlePage

    page = DecisiveBattlePage(ctrl, ocr=ocr)
    stage = page.recognize_stage(screen, chapter=6)
    page.enter_map()
    page.go_back()
"""

from __future__ import annotations

import re
import time

import numpy as np
from loguru import logger

from autowsgr.emulator import AndroidController
from autowsgr.types import PageName
from autowsgr.ui.page import click_and_wait_for_page
from autowsgr.vision import (
    Color,
    MatchStrategy,
    PixelChecker,
    PixelRule,
    PixelSignature,
    OCREngine,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 页面识别签名
# ═══════════════════════════════════════════════════════════════════════════════

PAGE_SIGNATURE = PixelSignature(
    name=PageName.DECISIVE_BATTLE,
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.8016, 0.8458, (20, 44, 78),  tolerance=30.0),
        PixelRule.of(0.9695, 0.8500, (15, 31, 56),  tolerance=30.0),
        PixelRule.of(0.7641, 0.8611, (22, 46, 84),  tolerance=30.0),
        PixelRule.of(0.0453, 0.0667, (38, 39, 43),  tolerance=30.0),
    ],
)
"""决战页面像素签名。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 坐标常量 (相对坐标 0.0–1.0, 参考分辨率 960×540)
# ═══════════════════════════════════════════════════════════════════════════════

CLICK_BACK: tuple[float, float] = (0.022, 0.058)
"""左上角回退按钮 ◁ — 直接返回主页面。"""

CLICK_PREV_CHAPTER: tuple[float, float] = (788 / 960, 507 / 540)
"""向前一章 ◁ (如 Ex-6 → Ex-5)。"""

CLICK_NEXT_CHAPTER: tuple[float, float] = (900 / 960, 507 / 540)
"""向后一章 ▷ (如 Ex-5 → Ex-6)。"""

CLICK_ENTER_MAP: tuple[float, float] = (500 / 960, 500 / 540)
"""点击页面中央进入当前章节地图。

旧代码: ``timer.click(500, 500)``。
"""

CHAPTER_NUM_AREA: tuple[float, float, float, float] = (0.818, 0.810, 0.875, 0.867)
"""章节编号 OCR 裁切区域 (x1, y1, x2, y2)。"""

# ── 磁盘购买 ──

CLICK_BUY_TICKET_OPEN: tuple[float, float] = (458 * 0.75 / 960, 665 * 0.75 / 540)
"""打开磁盘购买面板 (⊕ 按钮)。"""

CLICK_BUY_RESOURCE: dict[str, tuple[float, float]] = {
    "oil":      (638 / 960, 184 / 540),
    "ammo":     (638 / 960, 235 / 540),
    "steel":    (638 / 960, 279 / 540),
    "aluminum": (638 / 960, 321 / 540),
}
"""磁盘购买面板中各资源类型的点击位置。"""

CLICK_BUY_CONFIRM: tuple[float, float] = (488 / 960, 405 / 540)
"""磁盘购买确认按钮。"""

# ── 其他常量 ──

_CHAPTER_SWITCH_DELAY: float = 0.8
"""章节切换动画延迟 (秒)。"""

_CHAPTER_NAV_MAX_ATTEMPTS: int = 8
"""章节导航最大尝试次数。"""

MAX_CHAPTER: int = 6
MIN_CHAPTER: int = 4

# ── recognize_stage 检测点 ──

_STAGE_CHECK_POINTS: dict[int, list[tuple[float, float]]] = {
    4: [(0.381, 0.436), (0.596, 0.636), (0.778, 0.521)],
    5: [(0.418, 0.378), (0.760, 0.477), (0.550, 0.750)],
    6: [(0.606, 0.375), (0.532, 0.703), (0.862, 0.644)],
}
"""每章 3 个小关的像素检测点 (相对坐标)。

若检测点颜色接近白色 (250, 244, 253) 表示该小关已通过。
"""

_STAGE_CHECK_COLOR: Color = Color.of(250, 244, 253)
"""小关已通过标记颜色 (近白色)。"""

_STAGE_CHECK_TOLERANCE: float = 30.0
"""颜色匹配容差。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 页面控制器
# ═══════════════════════════════════════════════════════════════════════════════


class DecisiveBattlePage:
    """决战总览页控制器。

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
        ocr: OCREngine | None = None,
    ) -> None:
        self._ctrl = ctrl
        self._ocr = ocr

    # ── 页面识别 ──────────────────────────────────────────────────────────

    @staticmethod
    def is_current_page(screen: np.ndarray) -> bool:
        """判断截图是否为决战总览页。"""
        return PixelChecker.check_signature(screen, PAGE_SIGNATURE).matched

    # ── 小关进度识别 ──────────────────────────────────────────────────────

    @staticmethod
    def recognize_stage(screen: np.ndarray, chapter: int) -> int:
        """识别当前决战章节的小关进度 (0–3)。

        检查每个小关位置像素颜色，白色 (250,244,253) 为已通过。
        返回当前正在进行的小关编号; 3 表示全部通过。
        """
        check_points = _STAGE_CHECK_POINTS.get(chapter)
        if check_points is None:
            logger.warning("[UI] 决战 recognize_stage: 未知章节 {}", chapter)
            return 0

        for i, (rx, ry) in enumerate(check_points):
            if not PixelChecker.check_pixel(
                screen, rx, ry, _STAGE_CHECK_COLOR, _STAGE_CHECK_TOLERANCE,
            ):
                logger.info("[UI] 识别决战地图参数, 第 {} 小节正在进行", i)
                return i

        logger.info("[UI] 识别决战地图参数, 第 3 小节正在进行")
        return 3

    # ── 导航 ──────────────────────────────────────────────────────────────

    def go_back(self) -> None:
        """点击左上角 ◁，直接返回主页面 (跨级)。"""
        from autowsgr.ui.main_page import MainPage

        logger.info("[UI] 决战页面 ◁ → 主页面")
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_BACK,
            checker=MainPage.is_current_page,
            source=PageName.DECISIVE_BATTLE,
            target=PageName.MAIN,
        )

    def click_enter_map(self) -> None:
        """从决战总览页进入当前章节的决战地图页。"""
        logger.info("[UI] 决战总览 → 进入地图")
        self._ctrl.click(*CLICK_ENTER_MAP)

    # ── 章节 OCR ──────────────────────────────────────────────────────────

    def _read_chapter(self, screen: np.ndarray | None = None) -> int | None:
        """通过 OCR 读取当前章节编号 (Ex-N → N)。"""
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

        m = re.search(r"(\d)", result.text[::-1])
        if m:
            chapter = int(m.group(1))
            logger.debug("[UI] 决战章节 OCR: '{}' → Ex-{}", result.text, chapter)
            return chapter

        logger.debug("[UI] 决战章节 OCR 解析失败: '{}'", result.text)
        return None

    # ── 章节导航 ──────────────────────────────────────────────────────────

    def go_prev_chapter(self) -> None:
        """点击 ◁ 切换到前一章节。"""
        logger.info("[UI] 决战页面 → 前一章节 ◁")
        self._ctrl.click(*CLICK_PREV_CHAPTER)
        time.sleep(_CHAPTER_SWITCH_DELAY)

    def go_next_chapter(self) -> None:
        """点击 ▷ 切换到后一章节。"""
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

        Parameters
        ----------
        use:
            资源类型: ``"oil"``/``"ammo"``/``"steel"``/``"aluminum"``。
        times:
            单次资源点击次数。

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
        self._ctrl.click(*CLICK_BUY_TICKET_OPEN)
        time.sleep(1.5)

        resource_pos = CLICK_BUY_RESOURCE[use]
        for _ in range(times):
            self._ctrl.click(*resource_pos)
            time.sleep(1.0)

        self._ctrl.click(*CLICK_BUY_CONFIRM)
        time.sleep(1.0)
        logger.info("[UI] 决战磁盘购买完成")
