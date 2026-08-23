"""WebSocket 连接管理 — 管理客户端连接与消息广播。"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from loguru import logger

from autowsgr.infra.logger import get_logger


if TYPE_CHECKING:
    from fastapi import WebSocket


_log = get_logger('server.ws')


class WebSocketManager:
    """WebSocket 连接管理器。

    管理所有活跃的 WebSocket 连接，支持广播消息。
    """

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        # loguru sink 的 handler id (None 表示未注册)
        self._log_sink_handler_id: int | None = None

    def register_log_sink(
        self,
        loop: asyncio.AbstractEventLoop,
        level: str = 'INFO',
    ) -> None:
        """注册 loguru sink，把日志通过 WebSocket 推送给 GUI。

        loguru sink 是同步函数，但 ``send_log`` 是 async；通过
        ``run_coroutine_threadsafe`` 把协程提交到 lifespan 保存的事件循环，
        避免在日志调用方阻塞或抛 RuntimeError。

        Parameters
        ----------
        loop:
            事件循环引用 (由 FastAPI lifespan 提供)。
        level:
            最低日志级别，默认 INFO。DEBUG 不推送，避免大量噪音推送给 GUI。
        """
        # 防止重复注册 (开发期间 hot reload 场景)
        if self._log_sink_handler_id is not None:
            return

        def sink(message: Any) -> None:
            """loguru sink：把日志提交到事件循环异步推送。"""
            record = message.record
            asyncio.run_coroutine_threadsafe(
                self.send_log(record['level'].name, record['message']),
                loop,
            )

        self._log_sink_handler_id = logger.add(sink, level=level)

    async def connect(self, websocket: WebSocket) -> None:
        """接受新连接。"""
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
        _log.info('[WS] 新连接, 当前连接数: {}', len(self._connections))

    async def disconnect(self, websocket: WebSocket) -> None:
        """断开连接。"""
        async with self._lock:
            self._connections.discard(websocket)
        _log.info('[WS] 断开连接, 当前连接数: {}', len(self._connections))

    async def broadcast(self, message: dict[str, Any]) -> None:
        """广播消息到所有连接。"""
        if not self._connections:
            return

        data = json.dumps(message, ensure_ascii=False)
        dead_connections = []

        async with self._lock:
            for ws in list(self._connections):
                try:
                    await ws.send_text(data)
                except Exception:
                    dead_connections.append(ws)

            # 清理断开的连接
            for ws in dead_connections:
                self._connections.discard(ws)

    async def send_log(
        self,
        level: str,
        message: str,
        channel: str = '',
    ) -> None:
        """发送日志消息。"""
        await self.broadcast(
            {
                'type': 'log',
                'timestamp': datetime.now(UTC).isoformat(),
                'level': level,
                'channel': channel,
                'message': message,
            }
        )

    async def send_task_update(
        self,
        task_id: str,
        status: str,
        progress: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
    ) -> None:
        """发送任务状态更新。"""
        payload: dict[str, Any] = {
            'type': 'task_update',
            'task_id': task_id,
            'status': status,
        }
        if progress:
            payload['progress'] = progress
        if result:
            payload['result'] = result
        await self.broadcast(payload)

    async def send_task_completed(
        self,
        task_id: str,
        success: bool,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """发送任务完成通知。"""
        await self.broadcast(
            {
                'type': 'task_completed',
                'task_id': task_id,
                'success': success,
                'result': result,
                'error': error,
            }
        )


# 全局单例
ws_manager = WebSocketManager()
