# 调度层 (Scheduler)

## 职责

编排和调度游戏操作：任务队列管理、循环执行、异常恢复、定时任务。

**不包含**具体的游戏操作逻辑（那是 GameOps 的事），只做"什么时候做什么"。

---

## 1. Task 抽象

```python
# autowsgr/scheduler/task.py

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any
from loguru import logger

from autowsgr.ui.controller import UIController
from autowsgr.ui.recognizer import UIRecognizer


class TaskStatus(Enum):
    PENDING = auto()      # 待执行
    RUNNING = auto()      # 执行中
    COMPLETED = auto()    # 已完成
    FAILED = auto()       # 失败
    SKIPPED = auto()      # 跳过


@dataclass
class TaskResult:
    """任务执行结果"""
    status: TaskStatus
    message: str = ""
    data: Any = None


class Task(ABC):
    """任务基类"""
    
    def __init__(self, name: str, priority: int = 0) -> None:
        self.name = name
        self.priority = priority
        self.status = TaskStatus.PENDING
        self.run_count: int = 0
        self.last_run: datetime | None = None
        self.max_retries: int = 3
    
    @abstractmethod
    def should_run(self) -> bool:
        """判断是否应该执行"""
        ...
    
    @abstractmethod
    def execute(
        self,
        ctrl: UIController,
        recognizer: UIRecognizer,
    ) -> tuple[UIController, TaskResult]:
        """执行任务
        
        Returns: (执行后的 Controller, 结果)
        """
        ...
    
    def on_error(self, error: Exception) -> None:
        """错误回调"""
        logger.warning("任务 {} 出错: {}", self.name, error)
```

---

## 2. 具体任务类型

```python
# autowsgr/scheduler/tasks.py

from autowsgr.scheduler.task import Task, TaskResult, TaskStatus
from autowsgr.ops.sortie import SortieConfig, prepare_sortie
from autowsgr.ops.expedition import collect_expedition, dispatch_expedition
from autowsgr.ops.daily import run_daily_routine
from autowsgr.combat.engine import run_combat, CombatPlan


class SortieTask(Task):
    """出击任务"""
    
    def __init__(
        self,
        sortie_config: SortieConfig,
        combat_plan: CombatPlan,
        times: int = 1,
        **kwargs,
    ) -> None:
        super().__init__(name=f"出击_{sortie_config.chapter}-{sortie_config.map_id}", **kwargs)
        self._config = sortie_config
        self._plan = combat_plan
        self._total = times
        self._remaining = times
    
    def should_run(self) -> bool:
        return self._remaining > 0
    
    def execute(self, ctrl, recognizer):
        # 准备
        ctrl = prepare_sortie(ctrl, recognizer, config=self._config)
        # 战斗
        ctrl, result = run_combat(ctrl, recognizer, plan=self._plan)
        
        self._remaining -= 1
        return ctrl, TaskResult(
            status=TaskStatus.COMPLETED,
            message=f"剩余 {self._remaining}/{self._total}",
            data=result,
        )


class ExpeditionTask(Task):
    """远征收取/派遣任务"""
    
    def __init__(self, expedition_ids: list[int], **kwargs) -> None:
        super().__init__(name="远征管理", priority=10, **kwargs)
        self._expedition_ids = expedition_ids
        self._interval_seconds = 300  # 5 分钟检查一次
    
    def should_run(self) -> bool:
        if self.last_run is None:
            return True
        elapsed = (datetime.now() - self.last_run).total_seconds()
        return elapsed >= self._interval_seconds
    
    def execute(self, ctrl, recognizer):
        ctrl, collected = collect_expedition(ctrl, recognizer)
        if collected:
            ctrl = dispatch_expedition(ctrl, recognizer, expedition_ids=self._expedition_ids)
        return ctrl, TaskResult(
            status=TaskStatus.COMPLETED,
            message=f"收取 {len(collected)} 个远征",
        )


class DailyTask(Task):
    """日常自动任务"""
    
    def __init__(self, daily_config, **kwargs) -> None:
        super().__init__(name="日常自动化", priority=5, **kwargs)
        self._config = daily_config
        self._done_today = False
        self._last_date: str = ""
    
    def should_run(self) -> bool:
        today = datetime.now().strftime("%Y-%m-%d")
        if today != self._last_date:
            self._done_today = False
        return not self._done_today
    
    def execute(self, ctrl, recognizer):
        run_daily_routine(recognizer, config=self._config)
        self._done_today = True
        self._last_date = datetime.now().strftime("%Y-%m-%d")
        ctrl = go_main_page(recognizer)
        return ctrl, TaskResult(status=TaskStatus.COMPLETED)
```

---

## 3. Scheduler 调度器

```python
# autowsgr/scheduler/scheduler.py

import time
from datetime import datetime
from loguru import logger

from autowsgr.scheduler.task import Task, TaskStatus, TaskResult
from autowsgr.ui.recognizer import UIRecognizer
from autowsgr.ui.router import go_main_page
from autowsgr.infra import AutoWSGRError, CriticalError, NetworkError


class Scheduler:
    """任务调度器"""
    
    def __init__(self, recognizer: UIRecognizer) -> None:
        self._recognizer = recognizer
        self._tasks: list[Task] = []
        self._running = False
        self._on_error_callbacks: list = []
    
    def add_task(self, task: Task) -> None:
        self._tasks.append(task)
        logger.info("添加任务: {} (优先级={})", task.name, task.priority)
    
    def run(self) -> None:
        """主调度循环"""
        self._running = True
        logger.info("调度器启动，共 {} 个任务", len(self._tasks))
        
        # 初始化：回主页
        ctrl = go_main_page(self._recognizer)
        
        while self._running:
            # 找下一个应执行的任务
            task = self._pick_next_task()
            if task is None:
                if self._all_completed():
                    logger.info("所有任务已完成")
                    break
                # 没有待执行任务，等待
                time.sleep(10)
                continue
            
            # 执行任务
            logger.info("┌─ 开始: {} (第 {} 次)", task.name, task.run_count + 1)
            task.status = TaskStatus.RUNNING
            
            try:
                ctrl, result = task.execute(ctrl, self._recognizer)
                task.status = result.status
                task.run_count += 1
                task.last_run = datetime.now()
                logger.info("└─ 完成: {} — {}", task.name, result.message)
                
            except NetworkError:
                logger.warning("网络错误，尝试恢复...")
                ctrl = self._recover(ctrl)
                
            except CriticalError as e:
                logger.error("严重错误: {}，终止调度", e)
                self._running = False
                raise
                
            except AutoWSGRError as e:
                logger.warning("任务 {} 出错: {}", task.name, e)
                task.on_error(e)
                task.status = TaskStatus.FAILED
                # 尝试恢复到主页
                try:
                    ctrl = go_main_page(self._recognizer)
                except Exception:
                    ctrl = self._recover(ctrl)
    
    def stop(self) -> None:
        self._running = False
        logger.info("调度器停止")
    
    def _pick_next_task(self) -> Task | None:
        """选择下一个应执行的任务（优先级最高的）"""
        runnable = [t for t in self._tasks if t.should_run()]
        if not runnable:
            return None
        return max(runnable, key=lambda t: t.priority)
    
    def _all_completed(self) -> bool:
        return all(not t.should_run() for t in self._tasks)
    
    def _recover(self, ctrl) -> 'UIController':
        """错误恢复：重启游戏并回到主页"""
        logger.info("执行错误恢复...")
        try:
            return go_main_page(self._recognizer)
        except Exception:
            # 最终手段：重启应用
            logger.warning("回主页失败，重启游戏...")
            device = self._recognizer._device
            device.stop_app("com.huanmeng.zhanjian2")
            time.sleep(3)
            device.start_app("com.huanmeng.zhanjian2")
            time.sleep(15)
            return go_main_page(self._recognizer)
```

---

## 4. 用户使用入口

```python
# autowsgr/main.py

from pathlib import Path
from loguru import logger

from autowsgr.infra import ConfigManager
from autowsgr.infra import setup_logger
from autowsgr.vision.matcher import ImageMatcher
from autowsgr.vision.ocr import OCREngine
from autowsgr.emulator import ADBController
from autowsgr.emulator import EmulatorProcessManager
from autowsgr.ui.recognizer import UIRecognizer
from autowsgr.scheduler.scheduler import Scheduler


def create_scheduler(config_path: str | Path) -> Scheduler:
    """创建并配置调度器（一站式入口）"""
    # 1. 加载配置
    config = ConfigManager.load(config_path)
    setup_logger(config.log.dir, config.log.level)
    
    # 2. 启动模拟器（如需要）
    emu_mgr = EmulatorProcessManager.create("auto", config.emulator.type)
    if not emu_mgr.is_emulator_running():
        logger.info("启动模拟器...")
        serial = emu_mgr.start_emulator(config.emulator.path or emu_mgr.find_emulator())
    else:
        serial = config.emulator.serial
    
    # 3. 连接设备
    device = ADBController(serial=serial)
    device.connect()
    
    # 4. 初始化视觉层
    matcher = ImageMatcher()
    ocr = OCREngine.create(config.ocr.engine, config.ocr.gpu)
    
    # 5. 初始化 UI 识别器
    recognizer = UIRecognizer(device, matcher, ocr)
    
    # 6. 创建调度器
    scheduler = Scheduler(recognizer)
    
    return scheduler
```

**用户脚本示例：**
```python
from autowsgr.main import create_scheduler
from autowsgr.scheduler.tasks import SortieTask, ExpeditionTask
from autowsgr.ops.sortie import SortieConfig
from autowsgr.combat.plans import NormalCombatPlan

scheduler = create_scheduler("user_settings.yaml")

# 添加远征任务
scheduler.add_task(ExpeditionTask([5, 7, 21, 36]))

# 添加出击任务：5-4 打 20 次
scheduler.add_task(SortieTask(
    sortie_config=SortieConfig(chapter=5, map_id=4, fleet_id=1),
    combat_plan=NormalCombatPlan.from_yaml("plans/5-4.yaml"),
    times=20,
))

# 开始执行
scheduler.run()
```
