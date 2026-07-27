"""调度层 — 启动编排与任务调度。

提供一站式启动入口和 GameContext 构造：

- :func:`launch` — 加载配置 → 连接模拟器 → 启动游戏 → 返回就绪的 GameContext
- :class:`Launcher` — 可定制的启动器
- :class:`TaskScheduler` — 基础任务调度器 (顺序执行 + 远征定时检查 + 触发器调度)
- :class:`FightTask` — 战斗任务描述
- :func:`build_daily_plan` — 把 ``daily_automation`` 配置翻译成触发器 (auto_daily)

典型用法::

    from autowsgr.scheduler import launch, TaskScheduler, FightTask

    ctx = launch("user_settings.yaml")
    scheduler = TaskScheduler(ctx, expedition_interval=900)
    scheduler.add(FightTask(runner=my_runner, times=30))
    scheduler.run()

auto_daily 全天挂机::

    from autowsgr.scheduler import launch, TaskScheduler, build_daily_plan

    ctx = launch("user_settings.yaml")
    scheduler = TaskScheduler(ctx, expedition_interval=0)  # 远征交给触发器
    build_daily_plan(scheduler, ctx)
    scheduler.run_daily()
"""

from .daily_plan import build_daily_plan
from .launcher import Launcher, launch
from .scheduler import BatchRunnerAdapter, FightTask, TaskScheduler


__all__ = [
    'BatchRunnerAdapter',
    'FightTask',
    'Launcher',
    'TaskScheduler',
    'build_daily_plan',
    'launch',
]
