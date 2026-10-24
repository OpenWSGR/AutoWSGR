"""Regression coverage for missing map frames and unknown-node combat decisions."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from autowsgr.combat import handlers as handlers_mod
from autowsgr.combat.engine import CombatEngine
from autowsgr.combat.node_tracker import MapNodeData, NodeTracker
from autowsgr.combat.plan import CombatMode, CombatPlan, NodeDecision
from autowsgr.types import ConditionFlag, Formation


@pytest.fixture
def map_data() -> MapNodeData:
    data = MapNodeData.load(2, 1)
    assert data is not None
    return data


@pytest.fixture
def screen() -> np.ndarray:
    return np.zeros((540, 960, 3), dtype=np.uint8)


@pytest.fixture
def actions(monkeypatch: pytest.MonkeyPatch) -> dict[str, MagicMock]:
    mocks = {}
    for name in ('click_retreat', 'click_enter_fight', 'click_formation', 'click_proceed'):
        mocks[name] = MagicMock()
        monkeypatch.setattr(handlers_mod, name, mocks[name])
    monkeypatch.setattr(handlers_mod, 'get_enemy_info', lambda *_args, **_kwargs: {'DD': 6})
    monkeypatch.setattr(handlers_mod, 'get_enemy_formation', lambda *_args: None)
    monkeypatch.setattr(handlers_mod, 'image_exist', lambda *_args: False)
    return mocks


def make_engine(mode: str, node: str, selected_nodes: list[str]) -> CombatEngine:
    engine = CombatEngine(MagicMock())
    engine._plan = CombatPlan(
        mode=mode,
        chapter=2,
        map_id=1,
        selected_nodes=selected_nodes,
        default_node=NodeDecision(formation=Formation.wedge, proceed=True),
    )
    engine._node = node
    return engine


def set_frames(
    monkeypatch: pytest.MonkeyPatch,
    tracker: NodeTracker,
    positions: list[tuple[float, float] | None],
) -> None:
    monkeypatch.setattr(tracker, 'is_spot_page', lambda _screen: False)
    monkeypatch.setattr(tracker, '_find_yellow_cluster', MagicMock(side_effect=positions))
    monkeypatch.setattr(tracker, '_recheck_pixel', lambda *_args: True)


@pytest.mark.parametrize(
    ('position', 'expected_node'),
    [((0.254, 0.266), 'A'), ((0.249, 0.499), 'B')],
)
def test_first_visible_frame_identifies_outgoing_route(
    map_data: MapNodeData,
    screen: np.ndarray,
    monkeypatch: pytest.MonkeyPatch,
    position: tuple[float, float],
    expected_node: str,
) -> None:
    """A route must not require a second frame before the spot-enemy page appears."""
    tracker = NodeTracker(map_data)
    set_frames(monkeypatch, tracker, [position])
    assert tracker.track(screen) == expected_node


def test_confirmed_b_d_f_route_keeps_tracking(
    map_data: MapNodeData, screen: np.ndarray, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracker = NodeTracker(map_data)
    set_frames(
        monkeypatch,
        tracker,
        [(0.249, 0.499), (0.276, 0.598), (0.316, 0.747), (0.392, 0.784)],
    )
    assert [tracker.track(screen) for _ in range(4)] == ['B', 'D', 'D', 'F']


def test_reset_starts_new_sortie_without_previous_route_velocity(
    map_data: MapNodeData, screen: np.ndarray, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracker = NodeTracker(map_data)
    set_frames(monkeypatch, tracker, [(0.249, 0.499), (0.254, 0.266)])
    assert tracker.track(screen) == 'B'
    tracker.reset()
    assert tracker.current_node == '0'
    assert tracker.ship_position is None
    assert tracker.track(screen) == 'A'


@pytest.mark.parametrize('position', [(0.181, 0.268), (0.186, 0.268), (0.181, 0.273)])
def test_first_frame_near_origin_stays_unknown(
    map_data: MapNodeData,
    screen: np.ndarray,
    monkeypatch: pytest.MonkeyPatch,
    position: tuple[float, float],
) -> None:
    tracker = NodeTracker(map_data)
    set_frames(monkeypatch, tracker, [position, position])
    assert tracker.track(screen) == '0'
    assert tracker.track(screen) == '0'


def test_map_without_origin_does_not_guess_from_first_frame(
    map_data: MapNodeData, screen: np.ndarray, monkeypatch: pytest.MonkeyPatch
) -> None:
    nodes = {name: map_data.get(name) for name in map_data.node_names}
    tracker = NodeTracker(MapNodeData(nodes))
    set_frames(monkeypatch, tracker, [(0.254, 0.266), (0.330, 0.257)])
    assert tracker.track(screen) == '0'
    assert tracker.track(screen) == '0'


def test_origin_jitter_does_not_hide_the_first_outgoing_frame(
    map_data: MapNodeData, screen: np.ndarray, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracker = NodeTracker(map_data)
    set_frames(monkeypatch, tracker, [(0.181, 0.273), (0.186, 0.268), (0.254, 0.266)])
    assert [tracker.track(screen) for _ in range(3)] == ['0', '0', 'A']


def test_missing_ship_frame_keeps_node_unknown(
    map_data: MapNodeData, screen: np.ndarray, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracker = NodeTracker(map_data)
    set_frames(monkeypatch, tracker, [None])
    assert tracker.track(screen) == '0'


def test_only_route_frame_before_spot_enemy_retreats_at_disabled_a(
    map_data: MapNodeData,
    screen: np.ndarray,
    monkeypatch: pytest.MonkeyPatch,
    actions: dict[str, MagicMock],
) -> None:
    """Reproduce the log: one ship frame, then a spot page that hides the route."""
    tracker = NodeTracker(map_data)
    set_frames(monkeypatch, tracker, [(0.254, 0.266)])
    monkeypatch.setattr(tracker, 'is_spot_page', MagicMock(side_effect=[False, True]))
    assert tracker.track(screen) == 'A'
    engine = make_engine(CombatMode.NORMAL, tracker.track(screen), ['0', 'B', 'D', 'F'])

    assert engine._handle_spot_enemy() == ConditionFlag.FIGHT_END
    actions['click_retreat'].assert_called_once_with(engine._device)
    actions['click_enter_fight'].assert_not_called()
    assert engine.history.events[-1].node == 'A'
    assert engine.history.events[-1].action == '撤退'


@pytest.mark.parametrize('mode', [CombatMode.NORMAL, CombatMode.EVENT])
@pytest.mark.parametrize('selected_nodes', [[], ['0', 'B', 'D', 'F']])
def test_unknown_map_node_retreats_even_when_whitelist_allows_zero(
    mode: str, selected_nodes: list[str], actions: dict[str, MagicMock]
) -> None:
    engine = make_engine(mode, '0', selected_nodes)
    assert engine._handle_spot_enemy() == ConditionFlag.FIGHT_END
    actions['click_retreat'].assert_called_once_with(engine._device)
    actions['click_enter_fight'].assert_not_called()
    assert engine.history.events[-1].action == '撤退'


@pytest.mark.parametrize('mode', [CombatMode.NORMAL, CombatMode.EVENT])
@pytest.mark.parametrize('selected_nodes', [[], ['0', 'B', 'D', 'F']])
def test_unknown_map_node_does_not_select_formation(
    mode: str, selected_nodes: list[str], actions: dict[str, MagicMock]
) -> None:
    engine = make_engine(mode, '0', selected_nodes)
    assert engine._handle_formation() == ConditionFlag.SL
    actions['click_formation'].assert_not_called()


@pytest.mark.parametrize('mode', [CombatMode.NORMAL, CombatMode.EVENT])
def test_unknown_map_node_returns_to_port_instead_of_proceeding(
    mode: str, actions: dict[str, MagicMock]
) -> None:
    engine = make_engine(mode, '0', ['0', 'B', 'D', 'F'])
    assert engine._handle_proceed() == ConditionFlag.FIGHT_END
    actions['click_proceed'].assert_called_once_with(engine._device, go_forward=False)


@pytest.mark.parametrize('mode', [CombatMode.NORMAL, CombatMode.EVENT])
@pytest.mark.parametrize('node', ['B', 'F'])
def test_confirmed_enabled_node_still_enters_combat(
    mode: str, node: str, actions: dict[str, MagicMock]
) -> None:
    engine = make_engine(mode, node, ['0', 'B', 'D', 'F'])
    assert engine._handle_spot_enemy() == ConditionFlag.FIGHT_CONTINUE
    actions['click_enter_fight'].assert_called_once_with(engine._device)
    actions['click_retreat'].assert_not_called()
    assert engine._handle_formation() == ConditionFlag.FIGHT_CONTINUE
    actions['click_formation'].assert_called_once_with(engine._device, Formation.wedge)
    assert engine._handle_proceed() == ConditionFlag.FIGHT_CONTINUE
    actions['click_proceed'].assert_called_once_with(engine._device, go_forward=True)


@pytest.mark.parametrize('mode', [CombatMode.NORMAL, CombatMode.EVENT])
def test_confirmed_disabled_a_still_retreats(mode: str, actions: dict[str, MagicMock]) -> None:
    engine = make_engine(mode, 'A', ['0', 'B', 'D', 'F'])
    assert engine._handle_spot_enemy() == ConditionFlag.FIGHT_END
    actions['click_retreat'].assert_called_once_with(engine._device)
    actions['click_enter_fight'].assert_not_called()
    assert engine._handle_formation() == ConditionFlag.SL
    actions['click_formation'].assert_not_called()


@pytest.mark.parametrize('mode', [CombatMode.EXERCISE, CombatMode.BATTLE, CombatMode.DECISIVE])
def test_single_battle_modes_preserve_zero_node_behavior(
    mode: str, actions: dict[str, MagicMock]
) -> None:
    engine = make_engine(mode, '0', [])
    assert engine._handle_spot_enemy() == ConditionFlag.FIGHT_CONTINUE
    actions['click_enter_fight'].assert_called_once_with(engine._device)
    actions['click_retreat'].assert_not_called()
    assert engine._handle_formation() == ConditionFlag.FIGHT_CONTINUE
    actions['click_formation'].assert_called_once_with(engine._device, Formation.wedge)
    assert engine._handle_proceed() == ConditionFlag.FIGHT_CONTINUE
    actions['click_proceed'].assert_called_once_with(engine._device, go_forward=True)
