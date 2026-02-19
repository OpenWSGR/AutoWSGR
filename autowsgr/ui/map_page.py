"""地图页面 UI 控制器。

覆盖 **地图选择** 页面的全部界面交互。

页面布局::

    ┌──────────────────────────────────────────────────────────────┐
    │ ◁   [出征]  演习   远征   战役   决战                       │
    │                                                 🔴 (远征通知) │
    ├────────┬─────────────────────────────────────────────────────┤
    │ 第六章  │                                                    │
    │ 第七章  │              地图显示区域                           │
    │ 第八章  │                                                    │
    │[第九章] │         9-5/南大洋群岛  ✓ 已通关                  │
    │        │    A ── B ── C ── D                                 │
    │        │         │         │                                 │
    │        │    E ── F ── G ── H                                 │
    │        │              ···                                    │
    └────────┴─────────────────────────────────────────────────────┘

    [ ] = 当前选中项
    🔴  = 远征完成通知 (橙色圆点)

坐标体系:
    所有坐标为相对值 (0.0–1.0)，与分辨率无关。
    分为 **探测坐标** (采样颜色用于状态检测) 和 **点击坐标** (执行操作)。

使用方式::

    from autowsgr.ui.map_page import MapPage, MapPanel

    page = MapPage(ctrl)

    # 状态查询 (静态方法，只需截图)
    screen = ctrl.screenshot()
    if MapPage.is_current_page(screen):
        panel = MapPage.get_active_panel(screen)
        has_exp = MapPage.has_expedition_notification(screen)

    # 面板切换
    page.switch_panel(MapPanel.BATTLE)

    # 章节切换 (需要 OCR 引擎)
    from autowsgr.vision.ocr import OCREngine
    ocr = OCREngine.create("easyocr")
    page = MapPage(ctrl, ocr=ocr)
    page.navigate_to_chapter(5)
"""

from __future__ import annotations

import enum
import re
import time
from dataclasses import dataclass

import numpy as np
from loguru import logger

from autowsgr.emulator.controller import AndroidController
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
# 数据类
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class MapIdentity:
    """地图标识信息 (通过 OCR 解析地图标题得到)。

    Attributes
    ----------
    chapter:
        章节号 (1–9)。
    map_num:
        关卡号 (如 1–6)。
    name:
        地图名称，如 ``"南大洋群岛"``。
    raw_text:
        OCR 原始文本。
    """

    chapter: int
    map_num: int
    name: str
    raw_text: str


# ═══════════════════════════════════════════════════════════════════════════════
# 选中态参考颜色 (RGB)
# ═══════════════════════════════════════════════════════════════════════════════

_PANEL_ACTIVE = Color.of(15, 128, 220)
"""面板标签选中态颜色 — 明亮蓝色。"""

_EXPEDITION_NOTIF_COLOR = Color.of(245, 88, 47)
"""远征通知颜色 — 橙红色圆点。"""

_STATE_TOLERANCE = 30.0
"""状态检测颜色容差。"""

_EXPEDITION_TOLERANCE = 40.0
"""远征通知检测颜色容差 (稍宽松以适应动画)。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 探测坐标 — 采样颜色判断状态
# ═══════════════════════════════════════════════════════════════════════════════

PANEL_PROBE: dict[MapPanel, tuple[float, float]] = {
    MapPanel.SORTIE:     (0.2177, 0.0574),
    MapPanel.EXERCISE:   (0.3469, 0.0593),
    MapPanel.EXPEDITION: (0.4786, 0.0620),
    MapPanel.BATTLE:     (0.6062, 0.0574),
    MapPanel.DECISIVE:   (0.7365, 0.0574),
}
"""面板标签探测点。选中项探测颜色 ≈ (15, 128, 220)。"""

EXPEDITION_NOTIF_PROBE: tuple[float, float] = (0.4953, 0.0213)
"""远征通知探测点。有远征完成时显示橙色 ≈ (245, 88, 47)。"""

TITLE_CROP_REGION: tuple[float, float, float, float] = (0.62, 0.12, 0.92, 0.17)
"""地图标题 OCR 裁切区域 (x1, y1, x2, y2)，用于识别当前地图。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 侧边栏参数 — 章节检测与导航
# ═══════════════════════════════════════════════════════════════════════════════

SIDEBAR_SCAN_X: float = 0.08
"""侧边栏竖向扫描 x 坐标。"""

SIDEBAR_SCAN_Y_RANGE: tuple[float, float] = (0.12, 0.88)
"""侧边栏竖向扫描 y 范围 (min, max)。"""

SIDEBAR_SCAN_STEP: float = 0.01
"""侧边栏扫描步长。"""

SIDEBAR_BRIGHTNESS_THRESHOLD: int = 150
"""选中章节的亮度阈值 (R+G+B)。

选中章节有彩色图标 (如黄色岛屿 ≈ 252,227,47 → 亮度526)，
未选中章节为深色 (如 ≈ 24,40,65 → 亮度129)。
"""

CHAPTER_SPACING: float = 0.12
"""章节条目之间的 y 间距 (估算值)。"""

SIDEBAR_CLICK_X: float = 0.10
"""侧边栏点击的 x 坐标。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 点击坐标 — 执行操作
# ═══════════════════════════════════════════════════════════════════════════════

CLICK_BACK: tuple[float, float] = (0.022, 0.058)
"""回退按钮 (◁)。"""

CLICK_PANEL: dict[MapPanel, tuple[float, float]] = {
    MapPanel.SORTIE:     (0.2177, 0.0574),
    MapPanel.EXERCISE:   (0.3469, 0.0593),
    MapPanel.EXPEDITION: (0.4786, 0.0620),
    MapPanel.BATTLE:     (0.6062, 0.0574),
    MapPanel.DECISIVE:   (0.7365, 0.0574),
}
"""面板标签点击位置。"""

TOTAL_CHAPTERS: int = 9
"""总章节数。"""

CHAPTER_NAV_DELAY: float = 0.5
"""章节切换后等待动画的延迟 (秒)。"""

CHAPTER_NAV_MAX_ATTEMPTS: int = 12
"""章节导航最大尝试次数。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════════


def parse_map_title(text: str) -> MapIdentity | None:
    """解析地图标题文本。

    支持以下格式::

        "9-5南大洋群岛"
        "9-5/南大洋群岛"
        "9 - 5 南大洋群岛"
        "9-5"

    Parameters
    ----------
    text:
        OCR 识别出的原始文本。

    Returns
    -------
    MapIdentity | None
        解析成功返回地图信息，失败返回 ``None``。

    Examples
    --------
    >>> parse_map_title("9-5南大洋群岛")
    MapIdentity(chapter=9, map_num=5, name='南大洋群岛', raw_text='9-5南大洋群岛')
    >>> parse_map_title("3-4/北大西洋")
    MapIdentity(chapter=3, map_num=4, name='北大西洋', raw_text='3-4/北大西洋')
    >>> parse_map_title("无效文本") is None
    True
    """
    # 匹配 "X-Y" 格式，可选地跟随分隔符和地图名称
    match = re.search(r"(\d+)\s*[-–—]\s*(\d+)\s*[/／]?\s*(.*)", text)
    if not match:
        return None
    chapter = int(match.group(1))
    map_num = int(match.group(2))
    name = match.group(3).strip()
    return MapIdentity(
        chapter=chapter,
        map_num=map_num,
        name=name,
        raw_text=text,
    )


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
        """判断截图是否为地图页面。

        检测逻辑: 5 个面板标签探测点中恰好有 1 个为选中蓝色。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。
        """
        active_count = sum(
            1
            for (x, y) in PANEL_PROBE.values()
            if PixelChecker.get_pixel(screen, x, y).near(
                _PANEL_ACTIVE, _STATE_TOLERANCE
            )
        )
        return active_count == 1

    # ── 状态查询 — 面板 ──────────────────────────────────────────────────

    @staticmethod
    def get_active_panel(screen: np.ndarray) -> MapPanel | None:
        """获取当前激活的面板标签。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。

        Returns
        -------
        MapPanel | None
            当前激活的面板，或 ``None``。
        """
        for panel, (x, y) in PANEL_PROBE.items():
            pixel = PixelChecker.get_pixel(screen, x, y)
            if pixel.near(_PANEL_ACTIVE, _STATE_TOLERANCE):
                return panel
        return None

    # ── 状态查询 — 远征通知 ──────────────────────────────────────────────

    @staticmethod
    def has_expedition_notification(screen: np.ndarray) -> bool:
        """检测是否有远征完成通知。

        远征标签上方出现橙色圆点时返回 ``True``。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。
        """
        x, y = EXPEDITION_NOTIF_PROBE
        return PixelChecker.get_pixel(screen, x, y).near(
            _EXPEDITION_NOTIF_COLOR, _EXPEDITION_TOLERANCE
        )

    # ── 状态查询 — 侧边栏 (章节位置) ────────────────────────────────────

    @staticmethod
    def find_selected_chapter_y(screen: np.ndarray) -> float | None:
        """扫描侧边栏，定位选中章节的 y 坐标。

        通过沿侧边栏竖向扫描，找到亮度显著高于背景的区域，
        返回该区域的中心 y 坐标。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。

        Returns
        -------
        float | None
            选中章节的中心 y 坐标 (0.0–1.0)，未找到返回 ``None``。
        """
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
        """通过 OCR 识别当前地图。

        裁切标题区域并 OCR，解析 ``"X-Y/地图名"`` 格式。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。
        ocr:
            OCR 引擎实例。

        Returns
        -------
        MapIdentity | None
            识别出的地图信息，或 ``None``。
        """
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
        """点击回退按钮 (◁)，返回上一页。"""
        logger.info("[UI] 地图页面 → 回退")
        self._ctrl.click(*CLICK_BACK)

    # ── 动作 — 面板切换 ──────────────────────────────────────────────────

    def switch_panel(self, panel: MapPanel) -> None:
        """切换到指定面板标签。

        Parameters
        ----------
        panel:
            目标面板。
        """
        logger.info("[UI] 地图页面 → {}", panel.value)
        self._ctrl.click(*CLICK_PANEL[panel])

    # ── 动作 — 章节导航 ──────────────────────────────────────────────────

    def click_prev_chapter(self, screen: np.ndarray | None = None) -> bool:
        """点击侧边栏上方章节 (前一章)。

        根据当前选中章节位置，点击上方相邻章节条目。

        Parameters
        ----------
        screen:
            可选截图，省略时自动截取。

        Returns
        -------
        bool
            是否成功定位并点击。
        """
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
        """点击侧边栏下方章节 (后一章)。

        根据当前选中章节位置，点击下方相邻章节条目。

        Parameters
        ----------
        screen:
            可选截图，省略时自动截取。

        Returns
        -------
        bool
            是否成功定位并点击。
        """
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
        """导航到指定章节。

        通过 OCR 识别当前章节，然后反复点击前/后一章直到到达目标。
        每次点击后等待动画完成并重新识别。

        Parameters
        ----------
        target:
            目标章节编号 (1–9)。

        Returns
        -------
        int | None
            最终到达的章节号，导航失败返回 ``None``。

        Raises
        ------
        ValueError
            章节编号超出范围。
        RuntimeError
            未配置 OCR 引擎。
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
