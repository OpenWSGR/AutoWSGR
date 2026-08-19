"""决战相关识别模板 — 入口状态 + 地图页 + 浮层。

迁移并扩展自 ``ops.py`` 原 ``Decisive`` 类 (入口模板), 新增地图页与三种浮层
(战备舰队获取 / 确认退出 / 选择前进点), 替代 ``decisive/overlay.py`` 的像素签名。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.image_resources._lazy import LazyTemplate


if TYPE_CHECKING:
    from autowsgr.vision import ImageTemplate


class Decisive:
    """决战识别模板 (入口 + 地图页 + 浮层)。

    .. note::

        入口 / 地图页为 540p 基准; 三种浮层采集自 1280x720 实机
        (``source_resolution=(1280, 720)``)。
    """

    # ── 入口 (总览页) ──
    USE_LAST_FLEET = LazyTemplate('decisive/use_last_fleet_540p.png', 'decisive_use_last_fleet')
    """"使用上次舰队" 确认按钮 — 进入已有进度的章节时弹出。"""

    ENTRY_CANT_FIGHT = LazyTemplate(
        'decisive/entry_cant_fight_540p.png',
        'decisive_entry_cant_fight',
    )
    """入口状态: 无法出击。"""

    ENTRY_CHALLENGING = LazyTemplate(
        'decisive/entry_challenging_540p.png',
        'decisive_entry_challenging',
    )
    """入口状态: 挑战中 (当前章节正在进行)。"""

    ENTRY_REFRESHED = LazyTemplate(
        'decisive/entry_refreshed_540p.png',
        'decisive_entry_refreshed',
    )
    """入口状态: 已刷新 (有存档进度可继续)。"""

    ENTRY_REFRESH = LazyTemplate(
        'decisive/entry_refresh_540p.png',
        'decisive_entry_refresh',
    )
    """入口状态: 可重置 (显示"重置关卡")。"""

    # ── 地图页 ──
    MAP_PAGE = LazyTemplate('decisive/decisive_map_540p.png', 'decisive_map_page')
    """决战地图页特征: 右下角「编队+出征」按钮组 (classic ``decisive_battle_image/9``, 120x44)。

    .. warning::
        地图页上没有「剧情/奖励/说明」按钮组 — 那是入口/总览页元素，
        曾被误用作本模板导致进图后永远识别失败 (Ex-6 NavError 超时)。
    """

    # ── 浮层 ──
    FLEET_ACQUISITION = LazyTemplate(
        'decisive/fleet_acq_720p.png',
        'decisive_fleet_acq',
        source_resolution=(1280, 720),
    )
    """战备舰队获取浮层 (「刷新/关闭」按钮, 505x62)。"""

    CONFIRM_EXIT = LazyTemplate(
        'decisive/confirm_exit_720p.png',
        'decisive_confirm_exit',
        source_resolution=(1280, 720),
    )
    """确认退出浮层 (整浮层, 526x273)。"""

    ADVANCE_CHOICE = LazyTemplate(
        'decisive/advance_choice_720p.png',
        'decisive_advance_choice',
        source_resolution=(1280, 720),
    )
    """选择前进点浮层 (选项含涂字, 匹配率需实机验证, 281x191)。"""

    @classmethod
    def entry_status_templates(cls) -> list[ImageTemplate]:
        """按 :class:`~autowsgr.types.DecisiveEntryStatus` 枚举顺序返回入口状态模板列表。

        索引 0-3 分别对应 CANT_FIGHT / CHALLENGING / REFRESHED / REFRESH。
        """
        return [
            cls.ENTRY_CANT_FIGHT,
            cls.ENTRY_CHALLENGING,
            cls.ENTRY_REFRESHED,
            cls.ENTRY_REFRESH,
        ]
