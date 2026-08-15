"""通用页面识别模板 — 无专属浮层体系的独立页面。

迁移自 ``ops.py`` 原 ``Page`` 类。540p 基准, ``TM_CCOEFF_NORMED`` 置信度 >= 0.85,
与其他页面区分度高 (已做全截图交叉验证)。
"""

from __future__ import annotations

from autowsgr.image_resources._lazy import LazyTemplate


class CommonPage:
    """通用页面识别模板 (无专属浮层)。"""

    BACKYARD = LazyTemplate('page/backyard_540p.png', 'page_backyard')
    """后院页面特征 (classic ``backyard_page``, 482x387 大区域模板, 区分度极高, 置信度 0.995)。"""

    CANTEEN = LazyTemplate('page/canteen_540p.png', 'page_canteen')
    """食堂页面特征 (classic ``canteen_page``, 86x33 局部特征, 置信度 0.96)。"""

    BATTLE_PREP = LazyTemplate('page/fight_prepare_540p.png', 'page_battle_prep')
    """出征准备页面特征 (classic ``fight_prepare_page``, 183x48 局部特征, 置信度 0.98)。"""

    SIDEBAR = LazyTemplate('page/sidebar_540p.png', 'page_sidebar')
    """侧边栏页面特征 (classic ``options_page`` 大区域模板)。

    .. note::

        正样本置信度约 0.86 (大模板含背景, 易随主题波动), 故识别阈值用 0.8;
        其他页最高仅 0.32, 区分度充足。
    """
