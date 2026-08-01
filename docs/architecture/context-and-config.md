# 上下文与配置系统

> 返回 [架构概述](README.md)

本文档描述 AutoWSGR 的两大核心数据结构：**GameContext**（运行时上下文）和 **UserConfig**（用户配置模型）。

---

## GameContext — 运行时上下文

**文件**: `autowsgr/context/game_context.py`

`GameContext` 是一个 `@dataclass`，聚合了所有基础设施引用与游戏运行时状态。框架中几乎所有游戏层代码都通过 `ctx: GameContext` 参数获取共享服务。

### 结构

```python
@dataclass
class GameContext:
    # ── 基础设施引用 (构造时注入) ──
    ctrl: AndroidController       # 设备控制器 (截图+触控)
    config: UserConfig            # 用户配置 (只读)
    ocr: OCREngine                # OCR 引擎实例

    # ── 游戏运行时状态 ──
    resources: Resources          # 燃弹钢铝 + 道具
    fleets: list[Fleet]           # 4 支舰队 (fleet_id 1-4)
    expeditions: ExpeditionQueue  # 远征队列 (4 槽位)
    build_queue: BuildQueue       # 建造队列
    ship_registry: dict[str, Ship]  # 舰船注册表 (名称为键)
    current_page: PageName | None # 当前 UI 页面

    # ── 每日计数器 ──
    dropped_ship_count: int       # 当天掉落舰船数
    dropped_loot_count: int       # 当天掉落胖次数
    quick_repair_used: int        # 本次会话快修消耗

    # ── 控制信号 ──
    stop_event: threading.Event   # 任务停止信号 (由 TaskManager 设置)
```

### 便捷方法

| 方法                                         | 说明                                   |
|----------------------------------------------|----------------------------------------|
| `fleet(fleet_id: int) -> Fleet`              | 按编号 (1-4) 获取舰队                    |
| `get_ship(name: str) -> Ship`                | 按名称获取舰船，不存在则自动注册            |
| `is_ship_available(name: str) -> bool`       | 判断舰船是否可用 (非大破且非修理中)         |
| `update_ship_damage(name, state)`            | 更新舰船破损状态                          |
| `sync_before_combat(fleet_id, ships, ...)`   | 战斗前同步：出击编成、每日计数器            |
| `sync_after_combat(fleet_id, result)`        | 战斗后同步：血量状态、掉落统计              |

### 构造流程

`GameContext` 由 `Launcher.build_context()` 构造，详见 [scheduler-and-server.md](scheduler-and-server.md)：

```
Launcher.load_config() → UserConfig
Launcher.connect()     → ScrcpyController
Launcher.create_ocr()  → EasyOCREngine
Launcher.build_context() → GameContext(ctrl, config, ocr)
```

运行时状态（`resources`, `fleets` 等）使用默认值初始化，在后续操作中通过画面识别逐步更新。

---

## UserConfig — 用户配置模型

**文件**: `autowsgr/infra/config.py`

基于 Pydantic v2 的不可变配置模型层级。所有子配置均标记 `frozen=True`。

### 模型层级

```
UserConfig (顶层)
├── emulator: EmulatorConfig
│     type, path, serial, process_name
├── account: AccountConfig
│     game_app, account, password  (+property: package_name)
├── ocr: OCRConfig
│     gpu, mirror, ship_name_match_confidence, ship_name_corrections, ship_name_aliases
├── log: LogConfig
│     level, root, dir, show_*_debug 开关, channels
│     (+property: effective_channels)
├── daily_automation: DailyAutomationConfig | None
│     auto_expedition, auto_battle, auto_exercise, ...
├── decisive_battle: DecisiveConfig | None
│     chapter, level1, level2, flagship_priority, repair_level, ...
│
├── os_type: OSType              # 自动检测
├── operation_delay_min: float   # UI 操作延迟下界 (秒)
├── operation_delay_max: float   # UI 操作延迟上界 (秒)
├── dock_full_destroy: bool      # 船坞满自动清空
├── repair_manually: bool        # 手动修理模式
├── bathroom_count: int          # 修理位置总数
├── destroy_ship_work_mode       # 解装模式 (disable/include/exclude)
├── destroy_ship_types           # 解装舰种列表
└── remove_equipment_mode: bool  # 解装前卸装备
```

### 子配置详解

#### EmulatorConfig

| 字段           | 类型               | 默认值              | 说明               |
|----------------|--------------------|--------------------|-------------------|
| `type`         | `EmulatorType`     | `雷电`             | 模拟器类型          |
| `path`         | `str \| None`      | `None` (自动检测)   | 可执行文件路径       |
| `serial`       | `str \| None`      | `None` (自动检测)   | ADB serial 地址    |
| `process_name` | `str \| None`      | `None` (自动推断)   | 进程名             |

#### LogConfig

特殊属性 `effective_channels`：合并布尔开关 (`show_*_debug`) 与显式 `channels` 字典，生成最终通道级别映射。显式 `channels` 优先级高于布尔开关。

通道映射关系：

| 布尔开关                            | 关闭时禁用的通道                |
|-------------------------------------|-------------------------------|
| `show_emulator_debug = False`       | `emulator` → INFO             |
| `show_ui_debug = False`             | `ui` → INFO                  |
| `show_vision_debug = False`         | `vision` → INFO              |
| `show_ops_debug = False`            | `ops` → INFO                 |
| `show_combat_state_debug = False`   | `combat.engine` → INFO       |
| `show_combat_recognition_debug = False` | `combat.recognition` → INFO |
| `show_decisive_battle_info = True`  | `decisive` / `ops.decisive` / `ui.decisive` → DEBUG |

#### DecisiveConfig

| 字段                  | 类型          | 默认值                       | 说明                 |
|-----------------------|---------------|------------------------------|---------------------|
| `chapter`             | `int`         | `6`                          | 决战章节 (1-6)       |
| `level1`              | `list[str]`   | 预设 6 艘潜艇                | 一级舰队             |
| `level2`              | `list[str]`   | 预设 2 艘潜艇                | 二级舰队             |
| `flagship_priority`   | `list[str]`   | 预设旗舰优先级               | 旗舰优先队列          |
| `repair_level`        | `int`         | `1`                          | 1=中破修, 2=大破修   |
| `use_quick_repair`    | `bool`        | `True`                       | 是否使用快修          |
| `full_destroy`        | `bool`        | `False`                      | 船舱满解装            |
| `useful_skill`        | `bool`        | `False`                      | 充分利用技能          |
| `useful_skill_strict` | `bool`        | `False`                      | 严格利用技能          |

---

## 配置加载流程

**文件**: `autowsgr/infra/config.py` — `ConfigManager`

```
用户 YAML 文件 (usersettings.yaml)
       │
       ▼
ConfigManager.load(path)
  ├─ path 为 None → 自动检测当前目录 usersettings.yaml
  ├─ load_yaml(path) → dict
  └─ UserConfig(**dict) → Pydantic v2 校验
       ├─ field_validator: 类型强转 (destroy_ship_work_mode 中文别名)
       ├─ model_validator: 日志目录自动生成时间戳
       └─ frozen=True → 不可变配置对象
```

YAML 示例（最小配置）：

```yaml
emulator:
  type: 雷电
account:
  game_app: 官服
```

所有未指定的字段使用 Pydantic 默认值。`daily_automation` 和 `decisive_battle` 默认为 `None`（不启用）。

---

## 组件模型

### Fleet (`autowsgr/context/fleet.py`)

```python
@dataclass
class Fleet:
    fleet_id: int               # 编号 1-4
    ships: list[Ship]           # 最多 6 艘
    # Properties:
    size -> int                 # 编成舰船数
    damage_states -> list[ShipDamageState]
    has_severely_damaged -> bool
    needs_repair -> bool
```

### Ship (`autowsgr/context/ship.py`)

```python
@dataclass
class Ship:
    name: str
    ship_type: ShipType | None
    level: int | None
    health: int | None
    max_health: int | None
    damage_state: ShipDamageState = NORMAL
    locked: bool = True
    equipment: list[Equipment]
    repair_end_time: float | None
    repairing: bool = False
    # Properties:
    health_ratio -> float | None
    is_repairing -> bool
    available -> bool            # 非大破 & 非修理中
    needs_repair(mode) -> bool   # 按修理策略判断
```

### Resources (`autowsgr/context/resources.py`)

```python
@dataclass
class Resources:
    fuel: int = 0
    ammo: int = 0
    steel: int = 0
    aluminum: int = 0
    diamond: int = 0
    fast_repair: int = 0
    fast_build: int = 0
    ship_blueprint: int = 0
    equipment_blueprint: int = 0
```

### ExpeditionQueue (`autowsgr/context/expedition.py`)

4 个槽位，每个槽位为一个 `Expedition` 实例：

```python
@dataclass
class Expedition:
    chapter: int              # 远征章节 (1-9)
    node: int                 # 节点 (1-4)
    fleet: int                # 舰队编号
    start_time: float | None
    remaining_seconds: float
    is_active: bool
```

### BuildQueue (`autowsgr/context/build.py`)

```python
@dataclass
class BuildSlot:
    occupied: bool
    remaining_seconds: float
    # Properties: is_complete, is_idle

@dataclass
class BuildQueue:
    slots: list[BuildSlot]     # 4+ 槽位
    # Properties: idle_count, complete_count
```

---

## 与其他模块的关系

- **构造者**: [scheduler](scheduler-and-server.md) 的 `Launcher` 负责构造 `GameContext`
- **消费者**: [ops](ops.md) 层的所有 Runner 和操作函数通过 `ctx` 访问基础设施
- **更新者**: [combat](combat-engine.md) 引擎通过 `sync_before/after_combat()` 更新运行时状态
- **配置消费**: [emulator](emulator.md) 读取 `config.emulator`，[vision](vision.md) 读取 `config.ocr`
