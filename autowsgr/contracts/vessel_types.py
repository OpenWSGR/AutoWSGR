"""由 :mod:`autowsgr_native` 派生的舰队舰种公共契约。"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

from autowsgr_native.vessel_type import VesselType


if TYPE_CHECKING:
    from collections.abc import Mapping


CONTRACT_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class FleetVesselType:
    """一个可用于舰队规则的 native 舰种。"""

    code: str
    label: str
    native: VesselType


def _discover_fleet_vessel_types() -> tuple[FleetVesselType, ...]:
    """发现 native 普通舰种；``NO`` 是唯一的大写特殊类型。"""
    vessel_types: list[FleetVesselType] = []
    for attribute in sorted(name for name in dir(VesselType) if name.isupper()):
        native = getattr(VesselType, attribute)
        code = native.as_english()
        if code == 'NO':
            continue
        if code != attribute or VesselType.from_english(code) != native:
            raise RuntimeError(f'autowsgr_native 舰种契约无效: {attribute}')
        vessel_types.append(
            FleetVesselType(
                code=code.lower(),
                label=native.as_chinese(),
                native=native,
            ),
        )
    return tuple(vessel_types)


FLEET_VESSEL_TYPES = _discover_fleet_vessel_types()
"""当前 native 提供的全部普通舰种。"""

FLEET_VESSEL_TYPE_BY_CODE: Mapping[str, FleetVesselType] = MappingProxyType(
    {vessel_type.code: vessel_type for vessel_type in FLEET_VESSEL_TYPES},
)
"""小写 canonical code 到 native 舰种契约的只读映射。"""


def fleet_vessel_type_from_code(value: str) -> FleetVesselType:
    """校验并返回一个 canonical 舰队舰种。"""
    code = value.strip().lower()
    vessel_type = FLEET_VESSEL_TYPE_BY_CODE.get(code)
    if vessel_type is None:
        allowed = ', '.join(FLEET_VESSEL_TYPE_BY_CODE)
        raise ValueError(f'不支持的舰队舰种: {value!r}, 可选值: {allowed}')
    return vessel_type


def fleet_vessel_type_contract() -> dict[str, object]:
    """返回供 GUI 生成代码使用的稳定 JSON 契约。"""
    return {
        'schema_version': CONTRACT_SCHEMA_VERSION,
        'source': 'autowsgr_native.vessel_type.VesselType',
        'ship_types': [
            {
                'code': vessel_type.code,
                'label': vessel_type.label,
            }
            for vessel_type in FLEET_VESSEL_TYPES
        ],
    }


def main() -> None:
    """向标准输出写出 JSON 契约。"""
    sys.stdout.write(
        f'{json.dumps(fleet_vessel_type_contract(), ensure_ascii=False)}\n',
    )


if __name__ == '__main__':
    main()
