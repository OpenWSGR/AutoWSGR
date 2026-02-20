"""地图页面 UI 控制器。

覆盖 **地图选择** 页面的全部界面交互，包括面板切换、章节导航等。

数据常量和 OCR 解析逻辑见 :mod:`autowsgr.ui.map_data`。
"""

from __future__ import annotations

import enum
import time

import numpy as np
from loguru import logger

from autowsgr.emulator.controller import AndroidController
from autowsgr.ui.map_data import (
    CHAPTER_NAV_DELAY,
    CHAPTER_NAV_MAX_ATTEMPTS,
    CHAPTER_SPACING,
    CLICK_BACK,
    EXPEDITION_NOTIF_COLOR,
    EXPEDITION_NOTIF_PROBE,
    EXPEDITION_TOLERANCE,
    MAP_DATABASE,
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
from autowsgr.ui.page import click_and_wait_for_page, wait_for_page
from autowsgr.ui.tabbed_page import (
    TabbedPageType,
    get_active_tab_index,
    identify_page_type,
    make_tab_checker,
)
from autowsgr.vision.matcher import Color, PixelChecker
from autowsgr.vision.ocr import OCREngine


# ═══════════════════════════════════════════════════════════════════════════════
# 枚举
# ═══════════════════════════════════════════════════════════════════════════════


class MapPanel(enum.Enum):
    """地图页面顶部导航面板。"""

    SORTIE = "出征"
    EXERCISE = "演习"
    EXPEDITION = "远征"
    BATTLE = "战役"
    DECISIVE = "决战"


# ═══════════════════════════════════════════════════════════════════════════════
# 面板索引映射
# ═══════════════════════════════════════════════════════════════════════════════

_PANEL_LIST: list[MapPanel] = list(MapPanel)
"""面板枚举值列表 — 索引与标签栏探测位置一一对应。"""

_PANEL_TO_INDEX: dict[MapPanel, int] = {
    panel: i for i, panel in enumerate(_PANEL_LIST)
}

CLICK_PANEL: dict[MapPanel, tuple[float, float]] = {
    MapPanel.SORTIE:     (0.1396, 0.0574),
    MapPanel.EXERCISE:   (0.2745, 0.0537),
    MapPanel.EXPEDITION: (0.4042, 0.0556),
    MapPanel.BATTLE:     (0.5276, 0.0519),
    MapPanel.DECISIVE:   (0.6620, 0.0556),
}
"""面板标签点击位置。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 页面控制器
# ═══════════════════════════════════════════════════════════════════════════════


class MapPage:
    """地图页面控制器。

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
        """判断截图是否为地图页面。"""
        return identify_page_type(screen) == TabbedPageType.MAP

    # ── 状态查询 — 面板 ──────────────────────────────────────────────────

    @staticmethod
    def get_active_panel(screen: np.ndarray) -> MapPanel | None:
        """获取当前激活的面板标签。"""
        idx = get_active_tab_index(screen)
        if idx is None or idx >= len(_PANEL_LIST):
            return None
        return _PANEL_LIST[idx]

    # ── 状态查询 — 远征通知 ──────────────────────────────────────────────

    @staticmethod
    def has_expedition_notification(screen: np.ndarray) -> bool:
        """检测是否有远征完成通知。"""
        x, y = EXPEDITION_NOTIF_PROBE
        return PixelChecker.get_pixel(screen, x, y).near(
            EXPEDITION_NOTIF_COLOR, EXPEDITION_TOLERANCE
        )

    # ── 状态查询 — 侧边栏 (章节位置) ────────────────────────────────────

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

    # ── 状态查询 — 地图 OCR ──────────────────────────────────────────────

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

    # ── 动作 — 回退 ──────────────────────────────────────────────────────

    def go_back(self) -> None:
        """点击回退按钮 (◁)，返回主页面。"""
        from autowsgr.ui.main_page import MainPage

        logger.info("[UI] 地图页面 → 回退")
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_BACK,
            checker=MainPage.is_current_page,
            source="地图页面",
            target="主页面",
        )

    # ── 动作 — 面板切换 ──────────────────────────────────────────────────

    def switch_panel(self, panel: MapPanel) -> None:
        """切换到指定面板标签并验证到达。"""
        current = self.get_active_panel(self._ctrl.screenshot())
        logger.info(
            "[UI] 地图页面: {} → {}",
            current.value if current else "未知",
            panel.value,
        )
        target_idx = _PANEL_TO_INDEX[panel]
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_PANEL[panel],
            checker=make_tab_checker(TabbedPageType.MAP, target_idx),
            source=f"地图-{current.value if current else '?'}",
            target=f"地图-{panel.value}",
        )

    # ── 动作 — 章节导航 ──────────────────────────────────────────────────

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
