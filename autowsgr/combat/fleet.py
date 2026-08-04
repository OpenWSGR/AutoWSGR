"""舰队规则领域模型和入口转换。

YAML 与 HTTP 请求只在各自入口转换一次。执行器和 UI 只接收本模块定义的
不可变对象，不再解释字典、Pydantic DTO 或旧 candidates 字符串格式。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from autowsgr.contracts.vessel_types import (
    FLEET_VESSEL_TYPE_BY_CODE,
    FLEET_VESSEL_TYPES,
)
from autowsgr.types import ShipType


if TYPE_CHECKING:
    from autowsgr_native.vessel_type import VesselType

    from autowsgr.combat.plan import CombatPlan


NATIVE_FLEET_VESSEL_TYPES = tuple(vessel_type.native for vessel_type in FLEET_VESSEL_TYPES)
"""由公共 native 契约提供的普通舰种。"""

_NATIVE_CODE_TO_SHIP_TYPE: Mapping[str, ShipType] = MappingProxyType(
    {
        'cv': ShipType.CV,
        'cvl': ShipType.CVL,
        'av': ShipType.AV,
        'bb': ShipType.BB,
        'bbv': ShipType.BBV,
        'bc': ShipType.BC,
        'ca': ShipType.CA,
        'cav': ShipType.CAV,
        'clt': ShipType.CLT,
        'cl': ShipType.CL,
        'bm': ShipType.BM,
        'dd': ShipType.DD,
        'ssg': ShipType.SSG,
        'ss': ShipType.SS,
        'sc': ShipType.SC,
        'ap': ShipType.NAP,
        'asdg': ShipType.ASDG,
        'aadg': ShipType.AADG,
        'kp': ShipType.KP,
        'cg': ShipType.CG,
        'bbg': ShipType.BG,
        'bg': ShipType.CBG,
    },
)
"""native 0.3 舰种代码到 AutoWSGR 领域枚举的显式映射。"""

VESSEL_TYPE_TO_SHIP_TYPE: tuple[tuple[VesselType, ShipType], ...] = tuple(
    (vessel_type.native, _NATIVE_CODE_TO_SHIP_TYPE[vessel_type.code])
    for vessel_type in FLEET_VESSEL_TYPES
)

for _native_type, _ship_type in VESSEL_TYPE_TO_SHIP_TYPE:
    if _native_type.as_chinese() != _ship_type.value:
        raise RuntimeError(
            f'native 舰种中文语义不一致: {_native_type.as_english()}',
        )


def ship_type_from_native(vessel_type: VesselType) -> ShipType:
    """把 native 普通舰种转换为 AutoWSGR 领域枚举。"""
    for native_type, ship_type in VESSEL_TYPE_TO_SHIP_TYPE:
        if vessel_type == native_type:
            return ship_type
    message = f'不支持的 native 舰种: {vessel_type!r}'
    raise ValueError(message)


NATIVE_VESSEL_TYPE_BY_CODE: Mapping[str, VesselType] = MappingProxyType(
    {code: vessel_type.native for code, vessel_type in FLEET_VESSEL_TYPE_BY_CODE.items()},
)
"""API 使用的 native 0.3 canonical 舰种代码。"""


SHIP_TYPE_BY_CODE: Mapping[str, tuple[ShipType, ...]] = MappingProxyType(
    {
        **{
            code: (ship_type_from_native(vessel_type),)
            for code, vessel_type in NATIVE_VESSEL_TYPE_BY_CODE.items()
        },
        'ss_or_ssg': (ShipType.SS, ShipType.SSG),
    },
)
"""API 舰种代码到后端领域枚举的唯一映射。"""

LEGACY_SHIP_TYPE_ALIASES: Mapping[str, str] = MappingProxyType(
    {
        'cf': 'cv',
        'cgaa': 'cg',
        'cbg': 'bg',
        'ddg': 'asdg',
        'ddgaa': 'aadg',
    },
)
"""旧版 API/GUI 舰种代码到 canonical code 的兼容映射。"""

_ALL_SHIP_TYPE_CODES = {
    *SHIP_TYPE_BY_CODE,
    *LEGACY_SHIP_TYPE_ALIASES,
}

ALLOWED_SHIP_TYPE_CODES = frozenset(_ALL_SHIP_TYPE_CODES)


def parse_ship_type_codes(raw: object) -> tuple[ShipType, ...]:
    """校验舰种缩写并转换为去重后的领域枚举。"""
    if raw is None or raw == '':
        return ()
    values = [raw] if isinstance(raw, str) else raw
    if not isinstance(values, Sequence):
        raise TypeError('ship_type 必须是非空字符串列表')

    result: list[ShipType] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError('ship_type 必须是非空字符串列表')
        code = value.strip().lower()
        canonical_code = LEGACY_SHIP_TYPE_ALIASES.get(code, code)
        ship_types = SHIP_TYPE_BY_CODE.get(canonical_code)
        if ship_types is None:
            allowed = ', '.join(sorted(ALLOWED_SHIP_TYPE_CODES))
            raise ValueError(f'ship_type 不合法: {value!r}, 可选值: {allowed}')
        for ship_type in ship_types:
            if ship_type not in result:
                result.append(ship_type)
    return tuple(result)


@dataclass(frozen=True, slots=True)
class ShipSelector:
    """一艘主选或备选舰船的完整选择规则。"""

    name: str
    search_name: str | None = None
    ship_types: tuple[ShipType, ...] = ()
    min_level: int | None = None
    max_level: int | None = None
    relaxed_constraints: bool = False

    def __post_init__(self) -> None:
        name = self.name.strip()
        if not name:
            raise ValueError('name 不能为空')
        object.__setattr__(self, 'name', name)

        search_name = self.search_name.strip() if self.search_name else None
        object.__setattr__(self, 'search_name', search_name)
        if self.min_level is not None and self.min_level < 1:
            raise ValueError('min_level 必须大于等于 1')
        if self.max_level is not None and self.max_level < 1:
            raise ValueError('max_level 必须大于等于 1')
        if (
            self.min_level is not None
            and self.max_level is not None
            and self.max_level < self.min_level
        ):
            raise ValueError('max_level 必须大于或等于 min_level')


@dataclass(frozen=True, slots=True)
class FleetSlotRule:
    """一个舰队槽位的严格主选和有序宽泛备选。"""

    primary: ShipSelector | None = None
    candidates: tuple[ShipSelector, ...] = ()

    def __post_init__(self) -> None:
        if self.primary is None and not self.candidates:
            raise ValueError('位置至少需要一艘主选或备选舰船')

    @property
    def options(self) -> tuple[ShipSelector, ...]:
        """返回智能编队按顺序尝试的完整规则。"""
        if self.primary is None:
            return self.candidates
        return (self.primary, *self.candidates)

    @property
    def preferred_name(self) -> str:
        """返回集合分配开始时使用的首个舰名。"""
        return self.options[0].name


@dataclass(frozen=True, slots=True)
class FleetPreset:
    """YAML 中一套已经完成入口转换的舰队预设。"""

    name: str
    slots: tuple[FleetSlotRule, ...]


class FleetSelectionSource(StrEnum):
    """最终舰队选择的数据来源。"""

    OVERRIDE_RULES = 'override_rules'
    OVERRIDE_FLEET = 'override_fleet'
    PLAN_PRESET = 'plan_preset'
    PLAN_FLEET = 'plan_fleet'
    NONE = 'none'


@dataclass(frozen=True, slots=True)
class ResolvedFleetSelection:
    """runner 启动前确定的唯一舰队选择结果。"""

    fleet_id: int
    slot_rules: tuple[FleetSlotRule, ...] | None
    plain_fleet: tuple[str, ...] | None
    source: FleetSelectionSource

    @property
    def primary_names(self) -> list[str | None] | None:
        """返回战斗记录可使用的显式主选舰名。"""
        if self.slot_rules is not None:
            return [
                rule.primary.name if rule.primary is not None else None
                for rule in self.slot_rules[:6]
            ]
        return list(self.plain_fleet) if self.plain_fleet is not None else None


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError('舰船名称必须是字符串')
    return value.strip() or None


def _optional_level(rule: Mapping[str, Any], field: str) -> int | None:
    value = rule.get(field)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f'{field} 必须是整数')
    return value


def _selector_from_mapping(
    raw: Mapping[str, Any],
    *,
    relaxed: bool,
    inherited: Mapping[str, Any] | None = None,
) -> ShipSelector:
    name = _optional_text(raw.get('name'))
    if name is None:
        raise ValueError('name 不能为空')
    source = raw if inherited is None else inherited
    inherited_search_name = inherited.get('search_name') if inherited is not None else None
    return ShipSelector(
        name=name,
        search_name=_optional_text(raw.get('search_name', inherited_search_name)),
        ship_types=parse_ship_type_codes(source.get('ship_type')),
        min_level=_optional_level(source, 'min_level'),
        max_level=_optional_level(source, 'max_level'),
        relaxed_constraints=relaxed,
    )


def fleet_slot_from_api(raw: str | Mapping[str, Any]) -> FleetSlotRule:
    """把已经通过 HTTP schema 的槽位转换成 canonical 规则。"""
    if isinstance(raw, str):
        return FleetSlotRule(primary=ShipSelector(name=raw))
    if not isinstance(raw, Mapping):
        raise TypeError('舰队槽位必须是字符串或规则对象')

    name = _optional_text(raw.get('name'))
    primary = _selector_from_mapping(raw, relaxed=False) if name is not None else None
    raw_candidates = raw.get('candidates', [])
    if not isinstance(raw_candidates, Sequence) or isinstance(raw_candidates, str):
        raise TypeError('candidates 必须是规则对象列表')
    candidates = tuple(
        _selector_from_mapping(candidate, relaxed=False)
        for candidate in raw_candidates
        if isinstance(candidate, Mapping)
    )
    if len(candidates) != len(raw_candidates):
        raise TypeError('HTTP candidates 只接受规则对象')
    return FleetSlotRule(primary=primary, candidates=candidates)


def fleet_slot_from_yaml(raw: object) -> FleetSlotRule:
    """把 YAML 槽位转换成 canonical 规则，并仅在此兼容旧字符串候选。"""
    if isinstance(raw, str):
        return FleetSlotRule(primary=ShipSelector(name=raw))
    if not isinstance(raw, Mapping):
        raise TypeError('舰队槽位必须是字符串或规则对象')

    raw_candidates = raw.get('candidates', [])
    if not isinstance(raw_candidates, Sequence) or isinstance(raw_candidates, str):
        raise TypeError('candidates 必须是列表')
    candidates = list(raw_candidates)

    primary: ShipSelector | None = None
    if _optional_text(raw.get('name')) is not None:
        primary = _selector_from_mapping(raw, relaxed=False)
    normalized_candidates: list[ShipSelector] = []
    seen: set[str] = set()
    for candidate in candidates:
        if isinstance(candidate, str):
            selector = _selector_from_mapping(
                {'name': candidate},
                relaxed=False,
                inherited=raw,
            )
        elif isinstance(candidate, Mapping):
            selector = _selector_from_mapping(candidate, relaxed=False)
        else:
            raise TypeError('candidates 只能包含舰名字符串或规则对象')
        if selector.name in seen:
            continue
        normalized_candidates.append(selector)
        seen.add(selector.name)
    return FleetSlotRule(primary=primary, candidates=tuple(normalized_candidates))


def fleet_presets_from_yaml(raw: object) -> tuple[FleetPreset, ...] | None:
    """解析 YAML 的舰队预设列表。"""
    if raw is None:
        return None
    if not isinstance(raw, list):
        raise TypeError('fleet_presets 必须是列表')

    presets: list[FleetPreset] = []
    for raw_preset in raw:
        if not isinstance(raw_preset, Mapping):
            raise TypeError('fleet_presets 每一项必须是对象')
        name = _optional_text(raw_preset.get('name')) or ''
        raw_slots = raw_preset.get('ships')
        if not isinstance(raw_slots, list):
            raise TypeError('fleet_presets.ships 必须是非空列表')
        if not raw_slots:
            raise ValueError('fleet_presets 不能包含空 ships')
        presets.append(
            FleetPreset(
                name=name,
                slots=tuple(fleet_slot_from_yaml(slot) for slot in raw_slots),
            ),
        )
    return tuple(presets)


def exact_fleet_rules(names: Sequence[str]) -> tuple[FleetSlotRule, ...]:
    """把普通舰名列表转换成精确槽位规则。"""
    return tuple(FleetSlotRule(primary=ShipSelector(name=name)) for name in names)


def resolve_fleet_selection(
    plan: CombatPlan,
    *,
    fleet_id: int | None = None,
    fleet: Sequence[str] | None = None,
    slot_rules: Sequence[FleetSlotRule] | None = None,
) -> ResolvedFleetSelection:
    """按 override rules > override fleet > plan preset > plan fleet 集中解析。"""
    resolved_id = fleet_id if fleet_id is not None else plan.fleet_id
    if slot_rules is not None:
        return ResolvedFleetSelection(
            fleet_id=resolved_id,
            slot_rules=tuple(slot_rules),
            plain_fleet=None,
            source=FleetSelectionSource.OVERRIDE_RULES,
        )
    if fleet is not None:
        return ResolvedFleetSelection(
            fleet_id=resolved_id,
            slot_rules=None,
            plain_fleet=tuple(fleet),
            source=FleetSelectionSource.OVERRIDE_FLEET,
        )
    if plan.fleet_presets:
        return ResolvedFleetSelection(
            fleet_id=resolved_id,
            slot_rules=plan.fleet_presets[0].slots,
            plain_fleet=None,
            source=FleetSelectionSource.PLAN_PRESET,
        )
    if plan.fleet is not None:
        return ResolvedFleetSelection(
            fleet_id=resolved_id,
            slot_rules=None,
            plain_fleet=tuple(plan.fleet),
            source=FleetSelectionSource.PLAN_FLEET,
        )
    return ResolvedFleetSelection(
        fleet_id=resolved_id,
        slot_rules=None,
        plain_fleet=None,
        source=FleetSelectionSource.NONE,
    )
