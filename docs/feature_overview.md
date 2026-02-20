# AutoWSGR v2 功能总览与新旧对比

> 本文档全面整理 AutoWSGR v2 (`autowsgr/`) 已有功能，并与旧版 v1 (`autowsgr_legacy/`) 逐项对比。
>
> 更新日期: 2026-02-20

---

## 目录

- [1. 架构对比概览](#1-架构对比概览)
- [2. 基础设施层](#2-基础设施层-infralegacy-各处散落)
- [3. 视觉层](#3-视觉层-visionlegacy-各处散落)
- [4. 模拟器层](#4-模拟器层-emulatorlegacy-timercontrollers)
- [5. UI 控制层](#5-ui-控制层-uilegacy-constantsuitimer)
- [6. 战斗系统](#6-战斗系统-combatlegacy-fight)
- [7. 游戏操作层](#7-游戏操作层-opslegacy-gamefight)
- [8. 尚未迁移的功能](#8-尚未迁移的功能)
- [9. 新增功能](#9-新增功能v1-不具备)
- [10. 模块统计](#10-模块统计)

---

## 1. 架构对比概览

### v1 架构（单体）

```
Timer (God Object)
  ├── AndroidController (直接继承)
  ├── OSController
  ├── OCR Backend
  ├── UI 树 (WSGR_UI 全局单例)
  ├── Port 母港状态 (全局可变)
  └── 所有游戏操作方法 (全部挂在 Timer 上)
```

Timer 是核心上下文对象，同时扮演：设备控制器、OCR 引擎、UI 导航器、状态管理器、配置容器。
所有功能模块通过 `timer` 参数串联，形成**强耦合**的单体架构。

### v2 架构（分层解耦）

```
┌─────────────────────────────────────────────────┐
│  ops (GameOps)  — 跨页面组合操作                  │
│  ┌─────────────────────────────────────────────┐ │
│  │  combat — 战斗状态机引擎                      │ │
│  │  ┌─────────────────────────────────────────┐ │ │
│  │  │  ui — 单页面控制器                        │ │ │
│  │  │  ┌─────────────────────────────────────┐ │ │ │
│  │  │  │  vision — 视觉识别 (像素/模板/OCR)    │ │ │ │
│  │  │  │  emulator — 设备控制                  │ │ │ │
│  │  │  │  infra — 配置/日志/异常               │ │ │ │
│  │  │  └─────────────────────────────────────┘ │ │ │
│  │  └─────────────────────────────────────────┘ │ │
│  └─────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

每层只依赖下层，不向上耦合。模块间通过 `AndroidController` 实例 + 回调函数组合，
不再需要全局 God Object。

---

## 2. 基础设施层 (`infra/`|legacy 各处散落)

| 功能 | v2 模块 | v1 对应 | 状态 | 改进 |
|------|---------|---------|------|------|
| **配置管理** | `infra/config.py` — Pydantic v2 模型 | `configs.py` — frozen dataclass | ✅ 完成 | 类型校验+自动文档+JSON Schema |
| **异常体系** | `infra/exceptions.py` — 12 个分层异常 | `constants/custom_exceptions.py` — 5 个扁平异常 | ✅ 完成 | 结构化异常树，携带上下文 |
| **日志系统** | `infra/logger.py` — loguru 全局配置 | `utils/logger.py` — 自建 Logger 类 | ✅ 完成 | 结构化日志+双文件+图像保存 |
| **文件工具** | `infra/file_utils.py` — YAML/合并 | `utils/io.py` — 20+ 函数 | ✅ 精简 | 保留核心 3 函数，去除冗余 |

### 配置类对比

| 配置 | v2 | v1 | 差异 |
|------|----|----|------|
| 模拟器 | `EmulatorConfig` | 散落在 `UserConfig` 中 | v2 独立子模型 |
| 账号 | `AccountConfig` | `UserConfig.game_app` | v2 独立+`package_name` 属性 |
| OCR | `OCRConfig` | `UserConfig.ocr_backend` | v2 独立子模型 |
| 日志 | `LogConfig` | `UserConfig.log_level` | v2 8 个开关细粒度控制 |
| 节点 | `NodeConfig` | `NodeConfig` | 基本相同 |
| 战斗 | `FightConfig` | `FightConfig` | 基本相同 |
| 战役 | `BattleConfig` | `BattleConfig` | 基本相同 |
| 演习 | `ExerciseConfig` | `ExerciseConfig` | 基本相同 |
| 决战 | `DecisiveBattleConfig` | `DecisiveBattleConfig` | 基本相同 |
| 日常 | `DailyAutomationConfig` | `DailyAutomationConfig` | 基本相同 |

---

## 3. 视觉层 (`vision/`|legacy 各处散落)

| 功能 | v2 模块 | v1 对应 | 状态 | 改进 |
|------|---------|---------|------|------|
| **像素数据模型** | `vision/pixel.py` — Color/PixelRule/PixelSignature | `constants/colors.py` + 硬编码 | ✅ 完成 | 从魔法数字→结构化数据模型 |
| **像素检测引擎** | `vision/matcher.py` — PixelChecker(全静态) | `AndroidController.check_pixel()` | ✅ 完成 | 解耦设备控制，支持批量检测 |
| **ROI 区域** | `vision/roi.py` — ROI frozen dataclass | `utils/api_image.py` + 硬编码元组 | ✅ 完成 | 相对坐标，可组合，可序列化 |
| **图像模板数据** | `vision/image_template.py` — ImageTemplate/Rule/Signature | `constants/image_templates.py` — MyTemplate(airtest) | ✅ 完成 | 脱离 airtest 依赖，纯 OpenCV |
| **模板匹配引擎** | `vision/image_matcher.py` — ImageChecker(全静态) | `AndroidController.image_exist/wait_image` | ✅ 完成 | 解耦设备控制，签名匹配 |
| **OCR 引擎** | `vision/ocr.py` — OCREngine ABC + 工厂 | `timer/backends/ocr_backend.py` | ✅ 完成 | 抽象基类+工厂模式 |
| **图像裁剪/变换** | `vision/roi.py` — ROI.crop() | `utils/api_image.py` — 10 个函数 | ✅ 精简 | 统一到 ROI 数据模型 |
| **C++ DLL 识别** | ❌ 未迁移 | `timer/backends/api_dll.py` | � 接口预留 | 回调接口已定义(`GetEnemyInfoFunc`)，无视觉实现 |

---

## 4. 模拟器层 (`emulator/`|legacy `timer/controllers/`)

| 功能 | v2 模块 | v1 对应 | 状态 | 改进 |
|------|---------|---------|------|------|
| **设备控制抽象** | `emulator/controller.py` — AndroidController ABC | `timer/controllers/android_controller.py` | ✅ 完成 | 规范化 ABC，支持 mock |
| **ADB 实现** | `emulator/controller.py` — ADBController | 同上 (直接类) | ✅ 完成 | 分辨率校正+截图旋转修复 |
| **模拟器检测** | `emulator/detector.py` — 5 级优先级自动检测 | 无 (手动配置) | ✅ **新增** | 自动检测 + 交互选择 |
| **进程管理抽象** | `emulator/os_control.py` — EmulatorProcessManager ABC | `timer/controllers/os_controller.py` — Protocol | ✅ 完成 | 工厂模式，按 OS 自动分发 |
| **Windows 管理** | `emulator/_os_windows.py` | `os_controller.py` WindowsController | ✅ 完成 | 独立文件，MuMu CLI 增强 |
| **macOS 管理** | `emulator/_os_macos.py` | `os_controller.py` MacController | ✅ 完成 | MuMu 实例重启支持 |
| **Linux/WSL 管理** | `emulator/_os_linux.py` | `os_controller.py` LinuxController | ✅ 完成 | WSL→Windows 进程探测 |

---

## 5. UI 控制层 (`ui/`|legacy `constants/ui.py`+`timer/`)

| 功能 | v2 模块 | v1 对应 | 状态 | 改进 |
|------|---------|---------|------|------|
| **页面注册中心** | `ui/page.py` — register_page/get_current_page | `constants/ui.py` — Node/Edge/UI 树 | ✅ 完成 | 动态注册，插件化 |
| **导航树/BFS** | `ui/navigation.py` — NavEdge/find_path | `constants/ui.py` — UI.find_path(LCA) | ✅ 完成 | 平面图 BFS，支持跨级边 |
| **浮层处理** | `ui/overlay.py` — detect_overlay/dismiss | `timer.py` — Timer 内部方法 | ✅ 完成 | 独立模块，可组合 |
| **主页面** | `ui/main_page.py` — MainPage | `timer.py` — Timer.go_main_page() | ✅ 完成 | 独立控制器 |
| **地图页面** | `ui/map/page.py` — MapPage/MapPanel | `timer.py` | ✅ 完成 | 5 面板切换+OCR 章节导航 |
| **出征准备页** | `ui/battle/preparation.py` | `game/game_operation.py` 多个函数 | ✅ 完成 | 统一为单页面控制器 |
| **后院页面** | `ui/backyard_page.py` | 无独立模块 | ✅ **新增** | — |
| **浴室页面** | `ui/bath_page.py` | `port/facility.py` (空实现) | ✅ 完成 | — |
| **食堂页面** | `ui/canteen_page.py` | 无独立模块 | ✅ **新增** | — |
| **建造页面** | `ui/build_page.py` — BuildTab | 无独立模块 | ✅ **新增** | 4 Tab 切换 |
| **强化页面** | `ui/intensify_page.py` — IntensifyTab | 无独立模块 | ✅ **新增** | 3 Tab 切换 |
| **侧边栏** | `ui/sidebar_page.py` | 无独立模块 | ✅ **新增** | — |
| **任务页面** | `ui/mission_page.py` | 无独立模块 | ✅ **新增** | — |
| **好友页面** | `ui/friend_page.py` | 无独立模块 | ✅ **新增** | — |
| **决战总览页** | `ui/decisive_battle_page.py` | 无 (决战内嵌) | ✅ **新增** | — |
| **标签页检测** | `ui/tabbed_page.py` — TabbedPageType | 无 | ✅ **新增** | 通用标签页识别框架 |
| **地图数据库** | `ui/map/data.py` — MAP_DATABASE | 散落在 plan 文件中 | ✅ **新增** | 全地图名称数据库+OCR 解析 |

### 导航页面覆盖

| 页面 | v2 | v1 |
|------|----|----|
| 主页面 | ✅ MainPage | ✅ Node("main_page") |
| 地图页面 | ✅ MapPage | ✅ Node("map_page") |
| 出征准备 | ✅ BattlePreparationPage | ✅ (代码散落) |
| 后院 | ✅ BackyardPage | ❌ |
| 浴室 | ✅ BathPage | ✅ Node("bathroom_page") |
| 食堂 | ✅ CanteenPage | ❌ |
| 建造 | ✅ BuildPage | ✅ Node("build_page") |
| 强化 | ✅ IntensifyPage | ❌ |
| 侧边栏 | ✅ SidebarPage | ❌ |
| 任务 | ✅ MissionPage | ✅ Node("mission_page") |
| 好友 | ✅ FriendPage | ❌ |
| 决战总览 | ✅ DecisiveBattlePage | ❌ (内嵌) |

---

## 6. 战斗系统 (`combat/`|legacy `fight/`)

| 功能 | v2 模块 | v1 对应 | 状态 | 改进 |
|------|---------|---------|------|------|
| **战斗阶段枚举** | `combat/state.py` — CombatPhase(13个) | `fight/common.py` — FightInfo 内部状态图 | ✅ 完成 | 显式枚举+转移验证 |
| **战斗引擎** | `combat/engine.py` — CombatEngine+run_combat() | `fight/common.py` — FightPlan+FightInfo | ✅ 完成 | 引擎与决策分离 |
| **阶段处理器** | `combat/handlers.py` — PhaseHandlersMixin(11个) | `fight/common.py` — DecisionBlock | ✅ 完成 | Mixin 模式，可测试 |
| **规则引擎** | `combat/rules.py` — RuleEngine(安全) | `fight/common.py` — eval() | ✅ 完成 | **安全替代 eval()** |
| **作战计划** | `combat/plan.py` — CombatPlan+YAML | `fight/normal_fight.py` — plan_path | ✅ 完成 | 结构化数据类 |
| **战斗动作** | `combat/actions.py` — click_* 函数 | `game/game_operation.py` 散落函数 | ✅ 完成 | 集中管理+坐标常量化 |
| **状态识别** | `combat/recognizer.py` — CombatRecognizer | `fight/common.py` — FightInfo.update_state() | ✅ 完成 | 签名匹配+超时控制 |
| **战斗历史** | `combat/history.py` — CombatHistory | `fight/common.py` — FightHistory | ✅ 完成 | 事件类型枚举化 |
| **战斗结果** | `combat/callbacks.py` — CombatResult | `fight/common.py` — FightResultInfo | ✅ 完成 | 回调类型别名化 |
| **图像模板** | `combat/image_resources.py` — 延迟加载 | `constants/image_templates.py` — 全量加载 | ✅ 完成 | 按需加载，减少启动时间 |

### 战斗模式覆盖

| 模式 | v2 | v1 | 差异 |
|------|----|----|------|
| 常规战 (NORMAL) | ✅ CombatMode.NORMAL | ✅ NormalFightInfo/Plan | 多节点 proceed 决策 |
| 战役 (BATTLE) | ✅ CombatMode.BATTLE | ✅ BattleInfo/Plan | 单点，无 proceed |
| 演习 (EXERCISE) | ✅ CombatMode.EXERCISE | ✅ NormalExerciseInfo/Plan | 无 SL，专用阵型 |
| 活动 | ❌ 未迁移 | ✅ Event + 18 个活动文件 | 🔴 需要框架化支持 |

---

## 7. 游戏操作层 (`ops/`|legacy `game/`+`fight/`)

| 功能 | v2 模块 | v1 对应 | 状态 | 改进 |
|------|---------|---------|------|------|
| **跨页面导航** | `ops/navigate.py` — goto_page() | `timer.py` — Timer.set_page()/walk_to() | ✅ 完成 | 无状态函数式，含浮层处理 |
| **出征修理** | `ops/sortie.py` — apply_repair() | `game/game_operation.py` — quick_repair() | ✅ 完成 | 策略枚举化 |
| **常规战斗** | `ops/normal_fight.py` — NormalFightRunner | `fight/normal_fight.py` — NormalFightPlan | ✅ 完成 | YAML→Plan→Engine 流水线 |
| **演习战斗** | `ops/exercise.py` — ExerciseRunner | `fight/exercise.py` — NormalExercisePlan | ✅ 完成 | 独立 Config+Runner |
| **战役战斗** | `ops/campaign.py` — CampaignRunner | `fight/battle.py` — BattlePlan | ✅ 完成 | 支援开关集成 |
| **决战** | `ops/decisive/` — DecisiveController(7文件) | `fight/decisive_battle.py` — 单文件 | ✅ 完成 | 拆分为 7 模块，集成战斗引擎 |
| **远征收取** | `ops/expedition.py` — collect_expedition() | `game/expedition.py` — Expedition.run() | ✅ 完成 | 无状态函数 |
| **建造** | `ops/build.py` — build_ship/collect_built_ships | `game/build.py` — BuildManager | ✅ 完成 | 无状态函数 |
| **食堂** | `ops/cook.py` — cook() | `game/game_operation.py` — cook() | ✅ 完成 | — |
| **解装** | `ops/destroy.py` — destroy_ships() | `game/game_operation.py` — destroy_ship() | ✅ 完成 | — |
| **浴室修理** | `ops/repair.py` — repair_in_bath() | `game/game_operation.py` — repair_by_bath() | ✅ 完成 | — |
| **任务奖励** | `ops/reward.py` — collect_rewards() | `game/game_operation.py` — get_rewards() | ✅ 完成 | — |
| **图像模板** | `ops/image_resources.py` — Templates | `constants/image_templates.py` — IMG | ✅ 完成 | 分类+延迟加载 |
| **任务调度** | ❌ 未迁移 | `port/task_runner.py` — TaskRunner | 🔴 未迁移 | 自动练级/轮换/浴室调度 |
| **换船/编队** | ⚠️ 部分 | `game/game_operation.py` — change_ship/verify_team | 🟡 槽位操作已实现 | `select_fleet()`+`click_ship_slot()` 已有；跨页面 `change_fleet()` 未实现 |
| **舰队管理** | ⚠️ 部分 | `port/ship.py` — Fleet | 🟡 基础已实现 | 舰队选择+决战选编队已实现；舰队 OCR 识别为 TODO |
| **资源获取** | ❌ 未迁移 | `game/get_game_info.py` — get_resources() | 🔴 未迁移 | OCR 读取四资源 |
| **补给** | ⚠️ 部分 | `game/game_operation.py` — supply() | 🟡 UI 层已实现 | `supply()`/`toggle_auto_supply()`/`is_auto_supply_enabled()` 已实现；ops 层缺 `apply_supply()` |
| **日常调度** | ❌ 未迁移 | `scripts/daily_api.py` — DailyOperation | 🔴 未迁移 | 综合日常自动化 |
| **通知** | ❌ 未迁移 | `notification/miao_alert.py` | 🔴 未迁移 | 喵提醒推送 |
| **活动战斗** | ❌ 未迁移 | `fight/event/` — 18 个活动 | 🔴 未迁移 | 需要框架化 |
| **母港状态** | ❌ 未迁移 | `port/common.py` — Port/Ship | 🔴 未迁移 | 全局状态管理 |
| **敌方识别** | ⚠️ 部分 | C++ DLL + get_enemy_condition() | 🟡 接口预留 | 回调接口+规则引擎已就绪；无视觉识别实现，均为 `lambda: {}` |

---

## 8. 尚未迁移的功能

### 高优先级

| 功能 | 旧代码位置 | 影响范围 | v2 现状 | 缺失工作 |
|------|-----------|---------|---------|----------|
| **跨页面换船** | `game_operation.py` + `port/ship.py` | 常规战/决战/练级 | `select_fleet()`/`click_ship_slot()` 已有 | 进入选船页→搜索→确认 的完整流程 |
| **敌方编成识别** | `api_dll.py` + `get_game_info.py` | 索敌决策/阵型选择 | 回调接口/规则引擎已就绪 | 截图视觉分析代码（像素或模板匹配） |
| **补给** | `game_operation.py` — supply() | 每次出征 | UI 层 `supply()` 已实现 | ops 层封装 `apply_supply()` 便捷函数 |
| **任务调度器** | `port/task_runner.py` | 全自动挂机 | 无 | FightTask/RepairTask/TaskRunner 全部 |
| **日常自动化** | `scripts/daily_api.py` | 每日全自动 | 各子功能均已实现 | DailyOperation 组合调度主循环 |
| **活动战斗框架** | `fight/event/` | 限时活动 | 无 | Event 基类 + 巡戈作战 |

### 中优先级

| 功能 | 旧代码位置 | v2 现状 | 缺失工作 |
|------|-----------|---------|----------|
| **地图节点 OCR** | `api_dll.py` + `_handlers.py` | 章节导航 OCR 已实现 | `_recognize_node()` 内部仍是 TODO |
| **决战舰队 OCR** | `decisive_battle.py` | `_recognize_fleet_options()` 存根 | OCR 读取卡牌舰船名/费用 |
| **资源 OCR** | `get_game_info.py` | 无 | OCR 读取主页油弹钢铝 |
| **敌方阵型识别** | `get_game_info.py` | 接口预留 (`GetEnemyFormationFunc`) | OCR/模板匹配识别阵型字符 |
| **舰种检测** | `get_game_info.py` | 无 | 扫描区域颜色匹配 |
| **母港状态** | `port/common.py` | 无 | Ship/Port/BathRoom 数据模型 |
| **通知推送** | `notification/miao_alert.py` | 无 | 喵提醒 HTTP |

### 低优先级

| 功能 | 旧代码位置 | 说明 |
|------|-----------|------|
| **地图节点识别** | `api_dll.py` | C++ DLL，v2 用像素/OCR 替代中 |
| **旧 UI 树** | `constants/ui.py` | 已完全重写 |
| **旧图像模板** | `constants/image_templates.py` | 已完全重写 |

---

## 9. 新增功能（v1 不具备）

| 功能 | 模块 | 说明 |
|------|------|------|
| **模拟器自动检测** | `emulator/detector.py` | 5 级优先级自动发现设备 |
| **安全规则引擎** | `combat/rules.py` | 替代 `eval()`，防注入 |
| **结构化像素签名** | `vision/pixel.py` | 多规则组合 + 匹配策略 |
| **图像签名系统** | `vision/image_template.py` | 多模板 + ROI + 多策略匹配 |
| **标签页通用检测** | `ui/tabbed_page.py` | 通用框架，一个函数检测所有标签页类型 |
| **地图数据库** | `ui/map/data.py` | 全面地图名→编号映射 |
| **6 个新 UI 页面** | `ui/` | 后院/食堂/强化/侧边栏/好友/决战总览 |
| **结构化异常** | `infra/exceptions.py` | 12 个分层异常，携带上下文参数 |
| **Pydantic v2 配置** | `infra/config.py` | 类型自动校验 + JSON Schema |
| **决战 7 模块拆分** | `ops/decisive/` | 配置/状态/逻辑/处理器/覆盖层/控制器 分离 |

---

## 10. 模块统计

| 维度 | v2 | v1 |
|------|----|----|
| Python 文件 | ~50 | ~50 (不含 18 活动) |
| 子包 | 6 (`infra/vision/emulator/ui/combat/ops`) | 9 (constants~scripts) |
| 公开类 | ~60 | ~40 |
| 公开函数 | ~150 | ~70 |
| 枚举类型 | ~15 | ~12 |
| 配置模型 | 11 (Pydantic) | 8 (dataclass) |
| UI 页面控制器 | **14** | **5** (散落) |
| 战斗模式 | 3 (NORMAL/BATTLE/EXERCISE) | 3 + 活动 |
| 代码组织 | 分层解耦 | 单体 Timer |

### 迁移完成度

```
基础设施     ████████████████████ 100%
视觉层       ██████████████████░░  90%  (缺 C++ DLL)
模拟器层     ████████████████████ 100%
UI 控制层    ████████████████████ 100%  (14 页面)
战斗系统     ██████████████████░░  90%  (缺活动)
游戏操作     ████████████░░░░░░░░  60%  (缺调度/换船/日常)
```

**总体迁移进度: ~80%**

---

## 附录: 目录结构对比

<details>
<summary>v2 目录结构</summary>

```
autowsgr/
├── __init__.py
├── types.py              # 全局枚举
├── infra/                # 基础设施
│   ├── config.py
│   ├── exceptions.py
│   ├── logger.py
│   └── file_utils.py
├── vision/               # 视觉层
│   ├── pixel.py
│   ├── matcher.py
│   ├── roi.py
│   ├── image_template.py
│   ├── image_matcher.py
│   └── ocr.py
├── emulator/             # 模拟器层
│   ├── controller.py
│   ├── detector.py
│   ├── os_control.py
│   ├── _os_windows.py
│   ├── _os_macos.py
│   └── _os_linux.py
├── ui/                   # UI 控制层 (14 页面)
│   ├── page.py
│   ├── overlay.py
│   ├── navigation.py
│   ├── tabbed_page.py
│   ├── map/
│   │   ├── data.py
│   │   ├── page.py
│   │   └── ops.py
│   ├── main_page.py
│   ├── battle/
│   │   ├── constants.py
│   │   └── preparation.py
│   ├── backyard_page.py
│   ├── bath_page.py
│   ├── canteen_page.py
│   ├── build_page.py
│   ├── intensify_page.py
│   ├── sidebar_page.py
│   ├── mission_page.py
│   ├── friend_page.py
│   └── decisive_battle_page.py
├── combat/               # 战斗系统
│   ├── state.py
│   ├── engine.py
│   ├── handlers.py
│   ├── recognizer.py
│   ├── rules.py
│   ├── plan.py
│   ├── actions.py
│   ├── callbacks.py
│   ├── history.py
│   └── image_resources.py
└── ops/                  # 游戏操作层
    ├── navigate.py
    ├── sortie.py
    ├── normal_fight.py
    ├── exercise.py
    ├── campaign.py
    ├── expedition.py
    ├── build.py
    ├── cook.py
    ├── destroy.py
    ├── repair.py
    ├── reward.py
    ├── image_resources.py
    └── decisive/         # 决战 (7 模块)
        ├── _config.py
        ├── _state.py
        ├── _logic.py
        ├── _handlers.py
        ├── _overlay.py
        └── _controller.py
```

</details>

<details>
<summary>v1 目录结构</summary>

```
autowsgr_legacy/
├── __init__.py
├── configs.py
├── types.py
├── bin/
├── constants/
│   ├── colors.py
│   ├── custom_exceptions.py
│   ├── data_roots.py
│   ├── image_templates.py
│   ├── marker_points.py
│   ├── other_constants.py
│   ├── positions.py
│   └── ui.py
├── utils/
│   ├── api_image.py
│   ├── io.py
│   ├── logger.py
│   ├── math_functions.py
│   ├── operator.py
│   └── time.py
├── timer/
│   ├── timer.py          # God Object
│   ├── backends/
│   └── controllers/
├── game/
│   ├── game_operation.py
│   ├── get_game_info.py
│   ├── build.py
│   └── expedition.py
├── fight/
│   ├── common.py
│   ├── normal_fight.py
│   ├── battle.py
│   ├── exercise.py
│   ├── decisive_battle.py
│   └── event/            # 18 个活动
├── port/
│   ├── common.py
│   ├── ship.py
│   ├── facility.py
│   └── task_runner.py
├── scripts/
│   ├── main.py
│   └── daily_api.py
├── notification/
│   └── miao_alert.py
└── data/
```

</details>
