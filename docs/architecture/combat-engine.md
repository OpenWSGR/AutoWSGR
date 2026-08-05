# 战斗引擎

> 返回 [架构概述](README.md)

本文档描述 AutoWSGR 的核心战斗引擎——一个基于视觉识别的有限状态机。

---

## 架构概览

```
CombatEngine
├── CombatRecognizer        截图 → 阶段识别 (模板+像素)
├── PhaseHandlersMixin      各阶段处理器 (操作+决策)
├── CombatPlan              作战计划 (YAML 驱动)
│   └── NodeDecision        每节点战术 (阵型/夜战/规则)
├── CombatHistory           战斗事件记录
└── state.py                CombatPhase 枚举 + 转移图
```

---

## 状态机核心循环

**文件**: `autowsgr/combat/engine.py`

`CombatEngine.fight(plan, initial_ship_stats)` 执行完整战斗：

```
fight(plan)
    │
    ├─ _reset()                           # 重置状态
    ├─ 构造 CombatRecognizer
    ├─ 加载 NodeTracker (常规战/活动战)
    │
    └─ while True:
         │
         ├─ _step()
         │   ├─ _update_state()           # 等待+识别下一阶段
         │   │   ├─ resolve_successors()  # 查转移表 → 候选列表
         │   │   ├─ _get_poll_action()    # 构建轮询间动作
         │   │   └─ recognizer.wait_for_phase(candidates, poll_action)
         │   │
         │   └─ _make_decision(phase)     # 分发到对应 handler
         │       └─ _handle_*()           # 执行操作 → 返回 ConditionFlag
         │
         ├─ FIGHT_CONTINUE → 继续循环
         ├─ FIGHT_END → 结束 (成功)
         ├─ DOCK_FULL → 结束 (船坞满)
         └─ SL → 重启游戏 + 结束
```

### ConditionFlag

```python
class ConditionFlag(IntEnum):
    OPERATION_SUCCESS  # 操作成功
    DOCK_FULL          # 船坞已满
    SL                 # SL 重来
    FIGHT_CONTINUE     # 继续战斗
    FIGHT_END          # 战斗结束
```

---

## CombatPhase 状态枚举

**文件**: `autowsgr/combat/state.py`

```python
class CombatPhase(Enum):
    # 出征过渡
    START_FIGHT            # 点击出征后的短暂过渡
    DOCK_FULL              # 船坞已满弹窗

    # 航行
    PROCEED                # 继续前进/回港提示
    FIGHT_CONDITION        # 战况选择 (稳步前进/火力万岁/...)

    # 索敌
    SPOT_ENEMY_SUCCESS     # 索敌成功，显示敌方编成

    # 选阵型
    FORMATION              # 阵型选择界面

    # 战斗
    MISSILE_ANIMATION      # 导弹支援动画
    FIGHT_PERIOD           # 昼战/夜战进行中
    NIGHT_PROMPT           # 夜战选择 (追击/撤退)

    # 结算
    RESULT                 # 战果评价 (S/A/B/C/D/SS)
    GET_SHIP               # 掉落舰船

    # 特殊
    FLAGSHIP_SEVERE_DAMAGE # 旗舰大破强制回港

    # 结束页面
    MAP_PAGE               # 回到地图 (常规战)
    EXERCISE_PAGE          # 回到演习页
    EVENT_MAP_PAGE         # 回到活动地图
```

---

## 状态转移图

### ModeCategory 模式大类

```python
class ModeCategory(Enum):
    MAP     # 多节点地图 (常规战、活动战)
    SINGLE  # 单点战斗 (战役、演习、决战)
```

### 模式规格

| CombatMode | 大类   | 结束页面           |
|------------|--------|-------------------|
| NORMAL     | MAP    | MAP_PAGE          |
| EVENT      | MAP    | EVENT_MAP_PAGE    |
| BATTLE     | SINGLE | None (RESULT 终止) |
| DECISIVE   | SINGLE | None (RESULT 终止) |
| EXERCISE   | SINGLE | EXERCISE_PAGE     |

### build_transitions(category, end_page)

根据模式大类动态构建状态转移图。返回 `dict[CombatPhase, PhaseBranch]`。

`PhaseBranch` 有两种形式：

- **无条件列表**: `[CombatPhase.A, CombatPhase.B]` — 直接候选
- **动作分支字典**: `{'yes': [...], 'no': [...]}` — 按上一步动作分支

### MAP 模式典型流程

```
START_FIGHT → FIGHT_CONDITION → SPOT_ENEMY_SUCCESS → FORMATION
    → FIGHT_PERIOD → NIGHT_PROMPT → RESULT → GET_SHIP → PROCEED
    → FIGHT_CONDITION → ... (循环)
    → MAP_PAGE (终止)
```

分支节点：

- `SPOT_ENEMY_SUCCESS` → `fight` (进入战斗) / `detour` (迂回) / `retreat` (撤退)
- `PROCEED` → `yes` (继续) / `no` (回港)
- `NIGHT_PROMPT` → `yes` (追击) / `no` (撤退)

### SINGLE 模式典型流程

```
START_FIGHT → FORMATION → FIGHT_PERIOD → NIGHT_PROMPT → RESULT
```

无 PROCEED、无 FIGHT_CONDITION、无 GET_SHIP。

---

## 作战计划 (CombatPlan)

**文件**: `autowsgr/combat/plan.py`

### CombatPlan

```python
@dataclass
class CombatPlan:
    name: str                    # 计划名称
    mode: str                    # 战斗模式 (normal/battle/exercise/decisive/event)
    chapter: int                 # 章节
    map_id: int                  # 地图编号
    fleet_id: int                # 出征舰队
    fleet: list[str] | None      # 可选换船列表

    repair_mode: list[RepairMode]  # 6 个位置的修理策略
    fight_condition: FightCondition  # 战况选择
    selected_nodes: list[str]     # 选择节点

    nodes: dict[str, NodeDecision]  # 节点名 → 决策
    default_node: NodeDecision    # 默认节点决策

    event_name: str | None        # 活动名称 (event 模式)

    # 派生属性 (构造时计算):
    transitions: dict             # 状态转移图
    end_phase: CombatPhase        # 结束阶段
```

### NodeDecision

```python
@dataclass
class NodeDecision:
    formation: Formation = double_column  # 阵型
    night: bool = False                   # 是否夜战
    proceed: bool = True                  # 是否继续前进
    proceed_stop: RepairMode              # 达到此破损停止前进
    enemy_rules: RuleEngine | None        # 索敌规则 (按敌舰种判断)
    formation_rules: RuleEngine | None    # 阵型规则 (按敌阵型判断)
    detour: bool = False                  # 是否迂回
    long_missile_support: bool = False    # 远程导弹支援
    SL_when_spot_enemy_fails: bool        # 索敌失败 SL
    SL_when_detour_fails: bool            # 迂回失败 SL
    SL_when_enter_fight: bool             # 进入战斗 SL (卡点)
    formation_when_spot_enemy_fails: Formation | None  # 索敌失败替代阵型
```

### YAML 加载

作战计划从 YAML 文件加载，路径解析通过 `resolve_plan_path()`：

```
直接路径 → 补全 .yaml → data/plan/ 下搜索 → data/plan/ 下补全 .yaml
```

YAML 中 `nodes` 字段的每个节点配置映射到 `NodeConfig` (Pydantic) → `NodeDecision`:

```yaml
nodes:
  A:
    formation: 2          # 复纵阵
    night: true
    enemy_rules:
      - "(BB >= 2) and (CV > 0) => retreat"
  B:
    formation: 1
    detour: true
```

---

## 阶段处理器 (PhaseHandlersMixin)

**文件**: `autowsgr/combat/handlers.py`

`_make_decision(phase)` 根据当前阶段分发到对应 handler：

| 阶段                    | 处理器                          | 职责                                |
|-------------------------|--------------------------------|-------------------------------------|
| START_FIGHT             | (直接返回 FIGHT_CONTINUE)       | 过渡态                               |
| DOCK_FULL               | `_handle_dock_full()`          | 返回 DOCK_FULL flag                  |
| PROCEED                 | `_handle_proceed()`            | 检查修理需求 → 继续 / 回港           |
| FIGHT_CONDITION         | `_handle_fight_condition()`    | 选择战况                             |
| SPOT_ENEMY_SUCCESS      | `_handle_spot_enemy()`         | 识别敌方 → 规则引擎 → 战/迂回/撤退   |
| FORMATION               | `_handle_formation()`          | 选择阵型 (规则优先 → 默认)           |
| MISSILE_ANIMATION       | `_handle_missile_animation()`  | 跳过或等待                           |
| FIGHT_PERIOD            | `_handle_fight_period()`       | 等待战斗结束 + 血量分类              |
| NIGHT_PROMPT            | `_handle_night_prompt()`       | 追击或撤退                           |
| RESULT                  | `_handle_result()`             | 检测评级/MVP/掉落 → 记录             |
| GET_SHIP                | `_handle_get_ship()`           | 跳过掉落动画                         |
| FLAGSHIP_SEVERE_DAMAGE  | `_handle_flagship_severe()`    | 确认并 SL                           |
| MAP_PAGE / EXERCISE_PAGE / EVENT_MAP_PAGE | (终止态)   | 返回 FIGHT_END                       |

### 处理器输出

每个 handler 返回 `ConditionFlag`：

- `FIGHT_CONTINUE`: 正常，继续循环
- `FIGHT_END`: 到达终止页面
- `SL`: 触发 SL (旗舰大破 / 规则匹配)
- `DOCK_FULL`: 船坞满

handler 还会设置 `self._last_action` (如 `'yes'`/`'no'`/`'fight'`/`'detour'`)，用于转移图的分支查找。

---

## 战斗视觉识别器 (CombatRecognizer)

**文件**: `autowsgr/combat/recognizer.py`

### PhaseSignature

每个 `CombatPhase` 关联一个视觉签名：

```python
@dataclass
class PhaseSignature:
    template_key: TemplateKey | None         # 图像模板标识
    default_timeout: float = 15.0            # 超时 (秒)
    confidence: float = 0.8                  # 模板匹配最低置信度
    after_match_delay: float = 0.0           # 匹配后等待 (UI 动画)
    pixel_signature: PixelSignature | None   # 像素特征 (备选/独立)
```

签名注册表 `PHASE_SIGNATURES: dict[CombatPhase, PhaseSignature]` 定义了所有阶段的视觉特征。

### wait_for_phase(candidates, poll_action)

核心轮询方法：

```
while not timeout:
    screen = screenshot()
    if poll_action: poll_action(screen)    # 加速点击/节点追踪
    for phase in candidates:
        sig = PHASE_SIGNATURES[phase]
        if sig.template_key:
            match = ImageChecker.is_matching(screen, ...)
        elif sig.pixel_signature:
            match = PixelChecker.is_matching(screen, sig.pixel_signature)
        if match:
            sleep(sig.after_match_delay)
            return phase
raise CombatRecognitionTimeout
```

### 异常处理

- `CombatRecognitionTimeout`: 超时未识别到任何候选阶段 → 引擎尝试 `_try_recovery()`
- `CombatStopRequested`: 收到停止信号 (`ctx.stop_event`)

---

## 敌舰/阵型/掉落识别

**文件**: `autowsgr/combat/recognition.py`

### 敌舰识别

```python
recognize_enemy_ships(screen, mode='fight', dll=None) -> dict[str, int]
```

- 缩放到 960x540
- 裁剪 6 个敌舰图标区域
- 调用 C++ DLL 进行图像分类
- 返回舰种计数 `{'BB': 2, 'CV': 1, ...}`

### 敌方阵型识别

```python
recognize_enemy_formation(screen, ocr_engine) -> str
```

- 裁剪左上角 ROI
- OCR 识别（allowlist: `"单纵复轮型梯形横阵"`）
- 返回阵型名称字符串

### 掉落舰船识别

```python
recognize_ship_drop(screen, ocr_engine) -> tuple[str, str] | tuple[str, str]
```

- OCR 识别掉落文本
- 替换规则处理常见错误 (`REPLACE_RULE`)
- Levenshtein 编辑距离模糊匹配 `SHIPNAMES` 数据库

---

## 战斗记录

**文件**: `autowsgr/combat/history.py`

### CombatHistory

```python
@dataclass
class CombatHistory:
    events: list[CombatEvent]     # 每节点事件 (战况/索敌/阵型/...)
    fights: list[FightResult]     # 每次战斗结果
```

### CombatResult

```python
@dataclass
class CombatResult:
    flag: ConditionFlag           # 结束标志
    ship_stats: list[ShipDamageState]  # 战后血量 (6 位)
    node_count: int               # 经过节点数
    history: CombatHistory        # 详细记录
```

---

## 节点追踪器

**文件**: `autowsgr/combat/node_tracker.py`

MAP 模式下，通过跟踪我方舰队图标在地图上的移动来确定当前节点：

```python
class NodeTracker:
    def __init__(self, map_data: MapNodeData)
    def update_ship_position(screen: ndarray)  # 检测舰队图标位置
    def update_node() -> str                   # 根据位置判断当前节点
    def reset()
```

地图节点数据从 `data/map/` 加载：

```python
MapNodeData.load(chapter, map_id) -> MapNodeData | None
MapNodeData.load_event(event_name, chapter, map_id) -> MapNodeData | None
```

---

## 规则引擎

**文件**: `autowsgr/combat/rules.py`

作战计划中 `enemy_rules` 和 `enemy_formation_rules` 使用规则引擎进行条件判断：

```python
class RuleEngine:
    @classmethod
    def from_legacy_rules(cls, rules) -> RuleEngine
    @classmethod
    def from_formation_rules(cls, rules) -> RuleEngine

    def evaluate(self, enemy_info) -> RuleAction
        # 返回匹配动作，未匹配时返回 RuleAction.no_action()
```

舰种规则支持字符串格式 `"(BB >= 2) and (CV > 0) => retreat"`，
也支持 YAML 列表格式 `[(BB >= 2) and (CV > 0), retreat]`。

---

## 与其他模块的关系

- **下游**: [vision](vision.md) 提供模板匹配、像素匹配、OCR
- **下游**: [emulator](emulator.md) 提供截图和触控
- **上游**: [ops](ops.md) 的各 Runner 调用 `CombatEngine.fight()`
- **数据**: [context-and-config](context-and-config.md) 的 `GameContext` 提供运行时状态同步
