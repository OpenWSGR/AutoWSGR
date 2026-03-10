"""地图页面基类 — 声明共享依赖与公共查询方法。

所有面板 Mixin 均继承 :class:`BaseMapPage`，
最终由 :class:`~autowsgr.ui.map.page.MapPage` 组合为完整控制器。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from autowsgr.infra.logger import get_logger
from autowsgr.types import PageName
from autowsgr.ui.map.data import (
    CLICK_BACK,
    CLICK_PANEL,
    CLICK_SCREEN_CENTER,
    EXPEDITION_NOTIF_COLOR,
    EXPEDITION_NOTIF_PROBE,
    EXPEDITION_TOLERANCE,
    PANEL_LIST,
    PANEL_TO_INDEX,
    SIDEBAR_BRIGHTNESS_THRESHOLD,
    SIDEBAR_SCAN_STEP,
    SIDEBAR_SCAN_X,
    SIDEBAR_SCAN_Y_RANGE,
    TITLE_CROP_REGION,
    MapIdentity,
    MapPanel,
    parse_map_title,
)
from autowsgr.ui.tabbed_page import (
    TabbedPageType,
    get_active_tab_index,
    identify_page_type,
    make_tab_checker,
)
from autowsgr.ui.utils import NavigationError, click_and_wait_for_page
from autowsgr.vision import OCREngine, PixelChecker


if TYPE_CHECKING:
    import numpy as np

    from autowsgr.context import GameContext


_log = get_logger('ui')


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
        ctx: GameContext,
    ) -> None:
        self._ctx = ctx
        self._ctrl = ctx.ctrl
        self._ocr = ctx.ocr

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
        _log.debug(
            '[UI] 侧边栏选中章节: y_center={:.3f} ({}个亮点)',
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
            _log.debug('[UI] 地图标题 OCR 无结果')
            return None

        info = parse_map_title(result.text)
        if info is None:
            _log.debug("[UI] 地图标题解析失败: '{}'", result.text)
        else:
            _log.debug(
                '[UI] 地图识别: 第{}章 {}-{} {}',
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

        _log.info('[UI] 地图页面 → 回退')
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_BACK,
            checker=MainPage.is_current_page,
            source=PageName.MAP,
            target=PageName.MAIN,
        )

    _PANEL_SWITCH_MAX_RETRIES = 3
    _PANEL_SWITCH_RETRY_DELAY = 1.0

    def switch_panel(self, panel: MapPanel) -> None:
        """切换到指定面板标签并验证到达。"""
        current = self.get_active_panel(self._ctrl.screenshot())
        _log.info(
            '[UI] 地图页面: {} → {}',
            current.value if current else '未知',
            panel.value,
        )
        target_idx = PANEL_TO_INDEX[panel]
        source = f'地图-{current.value if current else "?"}'
        target = f'地图-{panel.value}'
        last_err: NavigationError | None = None

        for attempt in range(1, self._PANEL_SWITCH_MAX_RETRIES + 1):
            if attempt > 1:
                _log.warning(
                    '[UI] 面板切换重试 {}/{}: {} -> {} (等 {:.1f}s)',
                    attempt,
                    self._PANEL_SWITCH_MAX_RETRIES,
                    source,
                    target,
                    self._PANEL_SWITCH_RETRY_DELAY,
                )
                time.sleep(self._PANEL_SWITCH_RETRY_DELAY)

            try:
                click_and_wait_for_page(
                    self._ctrl,
                    click_coord=CLICK_PANEL[panel],
                    checker=make_tab_checker(TabbedPageType.MAP, target_idx),
                    source=source,
                    target=target,
                )
                return
            except NavigationError as e:
                last_err = e
                _log.warning(
                    '[UI] 面板切换失败 ({}/{}): {} -> {}',
                    attempt,
                    self._PANEL_SWITCH_MAX_RETRIES,
                    source,
                    target,
                )

        raise NavigationError(
            f'面板切换失败 (已重试 {self._PANEL_SWITCH_MAX_RETRIES} 次): {source} -> {target}',
            screen=self._ctrl.screenshot(),
        ) from last_err

    def ensure_panel(self, panel: MapPanel) -> None:
        """确保当前处于指定面板，若不是则切换。"""
        screen = self._ctrl.screenshot()
        if self.get_active_panel(screen) != panel:
            self.switch_panel(panel)

    def click_screen_center(self) -> None:
        """点击屏幕中央 — 用于跳过动画/确认弹窗。"""
        self._ctrl.click(*CLICK_SCREEN_CENTER)
