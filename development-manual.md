# AutoWSGR 开发手册

> 面向框架贡献者的完整开发指南。版本对应 AutoWSGR v2.2.2+

---

## 目录

1. [项目概述](#1-项目概述)
2. [开发环境搭建](#2-开发环境搭建)
3. [架构全景](#3-架构全景)
4. [基础设施层 (infra)](#4-基础设施层-infra)
5. [模拟器连接层 (emulator)](#5-模拟器连接层-emulator)
6. [视觉识别系统 (vision)](#6-视觉识别系统-vision)
7. [UI 页面系统 (ui)](#7-ui-页面系统-ui)
8. [战斗引擎 (combat)](#8-战斗引擎-combat)
9. [操作编排层 (ops)](#9-操作编排层-ops)
10. [调度与 HTTP 服务 (scheduler / server)](#10-调度与-http-服务-scheduler--server)
11. [上下文系统 (context)](#11-上下文系统-context)
12. [图像资源管理 (image_resources)](#12-图像资源管理-image_resources)
13. [代码规范与风格](#13-代码规范与风格)
14. [测试](#14-测试)
15. [构建与发布](#15-构建与发布)
16. [开发工作流](#16-开发工作流)
17. [调试与问题排查](#17-调试与问题排查)
18. [附录](#18-附录)

---

## 1. 项目概述

### 1.1 这是什么

AutoWSGR 是用 Python 与 C++ 实现的 **战舰少女R**（Warship Girls R）自动化框架。它通过视觉识别（模板匹配 + 像素特征 + OCR）感知游戏状态，以状态机驱动战斗流程，提供从设备控制到任务编排的完整自动化能力。

### 1.2 核心能力

| 能力 | 说明 |
|------|------|
| **模拟器控制** | ADB 连接、截图、触控、进程管理；支持雷电/MuMu/蓝叠 |
| **视觉识别** | 三层视觉栈：像素特征、模板匹配、OCR（EasyOCR） |
| **UI 导航** | 有向图 BFS 寻路，自动规划页面间最短路径 |
| **战斗引擎** | 有限状态机，YAML 驱动的作战计划（阵型/夜战/索敌规则） |
| **操作编排** | Runner 模式封装完整流程（导航→准备→战斗→同步） |
| **任务调度** | FIFO 多任务队列，支持远征自动检查 |
| **HTTP 服务** | FastAPI + WebSocket，提供 REST API 与实时日志 |

### 1.3 技术栈

| 领域 | 技术 |
|------|------|
| 语言 | Python ≥ 3.12, C++ (native DLL) |
| 构建 | hatchling |
| 包管理 | uv |
| 视觉 | OpenCV, EasyOCR, NumPy |
| 设备控制 | adbutils, scrcpy, av (视频解码) |
| 配置 | Pydantic v2 (frozen models) |
| 服务 | FastAPI, uvicorn, websockets |
| 代码质量 | Ruff (lint+format), codespell, pre-commit |
| 测试 | pytest, pytest-cov, pytest-xdist |

---

## 2. 开发环境搭建

### 2.1 前提条件

| 依赖 | 版本要求 | 说明 |
|------|----------|------|
| Python | ≥ 3.12, < 3.14 | 推荐 3.12.x |
| uv | ≥ 0.5 | 包管理工具 |
| Git | 任意 | 版本控制 |
| Android 模拟器 | 雷电/MuMu/蓝叠 | 需开启 ADB 调试 |

### 2.2 初始化步骤

```bash
# 克隆仓库
git clone git@github.com:OpenWSGR/AutoWSGR.git
cd AutoWSGR

# 安装依赖（含 dev 依赖）
uv sync

# 安装 pre-commit 钩子
pre-commit install
```

### 2.3 激活开发环境

```bash
# Windows
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate
```

激活后可直接运行命令，无需 `uv run` 前缀。

### 2.4 验证安装

```bash
# 运行测试
pytest

# 运行代码检查
pre-commit run --all-files

# 测试导入
python -c "import autowsgr; print(autowsgr.__version__)"
```

---

## 3. 架构全景

### 3.1 分层架构

```
┌──────────────────────────────────────────────────────┐
│  scheduler / server    调度器 & HTTP API               │
├──────────────────────────────────────────────────────┤
│  ops                   游戏操作编排                     │
├──────────────────────────────────────────────────────┤
│  combat                战斗引擎 (状态机)                │
├──────────────────────────────────────────────────────┤
│  ui                    页面识别 & 导航图                │
├──────────────────────────────────────────────────────┤
│  vision                像素特征 / 模板匹配 / OCR        │
├──────────────────────────────────────────────────────┤
│  emulator              设备控制 (截图 + 触控)           │
├──────────────────────────────────────────────────────┤
│  infra                 配置 / 日志 / 异常 / 类型        │
└──────────────────────────────────────────────────────┘
```

**核心原则**: 每一层只依赖其下方的层。跨层调用通过 `GameContext` 传递。

### 3.2 核心数据流

```
usersettings.yaml
       │
       ▼
  ConfigManager.load()          # YAML → Pydantic 校验 → UserConfig
       │
       ▼
  Launcher
    ├─ setup_logger()           # 日志初始化 (通道过滤)
    ├─ ScrcpyController.connect()  # ADB + scrcpy 连接
    ├─ EasyOCREngine.create()   # OCR 引擎初始化
    └─ GameContext(ctrl, config, ocr)
       │
       ▼
  NormalFightRunner / CampaignRunner / ...
    ├─ goto_page(MAP)           # UI 导航 (BFS 寻路)
    ├─ BattlePreparationPage    # 出征准备 (换船/补给/检测血量)
    └─ CombatEngine.fight(plan) # 战斗状态机循环
         │
         ├─ CombatRecognizer.wait_for_phase()  # 截图 → 模板+像素匹配 → 阶段
         ├─ PhaseHandler._handle_*()           # 阶段处理 (操作 + 决策)
         └─ CombatResult                       # 战果、血量、掉落
       │
       ▼
  TaskScheduler / HTTP API      # 多任务调度 / 外部接口
```

### 3.3 核心设计原则

| 原则 | 说明 |
|------|------|
| **GameContext 依赖注入** | 所有游戏层通过 `ctx: GameContext` 获取基础设施引用，不依赖全局变量 |
| **无状态操作** | UI 页面静态方法仅依赖截图数组；战斗 action 是纯函数；Ops Runner 可重复实例化 |
| **YAML 驱动配置** | 用户配置 `usersettings.yaml`、作战计划 `data/plan/*.yaml`、地图数据 `data/map/*.yaml` |
| **状态机模式** | 战斗引擎核心是 `CombatPhase` 状态机，转移图由模式大类动态构建 |
| **懒加载** | `LazyTemplate` 图像模板首次访问才加载；OCR 引擎由 Launcher 按需创建 |

### 3.4 包结构总览

```
autowsgr/
├── __init__.py              # 版本号 (__version__ = '2.2.2')
├── types.py                 # 全局枚举 (OSType, ShipType, Formation, PageName...)
├── constants/               # 舰船名数据库 (SHIPNAMES)
├── infra/                   # 配置、日志、异常、文件工具
├── emulator/                # 模拟器连接层 (ScrcpyController, 设备检测, 进程管理)
├── vision/                  # 视觉识别 (像素/模板/OCR)
├── image_resources/         # 图像模板资源 (LazyTemplate, TemplateKey)
├── ui/                      # UI 页面系统 (注册中心, 导航图, 页面控制器)
├── combat/                  # 战斗引擎 (状态机, 计划, 处理器, 识别器)
├── ops/                     # 游戏操作编排 (各类 Runner, 日常操作)
├── context/                 # 游戏上下文 (GameContext, Fleet, Ship, Resources)
├── scheduler/               # 启动器 + 任务调度器
├── server/                  # FastAPI HTTP/WebSocket 服务
└── data/                    # 静态数据 (图片模板, 地图数据, 作战计划)
```

---

## 4. 基础设施层 (infra)

**包路径**: `autowsgr/infra/`  
**职责**: 配置加载、日志、异常、文件工具、全局类型  

### 4.1 日志系统 (`logger.py`)

基于 loguru 的通道感知日志系统。

```python
from autowsgr.infra.logger import get_logger

_log = get_logger('combat')      # 获取 combat 通道的 logger
_log.info('进入战斗: {}', map_name)
```

**通道机制**:
- 每个模块通过通道名获取专属 logger
- 配置中可针对性开关特定通道的日志级别
- 日志前缀自动标注通道名

**通道命名约定**:

| 通道 | 使用模块 |
|------|----------|
| `infra` | 配置管理 |
| `emulator` | 模拟器连接 |
| `vision` | 视觉识别 |
| `vision.pixel` | 像素匹配 |
| `vision.template` | 模板匹配 |
| `ui` | 页面导航 |
| `context` | 游戏上下文 |
| `combat` | 战斗引擎 |
| `combat.engine` | 状态机转移 |
| `combat.recognition` | 战斗识别 |
| `ops` | 操作编排 |
| `ops.decisive` | 决战操作 |
| `scheduler` | 调度器 |
| `server` | HTTP 服务 |

**初始化** (`setup_logger`):
- 控制台彩色输出
- 文件输出（每次启动独立目录 `log/{timestamp}/`）
- 可选截图保存到日志目录

### 4.2 异常层级 (`exceptions.py`)

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
│   ├── NavigationError             #   导航超时
│   └── ActionFailedError           #   操作执行失败
├── GameError                       # 游戏逻辑错误
│   ├── NetworkError                #   网络错误
│   ├── DockFullError               #   船坞已满
│   └── ResourceError               #   资源不足
├── CombatError                     # 战斗系统错误
│   ├── CombatRecognitionTimeoutError  # 状态识别超时
│   └── CombatDecisionError         #   战斗决策错误
└── CriticalError                   # 致命错误
```

**设计要点**:
- 分层捕获 — 上层可按类别或精确类型捕获
- 异常携带丰富上下文（如 `CombatRecognitionTimeoutError` 携带 `candidates` 和 `timeout`）
- 使用 `ActionFailedError` 时附加 `action_name` 字段

### 4.3 类型系统 (`types.py`)

所有游戏语义枚举集中定义。

**枚举基类**:

| 基类 | 说明 |
|------|------|
| `BaseEnum` | 友好的中文错误提示 (`_missing_`) |
| `StrEnum` | `str + BaseEnum` |
| `IntEnum` | `int + BaseEnum` |

**系统枚举**:

| 枚举 | 说明 |
|------|------|
| `OSType` | windows / linux / macos (含自动检测) |
| `EmulatorType` | 雷电 / 蓝叠 / MuMu / 云手机 / 其他 |
| `OcrBackend` | easyocr / paddleocr |
| `GameAPP` | 官服 / 小米 / 应用宝 (含 package_name 映射) |

**游戏枚举**:

| 枚举 | 说明 |
|------|------|
| `ShipDamageState` | NORMAL / MODERATE / SEVERE / NO_SHIP |
| `RepairMode` | moderate_damage / severe_damage / repairing |
| `FightCondition` | 稳步前进 / 火力万岁 / ... (含 `relative_click_position`) |
| `Formation` | 单纵阵 / 复纵阵 / 轮型阵 / ... (含 `relative_position`) |
| `ShipType` | CV / BB / DD / SS ... 共 23 种 (含 `relative_position_in_destroy`) |
| `PageName` | 所有游戏页面名称枚举 |
| `ConditionFlag` | 战斗流程状态标记 (FIGHT_CONTINUE / FIGHT_END / SL / DOCK_FULL ...) |

**开发规范**: 新增游戏语义枚举时，必须在 `types.py` 中定义，不要分散在各模块。

### 4.4 配置系统 (`config.py`)

基于 Pydantic v2 的不可变配置模型层级。所有子配置标记 `frozen=True`。

**模型层级**:

```
UserConfig (顶层)
├── emulator: EmulatorConfig       # type, path, serial, process_name
├── account: AccountConfig         # game_app, account, password
├── ocr: OCRConfig                 # backend, gpu
├── log: LogConfig                 # level, root, dir, channels, show_*_debug
├── daily_automation: DailyAutomationConfig | None  # 日常自动化设置
├── decisive_battle: DecisiveConfig | None          # 决战配置
├── os_type: OSType                # 自动检测
├── delay: float                   # 延迟基本单位 (秒)
├── dock_full_destroy: bool        # 船坞满自动清空
└── destroy_ship_*                 # 解装设置
```

**配置加载流程**:

```yaml
# usersettings.yaml 示例
emulator:
  type: 雷电
account:
  game_app: 官服
```

```
YAML 文件 → ConfigManager.load() → Pydantic 校验 → UserConfig (frozen)
```

`ConfigManager.load()` 查找策略:
1. 显式指定的路径 → 直接加载
2. `None` → 自动检测当前目录下 `usersettings.yaml`
3. 文件不存在 → 使用内置默认值

### 4.5 文件工具 (`file_utils.py`)

| 函数 | 说明 |
|------|------|
| `load_yaml(path)` | 安全加载 YAML，空文件返回 `{}` |
| `save_yaml(data, path)` | 写入 YAML，自动创建父目录 |
| `resolve_plan_path(name, category)` | 4 级优先级搜索作战计划文件 |
| `merge_dicts(base, override)` | 递归深合并，不修改原字典 |

`resolve_plan_path` 搜索顺序:
1. 直接路径
2. 补全 `.yaml`
3. `autowsgr/data/plan/{category}/` 下搜索
4. 包目录 + 补全 `.yaml`

---

## 5. 模拟器连接层 (emulator)

**包路径**: `autowsgr/emulator/`  
**职责**: ADB 连接、截图、触控、模拟器进程管理  

### 5.1 双层架构

```
AndroidController (协议/接口)    截图 + 触控 + 应用管理
  └─ ScrcpyController (实现)     基于 scrcpy 协议
EmulatorProcessManager (抽象)    进程启停
  ├─ WindowsEmulatorManager      注册表路径查找
  ├─ MacEmulatorManager
  └─ LinuxEmulatorManager
detector.py                      ADB 设备自动检测
```

### 5.2 AndroidController 协议 (`controller/protocol.py`)

所有设备操作通过此协议访问，上层代码不关心具体实现。

```python
class AndroidController(Protocol):
    def connect() -> DeviceInfo
    def disconnect() -> None
    def screenshot() -> np.ndarray        # HxWx3, RGB, uint8
    def click(x: float, y: float) -> None # 归一化坐标 (0-1)
    def swipe(x1, y1, x2, y2, duration) -> None
    def key(key_code: int) -> None
    def input_text(text: str) -> None
    def is_app_running(package: str) -> bool
    def start_app(package: str, activity: str) -> None
    def stop_app(package: str) -> None
```

**坐标体系**: 所有坐标使用归一化相对值 (0.0 ~ 1.0)，内部转换为像素坐标。
- `(0.0, 0.0)` = 左上角，`(1.0, 1.0)` = 右下角
- 模板图片采集基准为 960x540

**截图格式**:
- 形状: `(H, W, 3)`，通道顺序: **RGB**（非 BGR）
- 数据类型: `uint8`

### 5.3 ScrcpyController (`controller/scrcpy.py`)

基于 scrcpy 协议的实现，通过 ADB 推送 `scrcpy-server.jar` 到设备。

**连接流程**:

```
ScrcpyController(serial, config)
       │
       ▼
  connect()
    ├─ serial 为 None → detector.resolve_serial(config)
    ├─ adb connect {serial}
    ├─ 推送 scrcpy-server.jar (从 data/bin/ 加载)
    ├─ 启动 scrcpy server 进程
    ├─ 建立视频流连接
    ├─ 启动解码线程
    └─ 等待首帧 → 返回 DeviceInfo
```

**开发注意事项**:
1. **截图性能**: `screenshot()` 返回最近一帧缓存，非即时截图。性能基准测试使用 `tools/benchmark_emulator.py`
2. **连接稳定性**: 模拟器重启后 ADB 连接可能断开，需重新 `connect()`
3. **二进制资源**: `scrcpy-server.jar` 打包在 `data/bin/` 中，随包分发

### 5.4 设备检测 (`detector.py`)

当用户未指定 ADB serial 时自动检测。

**决策优先级**:
1. `config.serial` 非空 → 直接使用
2. 在线设备恰好 1 个 → 自动采用
3. 在线设备多于 1 个，`config.type` 恰好匹配 1 个 → 自动采用
4. 无法唯一确定 → CLI 提示选择 / 抛出异常

**模拟器类型推断**: 根据 serial 格式

| serial 模式 | 推断类型 |
|------------|----------|
| `emulator-NNNN` | 雷电 |
| `127.0.0.1:16384+` | MuMu |
| `127.0.0.1:5555+` | 蓝叠 |

### 5.5 进程管理 (`os_control/`)

平台相关的模拟器进程管理。

| 平台 | 路径查找方式 | 支持的模拟器 |
|------|-------------|-------------|
| Windows | 注册表 (`winreg`) | 雷电、蓝叠、MuMu |
| macOS | 固定路径 `/Applications/` | MuMu、蓝叠 |
| Linux/WSL | 未实现 | - |

```python
class EmulatorProcessManager(ABC):
    def start() -> None       # 启动模拟器进程
    def stop() -> None        # 停止模拟器进程
    def is_running() -> bool  # 检查进程是否运行
```

---

## 6. 视觉识别系统 (vision)

**包路径**: `autowsgr/vision/`  
**职责**: 像素特征匹配、模板匹配、OCR 文字识别  

### 6.1 三层视觉栈

```
┌─────────────────────────────────────────┐
│  Layer 3: OCR                           │  文字识别 (舰船名/数字/阵型)
│    OCREngine → EasyOCREngine            │
├─────────────────────────────────────────┤
│  Layer 2: 模板匹配                       │  图片模板搜索 (按钮/图标)
│    ImageChecker + ImageTemplate         │
├─────────────────────────────────────────┤
│  Layer 1: 像素特征                       │  固定像素点颜色检测 (页面/状态)
│    PixelChecker + PixelSignature        │
└─────────────────────────────────────────┘
```

三层可独立使用，也可组合（如战斗识别器同时用模板匹配 + 像素特征双通道确认）。

### 6.2 Layer 1: 像素特征 (`pixel.py`, `matcher.py`)

通过检测截图中固定位置的像素颜色来判断页面/状态。速度极快（无需图像搜索），适用于页面识别。

```python
Color(r, g, b)                    # RGB 颜色值
  .distance(other) -> float       # 欧几里得色彩距离
  .near(other, tolerance) -> bool # 是否在容差内

PixelRule(x, y, color, tolerance) # 单像素检测规则 (相对坐标 0.0 ~ 1.0)

MatchStrategy                     # 多规则匹配策略
  ALL   — 所有规则必须匹配
  ANY   — 至少一条规则匹配
  COUNT — 匹配数量 >= threshold

PixelSignature(name, rules, strategy, threshold)
CompositePixelSignature           # 多个 PixelSignature 的 OR 组合
```

```python
# 使用示例
MAIN_PAGE_SIG = PixelSignature(
    name='main_page',
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.50, 0.85, (201, 129, 54)),
        PixelRule.of(0.75, 0.90, (34, 112, 195)),
    ],
)

screen = ctrl.screenshot()
if PixelChecker.is_matching(screen, MAIN_PAGE_SIG):
    print('当前在主页面')
```

### 6.3 Layer 2: 模板匹配 (`image_matcher.py`, `image_template.py`)

通过 OpenCV 模板匹配在截图中搜索目标图片。适用于按钮检测、图标识别。

```python
ROI(x1, y1, x2, y2)              # 感兴趣区域 (相对坐标 0-1)

ImageTemplate(
    image: np.ndarray,            # 模板图片 (HxWx3, RGB)
    name: str,                    # 模板名称
    source_resolution: (960, 540) # 采集分辨率
)

ImageRule(templates, strategy)    # 多模板 + 匹配策略
ImageSignature(rules, strategy)   # 多规则组合签名
```

**分辨率适配**: 模板采集基准 960x540。实际截图分辨率不同时自动缩放：
- 缩小: `cv2.INTER_AREA`
- 放大: `cv2.INTER_LINEAR`

### 6.4 Layer 3: OCR (`ocr.py`)

```python
class OCREngine(ABC):
    def recognize(image, allowlist='') -> list[OCRResult]
    def recognize_single(image, allowlist) -> OCRResult | None
    def recognize_number(image) -> int | None
    def recognize_ship_name(image, candidates) -> str | None

class EasyOCREngine(OCREngine):
    @classmethod
    def create(cls, gpu=False) -> EasyOCREngine  # 内部使用 easyocr
```

**舰船名模糊匹配**: 使用 Levenshtein 编辑距离在 `SHIPNAMES` 数据库中查找最接近的候选。全局替换规则 `REPLACE_RULE` 处理常见 OCR 错误。

### 6.5 开发工具

| 工具 | 路径 | 用途 |
|------|------|------|
| pixel_marker.py | `tools/pixel_marker.py` | tkinter GUI 标注 `PixelSignature` |
| debug_screenshot.py | `tools/debug_screenshot.py` | 截图 + ROI 裁剪 + OCR 测试 |

---

## 7. UI 页面系统 (ui)

**包路径**: `autowsgr/ui/`  
**职责**: 页面识别、BFS 导航寻路、页面控制器  

### 7.1 三组件设计

```
page.py              页面注册中心: register_page / get_current_page
navigation.py        导航图: NavEdge 有向图 + BFS find_path
utils.py             等待工具: wait_for_page / click_and_wait_for_page
pages/ (各页面类)     MainPage / MapPage / BathPage / ...
```

### 7.2 页面注册中心 (`page.py`)

全局注册表 `_PAGE_REGISTRY`，每个页面注册一个 `checker` 函数（基于 `PixelSignature`）。

```python
register_page(name: PageName, checker: Callable[[ndarray], bool])
get_current_page(screen: ndarray) -> str | None  # 遍历注册表
get_registered_pages() -> list[str]
```

每个页面在模块加载时自动调用 `register_page()` 完成注册。

### 7.3 页面控制器模式

每个页面遵循 **Page-per-class** 模式：

```python
class SomePage:
    # ── 静态方法 (无需设备，可独立测试) ──
    @staticmethod
    def is_current_page(screen: ndarray) -> bool

    @staticmethod
    def get_some_state(screen: ndarray) -> data

    # ── 实例方法 (需要设备) ──
    def __init__(self, ctx: GameContext)

    def navigate_to(self, target) -> None
    def go_back(self) -> None
    def click_button(self) -> None
```

**设计要点**: 静态方法仅依赖截图数组；实例方法通过 `ctx.ctrl` 执行设备操作。

### 7.4 核心页面一览

| 页面 | PageName | 职责 |
|------|----------|------|
| `MainPage` | `MAIN` | 中央枢纽，导航到各功能模块 |
| `MapPage` | `MAP` | 出击/演习/远征/战役/决战面板 |
| `BattlePreparationPage` | `BATTLE_PREP` | 舰队选择、血量检测、出征 |
| `BathPage` | `BATH` | 浴室修理 |
| `CanteenPage` | `CANTEEN` | 食堂烹饪 |
| `BuildPage` | `BUILD` | 建造/解装/开发/废弃 |
| `DecisiveBattlePage` | `DECISIVE_BATTLE` | 决战概览 + 地图控制器 |
| `MissionPage` | `MISSION` | 任务奖励领取 |
| `StartScreenPage` | `START_SCREEN` | 游戏启动画面 |

### 7.5 导航图 (`navigation.py`)

页面间的导航关系用 **有向图** 表示，每条边存储一个动作函数。

```
NavEdge(source, target, action, description)
```

**导航图拓扑**:

```
                    ┌─── MISSION
                    │
          SIDEBAR ──┼─── BUILD
          │   │     │
          │   │     ├─── INTENSIFY
          │   │     │
          │   │     └─── FRIEND
          │   │
  MAIN ───┤   ├─── EVENT_MAP
          │
          ├─── MAP ──── DECISIVE_BATTLE
          │     │
          │     └─── BATTLE_PREP
          │
          └─── BACKYARD ──┬─── BATH
                          │
                          └─── CANTEEN
```

**BFS 寻路**:

```python
find_path(source: PageName, target: PageName) -> list[NavEdge] | None
```

对 `NAV_GRAPH` 构建邻接表执行 BFS，返回最短路径。调用方逐条执行 `edge.action(ctx)` 完成导航。

**动作函数**: 使用延迟导入避免循环依赖：

```python
def _main_to_map(ctx: GameContext) -> None:
    from autowsgr.ui.main_page import MainPage
    MainPage(ctx).navigate_to(MainPage.Target.SORTIE)
```

### 7.6 等待工具 (`utils.py`)

| 函数 | 说明 |
|------|------|
| `wait_for_page(ctx, page, timeout)` | 轮询直到当前页面匹配 |
| `wait_leave_page(ctx, page, timeout)` | 轮询直到离开当前页面 |
| `click_and_wait_for_page(ctx, xy, target, timeout)` | 点击后等待目标页面 |
| `click_and_wait_leave_page(ctx, xy, page, timeout)` | 点击后等待离开页面 |
| `confirm_operation(ctx, description)` | 确认操作（通用弹窗） |

---

## 8. 战斗引擎 (combat)

**包路径**: `autowsgr/combat/`  
**职责**: 战斗状态机、作战计划、阶段处理器、视觉识别  

### 8.1 架构概览

```
CombatEngine
├── CombatRecognizer        截图 → 阶段识别 (模板+像素)
├── PhaseHandlersMixin      各阶段处理器 (操作+决策)
├── CombatPlan              作战计划 (YAML 驱动)
│   └── NodeDecision        每节点战术 (阵型/夜战/规则)
├── CombatHistory           战斗事件记录
└── state.py                CombatPhase 枚举 + 转移图
```

### 8.2 状态机核心循环 (`engine.py`)

```
fight(plan, initial_ship_stats)
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

### 8.3 CombatPhase 状态枚举 (`state.py`)

```python
class CombatPhase(Enum):
    START_FIGHT            # 点击出征后的短暂过渡
    DOCK_FULL              # 船坞已满弹窗
    PROCEED                # 继续前进/回港提示
    FIGHT_CONDITION        # 战况选择
    SPOT_ENEMY_SUCCESS     # 索敌成功
    FORMATION              # 阵型选择界面
    MISSILE_ANIMATION      # 导弹支援动画
    FIGHT_PERIOD           # 昼战/夜战进行中
    NIGHT_PROMPT           # 夜战选择
    RESULT                 # 战果评价
    GET_SHIP               # 掉落舰船
    FLAGSHIP_SEVERE_DAMAGE # 旗舰大破强制回港
    MAP_PAGE               # 回到地图 (常规战)
    EXERCISE_PAGE          # 回到演习页
    EVENT_MAP_PAGE         # 回到活动地图
```

### 8.4 模式分类与转移图

| CombatMode | 大类 | 结束页面 | 说明 |
|------------|------|----------|------|
| NORMAL | MAP | MAP_PAGE | 多节点地图 |
| EVENT | MAP | EVENT_MAP_PAGE | 活动地图 |
| BATTLE | SINGLE | RESULT | 单点战斗 |
| DECISIVE | SINGLE | RESULT | 决战 |
| EXERCISE | SINGLE | EXERCISE_PAGE | 演习 |

`build_transitions(category, end_page)` 根据模式大类动态构建转移图。

**MAP 模式典型流程**:
```
START_FIGHT → FIGHT_CONDITION → SPOT_ENEMY_SUCCESS → FORMATION
    → FIGHT_PERIOD → NIGHT_PROMPT → RESULT → GET_SHIP → PROCEED
    → FIGHT_CONDITION → ... (循环)
    → MAP_PAGE (终止)
```

**SINGLE 模式典型流程**:
```
START_FIGHT → FORMATION → FIGHT_PERIOD → NIGHT_PROMPT → RESULT
```

### 8.5 节点决策 (`plan.py`)

```python
@dataclass
class NodeDecision:
    formation: Formation           # 阵型
    night: bool                    # 夜战
    proceed: bool                  # 继续前进
    proceed_stop: RepairMode       # 停止前进破损等级
    enemy_rules: RuleEngine | None # 索敌规则
    formation_rules: RuleEngine | None  # 阵型规则
    detour: bool                   # 迂回
    SL_*: bool                     # 各种 SL 条件
```

YAML 配置示例:

```yaml
nodes:
  A:
    formation: 2          # 复纵阵
    night: true
    enemy_rules:
      - "(BB >= 2) and (CV > 0) => retreat"
```

### 8.6 阶段处理器 (`handlers.py`)

| 阶段 | 处理器 | 职责 |
|------|--------|------|
| PROCEED | `_handle_proceed()` | 检查修理需求 → 继续/回港 |
| FIGHT_CONDITION | `_handle_fight_condition()` | 选择战况 |
| SPOT_ENEMY_SUCCESS | `_handle_spot_enemy()` | 识别敌方 → 规则引擎 → 战/迂回/撤退 |
| FORMATION | `_handle_formation()` | 选择阵型 |
| FIGHT_PERIOD | `_handle_fight_period()` | 等待战斗结束 + 血量分类 |
| NIGHT_PROMPT | `_handle_night_prompt()` | 追击或撤退 |
| RESULT | `_handle_result()` | 检测评级/MVP/掉落 → 记录 |
| GET_SHIP | `_handle_get_ship()` | 跳过掉落动画 |

每个 handler 返回 `ConditionFlag`，并可能设置 `self._last_action` 供转移图分支查找。

### 8.7 战斗识别器 (`recognizer.py`)

每个 `CombatPhase` 关联一个 `PhaseSignature`：

```python
@dataclass
class PhaseSignature:
    template_key: TemplateKey | None       # 图像模板标识
    default_timeout: float = 15.0          # 超时 (秒)
    confidence: float = 0.8                # 最低置信度
    after_match_delay: float = 0.0         # 匹配后等待
    pixel_signature: PixelSignature | None # 像素特征
```

**wait_for_phase(candidates, poll_action)** 核心轮询方法:

```
while not timeout:
    screen = screenshot()
    if poll_action: poll_action(screen)
    for phase in candidates:
        if 模板匹配 or 像素匹配:
            return phase
raise CombatRecognitionTimeout
```

### 8.8 规则引擎 (`rules.py`)

作战计划中的 `enemy_rules` 和 `formation_rules` 使用规则引擎进行条件判断。

规则格式: `"(BB >= 2) and (CV > 0) => retreat"`

```python
class RuleEngine:
    @classmethod
    def from_legacy_rules(cls, rules) -> RuleEngine
    @classmethod
    def from_formation_rules(cls, rules) -> RuleEngine

    def evaluate(self, enemy_info) -> str | None
        # 返回匹配的动作 ("retreat"/"formation:1") 或 None
```

### 8.9 节点追踪器 (`node_tracker.py`)

MAP 模式下通过跟踪舰队图标在地图上的移动来确定当前节点：

```python
class NodeTracker:
    def update_ship_position(screen: ndarray)  # 检测舰队图标位置
    def update_node() -> str                   # 判断当前节点
    def reset()
```

---

## 9. 操作编排层 (ops)

**包路径**: `autowsgr/ops/`  
**职责**: 组合战斗引擎、UI 导航和上下文为完整的游戏操作流程  

### 9.1 Runner 模式

所有战斗类操作遵循统一的 Runner 模式：

```python
runner = SomeFightRunner(ctx, plan_or_config)
result = runner.run()                     # → CombatResult (单次)
results = runner.run_for_times(n)         # → list[CombatResult] (多次)
```

Runner 内部负责：页面导航 → 出征准备 → `CombatEngine.fight()` → 上下文同步。

### 9.2 战斗 Runner 一览

| Runner | 文件 | 模式 | 说明 |
|--------|------|------|------|
| `NormalFightRunner` | `normal_fight.py` | NORMAL | 多节点地图战斗 |
| `CampaignRunner` | `campaign.py` | BATTLE | 战役（每日次数限制） |
| `ExerciseRunner` | `exercise.py` | EXERCISE | 演习（遍历对手） |
| `EventFightRunner` | `event_fight.py` | EVENT | 活动战斗 |
| `DecisiveController` | `decisive/` | DECISIVE | 决战（三章推进） |

**NormalFightRunner 执行流程**:

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

### 9.3 非战斗操作

| 函数 | 文件 | 说明 |
|------|------|------|
| `ensure_game_ready(ctx, app)` | `startup.py` | 确保游戏就绪 |
| `restart_game(ctrl, app)` | `startup.py` | 完整重启周期 |
| `goto_page(ctx, target)` | `navigate.py` | BFS 寻路导航 |
| `identify_current_page(ctx)` | `navigate.py` | 截图识别当前页面 |
| `repair_in_bath(ctx, ...)` | `repair.py` | 浴室修理 |
| `collect_expedition(ctx)` | `expedition.py` | 收取远征 |
| `build_ship(ctx, recipe)` | `build.py` | 建造舰船 |
| `cook(ctx, ...)` | `cook.py` | 食堂烹饪 |
| `destroy_ships(ctx, ...)` | `destroy.py` | 解装舰船 |
| `supply_fleet(ctx, fleet_id)` | `supply.py` | 补给舰队 |
| `collect_rewards(ctx)` | `reward.py` | 领取任务奖励 |

### 9.4 决战系统 (`ops/decisive/`)

决战单独组织在子包中：

```
ops/decisive/
├── __init__.py         # DecisiveController 导出
├── base.py             # DecisiveBase 基类
├── controller.py       # DecisiveController (三章推进循环)
├── config.py           # 决战配置
├── handlers.py         # 状态处理器
├── logic.py            # DecisiveLogic (选船/阵容/技能策略)
└── state.py            # DecisiveState (章节状态机)
```

**三章推进流程**:

```
Level 1 → 出击 → 战斗 → 结算
    ↓
Level 2 → 出击 → 战斗 → 结算
    ↓
Level 3 → 出击 → 战斗 → 结算 (Boss)
```

---

## 10. 调度与 HTTP 服务 (scheduler / server)

### 10.1 启动器 (Launcher) (`scheduler/launcher.py`)

从零到就绪的引导流水线：

```
load_config()       → UserConfig (YAML → Pydantic)
    ↓
connect()           → ScrcpyController (ADB + scrcpy)
    ↓
create_ocr()        → EasyOCREngine (模型加载)
    ↓
build_context()     → GameContext(ctrl, config, ocr)
    ↓
ensure_ready(ctx)   → 确保游戏运行并在主页面
```

**一站式入口**:

```python
from autowsgr.scheduler import launch

ctx = launch('usersettings.yaml')             # 完整启动
ctx = launch('usersettings.yaml', ensure_game=False)  # 仅连接
```

**分步使用**（适合测试和自定义流程）：

```python
launcher = Launcher(config_path='usersettings.yaml')
launcher.load_config()
launcher.connect()
ctx = launcher.build_context()
launcher.ensure_ready(ctx)
```

### 10.2 任务调度器 (`scheduler/scheduler.py`)

面向脚本的简单顺序调度器。

```python
from autowsgr.scheduler import TaskScheduler, FightTask

scheduler = TaskScheduler(ctx, expedition_interval=15 * 60)
scheduler.add(FightTask(runner=my_runner, times=30))
results = scheduler.run()
```

**调度逻辑**:
1. FIFO 顺序执行每个 `FightTask`
2. 每轮检查远征间隔，超时则插入 `collect_expedition()`
3. `DOCK_FULL` 跳过当前任务剩余轮次

### 10.3 HTTP 服务 (`server/`)

基于 FastAPI 的 HTTP/WebSocket 接口。

**启动**:

```bash
uvicorn autowsgr.server.main:app --host 0.0.0.0 --port 8000
```

**路由结构**:

| 路由 | 模块 | 职责 |
|------|------|------|
| `POST /api/system/start` | `routes/system.py` | 启动系统 |
| `POST /api/system/stop` | `routes/system.py` | 停止系统 |
| `POST /api/task/*` | `routes/task.py` | 任务执行 |
| `GET /api/game/*` | `routes/game.py` | 游戏状态查询 |
| `POST /api/expedition/*` | `routes/ops.py` | 远征操作 |
| `GET /api/health` | `routes/health.py` | 健康检查 |
| `WS /ws/logs` | `ws_manager.py` | 实时日志流 |
| `WS /ws/task` | `ws_manager.py` | 任务状态更新 |

**TaskManager** (`task_manager.py`):

单任务串行执行（同一时刻只允许一个运行中任务），后台线程执行战斗，不阻塞 FastAPI 事件循环。

```
IDLE → RUNNING → COMPLETED
                → FAILED
                → STOPPED
```

### 10.4 脚本模式 vs 服务模式

| 对比项 | 脚本模式 (TaskScheduler) | 服务模式 (Server) |
|--------|--------------------------|-------------------|
| 调用方式 | Python 脚本直接调用 | HTTP/WebSocket 请求 |
| 任务执行 | 主线程同步顺序执行 | 后台线程异步执行 |
| 远征检查 | 内置定时检查 | 手动触发 |
| 进度查看 | 日志输出 | WebSocket 实时推送 |
| 停止控制 | Ctrl+C | `stop_task()` 优雅停止 |

---

## 11. 上下文系统 (context)

**包路径**: `autowsgr/context/`  
**职责**: GameContext 聚合基础设施引用与运行时状态  

### 11.1 GameContext (`game_context.py`)

```python
@dataclass
class GameContext:
    # ── 基础设施引用 (构造时注入) ──
    ctrl: AndroidController       # 设备控制器
    config: UserConfig            # 用户配置 (只读)
    ocr: OCREngine                # OCR 引擎实例

    # ── 游戏运行时状态 ──
    resources: Resources          # 燃弹钢铝 + 道具
    fleets: list[Fleet]           # 4 支舰队
    expeditions: ExpeditionQueue  # 远征队列
    build_queue: BuildQueue       # 建造队列
    ship_registry: dict[str, Ship]  # 舰船注册表
    current_page: PageName | None  # 当前页面

    # ── 每日计数器 ──
    dropped_ship_count: int       # 当天掉落舰船数
    dropped_loot_count: int       # 当天掉落胖次数
    quick_repair_used: int        # 快修消耗

    # ── 控制信号 ──
    stop_event: threading.Event   # 停止信号
```

### 11.2 组件模型

**Fleet** (`fleet.py`):

```python
@dataclass
class Fleet:
    fleet_id: int               # 编号 1-4
    ships: list[Ship]           # 最多 6 艘
    # Properties: size, damage_states, has_severely_damaged, needs_repair
```

**Ship** (`ship.py`):

```python
@dataclass
class Ship:
    name: str
    ship_type: ShipType | None
    level: int | None
    health: int | None
    max_health: int | None
    damage_state: ShipDamageState
    locked: bool = True
    # Properties: health_ratio, is_repairing, available, needs_repair(mode)
```

**Resources** (`resources.py`): fuel, ammo, steel, aluminum, diamond, fast_repair, fast_build, ship_blueprint, equipment_blueprint

### 11.3 战斗上下文同步

**战前 `sync_before_combat()`**:
- 同步舰队编成、舰船血量状态
- 更新每日计数器（掉落舰船数、战利品数）
- 同步到 `ship_registry`

**战后 `sync_after_combat()`**:
- 更新舰队战后血量
- 统计掉落

---

## 12. 图像资源管理 (image_resources)

**包路径**: `autowsgr/image_resources/`  
**职责**: 图像模板的集中管理与懒加载  

### 12.1 TemplateKey 枚举 (`keys.py`)

所有图像模板的唯一标识键，按功能分组：

| 分组 | 示例 |
|------|------|
| 战斗 | PROCEED, DOCK_FULL, FORMATION, FIGHT_PERIOD, RESULT, GET_SHIP |
| 结果等级 | RESULT_GRADE_S, RESULT_GRADE_A, ..., RESULT_GRADE_SS |
| 操作 | COOK_BUTTON, BUILD_BUTTON, INTENSIFY_BUTTON |
| 通用 | REPAIR_BUTTON, SUPPLY_BUTTON |

### 12.2 模板访问器

```python
# 战斗模板
CombatTemplates.FORMATION  → ImageTemplate
CombatTemplates.RESULT     → ImageTemplate

# 操作模板
Templates.Cook.COOK_BUTTON → ImageTemplate
Templates.Build.BUILD_BUTTON → ImageTemplate
```

### 12.3 LazyTemplate 懒加载 (`_lazy.py`)

模板图片在首次访问时从 `data/images/` 目录加载，避免启动时一次性加载所有图片。

```python
class LazyTemplate:
    def __get__(self, obj, type) -> ImageTemplate:
        # 首次: 从磁盘读取 → 转 RGB → 缓存
        # 后续: 直接返回缓存
```

### 12.4 图片目录结构

```
data/images/
├── combat/       # 战斗状态模板 (PROCEED, FORMATION, RESULT...)
├── combat/result # 战果等级 (S, A, B, C, D, SS)
├── build/        # 建造页面
├── choose_ship/  # 选船页面
├── cook/         # 食堂
├── common/       # 公共元素
├── decisive/     # 决战
├── error/        # 错误弹窗
├── event/        # 活动相关
├── reward/       # 奖励领取
└── ui/           # 通用 UI 元素
```

**开发规范**: 新增模板图片时，同时在 `keys.py` 添加 `TemplateKey`、在对应访问器类中添加属性、将图片放入 `data/images/` 对应子目录。

---

## 13. 代码规范与风格

### 13.1 Python 版本与工具

| 项目 | 要求 |
|------|------|
| Python | 3.12+ |
| 格式化 | Ruff (已覆盖 isort / black) |
| Lint | Ruff |
| 拼写检查 | codespell |
| 类型检查 | 运行时使用 `TYPE_CHECKING` 隔离 |

### 13.2 编码规范

| 规则 | 要求 |
|------|------|
| 行宽 | 100 字符 |
| 引号 | 单引号 (字符串)，双引号 (docstring) |
| 相对导入 | 禁止 (`ban-relative-imports = all`) |
| 类型注解 | 必须标注参数和返回值类型 |
| 文档字符串 | 使用 PEP 257 风格 |

### 13.3 Ruff 配置要点

完整配置见 `pyproject.toml` 的 `[tool.ruff]` 部分，主要启用规则：

- **FAST**: FastAPI 规则
- **ANN**: 类型注解规则
- **B**: flake8-bugbear
- **I**: isort
- **SIM**: flake8-simplify
- **PERF**: 性能规则
- **TRY**: tryceratops (异常处理)
- **PL**: Pylint
- **FURB**: refurb

### 13.4 日志规范

```python
from autowsgr.infra.logger import get_logger

_log = get_logger('module_name')  # 模块级私有变量

_log.debug('调试信息: {}', variable)   # 使用 {} 格式化，不用 f-string
_log.info('操作信息')
_log.warning('警告信息')
_log.error('错误信息')
```

### 13.5 异常处理规范

```python
# 精确捕获
try:
    result = engine.fight(plan, stats)
except CombatRecognitionTimeoutError as e:
    _log.warning('超时: {}', e)
except DockFullError:
    _log.warning('船坞已满')

# 分层捕获
except EmulatorError:
    # 捕获所有模拟器异常
```

### 13.6 模块组织

```
module/
├── __init__.py     # 公开 API 导出
├── core.py         # 核心逻辑
└── utils.py        # 辅助函数
```

**导入顺序** (由 Ruff isort 强制):
1. `from __future__ import annotations`
2. 标准库
3. 第三方库
4. 本地模块（使用绝对导入）

---

## 14. 测试

### 14.1 测试工具

| 工具 | 用途 |
|------|------|
| pytest | 主测试框架 |
| pytest-cov | 覆盖率报告 |
| pytest-xdist | 并行测试 |

### 14.2 测试目录结构

```
testing/
└── ui/          # UI 层测试
```

### 14.3 运行测试

```bash
# 运行所有测试
pytest

# 指定文件
pytest testing/ui/

# 带覆盖率
pytest --cov=autowsgr

# 并行运行
pytest -n auto
```

### 14.4 编写测试

**测试类型**:
- **单元测试**: 测试独立组件（如 `NodeDecision.from_dict()`）
- **UI 测试**: 测试页面识别静态方法（注入 mock 截图）
- **集成测试**: 测试完整流程（如 `Launcher.build_context()` 不依赖真实设备）

**测试模式**:
- 静态方法（如 `is_current_page(screen)`）仅依赖 `np.ndarray`，可独立测试
- 使用 `unittest.mock` 注入 mock 设备控制器

### 14.5 Pre-commit 检查

提交前务必运行：

```bash
pre-commit run --all-files
```

自动运行:
- Ruff lint + format
- codespell 拼写检查

---

## 15. 构建与发布

### 15.1 构建系统

| 项目 | 工具 |
|------|------|
| Build backend | hatchling |
| 依赖管理 | uv |
| 版本号 | `autowsgr/__init__.py` 中的 `__version__` |

### 15.2 构建

```bash
uv build
```

包数据（图片、YAML、JAR 等）位于 `autowsgr/data/`，由 hatchling 自动包含。

### 15.3 依赖管理

核心依赖在 `pyproject.toml` 的 `[project.dependencies]` 中：

```
rich, opencv-python-headless, loguru, keyboard,
easyocr>=1.7.1, adbutils>=2.0,<3.0, av>=12.0,
pydantic>=2.0,<3.0, fastapi>=0.100.0,
uvicorn[standard]>=0.23.0, websockets>=11.0,
autowsgr_native>=0.2.0
```

开发依赖在 `[dependency-groups] dev` 中：
```
pre-commit, pytest>=8.0, pytest-cov, pytest-xdist
```

### 15.4 版本号

```python
# autowsgr/__init__.py
__version__ = '2.2.2'
```

由 hatchling 从文件中读取。

---

## 16. 开发工作流

### 16.1 分支策略

- `main`: 稳定分支，PR 合入
- `feat/*`: 新功能
- `fix/*`: 修复

### 16.2 提交规范

使用约定式提交 (Conventional Commits)：

```
<type>(<scope>): <简短描述>

<正文>
```

**常用类型**:

| 类型 | 说明 |
|------|------|
| `feat` | 新功能 |
| `fix` | 修复 |
| `build` | 构建系统或依赖变更 |
| `docs` | 文档 |
| `style` | 不影响代码逻辑的格式调整 |
| `refactor` | 重构 |
| `test` | 测试 |

**示例**:

```
feat(combat): 添加导弹支援阶段识别

- 新增 MISSILE_ANIMATION 阶段处理
- 更新状态转移图支持新阶段
```

### 16.3 PR 流程

1. 创建 feature/fix 分支
2. 实现改动
3. 运行测试: `pytest`
4. 运行 pre-commit: `pre-commit run --all-files`
5. 提交 PR 到 main

**注意**: 代码自动审查使用 [Lunar](https://github.com/0xWelt/Lunar)，所有 PR 有概率触发 AI 评论。

### 16.4 添加新功能的一般步骤

1. **理解现有架构**: 阅读相关模块的架构文档 (`docs/architecture/`)
2. **确定所属层**: 新功能属于哪一层（infra/emulator/vision/ui/combat/ops/scheduler）
3. **定义类型**: 在 `types.py` 中添加所需枚举
4. **实现核心逻辑**: 按该层的模式编写代码
5. **集成**: 如果是战斗相关，注册新 `CombatPhase`；如果是 UI 相关，注册新 `PageName` 和导航边
6. **测试**: 添加单元测试
7. **文档**: 更新相关架构文档和使用文档

### 16.5 添加新作战计划

1. 创建 YAML 文件到 `data/plan/normal_fight/` 或 `data/plan/event/`
2. 遵循现有文件格式
3. 可选添加地图数据到 `data/map/`

---

## 17. 调试与问题排查

### 17.1 日志调优

通过 `usersettings.yaml` 控制日志输出：

```yaml
log:
  level: DEBUG                     # 全局级别
  show_combat_state_debug: false   # 静默战斗状态机转移日志
  show_vision_debug: true          # 开启视觉调试
  channels:                        # 通道级别覆盖
    "emulator": "INFO"             # 静默 emulator 通道
    "vision.pixel": "TRACE"        # 像素匹配 TRACE 级别
```

### 17.2 常见问题排查

| 问题 | 排查方法 |
|------|---------|
| 连接失败 | 检查 ADB 状态 (`adb devices`)，确认模拟器 ADB 调试已开启 |
| 页面识别卡住 | 使用 `debug_screenshot.py` 检查当前截图，验证 PixelSignature 是否正确 |
| 战斗识别超时 | 调大 `default_timeout`，检查模板图片是否正确匹配 |
| 导航失败 | 验证 `NavGraph` 中目标页面是否存在可达路径 |
| OCR 识别错误 | 检查 ROI 区域是否正确，调整 allowlist，更新 `REPLACE_RULE` |

### 17.3 调试工具

```bash
# 截图 + ROI 裁剪 + OCR
python tools/debug_screenshot.py --roi 0.8,0.8,0.9,0.9 --allowlist "0-9"

# 标注 PixelSignature
python tools/pixel_marker.py --serial 127.0.0.1:5555

# 模拟器性能基准测试
python tools/benchmark_emulator.py

# 更新舰船名称数据库
python tools/update_shipnames.py
```

### 17.4 保存调试截图

在 `usersettings.yaml` 中启用：

```yaml
log:
  show_vision_debug: true
```

`Launcher` 初始化日志系统时设置 `save_images=True` 即可在日志目录保存调试截图。

### 17.5 模拟测试环境

在不连接模拟器的情况下测试某些功能：

```python
# 使用 mock 设备控制器
from unittest.mock import MagicMock
from autowsgr.context import GameContext
from autowsgr.infra.config import UserConfig

mock_ctrl = MagicMock()
ctx = GameContext(ctrl=mock_ctrl, config=UserConfig(), ocr=MagicMock())

# 设置截图返回值
import numpy as np
mock_ctrl.screenshot.return_value = np.zeros((540, 960, 3), dtype=np.uint8)
```

---

## 18. 附录

### 18.1 关键文档索引

| 文档 | 内容 |
|------|------|
| [架构概述](architecture/README.md) | 整体架构、分层设计、核心数据流 |
| [战斗引擎](architecture/combat-engine.md) | 状态机、计划、处理器、识别器 |
| [模拟器连接](architecture/emulator.md) | AndroidController 协议、ScrcpyController、设备检测 |
| [UI 系统](architecture/ui.md) | 页面注册中心、导航图 BFS、页面控制器 |
| [视觉系统](architecture/vision.md) | 三层视觉栈、图像资源管理 |
| [上下文与配置](architecture/context-and-config.md) | GameContext、UserConfig 模型层级 |
| [操作层](architecture/ops.md) | 各类 Runner、非战斗操作、战斗同步 |
| [调度与服务](architecture/scheduler-and-server.md) | Launcher、TaskScheduler、FastAPI 服务 |
| [基础设施](architecture/infra.md) | 日志、异常、文件工具、类型系统 |

### 18.2 常见模式速查

| 场景 | 模式 | 参考 |
|------|------|------|
| 新游戏操作 | Runner 模式 | `NormalFightRunner` |
| 新页面识别 | Page-per-class + 注册 | `MainPage` |
| 新视觉特征 | PixelSignature 或 ImageSignature | `main_page.constants.py` |
| 新状态机 | CombatPhase + build_transitions | `state.py` |
| 新配置项 | Pydantic frozen model | `config.py` |
| 新调度任务 | FightTask + Runner | `scheduler.py` |

### 18.3 依赖关系速查

```
infra ← 所有层
emulator ← vision, ui, ops, combat
vision ← ui, combat
ui ← ops, combat
combat ← ops
context ← ops, combat, scheduler
scheduler → ops → combat → ui → vision → emulator → infra
```

### 18.4 项目配置文件

| 文件 | 用途 |
|------|------|
| `pyproject.toml` | 项目元数据、构建配置、Ruff 规则、pytest 配置 |
| `uv.lock` | 依赖锁定文件 |
| `renovate.json` | 自动依赖更新配置 |
| `.pre-commit-config.yaml` | pre-commit 钩子配置 |
| `usersettings.yaml` | 用户配置文件（不提交到 Git） |

---

> 本手册与 `docs/architecture/` 下的模块详细文档配合使用。开始贡献前，建议先阅读对应模块的架构文档。
