"""舰队规则匹配与校验。

本模块只判断舰名、舰种和等级是否满足指定规则，不负责目标分配、
页面操作或舰队状态调整。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.combat.fleet import FleetSlotRule, ShipSelector
from autowsgr.constants import normalize_ship_name, ship_name_identity

from ._detect import FleetDetectMixin


if TYPE_CHECKING:
    from ._detect import FleetSnapshot


class FleetRuleMixin(FleetDetectMixin):
    """提供单条规则、单个槽位和完整舰队的校验能力。"""

    @classmethod
    def _option_matches_name(
        cls,
        current_name: str | None,
        option: ShipSelector,
    ) -> bool:
        """判断准备页舰名是否与一条精确规则属于同一舰船身份。"""
        return ship_name_identity(current_name) == ship_name_identity(
            option.name
        ) and cls._matches_search_name(current_name, option.search_name)

    # 按“已分配舰名优先、其余规则随后”的顺序生成本槽完整规则。
    @classmethod
    def _slot_options(
        cls,
        name: str | None,
        selector: FleetSlotRule | None,
    ) -> list[ShipSelector]:
        normalized_name = normalize_ship_name(name)
        if selector is None:
            return [ShipSelector(name=normalized_name)] if normalized_name else []

        options = list(selector.options)
        target_identity = ship_name_identity(normalized_name)
        options.sort(
            key=lambda option: ship_name_identity(option.name) != target_identity,
        )
        return options

    # 判断当前标准舰名是否符合 selector 指定的搜索名称。
    @classmethod
    def _matches_search_name(cls, current_name: str | None, raw_search_name: str | None) -> bool:
        if current_name is None:
            return False
        if raw_search_name is None:
            return True
        if not raw_search_name.strip():
            return True

        search_name = raw_search_name.strip()
        # 当前舰名与搜索名完全相同时直接通过。
        if current_name == search_name:
            return True

        return ship_name_identity(current_name) == ship_name_identity(search_name)

    @classmethod
    def _option_for_name(
        cls,
        name: str | None,
        selector: FleetSlotRule | None,
    ) -> ShipSelector | None:
        """返回与实际舰名对应的独立规则。"""
        identity = ship_name_identity(name)
        return next(
            (
                option
                for option in cls._slot_options(name, selector)
                if ship_name_identity(option.name) == identity
            ),
            None,
        )

    @staticmethod
    def _requires_selection_validation(option: ShipSelector | None) -> bool:
        """返回规则是否必须通过选船页校验舰种或等级。"""
        return bool(
            option is not None
            and not option.relaxed_constraints
            and (option.ship_types or option.min_level is not None or option.max_level is not None)
        )

    @classmethod
    def _snapshot_satisfies_option(
        cls,
        snapshot: FleetSnapshot,
        slot: int,
        option: ShipSelector,
    ) -> bool:
        """强校验: 首次快照是否已从舰种/等级确认该槽位满足规则。

        名称匹配由调用方保证；这里只做约束校验。relaxed (弱校验) 规则
        不要求选船校验，无需调用本函数，名称匹配即视为放行。
        """
        ship_type = snapshot.ship_types[slot] if snapshot.ship_types else None
        ship_level = snapshot.ship_levels[slot] if snapshot.ship_levels else None

        if option.ship_types and ship_type not in option.ship_types:
            return False
        if option.min_level is not None or option.max_level is not None:
            if ship_level is None:
                return False
            if option.min_level is not None and ship_level < option.min_level:
                return False
            if option.max_level is not None and ship_level > option.max_level:
                return False
        return True

    # 判断一个当前槽位是否满足对应的目标舰名和搜索规则。
    @classmethod
    def _slot_matches(
        cls,
        current_name: str | None,
        target: str | None,
        selector: FleetSlotRule | None,
        *,
        selection_verified: bool = False,
    ) -> bool:
        # 目标为空时，只有当前槽也为空才算匹配。
        if target is None:
            return current_name is None
        if selector is None:
            return ship_name_identity(current_name) == ship_name_identity(target)
        option = cls._option_for_name(current_name, selector)
        if option is None:
            return False
        if cls._requires_selection_validation(option) and not selection_verified:
            return False
        return cls._matches_search_name(
            current_name,
            option.search_name,
        )

    # 验证当前六个槽位是否完整满足目标，并拒绝队内同名舰。
    @classmethod
    def _validate_with_selector(
        cls,
        current: list[str | None],
        desired: list[str | None],
        selectors: list[FleetSlotRule | None],
        verified_slots: set[int] | frozenset[int] = frozenset(),
    ) -> bool:
        members = [ship_name_identity(name) for name in current if name is not None]
        if len(members) != len(set(members)):
            return False

        return all(
            cls._slot_matches(
                current[i],
                desired[i],
                selectors[i],
                selection_verified=i in verified_slots,
            )
            for i in range(6)
        )
