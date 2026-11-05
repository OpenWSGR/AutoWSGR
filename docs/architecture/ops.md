# 操作层 (Ops)

> 返回 [架构概述](README.md)

本文档描述 AutoWSGR 的游戏操作编排层——将 [战斗引擎](combat-engine.md)、[UI 导航](ui.md) 和 [上下文](context-and-config.md) 组合为完整的游戏操作流程。

---

## 设计模式

### Runner 模式

所有战斗类操作遵循统一的 Runner 模式：

```python
runner = SomeFightRunner(ctx, plan_or_config)
result = runner.run()         # → CombatResult (单次)
results = runner.run_for_times(n)  # → list[CombatResult] (多次)
```

Runner 内部负责：页面导航 → 出征准备 → 调用 `CombatEngine.fight()` → 上下文同步。

### 非战斗操作

非战斗操作是独立的模块级函数：

```python
from autowsgr.ops import repair_in_bath, collect_expedition, build_ship
```

---

## 战斗 Runner 一览

### NormalFightRunner — 常规战

**文件**: `autowsgr/ops/normal_fight.py`

```python
NormalFightRunner(ctx, plan: CombatPlan, fleet_id: int, fleet: list[str] | None)
    .run() -> CombatResult
    .run_for_times(times, gap=0) -> list[CombatResult]
```

执行流程：

```
goto_page(MAP)
  → 选择章节/地图
  → BattlePreparationPage
    ├─ 换船 (如果 fleet 指定)
    ├─ 补给
    ├─ 检测血量 → ship_stats
    └─ 点击出征
  → CombatEngine.fight(plan, ship_stats)
  → sync_after_combat()
  → 处理船坞满 (dock_full_destroy)
```

### CampaignRunner — 战役

**文件**: `autowsgr/ops/campaign.py`

```python
CampaignRunner(ctx, campaign_name='困难航母', times=3, formation, night, repair_mode)
    .run() -> list[CombatResult]
```

- 支持 "简单/困难" + "驱逐/巡洋/战列/航母/潜艇" 组合
- 内部自带循环，一次 `run()` 执行 N 场
- `CombatMode = BATTLE`，无多节点逻辑

### ExerciseRunner — 演习

**文件**: `autowsgr/ops/exercise.py`

```python
ExerciseRunner(ctx, fleet_id: int)
    .run() -> list[CombatResult]
```

- 遍历 5 个对手，挑战可用的对手
- 每场使用 `CombatMode = EXERCISE`
- 返回所有场次结果列表

### EventFightRunner — 活动战

**文件**: `autowsgr/ops/event_fight.py`

```python
EventFightRunner(ctx, plan_yaml: str, times: int)
    .run() -> list[CombatResult]

# 快捷函数
run_event_fight(ctx, event_name, times, ...)
run_event_fight_from_yaml(ctx, yaml_path)
```

- 活动地图使用 `CombatMode = EVENT`
- 结束页为 `EVENT_MAP_PAGE`
- 需要指定 `event_name` 以加载对应节点数据

### DecisiveController — 决战

**文件**: `autowsgr/ops/decisive/`

```python
DecisiveController(ctx, config: DecisiveConfig)
    .run() -> DecisiveResult
    .run_for_times(times) -> list[DecisiveResult]
```

决战系统较为复杂，单独组织在 `ops/decisive/` 子包中：

```
ops/decisive/
├── __init__.py         # DecisiveController 导出
├── base.py             # DecisiveBase 基类 (配置合并/状态/逻辑)
├── controller.py       # DecisiveController (三章推进循环)
├── logic.py            # DecisiveLogic (选船/阵容/技能策略)
└── state.py            # DecisiveState (章节/舰队/维修状态)
```

三章推进流程：

```
Level 1 → 出击 → 战斗 → 结算
    ↓
Level 2 → 出击 → 战斗 → 结算
    ↓
Level 3 → 出击 → 战斗 → 结算 (Boss)
    ↓
DecisiveResult
```

配置合并：`ctx.config.decisive_battle`（YAML）与传入的 `config` 参数合并，后者优先。

---

## 非战斗操作

### 启动与游戏管理

**文件**: `autowsgr/ops/startup.py`

| 函数                               | 说明                              |
|------------------------------------|-----------------------------------|
| `is_game_running(ctrl, package)`   | 检查游戏进程是否运行                |
| `is_on_main_page(ctrl)`           | 截图检测是否在主页面                |
| `wait_for_game_ui(ctrl, timeout)` | 轮询等待游戏 UI 就绪               |
| `start_game(ctrl, app, package)`  | 启动游戏并等待                     |
| `go_main_page(ctrl)`              | 导航到主页面                       |
| `restart_game(ctrl, app)`         | 完整重启周期 (停止→启动→等待)       |
| `ensure_game_ready(ctx, app)`     | 确保游戏就绪 (启动+检查+到主页面)   |

### 页面导航

**文件**: `autowsgr/ops/navigate.py`

| 函数                                      | 说明                              |
|-------------------------------------------|-----------------------------------|
| `goto_page(ctx, target: PageName)`        | BFS 寻路 + 逐边执行动作            |
| `identify_current_page(ctx)`              | 截图 → 遍历页面注册表              |

`goto_page` 内部调用 [ui/navigation.py](ui.md) 的 `find_path()`，然后依次执行每条边的动作函数。

### 修理

**文件**: `autowsgr/ops/repair.py`

```python
repair_in_bath(ctx, fleet_id, mode: RepairMode, strategy)
```

导航到浴室 → 选择舰船 → 批量修理。支持快修 (`use_quick_repair`) 和普通修理。

### 远征

**文件**: `autowsgr/ops/expedition.py`

```python
collect_expedition(ctx)  # 收取所有已完成的远征
```

### 建造

**文件**: `autowsgr/ops/build.py`

```python
build_ship(ctx, recipe)        # 建造舰船
collect_built_ships(ctx)       # 收取已完成的建造
```

### 食堂

**文件**: `autowsgr/ops/cook.py`

```python
cook(ctx, ...)                 # 食堂烹饪
```

### 解装

**文件**: `autowsgr/ops/destroy.py`

```python
destroy_ships(ctx, ...)        # 解装舰船 (拆解全部/拆解舰种/保留舰种范围)
```

### 补给

**文件**: `autowsgr/ops/supply.py`

```python
supply_fleet(ctx, fleet_id)    # 补给指定舰队
```

### 奖励领取

**文件**: `autowsgr/ops/mission.py`

```python
collect_rewards(ctx)           # 领取任务/日常奖励
```

---

## 战斗上下文同步

每次战斗前后，Runner 负责同步 `GameContext`：

### 战前 (`sync_before_combat`)

- 从出征准备页识别: 出击舰船列表、等级、血量状态
- 更新每日计数器: 掉落舰船数、掉落胖次数
- 更新舰队编成: `ctx.fleet(fleet_id).ships = [...]`
- 同步到舰船注册表: `ctx.ship_registry`

### 战后 (`sync_after_combat`)

- 更新舰队战后血量: `ship.damage_state`
- 统计掉落: `ctx.dropped_ship_count += ...`

---

## YAML 计划加载

**文件**: `autowsgr/infra/file_utils.py` — `resolve_plan_path()`

作战计划文件的 4 级优先级搜索：

```
1. 直接路径                    → /home/user/my_plan.yaml
2. 补全 .yaml 扩展名            → /home/user/my_plan.yaml
3. data/plan/ 目录下搜索        → data/plan/normal_fight/8-5.yaml
4. data/plan/ 目录下补全 .yaml  → data/plan/normal_fight/8-5.yaml
```

内置计划文件在 `data/plan/` 中：

```
data/plan/
├── normal_fight/     # 常规战计划
│   ├── 1-1.yaml
│   ├── 8-5.yaml
│   └── ...
└── event/            # 活动战计划
    └── ...
```

---

## 公共 API 导出

**文件**: `autowsgr/ops/__init__.py`

```python
from autowsgr.ops import (
    NormalFightRunner,
    CampaignRunner,
    ExerciseRunner,
    EventFightRunner,
    DecisiveController,
    goto_page,
    ensure_game_ready,
    restart_game,
    repair_in_bath,
    collect_expedition,
    build_ship,
    collect_rewards,
    destroy_ships,
    ...
)
```

---

## 与其他模块的关系

- **下游**: [combat-engine](combat-engine.md) 提供 `CombatEngine.fight()`
- **下游**: [ui](ui.md) 提供页面导航和页面控制器
- **下游**: [emulator](emulator.md) 提供设备操作
- **数据**: [context-and-config](context-and-config.md) 的 `GameContext` 提供状态同步
- **上游**: [scheduler-and-server](scheduler-and-server.md) 调用 Runner 执行任务
