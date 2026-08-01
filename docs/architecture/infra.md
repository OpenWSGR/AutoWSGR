# 基础设施 (Infra)

> 返回 [架构概述](README.md)

本文档描述 AutoWSGR 的底层基础设施：日志、异常、文件工具、类型系统和静态数据。

---

## 日志系统

**文件**: `autowsgr/infra/logger.py`

基于 loguru 的通道感知日志系统。

### 初始化

```python
from autowsgr.infra.logger import setup_logger, get_logger

setup_logger(
    log_dir='./log',
    level='INFO',
    save_images=True,
    channels=['combat', 'vision'],  # 仅启用指定通道，None = 全部启用
)
```

`setup_logger` 在 Launcher 启动时调用，配置来自 `UserConfig.log`：

| 参数           | 说明                                    |
|----------------|-----------------------------------------|
| `log_dir`      | 日志目录（自动创建带时间戳的子目录）      |
| `level`        | 全局日志级别                             |
| `save_images`  | 是否保存截图到日志目录                   |
| `channels`     | 通道白名单 (`None` = 全部启用)           |

### 通道日志

```python
_log = get_logger('combat')     # 获取 combat 通道 logger
_log.info('进入战斗: {}', map_name)
```

每个模块通过 `get_logger(channel)` 获取专属 logger。通道机制允许：
- 按模块过滤日志输出
- 在配置中针对性开关特定通道
- 日志前缀自动标注通道名

### 日志输出

- 控制台: 彩色输出
- 文件: 每次启动独立目录 `log/{timestamp}/`
- 截图保存: `save_images=True` 时，配合 `save_screenshot()` 将调试截图保存到日志目录

---

## 异常层级

**文件**: `autowsgr/infra/exceptions.py`

所有异常继承自 `AutoWSGRError`，按模块分组：

```
AutoWSGRError
├── ConfigError                     # 配置错误
├── EmulatorError                   # 模拟器操作失败
│   ├── EmulatorConnectionError     #   连接失败
│   └── EmulatorNotFoundError       #   未检测到模拟器
├── VisionError                     # 视觉识别错误
│   └── OCRError                    #   OCR 识别失败
├── UIError                         # UI 操作错误
│   ├── PageNotFoundError           #   无法识别当前页面
│   ├── NavigationError             #   导航失败 (未在树中体现但存在于代码)
│   └── ActionFailedError           #   UIAction 执行失败
├── GameError                       # 游戏逻辑错误
│   ├── NetworkError                #   网络错误 (断线)
│   ├── DockFullError               #   船坞已满
│   └── ResourceError               #   资源不足
├── CombatError                     # 战斗系统错误
│   ├── CombatRecognitionTimeoutError  # 状态识别超时
│   └── CombatDecisionError         #   战斗决策错误
└── CriticalError                   # 致命错误
```

### 设计原则

- **分层捕获**: 上层可以按类别捕获 (`except EmulatorError`) 或精确捕获 (`except EmulatorConnectionError`)
- **信息丰富**: 如 `CombatRecognitionTimeoutError` 携带 `candidates` 和 `timeout` 属性
- **ActionFailedError**: 携带 `action_name` 字段，便于定位失败的具体操作

### 使用模式

```python
from autowsgr.infra.exceptions import DockFullError, CombatRecognitionTimeoutError

try:
    engine.fight(plan, ship_stats)
except CombatRecognitionTimeoutError as e:
    log.error('超时: {}s, 候选状态: {}', e.timeout, e.candidates)
except DockFullError:
    log.warning('船坞已满, 触发自动解装')
```

---

## 文件工具

**文件**: `autowsgr/infra/file_utils.py`

### YAML 操作

```python
from autowsgr.infra.file_utils import load_yaml, save_yaml

data = load_yaml('config.yaml')       # → dict (空文件返回 {})
save_yaml(data, 'output.yaml')        # 自动创建父目录
```

- `load_yaml`: 使用 `yaml.safe_load`，空文件返回 `{}`
- `save_yaml`: 自动 `mkdir(parents=True)`，`allow_unicode=True`

### 策略文件查找

```python
from autowsgr.infra.file_utils import resolve_plan_path

path = resolve_plan_path('8-5', category='normal_fight')
```

4 级优先级搜索：

1. 直接路径 → `8-5` 作为路径存在
2. 补全 `.yaml` → `8-5.yaml` 存在
3. 包数据目录 → `autowsgr/data/plan/normal_fight/8-5`
4. 包数据目录 + `.yaml` → `autowsgr/data/plan/normal_fight/8-5.yaml`

### 字典深合并

```python
from autowsgr.infra.file_utils import merge_dicts

result = merge_dicts(base_dict, override_dict)
```

递归合并，`override` 值优先，不修改原字典。

---

## 类型系统

**文件**: `autowsgr/types.py`

所有游戏语义枚举集中定义，供各层引用。

### 枚举基类

| 基类        | 说明                                    |
|-------------|----------------------------------------|
| `BaseEnum`  | 提供友好的中文报错 (`_missing_`)         |
| `StrEnum`   | `str + BaseEnum`                        |
| `IntEnum`   | `int + BaseEnum`                        |

### 系统枚举

| 枚举            | 值示例                        | 说明          |
|-----------------|-------------------------------|---------------|
| `OSType`        | `windows/linux/macos`         | 操作系统类型  |
| `EmulatorType`  | `雷电/蓝叠/MuMu/云手机/其他` | 模拟器类型    |
| `GameAPP`       | `官服/小米/应用宝`             | 游戏渠道服    |

`EmulatorType` 提供两个平台感知方法：
- `default_emulator_name(os_type)`: 返回默认 ADB serial
- `auto_emulator_path(os_type)`: 从注册表/文件系统自动查找安装路径

`GameAPP.package_name`: 返回 Android 包名。

### 游戏枚举

| 枚举                | 值                              | 说明           |
|---------------------|---------------------------------|----------------|
| `ShipDamageState`   | `NORMAL/MODERATE/SEVERE/NO_SHIP` | 舰船血量状态  |
| `RepairMode`        | `moderate_damage/severe_damage`  | 修理策略      |
| `FightCondition`    | `稳步前进/火力万岁/...`          | 战况选择      |
| `Formation`         | `单纵阵/复纵阵/轮型阵/...`       | 阵型          |
| `SearchEnemyAction` | `no_action/retreat/detour/...`   | 索敌后动作    |
| `ShipType`          | `CV/DD/SS/...` (23 种)          | 舰种          |

`FightCondition` 和 `Formation` 都携带 `relative_position` 属性，直接映射到屏幕点击坐标。

### 数据类

```python
@dataclass
class FleetSelection:
    name: str                            # 舰船或技能名称
    cost: int                            # 购买所需分数
    click_position: tuple[float, float]  # 卡片点击位置
```

### ConditionFlag

战斗结果标志枚举，用于调度器判断任务继续/中断。

---

## 静态数据

### 舰船名称

**文件**: `autowsgr/constants/shipnames.py` + `autowsgr/data/shipnames.yaml`

- `shipnames.yaml`: 舰船中文名 ↔ 内部 ID 映射
- `shipnames.py`: 加载 YAML 并提供查询函数
- `tools/update_shipnames.py`: 从游戏数据源更新 YAML

### 任务数据

**文件**: `autowsgr/data/missions.yaml`

日常/周常任务定义。

### 地图数据

**目录**: `autowsgr/data/map/`

各章节地图的节点信息、路线数据。

### 图像资源

**目录**: `autowsgr/data/images/`

模板图片，供视觉识别使用。详见 [vision.md](vision.md)。

---

## 配置系统

**文件**: `autowsgr/infra/config.py`

Pydantic v2 配置模型和加载逻辑。详流程见 [context-and-config.md](context-and-config.md)。

简要：
- `ConfigManager.load(path)` → `UserConfig`
- 6 个子配置模型: `EmulatorConfig/LogConfig/OcrConfig/AccountConfig/CombatConfig/DecisiveBattleConfig`
- YAML 加载 → Pydantic 校验 → 不可变配置对象

---

## 与其他模块的关系

- **被依赖**: 所有上层模块都依赖 infra 层
- 日志: 全框架使用 `get_logger(channel)`
- 异常: 各层抛出对应的异常子类
- 类型: `types.py` 的枚举贯穿配置/战斗/UI 各层
- 文件工具: 计划加载、配置加载都使用 `file_utils`
