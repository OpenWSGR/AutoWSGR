"""决战策略决策逻辑。

本模块包含所有「判断应该做什么」的纯逻辑，不执行任何 UI 操作。
控制器 (``_controller.py``) 调用此处的方法，根据结果决定下一步行为。
"""

from __future__ import annotations

from itertools import combinations
from typing import TYPE_CHECKING

from autowsgr.constants import DECISIVE_SKILL_NAMES, ship_name_identity
from autowsgr.infra.logger import get_logger
from autowsgr.ops.decisive.config import MapData
from autowsgr.types import FleetSelection, Formation, ShipDamageState


if TYPE_CHECKING:
    from autowsgr.context import GameContext
    from autowsgr.infra import DecisiveConfig
    from autowsgr.ops.decisive.state import DecisiveState


_log = get_logger('ops.decisive')

# ═══════════════════════════════════════════════════════════════════════════════
# 辅助数据类
# ═══════════════════════════════════════════════════════════════════════════════


def _is_ship(name: str) -> bool:
    """判断名称是否为舰船（而非增益技能）。"""
    return bool(name) and name not in DECISIVE_SKILL_NAMES


def _count_anti_sub(enemy: list[str | None]) -> int:
    """统计轻巡、驱逐、轻母反潜单位，空槽不计入。"""
    anti_sub_set = {'轻巡', '驱逐', '轻母'}
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
        *,
        prefer_healthy: bool = False,
    ) -> None:
        self.config = config
        self.state = state
        self._ctx = ctx
        self._prefer_healthy = prefer_healthy
        self._level1_set = set(config.level1)
        # level2_full = level1 + level2 + 增益技能
        self._level2_full = [*config.level1, *config.level2, *DECISIVE_SKILL_NAMES]

    # ── 战备舰队选择 ───────────────────────────────────────────────────

    def choose_ships(
        self,
        selections: dict[str, FleetSelection],
        *,
        first_node: bool = False,
    ) -> list[str]:
        """在预算内先增加主备池舰数，同数优先一级舰、低费用。"""
        primary = list(dict.fromkeys(ship_name_identity(name) for name in self.config.level1))
        pool = list(dict.fromkeys([*primary, *(ship_name_identity(n) for n in self.config.level2)]))
        owned = {ship_name_identity(name) for name in self.state.ships}.intersection(pool)
        score = self.state.score
        offers: dict[str, FleetSelection] = {}
        for name, offer in selections.items():
            identity = ship_name_identity(name)
            if (
                identity is not None
                and identity in pool
                and _is_ship(name)
                and 0 <= offer.cost <= score
                and (identity not in offers or offer.cost < offers[identity].cost)
            ):
                offers[identity] = offer

        target = 2 if first_node and len(owned) < 2 else 6
        candidates = [identity for identity in pool if identity in offers and identity not in owned]

        def best_bundle(candidates: list[str], capacity: int) -> tuple[str, ...]:
            best = ()
            best_rank = (0, 0, 0)
            for count in range(1, min(capacity, len(candidates)) + 1):
                for bundle in combinations(candidates, count):
                    cost = sum(offers[identity].cost for identity in bundle)
                    rank = (count, sum(identity in primary for identity in bundle), -cost)
                    if cost <= score and rank > best_rank:
                        best, best_rank = bundle, rank
            return best

        selected = list(best_bundle(candidates, target - len(owned)))
        score -= sum(offers[identity].cost for identity in selected)
        owned.update(selected)
        if not first_node and len(owned) >= 6:
            for upgrade in (False, True):
                candidates = [
                    identity
                    for identity in primary
                    if identity in offers
                    and identity not in selected
                    and (identity in owned) == upgrade
                ]
                batch = best_bundle(candidates, len(candidates))
                score -= sum(offers[identity].cost for identity in batch)
                selected.extend(batch)
                owned.update(batch)
        result = [offers[identity].name for identity in selected]
        if len(owned.intersection(primary)) >= 6:
            for name in DECISIVE_SKILL_NAMES:
                if name in selections and 0 <= selections[name].cost <= score:
                    result.append(name)
                    score -= selections[name].cost
        return result

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

        根据 ``MapData`` 中的 ``map_end`` 数据判断，
        替代原先硬编码 ``> "J"`` 的逻辑。

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

    def get_best_fleet(
        self, blocked: frozenset[str] = frozenset(), damaged: frozenset[str] = frozenset()
    ) -> list[str]:
        """按配置顺序挑选主备舰，启用按时长维修时优先使用健康候补。"""
        by_identity = {ship_name_identity(name): name for name in sorted(self.state.ships)}
        candidates = list(
            dict.fromkeys(
                ship_name_identity(name)
                for name in (*self.config.level1, *self.config.level2)
                if _is_ship(name)
            )
        )
        damage = {
            ship_name_identity(name): state
            for name, state in zip(self.state.fleet[1:], self.state.ship_stats, strict=True)
            if name
        }

        def needs_repair(identity: str) -> bool:
            health = damage.get(identity)
            if health is not None:
                return health >= self.config.repair_level
            return identity in damaged or not self._is_available(by_identity[identity])

        identities = [
            identity
            for identity in candidates
            if identity in by_identity and identity not in blocked
        ]
        if self._prefer_healthy:
            identities.sort(key=needs_repair)
        else:
            # 原编队优先级允许中破主力；有可用替补时，大破舰不占它的舰位。
            identities.sort(
                key=lambda identity: (
                    damage.get(identity) is ShipDamageState.SEVERE
                    or not self._is_available(by_identity[identity])
                )
            )
        selected = identities[:6]
        for name in self.config.flagship_priority:
            identity = ship_name_identity(name)
            if identity in selected:
                idx = selected.index(identity)
                selected[0], selected[idx] = selected[idx], selected[0]
                break
        return [
            '',
            *(by_identity[identity] for identity in selected),
            *([''] * (6 - len(selected))),
        ]

    def get_formation(self, node: str | None = None) -> Formation:
        """根据指定候选节点敌方编成选择阵型；省略节点时使用当前状态。

        兼容 Legacy 规则：
        - 当敌方反潜单位数 <= 0，或我方含 U-1206 且反潜单位 <= 1：梯形阵
        - 其他情况：复纵阵
        """
        enemy = MapData.get_enemy(
            self.config.chapter,
            self.state.stage,
            self.state.node if node is None else node,
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
