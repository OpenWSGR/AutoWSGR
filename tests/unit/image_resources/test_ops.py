"""Tests for autowsgr.image_resources.ops."""

from __future__ import annotations

import pytest

from autowsgr.image_resources.ops import (
    BackButton,
    Build,
    Confirm,
    Cook,
    Decisive,
    Error,
    Fight,
    FightResult,
    GameUI,
    Symbol,
    Templates,
)
from autowsgr.vision import ImageTemplate


@pytest.mark.parametrize(
    'template',
    [
        Templates.Cook.COOK_BUTTON,
        Templates.Cook.HAVE_COOK,
        Templates.Cook.NO_TIMES,
        Templates.Build.SHIP_START,
        Templates.Build.SHIP_COMPLETE,
        Templates.Build.SHIP_FAST,
        Templates.Build.SHIP_FULL_DEPOT,
        Templates.Build.EQUIP_START,
        Templates.Build.EQUIP_COMPLETE,
        Templates.Build.EQUIP_FAST,
        Templates.Build.EQUIP_FULL_DEPOT,
        Templates.Build.RESOURCE,
        Templates.GameUI.REWARD_COLLECT_ALL,
        Templates.GameUI.REWARD_COLLECT,
        Templates.Confirm.CONFIRM_1,
        Templates.Confirm.CONFIRM_2,
        Templates.Confirm.CONFIRM_3,
        Templates.Confirm.CONFIRM_4,
        Templates.Confirm.CONFIRM_5,
        Templates.Fight.NIGHT_BATTLE,
        Templates.Fight.RESULT_PAGE,
        Templates.FightResult.SS,
        Templates.FightResult.S,
        Templates.FightResult.A,
        Templates.FightResult.B,
        Templates.FightResult.C,
        Templates.FightResult.D,
        Templates.FightResult.LOOT,
        Templates.ChooseShip.PAGE_1,
        Templates.ChooseShip.PAGE_2,
        Templates.ChooseShip.PAGE_3,
        Templates.ChooseShip.PAGE_4,
        Templates.Symbol.GET_SHIP,
        Templates.Symbol.GET_ITEM,
        Templates.Symbol.CLICK_TO_CONTINUE,
        Templates.Error.BAD_NETWORK_1,
        Templates.Error.BAD_NETWORK_2,
        Templates.Error.NETWORK_RETRY,
        Templates.Error.REMOTE_LOGIN,
        Templates.Error.REMOTE_LOGIN_CONFIRM,
        Templates.Decisive.USE_LAST_FLEET,
        Templates.Decisive.ENTRY_CANT_FIGHT,
        Templates.Decisive.ENTRY_CHALLENGING,
        Templates.Decisive.ENTRY_REFRESHED,
        Templates.Decisive.ENTRY_REFRESH,
    ],
)
def test_leaf_attributes_return_image_template(template: object) -> None:
    """Key leaf attributes exist and return ImageTemplate instances."""
    assert isinstance(template, ImageTemplate)


def test_confirm_all_returns_five_image_templates() -> None:
    """Confirm.all() returns a list of exactly 5 ImageTemplates."""
    templates = Confirm.all()
    assert len(templates) == 5
    assert all(isinstance(t, ImageTemplate) for t in templates)


def test_fight_result_all_grades_returns_six_image_templates() -> None:
    """FightResult.all_grades() returns SS→D (6 items, no LOOT)."""
    templates = FightResult.all_grades()
    assert len(templates) == 6
    assert all(isinstance(t, ImageTemplate) for t in templates)
    assert FightResult.LOOT not in templates


@pytest.mark.xfail(
    raises=FileNotFoundError,
    reason='Back button images missing from data/images/common/',
)
def test_back_button_all_returns_non_empty_list() -> None:
    """BackButton.all() returns a non-empty list of ImageTemplates."""
    templates = BackButton.all()
    assert len(templates) > 0
    assert all(isinstance(t, ImageTemplate) for t in templates)


def test_decisive_entry_status_templates_returns_four() -> None:
    """Decisive.entry_status_templates() returns 4 ImageTemplates."""
    templates = Decisive.entry_status_templates()
    assert len(templates) == 4
    assert all(isinstance(t, ImageTemplate) for t in templates)


def test_fight_result_pages_returns_list() -> None:
    """Fight.result_pages() returns a list of ImageTemplates."""
    templates = Fight.result_pages()
    assert len(templates) > 0
    assert all(isinstance(t, ImageTemplate) for t in templates)


def test_templates_aggregates_all_sub_containers() -> None:
    """Templates exposes all sub-container classes."""
    assert Templates.Cook is Cook
    assert Templates.GameUI is GameUI
    assert Templates.Confirm is Confirm
    assert Templates.Build is Build
    assert Templates.Fight is Fight
    assert Templates.FightResult is FightResult
    assert Templates.Symbol is Symbol
    assert Templates.BackButton is BackButton
    assert Templates.Error is Error
    assert Templates.Decisive is Decisive


def test_lazy_loading_consistency() -> None:
    """Accessing the same LazyTemplate twice returns the identical object."""
    first = Templates.Cook.COOK_BUTTON
    second = Templates.Cook.COOK_BUTTON
    assert first is second
