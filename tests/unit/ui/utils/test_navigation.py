"""Tests for autowsgr.ui.utils.navigation."""

from __future__ import annotations

import pytest

from autowsgr.ui.utils.navigation import (
    DEFAULT_NAV_CONFIG,
    NavConfig,
    NavigationError,
)


def test_navigation_error_raise_and_catch() -> None:
    """NavigationError can be raised and caught; str(err) returns message."""
    with pytest.raises(NavigationError, match='page not found'):
        raise NavigationError('page not found')


def test_navigation_error_without_screen() -> None:
    """NavigationError without screen does not crash."""
    err = NavigationError('missing screen')
    assert str(err) == 'missing screen'


def test_nav_config_defaults() -> None:
    """NavConfig has expected default values."""
    config = NavConfig()
    assert config.max_retries == 2
    assert config.retry_delay == 1.0
    assert config.timeout == 5.0
    assert config.interval == 0.5
    assert config.handle_overlays is True


def test_nav_config_is_frozen() -> None:
    """NavConfig is frozen and raises AttributeError on mutation."""
    config = NavConfig()
    with pytest.raises(AttributeError):
        config.max_retries = 10  # ty: ignore[invalid-assignment]


def test_nav_config_has_slots() -> None:
    """NavConfig uses __slots__ and does not allow arbitrary attributes."""
    config = NavConfig()
    with pytest.raises(AttributeError):
        object.__setattr__(config, 'new_attr', 'value')


def test_default_nav_config_instance() -> None:
    """DEFAULT_NAV_CONFIG is a NavConfig instance with default values."""
    assert isinstance(DEFAULT_NAV_CONFIG, NavConfig)
    assert DEFAULT_NAV_CONFIG.max_retries == 2
    assert DEFAULT_NAV_CONFIG.retry_delay == 1.0
    assert DEFAULT_NAV_CONFIG.timeout == 5.0
    assert DEFAULT_NAV_CONFIG.interval == 0.5
    assert DEFAULT_NAV_CONFIG.handle_overlays is True


def test_nav_config_custom_values() -> None:
    """NavConfig accepts custom values."""
    config = NavConfig(
        max_retries=5,
        retry_delay=2.0,
        timeout=10.0,
        interval=1.0,
        handle_overlays=False,
    )
    assert config.max_retries == 5
    assert config.retry_delay == 2.0
    assert config.timeout == 10.0
    assert config.interval == 1.0
    assert config.handle_overlays is False
