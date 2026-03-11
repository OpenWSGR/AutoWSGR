"""顶层游戏上下文 — 基础设施 + 运行时状态聚合。"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from autowsgr.infra.logger import get_logger
from autowsgr.types import ShipDamageState

from .build import BuildQueue
from .expedition import ExpeditionQueue
from .fleet import Fleet
from .resources import Resources
from .ship import Ship


if TYPE_CHECKING:
    from autowsgr.combat.history import CombatResult
    from autowsgr.emulator import AndroidController
    from autowsgr.infra import UserConfig
    from autowsgr.types import PageName
    from autowsgr.vision import OCREngine


_log = get_logger('context')

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
    """四支舰队 (fleet_id 1-4)。"""
    expeditions: ExpeditionQueue = field(default_factory=ExpeditionQueue)
    """远征队列。"""
    build_queue: BuildQueue = field(default_factory=BuildQueue)
    """建造队列。"""
    ship_registry: dict[str, Ship] = field(default_factory=dict)
    """舰船注册表, 以名称为键。"""
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
        """按编号 (1-4) 获取舰队。"""
        if not 1 <= fleet_id <= len(self.fleets):
            raise ValueError(f'fleet_id 应在 1-{len(self.fleets)} 范围内，收到 {fleet_id}')
        return self.fleets[fleet_id - 1]

    def get_ship(self, name: str) -> Ship:
        """按名称获取舰船, 不存在则自动注册。"""
        if name not in self.ship_registry:
            self.ship_registry[name] = Ship(name=name)
        return self.ship_registry[name]

    def is_ship_available(self, name: str) -> bool:
        """判断舰船是否可用 (非大破 且 非修理中)。"""
        return self.get_ship(name).available

    def update_ship_damage(self, name: str, state: ShipDamageState) -> None:
        """更新舰船的破损状态。"""
        self.get_ship(name).damage_state = state

    # ── 战斗上下文同步 ──

    def sync_before_combat(
        self,
        fleet_id: int,
        ships: list[Ship] | None = None,
        *,
        loot_count: int | None = None,
        ship_acquired_count: int | None = None,
    ) -> None:
        """战斗开始前, 用识别到的信息更新上下文。

        Parameters
        ----------
        fleet_id:
            出击舰队编号 (1-4)。
        ships:
            从准备页面识别到的舰船列表 (含等级、血量状态)。
        loot_count:
            今日已获取战利品数量 (出征面板识别)。
        ship_acquired_count:
            今日已获取舰船数量 (出征面板识别)。
        """
        # 同步每日计数器
        if loot_count is not None:
            self.dropped_loot_count = loot_count
            _log.debug('[Context] 今日战利品数: {}', loot_count)
        if ship_acquired_count is not None:
            self.dropped_ship_count = ship_acquired_count
            _log.debug('[Context] 今日舰船数: {}', ship_acquired_count)

        # 同步出击舰队信息
        if ships is not None:
            fleet = self.fleet(fleet_id)
            fleet.ships = ships
            # 同步到舰船注册表
            for s in ships:
                if s.name:
                    registered = self.get_ship(s.name)
                    registered.level = s.level or registered.level
                    registered.damage_state = s.damage_state
            _log.info(
                '[Context] 舰队 {} 出击编成: {}',
                fleet_id,
                ', '.join(f'{s.name or "?"} Lv.{s.level}' for s in ships),
            )

    def sync_after_combat(
        self,
        fleet_id: int,
        result: CombatResult,
    ) -> None:
        """战斗结束后, 用结果更新上下文。

        Parameters
        ----------
        fleet_id:
            出击舰队编号 (1-4)。
        result:
            战斗结果。
        """
        from autowsgr.types import ConditionFlag

        if result.flag not in (
            ConditionFlag.OPERATION_SUCCESS,
            ConditionFlag.FIGHT_END,
        ):
            return

        # 更新舰队战后血量
        fleet = self.fleet(fleet_id)
        for i, ship in enumerate(fleet.ships):
            if i < len(result.ship_stats):
                state = result.ship_stats[i]
                if state != ShipDamageState.NO_SHIP:
                    ship.damage_state = state
                    if ship.name:
                        self.get_ship(ship.name).damage_state = state

        # 统计本次掉落舰船数
        fight_results = result.fight_results
        new_drops = sum(1 for fr in fight_results if fr.dropped_ship)
        if new_drops:
            self.dropped_ship_count += new_drops
            _log.info('[Context] 本次掉落 {} 艘, 今日累计 {}', new_drops, self.dropped_ship_count)

        _log.debug(
            '[Context] 舰队 {} 战后状态: {}',
            fleet_id,
            [s.damage_state.name for s in fleet.ships],
        )
