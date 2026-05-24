"""测试 autowsgr.ui.battle.detection."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from autowsgr.context.ship import Ship
from autowsgr.types import ShipDamageState
from autowsgr.ui.battle.detection import DetectionMixin, FleetInfo


class TestFleetInfo:
    def test_defaults(self) -> None:
        info = FleetInfo()
        assert info.fleet_id is None
        assert info.ship_levels == {}
        assert info.ship_damage == {}

    def test_to_ships_with_names(self) -> None:
        info = FleetInfo(
            ship_levels={0: 120, 1: 98, 2: None, 3: 50},
            ship_damage={
                0: ShipDamageState.NORMAL,
                1: ShipDamageState.MODERATE,
                2: ShipDamageState.NO_SHIP,
                3: ShipDamageState.NORMAL,
                4: ShipDamageState.NO_SHIP,
                5: ShipDamageState.NO_SHIP,
            },
        )
        names = ['ship_a', None, None, 'ship_d']
        ships = info.to_ships(names)

        assert len(ships) == 3
        assert ships[0] == Ship(
            name='ship_a',
            level=120,
            damage_state=ShipDamageState.NORMAL,
        )
        assert ships[1] == Ship(
            name='',
            level=98,
            damage_state=ShipDamageState.MODERATE,
        )
        assert ships[2] == Ship(
            name='ship_d',
            level=50,
            damage_state=ShipDamageState.NORMAL,
        )

    def test_to_ships_with_none_names(self) -> None:
        info = FleetInfo(
            ship_levels={0: 10},
            ship_damage={
                0: ShipDamageState.NORMAL,
                1: ShipDamageState.NO_SHIP,
                2: ShipDamageState.NO_SHIP,
                3: ShipDamageState.NO_SHIP,
                4: ShipDamageState.NO_SHIP,
                5: ShipDamageState.NO_SHIP,
            },
        )
        ships = info.to_ships(None)

        assert len(ships) == 1
        assert ships[0] == Ship(
            name='',
            level=10,
            damage_state=ShipDamageState.NORMAL,
        )

    def test_to_ships_uses_ship_levels(self) -> None:
        info = FleetInfo(
            ship_levels={0: 77, 1: None},
            ship_damage={
                0: ShipDamageState.NORMAL,
                1: ShipDamageState.SEVERE,
                2: ShipDamageState.NO_SHIP,
                3: ShipDamageState.NO_SHIP,
                4: ShipDamageState.NO_SHIP,
                5: ShipDamageState.NO_SHIP,
            },
        )
        ships = info.to_ships()

        assert len(ships) == 2
        assert ships[0].level == 77
        assert ships[1].level == 0


class TestParseLevel:
    @pytest.mark.parametrize(
        ('text', 'expected'),
        [
            ('Lv.120', 120),
            ('lv 98', 98),
            ('0.106', 106),
            ('1V.31', 31),
            ('497', 97),
            ('abc', None),
            ('', None),
        ],
    )
    def test_cases(self, text: str, expected: int | None) -> None:
        assert DetectionMixin._parse_level(text) == expected


class TestBestLevelFromResults:
    def _make_result(self, text: str) -> SimpleNamespace:
        return SimpleNamespace(text=text)

    def test_prefers_v_results(self) -> None:
        results = [
            self._make_result('abc'),
            self._make_result('120'),
            self._make_result('Lv.99'),
        ]
        assert DetectionMixin._best_level_from_results(results) == 99

    def test_falls_back_to_pure_digits(self) -> None:
        results = [
            self._make_result('abc'),
            self._make_result('120'),
            self._make_result('xyz'),
        ]
        assert DetectionMixin._best_level_from_results(results) == 120

    def test_returns_none_when_no_candidates(self) -> None:
        results = [
            self._make_result('abc'),
            self._make_result('xyz'),
        ]
        assert DetectionMixin._best_level_from_results(results) is None
