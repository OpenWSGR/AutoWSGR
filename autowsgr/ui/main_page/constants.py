"""主页面常量 — 枚举类封装。

所有坐标均为相对值 ``(rx, ry)``，基于 960×540 分辨率。
"""

from __future__ import annotations

import enum

from autowsgr.types import PageName
from autowsgr.vision import Color, MatchStrategy, PixelRule, PixelSignature


# ═══════════════════════════════════════════════════════════════════════════════
# 导航目标
# ═══════════════════════════════════════════════════════════════════════════════


class Target(enum.Enum):
    """主页面可导航的目标。"""

    SORTIE = '出征'
    TASK = '任务'
    SIDEBAR = '侧边栏'
    HOME = '主页'
    EVENT = '活动'

    @property
    def page_name(self) -> str:
        """对应的目标页面名称。"""
        return _TARGET_PAGES[self]


_TARGET_PAGES: dict[Target, str] = {
    Target.SORTIE: PageName.MAP,
    Target.TASK: PageName.MISSION,
    Target.SIDEBAR: PageName.SIDEBAR,
    Target.HOME: PageName.BACKYARD,
    Target.EVENT: PageName.EVENT_MAP,
}


# ═══════════════════════════════════════════════════════════════════════════════
# 浮层类型
# ═══════════════════════════════════════════════════════════════════════════════


class OverlayKind(enum.Enum):
    """主页面可出现的浮层类型。"""

    NEWS = '新闻公告'
    SIGN = '每日签到'
    BOOKING = '活动预约'


# ═══════════════════════════════════════════════════════════════════════════════
# 坐标枚举
# ═══════════════════════════════════════════════════════════════════════════════


class NavCoord(enum.Enum):
    """导航目标点击坐标。"""

    SORTIE = (0.9375, 0.8981)
    TASK = (0.6823, 0.9037)
    SIDEBAR = (0.0490, 0.8981)
    HOME = (0.0531, 0.1519)
    EVENT = (0.8844, 0.4833)

    @property
    def xy(self) -> tuple[float, float]:
        return self.value


class ProbePoint(enum.Enum):
    """状态探测点坐标。"""

    EXPEDITION_READY = (0.9719, 0.8407)
    """远征完成探测点 — (933, 454)。"""

    TASK_READY = (0.7229, 0.8463)
    """任务可领取探测点 — (694, 457)。"""

    @property
    def xy(self) -> tuple[float, float]:
        return self.value


class DismissCoord(enum.Enum):
    """浮层 / 弹窗消除点击坐标。"""

    NEWS_NOT_SHOW = (0.0729, 0.8981)
    """新闻「不再显示」复选框 — (70, 485)。"""

    NEWS_CLOSE = (0.0313, 0.0556)
    """新闻关闭按钮 — (30, 30)。"""

    SIGN_CONFIRM = (0.4938, 0.6611)
    """签到领取/关闭按钮 — (474, 357)。"""

    BOOKING = (0.618, 0.564)
    """预约页面关闭坐标。"""

    @property
    def xy(self) -> tuple[float, float]:
        return self.value


# ═══════════════════════════════════════════════════════════════════════════════
# 颜色 & 容差
# ═══════════════════════════════════════════════════════════════════════════════


class ThemeColor(enum.Enum):
    """主页面关键颜色 ``((R, G, B), tolerance)``。"""

    NOTIFICATION_RED = ((255, 89, 45), 40.0)
    """通知红点。"""

    EVENT_SIDEBAR_BG = ((121, 130, 135), 50.0)
    """侧边栏无活动时背景灰色。"""

    @property
    def color(self) -> Color:
        return Color.of(*self.value[0])

    @property
    def tolerance(self) -> float:
        return self.value[1]


# ═══════════════════════════════════════════════════════════════════════════════
# 像素签名
# ═══════════════════════════════════════════════════════════════════════════════


class Sig(enum.Enum):
    """主页面像素签名集合。

    通过 ``.ps`` 属性访问 :class:`PixelSignature` 实例。
    """

    PAGE = 'page'
    """主页面基础签名 — 检测资源栏 + 角落特征。"""

    NEWS = 'news'
    """新闻公告浮层签名。"""

    NEWS_NOT_SHOW = 'news_not_show'
    """「不再显示」复选框已勾选态签名 (蓝色)。"""

    SIGN = 'sign'
    """每日签到浮层签名。"""

    BOOKING = 'booking'
    """预约页面签名。"""

    @property
    def ps(self) -> PixelSignature:
        """对应的 :class:`PixelSignature` 实例。"""
        return _SIGNATURES[self]


_SIGNATURES: dict[Sig, PixelSignature] = {
    Sig.PAGE: PixelSignature(
        name=PageName.MAIN,
        strategy=MatchStrategy.ALL,
        rules=[
            PixelRule.of(0.6453, 0.9375, (52, 115, 168), tolerance=30.0),
            PixelRule.of(0.8126, 0.8681, (213, 206, 180), tolerance=30.0),
            PixelRule.of(0.9696, 0.8903, (121, 130, 135), tolerance=30.0),
            PixelRule.of(0.0570, 0.8847, (251, 252, 255), tolerance=30.0),
        ],
    ),
    Sig.NEWS: PixelSignature(
        name='news_overlay',
        strategy=MatchStrategy.ALL,
        rules=[
            PixelRule.of(0.1437, 0.9065, (254, 255, 255), tolerance=40.0),
            PixelRule.of(0.9411, 0.0685, (253, 254, 255), tolerance=40.0),
            PixelRule.of(0.9016, 0.0704, (254, 255, 255), tolerance=40.0),
            PixelRule.of(0.8599, 0.0685, (254, 255, 255), tolerance=40.0),
            PixelRule.of(0.2010, 0.9046, (254, 255, 255), tolerance=40.0),
            PixelRule.of(0.8849, 0.0574, (247, 249, 248), tolerance=40.0),
        ],
    ),
    Sig.NEWS_NOT_SHOW: PixelSignature(
        name='news_not_show',
        strategy=MatchStrategy.ALL,
        rules=[
            PixelRule.of(0.0714, 0.9065, (49, 130, 211), tolerance=40.0),
            PixelRule.of(0.0620, 0.9130, (52, 130, 205), tolerance=40.0),
        ],
    ),
    Sig.SIGN: PixelSignature(
        name='sign_overlay',
        strategy=MatchStrategy.ALL,
        rules=[
            PixelRule.of(0.8766, 0.3046, (216, 218, 215), tolerance=40.0),
            PixelRule.of(0.1490, 0.3000, (255, 255, 255), tolerance=40.0),
            PixelRule.of(0.1786, 0.4019, (250, 255, 255), tolerance=40.0),
            PixelRule.of(0.4432, 0.4019, (254, 255, 255), tolerance=40.0),
        ],
    ),
    Sig.BOOKING: PixelSignature(
        name='booking_overlay',
        strategy=MatchStrategy.ALL,
        rules=[
            PixelRule.of(0.3375, 0.3861, (225, 225, 225), tolerance=30.0),
            PixelRule.of(0.6078, 0.3625, (225, 225, 225), tolerance=30.0),
            PixelRule.of(0.3344, 0.5694, (33, 122, 216), tolerance=30.0),
            PixelRule.of(0.5789, 0.5681, (153, 37, 37), tolerance=30.0),
            PixelRule.of(0.4875, 0.5736, (225, 225, 225), tolerance=30.0),
        ],
    ),
}
