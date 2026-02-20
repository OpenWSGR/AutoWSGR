"""地图数据 — 地图数据库、坐标常量、OCR 解析。

从 ``map_page.py`` 中分离的纯数据与解析逻辑，供 ``MapPage`` 及其他模块引用。
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass

from loguru import logger

from autowsgr.vision.matcher import Color


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
# 地图数据库
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
"""已知地图 (章节, 关卡号) → 名称。"""

CHAPTER_MAP_COUNTS: dict[int, int] = {}
"""每章含有的地图数量 (自动从 MAP_DATABASE 推算)。"""

for _ch, _mn in MAP_DATABASE:
    CHAPTER_MAP_COUNTS[_ch] = max(CHAPTER_MAP_COUNTS.get(_ch, 0), _mn)


TOTAL_CHAPTERS: int = 9
"""总章节数。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 参考颜色 (RGB)
# ═══════════════════════════════════════════════════════════════════════════════

EXPEDITION_NOTIF_COLOR = Color.of(245, 88, 47)
"""远征通知颜色 — 橙红色圆点。"""

EXPEDITION_TOLERANCE = 40.0
"""远征通知检测颜色容差 (稍宽松以适应动画)。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 探测坐标
# ═══════════════════════════════════════════════════════════════════════════════

EXPEDITION_NOTIF_PROBE: tuple[float, float] = (0.4953, 0.0213)
"""远征通知探测点。有远征完成时显示橙色 ≈ (245, 88, 47)。"""

TITLE_CROP_REGION: tuple[float, float, float, float] = (0.7, 0.18, 0.9, 0.215)
"""地图标题 OCR 裁切区域 (x1, y1, x2, y2)。"""


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
"""选中章节的亮度阈值 (R+G+B)。"""

CHAPTER_SPACING: float = 0.12
"""章节条目之间的 y 间距 (估算值)。"""

SIDEBAR_CLICK_X: float = 0.10
"""侧边栏点击的 x 坐标。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 点击坐标
# ═══════════════════════════════════════════════════════════════════════════════

CLICK_BACK: tuple[float, float] = (0.022, 0.058)
"""回退按钮 (◁)。"""

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

        "9-5南大洋群岛"    "9-5/南大洋群岛"
        "9 - 5 南大洋群岛" "9-5"

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
    """
    # ── 第 1 步: 严格单位数匹配 ──
    m = re.search(r"(\d)\s*[-–—]\s*(\d)\s*[/／]?\s*(.*)", text)
    if m:
        chapter = int(m.group(1))
        map_num = int(m.group(2))
        name = m.group(3).strip()

        # OCR 粘连修正: 名称开头可能残留数字
        cleaned_name = re.sub(r"^\d+", "", name).strip()

        db_name = MAP_DATABASE.get((chapter, map_num))
        if db_name is not None:
            name = db_name
        elif cleaned_name != name:
            logger.debug(
                "[UI] OCR 名称残留数字: '{}' → '{}'",
                name,
                cleaned_name,
            )
            name = cleaned_name

        return MapIdentity(
            chapter=chapter,
            map_num=map_num,
            name=name,
            raw_text=text,
        )

    # ── 第 2 步: 多位数匹配 + 校正 ──
    m = re.search(r"(\d+)\s*[-–—]\s*(\d+)\s*[/／]?\s*(.*)", text)
    if not m:
        return None

    raw_chapter = int(m.group(1))
    raw_map_num = int(m.group(2))
    raw_name = m.group(3).strip()

    # 尝试将多位数 map_num 拆成 "首位 + 剩余" 进行校正
    if raw_map_num >= 10 and 1 <= raw_chapter <= TOTAL_CHAPTERS:
        map_str = str(raw_map_num)
        candidate = int(map_str[0])

        if (raw_chapter, candidate) in MAP_DATABASE:
            db_name = MAP_DATABASE[(raw_chapter, candidate)]
            logger.debug(
                "[UI] OCR 校正: '{}'→{}-{} '{}' (数据库: '{}')",
                text,
                raw_chapter,
                candidate,
                raw_name,
                db_name,
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
# 地图页面点击坐标
# ═══════════════════════════════════════════════════════════════════════════════

# ── 战役坐标 ──

CAMPAIGN_POSITIONS: dict[int, tuple[float, float]] = {
    1: (0.350, 0.225),   # 航母 (carrier)
    2: (0.350, 0.400),   # 潜艇 (submarine)
    3: (0.350, 0.575),   # 驱逐 (destroyer)
    4: (0.350, 0.750),   # 巡洋 (cruiser)
    5: (0.350, 0.900),   # 战列 (battleship)
}
"""5 种战役类型的点击位置。"""

CAMPAIGN_NAMES: dict[int, str] = {
    1: "航母",
    2: "潜艇",
    3: "驱逐",
    4: "巡洋",
    5: "战列",
}
"""战役编号 → 中文名称。"""

CLICK_DIFFICULTY_EASY: tuple[float, float] = (0.800, 0.130)
"""切换到「简单」难度。"""

CLICK_DIFFICULTY_HARD: tuple[float, float] = (0.900, 0.130)
"""切换到「困难」难度。"""

CLICK_ENTER_CAMPAIGN: tuple[float, float] = (0.850, 0.500)
"""点击进入战役 (选中战役后的确认)。"""

# ── 出征地图节点切换 ──

CLICK_MAP_NEXT: tuple[float, float] = (937 / 960, 277 / 540)
"""出征面板中地图节点向右切换 (→)。"""

CLICK_MAP_PREV: tuple[float, float] = (247 / 960, 277 / 540)
"""出征面板中地图节点向左切换 (←)。"""

CLICK_ENTER_SORTIE: tuple[float, float] = (0.625, 0.556)
"""出征面板中点击地图节点进入出征准备。"""

# ── 决战面板进入 ──

CLICK_ENTER_DECISIVE: tuple[float, float] = (115 / 960, 113 / 540)
"""从地图页「决战」面板点击进入决战总览页。"""

# ── 出征地图节点 ──

MAP_NODE_POSITIONS: dict[int, tuple[float, float]] = {
    1: (0.500, 0.200),
    2: (0.500, 0.350),
    3: (0.500, 0.500),
    4: (0.500, 0.650),
    5: (0.500, 0.800),
}
"""出征面板中各地图节点的点击位置 (1–5, 从上到下)。"""

# ── 演习坐标 ──

RIVAL_POSITIONS: list[tuple[float, float]] = [
    (0.800, 0.222),
    (0.800, 0.444),
    (0.800, 0.667),
    (0.800, 0.889),
]
"""演习面板中 4 个对手位置的「挑战」按钮。"""

CLICK_REFRESH_RIVALS: tuple[float, float] = (0.938, 0.056)
"""演习面板 — 刷新对手按钮 (右上角)。"""

CLICK_CHALLENGE: tuple[float, float] = (0.800, 0.500)
"""演习面板 — 通用挑战按钮。"""

# ── 远征 ──

CLICK_SCREEN_CENTER: tuple[float, float] = (0.5, 0.5)
"""屏幕中央 — 用于闪过动画/确认弹窗。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 面板枚举及映射
# ═══════════════════════════════════════════════════════════════════════════════


class MapPanel(enum.Enum):
    """地图页面顶部导航面板。"""

    SORTIE = "出征"
    EXERCISE = "演习"
    EXPEDITION = "远征"
    BATTLE = "战役"
    DECISIVE = "决战"


PANEL_LIST: list[MapPanel] = list(MapPanel)
"""面板枚举值列表 — 索引与标签栏探测位置一一对应。"""

PANEL_TO_INDEX: dict[MapPanel, int] = {
    panel: i for i, panel in enumerate(PANEL_LIST)
}

CLICK_PANEL: dict[MapPanel, tuple[float, float]] = {
    MapPanel.SORTIE:     (0.1396, 0.0574),
    MapPanel.EXERCISE:   (0.2745, 0.0537),
    MapPanel.EXPEDITION: (0.4042, 0.0556),
    MapPanel.BATTLE:     (0.5276, 0.0519),
    MapPanel.DECISIVE:   (0.6620, 0.0556),
}
"""面板标签点击位置。"""
