"""舰队编成更换子包。

统一 "扫描 -> 定点更换 -> 调整次序" 流程,
常规出征与决战共用, 通过 ``_use_search`` 控制是否使用搜索框。

内部模块:

- ``_detect.py`` -- 准备页舰队 OCR 检测
- ``_planning.py`` -- 目标规划与规则校验
- ``_change.py`` -- 更换算法 Mixin
"""

from autowsgr.ui.battle.fleet_change._change import FleetChangeMixin


__all__ = ['FleetChangeMixin']
