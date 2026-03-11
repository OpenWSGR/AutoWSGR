"""FastAPI 主应用 — 应用入口、生命周期管理和 WebSocket 端点。

路由按功能拆分到 routes/ 子包:
- routes/system.py  — /api/system/*     系统管理
- routes/task.py    — /api/task/*       任务执行
- routes/game.py    — /api/game/*       游戏状态查询
- routes/ops.py     — /api/expedition/* /api/build/* 等操作
- routes/health.py  — /api/health       健康检查

WebSocket 端点保留在此文件:
- WS  /ws/logs  — 实时日志流
- WS  /ws/task  — 任务状态更新

使用方式:
    uvicorn autowsgr.server.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from autowsgr.infra.logger import get_logger
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

# ── 注册路由模块 ──
from autowsgr.server.routes.game import router as game_router  # noqa: E402
from autowsgr.server.routes.health import router as health_router  # noqa: E402
from autowsgr.server.routes.ops import router as ops_router  # noqa: E402
from autowsgr.server.routes.system import router as system_router  # noqa: E402
from autowsgr.server.routes.task import router as task_router  # noqa: E402


app.include_router(system_router)
app.include_router(task_router)
app.include_router(game_router)
app.include_router(ops_router)
app.include_router(health_router)


# ═══════════════════════════════════════════════════════════════════════════════
# WebSocket 接口
# ═══════════════════════════════════════════════════════════════════════════════


@app.websocket('/ws/logs')
async def ws_logs(websocket: WebSocket):
    """实时日志流。"""
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
# 入口
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host='0.0.0.0', port=8000)
