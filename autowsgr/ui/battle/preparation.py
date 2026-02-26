"""出征准备页面 UI 控制器。

最终控制器类 :class:`BattlePreparationPage` 通过菱形继承聚合所有 Mixin:

继承结构::

    BaseBattlePreparation
    ├── DetectionMixin      (血量 / 等级识别)
    ├── SupplyMixin         (补给 / 支援)
    ├── RepairMixin         (修理, 依赖 DetectionMixin)
    └── FleetChangeMixin    (换船, 依赖 DetectionMixin)
            ↓
    BattlePreparationPage   (最终控制器)

数据常量见 :mod:`autowsgr.ui.battle.constants`。
"""

from __future__ import annotations

from autowsgr.ui.battle.base import (
    CLICK_PANEL,
    PAGE_SIGNATURE,
    PANEL_PROBE,
    BaseBattlePreparation,
    Panel,
    RepairStrategy,
)
from autowsgr.ui.battle.detection import DetectionMixin, FleetInfo
from autowsgr.ui.battle.fleet_change import FleetChangeMixin
from autowsgr.ui.battle.repair import RepairMixin
from autowsgr.ui.battle.supply import SupplyMixin


__all__ = [
    'CLICK_PANEL',
    'PAGE_SIGNATURE',
    'PANEL_PROBE',
    'BattlePreparationPage',
    'FleetInfo',
    'Panel',
    'RepairStrategy',
]


class BattlePreparationPage(
    DetectionMixin,
    SupplyMixin,
    RepairMixin,
    FleetChangeMixin,
    BaseBattlePreparation,
):
    """出征准备页面控制器。

    聚合所有 Mixin 能力:

    - **检测** (:class:`DetectionMixin`):
      ``detect_ship_damage``, ``detect_fleet_info``
    - **补给/支援** (:class:`SupplyMixin`):
      ``supply``, ``apply_supply``, ``toggle_battle_support``, ``is_support_enabled``
    - **修理** (:class:`RepairMixin`):
      ``repair_slots``, ``apply_repair``
    - **换船** (:class:`FleetChangeMixin`):
      ``change_fleet``
    - **基础** (:class:`BaseBattlePreparation`):
      ``go_back``, ``start_battle``, ``select_fleet``, ``select_panel`` 等
    """

    # FleetInfo 挂在类上方便外部引用: BattlePreparationPage.FleetInfo
    FleetInfo = FleetInfo
