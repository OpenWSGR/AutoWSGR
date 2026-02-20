# 决战模式使用指南

> 详解 AutoWSGR v2 的决战 (Decisive Battle) 系统 — 最复杂的战斗模式。

---

## 目录

- [1. 决战概述](#1-决战概述)
- [2. 配置](#2-配置)
- [3. 基本用法](#3-基本用法)
- [4. 架构与状态机](#4-架构与状态机)
- [5. 舰队选择策略](#5-舰队选择策略)
- [6. 进阶用法](#6-进阶用法)
- [7. 与 v1 对比](#7-与-v1-对比)

---

## 1. 决战概述

决战是《战舰少女R》中最复杂的战斗模式，具有以下特点：

- **3 个小关** (Stage 1~3)，通过全部后大关通关
- **每个小关多节点**，需要逐节点推进
- **舰队获取**: 从卡池中选择舰船组建临时舰队
- **进阶选择**: 每完成一个小关选择增益 buff
- **修理受限**: 无法使用正常修理，依赖进阶修复卡
- **掉线惩罚**: 撤退会清空当前章节所有进度

---

## 2. 配置

### DecisiveConfig

```python
from autowsgr.ops.decisive import DecisiveConfig

config = DecisiveConfig(
    chapter=6,                    # 决战章节 (1~6)
    level1=[                      # 一级舰队 (优先选择)
        "鲃鱼", "U-1206", "射水鱼",
        "U-96", "U-1405", "U-47",
    ],
    level2=[                      # 二级舰队 (补充选择)
        "U-81", "大青花鱼", "M-296",
        "U-505", "伊-25",
    ],
    flagship_priority=[           # 旗舰优先级
        "U-1405", "U-47", "U-1206",
    ],
    repair_level=2,               # 修理策略: 1=中破修, 2=大破修
    full_destroy=True,            # 船舱满时自动解装
)
```

### 配置字段参考

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `chapter` | int | `6` | 决战章节编号 (1~6) |
| `level1` | list[str] | `[]` | 一级舰队舰船名列表 (核心，优先选择) |
| `level2` | list[str] | `[]` | 二级舰队舰船名列表 (备选，补充选择) |
| `flagship_priority` | list[str] | `[]` | 旗舰优先级队列 (按顺序尝试) |
| `repair_level` | int | `2` | 修理策略: 1=中破即修, 2=大破才修 |
| `full_destroy` | bool | `True` | 船舱满时自动解装 |

### YAML 配置 (在 user_settings.yaml 中)

```yaml
decisive_battle:
  chapter: 6
  level1: ["鲃鱼", "U-1206", "射水鱼", "U-96", "U-1405", "U-47"]
  level2: ["U-81", "大青花鱼", "M-296", "U-505", "伊-25"]
  flagship_priority: ["U-1405", "U-47", "U-1206"]
  repair_level: 2
  full_destroy: True
```

---

## 3. 基本用法

### 执行一次决战

```python
from autowsgr.ops.decisive import DecisiveConfig, DecisiveController, DecisiveResult

config = DecisiveConfig(
    chapter=6,
    level1=["鲃鱼", "U-1206", "射水鱼", "U-96", "U-1405", "U-47"],
    level2=["U-81", "大青花鱼", "M-296"],
    flagship_priority=["U-1405"],
    repair_level=2,
)

controller = DecisiveController(ctrl, config, image_matcher=image_matcher)
result = controller.run()

match result:
    case DecisiveResult.CHAPTER_CLEAR:
        print("大关通关!")
    case DecisiveResult.RETREAT:
        print("撤退 (进度清空)")
    case DecisiveResult.LEAVE:
        print("暂离保存")
    case DecisiveResult.ERROR:
        print("异常退出")
```

### 执行多次决战

```python
results = controller.run_for_times(3)

for i, r in enumerate(results):
    print(f"第 {i+1} 轮: {r.value}")
```

> `run_for_times()` 遇到 `LEAVE` 或 `ERROR` 时自动停止。

### 通过 ops 统一导入

```python
from autowsgr.ops import DecisiveConfig, DecisiveController, DecisiveResult

controller = DecisiveController(ctrl, config)
result = controller.run()
```

---

## 4. 架构与状态机

### 模块拆分 (7 个文件)

```
ops/decisive/
├── __init__.py          # 公共导出
├── _config.py           # DecisiveConfig 配置
├── _state.py            # DecisivePhase 枚举 + DecisiveState 状态
├── _logic.py            # DecisiveLogic 纯决策逻辑
├── _handlers.py         # PhaseHandlersMixin 阶段处理器 (12 个)
├── _overlay.py          # 决战 overlay/弹窗检测 + 坐标常量
└── _controller.py       # DecisiveController 主控制器
```

### 状态机流程

```
                         ┌──────────────────────────────┐
                         │                              │
ENTER_MAP ──→ CHOOSE_FLEET ──→ MAP_READY               │
                                   │                    │
                    ┌──────────────┤                    │
                    ↓              ↓                    │
             ADVANCE_CHOICE   PREPARE_COMBAT            │
                    │              ↓                    │
                    │         IN_COMBAT                  │
                    │              ↓                    │
                    │         NODE_RESULT                │
                    │              │                    │
                    └──────────────┤                    │
                                   │                    │
                    ┌──────────────┼──────────────┐    │
                    ↓              ↓              ↓    │
               MAP_READY     STAGE_CLEAR      RETREAT ──┘
                                   │
                    ┌──────────────┤
                    ↓              ↓
               ENTER_MAP    CHAPTER_CLEAR ──→ FINISHED
                    ↑
                    └── (下一个小关)
```

### DecisivePhase 枚举 (14 个状态)

| 阶段 | 说明 |
|------|------|
| `INIT` | 初始化 |
| `ENTER_MAP` | 进入地图 |
| `CHOOSE_FLEET` | 首次选择舰队 |
| `MAP_READY` | 地图就绪，等待行动 |
| `ADVANCE_CHOICE` | 进阶选择 (buff) |
| `PREPARE_COMBAT` | 出征准备 |
| `IN_COMBAT` | 战斗进行中 |
| `NODE_RESULT` | 节点战斗结果 |
| `STAGE_CLEAR` | 小关通关 |
| `CHAPTER_CLEAR` | 大关通关 (3小关全过) |
| `RETREAT` | 撤退 |
| `LEAVE` | 暂离 |
| `FINISHED` | 本轮结束 |

### DecisiveResult 枚举

| 结果 | 说明 |
|------|------|
| `CHAPTER_CLEAR` | 大关通关 |
| `RETREAT` | 撤退 (清空进度) |
| `LEAVE` | 暂离保存 (保留进度) |
| `ERROR` | 异常退出 |

---

## 5. 舰队选择策略

### DecisiveLogic 决策引擎

决战中舰队选择由 `DecisiveLogic` 管理:

1. **choose_ships()**: 从卡池中按 level1 → level2 优先级选择舰船
2. **get_best_fleet()**: 选出最佳 6 人舰队编成
3. **should_retreat()**: 判断是否需要撤退 (可用舰船不足)
4. **should_repair()**: 根据 `repair_level` 判断是否需要修理
5. **get_advance_choice()**: 从进阶选项中选择最佳 buff

### 舰队优先级

```
Level 1 (一级舰队)  →  最高优先级，核心主力
Level 2 (二级舰队)  →  补充选择，替补
其他可用舰船        →  最低优先级
```

### 旗舰选择

按 `flagship_priority` 顺序，选择队伍中第一个可用的舰船作为旗舰。

---

## 6. 进阶用法

### 自定义 OCR 函数

决战的某些操作需要 OCR 识别 (如舰船名称):

```python
from autowsgr.vision.ocr import OCREngine

ocr = OCREngine.create("easyocr", gpu=False)

controller = DecisiveController(
    ctrl, config,
    ocr_func=ocr.recognize_single,
    image_matcher=image_matcher,
)
```

### 查询当前状态

```python
controller = DecisiveController(ctrl, config)

# 执行过程中可以查看状态
state = controller.state
print(f"小关: {state.stage}, 节点: {state.node}")
print(f"阶段: {state.phase}")
print(f"舰队血量: {state.ship_stats}")
```

### DecisiveState 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `chapter` | int | 当前章节 |
| `stage` | int | 当前小关 (1~3) |
| `node` | int | 当前节点 |
| `phase` | DecisivePhase | 当前状态机阶段 |
| `ship_stats` | list[int] | 6 舰血量 (0=正常) |
| `fleet` | FleetSelection | 当前编队选择 |
| `is_begin` | bool | 是否为本小关首次进入 |

---

## 7. 与 v1 对比

### 架构差异

| 维度 | v1 | v2 |
|------|----|----|
| 代码组织 | 单文件 `decisive_battle.py` (~500行) | 7 个模块，职责分离 |
| 配置 | `DecisiveBattleConfig` (dataclass) | `DecisiveConfig` (独立 dataclass) |
| 战斗逻辑 | 内嵌在 `DecisiveBattle` 中 | 委托 `CombatEngine` |
| 决策 | `Logic` 类内嵌 | `DecisiveLogic` 独立 |
| 状态管理 | `DecisiveStats` | `DecisiveState` + `DecisivePhase` 枚举 |
| overlay 处理 | 硬编码坐标 | `_overlay.py` 集中管理 |
| 修理 | 自定义实现 | 复用 `apply_repair()` + `BattlePreparationPage` |

### API 对比

```python
# ── v1 ──
from autowsgr.fight import DecisiveBattle
from autowsgr.scripts.main import start_script

timer = start_script('./user_settings.yaml')
db = DecisiveBattle(timer)
db.run_for_times(3)

# ── v2 ──
from autowsgr.ops.decisive import DecisiveConfig, DecisiveController

config = DecisiveConfig(chapter=6, level1=[...], level2=[...])
controller = DecisiveController(ctrl, config, image_matcher=matcher)
results = controller.run_for_times(3)
```

### 新增能力

| 能力 | v1 | v2 |
|------|----|----|
| 状态机可视化 | ❌ | ✅ 14 状态枚举 |
| 战斗引擎集成 | ❌ 硬编码 | ✅ CombatEngine |
| 运行时状态查询 | ❌ | ✅ `controller.state` |
| 单元可测试 | ❌ 依赖 timer | ✅ mock ctrl |
| 异常分类 | ❌ 通用异常 | ✅ 结构化异常 |
| overlay 检测 | ❌ 零散 | ✅ 集中管理 |

---

## 附录: 决战章节信息

| 章节 | 敌方主力 | 推荐舰种 |
|------|---------|---------|
| 1 | 驱逐/轻巡 | 驱逐、轻巡 |
| 2 | 重巡/战巡 | 重巡、战列 |
| 3 | 战列/航母 | 战列、航母 |
| 4 | 潜艇混合 | 反潜编队 |
| 5 | 航母重甲 | 航母、战列 |
| 6 | 潜艇特化 | 潜艇编队 |

> 章节信息仅供参考，实际敌方编成以游戏内数据为准。
