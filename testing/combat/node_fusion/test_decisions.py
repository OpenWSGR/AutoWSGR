"""未知地图节点的作战保护回归测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from autowsgr.combat import handlers as handlers_mod
from autowsgr.combat.engine import CombatEngine
from autowsgr.combat.plan import CombatMode, CombatPlan, NodeDecision
from autowsgr.types import ConditionFlag, Formation


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
