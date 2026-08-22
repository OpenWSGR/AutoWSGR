"""按 YAML 计划的一次性出击 — 触发器模式封装。

把 :func:`TaskScheduler.run_daily` 的常驻挂机循环收窄为"单个 YAML 计划打满
达标次数即退出": 战果要求 (``node_args`` 各节点的 ``grade``) 不达标的场次
不计入次数并自动重打, 全部达标后由看门狗置停止信号收尾。

典型用法 (周常/活动日常等一次性脚本)::

    from autowsgr.scheduler import launch
    from autowsgr.scheduler.plan_runner import run_yaml_plan

    ctx = launch('usersettings.full.yaml')
    results = run_yaml_plan(ctx, './week/1.yaml', times=1, fleet_id=2)
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from autowsgr.combat.fleet import (
    FleetSelectionSource,
    ResolvedFleetSelection,
    resolve_fleet_selection,
)
from autowsgr.infra.logger import get_logger
from autowsgr.ops.normal_fight import NormalFightRunner, get_normal_fight_plan
from autowsgr.scheduler.scheduler import TaskScheduler
from autowsgr.scheduler.triggers import NormalFightPlan, NormalFightTrigger


if TYPE_CHECKING:
    from pathlib import Path

    from autowsgr.combat import CombatResult
    from autowsgr.context import GameContext

_log = get_logger('scheduler')

# 看门狗轮询间隔 (秒): all_done 检查频率, 无需太密
_POLL_INTERVAL = 5.0


def run_yaml_plan(
    ctx: GameContext,
    yaml_path: str,
    *,
    times: int = 1,
    fleet_id: int | None = None,
    keep_fleet: bool = False,
    plan_root: str | Path | None = None,
) -> list[CombatResult]:
    """按 YAML 计划执行常规战, 打满达标次数后自动退出。

    与 :func:`~autowsgr.ops.normal_fight.run_normal_fight_from_yaml` 的区别:
    本函数走触发器计数 (:class:`NormalFightTrigger`), plan 中配置了战果要求
    (``node_args`` 下 ``grade``) 时, 只有战果全部达标的场次才计入 *times*;
    评级不足 / SL 重开的场次不计入并自动重打。

    阻塞直到完成或 ``ctx.stop_event`` 被置位; 返回已执行的场次结果
    (含未达标场, 供排查)。远征收取请在外部自行调用 :func:`collect_expedition`。

    Parameters
    ----------
    ctx:
        游戏上下文 (:func:`launch` 返回)。
    yaml_path:
        计划文件路径或策略名 (同 :func:`get_normal_fight_plan`)。
    times:
        目标达标次数。
    fleet_id:
        出击舰队编号; ``None`` 则用 plan 内配置。
    keep_fleet:
        ``True`` 则忽略 plan 内的 ``fleet`` / ``fleet_presets`` 换船配置,
        只选 *fleet_id* 舰队出征、不更换队伍编制 (沿用游戏内现有编成);
        默认 ``False``, 按 plan 配置换船。
    plan_root:
        用户自定义计划根目录 (同 :func:`get_normal_fight_plan`)。

    Returns
    -------
    list[CombatResult]
        全部尝试场次的结果列表 (含未达标场)。
    """
    plan = get_normal_fight_plan(yaml_path, plan_root=plan_root)
    resolved_fleet_id = fleet_id or plan.fleet_id or 1

    if keep_fleet:
        # 无换船规则: 只选舰队编号, 不动编制 (source=NONE → runner 跳过 change_fleet)
        selection = ResolvedFleetSelection(
            fleet_id=resolved_fleet_id,
            slot_rules=None,
            plain_fleet=None,
            source=FleetSelectionSource.NONE,
        )
    else:
        selection = resolve_fleet_selection(plan, fleet_id=fleet_id)

    fight_plan = NormalFightPlan(
        # 默认参数捕获 selection, 避免闭包晚绑定
        factory=lambda c, p=plan, s=selection: NormalFightRunner(c, p, s),
        name=str(yaml_path),
        fleet_id=resolved_fleet_id,
        target=times,
        conditions=plan.conditions,  # 镜像只读: 触发器按条件计数
    )
    trigger = NormalFightTrigger(priority=100, name='计划出击', plans=[fight_plan])
    scheduler = TaskScheduler(ctx, expedition_interval=0)
    scheduler.register_trigger(trigger)

    # 打满即退: run_daily 是常驻挂机循环, 由看门狗在本计划达标后置停止信号收尾。
    # completed 由触发器 on_done 原地更新 (同一对象引用), 此处直接读自身状态即可
    def _watchdog() -> None:
        while not ctx.stop_event.is_set():
            if fight_plan.completed >= times:
                _log.info('[PlanRunner] {} 已打满 {} 次达标场次, 停止调度', yaml_path, times)
                ctx.stop_event.set()
                return
            ctx.stop_event.wait(_POLL_INTERVAL)

    watchdog = threading.Thread(target=_watchdog, daemon=True, name='plan-runner-watchdog')
    watchdog.start()
    try:
        scheduler.run_daily()
    finally:
        ctx.stop_event.set()  # 兜底唤醒看门狗, 避免 join 卡死
        watchdog.join()
    return scheduler.tasks[0].results if scheduler.tasks else []
