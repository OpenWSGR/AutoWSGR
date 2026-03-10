"""任务页面数据 - 枚举、数据结构、常量、坐标。"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from autowsgr.vision.pixel import Color
from autowsgr.vision.roi import ROI


# ═══════════════════════════════════════════════════════════════════════════════
# 面板枚举
# ═══════════════════════════════════════════════════════════════════════════════


class MissionPanel(enum.Enum):
    """任务页面内部子标签。"""

    ALL = '全部'
    MAIN = '主线'
    DAILY = '日常'
    WEEKLY = '周常'
    TIMED = '限时'


PANEL_LIST: list[MissionPanel] = list(MissionPanel)
"""面板枚举值列表。"""

CLICK_PANEL: dict[MissionPanel, tuple[float, float]] = {
    MissionPanel.ALL: (0.1539, 0.0667),
    MissionPanel.MAIN: (0.2797, 0.0681),
    MissionPanel.DAILY: (0.4047, 0.0611),
    MissionPanel.WEEKLY: (0.5406, 0.0583),
    MissionPanel.TIMED: (0.6672, 0.0569),
}
"""面板子标签点击位置。"""

PANEL_SWITCH_DELAY: float = 0.5
"""面板切换后等待 (秒)。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 按钮类型 & 任务数据
# ═══════════════════════════════════════════════════════════════════════════════


class ButtonType(enum.Enum):
    """任务行右侧按钮类型。"""

    GOTO = 'goto'
    """蓝色 "前往" 按钮 - 任务未完成。"""

    CLAIM = 'claim'
    """橙色/金色 "领取" 按钮 - 任务已完成可领取。"""


@dataclass(frozen=True, slots=True)
class MissionInfo:
    """单条任务识别结果。"""

    name: str
    """数据库匹配后的标准任务名 (若未匹配则为 OCR 原始文本)。"""
    raw_text: str
    """OCR 原始识别文本。"""
    progress: int
    """完成百分比 0-100 (-1 表示未能识别)。"""
    claimable: bool
    """是否可领取 (按钮为 "领取")。"""
    confidence: float
    """OCR 置信度 (名称识别)。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 按钮扫描颜色常量
# ═══════════════════════════════════════════════════════════════════════════════

# "前往" 按钮蓝色
GOTO_COLOR = Color(r=15, g=132, b=228)
GOTO_TOLERANCE = 40.0

# "领取" 按钮检测: 高红+中绿+低蓝 (橙/金色)
CLAIM_R_MIN = 180
CLAIM_G_MIN = 120
CLAIM_B_MAX = 80

# 按钮扫描区域 (右侧按钮列)
BUTTON_SCAN_ROI = ROI(0.86, 0.17, 0.96, 0.85)

# 扫描步长 (相对坐标)
SCAN_X: float = 0.91  # 按钮中心 x
SCAN_Y_STEP: float = 0.005  # y 步进

# 聚类阈值: 相对 y 距离小于此值视为同一按钮
# "领取" 按钮中央文字区域会产生 ~0.04 的颜色间断, 需 >= 0.05 才能合并
CLUSTER_GAP: float = 0.06

# 最小聚类大小: 低于此值的簇视为噪点而非真实按钮
MIN_CLUSTER_SIZE: int = 3

# 宽按钮 (一键领取) 过滤: 检测 x 坐标
WIDE_BTN_CHECK_X: float = 0.80

# 名称裁切区域上边界: name_top < 此值表示名称被页面标题栏遮挡, 不可读
NAME_CROP_MIN_Y: float = 0.12

# OCR 置信度下限: 低于此值视为无效识别
OCR_CONFIDENCE_MIN: float = 0.10


# ═══════════════════════════════════════════════════════════════════════════════
# OCR 裁切常量
# ═══════════════════════════════════════════════════════════════════════════════

# 名称裁切
NAME_ROI_X1: float = 0.22
NAME_ROI_X2: float = 0.60
NAME_Y_OFFSET: float = -0.145  # 名称中心在按钮中心上方 (负值)
NAME_ROI_Y_PAD: float = 0.035  # 名称区域上下半高

# 进度裁切
PROGRESS_ROI_X1: float = 0.75
PROGRESS_ROI_X2: float = 0.87
PROGRESS_Y_OFFSET: float = 0.105
PROGRESS_ROI_Y_PAD: float = 0.035

# 进度正则: 匹配 "XX%"
PROGRESS_RE = re.compile(r'(\d{1,3})\s*%')


# ═══════════════════════════════════════════════════════════════════════════════
# 点击坐标
# ═══════════════════════════════════════════════════════════════════════════════

CLICK_BACK: tuple[float, float] = (0.022, 0.058)
"""回退按钮。"""

CLICK_CONFIRM_CENTER: tuple[float, float] = (0.5, 0.5)
"""领取奖励后弹窗确认 - 点击屏幕中央关闭。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 任务数据库
# ═══════════════════════════════════════════════════════════════════════════════

_MISSIONS_YAML = Path(__file__).resolve().parent.parent.parent / 'data' / 'missions.yaml'
_mission_db_cache: dict | None = None


def _load_mission_db() -> dict:
    """加载并缓存任务数据库。"""
    global _mission_db_cache
    if _mission_db_cache is None:
        with open(_MISSIONS_YAML, encoding='utf-8') as f:
            _mission_db_cache = yaml.safe_load(f)
    assert _mission_db_cache is not None
    return _mission_db_cache


def get_all_mission_names() -> list[str]:
    """获取数据库中所有任务名称 (用于模糊匹配)。"""
    db = _load_mission_db()
    names: list[str] = []
    for category in ('daily', 'weekly'):
        for mission in db.get(category, []):
            name = mission['name']
            if name not in names:
                names.append(name)
    return names
