"""系统管理路由 — /api/system/*"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from autowsgr.infra.logger import get_logger
from autowsgr.server.schemas import ApiResponse
from autowsgr.server.task_manager import task_manager

from .. import main as _main


_log = get_logger('server')

router = APIRouter(prefix='/api/system', tags=['system'])


class SystemStartRequest(BaseModel):
    """系统启动请求。"""

    config_path: str | None = None


@router.post('/start', response_model=ApiResponse)
async def system_start(request: SystemStartRequest):
    """启动系统 (连接模拟器、启动游戏)。"""
    if _main._ctx is not None:
        return ApiResponse(success=True, message='系统已启动')

    try:
        from autowsgr.scheduler import launch

        config_path = request.config_path or 'usersettings.yaml'
        _log.info('[System] 正在启动, 配置: {}', config_path)
        _main._ctx = launch(config_path)
        _log.info('[System] 启动成功')

        return ApiResponse(success=True, message='系统启动成功')

    except Exception as e:
        _log.error('[System] 启动失败: {}', e)
        return ApiResponse(success=False, error=str(e))


@router.post('/stop', response_model=ApiResponse)
async def system_stop():
    """停止系统。"""
    if _main._ctx is None:
        return ApiResponse(success=True, message='系统未运行')

    if task_manager.is_running:
        task_manager.stop_task()

    _main._ctx = None
    _log.info('[System] 系统已停止')
    return ApiResponse(success=True, message='系统已停止')


@router.get('/status', response_model=ApiResponse)
async def system_status():
    """获取系统状态。"""
    return ApiResponse(
        success=True,
        data={
            'status': task_manager.current_task.status.value
            if task_manager.current_task
            else 'idle',
            'emulator_connected': _main._ctx is not None,
            'game_running': _main._ctx is not None,
            'current_task': task_manager.current_task.task_id
            if task_manager.current_task
            else None,
        },
    )
