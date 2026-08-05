"""活动战斗操作 — 活动地图 (Event) 战斗 (兼容入口)。

自 event/normal 融合后, 活动战统一由
:class:`~autowsgr.ops.normal_fight.NormalFightRunner` 按 ``plan.chapter``
(E/H vs 数字) 自动路由到活动地图导航; 入口 (α/β) 从 ``plan.map``
(如 ``1a``) 解析。本模块保留 :class:`EventFightRunner` 与 ``run_event_fight*``
作为兼容入口, 供 server / examples / 旧代码使用, 内部全部委托
:class:`NormalFightRunner`。

新代码建议直接用 ``run_normal_fight`` / :class:`NormalFightRunner` ——
把活动 plan (chapter=E/H) 放进 ``normal_fight_tasks`` 即可由 auto_daily 调度,
无需为活动单独配置/调用。

使用方式::

    from autowsgr.ops import run_event_fight_from_yaml

    results = run_event_fight_from_yaml(ctx, '激斗漩涡H1a', times=5)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from autowsgr.combat import CombatPlan, CombatResult
from autowsgr.combat.fleet import (
    FleetSlotRule,
    ResolvedFleetSelection,
    resolve_fleet_selection,
    validate_fleet_selection_arguments,
)
from autowsgr.infra.logger import get_logger
from autowsgr.ops.normal_fight import NormalFightRunner


if TYPE_CHECKING:
    from collections.abc import Sequence

    from autowsgr.context import GameContext

_log = get_logger('ops')


# ═══════════════════════════════════════════════════════════════════════════════
# 活动战斗执行器 (兼容薄包装)
# ═══════════════════════════════════════════════════════════════════════════════


class EventFightRunner(NormalFightRunner):
    """[已融合] 活动战斗执行器 — 委托 :class:`NormalFightRunner`。

    活动战与常规战已融合: 由 ``plan.chapter`` (E/H vs 数字) 决定导航入口,
    活动地图代号 (如 ``"H1"``) 与入口 (α/β) 均从 ``plan`` 推导。
    本类保留为兼容薄包装, 不再有独立的活动战逻辑, 所有方法继承自
    :class:`NormalFightRunner`。

    Parameters
    ----------
    ctx, plan:
        见 :class:`NormalFightRunner`。
    entrance:
        入口 override (兼容旧 API, ``"alpha"``/``"beta"``);
        不传则从 ``plan.map`` (如 ``1a``) 推导。
    event_name:
        活动 plan 目录名 override (兼容旧 API); 不传则用 ``plan.event_name``。
    map_code:
        已废弃 (从 ``plan`` 推导), 仅为兼容旧签名保留, 传入时忽略。
    """

    def __init__(
        self,
        ctx: GameContext,
        plan: CombatPlan,
        fleet_selection: ResolvedFleetSelection | None = None,
        *,
        fleet_id: int | None = None,
        fleet: Sequence[str] | None = None,
        fleet_rules: Sequence[FleetSlotRule] | None = None,
        map_code: str | None = None,  # noqa: ARG002 - 已废弃, 仅为兼容旧签名保留
        entrance: Literal['alpha', 'beta'] | None = None,
        event_name: str | None = None,
    ) -> None:
        # entrance override: 覆盖 plan.entrance (UI 层 a/b ↔ α/β)
        if entrance is not None:
            plan.entrance = 'a' if entrance == 'alpha' else 'b'
        # event_name override: 回填 plan.event_name
        if event_name and not plan.event_name:
            plan.event_name = event_name
        super().__init__(
            ctx,
            plan,
            fleet_selection,
            fleet_id=fleet_id,
            fleet=fleet,
            fleet_rules=fleet_rules,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════════════════════════════


def run_event_fight(
    ctx: GameContext,
    plan: CombatPlan,
    *,
    map_code: str | None = None,
    entrance: Literal['alpha', 'beta'] | None = None,
    times: int = 1,
    gap: float = 0.0,
    fleet_id: int | None = None,
    fleet: Sequence[str] | None = None,
    fleet_rules: Sequence[FleetSlotRule] | None = None,
    fleet_selection: ResolvedFleetSelection | None = None,
) -> list[CombatResult]:
    """执行活动战的便捷函数 (兼容入口, 委托 :class:`NormalFightRunner`)。

    自融合后活动地图代号与入口均从 ``plan`` 推导; *map_code* / *entrance*
    仅作 override (兼容旧调用方), 不传亦可。

    Parameters
    ----------
    ctx:
        游戏上下文。
    plan:
        战斗计划 (``chapter`` 应为 E/H)。
    map_code:
        已废弃 (从 plan 推导), 传入忽略。
    entrance:
        入口 override (``"alpha"``/``"beta"``); 不传则从 ``plan.map`` 推导。
    times:
        重复次数。
    gap:
        每次间隔 (秒)。

    Returns
    -------
    list[CombatResult]
    """
    validate_fleet_selection_arguments(
        fleet_selection,
        fleet_id=fleet_id,
        fleet=fleet,
        slot_rules=fleet_rules,
    )
    resolved_selection = fleet_selection or resolve_fleet_selection(
        plan,
        fleet_id=fleet_id,
        fleet=fleet,
        slot_rules=fleet_rules,
    )
    runner = EventFightRunner(
        ctx,
        plan,
        resolved_selection,
        map_code=map_code,
        entrance=entrance,
    )
    return runner.run_for_times(times, gap=gap)


def run_event_fight_from_yaml(
    ctx: GameContext,
    yaml_path: str,
    *,
    map_code: str | None = None,
    entrance: Literal['alpha', 'beta'] | None = None,
    times: int = 1,
    fleet_id: int | None = None,
    fleet: Sequence[str] | None = None,
    fleet_rules: Sequence[FleetSlotRule] | None = None,
) -> list[CombatResult]:
    """从 YAML 文件加载计划并执行活动战 (兼容入口)。

    *yaml_path* 支持以下格式:

    - 绝对路径 / 相对路径: 直接加载。
    - 策略名称 (如 ``"激斗漩涡H1a"``): 自动在 ``autowsgr/data/plan/event/``
      包数据目录中查找, 可省略 ``.yaml`` 后缀。

    Parameters
    ----------
    ctx:
        游戏上下文。
    yaml_path:
        YAML 配置路径或策略名称。
    map_code:
        已废弃 (从 plan 推导), 传入忽略。
    entrance:
        入口 override; 不传则从 ``plan.map`` 推导。
    times:
        重复次数。
    fleet_id:
        舰队 ID。
    fleet:
        舰船列表。

    Returns
    -------
    list[CombatResult]
    """
    from autowsgr.infra.file_utils import resolve_plan_path

    resolved = resolve_plan_path(yaml_path, category='event')
    plan = CombatPlan.from_yaml(resolved)
    return run_event_fight(
        ctx,
        plan,
        map_code=map_code,
        entrance=entrance,
        times=times,
        fleet_id=fleet_id,
        fleet=fleet,
        fleet_rules=fleet_rules,
    )
