"""游戏资源状态模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Resources:
    """游戏资源。

    包含四项基础资源（燃料、弹药、钢材、铝材）和常用物品数量。
    数值由画面 OCR 识别后写入。
    """

    fuel: int = 0
    """燃料。"""
    ammo: int = 0
    """弹药。"""
    steel: int = 0
    """钢材。"""
    aluminum: int = 0
    """铝材。"""

    diamond: int = 0
    """钻石。"""
    fast_repair: int = 0
    """快速修复材料（桶）。"""
    fast_build: int = 0
    """快速建造材料。"""
    ship_blueprint: int = 0
    """舰船蓝图。"""
    equipment_blueprint: int = 0
    """装备蓝图。"""

    @property
    def basic(self) -> tuple[int, int, int, int]:
        """基础四资源 (燃料, 弹药, 钢材, 铝材)。"""
        return self.fuel, self.ammo, self.steel, self.aluminum
