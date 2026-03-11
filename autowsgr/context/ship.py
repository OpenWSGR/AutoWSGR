"""舰船运行时状态模型。"""

from __future__ import annotations

import time
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

    repair_end_time: float = 0.0
    """修理完成的时间戳 (``time.time()``)。0 表示未在修理。"""

    repairing: bool = False
    """是否由上层标记为修理中 (手动设置/清除, 决战只读)。"""

    # ── 计算属性 ──

    @property
    def health_ratio(self) -> float:
        """当前耐久比例 (0.0-1.0)；*max_health* 未知时返回 1.0。"""
        if self.max_health <= 0:
            return 1.0
        return self.health / self.max_health

    @property
    def is_repairing(self) -> bool:
        """舰船是否正在修理中。"""
        return self.repairing or time.time() < self.repair_end_time

    @property
    def available(self) -> bool:
        """舰船是否可用 (非大破 且 非修理中)。"""
        if self.damage_state == ShipDamageState.SEVERE:
            return False
        return not self.is_repairing

    def set_repair(self, duration_seconds: int) -> None:
        """标记舰船进入修理状态。

        Parameters
        ----------
        duration_seconds:
            修理时长 (秒)。0 表示快修 (立即完成)。
        """
        self.repair_end_time = time.time() + duration_seconds
        self.damage_state = ShipDamageState.NORMAL

    def needs_repair(self, mode: RepairMode) -> bool:
        """根据修理策略判断是否需要入浴。"""
        if self.is_repairing:
            return False
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
