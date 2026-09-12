"""决战策略决策逻辑。

本模块包含所有「判断应该做什么」的纯逻辑，不执行任何 UI 操作。
控制器 (``_controller.py``) 调用此处的方法，根据结果决定下一步行为。
"""

from __future__ import annotations

from itertools import combinations
from typing import TYPE_CHECKING

from autowsgr.infra.logger import get_logger
from autowsgr.types import FleetSelection, Formation

from .config import MapData


if TYPE_CHECKING:
    from autowsgr.context import GameContext
    from autowsgr.infra import DecisiveConfig

    from .state import DecisiveState


_log = get_logger('ops.decisive')

# ═══════════════════════════════════════════════════════════════════════════════
# 辅助数据类
# ═══════════════════════════════════════════════════════════════════════════════


def _is_ship(name: str) -> bool:
    """判断名称是否为舰船（而非增益技能）。"""
    return name not in {'长跑训练', '肌肉记忆', '黑科技'}


def _count_anti_sub(enemy: list[str]) -> int:
    """统计敌方反潜单位数量（Legacy: CL/DD/CVL）。"""
    anti_sub_set = {'CL', 'DD', 'CVL'}
    return sum(1 for ship_type in enemy if ship_type in anti_sub_set)


# ═══════════════════════════════════════════════════════════════════════════════
# 决策模块
# ═══════════════════════════════════════════════════════════════════════════════


class DecisiveLogic:
    """决战策略决策模块。

    封装购买优先级、最优编队计算、修理判断、撤退判断等纯逻辑。
    不执行任何 UI 操作，仅返回决策结果供控制器使用。

    Parameters
    ----------
    config:
        决战配置（不变量）。
    state:
        决战运行状态（共享引用，只读取，不修改）。
    """

    def __init__(
        self,
        config: DecisiveConfig,
        state: DecisiveState,
        ctx: GameContext | None = None,
    ) -> None:
        self.config = config
        self.state = state
        self._ctx = ctx
        self._level1_set = set(config.level1)
        # level2_full = level1 + level2 + 增益技能
        self._level2_full = list({'长跑训练', '肌肉记忆', *config.level1, *config.level2, '黑科技'})

    # ── 战备舰队选择 ───────────────────────────────────────────────────

    def choose_ships(
        self,
        selections: dict[str, FleetSelection],
        *,
        first_node: bool = False,
    ) -> list[str]:
        """从可购买列表中选择要购买的舰船/技能。

        策略优先级::

            舰队为空/仅1艘 → 只购买 level1 舰船
            舰队未满编     → 购买 level2 中的舰船 (不买技能)
            满编但有非一级 → 优先凑齐 level1
            满编且全一级   → 可购买增益技能
            第一节点额外   → 同时尝试购买二级舰船

        Parameters
        ----------
        selections:
            当前可购买项 ``{name: FleetSelection}``。
        first_node:
            是否为第一小关第一节点。

        Returns
        -------
        list[str]
            选中购买的名称列表（按决策顺序）。
        """
        owned = {name for name in getattr(self.state, 'ships', set()) if _is_ship(name)}
        score = self.state.score
        primary = [name for name in self.config.level1 if _is_ship(name)]
        backup = [
            name for name in self.config.level2 if _is_ship(name) and name not in self._level1_set
        ]
        ordered = [*primary, *backup]

        target_count = 2 if first_node and len(owned) < 2 else 6
        missing_count = max(0, target_count - len(owned))
        candidates = [name for name in ordered if name in selections and name not in owned]

        # Maximize new ships first, then primary ships, then preserve resources.
        selected: list[str] = []
        if missing_count and candidates:
            best_names: tuple[str, ...] = ()
            best_rank = (-1, -1, 0)
            for size in range(1, min(missing_count, len(candidates)) + 1):
                for names in combinations(candidates, size):
                    cost = sum(selections[name].cost for name in names)
                    if cost > score:
                        continue
                    primary_count = sum(name in self._level1_set for name in names)
                    rank = (size, primary_count, -cost)
                    if rank > best_rank:
                        best_names = names
                        best_rank = rank
            selected.extend(best_names)
            score -= sum(selections[name].cost for name in best_names)
            owned.update(best_names)

        # Once six ships exist, add missing primary ships before buying upgrades.
        if not first_node and len(owned) >= 6:
            for name in primary:
                if name not in owned and name in selections and score >= selections[name].cost:
                    selected.append(name)
                    score -= selections[name].cost
                    owned.add(name)

            # Upgrade only primary ships already in the acquired pool.
            for name in primary:
                if name in owned and name in selections and name not in selected:
                    if score < selections[name].cost:
                        continue
                    selected.append(name)
                    score -= selections[name].cost

        return selected

    # ── 状态判断 ───────────────────────────────────────────────────────

    def should_retreat(self, fleet: list[str]) -> bool:
        """舰船数量不足时应当撤退。

        - 节点 A: < 2 艘则撤退
        - 其他节点: < 1 艘则撤退
        """
        ship_count = sum(1 for s in fleet[1:] if s)
        if self.state.node == 'A':
            return ship_count < 2
        return ship_count < 1

    def should_repair(self) -> bool:
        """根据修理等级判断是否需要修理。"""
        if not self.config.use_quick_repair:
            return False
        return any(
            status >= self.config.repair_level for status in self.state.ship_stats if status > 0
        )

    def is_stage_end(self, node: str | None = None) -> bool:
        """判断当前节点是否为该小关的终止节点。

        根据 per-EX 地图数据中的终点节点判断，
        替代原先的静态终点常量。

        Parameters
        ----------
        node:
            要检查的节点字母；为 ``None`` 时使用 ``state.node``。
        """
        if node is None:
            node = self.state.node
        return MapData.is_stage_end(
            self.config.chapter,
            self.state.stage,
            node,
        )

    def is_key_point(self, node: str | None = None) -> bool:
        """判断当前节点是否为关键点 (需夜战)。

        Parameters
        ----------
        node:
            要检查的节点字母；为 ``None`` 时使用 ``state.node``。
        """
        if node is None:
            node = self.state.node
        return MapData.is_key_point(
            self.config.chapter,
            self.state.stage,
            node,
        )

    def check_useful_skill(self, gained: list[str]) -> bool:
        """充分利用技能, 要求地图1必须为Lv1+Lv2中的船; 其余地图至少一半的船为Lv1中的船。
        严格利用技能, 开启时要求地图1技能不能获取+1的船;

        Parameters
        ----------
        gained:
            技能获得的舰船列表
        """
        if len(gained) == 1:
            ship = gained[0]
            # 严格模式下检查重复舰船
            if self.config.useful_skill_strict and ship in self.state.ships:
                _log.info(
                    '[决战] 处于严格模式，获取到重复舰船：{}, 舰队{}',
                    ship,
                    self.state.ships,
                )
                return False
            # 检查是否在 level2 列表中
            return ship in self._level2_full

        # 多艘船：检查 level1 舰船是否占一半以上
        useful_ships = set(gained) & self._level1_set
        return len(useful_ships) >= len(gained) / 2

    # ── 编队计算 ───────────────────────────────────────────────────────

    def get_best_fleet(self) -> list[str]:
        """根据当前拥有的舰船计算最优编队。

        Returns
        -------
        list[str]
            长度 7 的列表：索引 0 留空，1-6 为各位置舰船名。
        """
        ships = self.state.ships
        current_fleet = {name for name in self.state.fleet[1:] if name}
        best: list[str] = ['']
        _log.debug('[决战] 当前舰船: {}', ships)
        for ship in self.config.level1:
            if ship in ships and (ship in current_fleet or self._is_available(ship)) and len(best) < 7:
                best.append(ship)

        for ship in self.config.level2:
            if (
                ship in ships
                and ship not in best
                and (ship in current_fleet or self._is_available(ship))
                and len(best) < 7
            ):
                best.append(ship)

        for flag_ship in self.config.flagship_priority:
            if flag_ship in best[1:]:
                idx = best.index(flag_ship)
                best[idx], best[1] = best[1], best[idx]
                break

        while len(best) < 7:
            best.append('')

        _log.debug('[决战] 最优编队: {}', best)
        return best

    # ── 路径选择 ───────────────────────────────────────────────────────

    def get_formation(self) -> Formation:
        """根据当前节点敌方编成动态选择阵型。

        兼容 Legacy 规则：
        - 当敌方反潜单位数 <= 0，或我方含 U-1206 且反潜单位 <= 1：梯形阵
        - 其他情况：复纵阵
        """
        enemy = MapData.get_enemy(
            self.config.chapter,
            self.state.stage,
            self.state.node,
        )
        anti_sub = _count_anti_sub(enemy)

        if ('U-1206' in self.state.fleet and anti_sub <= 1) or anti_sub <= 0:
            return Formation.wedge
        return Formation.double_column

    # ── 内部辅助 ───────────────────────────────────────────────────────

    def _is_available(self, name: str) -> bool:
        """判断舰船是否可用 (有 ctx 时查注册表, 否则始终可用)。"""
        if self._ctx is None:
            return True
        return self._ctx.is_ship_available(name)
