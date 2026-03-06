"""FastAPI 主应用 — HTTP REST API 和 WebSocket 端点。

本模块提供以下接口:
- POST /api/task/start       — 启动任务 (异步执行)
- POST /api/task/stop        — 停止任务
- GET  /api/task/status      — 查询状态
- POST /api/expedition/check — 检查并收取远征
- WS   /ws/logs              — 实时日志流
- WS   /ws/task              — 任务状态更新

使用方式:
    uvicorn autowsgr.server.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Discriminator

from autowsgr.infra.logger import get_logger
from autowsgr.server.schemas import (
    ApiResponse,
    CampaignRequest,
    DecisiveRequest,
    EventFightRequest,
    ExerciseRequest,
    NormalFightRequest,
)
from autowsgr.server.task_manager import task_manager
from autowsgr.server.ws_manager import ws_manager


_log = get_logger('server')


# ═══════════════════════════════════════════════════════════════════════════════
# 全局状态
# ═══════════════════════════════════════════════════════════════════════════════

# GameContext 全局引用 (启动后设置)
_ctx: Any = None


def get_context() -> Any:
    """获取全局 GameContext。"""
    global _ctx
    if _ctx is None:
        raise RuntimeError('系统未启动，请先调用 POST /api/system/start')
    return _ctx


# ═══════════════════════════════════════════════════════════════════════════════
# 生命周期管理
# ═══════════════════════════════════════════════════════════════════════════════


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理。"""
    # 启动时: 设置事件循环引用
    loop = asyncio.get_running_loop()
    task_manager.set_loop(loop)
    _log.info('[Server] HTTP Server 已启动')

    yield

    # 关闭时: 清理资源
    global _ctx
    if _ctx is not None:
        _log.info('[Server] 断开模拟器连接')
        # 如果需要，可以在这里调用清理逻辑
    _log.info('[Server] HTTP Server 已关闭')


# ═══════════════════════════════════════════════════════════════════════════════
# FastAPI 应用
# ═══════════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title='AutoWSGR HTTP API',
    description='战舰少女R 自动化脚本 HTTP 接口',
    version='1.0.0',
    lifespan=lifespan,
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],  # 生产环境应限制
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


# ═══════════════════════════════════════════════════════════════════════════════
# 系统管理接口
# ═══════════════════════════════════════════════════════════════════════════════


class SystemStartRequest(BaseModel):
    """系统启动请求。"""

    config_path: str | None = None


@app.post('/api/system/start', response_model=ApiResponse)
async def system_start(request: SystemStartRequest):
    """启动系统 (连接模拟器、启动游戏)。"""
    global _ctx

    if _ctx is not None:
        return ApiResponse(success=True, message='系统已启动')

    try:
        from autowsgr.scheduler import launch

        config_path = request.config_path or 'usersettings.yaml'
        _log.info('[System] 正在启动, 配置: {}', config_path)
        _ctx = launch(config_path)
        _log.info('[System] 启动成功')

        return ApiResponse(success=True, message='系统启动成功')

    except Exception as e:
        _log.error('[System] 启动失败: {}', e)
        return ApiResponse(success=False, error=str(e))


@app.post('/api/system/stop', response_model=ApiResponse)
async def system_stop():
    """停止系统。"""
    global _ctx

    if _ctx is None:
        return ApiResponse(success=True, message='系统未运行')

    # 先停止正在运行的任务
    if task_manager.is_running:
        task_manager.stop_task()

    _ctx = None
    _log.info('[System] 系统已停止')
    return ApiResponse(success=True, message='系统已停止')


@app.get('/api/system/status', response_model=ApiResponse)
async def system_status():
    """获取系统状态。"""
    return ApiResponse(
        success=True,
        data={
            'status': task_manager.current_task.status.value
            if task_manager.current_task
            else 'idle',
            'emulator_connected': _ctx is not None,
            'game_running': _ctx is not None,
            'current_task': task_manager.current_task.task_id
            if task_manager.current_task
            else None,
        },
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 任务执行接口
# ═══════════════════════════════════════════════════════════════════════════════


TaskRequestUnion = Annotated[
    NormalFightRequest | EventFightRequest | CampaignRequest | ExerciseRequest | DecisiveRequest,
    Discriminator('type'),
]


@app.post('/api/task/start', response_model=ApiResponse)
async def task_start(
    request: TaskRequestUnion,
):  # type: ignore
    """启动任务 (异步执行，立即返回)。"""
    if task_manager.is_running:
        raise HTTPException(status_code=409, detail='已有任务正在运行')

    try:
        ctx = get_context()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # 将任务管理器的停止事件绑定到游戏上下文
    ctx.stop_event = task_manager._stop_event

    # 根据任务类型分发
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


async def _start_normal_fight(ctx: Any, request: NormalFightRequest) -> ApiResponse:
    """启动常规战任务。"""
    from autowsgr.combat import CombatPlan
    from autowsgr.ops import run_normal_fight

    def executor(task_info: Any) -> list[dict[str, Any]]:
        """执行常规战。"""
        results = []

        # 构建或加载计划
        if request.plan_id:
            plan = CombatPlan.from_yaml(request.plan_id)
        elif request.plan:
            plan = _build_combat_plan(request.plan)
        else:
            raise ValueError('必须提供 plan 或 plan_id')

        for i in range(request.times):
            if task_manager.should_stop():
                break

            task_manager.update_progress(current_round=i + 1)
            _log.info('[Task] 常规战第 {}/{} 轮', i + 1, request.times)

            try:
                result = run_normal_fight(ctx, plan, times=1)[0]
                results.append(_convert_combat_result(result, i + 1))
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
            plan = _build_combat_plan(request.plan)
        else:
            raise ValueError('必须提供 plan 或 plan_id')

        fleet_id = request.fleet_id or plan.fleet_id

        for i in range(request.times):
            if task_manager.should_stop():
                break

            task_manager.update_progress(current_round=i + 1)
            _log.info('[Task] 活动战第 {}/{} 轮', i + 1, request.times)

            try:
                result = run_event_fight(ctx, plan, times=1, fleet_id=fleet_id)[0]
                results.append(_convert_combat_result(result, i + 1))
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
            times=request.times,
        )

        results = []
        for i in range(request.times):
            if task_manager.should_stop():
                break

            task_manager.update_progress(current_round=i + 1)
            _log.info('[Task] 战役第 {}/{} 轮', i + 1, request.times)

            try:
                result = runner.run()
                # CampaignRunner.run() 返回完整结果列表
                results.append(
                    {
                        'round': i + 1,
                        'success': True,
                    }
                )
                task_manager.add_result(results[-1])
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
            return [{'round': i + 1, 'success': True} for i in range(len(results))]
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
            level1=request.level1,
            level2=request.level2,
            flagship_priority=request.flagship_priority,
        )

        controller = DecisiveController(ctx, config)
        task_manager.update_progress(current_round=1, current_node='决战')

        try:
            result = controller.run()
            return [{'round': 1, 'success': True, 'result': result.value}]
        except Exception as e:
            return [{'round': 1, 'success': False, 'error': str(e)}]

    task_id = task_manager.start_task(
        task_type='decisive',
        total_rounds=1,
        executor=executor,
    )

    return ApiResponse(
        success=True,
        data={'task_id': task_id, 'status': 'running'},
        message='任务已启动',
    )


@app.post('/api/task/stop', response_model=ApiResponse)
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


@app.get('/api/task/status', response_model=ApiResponse)
async def task_status():
    """查询当前任务状态。"""
    status = task_manager.get_status()
    return ApiResponse(success=True, data=status)


# ═══════════════════════════════════════════════════════════════════════════════
# 远征接口
# ═══════════════════════════════════════════════════════════════════════════════


@app.post('/api/expedition/check', response_model=ApiResponse)
async def expedition_check():
    """检查并收取已完成的远征。"""
    try:
        ctx = get_context()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    if task_manager.is_running:
        raise HTTPException(status_code=409, detail='任务执行中，无法检查远征')

    from autowsgr.ops.expedition import collect_expedition

    try:
        result = await asyncio.to_thread(collect_expedition, ctx)
        return ApiResponse(
            success=True,
            data={'collected': result},
            message='远征检查完成',
        )
    except Exception as e:
        _log.opt(exception=True).warning('[API] 远征检查失败: {}', e)
        return ApiResponse(success=False, error=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# WebSocket 接口
# ═══════════════════════════════════════════════════════════════════════════════


@app.websocket('/ws/logs')
async def ws_logs(websocket: WebSocket):
    """实时日志流。"""
    await ws_manager.connect(websocket)
    try:
        while True:
            # 保持连接，等待客户端消息或断开
            data = await websocket.receive_text()
            # 可以处理客户端发来的控制消息
            try:
                msg = json.loads(data)
                if msg.get('type') == 'ping':
                    await websocket.send_text(json.dumps({'type': 'pong'}))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)


@app.websocket('/ws/task')
async def ws_task(websocket: WebSocket):
    """任务状态更新流。"""
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get('type') == 'ping':
                    await websocket.send_text(json.dumps({'type': 'pong'}))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════════


def _build_combat_plan(request: Any) -> Any:
    """从请求构建 CombatPlan 对象。"""
    from autowsgr.combat import CombatPlan, NodeDecision
    from autowsgr.types import Formation, RepairMode

    # 转换节点决策
    def build_node_decision(node_req: Any) -> NodeDecision:
        return NodeDecision(
            formation=Formation(node_req.formation),
            night=node_req.night,
            proceed=node_req.proceed,
            proceed_stop=[RepairMode(r) for r in node_req.proceed_stop],
            detour=node_req.detour,
        )

    node_args = {k: build_node_decision(v) for k, v in request.node_args.items()}

    return CombatPlan(
        name=request.name,
        mode=request.mode,
        chapter=request.chapter,
        map_id=request.map,
        fleet_id=request.fleet_id,
        fleet=request.fleet,
        repair_mode=[RepairMode(r) for r in request.repair_mode],
        fight_condition=request.fight_condition,
        selected_nodes=request.selected_nodes,
        default_node=build_node_decision(request.node_defaults),
        nodes=node_args,
    )


def _convert_combat_result(result: Any, round_num: int) -> dict[str, Any]:
    """转换 CombatResult 为响应格式。"""
    # 提取节点列表
    nodes = []
    if result.history:
        for event in result.history.events:
            if event.node and event.node not in nodes:
                nodes.append(event.node)

    # 提取 MVP
    mvp = None
    if result.history:
        fight_results = result.history.get_fight_results()
        if isinstance(fight_results, dict):
            for fr in fight_results.values():
                if fr.mvp and fr.mvp > 0:
                    # MVP 是位置 (1-6)，需要转换
                    mvp = f'位置{fr.mvp}'
                    break

    return {
        'round': round_num,
        'success': result.flag.value == 'success',
        'nodes': nodes,
        'mvp': mvp,
        'ship_damage': [s.value for s in result.ship_stats] if result.ship_stats else [],
        'node_count': result.node_count,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host='0.0.0.0', port=8000)
