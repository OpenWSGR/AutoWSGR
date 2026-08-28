"""WebSocket 连接管理 — 管理客户端连接与消息广播。"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

from autowsgr.infra.logger import get_logger


if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import WebSocket


_log = get_logger('server.ws')
Stream = Literal['logs', 'task']

# ═══════════════════════════════════════════════════════════════════════════════
# GUI 统计所需日志白名单正则
# ═══════════════════════════════════════════════════════════════════════════════
# DailySortieStats.consume 从 WebSocket log 消息中解析统计数据（战斗/快修/泡澡/战利品/船数/掉落/远征）
# 只推送匹配以下正则的日志，避免 GUI 收到全量 INFO 噪音。
_STATS_LOG_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r'\[Combat\]\s*战果:.*评价'),  # 战斗评级 (battleCount/grades)
    re.compile(r'\[Combat\]\s*获得舰船'),       # 舰船掉落 (shipCount/shipDrops)
    re.compile(r'\[UI\]\s*战利品数量:\s*\d'),  # 战利品统计 (lootCount/lootLimit)
    re.compile(r'\[UI\]\s*舰船数量:\s*\d'),     # 船坞容量统计 (shipCount/shipLimit)
    re.compile(r'\[UI\]\s*修理位置:'),         # 快修使用 (quickRepairCount)
    re.compile(r'\[OPS\]\s*浴室修理'),         # 泡澡修理 (bathRepairCount)
    re.compile(r'\[UI\]\s*远征收取:\s*\d'),    # 远征完成 (expeditionCount)
)


def _is_stats_log(message: str) -> bool:
    """判断日志内容是否为 GUI 统计所需。"""
    return any(p.search(message) for p in _STATS_LOG_PATTERNS)


class WebSocketManager:
    """WebSocket 连接管理器。

    管理所有活跃的 WebSocket 连接，支持广播消息。
    """

    def __init__(self) -> None:
        self._connections: dict[Stream, set[WebSocket]] = {'logs': set(), 'task': set()}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, stream: Stream) -> None:
        """接受新连接。"""
        await websocket.accept()
        async with self._lock:
            self._connections[stream].add(websocket)
        _log.info('[WS] {} 新连接, 当前连接数: {}', stream, len(self._connections[stream]))

    async def disconnect(self, websocket: WebSocket, stream: Stream) -> None:
        """断开连接。"""
        async with self._lock:
            self._connections[stream].discard(websocket)
        _log.info('[WS] {} 断开连接, 当前连接数: {}', stream, len(self._connections[stream]))

    async def broadcast(self, stream: Stream, message: dict[str, Any]) -> None:
        """广播消息到所有连接。"""
        if not self._connections[stream]:
            return

        data = json.dumps(message, ensure_ascii=False)
        dead_connections = []

        async with self._lock:
            for ws in list(self._connections[stream]):
                try:
                    await ws.send_text(data)
                except Exception:
                    dead_connections.append(ws)

            # 清理断开的连接
            for ws in dead_connections:
                self._connections[stream].discard(ws)

    async def send_log(
        self,
        level: str,
        message: str,
        channel: str = '',
    ) -> None:
        """发送日志消息。"""
        await self.broadcast(
            'logs',
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
        await self.broadcast('task', payload)

    async def send_task_completed(
        self,
        task_id: str,
        success: bool,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """发送任务完成通知。"""
        await self.broadcast(
            'task',
            {
                'type': 'task_completed',
                'task_id': task_id,
                'success': success,
                'result': result,
                'error': error,
            }
        )

    # ══════════════════════════════════════════════════════════════════════
    # 统计日志 sink (供 GUI DailySortieStats 消费)
    # ══════════════════════════════════════════════════════════════════════

    def build_log_sink(self, loop: asyncio.AbstractEventLoop) -> Callable[[dict[str, Any]], None]:
        """构建 loguru sink 回调，仅推送 GUI 统计需要的日志。

        只推送匹配 :data:`_STATS_LOG_PATTERNS` 白名单的消息；
        普通点击/导航/初始化等 INFO 日志被过滤掉，避免 GUI 端日志面板噪音。
        """
        def _sink(message: Any) -> None:  # loguru.Message (avoid runtime import)
            text = str(message.record.get('message', ''))
            if not _is_stats_log(text):
                return
            raw_level = message.record.get('level', '')
            level = raw_level.name if hasattr(raw_level, 'name') else str(raw_level)
            ch = message.record.get('extra', {}).get('ch', '') or ''

            if not loop.is_closed():
                asyncio.run_coroutine_threadsafe(self.send_log(level, text, ch), loop)

        return _sink


# 全局单例
ws_manager = WebSocketManager()
