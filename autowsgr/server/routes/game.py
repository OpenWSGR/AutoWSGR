"""游戏状态查询路由 — /api/game/*, /api/expedition/status, /api/build/status"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from autowsgr.infra.logger import get_logger
from autowsgr.server.schemas import ApiResponse
from autowsgr.server.serializers import (
    serialize_build_queue,
    serialize_expedition_queue,
    serialize_fleet,
    serialize_resources,
)
from autowsgr.server.task_manager import task_manager

from ..main import get_context


_log = get_logger('server')

router = APIRouter(tags=['game'])


@router.get('/api/game/acquisition', response_model=ApiResponse)
async def game_acquisition():
    """从出征面板截图 OCR 识别今日舰船 (X/500) 与战利品 (X/50) 获取数量。

    仅在空闲时可用 (需要控制画面导航到出征面板)。
    """
    try:
        ctx = get_context()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    if task_manager.is_running:
        raise HTTPException(status_code=409, detail='任务执行中，无法查询获取数量')

    from autowsgr.ops.navigate import goto_page
    from autowsgr.ui.map.page import MapPage

    def _recognize() -> dict[str, int | None]:
        goto_page(ctx, '地图页面')
        map_page = MapPage(ctx)
        counts = map_page.get_acquisition_counts()
        return {
            'ship_count': counts.ship_count,
            'ship_max': counts.ship_max,
            'loot_count': counts.loot_count,
            'loot_max': counts.loot_max,
        }

    try:
        data = await asyncio.to_thread(_recognize)
        return ApiResponse(success=True, data=data, message='获取数量识别完成')
    except Exception as e:
        _log.opt(exception=True).warning('[API] 获取数量识别失败: {}', e)
        return ApiResponse(success=False, error=str(e))


@router.get('/api/game/context', response_model=ApiResponse)
async def game_context_info():
    """返回当前游戏上下文中的运行时状态。

    包含资源、舰队、远征、建造等完整游戏状态数据。
    不需要截图或画面操作，直接读取内存中的状态。
    """
    try:
        ctx = get_context()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    return ApiResponse(
        success=True,
        data={
            'dropped_ship_count': ctx.dropped_ship_count,
            'dropped_loot_count': ctx.dropped_loot_count,
            'quick_repair_used': ctx.quick_repair_used,
            'current_page': ctx.current_page,
            'resources': serialize_resources(ctx.resources),
            'fleets': [serialize_fleet(f) for f in ctx.fleets],
            'expeditions': serialize_expedition_queue(ctx.expeditions),
            'build_queue': serialize_build_queue(ctx.build_queue),
        },
    )


@router.get('/api/expedition/status', response_model=ApiResponse)
async def expedition_status():
    """查询远征槽位状态（4 个槽位的章节、节点、剩余时间等）。"""
    try:
        ctx = get_context()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    return ApiResponse(
        success=True,
        data=serialize_expedition_queue(ctx.expeditions),
    )


@router.get('/api/build/status', response_model=ApiResponse)
async def build_status():
    """查询建造队列状态。"""
    try:
        ctx = get_context()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    return ApiResponse(
        success=True,
        data=serialize_build_queue(ctx.build_queue),
    )
