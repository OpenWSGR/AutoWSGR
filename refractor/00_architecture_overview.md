# 重构方案 V2 — 架构总览

## 设计原则

1. **完全重写**，不考虑向后兼容
2. **分层严格**，上层只依赖下层，禁止反向依赖和跨层调用
3. **每页一个 Controller**，页面的识别、交互、导航高度内聚
4. **函数式游戏操作层**，组装 UIController 完成业务流程
5. **GameContext 极简**，仅 UserConfig + Logger，不做 God Object

---

## 架构分层

```
┌─────────────────────────────────────────────────┐
│                 调度层 (Scheduler)                │  任务编排、自动化流程
├─────────────────────────────────────────────────┤
│              游戏操作层 (GameOps)                 │  函数式，组装 Controller
├─────────────────────────────────────────────────┤
│              UI 控制层 (UIControl)               │  每页一个 Controller
│  ┌──────────────┬──────────────┬───────────────┐ │
│  │ UIRecognizer │ UIController │   UIAction    │ │
│  └──────────────┴──────────────┴───────────────┘ │
├─────────────────────────────────────────────────┤
│           模拟器操作层 (Emulator)                 │  ADB 点击/滑动/截图
│              AndroidController                   │
├─────────────────────────────────────────────────┤
│              视觉层 (Vision)                     │  OCR + 模板匹配
│  ┌──────────────┬──────────────┐                 │
│  │  OCREngine   │ ImageMatcher │                 │
│  └──────────────┴──────────────┘                 │
├─────────────────────────────────────────────────┤
│            基础设施层 (Infra)                     │  日志、配置、异常
│  ┌──────────┬───────────────┬─────────┐          │
│  │  Logger  │ ConfigManager │ Errors  │          │
│  └──────────┴───────────────┴─────────┘          │
└─────────────────────────────────────────────────┘

横切关注点: GameContext (UserConfig + Logger)
```

## 依赖规则

```
Scheduler → GameOps → UIControl → Emulator → Vision → Infra
                                          ↘        ↗
                                           Infra
```

- **Infra** 不依赖任何其他层
- **Vision** 仅依赖 Infra（日志、配置中的 OCR 设置）
- **Emulator** 依赖 Vision（截图后可能需要即时匹配）和 Infra
- **UIControl** 依赖 Emulator（点击/截图）和 Vision（识别页面）
- **GameOps** 依赖 UIControl（组装 Controller 完成流程）
- **Scheduler** 依赖 GameOps（调度任务）

**注意：Emulator 是否应该依赖 Vision？**

这里有一个设计选择。当前代码中 `AndroidController.image_exist()`, `wait_image()` 等方法把图像匹配直接混在设备控制里。在新架构中有两种方案：

- **方案 A**：Emulator 纯粹做 ADB 操作（click, swipe, screenshot），Vision 独立。需要匹配时由上层（UIControl）同时调用两者。
- **方案 B**：Emulator 依赖 Vision，提供 `click_image()`, `wait_image()` 等便捷方法。

**推荐方案 A** — 保持 Emulator 纯粹，UIControl 负责"看到什么就点什么"的逻辑。

修正后的依赖：
```
Scheduler → GameOps → UIControl → { Emulator, Vision } → Infra
```

---

## GameContext

```python
@dataclass
class GameContext:
    """全局上下文 — 仅持有配置和日志"""
    config: UserConfig
    logger: Logger
```

GameContext **不持有** AndroidController、Vision 等运行时服务。这些服务通过依赖注入传给需要它们的组件。

---

## 对象生命周期 & 组装

```python
def bootstrap(config_path: str) -> Scheduler:
    """启动流程 — 组装所有组件"""
    # 1. 基础设施
    config = ConfigManager.load(config_path)
    logger = Logger(config.log)
    ctx = GameContext(config=config.user, logger=logger)
    
    # 2. 视觉层
    ocr = OCREngine.create(config.ocr)
    matcher = ImageMatcher(config.vision)
    
    # 3. 模拟器层
    emulator = AndroidController(config.emulator, logger)
    
    # 4. UI 控制层
    recognizer = UIRecognizer(emulator, matcher)
    controller_factory = UIControllerFactory(emulator, matcher, ocr, recognizer)
    
    # 5. 游戏操作层
    ops = GameOps(controller_factory, ctx)
    
    # 6. 调度层
    scheduler = Scheduler(ops, ctx)
    
    return scheduler
```

---

## 各层详细设计

→ 见后续文档：
- [01_infrastructure.md](01_infrastructure.md) — 基础设施层
- [02_vision.md](02_vision.md) — 视觉层
- [03_emulator.md](03_emulator.md) — 模拟器操作层
- [04_ui_control.md](04_ui_control.md) — UI 控制层（核心）
- [05_game_ops.md](05_game_ops.md) — 游戏操作层
- [06_scheduler.md](06_scheduler.md) — 调度层
- [07_combat_system.md](07_combat_system.md) — 战斗系统专项
- [08_directory_structure.md](08_directory_structure.md) — 目录结构 & 文件映射
