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
from autowsgr.ui.page import click_and_wait_for_page, wait_for_page
from autowsgr.vision.matcher import Color, MatchStrategy, PixelChecker, PixelRule, PixelSignature
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
# 参考颜色 (RGB)
# ═══════════════════════════════════════════════════════════════════════════════

_EXPEDITION_NOTIF_COLOR = Color.of(245, 88, 47)
"""远征通知颜色 — 橙红色圆点。"""

_EXPEDITION_TOLERANCE = 40.0
"""远征通知检测颜色容差 (稍宽松以适应动画)。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 已知地图数据库 — 用于 OCR 校正
# ═══════════════════════════════════════════════════════════════════════════════

MAP_DATABASE: dict[tuple[int, int], str] = {
    # 第一章：母港周边哨戒
    (1, 1): "母港附近海域",
    (1, 2): "东北防线海域",
    (1, 3): "仁州附近海域",
    (1, 4): "深海仁州基地",
    (1, 5): "乌兰巴托附近水域",
    # 第二章：扶桑海域攻略
    (2, 1): "扶桑西部海域",
    (2, 2): "扶桑西南海域",
    (2, 3): "扶桑南部海域",
    (2, 4): "深海扶桑基地",
    (2, 5): "深海前哨核心地区",
    (2, 6): "深海前哨北方地区",
    # 第三章：星洲海峡突破
    (3, 1): "母港南部海域",
    (3, 2): "东南群岛（1）",
    (3, 3): "东南群岛（2）",
    (3, 4): "星洲海峡",
    # 第四章：西行航线开辟
    (4, 1): "克拉代夫东部海域",
    (4, 2): "克拉代夫西部海域",
    (4, 3): "泪之扉附近海域",
    (4, 4): "泪之扉防线",
    # 第五章：地中海死斗
    (5, 1): "塞浦路斯附近海域",
    (5, 2): "克里特附近海域",
    (5, 3): "马耳他附近海域",
    (5, 4): "直布罗陀东部海域",
    (5, 5): "直布罗陀要塞",
    # 第六章：北海风暴
    (6, 1): "洛里昂南部海域",
    (6, 2): "英吉利海峡",
    (6, 3): "斯卡帕湾",
    (6, 4): "丹麦海峡",
    # 第七章：比斯开湾战役
    (7, 1): "比斯开湾",
    (7, 2): "马德拉海域",
    (7, 3): "亚速尔海域",
    (7, 4): "百慕大三角附近海域",
    (7, 5): "百慕大三角防波堤",
    # 第八章：新大陆海域鏖战
    (8, 1): "百慕大中心海域",
    (8, 2): "百慕大南群岛",
    (8, 3): "北加勒比海域",
    (8, 4): "东部海岸群岛",
    (8, 5): "地峡海湾",
    # 第九章：南狭长海域
    (9, 1): "地峡外海",
    (9, 2): "大洋南湾",
    (9, 3): "南入海口海域",
    (9, 4): "河口外海",
    (9, 5): "南大洋群岛",
}
"""已知地图 (章节, 关卡号) → 名称。

用于 OCR 校正: 当 OCR 将地图名首字误拼为数字时 (如 ``"9-51南大洋群岛"``
本应为 ``"9-5/南大洋群岛"``), 可通过已知数据修正。
"""

CHAPTER_MAP_COUNTS: dict[int, int] = {}
"""每章含有的地图数量 (自动从 MAP_DATABASE 推算)。"""

for _ch, _mn in MAP_DATABASE:
    CHAPTER_MAP_COUNTS[_ch] = max(CHAPTER_MAP_COUNTS.get(_ch, 0), _mn)


# ═══════════════════════════════════════════════════════════════════════════════
# 各面板独立像素签名 (来自 sig.py 重新采集)
# ═══════════════════════════════════════════════════════════════════════════════

PANEL_SIGNATURES: dict[MapPanel, PixelSignature] = {
    MapPanel.SORTIE: PixelSignature(
        name="map_page出征",
        strategy=MatchStrategy.ALL,
        rules=[
            PixelRule.of(0.8938, 0.0602, (241, 96, 69),  tolerance=30.0),
            PixelRule.of(0.1437, 0.0519, (15, 132, 228), tolerance=30.0),
            PixelRule.of(0.0359, 0.5620, (253, 226, 47), tolerance=30.0),
        ],
    ),
    MapPanel.EXERCISE: PixelSignature(
        name="map_page演习",
        strategy=MatchStrategy.ALL,
        rules=[
            PixelRule.of(0.2677, 0.0472, (15, 132, 228),  tolerance=30.0),
            PixelRule.of(0.1406, 0.0509, (18, 21, 40),    tolerance=30.0),
            PixelRule.of(0.0292, 0.0574, (164, 167, 176), tolerance=30.0),
            PixelRule.of(0.4161, 0.0556, (20, 34, 60),    tolerance=30.0),
            PixelRule.of(0.5443, 0.0556, (20, 36, 59),    tolerance=30.0),
            PixelRule.of(0.6807, 0.0444, (26, 38, 62),    tolerance=30.0),
            PixelRule.of(0.4578, 0.0593, (138, 146, 165), tolerance=30.0),
            PixelRule.of(0.3208, 0.0472, (9, 130, 234),   tolerance=30.0),
            PixelRule.of(0.3010, 0.0639, (15, 139, 239),  tolerance=30.0),
        ],
    ),
    MapPanel.EXPEDITION: PixelSignature(
        name="map_page远征",
        strategy=MatchStrategy.ALL,
        rules=[
            PixelRule.of(0.4021, 0.0509, (15, 132, 228), tolerance=30.0),
            PixelRule.of(0.0380, 0.5722, (253, 226, 47), tolerance=30.0),
            PixelRule.of(0.5208, 0.0602, (22, 38, 63),   tolerance=30.0),
            PixelRule.of(0.2661, 0.0574, (21, 36, 59),   tolerance=30.0),
        ],
    ),
    MapPanel.BATTLE: PixelSignature(
        name="map_page战役",
        strategy=MatchStrategy.ALL,
        rules=[
            PixelRule.of(0.6057, 0.0491, (17, 127, 222),  tolerance=30.0),
            PixelRule.of(0.9542, 0.1509, (240, 220, 11),  tolerance=30.0),
            PixelRule.of(0.2260, 0.1565, (100, 99, 95),   tolerance=30.0),
            PixelRule.of(0.1094, 0.1565, (104, 104, 102), tolerance=30.0),
            PixelRule.of(0.4589, 0.1574, (105, 109, 110), tolerance=30.0),
        ],
    ),
    MapPanel.DECISIVE: PixelSignature(
        name="map_page决战",
        strategy=MatchStrategy.ALL,
        rules=[
            PixelRule.of(0.1797, 0.1731, (247, 68, 90),   tolerance=30.0),
            PixelRule.of(0.1651, 0.3907, (227, 203, 216), tolerance=30.0),
            PixelRule.of(0.1240, 0.4611, (255, 210, 253), tolerance=30.0),
            PixelRule.of(0.6583, 0.0454, (15, 132, 228),  tolerance=30.0),
            PixelRule.of(0.1880, 0.3833, (229, 196, 213), tolerance=30.0),
            PixelRule.of(0.0943, 0.2417, (238, 219, 215), tolerance=30.0),
        ],
    ),
}
"""各面板独立像素签名 — 5 个 panel 分别采集，互相独立。

``is_current_page`` = 任意一个签名匹配；
``get_active_panel`` = 第一个匹配的签名对应的 panel。
"""

EXPEDITION_NOTIF_PROBE: tuple[float, float] = (0.4953, 0.0213)
"""远征通知探测点。有远征完成时显示橙色 ≈ (245, 88, 47)。"""

TITLE_CROP_REGION: tuple[float, float, float, float] = (0.7, 0.18, 0.9, 0.215)
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
    MapPanel.SORTIE:     (0.1396, 0.0574),
    MapPanel.EXERCISE:   (0.2745, 0.0537),
    MapPanel.EXPEDITION: (0.4042, 0.0556),
    MapPanel.BATTLE:     (0.5276, 0.0519),
    MapPanel.DECISIVE:   (0.6620, 0.0556),
}
"""面板标签点击位置 (与探测坐标一致)。"""

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

    常规海域的章节号和关卡号均为 **1 位数字** (1–9, 1–6)。
    若 OCR 将地图名首字误拼到数字后 (如 ``"9-51南大洋群岛"``),
    则通过 :data:`MAP_DATABASE` 校正。

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
    >>> parse_map_title("9-51南大洋群岛")  # OCR 误读
    MapIdentity(chapter=9, map_num=5, name='南大洋群岛', raw_text='9-51南大洋群岛')
    >>> parse_map_title("无效文本") is None
    True
    """
    # ── 第 1 步: 严格单位数匹配 (正常情况, 章节 1–9, 关卡 1–6) ──
    m = re.search(r"(\d)\s*[-–—]\s*(\d)\s*[/／]?\s*(.*)", text)
    if m:
        chapter = int(m.group(1))
        map_num = int(m.group(2))
        name = m.group(3).strip()

        # OCR 粘连修正: 名称开头可能残留数字
        # 如 "9-51南大洋群岛" → name="1南大洋群岛"，应去掉 "1"
        cleaned_name = re.sub(r"^\d+", "", name).strip()

        # 若匹配到的是已知地图，优先使用数据库名称
        db_name = MAP_DATABASE.get((chapter, map_num))
        if db_name is not None:
            name = db_name
        elif cleaned_name != name:
            # 不在数据库但有数字残留，使用清理后的名称
            logger.debug(
                "[UI] OCR 名称残留数字: '{}' → '{}'", name, cleaned_name,
            )
            name = cleaned_name

        return MapIdentity(
            chapter=chapter, map_num=map_num, name=name, raw_text=text,
        )

    # ── 第 2 步: 多位数匹配 + 校正 (处理 OCR 粘连) ──
    # 例: "9-51南大洋群岛" → (\d+)=9, (\d+)=51, rest="南大洋群岛"
    m = re.search(r"(\d+)\s*[-–—]\s*(\d+)\s*[/／]?\s*(.*)", text)
    if not m:
        return None

    raw_chapter = int(m.group(1))
    raw_map_num = int(m.group(2))
    raw_name = m.group(3).strip()

    # 尝试将多位数 map_num 拆成 "首位 + 剩余" 进行校正
    # 例: chapter=9, raw_map_num=51 → 尝试 map_num=5, 剩余="1"
    if raw_map_num >= 10 and 1 <= raw_chapter <= TOTAL_CHAPTERS:
        map_str = str(raw_map_num)
        candidate = int(map_str[0])
        extra_digits = map_str[1:]  # 多余的数字 (来自中文首字误识别)

        if (raw_chapter, candidate) in MAP_DATABASE:
            db_name = MAP_DATABASE[(raw_chapter, candidate)]
            logger.debug(
                "[UI] OCR 校正: '{}'→{}-{} '{}' (数据库: '{}')",
                text, raw_chapter, candidate, raw_name, db_name,
            )
            return MapIdentity(
                chapter=raw_chapter,
                map_num=candidate,
                name=db_name,
                raw_text=text,
            )

    # 无法校正，返回原始解析结果
    return MapIdentity(
        chapter=raw_chapter,
        map_num=raw_map_num,
        name=raw_name,
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

        任意一个面板签名 (出征/演习/远征/战役/决战) 匹配即返回 ``True``。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。
        """
        return any(
            PixelChecker.check_signature(screen, sig).matched
            for sig in PANEL_SIGNATURES.values()
        )

    # ── 状态查询 — 面板 ──────────────────────────────────────────────────

    @staticmethod
    def get_active_panel(screen: np.ndarray) -> MapPanel | None:
        """获取当前激活的面板标签。

        遍历 :data:`PANEL_SIGNATURES`，返回第一个匹配签名对应的面板。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。

        Returns
        -------
        MapPanel | None
            当前激活的面板，或 ``None``。
        """
        for panel, sig in PANEL_SIGNATURES.items():
            if PixelChecker.check_signature(screen, sig).matched:
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
        """点击回退按钮 (◁)，返回主页面。

        点击后反复截图验证，确认已到达主页面。

        Raises
        ------
        NavigationError
            超时仍在地图页面。
        """
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
        """切换到指定面板标签并验证到达。

        会先截图判断当前面板状态并记录日志，然后点击目标面板，
        最后验证目标面板签名匹配。

        Parameters
        ----------
        panel:
            目标面板。

        Raises
        ------
        NavigationError
            超时未到达目标面板。
        """
        current = self.get_active_panel(self._ctrl.screenshot())
        logger.info(
            "[UI] 地图页面: {} → {}",
            current.value if current else "未知",
            panel.value,
        )
        target_sig = PANEL_SIGNATURES[panel]
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_PANEL[panel],
            checker=lambda s, sig=target_sig: PixelChecker.check_signature(s, sig).matched,
            source=f"地图-{current.value if current else '?'}",
            target=f"地图-{panel.value}",
        )

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
