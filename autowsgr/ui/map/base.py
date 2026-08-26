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
        """扫描侧边栏, 定位选中章节高亮条的 y 坐标。

        单级算法: 自适应阈值 + 连续段 (中心加权)。
          - 阈值 = max(峰值亮度×0.70, 均值+40), 放宽以兼容不同高亮主题;
          - 邻接高亮点合并为「段」, 取最长段 (≥2 step 合格) 的亮度加权中心;
          - 段覆盖 3%~60% 视为有效; 超出该范围直接返回 None。
          - **不再使用 Top-K 均值降级**: 之前 12% 亮点加权均值实际等价
            于「侧边栏所有文字像素亮度中心」≈ 屏幕 0.45~0.5 固定区域,
            与真实选中章高亮位置完全无关, 导致 target_y 恒定跳错。
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

        # ── 第 2 步: 自适应阈值 (0.70*峰值 / 均值+40, 比旧版 avg+80 宽松 2x) ──
        adaptive_threshold = max(int(max_bright * 0.70), int(avg_bright) + 40)

        # ── 第 3 步: 连续段 (≥2 step 合格) ──
        segments: list[list[tuple[float, int]]] = []  # [(y, brightness)]
        current: list[tuple[float, int]] = []
        prev_y: float | None = None

        for yy, br in zip(ys, brights):
            if br >= adaptive_threshold:
                if prev_y is not None and (yy - prev_y) <= step * 1.5:
                    current.append((yy, br))
                else:
                    if current:
                        segments.append(current)
                    current = [(yy, br)]
                prev_y = yy
            else:
                if current:
                    segments.append(current)
                    current = []
                prev_y = None
        if current:
            segments.append(current)

        MIN_SEG_STEPS = 2  # ≥2 个连续采样点 (≈0.02 高度) 才认为是高亮条
        valid = [seg for seg in segments if len(seg) >= MIN_SEG_STEPS]
        segs_info = sorted(
            ((len(s), min(x[0] for x in s), max(x[0] for x in s)) for s in segments),
            reverse=True,
        )[:3]

        if not valid:
            _log.debug(
                '[UI] 侧边栏无有效高亮段 (segs={}, 最长段={}, max_br={} avg_br={} th={})',
                len(segments),
                segs_info[0] if segs_info else 'none',
                max_bright, int(avg_bright), adaptive_threshold,
            )
            return None

        # 取最长段, 以亮度加权求中心 (比纯平均更贴近高亮条峰值位置)
        longest = max(valid, key=lambda s: len(s))
        cover = len(longest) / total_count
        if not (0.03 <= cover <= 0.60):
            _log.debug(
                '[UI] 侧边栏高亮段覆盖异常 cover={:.0%} (segs={} valid={}), 放弃',
                cover, len(segments), len(valid),
            )
            return None

        total_w = sum(x[1] for x in longest)
        if total_w <= 0:
            return None
        center = sum(x[0] * x[1] for x in longest) / total_w
        y_start = longest[0][0]
        y_end = longest[-1][0]
        _log.debug(
            '[UI] 侧边栏选中章 y={:.3f} (段长{}点 {:.3f}-{:.3f}, max_br={} avg_br={} th={} cover={:.0%})',
            center, len(longest), y_start, y_end,
            max_bright, int(avg_bright), adaptive_threshold, cover,
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
