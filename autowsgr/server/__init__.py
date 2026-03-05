"""HTTP Server 模块 — 提供 REST API 和 WebSocket 接口。

本模块封装 autowsgr 核心功能，通过 FastAPI 暴露 HTTP 接口供前端调用。

主要功能:
- 任务执行 (常规战/战役/演习/决战/活动)
- 状态查询
- 实时日志推送 (WebSocket)
- 异步任务管理

使用方式:
    uvicorn autowsgr.server.main:app --host 0.0.0.0 --port 8000
"""

from .main import app
from .schemas import (
    CombatPlanRequest,
    NodeDecisionRequest,
    TaskStartRequest,
    TaskStatusResponse,
)
from .task_manager import TaskManager, TaskStatus


__all__ = [
    'CombatPlanRequest',
    'NodeDecisionRequest',
    'TaskManager',
    'TaskStartRequest',
    'TaskStatus',
    'TaskStatusResponse',
    'app',
]
