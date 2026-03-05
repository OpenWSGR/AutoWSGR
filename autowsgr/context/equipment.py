"""装备模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Equipment:
    """舰船装备槽中的一件装备。

    自动化框架中主要通过名称匹配来管理装备；
    详细属性（火力、命中等）通常无法从游戏画面直接读取，按需扩展。
    """

    name: str = ''
    """装备名称。"""
    locked: bool = False
    """是否锁定（锁定装备不会被误拆解）。"""
