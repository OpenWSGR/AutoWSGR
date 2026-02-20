"""出征准备页面子包。

re-export 公开 API，外部统一通过 ``autowsgr.ui.battle`` 导入。
"""

from autowsgr.ui.battle.preparation import (
    CLICK_PANEL,
    PANEL_PROBE,
    BattlePreparationPage,
    Panel,
    RepairStrategy,
)

__all__ = [
    "CLICK_PANEL",
    "PANEL_PROBE",
    "BattlePreparationPage",
    "Panel",
    "RepairStrategy",
]
