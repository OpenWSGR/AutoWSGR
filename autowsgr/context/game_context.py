"""顶层游戏上下文 — 基础设施 + 运行时状态聚合。"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .build import BuildQueue
from .expedition import ExpeditionQueue
from .fleet import Fleet
from .resources import Resources


if TYPE_CHECKING:
    from autowsgr.emulator import AndroidController
    from autowsgr.infra import UserConfig
    from autowsgr.types import PageName
    from autowsgr.vision import OCREngine

# 游戏固定 4 支舰队
_NUM_FLEETS = 4


def _default_fleets() -> list[Fleet]:
    return [Fleet(fleet_id=i) for i in range(1, _NUM_FLEETS + 1)]


@dataclass
class GameContext:
    """游戏运行时上下文 — 持有基础设施引用与可观测游戏状态。

    构造时由调度层 (:mod:`autowsgr.scheduler.launcher`) 注入
    ``ctrl`` / ``config`` / ``ocr``，各子模块通过 ``ctx`` 获取
    共享服务，不再各自创建。

    Attributes (基础设施)
    ---------------------
    ctrl : AndroidController
        设备控制器 (截图 + 触控)。
    config : UserConfig
        用户配置 (只读)。
    ocr : OCREngine | None
        OCR 引擎实例 (可选，创建后复用)。

    Attributes (游戏状态)
    ----------------------
    resources, fleets, expeditions, build_queue, current_page, …
        从游戏画面中读取 / 推断出的动态数据。
    """

    # ── 基础设施引用 (必填) ──

    ctrl: AndroidController
    """设备控制器 (截图 + 触控)。"""
    config: UserConfig
    """用户配置 (只读)。"""

    # ── 基础设施引用 (可选) ──

    ocr: OCREngine
    """OCR 引擎实例 (章节/阵型识别等)。"""

    # ── 游戏运行时状态 ──

    resources: Resources = field(default_factory=Resources)
    """当前资源。"""
    fleets: list[Fleet] = field(default_factory=_default_fleets)
    """四支舰队 (fleet_id 1–4)。"""
    expeditions: ExpeditionQueue = field(default_factory=ExpeditionQueue)
    """远征队列。"""
    build_queue: BuildQueue = field(default_factory=BuildQueue)
    """建造队列。"""
    current_page: PageName | None = None
    """当前游戏页面。"""

    # ── 每日计数器 ──

    dropped_ship_count: int = 0
    """当天掉落舰船数。"""
    dropped_loot_count: int = 0
    """当天掉落胖次数。"""
    quick_repair_used: int = 0
    """本次会话已消耗快修数。"""

    stop_event: threading.Event = field(default_factory=threading.Event)
    """任务停止信号 (由 TaskManager 设置)。"""

    # ── 便捷访问 ──

    def fleet(self, fleet_id: int) -> Fleet:
        """按编号 (1–4) 获取舰队。"""
        if not 1 <= fleet_id <= len(self.fleets):
            raise ValueError(f'fleet_id 应在 1–{len(self.fleets)} 范围内，收到 {fleet_id}')
        return self.fleets[fleet_id - 1]
