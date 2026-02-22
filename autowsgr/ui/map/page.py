"""地图页面 UI 控制器。

覆盖 **地图选择** 页面的全部界面交互，包括面板切换、章节导航等。

所有面板功能由各 Mixin 提供，主类 :class:`MapPage` 通过多重继承组合。

数据常量和 OCR 解析逻辑见 :mod:`autowsgr.ui.map.data`。
"""

from __future__ import annotations

from autowsgr.emulator import AndroidController
from autowsgr.ui.map.panels import (
    CampaignPanelMixin,
    DecisivePanelMixin,
    ExercisePanelMixin,
    ExpeditionPanelMixin,
    SortiePanelMixin,
)
from autowsgr.vision import OCREngine


class MapPage(
    SortiePanelMixin,
    CampaignPanelMixin,
    DecisivePanelMixin,
    ExercisePanelMixin,
    ExpeditionPanelMixin,
):
    """地图页面控制器。

    继承自所有面板 Mixin，提供完整的地图页面操作能力:

    - **出征** (:class:`SortiePanelMixin`): 章节导航、进入出征准备。
    - **战役** (:class:`CampaignPanelMixin`): 难度选择、进入战役。
    - **决战** (:class:`DecisivePanelMixin`): 进入决战总览。
    - **演习** (:class:`ExercisePanelMixin`): 对手检测、选择、战斗、刷新、阵容识别。
    - **远征** (:class:`ExpeditionPanelMixin`): 远征收取。

    公共查询方法 (页面识别、面板检测等) 和章节导航由
    :class:`~autowsgr.ui.map.base.BaseMapPage` 提供。

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
        super().__init__(ctrl, ocr)
