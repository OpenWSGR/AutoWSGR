"""场景策略和证据模块共享的不可变状态；不持有跨事件历史。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    import numpy as np

_NAV = 'NAVIGATING'
_SPOT = 'SPOT'
_DETOUR = 'DETOUR_PENDING'
_DEPART = 'DEPART_PENDING'
_COMBAT = 'COMBAT'
_POST = 'POST_COMBAT'
_RETURN = 'RETURN_PENDING'
_END = 'END'
_PHASE_STAGE = {
    'SPOT_ENEMY_SUCCESS': _SPOT,
    'FORMATION': _COMBAT,
    'MISSILE_ANIMATION': _COMBAT,
    'FIGHT_PERIOD': _COMBAT,
    'NIGHT_PROMPT': _COMBAT,
    'RESULT': _POST,
    'EXP_SETTLEMENT': _POST,
    'GET_SHIP': _POST,
    'PROCEED': _POST,
    'GARRISON': _POST,
    'FLAGSHIP_SEVERE_DAMAGE': _POST,
}


_MAP_READY = 'MAP_READY'
_TERMINAL = 'TERMINAL_PENDING'


@dataclass(frozen=True, slots=True)
class _EnemySignature:
    ships: tuple[str | None, ...]
    formation: int | None
    detour: bool | None


@dataclass(frozen=True, slots=True)
class _State:
    node: str
    stage: str
    variant: int = -1
    route: tuple[str, ...] = ()
    edge: int = 0
    evidence: tuple[_EnemySignature, ...] = ()
    pending_since: float | None = None
    detour_succeeds: bool | None = None
    leg_observed: bool = False
    leg_origin: str | None = None
    labels: tuple[str, ...] = ()
    encounter_id: str | None = None


@dataclass(frozen=True, slots=True)
class _Edge:
    source: int
    target: int
    weight: float
    label: str
    path: tuple[str, ...]
    geometry: float
    enemy: float
    node_label: float = 0.0


@dataclass(slots=True)
class _Layer:
    event_id: int
    states: tuple[_State, ...]
    forward: np.ndarray
    viterbi: np.ndarray
    edges: tuple[_Edge, ...]
    best_edges: tuple[int, ...]
