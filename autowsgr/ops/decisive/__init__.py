"""决战过程控制器包 (Decisive Battle Controller)。

本包是 **决战** 玩法的完整过程控制器，衔接在
:class:`~autowsgr.ui.decisive_battle_page.DecisiveBattlePage`
（决战总览页 UI）与 :mod:`~autowsgr.combat.engine`（战斗引擎）之间，
负责管理决战三小关 × 多节点的推进流程、弹窗 overlay 处理、
战备舰队选择以及单次战斗调度。

决战页面结构
============

决战共有 3 层页面/状态 + 多种弹窗 overlay::

    ┌──────────────────────────────────────────────────────────────────┐
    │  1. 决战总览页 (DecisiveBattlePage)                             │
    │     ↓ 点击「出征」                                               │
    │  2. 决战地图页 (DecisiveMapController)  ← 地图页 UI 操作         │
    │     ├─ overlay: 战备舰队获取           ← 选择购买舰船/技能        │
    │     ├─ overlay: 确认退出 (撤退/暂离)   ← 撤退或暂离当前章节      │
    │     └─ overlay: 选择前进点             ← 多路径分支选择           │
    │  3. 出征准备页 (BattlePreparationPage)                          │
    │     ↓ 开始出征                                                   │
    │  4. 战斗引擎 (CombatEngine)                                     │
    └──────────────────────────────────────────────────────────────────┘

包结构 (继承体系)
=================

::

    decisive/
    ├── __init__.py     ← 本文件 (统一导出)
    ├── base.py         ← DecisiveBase (成员声明 & 初始化)
    ├── config.py       ← MapData (地图静态数据)
    ├── state.py        ← DecisiveState (运行时状态)
    ├── logic.py        ← DecisiveLogic (纯决策)
    ├── chapter.py      ← DecisiveChapterOps(DecisiveBase) (章节管理)
    ├── handlers.py     ← DecisivePhaseHandlers(DecisiveBase) (阶段处理器)
    └── controller.py   ← DecisiveController(DecisivePhaseHandlers, DecisiveChapterOps)

    DecisiveBase
    ├── DecisiveChapterOps(DecisiveBase)
    ├── DecisivePhaseHandlers(DecisiveBase)
    └── DecisiveController(DecisivePhaseHandlers, DecisiveChapterOps)

UI 层 (autowsgr.ui.decisive)::

    ui/decisive/
    ├── overlay.py          ← 签名/坐标常量/检测函数/DecisiveOverlay
    ├── map_controller.py   ← DecisiveMapController (地图页 UI 操作)
    └── fleet_ocr.py        ← 舰队 OCR 识别函数

使用示例
========

::

    from autowsgr.ops.decisive import DecisiveController
    from autowsgr.infra import DecisiveConfig

    config = DecisiveConfig(
        chapter=6,
        level1=["U-1206", "U-96", "射水鱼", "大青花鱼", "鹦鹉螺", "鲃鱼"],
        level2=["甘比尔湾", "平海"],
        flagship_priority=["U-1206"],
    )
    controller = DecisiveController(ctx, config)

    # 打一轮
    result = controller.run()

    # 打多轮 (含自动重置)
    results = controller.run_for_times(3)
"""

from autowsgr.types import DecisivePhase, FleetSelection
from autowsgr.ui.decisive import (
    DecisiveMapController,
)

from .base import DecisiveBase
from .config import MapData
from .controller import DecisiveController, DecisiveResult
from .logic import DecisiveLogic
from .state import DecisiveState


__all__ = [
    # 基类
    'DecisiveBase',
    # 配置 & 地图数据
    'MapData',
    # 状态
    'DecisivePhase',
    'DecisiveState',
    # 逻辑
    'FleetSelection',
    'DecisiveLogic',
    # 地图控制器
    'DecisiveMapController',
    # 控制器
    'DecisiveResult',
    'DecisiveController',
]
