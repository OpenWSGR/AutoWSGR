# AutoWSGR 架构概述

本文档面向框架开发者，描述 AutoWSGR 后端的整体架构、分层设计与核心数据流。

> **用户使用文档** 见 [docs/usage/](../usage/)。

---

## 分层架构

```
┌─────────────────────────────────────────────────────┐
│  scheduler / server    调度器 & HTTP API             │
├─────────────────────────────────────────────────────┤
│  ops                   游戏操作编排                   │
├─────────────────────────────────────────────────────┤
│  combat                战斗引擎 (状态机)              │
├─────────────────────────────────────────────────────┤
│  ui                    页面识别 & 导航图              │
├─────────────────────────────────────────────────────┤
│  vision                像素特征 / 模板匹配 / OCR      │
├─────────────────────────────────────────────────────┤
│  emulator              设备控制 (截图 + 触控)         │
├─────────────────────────────────────────────────────┤
│  infra                 配置 / 日志 / 异常 / 类型      │
└─────────────────────────────────────────────────────┘
```

每一层只依赖其下方的层。跨层调用通过 `GameContext` 传递。

| 层            | 包路径                | 职责                            | 细节文档                                     |
|---------------|----------------------|---------------------------------|----------------------------------------------|
| **infra**     | `autowsgr/infra/`    | 配置加载、日志、异常、文件工具、全局类型  | [infra.md](infra.md)                         |
| **emulator**  | `autowsgr/emulator/` | ADB 连接、截图、触控、进程管理         | [emulator.md](emulator.md)                   |
| **vision**    | `autowsgr/vision/`   | 像素匹配、模板匹配、OCR 文字识别       | [vision.md](vision.md)                       |
| **ui**        | `autowsgr/ui/`       | 游戏页面识别、导航图 BFS 寻路          | [ui.md](ui.md)                               |
| **combat**    | `autowsgr/combat/`   | 战斗状态机、阶段识别、作战计划          | [combat-engine.md](combat-engine.md)         |
| **ops**       | `autowsgr/ops/`      | 战斗 Runner、远征、修理、建造等操作     | [ops.md](ops.md)                             |
| **scheduler** | `autowsgr/scheduler/` | 启动器、任务调度                     | [scheduler-and-server.md](scheduler-and-server.md) |
| **server**    | `autowsgr/server/`   | FastAPI HTTP/WebSocket 接口       | [scheduler-and-server.md](scheduler-and-server.md) |
| **context**   | `autowsgr/context/`  | 游戏上下文 (状态聚合)                | [context-and-config.md](context-and-config.md) |

---

## 核心数据流

一次典型的"启动 → 战斗 → 收集结果"流程：

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

---

## 关键设计原则

### 1. GameContext 依赖注入

所有游戏层代码通过 `ctx: GameContext` 获取基础设施引用（`ctrl` / `config` / `ocr`），不依赖全局变量。这使得单元测试可以注入 mock 对象。

```python
@dataclass
class GameContext:
    ctrl: AndroidController     # 设备控制器
    config: UserConfig          # 用户配置 (只读)
    ocr: OCREngine              # OCR 引擎
    resources: Resources        # 运行时: 资源
    fleets: list[Fleet]         # 运行时: 舰队 (1-4)
    ...
```

### 2. 无状态操作

- **UI 页面类**：静态方法 `is_current_page(screen)` 做识别，实例方法做操作
- **战斗 action 函数**：纯函数 `(device, data) -> None`，无副作用
- **Ops Runner**：可重复实例化，每次 `run()` 独立执行

### 3. YAML 驱动配置

- 用户配置：`usersettings.yaml` → Pydantic `UserConfig`
- 作战计划：`data/plan/*.yaml` → `CombatPlan` + `NodeDecision`
- 地图数据：`data/map/*.yaml` → `MapNodeData`

### 4. 状态机模式

战斗引擎核心是 `CombatPhase` 状态机，转移图由 `build_transitions(ModeCategory, end_page)` 动态构建。每步循环：截图 → 识别阶段 → 查转移表 → 执行处理器 → 返回标志位。

### 5. 懒加载

- `LazyTemplate`：图像模板在首次访问时从磁盘加载
- `OCREngine`：由 `Launcher` 按需创建
- 模块级延迟导入：UI 导航动作函数内部 import 页面类，避免循环依赖

---

## 项目目录速查

```
autowsgr/
├── __init__.py              # 版本号 (__version__)
├── types.py                 # 全局枚举 (OSType, ShipType, Formation, ...)
├── constants/               # 舰船名数据库 (SHIPNAMES)
├── infra/                   # 配置、日志、异常、文件工具
│   ├── config.py            #   UserConfig Pydantic 模型层级
│   ├── logger.py            #   loguru 通道日志系统
│   ├── exceptions.py        #   异常层级树
│   └── file_utils.py        #   YAML/路径工具
├── emulator/                # 模拟器连接层
│   ├── controller/          #   ScrcpyController (AndroidController 实现)
│   ├── os_control/          #   进程管理 (Windows/Mac/Linux)
│   └── detector.py          #   设备自动检测
├── vision/                  # 视觉识别
│   ├── pixel.py             #   像素特征数据模型
│   ├── matcher.py           #   PixelChecker 引擎
│   ├── image_matcher.py     #   ImageChecker 模板匹配引擎
│   ├── ocr.py               #   OCREngine 抽象 + EasyOCR
│   ├── roi.py               #   ROI 区域定义
│   └── image_template.py    #   ImageTemplate 数据模型
├── image_resources/         # 图像模板资源
│   ├── keys.py              #   TemplateKey 枚举
│   ├── combat.py            #   CombatTemplates (战斗模板)
│   ├── ops.py               #   Templates (操作模板)
│   └── _lazy.py             #   LazyTemplate 懒加载
├── ui/                      # UI 页面系统
│   ├── page.py              #   页面注册中心
│   ├── navigation.py        #   导航图 + BFS 寻路
│   ├── utils.py             #   等待/点击工具
│   ├── main_page.py         #   主页面
│   ├── map/                 #   地图页面
│   ├── battle/              #   出征准备页
│   ├── decisive/            #   决战 UI
│   └── ...                  #   其他页面
├── combat/                  # 战斗引擎
│   ├── engine.py            #   CombatEngine 状态机主循环
│   ├── state.py             #   CombatPhase 枚举 + 转移图
│   ├── plan.py              #   CombatPlan + NodeDecision + CombatMode
│   ├── handlers.py          #   PhaseHandlersMixin (阶段处理器)
│   ├── recognizer.py        #   CombatRecognizer (视觉识别器)
│   ├── recognition.py       #   敌舰/阵型/掉落识别
│   ├── actions.py           #   战斗操作函数 (点击/检测)
│   ├── rules.py             #   RuleEngine (索敌规则)
│   ├── history.py           #   CombatHistory + CombatResult
│   └── node_fusion/         #   融合追踪、船位、敌情与历史回放
├── ops/                     # 游戏操作
│   ├── normal_fight.py      #   NormalFightRunner
│   ├── campaign.py          #   CampaignRunner
│   ├── exercise.py          #   ExerciseRunner
│   ├── event_fight.py       #   EventFightRunner
│   ├── decisive/            #   DecisiveController
│   ├── startup.py           #   启动/重启游戏
│   ├── navigate.py          #   goto_page / identify_current_page
│   ├── repair.py            #   澡堂修理
│   ├── expedition.py        #   远征收取
│   ├── build.py             #   建造/收船
│   ├── cook.py              #   食堂烹饪
│   ├── destroy.py           #   解装
│   └── supply.py            #   补给
├── context/                 # 游戏上下文
│   ├── game_context.py      #   GameContext 核心类
│   ├── fleet.py             #   Fleet 模型
│   ├── ship.py              #   Ship 模型
│   ├── resources.py         #   Resources 模型
│   ├── expedition.py        #   ExpeditionQueue
│   └── build.py             #   BuildQueue
├── scheduler/               # 调度器
│   ├── launcher.py          #   Launcher 启动链 + launch()
│   └── scheduler.py         #   TaskScheduler
├── server/                  # HTTP 服务
│   ├── main.py              #   FastAPI 应用
│   ├── task_manager.py      #   TaskManager
│   ├── ws_manager.py        #   WebSocket 管理
│   ├── schemas.py           #   请求/响应模型
│   └── routes/              #   路由模块
└── data/                    # 静态数据
    ├── missions.yaml        #   任务数据库
    ├── shipnames.yaml       #   舰船图鉴
    ├── images/              #   模板图片
    ├── map/                 #   地图节点数据
    ├── plan/                #   作战计划 (YAML)
    └── bin/                 #   二进制资源 (scrcpy-server 等)
```

---

## 细节文档索引

| 文档                                                | 内容                                               |
|-----------------------------------------------------|----------------------------------------------------|
| [context-and-config.md](context-and-config.md)      | GameContext 结构、UserConfig 模型层级、配置加载流程    |
| [emulator.md](emulator.md)                          | AndroidController 协议、ScrcpyController、设备检测   |
| [vision.md](vision.md)                              | 三层视觉栈（像素/模板/OCR）、图像资源管理             |
| [ui.md](ui.md)                                      | 页面注册中心、导航图 BFS、页面控制器                   |
| [combat-engine.md](combat-engine.md)                | 战斗状态机、CombatPlan、阶段处理器、视觉识别器         |
| [ops.md](ops.md)                                    | 战斗 Runner、非战斗操作、启动与导航                   |
| [scheduler-and-server.md](scheduler-and-server.md)  | Launcher 启动链、TaskScheduler、FastAPI HTTP 服务     |
| [infra.md](infra.md)                                | 通道日志、异常层级、文件工具、枚举类型、数据文件        |
