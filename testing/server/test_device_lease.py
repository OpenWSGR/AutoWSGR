"""Shared emulator ownership tests."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from autowsgr.server.device_lease import (
    DeviceOperationLease,
    exclusive_device_operation,
)


def test_stale_token_cannot_release_new_owner() -> None:
    """Only the exact current owner can release the device."""
    lease = DeviceOperationLease()
    first = lease.acquire('first')
    lease.release(first)
    second = lease.acquire('second')

    lease.release(first)

    assert lease.owner == 'second'
    lease.release(second)
    assert lease.owner is None


def test_http_device_operation_rejects_busy_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Device-driving HTTP operations return 409 instead of waiting."""
    lease = DeviceOperationLease()
    monkeypatch.setattr(
        'autowsgr.server.device_lease.device_operation_lease',
        lease,
    )
    active = lease.acquire('task:active')
    called = False

    @exclusive_device_operation('api:test')
    async def operation() -> None:
        nonlocal called
        called = True

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(operation())

    assert exc_info.value.status_code == 409
    assert called is False
    lease.release(active)


def test_http_device_operation_releases_after_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An operation exception cannot leak device ownership."""
    lease = DeviceOperationLease()
    monkeypatch.setattr(
        'autowsgr.server.device_lease.device_operation_lease',
        lease,
    )

    @exclusive_device_operation('api:test')
    async def operation() -> None:
        raise RuntimeError('failed')

    with pytest.raises(RuntimeError, match='failed'):
        asyncio.run(operation())

    assert lease.owner is None
