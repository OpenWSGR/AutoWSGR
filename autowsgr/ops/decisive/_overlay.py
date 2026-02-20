"""决战地图页 Overlay 枚举、像素签名与坐标常量。

决战地图页上可能叠加以下三种弹窗::

    FLEET_ACQUISITION  战备舰队获取 — 选择购买舰船/技能
    CONFIRM_EXIT       确认退出     — 暂离(保存) 或 撤退(清空)
    ADVANCE_CHOICE     选择前进点   — 多路径分支选择

每种弹窗均由 ``PixelSignature`` 识别。
``detect_decisive_overlay()`` 按优先级顺序依次检测并返回首个命中结果。
"""

from __future__ import annotations

import enum

import numpy as np
from loguru import logger

from autowsgr.vision.matcher import (
    MatchStrategy,
    PixelChecker,
    PixelRule,
    PixelSignature,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 枚举
# ═══════════════════════════════════════════════════════════════════════════════


class DecisiveOverlay(enum.Enum):
    """决战地图页上的弹窗类型。"""

    FLEET_ACQUISITION = "fleet_acquisition"
    """战备舰队获取 — 选择购买舰船/技能。"""

    CONFIRM_EXIT = "confirm_exit"
    """确认退出 — 暂离或撤退。"""

    ADVANCE_CHOICE = "advance_choice"
    """选择前进点 — 分支路径选择。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 像素签名
# ═══════════════════════════════════════════════════════════════════════════════

# ── 战备舰队获取 ──
# 特征: 顶部「战备舰队获取」白色标题 + 底部刷新/关闭按钮区域
SIG_FLEET_ACQUISITION = PixelSignature(
    name="决战-战备舰队获取",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.4953, 0.1083, (253, 251, 255), tolerance=30.0),
        PixelRule.of(0.5305, 0.1014, (254, 254, 254), tolerance=30.0),
        PixelRule.of(0.4031, 0.1028, (255, 252, 255), tolerance=30.0),
        PixelRule.of(0.4492, 0.1181, (254, 254, 254), tolerance=30.0),
    ],
)

# ── 确认退出 ──
# 特征: 左「暂离」蓝色按钮 + 右「撤退」红色按钮 + 对话框灰色背景
SIG_CONFIRM_EXIT = PixelSignature(
    name="决战-确认退出",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.3430, 0.5667, (29, 124, 214),  tolerance=30.0),
        PixelRule.of(0.4180, 0.5694, (29, 124, 214),  tolerance=30.0),
        PixelRule.of(0.5813, 0.5667, (152, 36, 36),   tolerance=30.0),
        PixelRule.of(0.6578, 0.5639, (156, 38, 38),   tolerance=30.0),
        PixelRule.of(0.4953, 0.4875, (225, 225, 225), tolerance=30.0),
        PixelRule.of(0.5023, 0.2819, (7, 117, 194),   tolerance=30.0),
    ],
)

# ── 选择前进点 ──
# 特征: 底部「确认」蓝色按钮 + 右侧编队/出征按钮变为深色背景 (被遮挡)
SIG_ADVANCE_CHOICE = PixelSignature(
    name="决战-选择前进点",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.4484, 0.8333, (37, 146, 249), tolerance=30.0),
        PixelRule.of(0.4484, 0.8833, (28, 136, 237), tolerance=30.0),
        PixelRule.of(0.5492, 0.8306, (38, 147, 250), tolerance=30.0),
        PixelRule.of(0.5516, 0.8833, (28, 136, 237), tolerance=30.0),
        PixelRule.of(0.7008, 0.9028, (13, 49, 85),   tolerance=30.0),
        PixelRule.of(0.7031, 0.9514, (9, 45, 79),    tolerance=30.0),
        PixelRule.of(0.8695, 0.9042, (13, 49, 85),   tolerance=30.0),
        PixelRule.of(0.8727, 0.9514, (9, 45, 79),    tolerance=30.0),
    ],
)

# ── 决战地图页 (无 overlay) ──
# 特征: 左上角撤退按钮橙色 + 右下角编队/出征三个蓝色按钮
SIG_MAP_PAGE = PixelSignature(
    name="决战-地图页",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.0641, 0.0667, (218, 130, 20), tolerance=30.0),
        PixelRule.of(0.7969, 0.9194, (34, 143, 246), tolerance=30.0),
        PixelRule.of(0.9555, 0.9208, (34, 143, 246), tolerance=30.0),
        PixelRule.of(0.7055, 0.9236, (34, 143, 246), tolerance=30.0),
        PixelRule.of(0.1227, 0.0750, (215, 142, 14), tolerance=30.0),
    ],
)

# 按优先级排列的 overlay → 签名映射
OVERLAY_SIGNATURES: list[tuple[DecisiveOverlay, PixelSignature]] = [
    (DecisiveOverlay.FLEET_ACQUISITION, SIG_FLEET_ACQUISITION),
    (DecisiveOverlay.CONFIRM_EXIT,      SIG_CONFIRM_EXIT),
    (DecisiveOverlay.ADVANCE_CHOICE,    SIG_ADVANCE_CHOICE),
]

_SIG_BY_TYPE: dict[DecisiveOverlay, PixelSignature] = dict(OVERLAY_SIGNATURES)


# ═══════════════════════════════════════════════════════════════════════════════
# 坐标常量 (相对坐标 0.0–1.0, 参考分辨率 960×540)
# ═══════════════════════════════════════════════════════════════════════════════

# ── 决战地图页通用 ──

CLICK_RETREAT_BUTTON: tuple[float, float] = (36 / 960, 33 / 540)
"""左上角「撤退」按钮 — 触发确认退出 overlay。"""

CLICK_SORTIE: tuple[float, float] = (900 / 960, 500 / 540)
"""右下角「出征」按钮 — 进入出征准备页。"""

CLICK_FLEET_EDIT: tuple[float, float] = (700 / 960, 500 / 540)
"""右下角「编队」按钮 — 进入编队页面。"""

CLICK_BUY_EXP: tuple[float, float] = (75 / 960, 500 / 540)
"""左下角「购买经验值」按钮。"""

CLICK_SKILL: tuple[float, float] = (0.2143, 0.894)
"""副官技能按钮。"""

# ── 战备舰队获取 overlay ──

CLICK_FLEET_REFRESH: tuple[float, float] = (380 / 960, 500 / 540)
"""「刷新」按钮 — 刷新备选舰船。"""

CLICK_FLEET_CLOSE: tuple[float, float] = (580 / 960, 500 / 540)
"""「关闭」按钮 — 关闭战备舰队获取 overlay。"""

FLEET_CARD_X_POSITIONS: list[float] = [0.25, 0.375, 0.5, 0.625, 0.75]
"""5 张舰船卡水平中心 X 坐标。"""

FLEET_CARD_CLICK_Y: float = 0.5
"""舰船卡点击 Y 坐标。"""

SHIP_NAME_X_RANGES: list[tuple[float, float]] = [
    (0.195, 0.305),
    (0.318, 0.429),
    (0.445, 0.555),
    (0.571, 0.677),
    (0.695, 0.805),
]
"""5 张舰船卡名称 OCR 区域 X 范围。"""

SHIP_NAME_Y_RANGE: tuple[float, float] = (0.685, 0.715)
"""舰船名称 OCR 区域 Y 范围。"""

COST_AREA: tuple[tuple[float, float], tuple[float, float]] = (
    (0.195, 0.808),
    (0.805, 0.764),
)
"""费用 OCR 整行区域 (x1y1, x2y2)。"""

RESOURCE_AREA: tuple[tuple[float, float], tuple[float, float]] = (
    (0.911, 0.082),
    (0.974, 0.037),
)
"""右上角可用分数 OCR 区域。"""

# ── 确认退出 overlay ──

CLICK_LEAVE: tuple[float, float] = (0.372, 0.584)
"""「暂离」按钮 — 保存进度后退出。"""

CLICK_RETREAT_CONFIRM: tuple[float, float] = (600 / 960, 300 / 540)
"""「撤退」按钮 — 清空进度后退出。"""

# ── 选择前进点 overlay ──

CLICK_ADVANCE_CONFIRM: tuple[float, float] = (0.5, 0.856)
"""「确认」按钮 — 确认前进点选择。"""

ADVANCE_CARD_POSITIONS: list[tuple[float, float]] = [
    (0.35, 0.5),  # 左侧选项 (如 A1)
    (0.65, 0.5),  # 右侧选项 (如 A2)
    (0.50, 0.5),  # 中央选项 (若有第三个)
]
"""前进点卡片点击位置，最多 3 个分支。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 检测函数
# ═══════════════════════════════════════════════════════════════════════════════


def detect_decisive_overlay(screen: np.ndarray) -> DecisiveOverlay | None:
    """按优先级检测决战地图页上的弹窗。

    Parameters
    ----------
    screen:
        截图 (H×W×3, RGB)。

    Returns
    -------
    DecisiveOverlay | None
        首个命中的弹窗类型；无弹窗则返回 ``None``。
    """
    for overlay_type, sig in OVERLAY_SIGNATURES:
        if PixelChecker.check_signature(screen, sig):
            logger.debug("[决战] 检测到 overlay: {}", overlay_type.value)
            return overlay_type
    return None


def is_decisive_map_page(screen: np.ndarray) -> bool:
    """截图是否为决战地图页 (无 overlay 遮挡)。"""
    return PixelChecker.check_signature(screen, SIG_MAP_PAGE).matched


def is_fleet_acquisition(screen: np.ndarray) -> bool:
    """截图是否为战备舰队获取 overlay。"""
    return PixelChecker.check_signature(screen, SIG_FLEET_ACQUISITION).matched


def is_advance_choice(screen: np.ndarray) -> bool:
    """截图是否为选择前进点 overlay。"""
    return PixelChecker.check_signature(screen, SIG_ADVANCE_CHOICE).matched


def is_confirm_exit(screen: np.ndarray) -> bool:
    """截图是否为确认退出 overlay。"""
    return PixelChecker.check_signature(screen, SIG_CONFIRM_EXIT).matched


def get_overlay_signature(overlay: DecisiveOverlay) -> PixelSignature:
    """按类型获取对应的像素签名。"""
    return _SIG_BY_TYPE[overlay]
