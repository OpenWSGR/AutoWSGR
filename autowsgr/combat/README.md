## 测试计划

### 需测试模块

- actions
    - detect_result_grade
    - detect_ship_stats
- engine
    - fight
    - _try_recovery
- handlers
    - _handle_fight_condition
    - _handle_spot_enemy
    - _handle_formation
    - _handle_missile_animation
    - _handle_night_prompt
    - _handle_result
    - _handle_get_ship
    - _handle_proceed
- node_tracker
- recognition
    - recognize_enemy_ships
    - recognize_enemy_formation

### 脱机测试（未做）

- recognize_enemy_ships、recognize_enemy_formation 可从截图直接测试
- detect_result_grade、detect_ship_stats 可从截图直接测试
- 决策相关，可通过 mock 数据测试

### 战役测试（已通过）

- 潜艇战役
    - _handle_spot_enemy
    - _handle_formation
    - _handle_night_prompt
    - _handle_result

### 常规图测试（已通过）

- 7-46SS
    - fight
    - node_tracker
    - _handle_get_ship
    - _handle_proceed

### 特别测试（未做）

- 旗舰大破回港测试
    - _handle_flagship_severe_damage
- 远程打击测试
    - _handle_missile_animation

### 补充测试（未做）

- 中破规则回港测试
    - 需要在 proceed 中选择回港
- 敌方阵容不匹配测试
    - 需要在 _handle_spot_enemy 中回港
- SL 测试
    - 索敌失败需要正确 SL


## 功能简介

点击 "开始出征" 后，所有动作均由本模块处理，战斗结束或者出现异常状况时，会通过返回值报告详细信息。

### CombatEngine

```python
class CombatEngine:
    def __init__(self, ctx: GameContext) -> None:
        pass

    def fight(self, plan: CombatPlan, initial_ship_stats: list[ShipDamageState]) -> CombatResult:
        pass
```

- fight: 执行一次完整的战斗循环，直到战斗结束或者出现异常状况。返回 CombatResult 以报告结果。

### CombatResult

```python
@dataclass
class CombatResult:
    flag: ConditionFlag = ConditionFlag.FIGHT_END
    history: CombatHistory = field(default_factory=CombatHistory)
    ship_stats: list[ShipDamageState] = field(
        default_factory=lambda: [ShipDamageState.NORMAL] * 6,
    )
    node_count: int = 0
```

- flag: 结束状态标记，包括正常结束、SL、船坞已满、战役次数耗尽等
- history: 战斗历史记录，包含每个节点的决策和状态
- ship_stats: 战斗结束时的舰船状态列表
- node_count: 经过的节点数量

### CombatHistory

`CombatHistory` 记录了一次完整战斗的事件历史。它通过收集 `CombatEvent` 来追踪战斗过程中的关键节点和结果。

```python
class CombatHistory:
    events: list[CombatEvent]

    def add(self, event: CombatEvent) -> None: ...
    def reset(self) -> None: ...
    def get_fight_results(self) -> dict[str, FightResult] | list[FightResult]: ...
```

- **`events`**: 记录的事件列表，每个事件包含节点名称、事件类型（如 `ENTER_NODE`, `RESULT`）和具体数据。
- **`add` / `reset`**: 添加新事件或清空当前历史记录。
- **`get_fight_results`**: 提取所有战果结算事件的结果，方便后续统计或决策。

可以输出一下来查看：

```text
[FORMATION] | 节点=A | 动作=阵型4 (wedge)
[RESULT] | 节点=A | 结果=MVP=0 评价=SS
[GET_SHIP] | 节点=A
[PROCEED] | 节点=A | 动作=前进 | 血量=[<ShipDamageState.NORMAL: 0>, <ShipDamageState.NORMAL: 0>, <ShipDamageState.NORMAL: 0>, <ShipDamageState.NORMAL: 0>, <ShipDamageState.NORMAL: 0>, <ShipDamageState.NORMAL: 0>]
[SPOT_ENEMY] | 节点=D | 动作=战斗 | 敌方={'CVL': 3, 'BC': 1, 'ALL': 4}
[FORMATION] | 节点=D | 动作=阵型4 (wedge)
[RESULT] | 节点=D | 结果=MVP=0 评价=SS
[GET_SHIP] | 节点=D
[PROCEED] | 节点=D | 动作=前进 | 血量=[<ShipDamageState.NORMAL: 0>, <ShipDamageState.NORMAL: 0>, <ShipDamageState.NORMAL: 0>, <ShipDamageState.NORMAL: 0>, <ShipDamageState.NORMAL: 0>, <ShipDamageState.NORMAL: 0>]
[SPOT_ENEMY] | 节点=E | 动作=战斗 | 敌方={'CVL': 3, 'BC': 1, 'ALL': 4}
[FORMATION] | 节点=E | 动作=阵型4 (wedge)
[RESULT] | 节点=E | 结果=MVP=0 评价=SS
[GET_SHIP] | 节点=E
[AUTO_RETURN] | 节点=E | 动作=正常
```

### CombatPlan

`CombatPlan` 聚合了出征配置以及每个节点的战术决策，是指导 `CombatEngine` 运行的核心配置类。

```python
@dataclass
class CombatPlan:
    name: str = ""
    mode: str = CombatMode.NORMAL
    chapter: int | str = 1
    map_id: int | str = 1
    fleet_id: int = 1
    fleet: list[str] | None = None
    repair_mode: RepairMode | list[RepairMode] = RepairMode.severe_damage
    fight_condition: FightCondition = FightCondition.aim
    selected_nodes: list[str] = field(default_factory=list)
    nodes: dict[str, NodeDecision] = field(default_factory=dict)
    default_node: NodeDecision = field(default_factory=NodeDecision)
    event_name: str | None = None
```

- **`mode`**: 定义了战斗的模式，有 `normal_fight`、`exercise`、`campaign`、`event`。
- **`chapter` / `map_id`**: 活动战和常规战有效，指定了章节（活动章节包括 `E` 和 `H`）和地图。
- **`repair_mode`**: 定义了舰队的修理策略（如中破修、大破修等）。单个值表示全局策略，列表则针对每个位置单独设置。逻辑当舰船状态达到或超过该条件时执行修理
- **`nodes` / `default_node`**: 存储了针对特定节点的战术决策（`NodeDecision`），如果未配置则使用默认决策。
- **`selected_nodes`**: 定义了计划中包含的节点列表，战斗过程中只会处理这些节点，其他节点将被跳过（遇到直接撤退或者 SL）。
- **`event_name`**: 活动战有效，必填，指定了活动名称以便于识别和统计。

### NodeDecision

`NodeDecision` 定义了在特定节点上的战术选择，如阵型、夜战策略等。

```python
@dataclass
class NodeDecision:
    formation: Formation = Formation.double_column
    night: bool = False
    proceed: bool = True
    proceed_stop: RepairMode | list[RepairMode] = RepairMode.severe_damage
    enemy_rules: RuleEngine | None = None
    formation_rules: RuleEngine | None = None
    detour: bool = False
    long_missile_support: bool = False
    SL_when_spot_enemy_fails: bool = False
    SL_when_detour_fails: bool = True
    SL_when_enter_fight: bool = False
    formation_when_spot_enemy_fails: Formation | None = None
    ...
```

- **`formation`**: 选择的阵型（如单纵、复纵等）。
- **`night`**: 是否进行夜战的策略。
- **`proceed`**: 战斗结束后的前进策略（如继续前进、回港等）。
- **`proceed_stop`**: 针对每个位置舰船状态的前进停止条件，非列表为全局条件，列表则针对每个位置单独设置。损坏状态达到或超过该条件时停止前进，会覆盖 `proceed` 的设置。
- **`enemy_rules` / `formation_rules`**: 索敌成功时，应用的规则引擎，用于决定战术选择，包括是否撤退，阵形选择。
- **`SL_when_*`**: 在特定失败条件下是否进行 SL。
- **`formation_when_spot_enemy_fails`**: 在索敌失败时选择的阵型。

## 未来计划

- 进一步改进稳定性，确保在各种设备环境下都能正常执行
    - 添加更多状态检查点，确保每个状态都正确转移
    - 添加重试机制
- 改进识别效率
    - 消去无意义截图
    - 改进识别算法
- 改进敌方阵容识别精确度（目前 DLL 识别已经报告了误判）
- 正确报告非预期异常，例如网络断开等
