# 战斗系统使用指南

> 详解 AutoWSGR v2 的三种战斗模式：常规战、战役、演习。
> 包含作战计划配置、YAML 格式说明、节点决策规则。

---

## 目录

- [1. 战斗流程概览](#1-战斗流程概览)
- [2. 作战计划 (CombatPlan)](#2-作战计划-combatplan)
- [3. 常规战斗 (Normal Fight)](#3-常规战斗-normal-fight)
- [4. 战役 (Campaign)](#4-战役-campaign)
- [5. 演习 (Exercise)](#5-演习-exercise)
- [6. 节点决策与规则引擎](#6-节点决策与规则引擎)
- [7. 战斗结果处理](#7-战斗结果处理)
- [8. 进阶：自定义回调](#8-进阶自定义回调)

---

## 1. 战斗流程概览

所有战斗类型共享相同的底层引擎 (`CombatEngine`)，流程如下：

```
进入地图 → 出征准备 (选舰队/修理) → 开始出征
                    ↓
    ┌───────── 战斗循环 ─────────┐
    │  战况选择 → 索敌 → 阵型 →   │
    │  导弹 → 昼战 → 夜战判定 →   │
    │  战果 → 掉落 → 前进/回港    │
    └─────────────────────────────┘
                    ↓
            返回战斗结果
```

### 三种模式差异

| 特性 | 常规战 (NORMAL) | 战役 (BATTLE) | 演习 (EXERCISE) |
|------|----------------|---------------|-----------------|
| 地图节点 | 多节点 | 单点 | 单点 |
| 前进/回港 | 有 | 无 | 无 |
| 旗舰大破 | 可选 SL | 直接结束 | 无影响 |
| 战况选择 | 有 (可配置) | 有 | 无 |
| 修理 | 出征前 | 出征前 | 出征前 |
| 结束页面 | 地图页面 | 战役页面 | 演习页面 |

---

## 2. 作战计划 (CombatPlan)

### YAML 配置格式

```yaml
# plans/normal_fight/5-4.yaml
name: "5-4 周常"
chapter: 5
map: 4
fleet_id: 1
repair_mode: 2                    # 1=中破修, 2=大破修
fight_condition: 1                # 1~5 战况选择
selected_nodes: [A, B, D, F]      # 白名单节点 (只打这些)

# 默认节点决策 (所有节点通用)
node_defaults:
  formation: 2                    # 阵型: 1单纵 2复纵 3轮型 4梯形 5单横
  night: True                     # 是否追击夜战
  proceed: True                   # 是否继续前进 (True=前进, False=回港)

# 特定节点覆盖
node_args:
  A:
    formation: 5                  # A 点用单横
    night: False
  D:
    enemy_rules:                  # 索敌规则
      - [CV > 0, retreat]         # 有航母就撤退
    proceed: False                # D 点打完回港
  F:
    night: True
    proceed: False
```

### YAML 字段参考

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `name` | str | `""` | 计划名称 (日志用) |
| `chapter` | int | `1` | 章节编号 |
| `map` | int | `1` | 地图编号 |
| `fleet_id` | int | `1` | 出征舰队 (1~4) |
| `repair_mode` | int | `2` | 修理策略: 1=中破修, 2=大破修 |
| `fight_condition` | int | `1` | 战况选择 (1~5) |
| `selected_nodes` | list | `[]` | 白名单节点 (空=全部) |
| `map_entrance` | str | `"alpha"` | 地图入口 (alpha/beta) |
| `node_defaults` | dict | `{}` | 所有节点的默认决策 |
| `node_args` | dict | `{}` | 各节点独立决策 (覆盖默认) |

### 节点决策字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `formation` | int | `1` | 阵型编号 (1~5) |
| `night` | bool | `False` | 是否追击夜战 |
| `proceed` | bool | `True` | 是否前进 (NORMAL 模式) |
| `enemy_rules` | list | `[]` | 索敌规则 (见下文) |
| `formation_rules` | list | `[]` | 阵型选择规则 |
| `SL_when_spot_enemy_fails` | bool | `False` | 索敌失败时 SL |
| `SL_when_enemy_ship_type` | list | `[]` | 遇到特定舰种 SL |
| `proceed_stop` | list | `[]` | 中破停止位 (如 `[1,3]`) |

### 编程方式创建

```python
from autowsgr.combat.plan import CombatPlan, CombatMode, NodeDecision
from autowsgr.types import Formation

plan = CombatPlan(
    name="自定义 5-4",
    mode=CombatMode.NORMAL,
    chapter=5,
    map_id=4,
    fleet_id=1,
    default_node=NodeDecision(
        formation=Formation.double_column,
        night=True,
        proceed=True,
    ),
    nodes={
        "A": NodeDecision(formation=Formation.single_horizontal, night=False),
        "D": NodeDecision(proceed=False),
    },
)
```

---

## 3. 常规战斗 (Normal Fight)

### 基本用法

```python
from autowsgr.combat.plan import CombatPlan
from autowsgr.ops import run_normal_fight, run_normal_fight_from_yaml

# 方式一: 从 YAML 加载
results = run_normal_fight_from_yaml(
    ctrl,
    "plans/normal_fight/5-4.yaml",
    times=5,
)

# 方式二: 编程构建
plan = CombatPlan.from_yaml("plans/normal_fight/5-4.yaml")
results = run_normal_fight(ctrl, plan, times=5)
```

### 使用 Runner 类（更多控制）

```python
from autowsgr.ops.normal_fight import NormalFightRunner

runner = NormalFightRunner(
    ctrl,
    plan,
    ocr=ocr_engine,              # 可选: 章节导航用
    get_enemy_info=my_enemy_cb,  # 可选: 敌方编成识别
)

# 执行一次
result = runner.run()

# 执行多次，每次间隔 3 秒
results = runner.run_for_times(10, gap=3.0)
```

### 流程细节

1. **导航**: `goto_page("地图页面")` → 切换到出征面板
2. **选章节**: OCR 识别当前章节 → 翻页到目标章节
3. **选地图**: 点击地图节点位置
4. **出征准备**: 选舰队 → 修理 → 检测血量 → 出征
5. **战斗循环**: CombatEngine 按 `NORMAL_FIGHT_TRANSITIONS` 状态图执行
6. **结果处理**: 返回 `CombatResult`，含 `flag`、`ship_stats`、`node_count`

---

## 4. 战役 (Campaign)

### 基本用法

```python
from autowsgr.ops import CampaignConfig, run_campaign

config = CampaignConfig(
    map_index=3,           # 1=航母, 2=潜艇, 3=驱逐, 4=巡洋, 5=战列
    difficulty="hard",     # "easy" 或 "hard"
    fleet_id=1,
    formation=2,           # 复纵阵
    night=True,
    auto_support=True,     # 开启战役支援
    max_times=3,           # 最多打 3 次
)

results = run_campaign(ctrl, config)
```

### 使用 Runner 类

```python
from autowsgr.ops.campaign import CampaignRunner

runner = CampaignRunner(ctrl, config)

# 执行指定次数
results = runner.run_for_times(5)

# 执行到次数用完自动停止
results = runner.run_for_times()  # 使用 config.max_times
```

### 战役编号对照

| map_index | 战役类型 |
|-----------|---------|
| 1 | 航母 (carrier) |
| 2 | 潜艇 (submarine) |
| 3 | 驱逐 (destroyer) |
| 4 | 巡洋 (cruiser) |
| 5 | 战列 (battleship) |

### 支援设置

```python
config = CampaignConfig(
    auto_support=True,    # 每次出征自动检查并开启支援
    # ...
)
```

---

## 5. 演习 (Exercise)

### 基本用法

```python
from autowsgr.ops import ExerciseConfig, run_exercise

config = ExerciseConfig(
    fleet_id=2,             # 演习用第 2 舰队
    exercise_times=4,       # 最多打 4 次
    formation=2,            # 复纵阵
    night=False,            # 不追击夜战
    max_refresh_times=2,    # 最多刷新 2 次对手
    robot=True,             # 优先挑战机器人
)

results = run_exercise(ctrl, config)
```

### 使用 Runner 类

```python
from autowsgr.ops.exercise import ExerciseRunner

runner = ExerciseRunner(ctrl, config)
results = runner.run()
```

### 对手选择策略

当前实现按顺序选择对手。可通过继承 `ExerciseRunner` 并重写 `_select_rival()` 方法来实现自定义选择逻辑：

```python
class SmartExerciseRunner(ExerciseRunner):
    def _select_rival(self, attempt: int) -> bool:
        # 自定义选择逻辑: 检查对手等级、舰队强度等
        screen = self._ctrl.screenshot()
        # ... 自定义判断 ...
        return True
```

---

## 6. 节点决策与规则引擎

### 索敌规则 (enemy_rules)

索敌成功后，根据敌方编成做出决策。规则格式：`[条件, 动作]`

```yaml
enemy_rules:
  - [CV > 0, retreat]         # 有航母 → 撤退
  - [SS == 5, retreat]        # 5 艘潜艇 → 撤退
  - [SAP != 1, retreat]       # 轻母不等于 1 → 撤退
  - [BB >= 2, detour]         # 战列 >= 2 → 迂回
```

**条件格式**: `<舰种> <运算符> <数量>`

支持的舰种代号:

| 代号 | 舰种 | 代号 | 舰种 |
|------|------|------|------|
| CV | 航母 | BB | 战列 |
| CA | 重巡 | CL | 轻巡 |
| DD | 驱逐 | SS | 潜艇 |
| SAP | 轻母 | BC | 战巡 |
| NAP | 重母 | BM | 浅水重炮 |

支持的运算符: `==`, `!=`, `>`, `<`, `>=`, `<=`

支持的动作:

| 动作 | 说明 |
|------|------|
| `retreat` | 撤退 |
| `detour` | 迂回 |
| `refresh` | 刷新 (暂不支持) |

### 阵型规则 (formation_rules)

根据敌方编成动态选择阵型:

```yaml
formation_rules:
  - [SS > 0, 5]              # 有潜艇 → 单横 (5)
  - [CV >= 2, 3]             # 航母 >= 2 → 轮型 (3)
```

### v2 规则引擎 vs v1 eval()

v1 使用 `eval()` 直接执行条件字符串，存在代码注入风险。
v2 使用 `RuleEngine` 安全解析，只允许预定义的变量和运算符:

```python
from autowsgr.combat.rules import RuleEngine

engine = RuleEngine.from_legacy_rules([
    ["CV > 0", "retreat"],
    ["SS == 5", "retreat"],
])

# 安全评估
context = {"CV": 1, "SS": 3, "DD": 2}
action = engine.evaluate(context)
```

---

## 7. 战斗结果处理

### CombatResult 结构

```python
@dataclass
class CombatResult:
    flag: ConditionFlag          # 战斗状态标记
    history: CombatHistory       # 完整事件历史
    ship_stats: list[int]        # 战后血量 [0, s1, s2, s3, s4, s5, s6]
    node_count: int              # 推进节点数
```

### ConditionFlag 枚举

| 标记 | 含义 | 常见场景 |
|------|------|---------|
| `FIGHT_END` | 战斗正常结束 | 默认 |
| `OPERATION_SUCCESS` | 操作成功 | 通关 |
| `FIGHT_CONTINUE` | 继续战斗 | 多节点未结束 |
| `SL` | SL 重来 | 旗舰大破/不满意结果 |
| `DOCK_FULL` | 船坞已满 | 需要解装 |
| `BATTLE_TIMES_EXCEED` | 次数用完 | 战役每日限制 |
| `SKIP_FIGHT` | 跳过战斗 | 非白名单节点 |

### 结果判断示例

```python
from autowsgr.types import ConditionFlag

results = runner.run_for_times(10)

for i, r in enumerate(results):
    if r.flag == ConditionFlag.OPERATION_SUCCESS:
        print(f"第 {i+1} 次: 成功! 推进 {r.node_count} 节点")
    elif r.flag == ConditionFlag.SL:
        print(f"第 {i+1} 次: SL")
    elif r.flag == ConditionFlag.DOCK_FULL:
        print(f"第 {i+1} 次: 船坞满")
        break
```

---

## 8. 进阶：自定义回调

`run_combat()` 和各 Runner 支持多种回调函数，用于注入自定义逻辑：

### 可用回调

| 回调 | 签名 | 用途 |
|------|------|------|
| `get_enemy_info` | `(screen) → dict` | 获取敌方编成 |
| `get_enemy_formation` | `(screen) → Formation` | 获取敌方阵型 |
| `detect_ship_stats` | `(screen) → list[int]` | 检测我方血量 |
| `detect_result_grade` | `(screen) → str` | 检测战果等级 |
| `get_ship_drop` | `(screen) → str` | 获取掉落舰船 |
| `image_exist` | `(screen, key) → bool` | 检查图像是否存在 |
| `click_image` | `(screen, key) → bool` | 点击图像位置 |

### 示例：带敌方识别的常规战

```python
def my_enemy_info(screen):
    """通过 OCR 或模板匹配识别敌方编成"""
    return {"CV": 1, "DD": 3, "SS": 2}

runner = NormalFightRunner(
    ctrl, plan,
    get_enemy_info=my_enemy_info,
)
results = runner.run_for_times(5)
```

---

## 附录: 常用 YAML 计划示例

### 6-1 炸鱼 (5SS)

```yaml
chapter: 6
map: 1
selected_nodes: [A]
fight_condition: 4
repair_mode: 1
fleet_id: 4
node_defaults:
  enemy_rules:
    - [SS != 5, retreat]
  formation: 5
  night: False
  proceed: False
```

### 8-5 AI 捞鱼

```yaml
chapter: 8
map: 5
selected_nodes: [A, I]
repair_mode: 2
fleet_id: 2
node_defaults:
  formation: 2
  night: True
  proceed: True
node_args:
  I:
    proceed: False
```

### 2-1 捞胖次

```yaml
chapter: 2
map: 1
selected_nodes: [C, E, F]
repair_mode: 1
node_defaults:
  enemy_rules:
    - [SAP != 1, retreat]
  SL_when_spot_enemy_fails: True
  formation: 4
  night: False
  proceed: True
```
