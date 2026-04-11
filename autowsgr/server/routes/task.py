"""任务执行路由 — /api/task/*"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException
from pydantic import Discriminator

from autowsgr.infra.logger import get_logger
from autowsgr.server.schemas import (
    ApiResponse,
    CampaignRequest,
    DecisiveRequest,
    EventFightRequest,
    ExerciseRequest,
    NormalFightRequest,
)
from autowsgr.server.serializers import build_combat_plan, convert_combat_result
from autowsgr.server.task_manager import task_manager

from ..main import get_context


_log = get_logger('server')

router = APIRouter(prefix='/api/task', tags=['task'])


TaskRequestUnion = Annotated[
    NormalFightRequest | EventFightRequest | CampaignRequest | ExerciseRequest | DecisiveRequest,
    Discriminator('type'),
]


@router.post('/start', response_model=ApiResponse)
async def task_start(request: TaskRequestUnion):  # type: ignore
    """启动任务 (异步执行，立即返回)。"""
    if task_manager.is_running:
        raise HTTPException(status_code=409, detail='已有任务正在运行')

    try:
        ctx = get_context()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    ctx.stop_event = task_manager._stop_event

    if isinstance(request, NormalFightRequest):
        return await _start_normal_fight(ctx, request)
    elif isinstance(request, EventFightRequest):
        return await _start_event_fight(ctx, request)
    elif isinstance(request, CampaignRequest):
        return await _start_campaign(ctx, request)
    elif isinstance(request, ExerciseRequest):
        return await _start_exercise(ctx, request)
    elif isinstance(request, DecisiveRequest):
        return await _start_decisive(ctx, request)
    else:
        raise HTTPException(status_code=400, detail='未知的任务类型')


@router.post('/stop', response_model=ApiResponse)
async def task_stop():
    """停止当前任务。"""
    if not task_manager.is_running:
        return ApiResponse(success=True, message='没有正在运行的任务')

    success = task_manager.stop_task()
    if success:
        return ApiResponse(
            success=True,
            data={
                'task_id': task_manager.current_task.task_id,
                'status': 'stopped',
            },
            message='已请求停止任务',
        )
    else:
        return ApiResponse(success=False, error='停止失败')


@router.get('/status', response_model=ApiResponse)
async def task_status():
    """查询当前任务状态。"""
    status = task_manager.get_status()
    return ApiResponse(success=True, data=status)


# ═══════════════════════════════════════════════════════════════════════════════
# 任务启动辅助
# ═══════════════════════════════════════════════════════════════════════════════


async def _start_normal_fight(ctx: Any, request: NormalFightRequest) -> ApiResponse:
    """启动常规战任务。"""
    from autowsgr.combat import CombatPlan
    from autowsgr.ops import run_normal_fight

    def executor(task_info: Any) -> list[dict[str, Any]]:
        results = []

        if request.plan_id:
            plan = CombatPlan.from_yaml(request.plan_id)
        elif request.plan:
            plan = build_combat_plan(request.plan)
        else:
            raise ValueError('必须提供 plan 或 plan_id')

        # 允许 plan_id + plan 覆盖: 前端可在不改 YAML 的情况下动态指定舰队与舰船名单。
        request_plan = request.plan
        override_fleet_id = request_plan.fleet_id if request_plan is not None else None
        override_fleet = request_plan.fleet if request_plan is not None else None
        override_fleet_rules = request_plan.fleet_rules if request_plan is not None else None

        for i in range(request.times):
            if task_manager.should_stop():
                break

            task_manager.update_progress(current_round=i + 1)
            _log.info('[Task] 常规战第 {}/{} 轮', i + 1, request.times)

            try:
                result = run_normal_fight(
                    ctx,
                    plan,
                    times=1,
                    fleet_id=override_fleet_id,
                    fleet=override_fleet,
                    fleet_rules=override_fleet_rules,
                )[0]
                results.append(convert_combat_result(result, i + 1))
                task_manager.add_result(results[-1])
            except Exception as e:
                _log.error('[Task] 第 {} 轮失败: {}', i + 1, e)
                results.append({'round': i + 1, 'success': False, 'error': str(e)})

        return results

    task_id = task_manager.start_task(
        task_type='normal_fight',
        total_rounds=request.times,
        executor=executor,
    )

    return ApiResponse(
        success=True,
        data={'task_id': task_id, 'status': 'running'},
        message='任务已启动',
    )


async def _start_event_fight(ctx: Any, request: EventFightRequest) -> ApiResponse:
    """启动活动战任务。"""
    from autowsgr.combat import CombatPlan
    from autowsgr.ops import run_event_fight

    def executor(task_info: Any) -> list[dict[str, Any]]:
        results = []

        if request.plan_id:
            plan = CombatPlan.from_yaml(request.plan_id)
        elif request.plan:
            plan = build_combat_plan(request.plan)
        else:
            raise ValueError('必须提供 plan 或 plan_id')

        request_plan = request.plan
        override_fleet = request_plan.fleet if request_plan is not None else None
        override_fleet_rules = request_plan.fleet_rules if request_plan is not None else None
        # 优先级: 顶层 fleet_id > plan 覆盖 fleet_id > YAML 内 fleet_id
        if request.fleet_id is not None:
            fleet_id = request.fleet_id
        elif request_plan is not None and request_plan.fleet_id is not None:
            fleet_id = request_plan.fleet_id
        else:
            fleet_id = plan.fleet_id

        for i in range(request.times):
            if task_manager.should_stop():
                break

            task_manager.update_progress(current_round=i + 1)
            _log.info('[Task] 活动战第 {}/{} 轮', i + 1, request.times)

            try:
                result = run_event_fight(
                    ctx,
                    plan,
                    times=1,
                    fleet_id=fleet_id,
                    fleet=override_fleet,
                    fleet_rules=override_fleet_rules,
                )[0]
                results.append(convert_combat_result(result, i + 1))
                task_manager.add_result(results[-1])
            except Exception as e:
                _log.error('[Task] 第 {} 轮失败: {}', i + 1, e)
                results.append({'round': i + 1, 'success': False, 'error': str(e)})

        return results

    task_id = task_manager.start_task(
        task_type='event_fight',
        total_rounds=request.times,
        executor=executor,
    )

    return ApiResponse(
        success=True,
        data={'task_id': task_id, 'status': 'running'},
        message='任务已启动',
    )


async def _start_campaign(ctx: Any, request: CampaignRequest) -> ApiResponse:
    """启动战役任务。"""
    from autowsgr.ops import CampaignRunner

    def executor(task_info: Any) -> list[dict[str, Any]]:
        runner = CampaignRunner(
            ctx,
            campaign_name=request.campaign_name,
            times=1,
        )

        results = []
        for i in range(request.times):
            if task_manager.should_stop():
                break

            task_manager.update_progress(current_round=i + 1)
            _log.info('[Task] 战役第 {}/{} 轮', i + 1, request.times)

            try:
                result = runner.run()
                for j, r in enumerate(result):
                    converted = convert_combat_result(r, i * len(result) + j + 1)
                    results.append(converted)
                    task_manager.add_result(converted)
            except Exception as e:
                _log.error('[Task] 第 {} 轮失败: {}', i + 1, e)
                results.append({'round': i + 1, 'success': False, 'error': str(e)})

        return results

    task_id = task_manager.start_task(
        task_type='campaign',
        total_rounds=request.times,
        executor=executor,
    )

    return ApiResponse(
        success=True,
        data={'task_id': task_id, 'status': 'running'},
        message='任务已启动',
    )


async def _start_exercise(ctx: Any, request: ExerciseRequest) -> ApiResponse:
    """启动演习任务。"""
    from autowsgr.ops import ExerciseRunner

    def executor(task_info: Any) -> list[dict[str, Any]]:
        runner = ExerciseRunner(ctx, fleet_id=request.fleet_id)
        task_manager.update_progress(current_round=1, current_node='演习')

        try:
            results = runner.run()
            return [convert_combat_result(r, i + 1) for i, r in enumerate(results)]
        except Exception as e:
            return [{'round': 1, 'success': False, 'error': str(e)}]

    task_id = task_manager.start_task(
        task_type='exercise',
        total_rounds=1,
        executor=executor,
    )

    return ApiResponse(
        success=True,
        data={'task_id': task_id, 'status': 'running'},
        message='任务已启动',
    )


async def _start_decisive(ctx: Any, request: DecisiveRequest) -> ApiResponse:
    """启动决战任务。"""
    from autowsgr.infra import DecisiveConfig
    from autowsgr.ops import DecisiveController

    def executor(task_info: Any) -> list[dict[str, Any]]:
        config = DecisiveConfig(
            chapter=request.chapter,
            decisive_rounds=request.decisive_rounds,
            level1=request.level1,
            level2=request.level2,
            flagship_priority=request.flagship_priority,
            use_quick_repair=request.use_quick_repair,
        )

        controller = DecisiveController(ctx, config)
        results: list[dict[str, Any]] = []

        try:
            for i in range(request.decisive_rounds):
                if task_manager.should_stop():
                    break

                task_manager.update_progress(current_round=i + 1, current_node='决战')
                _log.info('[Task] 决战第 {}/{} 轮', i + 1, request.decisive_rounds)
                result = controller.run()
                converted = {'round': i + 1, 'success': True, 'result': result.value}
                results.append(converted)
                task_manager.add_result(converted)

                if result.value in {'leave', 'error'}:
                    _log.warning('[Task] 决战第 {} 轮终止: {}', i + 1, result.value)
                    break
        except Exception as e:
            results.append({'round': len(results) + 1, 'success': False, 'error': str(e)})

        return results

    task_id = task_manager.start_task(
        task_type='decisive',
        total_rounds=request.decisive_rounds,
        executor=executor,
    )

    return ApiResponse(
        success=True,
        data={'task_id': task_id, 'status': 'running'},
        message='任务已启动',
    )
