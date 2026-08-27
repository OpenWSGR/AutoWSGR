"""系统管理路由 — /api/system/*"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from autowsgr.infra.logger import get_logger
from autowsgr.server.device_lease import (
    DeviceOperationBusyError,
    device_operation_lease,
    exclusive_device_operation,
)
from autowsgr.server.schemas import ApiResponse
from autowsgr.server.task_manager import task_manager

from .. import main as _main


_log = get_logger('server')

router = APIRouter(prefix='/api/system', tags=['system'])
_TASK_STOP_TIMEOUT_SECONDS = 30.0


class SystemStartRequest(BaseModel):
    """系统启动请求。"""

    config_path: str | None = None


@router.post('/start', response_model=ApiResponse)
@exclusive_device_operation('api:system-start')
async def system_start(request: SystemStartRequest) -> ApiResponse:
    """启动系统 (连接模拟器、启动游戏)。"""
    async with _main.lifecycle_lock:
        if _main._ctx is not None:
            return ApiResponse(success=True, message='系统已启动')

        try:
            from autowsgr.scheduler import launch

            config_path = request.config_path or 'usersettings.yaml'
            _log.info('[System] 正在启动, 配置: {}', config_path)
            _main._ctx = await asyncio.to_thread(launch, config_path=config_path)
            _main.register_stats_log_sink(asyncio.get_running_loop())
            _log.info('[System] 启动成功')

            return ApiResponse(success=True, message='系统启动成功')

        except Exception as e:
            _log.error('[System] 启动失败: {}', e)
            return ApiResponse(success=False, error=str(e))


@router.post('/stop', response_model=ApiResponse)
async def system_stop() -> ApiResponse:
    """停止系统。"""
    async with _main.lifecycle_lock:
        if _main._ctx is None:
            return ApiResponse(success=True, message='系统未运行')

        if task_manager.is_running:
            task_manager.stop_task()

        completed = await asyncio.to_thread(
            task_manager.wait_for_completion,
            _TASK_STOP_TIMEOUT_SECONDS,
        )
        if not completed:
            _log.error('[System] 任务未在超时前停止, 保留当前系统上下文')
            return ApiResponse(
                success=False,
                error='任务未在超时前停止，系统上下文仍保持活动状态',
            )

        try:
            lease_token = device_operation_lease.acquire('api:system-stop')
        except DeviceOperationBusyError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        try:
            _main._ctx = None
            _log.info('[System] 系统已停止')
            return ApiResponse(success=True, message='系统已停止')
        finally:
            device_operation_lease.release(lease_token)


@router.get('/status', response_model=ApiResponse)
async def system_status() -> ApiResponse:
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


@router.get('/emulator/devices', response_model=ApiResponse)
async def emulator_devices() -> ApiResponse:
    """查询 ADB 设备列表，用于检查模拟器运行状态。

    会先对已知 TCP serial（MuMu 等）执行 adb connect，再列出设备。
    """
    try:
        from autowsgr.emulator.detector import connect_and_list_devices

        devices = await asyncio.to_thread(connect_and_list_devices)
        return ApiResponse(
            success=True,
            data=[{'serial': s, 'status': st} for s, st in devices],
        )
    except Exception as e:
        _log.warning('[System] ADB 设备查询失败: {}', e)
        return ApiResponse(success=False, error=str(e))
