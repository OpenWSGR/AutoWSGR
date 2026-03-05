"""舰队模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from autowsgr.types import RepairMode, ShipDamageState


if TYPE_CHECKING:
    from .ship import Ship


@dataclass
class Fleet:
    """一支舰队（最多 6 艘舰船）。

    游戏共 4 支舰队 (fleet_id 1–4)。
    第 3 舰队需通关 1-3，第 4 舰队需通关 2-3 后解锁。
    """

    fleet_id: int = 1
    """舰队编号 (1–4)。"""
    ships: list[Ship] = field(default_factory=list)
    """舰队成员（索引 0 为旗舰）。"""

    # ── 计算属性 ──

    @property
    def size(self) -> int:
        """当前舰队人数。"""
        return len(self.ships)

    @property
    def damage_states(self) -> list[ShipDamageState]:
        """各位置的破损状态列表。"""
        return [s.damage_state for s in self.ships]

    @property
    def has_severely_damaged(self) -> bool:
        """舰队中是否存在大破舰船。"""
        return any(s.damage_state == ShipDamageState.SEVERE for s in self.ships)

    def needs_repair(self, mode: RepairMode) -> bool:
        """舰队中是否有任何舰船需要修理。"""
        return any(s.needs_repair(mode) for s in self.ships)
