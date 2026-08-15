"""浴室识别模板 — 浴室页面 + 选择修理浮层。

「选择修理」浮层打开时仍识别为浴室页面 (``BathPage.is_current_page`` 对基础页与
浮层做 OR 组合)。
"""

from __future__ import annotations

from autowsgr.image_resources._lazy import LazyTemplate


class Bath:
    """浴室识别模板 (页面 + 浮层)。

    .. note::

        ``BATH`` 为 540p 基准 (classic ``bath_page``); ``CHOOSE_REPAIR`` 采集自
        1280x720 实机 (``source_resolution=(1280, 720)``)。
    """

    BATH = LazyTemplate('bath/bath_540p.png', 'page_bath')
    """浴室页面特征 (classic ``bath_page``, 127x41 局部特征, 置信度 0.91)。"""

    CHOOSE_REPAIR = LazyTemplate(
        'bath/choose_repair_720p.png',
        'overlay_bath_choose_repair',
        source_resolution=(1280, 720),
    )
    """「选择受损舰船」浮层 (标题栏, 234x54)。"""
