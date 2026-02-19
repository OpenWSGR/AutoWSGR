# 目录结构 & 文件映射

## 新目录结构

```
autowsgr/
├── __init__.py
├── main.py                         # create_scheduler() 入口
├── types.py                        # 全局枚举 (Formation, ShipType, ...)
│
├── infra/                          # ① 基础设施层
│   ├── __init__.py
│   ├── logger.py                   # setup_logger()，全局用 loguru
│   ├── config.py                   # Pydantic: UserConfig, EmulatorConfig, ...
│   ├── exceptions.py               # 异常层级
│   └── file_utils.py               # load_yaml, merge_dicts
│
├── vision/                         # ② 视觉层
│   ├── __init__.py
│   ├── matcher.py                  # ImageMatcher, MatchResult, Color
│   ├── ocr.py                      # OCREngine ABC, EasyOCR, PaddleOCR
│   ├── native.py                   # NativeRecognizer (C++ DLL)
│   └── templates.py                # PageTemplate, FightTemplate, TemplateRegistry
│
├── emulator/                       # ③ 模拟器操作层
│   ├── __init__.py
│   ├── controller.py               # AndroidController ABC, ADBController
│   └── os_control.py               # EmulatorProcessManager, Windows/Mac/Linux
│
├── ui/                             # ④ UI 控制层
│   ├── __init__.py
│   ├── controller.py               # UIController ABC
│   ├── action.py                   # UIAction, ClickStep, SwipeStep
│   ├── recognizer.py               # UIRecognizer
│   ├── router.py                   # navigate(), go_main_page(), ADJACENCY
│   └── pages/                      # 每页一个 Controller
│       ├── __init__.py
│       ├── main_page.py            # MainPageController
│       ├── map_page.py             # MapPageController
│       ├── fight_prepare.py        # FightPrepareController
│       ├── exercise.py             # ExercisePageController
│       ├── expedition.py           # ExpeditionPageController
│       ├── battle.py               # BattlePageController
│       ├── build.py                # BuildPageController
│       ├── destroy.py              # DestroyPageController
│       ├── backyard.py             # BackyardPageController
│       ├── bath.py                 # BathPageController
│       ├── canteen.py              # CanteenPageController
│       ├── choose_ship.py          # ChooseShipPageController
│       ├── mission.py              # MissionPageController
│       ├── options.py              # OptionsPageController
│       └── decisive_battle.py      # DecisiveBattleController
│
├── ops/                            # ⑤ 游戏操作层（函数式）
│   ├── __init__.py
│   ├── sortie.py                   # prepare_sortie, change_fleet, apply_repair
│   ├── expedition.py               # collect_expedition, dispatch_expedition
│   ├── build.py                    # build_ship, collect_built_ships
│   ├── destroy.py                  # destroy_ships
│   ├── cook.py                     # cook
│   └── daily.py                    # run_daily_routine, collect_rewards
│
├── combat/                         # 战斗系统（独立子系统）
│   ├── __init__.py
│   ├── state.py                    # CombatState, STATE_TRANSITIONS
│   ├── recognizer.py               # CombatStateRecognizer, STATE_SIGNATURES
│   ├── rules.py                    # Rule, RuleEngine (替代 eval)
│   ├── plan.py                     # CombatPlan, NodeDecision
│   ├── engine.py                   # run_combat()
│   ├── event.py                    # EventConfig, EventCombatEngine
│   └── decisive.py                 # DecisiveBattle (特殊模式)
│
├── scheduler/                      # ⑥ 调度层
│   ├── __init__.py
│   ├── task.py                     # Task ABC, TaskResult, TaskStatus
│   ├── tasks.py                    # SortieTask, ExpeditionTask, DailyTask
│   └── scheduler.py                # Scheduler
│
├── notification/                   # 通知（跨层）
│   ├── __init__.py
│   └── miao_alert.py               # 喵提醒
│
└── data/                           # 静态数据
    ├── images/                     # 模板图片
    │   ├── identify_images/
    │   ├── fight_image/
    │   ├── back_buttons/
    │   ├── ...
    ├── plans/                      # 作战计划 YAML
    │   ├── normal/
    │   ├── event/
    │   └── exercise/
    ├── events/                     # 事件配置 YAML
    │   ├── 2024_spring.yaml
    │   ├── 2025_winter.yaml
    │   └── ...
    └── ocr/
        ├── ship_name.yaml
        └── relative_location.yaml


tests/
├── conftest.py
├── unit/
│   ├── infra/
│   │   ├── test_config.py
│   │   └── test_exceptions.py
│   ├── vision/
│   │   ├── test_matcher.py
│   │   └── test_ocr.py
│   ├── ui/
│   │   ├── test_router.py
│   │   └── test_controller.py
│   ├── combat/
│   │   ├── test_rules.py
│   │   ├── test_state_machine.py
│   │   └── test_plan.py
│   └── scheduler/
│       └── test_scheduler.py
├── integration/
│   ├── test_navigation.py
│   └── test_combat_flow.py
└── fixtures/
    ├── screens/
    ├── configs/
    └── plans/

examples/
├── auto_daily.py
├── sortie_5_4.py
├── decisive_battle.py
├── event.py
├── user_settings.yaml
└── plans/
    ├── 5-4.yaml
    └── exercise.yaml
```

---

## 新旧文件完整映射

### 基础设施层

| 原文件 | 新文件 | 操作 |
|--------|--------|------|
| `utils/logger.py` | `infra/logger.py` | 重写（去包装层） |
| `configs.py` | `infra/config.py` | 重写（Pydantic v2） |
| `constants/custom_exceptions.py` | `infra/exceptions.py` | 重写（修正继承） |
| `utils/io.py` | `infra/file_utils.py` | 精简 |
| `utils/operator.py` | 删除 | 内联到调用处 |
| `utils/time.py` | 删除或内联 | Stopwatch 仅 combat 用 |

### 视觉层

| 原文件 | 新文件 | 操作 |
|--------|--------|------|
| `utils/api_image.py` | `vision/matcher.py` | 重写 |
| `utils/math_functions.py` | `vision/matcher.py` (Color.distance) | 合入 |
| `timer/backends/ocr_backend.py` | `vision/ocr.py` | 重写（Protocol→ABC） |
| `timer/backends/api_dll.py` | `vision/native.py` | 封装保留 |
| `constants/image_templates.py` | `vision/templates.py` | 重写（枚举化） |
| `constants/colors.py` | `vision/matcher.py` (Color) | 合入 |
| `constants/marker_points.py` | `ui/pages/*.py` | 分散到各 Controller |
| `constants/positions.py` | `ui/pages/*.py` | 分散到各 Controller |

### 模拟器操作层

| 原文件 | 新文件 | 操作 |
|--------|--------|------|
| `timer/controllers/android_controller.py` | `emulator/controller.py` | 重写（剥离视觉） |
| `timer/controllers/os_controller.py` | `emulator/os_control.py` | 重写 |

### UI 控制层

| 原文件 | 新文件 | 操作 |
|--------|--------|------|
| `constants/ui.py` (Node, Edge, UI, WSGR_UI) | `ui/controller.py` + `ui/action.py` + `ui/router.py` | 重写 |
| `timer/timer.py` (go_main_page, walk_to, operate, ...) | `ui/router.py` | 重写 |
| `timer/timer.py` (identify_page, get_now_page, ...) | `ui/recognizer.py` | 重写 |
| 无 | `ui/pages/*.py` (15 个 Controller) | 新增 |

### 游戏操作层

| 原文件 | 新文件 | 操作 |
|--------|--------|------|
| `game/game_operation.py` | `ops/sortie.py` + `ops/destroy.py` + `ops/cook.py` + `ops/daily.py` | 拆分为函数式 |
| `game/get_game_info.py` | 分散到各 Controller 和 `combat/` | 按职责归位 |
| `game/expedition.py` | `ops/expedition.py` | 重写 |
| `game/build.py` | `ops/build.py` | 重写 |
| `port/common.py` | 删除 | Ship/Fleet 概念移入 Controller |
| `port/ship.py` | `ui/pages/fight_prepare.py` + `ui/pages/choose_ship.py` | 归入 Controller |
| `port/facility.py` | 删除 | 空类 |

### 战斗系统

| 原文件 | 新文件 | 操作 |
|--------|--------|------|
| `fight/common.py` (FightInfo, FightPlan, DecisionBlock) | `combat/state.py` + `combat/engine.py` + `combat/rules.py` | 拆分重写 |
| `fight/normal_fight.py` | `combat/plan.py` + YAML | 数据化 |
| `fight/battle.py` | `combat/plan.py` (复用) | 合入 |
| `fight/exercise.py` | `combat/plan.py` (复用) | 合入 |
| `fight/decisive_battle.py` | `combat/decisive.py` | 独立保留（复杂） |
| `fight/event/*.py` (17 个) | `combat/event.py` + `data/events/*.yaml` | 数据驱动化 |

### 调度层

| 原文件 | 新文件 | 操作 |
|--------|--------|------|
| `port/task_runner.py` | `scheduler/task.py` + `scheduler/tasks.py` + `scheduler/scheduler.py` | 拆分重写 |
| `scripts/main.py` | `main.py` | 重写 |
| `scripts/daily_api.py` | `ops/daily.py` | 合入 |

### 删除的文件/目录

| 原文件 | 原因 |
|--------|------|
| `constants/__init__.py` + 整个旧 constants 目录 | 逻辑分散到各层 |
| `timer/` 整个目录 | Timer 已消失 |
| `fight/` 整个旧目录 | 重建为 combat/ |
| `game/` 整个旧目录 | 拆分到 ops/ 和 ui/pages/ |
| `port/` 整个旧目录 | 归入 ui/pages/ 和删除 |
| `scripts/` 整个目录 | 合入 main.py 和 ops/ |
| `utils/` 整个目录 | 合入 infra/ 和 vision/ |

---

## 层间依赖验证

```python
# 可用 import-linter 强制执行
[importlinter]
root_package = autowsgr

[importlinter:contract:layers]
name = 分层架构
type = layers
layers =
    autowsgr.scheduler
    autowsgr.ops
    autowsgr.combat
    autowsgr.ui
    autowsgr.emulator
    autowsgr.vision
    autowsgr.infra
```

| 层 | 可依赖 | 禁止依赖 |
|----|--------|---------|
| `infra/` | 标准库, 第三方 (pydantic, loguru, yaml) | vision, emulator, ui, ops, combat, scheduler |
| `vision/` | infra, 标准库, cv2, numpy, easyocr, paddleocr | emulator, ui, ops, combat, scheduler |
| `emulator/` | infra, 标准库, airtest | vision, ui, ops, combat, scheduler |
| `ui/` | infra, vision, emulator | ops, combat, scheduler |
| `ops/` | infra, vision, ui, combat | scheduler |
| `combat/` | infra, vision, emulator, ui | ops, scheduler |
| `scheduler/` | infra, ops, combat, ui | - |

**注意**: `ops/` 和 `combat/` 都依赖 `ui/`，但互不依赖。`scheduler/` 同时依赖两者。
