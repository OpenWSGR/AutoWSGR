"""服务端路由模块。

按功能拆分为:
- system: 系统管理 (/api/system/*)
- task: 任务执行 (/api/task/*)
- game: 游戏状态查询 (/api/game/*, /api/expedition/status, /api/build/status)
- ops: 操作端点 (/api/expedition/check, /api/build/*, /api/reward/*, /api/cook, /api/repair/*, /api/destroy)
- health: 健康检查 (/api/health)
"""

from collections.abc import Callable
from typing import Any

from fastapi import HTTPException


def require_context(getter: Callable[[], Any]) -> Any:
    try:
        return getter()
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
