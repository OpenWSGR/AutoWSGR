# 日常操作使用指南

> 详解 AutoWSGR v2 提供的日常游戏操作函数：导航、远征、建造、食堂、修理、解装、任务奖励等。

---

## 目录

- [1. 统一导入](#1-统一导入)
- [2. 页面导航](#2-页面导航)
- [3. 远征收取](#3-远征收取)
- [4. 任务奖励](#4-任务奖励)
- [5. 建造与收取](#5-建造与收取)
- [6. 食堂做菜](#6-食堂做菜)
- [7. 浴室修理](#7-浴室修理)
- [8. 出征修理](#8-出征修理)
- [9. 解装舰船](#9-解装舰船)
- [10. 组合使用示例](#10-组合使用示例)
- [11. 与 v1 API 对照](#11-与-v1-api-对照)

---

## 1. 统一导入

所有日常操作函数均通过 `autowsgr.ops` 统一导出：

```python
from autowsgr.ops import (
    # 导航
    goto_page,
    identify_current_page,
    # 远征
    collect_expedition,
    # 任务奖励
    collect_rewards,
    # 建造
    BuildRecipe, build_ship, collect_built_ships,
    # 食堂
    cook,
    # 解装
    destroy_ships,
    # 浴室修理
    repair_in_bath,
    # 出征修理
    RepairStrategy, apply_repair,
)
```

所有函数的第一个参数都是 `ctrl: AndroidController`，**无全局状态，无副作用**。

---

## 2. 页面导航

### 识别当前页面

```python
page = identify_current_page(ctrl)
print(f"当前在: {page}")  # 如 "主页面", "地图页面", None (未识别)
```

### 导航到目标页面

```python
# 自动规划最短路径并逐步跳转
goto_page(ctrl, "建造页面")

# 内置浮层处理 (公告、签到等)
goto_page(ctrl, "主页面")  # 自动关闭弹窗后到达主页面
```

### 支持的页面

| 页面名称 | 对应控制器 |
|---------|-----------|
| `"主页面"` | MainPage |
| `"地图页面"` | MapPage |
| `"出征准备页面"` | BattlePreparationPage |
| `"后院页面"` | BackyardPage |
| `"浴室页面"` | BathPage |
| `"食堂页面"` | CanteenPage |
| `"建造页面"` | BuildPage |
| `"强化页面"` | IntensifyPage |
| `"侧边栏页面"` | SidebarPage |
| `"任务页面"` | MissionPage |
| `"好友页面"` | FriendPage |

### 导航树

```
主页面
├── 地图页面 → 出征准备页面 → 浴室页面 (跨级)
├── 任务页面
├── 后院页面 → 浴室页面 / 食堂页面
└── 侧边栏页面 → 建造页面 / 强化页面 / 好友页面
```

---

## 3. 远征收取

```python
collected = collect_expedition(ctrl)
# collected: bool — 是否有远征被收取

if collected:
    print("远征已收取并重新派遣")
```

**流程**:
1. 导航到地图页面
2. 检测远征通知图标
3. 点击收取 → 确认 → 重新派遣
4. 返回

---

## 4. 任务奖励

```python
rewarded = collect_rewards(ctrl)
# rewarded: bool — 是否有奖励被收取
```

**流程**:
1. 导航到任务页面
2. 检测可领取的任务
3. 逐个点击领取
4. 返回

---

## 5. 建造与收取

### 收取已完成的建造

```python
count = collect_built_ships(ctrl)
print(f"收取了 {count} 艘")
```

### 开始新建造

```python
from autowsgr.ops import BuildRecipe

recipe = BuildRecipe(fuel=30, ammo=30, steel=30, bauxite=30)
build_ship(ctrl, recipe)
```

### BuildRecipe 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `fuel` | int | 油 |
| `ammo` | int | 弹 |
| `steel` | int | 钢 |
| `bauxite` | int | 铝 |

---

## 6. 食堂做菜

```python
cook(ctrl, position=1)  # 在第 1 个位置做菜
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `ctrl` | AndroidController | — | 设备控制器 |
| `position` | int | `1` | 做菜位置 (1~3) |

---

## 7. 浴室修理

```python
repair_in_bath(ctrl)
```

**流程**: 导航到浴室页面 → 选择待修舰船 → 开始修理

---

## 8. 出征修理

出征前在出征准备页面执行的修理操作：

```python
from autowsgr.ops import RepairStrategy, apply_repair

# 中破修 — 修理中破及以上的舰船
apply_repair(ctrl, strategy=RepairStrategy.MODERATE)

# 大破修 — 只修理大破的舰船
apply_repair(ctrl, strategy=RepairStrategy.SEVERE)
```

### RepairStrategy 枚举

| 策略 | 说明 |
|------|------|
| `RepairStrategy.MODERATE` | 中破修 (中破+大破) |
| `RepairStrategy.SEVERE` | 大破修 (仅大破) |

> 注意：`apply_repair()` 应在出征准备页面调用。
> 各 Runner 会自动在出征前调用它，通常不需要手动调用。

---

## 9. 解装舰船

```python
destroy_ships(ctrl)
```

当船坞满时自动触发解装流程。支持按舰种过滤（配置方式见 `UserConfig`）。

---

## 10. 组合使用示例

### 示例 1: 简单日常脚本

```python
from autowsgr.emulator.controller import ADBController
from autowsgr.ops import (
    goto_page, collect_expedition, collect_rewards,
    repair_in_bath, run_campaign, CampaignConfig,
)

# 连接
ctrl = ADBController(serial="127.0.0.1:5555")
ctrl.connect()

# 1. 收取远征
collect_expedition(ctrl)

# 2. 收取任务奖励
collect_rewards(ctrl)

# 3. 执行 3 次战役
config = CampaignConfig(map_index=3, difficulty="hard")
results = run_campaign(ctrl, config, image_matcher, times=3)

# 4. 浴室修理
repair_in_bath(ctrl)

# 5. 回到主页面
goto_page(ctrl, "主页面")

ctrl.disconnect()
```

### 示例 2: 战役 + 常规战组合

```python
from autowsgr.ops import (
    run_campaign, CampaignConfig,
    run_normal_fight_from_yaml,
    collect_expedition,
)

# 先打完每日战役
campaign_config = CampaignConfig(
    map_index=4,
    difficulty="hard",
    max_times=3,
)
run_campaign(ctrl, campaign_config, image_matcher)

# 收取可能完成的远征
collect_expedition(ctrl)

# 然后常规战刷图
run_normal_fight_from_yaml(
    ctrl,
    "plans/normal_fight/5-4.yaml",
    image_matcher,
    times=10,
)
```

### 示例 3: 演习 + 远征循环

```python
import time
from autowsgr.ops import (
    run_exercise, ExerciseConfig,
    collect_expedition,
    collect_rewards,
)

# 先演习
exercise_config = ExerciseConfig(
    fleet_id=2,
    exercise_times=4,
    formation=2,
    night=False,
)
run_exercise(ctrl, exercise_config, image_matcher=image_matcher)

# 远征循环
while True:
    collected = collect_expedition(ctrl)
    if collected:
        collect_rewards(ctrl)
    time.sleep(300)  # 每 5 分钟检查一次
```

---

## 11. 与 v1 API 对照

| 操作 | v1 写法 | v2 写法 |
|------|---------|---------|
| 导航 | `timer.set_page("map_page")` | `goto_page(ctrl, "地图页面")` |
| 远征 | `Expedition(timer).run()` | `collect_expedition(ctrl)` |
| 奖励 | `get_rewards(timer)` | `collect_rewards(ctrl)` |
| 建造 | `BuildManager(timer).build(...)` | `build_ship(ctrl, recipe)` |
| 收建造 | `BuildManager(timer).get_build()` | `collect_built_ships(ctrl)` |
| 做菜 | `cook(timer, position)` | `cook(ctrl, position)` |
| 修理 | `repair_by_bath(timer)` | `repair_in_bath(ctrl)` |
| 快修 | `quick_repair(timer, 2, ...)` | `apply_repair(ctrl, RepairStrategy.SEVERE)` |
| 解装 | `destroy_ship(timer, ...)` | `destroy_ships(ctrl)` |
| 战役 | `BattlePlan(timer, '困难驱逐').run()` | `run_campaign(ctrl, config, matcher)` |
| 常规战 | `NormalFightPlan(timer, '5-4').run()` | `run_normal_fight(ctrl, plan, matcher)` |
| 演习 | `NormalExercisePlan(timer, ...).run()` | `run_exercise(ctrl, config, matcher)` |
| 决战 | `DecisiveBattle(timer).run()` | `DecisiveController(ctrl, config).run()` |

**核心变化**: `timer` → `ctrl`，God Object → 纯函数。
