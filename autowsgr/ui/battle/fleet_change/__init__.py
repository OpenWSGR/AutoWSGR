"""舰队编成更换子包。

统一 "扫描 -> 定点更换 -> 调整次序" 流程,
常规出征与决战共用, 通过 ``_use_search`` 控制是否使用搜索框。

内部模块:

- ``_detect.py`` -- 准备页舰队 OCR 检测
- ``_rules.py`` -- 舰队规则匹配与校验
- ``_planning.py`` -- 目标分配与槽位规划
- ``_alignment.py`` -- 舰队调整与船池页面操作
- ``_change.py`` -- 换船主流程编排
"""

from autowsgr.ui.battle.fleet_change._change import FleetChangeMixin


__all__ = ['FleetChangeMixin']
