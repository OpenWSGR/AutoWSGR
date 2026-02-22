"""地图页面基类 — 声明共享依赖与公共查询方法。

所有面板 Mixin 均继承 :class:`BaseMapPage`，
最终由 :class:`~autowsgr.ui.map.page.MapPage` 组合为完整控制器。
"""

from __future__ import annotations

import time

import numpy as np
from loguru import logger

from autowsgr.emulator import AndroidController
from autowsgr.ui.map.data import (
    CHAPTER_NAV_DELAY,
    CHAPTER_NAV_MAX_ATTEMPTS,
    CHAPTER_SPACING,
    CLICK_BACK,
    CLICK_PANEL,
    CLICK_SCREEN_CENTER,
    EXPEDITION_NOTIF_COLOR,
    EXPEDITION_NOTIF_PROBE,
    EXPEDITION_TOLERANCE,
    MapPanel,
    PANEL_LIST,
    PANEL_TO_INDEX,
    SIDEBAR_BRIGHTNESS_THRESHOLD,
    SIDEBAR_CLICK_X,
    SIDEBAR_SCAN_STEP,
    SIDEBAR_SCAN_X,
    SIDEBAR_SCAN_Y_RANGE,
    TITLE_CROP_REGION,
    TOTAL_CHAPTERS,
    MapIdentity,
    parse_map_title,
)
from autowsgr.types import PageName
from autowsgr.ui.page import click_and_wait_for_page
from autowsgr.ui.tabbed_page import (
    TabbedPageType,
    get_active_tab_index,
    identify_page_type,
    make_tab_checker,
)
from autowsgr.vision import OCREngine, PixelChecker


class BaseMapPage:
    """地图页面基类。

    声明所有面板 Mixin 需要的共享依赖与公共查询 / 导航方法。

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

    # ═══════════════════════════════════════════════════════════════════════
    # 页面识别
    # ═══════════════════════════════════════════════════════════════════════

    @staticmethod
    def is_current_page(screen: np.ndarray) -> bool:
        """判断截图是否为地图页面。"""
        return identify_page_type(screen) == TabbedPageType.MAP

    # ═══════════════════════════════════════════════════════════════════════
    # 状态查询 — 面板
    # ═══════════════════════════════════════════════════════════════════════

    @staticmethod
    def get_active_panel(screen: np.ndarray) -> MapPanel | None:
        """获取当前激活的面板标签。"""
        idx = get_active_tab_index(screen)
        if idx is None or idx >= len(PANEL_LIST):
            return None
        return PANEL_LIST[idx]

    # ═══════════════════════════════════════════════════════════════════════
    # 状态查询 — 远征通知
    # ═══════════════════════════════════════════════════════════════════════

    @staticmethod
    def has_expedition_notification(screen: np.ndarray) -> bool:
        """检测是否有远征完成通知。"""
        x, y = EXPEDITION_NOTIF_PROBE
        return PixelChecker.get_pixel(screen, x, y).near(
            EXPEDITION_NOTIF_COLOR, EXPEDITION_TOLERANCE
        )

    # ═══════════════════════════════════════════════════════════════════════
    # 状态查询 — 侧边栏 (章节位置)
    # ═══════════════════════════════════════════════════════════════════════

    @staticmethod
    def find_selected_chapter_y(screen: np.ndarray) -> float | None:
        """扫描侧边栏，定位选中章节的 y 坐标。"""
        y_min, y_max = SIDEBAR_SCAN_Y_RANGE
        bright_ys: list[float] = []

        y = y_min
        while y <= y_max:
            c = PixelChecker.get_pixel(screen, SIDEBAR_SCAN_X, y)
            brightness = c.r + c.g + c.b
            if brightness >= SIDEBAR_BRIGHTNESS_THRESHOLD:
                bright_ys.append(y)
            y += SIDEBAR_SCAN_STEP

        if not bright_ys:
            return None

        center = sum(bright_ys) / len(bright_ys)
        logger.debug(
            "[UI] 侧边栏选中章节: y_center={:.3f} ({}个亮点)",
            center,
            len(bright_ys),
        )
        return center

    # ═══════════════════════════════════════════════════════════════════════
    # 状态查询 — 地图 OCR
    # ═══════════════════════════════════════════════════════════════════════

    @staticmethod
    def recognize_map(
        screen: np.ndarray,
        ocr: OCREngine,
    ) -> MapIdentity | None:
        """通过 OCR 识别当前地图。"""
        x1, y1, x2, y2 = TITLE_CROP_REGION
        cropped = PixelChecker.crop(screen, x1, y1, x2, y2)
        result = ocr.recognize_single(cropped)
        if not result.text:
            logger.debug("[UI] 地图标题 OCR 无结果")
            return None

        info = parse_map_title(result.text)
        if info is None:
            logger.debug("[UI] 地图标题解析失败: '{}'", result.text)
        else:
            logger.debug(
                "[UI] 地图识别: 第{}章 {}-{} {}",
                info.chapter,
                info.chapter,
                info.map_num,
                info.name,
            )
        return info

    # ═══════════════════════════════════════════════════════════════════════
    # 动作 — 回退 / 面板切换 / 通用点击
    # ═══════════════════════════════════════════════════════════════════════

    def go_back(self) -> None:
        """点击回退按钮 (◁)，返回主页面。"""
        from autowsgr.ui.main_page import MainPage

        logger.info("[UI] 地图页面 → 回退")
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_BACK,
            checker=MainPage.is_current_page,
            source=PageName.MAP,
            target=PageName.MAIN,
        )

    def switch_panel(self, panel: MapPanel) -> None:
        """切换到指定面板标签并验证到达。"""
        current = self.get_active_panel(self._ctrl.screenshot())
        logger.info(
            "[UI] 地图页面: {} → {}",
            current.value if current else "未知",
            panel.value,
        )
        target_idx = PANEL_TO_INDEX[panel]
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_PANEL[panel],
            checker=make_tab_checker(TabbedPageType.MAP, target_idx),
            source=f"地图-{current.value if current else '?'}",
            target=f"地图-{panel.value}",
        )

    def ensure_panel(self, panel: MapPanel) -> None:
        """确保当前处于指定面板，若不是则切换。"""
        screen = self._ctrl.screenshot()
        if self.get_active_panel(screen) != panel:
            self.switch_panel(panel)

    def click_screen_center(self) -> None:
        """点击屏幕中央 — 用于跳过动画/确认弹窗。"""
        self._ctrl.click(*CLICK_SCREEN_CENTER)

    # ═══════════════════════════════════════════════════════════════════════
    # 动作 — 章节导航 (出征面板共用)
    # ═══════════════════════════════════════════════════════════════════════

    def click_prev_chapter(self, screen: np.ndarray | None = None) -> bool:
        """点击侧边栏上方章节 (前一章)。"""
        if screen is None:
            screen = self._ctrl.screenshot()
        sel_y = self.find_selected_chapter_y(screen)
        if sel_y is None:
            logger.warning("[UI] 侧边栏未找到选中章节，无法切换")
            return False
        target_y = sel_y - CHAPTER_SPACING
        if target_y < SIDEBAR_SCAN_Y_RANGE[0]:
            logger.warning("[UI] 已在最前章节，无法继续向前")
            return False
        logger.info("[UI] 地图页面 → 上一章 (y={:.3f})", target_y)
        self._ctrl.click(SIDEBAR_CLICK_X, target_y)
        return True

    def click_next_chapter(self, screen: np.ndarray | None = None) -> bool:
        """点击侧边栏下方章节 (后一章)。"""
        if screen is None:
            screen = self._ctrl.screenshot()
        sel_y = self.find_selected_chapter_y(screen)
        if sel_y is None:
            logger.warning("[UI] 侧边栏未找到选中章节，无法切换")
            return False
        target_y = sel_y + CHAPTER_SPACING
        if target_y > SIDEBAR_SCAN_Y_RANGE[1]:
            logger.warning("[UI] 已在最后章节，无法继续向后")
            return False
        logger.info("[UI] 地图页面 → 下一章 (y={:.3f})", target_y)
        self._ctrl.click(SIDEBAR_CLICK_X, target_y)
        return True

    def navigate_to_chapter(self, target: int) -> int | None:
        """导航到指定章节 (通过 OCR 识别当前位置并逐步点击)。

        Parameters
        ----------
        target:
            目标章节编号 (1–9)。
        """
        if not 1 <= target <= TOTAL_CHAPTERS:
            raise ValueError(
                f"章节编号必须为 1–{TOTAL_CHAPTERS}，收到: {target}"
            )
        if self._ocr is None:
            raise RuntimeError("需要 OCR 引擎才能导航到指定章节")

        for attempt in range(CHAPTER_NAV_MAX_ATTEMPTS):
            screen = self._ctrl.screenshot()
            info = self.recognize_map(screen, self._ocr)
            if info is None:
                logger.warning(
                    "[UI] 章节导航: OCR 识别失败 (第 {} 次尝试)", attempt + 1
                )
                return None

            current = info.chapter
            if current == target:
                logger.info("[UI] 章节导航: 已到达第 {} 章", target)
                return current

            logger.info(
                "[UI] 章节导航: 当前第 {} 章 → 目标第 {} 章",
                current,
                target,
            )

            if current > target:
                ok = self.click_prev_chapter(screen)
            else:
                ok = self.click_next_chapter(screen)

            if not ok:
                logger.warning("[UI] 章节导航: 点击失败，终止")
                return None

            time.sleep(CHAPTER_NAV_DELAY)

        logger.warning(
            "[UI] 章节导航: 超过最大尝试次数 ({}), 目标第 {} 章",
            CHAPTER_NAV_MAX_ATTEMPTS,
            target,
        )
        return None
