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

包结构
======

::

    decisive/
    ├── __init__.py           ← 本文件 (统一导出)
    ├── _state.py             ← DecisivePhase, DecisiveState
    ├── _config.py            ← MapData
    ├── _logic.py             ← DecisiveLogic (纯决策)
    └── _controller.py        ← DecisiveResult, DecisiveController (状态机编排)

UI 层 (autowsgr.ui.decisive)::

    ui/decisive/
    ├── overlay.py            ← 签名/坐标常量/检测函数/DecisiveOverlay
    └── map_controller.py     ← DecisiveMapController (地图页 UI 操作)

架构分层
========

::

    DecisiveController (编排器)
    ├── DecisiveLogic          ← 纯逻辑决策 (选船/编队/修理判断/小关结束)
    ├── DecisiveMapController  ← 地图页 UI 操作 (overlay/出征/撤退/修理)
    ├── BattlePreparationPage  ← 出征准备页 UI (编队/修理/出征)
    └── DecisiveBattlePage     ← 决战总览页 UI (章节导航/重置)

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
    controller = DecisiveController(ctrl, config)

    # 打一轮
    result = controller.run()

    # 打多轮 (含自动重置)
    results = controller.run_for_times(3)
"""

from autowsgr.types import FleetSelection
from ._config import MapData
from ._controller import DecisiveController, DecisiveResult
from ._logic import DecisiveLogic
from ._state import DecisivePhase, DecisiveState
from autowsgr.ui.decisive import (
    ADVANCE_CARD_POSITIONS,
    CLICK_ADVANCE_CONFIRM,
    CLICK_BUY_EXP,
    CLICK_FLEET_CLOSE,
    CLICK_FLEET_EDIT,
    CLICK_FLEET_REFRESH,
    CLICK_LEAVE,
    CLICK_RETREAT_BUTTON,
    CLICK_RETREAT_CONFIRM,
    CLICK_SKILL,
    CLICK_SORTIE,
    COST_AREA,
    FLEET_CARD_CLICK_Y,
    FLEET_CARD_X_POSITIONS,
    RESOURCE_AREA,
    SHIP_NAME_X_RANGES,
    SHIP_NAME_Y_RANGE,
    DecisiveMapController,
    DecisiveOverlay,
    detect_decisive_overlay,
    get_overlay_signature,
    is_advance_choice,
    is_confirm_exit,
    is_decisive_map_page,
    is_fleet_acquisition,
)

__all__ = [
    # 配置 & 地图数据
    "DecisiveConfig",
    "MapData",
    # 状态
    "DecisivePhase",
    "DecisiveState",
    # Overlay
    "DecisiveOverlay",
    "detect_decisive_overlay",
    "get_overlay_signature",
    "is_decisive_map_page",
    "is_fleet_acquisition",
    "is_advance_choice",
    "is_confirm_exit",
    # 坐标常量
    "CLICK_RETREAT_BUTTON",
    "CLICK_SORTIE",
    "CLICK_FLEET_EDIT",
    "CLICK_BUY_EXP",
    "CLICK_SKILL",
    "CLICK_FLEET_REFRESH",
    "CLICK_FLEET_CLOSE",
    "FLEET_CARD_X_POSITIONS",
    "FLEET_CARD_CLICK_Y",
    "SHIP_NAME_X_RANGES",
    "SHIP_NAME_Y_RANGE",
    "COST_AREA",
    "RESOURCE_AREA",
    "CLICK_LEAVE",
    "CLICK_RETREAT_CONFIRM",
    "CLICK_ADVANCE_CONFIRM",
    "ADVANCE_CARD_POSITIONS",
    # 逻辑
    "FleetSelection",
    "DecisiveLogic",
    # 地图控制器
    "DecisiveMapController",
    # 控制器
    "DecisiveResult",
    "DecisiveController",
]
