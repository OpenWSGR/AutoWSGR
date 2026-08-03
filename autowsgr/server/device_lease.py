"""Exclusive ownership for operations that drive the shared emulator."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from functools import wraps
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


class DeviceOperationBusyError(RuntimeError):
    """Raised when another operation already owns the shared device."""


@dataclass(frozen=True)
class DeviceOperationToken:
    """Opaque ownership token used for compare-and-release semantics."""

    owner: str
    identity: object


class DeviceOperationLease:
    """A non-blocking, token-owned lease for the shared emulator."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._token: DeviceOperationToken | None = None

    def acquire(self, owner: str) -> DeviceOperationToken:
        """Acquire ownership immediately or report that the device is busy."""
        with self._lock:
            if self._token is not None:
                raise DeviceOperationBusyError(f'设备正由 {self._token.owner} 使用')
            token = DeviceOperationToken(owner=owner, identity=object())
            self._token = token
            return token

    def release(self, token: DeviceOperationToken) -> None:
        """Release ownership only when the exact active token is supplied."""
        with self._lock:
            if self._token is token:
                self._token = None

    @property
    def owner(self) -> str | None:
        """Return the current owner for status and diagnostics."""
        with self._lock:
            return self._token.owner if self._token is not None else None


device_operation_lease = DeviceOperationLease()


def exclusive_device_operation(
    owner: str,
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Reject concurrent HTTP device operations with a consistent 409 response."""
    from fastapi import HTTPException

    def decorator(
        handler: Callable[..., Awaitable[Any]],
    ) -> Callable[..., Awaitable[Any]]:
        @wraps(handler)
        async def wrapped(*args: Any, **kwargs: Any) -> Any:
            try:
                token = device_operation_lease.acquire(owner)
            except DeviceOperationBusyError as error:
                raise HTTPException(status_code=409, detail=str(error)) from error
            try:
                return await handler(*args, **kwargs)
            finally:
                device_operation_lease.release(token)

        return wrapped

    return decorator
