"""地图页面 UI 控制器。

覆盖 **地图选择** 页面的全部界面交互，包括面板切换、章节导航等。

数据常量和 OCR 解析逻辑见 :mod:`autowsgr.ui.map.data`。
战役 / 决战 / 演习 / 远征操作见 :mod:`autowsgr.ui.map.ops`。
"""

from __future__ import annotations

import time

import numpy as np
from loguru import logger

from autowsgr.emulator import AndroidController
from autowsgr.ui.map.data import (
    CHAPTER_MAP_COUNTS,
    CHAPTER_NAV_DELAY,
    CHAPTER_NAV_MAX_ATTEMPTS,
    CHAPTER_SPACING,
    CLICK_BACK,
    CLICK_ENTER_SORTIE,
    CLICK_MAP_NEXT,
    CLICK_MAP_PREV,
    CLICK_PANEL,
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
from autowsgr.ui.map.ops import _MapPageOpsMixin
from autowsgr.types import PageName
from autowsgr.ui.page import click_and_wait_for_page
from autowsgr.ui.tabbed_page import (
    TabbedPageType,
    get_active_tab_index,
    identify_page_type,
    make_tab_checker,
)
from autowsgr.vision import OCREngine, PixelChecker


# ═══════════════════════════════════════════════════════════════════════════════
# 页面控制器
# ═══════════════════════════════════════════════════════════════════════════════


class MapPage(_MapPageOpsMixin):
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
        if idx is None or idx >= len(PANEL_LIST):
            return None
        return PANEL_LIST[idx]

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
            source=PageName.MAP,
            target=PageName.MAIN,
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
        target_idx = PANEL_TO_INDEX[panel]
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

    # ── 动作 — 进入出征 (地图 → 出征准备) ───────────────────────────────

    def enter_sortie(self, chapter: int | str, map_num: int | str) -> None:
        """进入出征: 选择指定章节和地图节点，直接到达出征准备页面。

        Parameters
        ----------
        chapter:
            目标章节编号 (1–9) 或事件地图标识字符串。
        map_num:
            目标地图节点编号 (1–6) 或事件地图标识字符串。

        Raises
        ------
        ValueError
            章节或地图编号无效 (仅数字模式)。
        NavigationError
            导航超时。
        """
        from autowsgr.ui.battle.preparation import BattlePreparationPage

        logger.info("[UI] 地图页面 → 进入出征 {}-{}", chapter, map_num)

        # 1. 确保在出征面板
        screen = self._ctrl.screenshot()
        if self.get_active_panel(screen) != MapPanel.SORTIE:
            self.switch_panel(MapPanel.SORTIE)
            time.sleep(0.5)

        # 2. 导航到指定章节
        if isinstance(chapter, int):
            max_maps = CHAPTER_MAP_COUNTS.get(chapter, 0)
            if max_maps == 0:
                raise ValueError(f"章节 {chapter} 不在已知地图数据中")
            if isinstance(map_num, int) and not 1 <= map_num <= max_maps:
                raise ValueError(
                    f"章节 {chapter} 的地图编号必须为 1–{max_maps}，收到: {map_num}"
                )
            result = self.navigate_to_chapter(chapter)
            if result is None:
                from autowsgr.ui.page import NavigationError
                raise NavigationError(f"无法导航到第 {chapter} 章")

        # 3. 切换到指定地图节点
        if isinstance(map_num, int) and self._ocr is not None:
            screen = self._ctrl.screenshot()
            info = self.recognize_map(screen, self._ocr)
            if info is not None:
                current_map = info.map_num
                if current_map != map_num:
                    delta = map_num - current_map
                    if delta > 0:
                        for _ in range(delta):
                            self._ctrl.click(*CLICK_MAP_NEXT)
                            time.sleep(0.3)
                    else:
                        for _ in range(-delta):
                            self._ctrl.click(*CLICK_MAP_PREV)
                            time.sleep(0.3)
                    time.sleep(0.5)

        # 4. 点击进入出征准备
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_ENTER_SORTIE,
            checker=BattlePreparationPage.is_current_page,
            source=f"地图-出征 {chapter}-{map_num}",
            target=PageName.BATTLE_PREP,
        )
