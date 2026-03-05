"""舰船运行时状态模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from autowsgr.types import RepairMode, ShipDamageState, ShipType


if TYPE_CHECKING:
    from .equipment import Equipment


@dataclass
class Ship:
    """单艘舰船的可观测状态。

    字段值来自画面识别（血条、OCR 等），在出击和检查时更新。
    """

    name: str = ''
    """舰船名称。"""
    ship_type: ShipType | None = None
    """舰种。"""
    level: int = 0
    """当前等级。"""

    health: int = 0
    """当前耐久。"""
    max_health: int = 0
    """最大耐久。"""
    damage_state: ShipDamageState = ShipDamageState.NORMAL
    """破损状态（由血条颜色判定）。"""

    locked: bool = False
    """是否锁定。"""
    equipment: list[Equipment] = field(default_factory=list)
    """已装备列表。"""

    # ── 计算属性 ──

    @property
    def health_ratio(self) -> float:
        """当前耐久比例 (0.0–1.0)；*max_health* 未知时返回 1.0。"""
        if self.max_health <= 0:
            return 1.0
        return self.health / self.max_health

    def needs_repair(self, mode: RepairMode) -> bool:
        """根据修理策略判断是否需要入浴。"""
        match mode:
            case RepairMode.moderate_damage:
                return self.damage_state in (
                    ShipDamageState.MODERATE,
                    ShipDamageState.SEVERE,
                )
            case RepairMode.severe_damage:
                return self.damage_state == ShipDamageState.SEVERE
            case _:
                return False
