"""主页面识别模板 — 主页基础页面 + 登录/操作浮层。

主页面 (main page) 上可能叠加的浮层: 新闻公告 / 每日签到 / 活动预约 / 提督信息。
浮层打开时仍识别为主页面 (``MainPage.is_current_page`` 对基础页与各浮层做 OR 组合)。
"""

from __future__ import annotations

from autowsgr.image_resources._lazy import LazyTemplate


class MainPage:
    """主页面模板 (基础页面 + 浮层)。

    .. note::

        ``MAIN`` 为 540p 基准 (classic ``main_page``); 浮层模板中 NEWS / SIGN /
        USER_INFO 采集自 1280x720 实机 (``source_resolution=(1280, 720)``), BOOKING
        迁移自 classic 540p。``load_template`` 据此自动缩放到实际截图分辨率。
    """

    # ── 基础页面 ──
    MAIN = LazyTemplate('main_page/main_page_540p.png', 'page_main')
    """主页面基础特征 (classic ``main_page``)。"""

    # ── 浮层 ──
    NEWS = LazyTemplate(
        'main_page/news_720p.png',
        'overlay_news',
        source_resolution=(1280, 720),
    )
    """新闻公告浮层 (「今日不再显示」文字, 162x45)。"""

    SIGN = LazyTemplate(
        'main_page/sign_720p.png',
        'overlay_sign',
        source_resolution=(1280, 720),
    )
    """每日签到浮层 (「每日签到 >>」标题, 293x48)。"""

    BOOKING = LazyTemplate('main_page/booking_540p.png', 'overlay_booking')
    """活动预约浮层 (classic 「是否跳转前往预定页面」, 199x29)。"""

    USER_INFO = LazyTemplate(
        'main_page/user_info_720p.png',
        'overlay_user_info',
        source_resolution=(1280, 720),
    )
    """提督信息浮层 (全屏个人资料「远征大成功」标签, 249x63)。"""
