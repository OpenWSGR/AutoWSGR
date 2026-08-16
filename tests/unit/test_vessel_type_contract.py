"""native 舰种公共契约测试。"""

from autowsgr.contracts.vessel_types import (
    FLEET_VESSEL_TYPE_BY_CODE,
    FLEET_VESSEL_TYPES,
    fleet_vessel_type_contract,
    fleet_vessel_type_from_code,
)


def test_fleet_vessel_type_contract_is_derived_from_native():
    payload = fleet_vessel_type_contract()

    assert payload['schema_version'] == 1
    assert payload['source'] == 'autowsgr_native.vessel_type.VesselType'
    assert payload['ship_types'] == [
        {'code': vessel_type.code, 'label': vessel_type.native.as_chinese()}
        for vessel_type in FLEET_VESSEL_TYPES
    ]
    assert set(FLEET_VESSEL_TYPE_BY_CODE) == {
        vessel_type.native.as_english().lower() for vessel_type in FLEET_VESSEL_TYPES
    }
    assert 'no' not in FLEET_VESSEL_TYPE_BY_CODE


def test_guided_missile_cruiser_codes_follow_native_semantics():
    assert fleet_vessel_type_from_code('KP').label == '导巡'
    assert fleet_vessel_type_from_code('cg').label == '防巡'
