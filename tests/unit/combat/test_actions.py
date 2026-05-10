"""Tests for autowsgr.combat.actions."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock, call, patch

import pytest

from autowsgr.combat.actions import (
    Coords,
    check_blood,
    click_enter_fight,
    click_fight_condition,
    click_formation,
    click_image,
    click_night_battle,
    click_proceed,
    click_result,
    click_retreat,
    click_skip_missile_animation,
    click_speed_up,
    click_start_march,
    dismiss_resource_confirm,
    get_enemy_formation,
    image_exist,
)
from autowsgr.types import RepairMode, ShipDamageState
from autowsgr.vision.image_template import ImageMatchDetail


class TestCheckBlood:
    """Tests for check_blood pure logic."""

    def test_scalar_repair_mode_all_ok(self) -> None:
        stats = [ShipDamageState.NORMAL] * 6
        assert check_blood(stats, RepairMode.moderate_damage) is True

    def test_scalar_repair_mode_one_exceeds(self) -> None:
        stats = [ShipDamageState.NORMAL] * 5 + [ShipDamageState.MODERATE]
        assert check_blood(stats, RepairMode.moderate_damage) is False

    def test_per_slot_list(self) -> None:
        stats = [
            ShipDamageState.NORMAL,
            ShipDamageState.MODERATE,
            ShipDamageState.NORMAL,
            ShipDamageState.NORMAL,
            ShipDamageState.NORMAL,
            ShipDamageState.NORMAL,
        ]
        rules = [
            RepairMode.severe_damage,
            RepairMode.moderate_damage,
            RepairMode.severe_damage,
            RepairMode.severe_damage,
            RepairMode.severe_damage,
            RepairMode.severe_damage,
        ]
        assert check_blood(stats, rules) is False

    def test_no_ship_skipped(self) -> None:
        stats = [ShipDamageState.NO_SHIP] * 6
        assert check_blood(stats, RepairMode.moderate_damage) is True

    def test_threshold_boundaries(self) -> None:
        # moderate_damage (1): NORMAL (0) ok, MODERATE (1) fail, SEVERE (2) fail
        assert check_blood([ShipDamageState.NORMAL], RepairMode.moderate_damage) is True
        assert check_blood([ShipDamageState.MODERATE], RepairMode.moderate_damage) is False
        assert check_blood([ShipDamageState.SEVERE], RepairMode.moderate_damage) is False

        # severe_damage (2): NORMAL (0) ok, MODERATE (1) ok, SEVERE (2) fail
        assert check_blood([ShipDamageState.NORMAL], RepairMode.severe_damage) is True
        assert check_blood([ShipDamageState.MODERATE], RepairMode.severe_damage) is True
        assert check_blood([ShipDamageState.SEVERE], RepairMode.severe_damage) is False


def test_coords_attributes_are_tuples_of_floats() -> None:
    for name in dir(Coords):
        if name.startswith('_'):
            continue
        value = getattr(Coords, name)
        assert isinstance(value, tuple), f'{name} is not a tuple'
        assert len(value) == 2, f'{name} does not have length 2'
        assert all(isinstance(v, float) for v in value), f'{name} values are not floats'


class TestClickFunctions:
    """Tests for click_* helpers."""

    @pytest.fixture
    def device(self) -> MagicMock:
        return MagicMock()

    def test_click_start_march(self, device: MagicMock) -> None:
        with patch('autowsgr.combat.actions.time.sleep'):
            click_start_march(device)
        device.click.assert_called_once_with(*Coords.START_MARCH)

    def test_click_retreat(self, device: MagicMock) -> None:
        with patch('autowsgr.combat.actions.time.sleep'):
            click_retreat(device)
        device.click.assert_called_once_with(*Coords.RETREAT)

    def test_click_enter_fight(self, device: MagicMock) -> None:
        with patch('autowsgr.combat.actions.time.sleep'):
            click_enter_fight(device)
        device.click.assert_called_once_with(*Coords.ENTER_FIGHT)

    def test_click_result(self, device: MagicMock) -> None:
        with patch('autowsgr.combat.actions.time.sleep'):
            click_result(device)
        device.click.assert_called_once_with(*Coords.CLICK_RESULT)

    def test_click_skip_missile_animation(self, device: MagicMock) -> None:
        with patch('autowsgr.combat.actions.time.sleep'):
            click_skip_missile_animation(device)
        assert device.click.call_count == 2
        device.click.assert_has_calls(
            [call(*Coords.SPEED_UP_BATTLE), call(*Coords.SPEED_UP_BATTLE)]
        )

    def test_click_night_battle_pursue(self, device: MagicMock) -> None:
        with patch('autowsgr.combat.actions.time.sleep'):
            click_night_battle(device, pursue=True)
        device.click.assert_called_once_with(*Coords.NIGHT_YES)

    def test_click_night_battle_retreat(self, device: MagicMock) -> None:
        with patch('autowsgr.combat.actions.time.sleep'):
            click_night_battle(device, pursue=False)
        device.click.assert_called_once_with(*Coords.NIGHT_NO)

    def test_click_proceed_forward(self, device: MagicMock) -> None:
        with patch('autowsgr.combat.actions.time.sleep'):
            click_proceed(device, go_forward=True)
        device.click.assert_called_once_with(*Coords.PROCEED_YES)

    def test_click_proceed_retreat(self, device: MagicMock) -> None:
        with patch('autowsgr.combat.actions.time.sleep'):
            click_proceed(device, go_forward=False)
        device.click.assert_called_once_with(*Coords.PROCEED_NO)

    def test_click_formation(self, device: MagicMock) -> None:
        with patch('autowsgr.combat.actions.time.sleep'):
            formation = MagicMock()
            formation.relative_position = (0.123, 0.456)
            click_formation(device, cast('Any', formation))
        device.click.assert_called_once_with(0.123, 0.456)

    def test_click_fight_condition(self, device: MagicMock) -> None:
        with patch('autowsgr.combat.actions.time.sleep'):
            condition = MagicMock()
            condition.relative_click_position = (0.789, 0.321)
            click_fight_condition(device, cast('Any', condition))
        device.click.assert_called_once_with(0.789, 0.321)

    def test_click_speed_up_normal(self, device: MagicMock) -> None:
        with patch('autowsgr.combat.actions.time.sleep'):
            click_speed_up(device, battle_mode=False)
        device.click.assert_called_once_with(*Coords.SPEED_UP_NORMAL)

    def test_click_speed_up_battle(self, device: MagicMock) -> None:
        with patch('autowsgr.combat.actions.time.sleep'):
            click_speed_up(device, battle_mode=True)
        device.click.assert_called_once_with(*Coords.SPEED_UP_BATTLE)


class TestImageExist:
    """Tests for image_exist."""

    @pytest.fixture
    def device(self) -> MagicMock:
        return MagicMock()

    @patch('autowsgr.combat.actions.ImageChecker')
    def test_image_exist_true(self, mock_checker: MagicMock, device: MagicMock) -> None:
        mock_checker.find_any.return_value = MagicMock()
        template_key = MagicMock()
        template_key.templates = [MagicMock()]

        result = image_exist(device, cast('Any', template_key), confidence=0.8)
        assert result is True
        device.screenshot.assert_called_once()
        mock_checker.find_any.assert_called_once()

    @patch('autowsgr.combat.actions.ImageChecker')
    def test_image_exist_false(self, mock_checker: MagicMock, device: MagicMock) -> None:
        mock_checker.find_any.return_value = None
        template_key = MagicMock()
        template_key.templates = [MagicMock()]

        result = image_exist(device, cast('Any', template_key), confidence=0.8)
        assert result is False
        device.screenshot.assert_called_once()
        mock_checker.find_any.assert_called_once()


class TestClickImage:
    """Tests for click_image."""

    @pytest.fixture
    def device(self) -> MagicMock:
        return MagicMock()

    @patch('autowsgr.combat.actions.ImageChecker')
    def test_click_image_success(self, mock_checker: MagicMock, device: MagicMock) -> None:
        with patch('autowsgr.combat.actions.time.sleep'):
            detail = ImageMatchDetail(
                template_name='test',
                confidence=0.9,
                center=(0.5, 0.6),
                top_left=(0.4, 0.5),
                bottom_right=(0.6, 0.7),
            )
            mock_checker.find_any.return_value = detail
            template_key = MagicMock()
            template_key.templates = [MagicMock()]

            result = click_image(device, cast('Any', template_key), timeout=1.0)
            assert result is True
            device.screenshot.assert_called_once()
            device.click.assert_called_once_with(0.5, 0.6)

    @patch('autowsgr.combat.actions.ImageChecker')
    def test_click_image_timeout(self, mock_checker: MagicMock, device: MagicMock) -> None:
        with patch('autowsgr.combat.actions.time.sleep'):
            mock_checker.find_any.return_value = None
            template_key = MagicMock()
            template_key.templates = [MagicMock()]

            with patch('autowsgr.combat.actions.time.time', side_effect=[0.0, 0.0, 0.0, 10.0]):
                result = click_image(device, cast('Any', template_key), timeout=0.1)
                assert result is False
                assert device.screenshot.call_count == 2
                assert mock_checker.find_any.call_count == 2
                device.click.assert_not_called()


def test_get_enemy_formation_returns_empty_when_no_ocr() -> None:
    device = MagicMock()
    assert get_enemy_formation(device, cast('Any', None)) == ''
    device.screenshot.assert_not_called()


class TestDismissResourceConfirm:
    """Tests for dismiss_resource_confirm."""

    @patch('autowsgr.combat.actions.ImageChecker')
    def test_no_confirm_found(self, mock_checker: MagicMock) -> None:
        with (
            patch('autowsgr.combat.actions.time.sleep'),
            patch('autowsgr.combat.actions.Templates'),
        ):
            mock_checker.find_any.return_value = None
            device = MagicMock()
            screen = MagicMock()
            dismiss_resource_confirm(device, screen)
        device.click.assert_not_called()

    @patch('autowsgr.combat.actions.ImageChecker')
    def test_confirm_found_and_clicked(self, mock_checker: MagicMock) -> None:
        with (
            patch('autowsgr.combat.actions.time.sleep'),
            patch('autowsgr.combat.actions.Templates'),
        ):
            detail = ImageMatchDetail(
                template_name='confirm',
                confidence=0.8,
                center=(0.5, 0.5),
                top_left=(0.4, 0.4),
                bottom_right=(0.6, 0.6),
            )
            mock_checker.find_any.return_value = detail
            device = MagicMock()
            screen = MagicMock()
            dismiss_resource_confirm(device, screen)
        device.click.assert_called_once_with(0.5, 0.5)
