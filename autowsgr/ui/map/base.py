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
    CLICK_EXPEDITION_SKIP,
    CLICK_PANEL,
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
    check_tabbed_page,
    get_active_tab_index,
    make_tab_checker,
)
from autowsgr.ui.utils import NavigationError, click_and_wait_for_page
from autowsgr.vision import OCREngine, PageMatch, PixelChecker


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
    def is_current_page(screen: np.ndarray) -> PageMatch:
        """判断截图是否为地图页面 (返回带覆盖度分数的 PageMatch)。"""
        return check_tabbed_page(screen, TabbedPageType.MAP)

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
        """扫描侧边栏, 定位选中章节高亮条的 y 坐标 (自适应+连续段算法)。

        选中章节在侧边栏上呈现为一段**连续且明显亮于背景**的横向条带。
        离散的文字像素 (每章标题字符) 亮度也高但不是连续段, 会被过滤。

        算法步骤:
          1. 沿 SIDEBAR_SCAN_X 列扫描 SIDEBAR_SCAN_Y_RANGE 区间, 记录每个 y 的亮度 (R+G+B)。
          2. 自适应阈值 = max(峰值亮度 * 0.80, 平均亮度 + 120)。
          3. 对达到阈值的 y, 按邻接关系分组为"连续段" (相邻 step 都亮即合并)。
          4. 丢弃长度 < 3 个 step 的段 (典型为单个文字像素噪音)。
          5. 取最长连续段作为选中章高亮条, 段的中心 y 即为结果。
          6. 若最长段覆盖扫描范围 > 60% → 阈值被背景淹没, 返回 None。
        """
        y_min, y_max = SIDEBAR_SCAN_Y_RANGE
        step = SIDEBAR_SCAN_STEP

        # ── 第 1 步: 全量扫描亮度 ──
        ys: list[float] = []
        brights: list[int] = []
        max_bright = 0
        sum_bright = 0

        y = y_min
        while y <= y_max:
            c = PixelChecker.get_pixel(screen, SIDEBAR_SCAN_X, y)
            brightness = c.r + c.g + c.b
            ys.append(y)
            brights.append(brightness)
            if brightness > max_bright:
                max_bright = brightness
            sum_bright += brightness
            y += step

        total_count = len(ys)
        if total_count == 0:
            _log.warning('[UI] 侧边栏扫描采样为空')
            return None

        avg_bright = sum_bright / total_count

        # ── 第 2 步: 自适应阈值 ──
        adaptive_threshold = max(int(max_bright * 0.80), int(avg_bright) + 120)

        # ── 第 3 步: 连续段分组 (相邻 step 间距=step, 差值≤step 即连续) ──
        segments: list[list[float]] = []  # 每段 = [y1, y2, ...]
        current: list[float] = []
        prev_y: float | None = None

        for yy, br in zip(ys, brights):
            if br >= adaptive_threshold:
                if prev_y is not None and (yy - prev_y) <= step * 1.5:
                    # 与上一个亮邻接 → 合并到当前段
                    current.append(yy)
                else:
                    # 新段
                    if current:
                        segments.append(current)
                    current = [yy]
                prev_y = yy
            else:
                if current:
                    segments.append(current)
                    current = []
                prev_y = None
        if current:
            segments.append(current)

        # ── 第 4 步: 按长度过滤, 取最长段 ──
        MIN_SEGMENT_STEPS = 3  # 最少连续 3 个采样点才视为高亮条 (≈0.03 高度)
        valid = [seg for seg in segments if len(seg) >= MIN_SEGMENT_STEPS]

        if not valid:
            _log.warning(
                '[UI] 侧边栏无有效高亮段 (segs={}, max_len={}, max_br={} avg_br={} th={})',
                len(segments),
                max((len(s) for s in segments), default=0),
                max_bright, int(avg_bright), adaptive_threshold,
            )
            return None

        longest = max(valid, key=len)
        cover_ratio = len(longest) / total_count
        if cover_ratio > 0.60:
            _log.warning(
                '[UI] 侧边栏高亮段覆盖过大 ({:.0%}, len={}/{}), 疑似背景整体偏亮 (max={} th={}), 跳过',
                cover_ratio, len(longest), total_count, max_bright, adaptive_threshold,
            )
            return None

        center = sum(longest) / len(longest)
        y_start, y_end = longest[0], longest[-1]
        _log.debug(
            '[UI] 侧边栏选中章 y={:.3f} (段长{}点 {:.3f}-{:.3f}, max_br={} avg_br={} th={} cover={:.0%})',
            center, len(longest), y_start, y_end,
            max_bright, int(avg_bright), adaptive_threshold, cover_ratio,
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
        result = ocr.recognize_maxlen(cropped)
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
            except NavigationError as e:
                last_err = e
                _log.warning(
                    '[UI] 面板切换失败 ({}/{}): {} -> {}',
                    attempt,
                    self._PANEL_SWITCH_MAX_RETRIES,
                    source,
                    target,
                )
            else:
                return

        raise NavigationError(
            f'面板切换失败 (已重试 {self._PANEL_SWITCH_MAX_RETRIES} 次): {source} -> {target}',
            screen=self._ctrl.screenshot(),
        ) from last_err

    def ensure_panel(self, panel: MapPanel) -> None:
        """确保当前处于指定面板，若不是则切换。"""
        screen = self._ctrl.screenshot()
        if self.get_active_panel(screen) != panel:
            self.switch_panel(panel)

    def click_expedition_skip(self) -> None:
        """点击屏幕右侧 — 用于跳过远征动画。"""
        self._ctrl.click(*CLICK_EXPEDITION_SKIP)
