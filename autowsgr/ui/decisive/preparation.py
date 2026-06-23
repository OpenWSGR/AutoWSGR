"""决战出征准备页 UI 控制器（决战专用版）。

继承自 :class:`~autowsgr.ui.battle.preparation.BattlePreparationPage`，
仅通过 ``_use_search = False`` 切换为 "不使用搜索框" 的换船模式。

与普通换船的差异
---------------
- 普通换船: 点击搜索框 -> 输入舰船名 -> 等待筛选结果 -> 点击第一项
- 决战换船: 直接 OCR 识别选船列表 -> 按编辑距离模糊匹配 -> 点击目标坐标

这是因为决战选船流程没有搜索框（界面为直接列表展示），
且候选集合相对固定（由配置 level1/level2 决定）。

换船算法 (扫描 -> 定点更换 -> 调整次序) 由父类
:class:`~autowsgr.ui.battle.fleet_change.FleetChangeMixin` 统一提供。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.ui.battle.preparation import BattlePreparationPage


if TYPE_CHECKING:
    from autowsgr.context import GameContext
    from autowsgr.infra import DecisiveConfig
    from autowsgr.vision import OCREngine


class DecisiveBattlePreparationPage(BattlePreparationPage):
    """决战出征准备页面控制器（无搜索框换船版）。

    与 :class:`BattlePreparationPage` 唯一的区别是
    ``_use_search = False``，使选船页面跳过搜索框，直接
    通过 DLL 行定位 + OCR 识别舰船列表并点击目标。

    Parameters
    ----------
    ctx:
        游戏上下文。
    config:
        决战配置。
    ocr:
        OCR 引擎（必须提供，换船时依赖 OCR）。
    """

    _use_search: bool = False

    def __init__(
        self,
        ctx: GameContext,
        config: DecisiveConfig,
        ocr: OCREngine | None = None,
    ) -> None:
        super().__init__(ctx, ocr)
        _ocr = ocr if ocr is not None else ctx.ocr
        if _ocr is None:
            raise ValueError('DecisivePreparation requires an OCR engine')
        self._ocr: OCREngine = _ocr
        self._config = config
