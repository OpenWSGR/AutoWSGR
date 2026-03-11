"""健康检查路由 — /api/health"""

from __future__ import annotations

import time

from fastapi import APIRouter

from autowsgr.server.schemas import ApiResponse
from autowsgr.server.task_manager import task_manager

from .. import main as _main


router = APIRouter(tags=['health'])

_server_start_time = time.monotonic()


@router.get('/api/health', response_model=ApiResponse)
async def health_check():
    """健康检查端点。"""
    uptime = int(time.monotonic() - _server_start_time)
    task_info = None
    if task_manager.current_task and task_manager.is_running:
        task_info = {
            'task_id': task_manager.current_task.task_id,
            'status': task_manager.current_task.status.value,
        }

    return ApiResponse(
        success=True,
        data={
            'status': 'ok',
            'uptime_seconds': uptime,
            'emulator_connected': _main._ctx is not None,
            'current_task': task_info,
        },
    )
