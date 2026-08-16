"""Device-driving route conflict tests."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from autowsgr.server import main as server_main
from autowsgr.server.device_lease import device_operation_lease
from autowsgr.server.routes import game, ops


@pytest.mark.parametrize(
    'route_call',
    [
        ops.expedition_check,
        lambda: ops.expedition_auto_check(ops.ExpeditionAutoCheckRequest()),
        ops.build_collect,
        lambda: ops.build_start(ops.BuildStartRequest()),
        ops.reward_collect,
        lambda: ops.cook_action(ops.CookRequest()),
        ops.repair_bath,
        lambda: ops.repair_ship(ops.RepairShipRequest(ship_name='测试舰')),
        lambda: ops.destroy_action(ops.DestroyRequest()),
        game.game_acquisition,
    ],
)
def test_device_routes_reject_active_owner_before_context_access(
    monkeypatch: pytest.MonkeyPatch,
    route_call: object,
) -> None:
    """Every direct device route shares the same non-blocking lease."""
    context_reads = 0

    def get_context() -> object:
        nonlocal context_reads
        context_reads += 1
        return object()

    monkeypatch.setattr(ops, 'get_context', get_context)
    monkeypatch.setattr(game, 'get_context', get_context)
    monkeypatch.setattr(server_main, '_ctx', object())
    token = device_operation_lease.acquire('task:active')
    try:
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(route_call())  # type: ignore[operator]
    finally:
        device_operation_lease.release(token)

    assert exc_info.value.status_code == 409
    assert context_reads == 0
