"""auto_daily 计划构建 — 把 :class:`DailyAutomationConfig` 翻译成触发器。

激活 dev 的「死配置」``daily_automation``: 读取其字段, 为每个启用的日常任务
(远征 / 战役 / 演习 / 常规战) 构造触发器并注册到 :class:`TaskScheduler`。

优先级 (数值小先执行, 由 :mod:`autowsgr.scheduler.triggers` 定义)::

    远征 0  <  奖励 1  <  战役 5  <  演习 10  <  常规战 100  <  浴室修理 200 (空闲填充, 最后执行)

使用方式::

    from autowsgr.scheduler import launch, TaskScheduler, build_daily_plan

    ctx = launch("user_settings.yaml")
    scheduler = TaskScheduler(ctx, expedition_interval=0)  # 旧远征检查交给触发器
    build_daily_plan(scheduler, ctx)
    scheduler.run_daily()
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.combat import CombatResult
from autowsgr.infra.logger import get_logger
from autowsgr.scheduler.triggers import (
    CampaignTrigger,
    ExerciseTrigger,
    ExpeditionTrigger,
    NormalFightPlan,
    NormalFightTrigger,
    TimerTrigger,
)
from autowsgr.types import ConditionFlag


if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from autowsgr.context import GameContext
    from autowsgr.infra.config import DailyAutomationConfig
    from autowsgr.scheduler.scheduler import TaskScheduler

_log = get_logger('scheduler')

# 优先级常量 (数值越小越先执行)
PRIO_EXPEDITION = 0
PRIO_BONUS = 1
PRIO_CAMPAIGN = 5
PRIO_EXERCISE = 10
PRIO_NORMAL_FIGHT = 100
# 浴室修理: 空闲填充, 排在所有战斗任务之后 —— 仅当战役/演习/常规战都无 pending
# 任务 (常规战 _is_exhausted、战役演习 _exhausted) 时才出队执行, 还原 classic
# "所有战斗 (含常规战) 完成后才修船" 的语义。与 NormalFightTrigger 用 prio=100
# 实现"空闲填充"同理, 只是浴室修理比常规战更晚 (优先级更低)。
PRIO_BATH_REPAIR = 200

# 远征定时触发间隔 (秒)。collect_expedition 内部会先检查是否有远征可收取,
# 无则空转返回, 故可较短; 默认 10 分钟轮询一次。
DEFAULT_EXPEDITION_INTERVAL = 600.0


class _FunctionRunner:
    """把任意 ``fn(ctx)`` 包成 ``run() -> CombatResult`` 的 runner。

    远征等非战斗任务没有 CombatResult 语义, 这里统一返回 ``OPERATION_SUCCESS``;
    异常被吞掉并记录 (远征失败不应中断整日挂机)。
    """

    def __init__(self, fn: Callable[[], object], name: str = '远征') -> None:
        self._fn = fn
        self._name = name

    def run(self) -> CombatResult:
        try:
            self._fn()
        except Exception as exc:
            _log.opt(exception=True).warning('[daily] {} 执行异常: {}', self._name, exc)
        return CombatResult(flag=ConditionFlag.OPERATION_SUCCESS)


def build_daily_plan(
    scheduler: TaskScheduler,
    ctx: GameContext,
    *,
    expedition_interval: float = DEFAULT_EXPEDITION_INTERVAL,
) -> None:
    """读取 ``ctx.config.daily_automation``, 注册各触发器到 ``scheduler``。

    Parameters
    ----------
    scheduler:
        目标调度器。
    ctx:
        游戏上下文 (提供 config / 控制器)。
    expedition_interval:
        远征定时触发的轮询间隔 (秒)。
    """
    cfg = ctx.config.daily_automation
    if cfg is None:
        _log.warning('[daily] 未配置 daily_automation, 不注册任何触发器')
        return

    _log.info('[daily] 构建 auto_daily 计划')

    # ── 远征 (定时, prio 0) ──
    if cfg.auto_expedition:
        from autowsgr.ops.expedition import collect_expedition

        scheduler.register_trigger(
            ExpeditionTrigger(
                task_factory=lambda c: _FunctionRunner(
                    lambda: collect_expedition(c),
                    name='远征',
                ),
                priority=PRIO_EXPEDITION,
                name='远征',
                interval=expedition_interval,
            ),
        )

    # ── 任务奖励 (定时, prio 1, 随远征周期) ──
    if cfg.auto_gain_bonus:
        from autowsgr.ops.reward import collect_rewards

        scheduler.register_trigger(
            TimerTrigger(
                task_factory=lambda c: _FunctionRunner(
                    lambda: collect_rewards(c),
                    name='任务奖励',
                ),
                priority=PRIO_BONUS,
                name='任务奖励',
                interval=expedition_interval,
            ),
        )

    # ── 浴室修理 (定时, prio 200, 空闲填充: 所有战斗完成后才执行) ──
    if cfg.auto_bath_repair:
        from autowsgr.ops.repair import repair_one_available

        scheduler.register_trigger(
            TimerTrigger(
                task_factory=lambda c: _FunctionRunner(
                    lambda: repair_one_available(
                        c,
                        blacklist=cfg.bath_repair_blacklist,
                    ),
                    name='浴室修理',
                ),
                priority=PRIO_BATH_REPAIR,
                name='浴室修理',
                interval=expedition_interval,
            ),
        )

    # ── 战役 (条件, prio 5) ──
    if cfg.auto_battle:
        from autowsgr.ops.campaign import CampaignRunner

        battle_type = cfg.battle_type
        scheduler.register_trigger(
            CampaignTrigger(
                # times=1: 每个任务打一场, 场间允许远征插队; 次数耗尽由 BATTLE_TIMES_EXCEED 自适应
                task_factory=lambda c: CampaignRunner(c, battle_type, times=1),
                priority=PRIO_CAMPAIGN,
                name=f'战役/{battle_type}',
            ),
        )

    # ── 演习 (条件, prio 10) ──
    if cfg.auto_exercise:
        from autowsgr.ops.exercise import ExerciseOnceRunner

        fleet_id = cfg.exercise_fleet_id or 1
        scheduler.register_trigger(
            ExerciseTrigger(
                task_factory=lambda c: ExerciseOnceRunner(c, fleet_id),
                priority=PRIO_EXERCISE,
                name='演习',
            ),
        )

    # ── 常规战 (条件, prio 100, 空闲填充) ──
    if cfg.auto_normal_fight and cfg.normal_fight_tasks:
        _register_normal_fight(scheduler, cfg, plan_root=ctx.config.plan_root)

    # ── 浴室修理被无限常规战抢占的告警 ──
    # 改 prio 后浴室修理 (200) 排在常规战 (100) 之后; 若存在无限常规战
    # (times=None) 且未开任何停止上限, 常规战会持续产出 prio=100 任务、
    # 永远抢占浴室修理致其无声失效。这是 classic 没有的 dev 新场景, 显式提示。
    if _bath_repair_starved_by_normal_fight(cfg):
        _log.warning(
            '[daily] 已启用浴室修理, 但存在无限常规战 (times 未设置) 且未开启任何'
            '停止上限 (stop_max_ship / stop_max_loot / quick_repair_limit)。'
            '常规战会持续抢占浴室修理, 后者将永远不会执行。请为常规战设置 times '
            '或开启任一停止上限。',
        )

    if not scheduler._triggers:
        _log.warning('[daily] 未启用任何日常任务, run_daily 将空转')


def _bath_repair_starved_by_normal_fight(cfg: DailyAutomationConfig) -> bool:
    """无限常规战是否会持续抢占浴室修理、致其永不执行。

    条件: 启用浴室修理 + 启用常规战 + 存在 ``times=None`` 的常规战任务 +
    三个停止上限 (stop_max_ship / stop_max_loot / quick_repair_limit) 全关。
    抽成纯函数便于单测。
    """
    return (
        cfg.auto_bath_repair
        and cfg.auto_normal_fight
        and bool(cfg.normal_fight_tasks)
        and any(task.times is None for task in cfg.normal_fight_tasks)
        and not (cfg.stop_max_ship or cfg.stop_max_loot or cfg.quick_repair_limit)
    )


def _register_normal_fight(
    scheduler: TaskScheduler,
    cfg: DailyAutomationConfig,
    *,
    plan_root: str | Path | None = None,
) -> None:
    """把 normal_fight_tasks 翻译成 NormalFightPlan 列表并注册触发器。

    *plan_root* 透传给 :func:`get_normal_fight_plan`, 用户自定义目录优先。
    """
    from autowsgr.combat.fleet import resolve_fleet_selection
    from autowsgr.ops.normal_fight import NormalFightRunner, get_normal_fight_plan

    plans: list[NormalFightPlan] = []
    for task in cfg.normal_fight_tasks:
        try:
            plan = get_normal_fight_plan(task.name, plan_root=plan_root)
        except Exception as exc:
            _log.opt(exception=True).warning(
                '[daily] 无法解析常规战计划 {!r}, 跳过: {}',
                task.name,
                exc,
            )
            continue
        fleet_id = task.fleet_id or plan.fleet_id or 1
        plans.append(
            NormalFightPlan(
                # 默认参数捕获 plan/fleet, 避免闭包晚绑定
                factory=lambda c, p=plan, f=fleet_id: NormalFightRunner(
                    c,
                    p,
                    resolve_fleet_selection(p, fleet_id=f),
                ),
                name=task.name,
                fleet_id=fleet_id,
                target=task.times,  # None = 无限 (空闲填充)
            ),
        )

    if not plans:
        _log.warning('[daily] 常规战任务列表为空或全部解析失败, 跳过常规战触发器')
        return

    scheduler.register_trigger(
        NormalFightTrigger(
            priority=PRIO_NORMAL_FIGHT,
            name='常规战',
            plans=plans,
            stop_max_ship=cfg.stop_max_ship,
            stop_max_loot=cfg.stop_max_loot,
            quick_repair_limit=cfg.quick_repair_limit,
        ),
    )
