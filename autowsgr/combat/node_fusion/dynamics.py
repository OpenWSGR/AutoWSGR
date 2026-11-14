"""场景负责合法转移和初始分布，共享推断内核不猜测页面的业务含义。"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import TYPE_CHECKING

from autowsgr.combat.node_fusion.geometry import reachable_paths
from autowsgr.combat.node_fusion.state import (
    _COMBAT,
    _DEPART,
    _DETOUR,
    _END,
    _MAP_READY,
    _NAV,
    _PHASE_STAGE,
    _POST,
    _RETURN,
    _SPOT,
    _TERMINAL,
    _State,
)


if TYPE_CHECKING:
    from autowsgr.combat.node_fusion.map import TrackingMap
    from autowsgr.combat.node_fusion.model import FusionObservation, FusionProfile


class MapDynamics:
    """保留常规和活动地图的路由、航行动画、迂回与降级定位语义。"""

    name = 'map'
    decision_stages = frozenset({_SPOT, _DETOUR, _COMBAT, _POST})

    def __init__(self, map_data: TrackingMap, profile: FusionProfile) -> None:
        self.map_data = map_data
        self.profile = profile
        self._geometric = not map_data.capabilities['encounter_history']
        self._routes = (
            {} if self._geometric else {name: map_data.paths_from(name) for name in map_data.nodes}
        )
        self._geometric_paths = (
            {name: reachable_paths(map_data, name) for name in {*map_data.nodes, '0'}}
            if self._geometric
            else {}
        )

    def initial_states(self, initial: dict[str, float] | None) -> list[tuple[_State, float]]:
        if initial is not None:
            raise ValueError('Explicit initial nodes require decisive dynamics')
        return [(_State('0', _NAV), 1.0)]

    def _variants(self, node: str) -> tuple[int, ...]:
        """缺少敌情模板时保留一个未知变体，其他证据仍然可用。"""
        variants = self.map_data.nodes[node].enemy_formations
        return tuple(range(len(variants))) if variants else (-1,)

    def _fresh_enemy_available(self, obs: FusionObservation) -> bool:
        enemy = obs.enemies
        if enemy is None:
            return False
        capabilities = self.map_data.capabilities
        return bool(
            (capabilities['enemy'] and (any(enemy.ships) or enemy.formation is not None))
            or (capabilities['detour'] and enemy.detour is not None)
        )

    def _geometric_arrivals(
        self, state: _State, obs: FusionObservation, stage: str
    ) -> list[tuple[_State, float, str, tuple[str, ...]]]:
        """页面只确认本段证据支持的点，不根据遭遇次数推进一条边。"""
        if not self._can_arrive(state, obs.timestamp):
            return []
        if state.stage == _NAV and state.leg_observed:
            # 页面证据在本段位置分布上评分，不因出现按钮再展开一次可达节点。
            source = state.leg_origin or state.node
            path = self._geometric_paths[source].get(state.node, ())
            candidates = {state.node: path}
        elif self._fresh_enemy_available(obs):
            candidates = self._geometric_paths[state.node]
        else:
            return []
        eligible = {
            name: path for name, path in candidates.items() if not self.map_data.nodes[name].silent
        }
        result = []
        for name, path in eligible.items():
            # 没有起点时从首次确认的节点开始记录，不补造入口或边。
            recorded_path = path or ((name,) if self.map_data.capabilities['topology'] else ())
            variants = self._variants(name)
            for variant in variants:
                label = 'new_encounter' if state.detour_succeeds else 'geometric_arrival'
                result.append(
                    (
                        _State(name, stage, variant),
                        1 / len(eligible) / len(variants),
                        label,
                        recorded_path,
                    )
                )
        return result

    def _geometric_transitions(  # noqa: PLR0911 -- 按页面和动作区分证据是否足够。
        self, state: _State, obs: FusionObservation
    ) -> list[tuple[_State, float, str, tuple[str, ...]]]:
        """资料不足时只使用几何及已知可达性，不假定未知点的战斗属性。"""
        same = [(state, 1.0, 'same_encounter', ())]
        if obs.kind == 'motion':
            if state.stage not in (_NAV, _DEPART, _DETOUR) or (
                state.stage == _DETOUR and state.detour_succeeds is False
            ):
                return same
            source = state.leg_origin if state.leg_observed else state.node
            paths = self._geometric_paths[source]
            return [
                (
                    replace(
                        state,
                        node=name,
                        stage=_NAV,
                        variant=-1,
                        route=(),
                        evidence=(),
                        leg_observed=True,
                        leg_origin=source,
                    ),
                    1 / len(paths),
                    'geometric_move',
                    (),
                )
                for name in paths
            ]
        if obs.phase in ('MAP_PAGE', 'EVENT_MAP_PAGE'):
            # 返回地图页只说明出征结束，不能凭此推断经过了哪些未知点。
            return [(replace(state, stage=_END), 1.0, 'same_encounter', ())]
        stage = _PHASE_STAGE.get(obs.phase or '')
        if stage is None:
            return same
        if state.stage in (_NAV, _DEPART):
            if obs.phase == 'PROCEED' and state.stage == _DEPART and state.node != '0':
                return [(replace(state, stage=_POST), 1.0, 'same_encounter', ())]
            return self._geometric_arrivals(state, obs, stage)
        if state.stage == _DETOUR:
            if state.detour_succeeds:
                arrivals = self._geometric_arrivals(state, obs, stage)
                return arrivals or (same if stage == _SPOT else [])
            return [
                (
                    replace(state, stage=_DETOUR if stage == _SPOT else stage),
                    1.0,
                    'same_encounter',
                    (),
                )
            ]
        if state.stage == _END:
            return []
        return [(replace(state, stage=stage), 1.0, 'same_encounter', ())]

    def _navigation(self, state: _State) -> list[tuple[_State, float, str, tuple[str, ...]]]:
        if state.route:
            return [(state, 1.0, 'same_encounter', ())]
        return [
            (replace(state, stage=_NAV, route=route.nodes), route.probability, 'departure', ())
            for route in self._routes[state.node]
            if len(route.nodes) >= 2
        ]

    def _can_arrive(self, state: _State, timestamp: float) -> bool:
        minimum = self.profile.min_travel_seconds
        return not (
            minimum is not None
            and state.pending_since is not None
            and timestamp - state.pending_since < minimum - self.profile.travel_time_margin
        )

    def _arrivals(
        self,
        state: _State,
        stage: str,
        timestamp: float,
    ) -> list[tuple[_State, float, str, tuple[str, ...]]]:
        if not self._can_arrive(state, timestamp):
            return []
        options = []
        for nav, prior, _, _ in self._navigation(state):
            destination = self.map_data.nodes[nav.route[-1]]
            if destination.silent:
                continue
            options.extend(
                (
                    _State(destination.name, stage, variant),
                    prior / max(1, len(destination.enemy_formations or ())),
                    'new_encounter',
                    nav.route,
                )
                for variant in self._variants(destination.name)
            )
        return options

    def _action_transitions(
        self, state: _State, obs: FusionObservation
    ) -> list[tuple[_State, float, str, tuple[str, ...]]]:
        same = [(state, 1.0, 'same_encounter', ())]
        if obs.clicked is False:
            return same
        if obs.action == 'detour':
            if state.stage == _NAV or (state.stage == _DETOUR and state.detour_succeeds):
                return same
            # 每次真实操作只分配一次潜在结果，同页 OCR 波动不能重分先验。
            return [
                (
                    replace(
                        state,
                        stage=_DETOUR,
                        route=(),
                        edge=0,
                        pending_since=obs.timestamp,
                        detour_succeeds=outcome,
                        leg_observed=False,
                        leg_origin=None,
                    ),
                    0.5,
                    'action_intent',
                    (),
                )
                for outcome in (False, True)
            ]
        stages = {'proceed': _DEPART, 'retreat': _RETURN, 'end': _RETURN}
        if obs.action in stages:
            since = state.pending_since if state.stage in (_DETOUR, _DEPART, _NAV) else None
            return [
                (
                    replace(
                        state,
                        stage=stages[obs.action],
                        route=(),
                        edge=0,
                        pending_since=since if since is not None else obs.timestamp,
                        detour_succeeds=None,
                        leg_observed=False,
                        leg_origin=None,
                    ),
                    1.0,
                    'action_intent',
                    (),
                )
            ]
        # 点击开战或阵型按钮本身不能证明页面已切换。
        return same

    def transitions(  # noqa: PLR0911 -- 分阶段列出转移，明确排除非法路径。
        self,
        state: _State,
        obs: FusionObservation,
    ) -> list[tuple[_State, float, str, tuple[str, ...]]]:
        same = [(state, 1.0, 'same_encounter', ())]
        if obs.kind == 'action':
            return self._action_transitions(state, obs)
        if self._geometric:
            return self._geometric_transitions(state, obs)
        if obs.kind == 'motion':
            return self._motion_transitions(state)
        if obs.phase in ('MAP_PAGE', 'EVENT_MAP_PAGE'):
            return self._end_transitions(state, obs.timestamp)
        stage = _PHASE_STAGE.get(obs.phase or '')
        if stage is None:
            # 战况选择可能发生在航行前，不能把它当作到达下一点的依据。
            return same
        if state.stage in (_NAV, _DEPART):
            options = self._arrivals(state, stage, obs.timestamp)
            if obs.phase == 'PROCEED' and state.node != '0':
                return [(replace(state, stage=_POST, route=(), edge=0), 1.0, 'same_encounter', ())]
            return options
        if state.stage == _DETOUR:
            arrivals = self._arrivals(state, stage, obs.timestamp)
            if state.detour_succeeds:
                if arrivals:
                    return arrivals
                # 成功离开前仍可能看见索敌页；过早出现阵型或战斗页则属于原点。
                return same if stage == _SPOT else []
            same_stage = _DETOUR if stage == _SPOT else stage
            return [(replace(state, stage=same_stage), 1.0, 'same_encounter', ())]
        if state.stage == _END:
            return []
        return [(replace(state, stage=stage), 1.0, 'same_encounter', ())]

    def _motion_transitions(
        self, state: _State
    ) -> list[tuple[_State, float, str, tuple[str, ...]]]:
        if state.stage not in (_NAV, _DEPART, _DETOUR):
            return [(state, 1.0, 'same_encounter', ())]
        if state.stage == _DETOUR and state.detour_succeeds is False:
            return [(state, 1.0, 'same_encounter', ())]
        options = []
        navigation = self._navigation(state)
        for nav, prior, label, path in navigation:
            remaining = len(nav.route) - 2 - nav.edge
            if remaining <= 0:
                options.append((nav, prior, label, path))
            else:
                options.append((nav, prior * 0.9, label, path))
                options.extend(
                    (replace(nav, edge=edge), prior * 0.1 / remaining, 'pass_noncombat', ())
                    for edge in range(nav.edge + 1, len(nav.route) - 1)
                )
        if state.stage in (_DEPART, _DETOUR):
            # 点击只是操作意图，保留尚未成功离开的可能。
            options = [(s, p * 0.9, label, path) for s, p, label, path in options]
            options.append((state, 0.1 if navigation else 1.0, 'same_encounter', ()))
        return options

    def _end_transitions(
        self, state: _State, timestamp: float
    ) -> list[tuple[_State, float, str, tuple[str, ...]]]:
        if state.stage == _RETURN or not self.map_data.nodes[state.node].next_nodes:
            return [(replace(state, stage=_END), 1.0, 'same_encounter', ())]
        if not self._can_arrive(state, timestamp) or (
            state.stage == _DETOUR and state.detour_succeeds is False
        ):
            return []
        options = []
        if state.stage in (_NAV, _DEPART, _DETOUR):
            for nav, prior, _, _ in self._navigation(state):
                target = self.map_data.nodes[nav.route[-1]]
                if target.silent and not target.next_nodes:
                    options.append((_State(target.name, _END), prior, 'pass_noncombat', nav.route))
        return options


class DecisiveDynamics:
    """顺序小关：推进只接受一次已确认战斗，节点预测不代表真实通关。"""

    name = 'decisive'
    _geometric = False
    decision_stages = frozenset({_MAP_READY, _SPOT, _COMBAT, _POST})

    def __init__(self, map_data: TrackingMap, profile: FusionProfile) -> None:
        self.map_data = map_data
        self.profile = profile
        names = tuple(map_data.nodes)
        if '0' in names or not names:
            raise ValueError('Decisive maps require actual encounter nodes without a fake entry')
        terminals = [name for name, node in map_data.nodes.items() if node.next_nodes == ()]
        if len(terminals) != 1 or any(
            node.next_nodes is None or len(node.next_nodes) > 1 for node in map_data.nodes.values()
        ):
            raise ValueError('Decisive maps must have one terminal and one sequential route')
        self.terminal = terminals[0]
        # 从每个可能恢复点均须能够沿确定的后继到达同一终点。
        for name in names:
            seen: set[str] = set()
            current = name
            while current != self.terminal:
                if current in seen:
                    raise ValueError('Decisive maps cannot contain cycles')
                seen.add(current)
                current = map_data.nodes[current].next_nodes[0]

    def _variants(self, node: str) -> tuple[int, ...]:
        variants = self.map_data.nodes[node].enemy_formations
        return tuple(range(len(variants))) if variants else (-1,)

    def initial_states(self, initial: dict[str, float] | None) -> list[tuple[_State, float]]:
        weights = initial if initial is not None else dict.fromkeys(self.map_data.nodes, 1.0)
        if not weights or any(
            name not in self.map_data.nodes
            or isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
            for name, value in weights.items()
        ):
            raise ValueError('Invalid decisive initial node distribution')
        total = sum(weights.values())
        if total <= 0:
            raise ValueError('Initial node distribution requires positive mass')
        return [
            (_State(name, _MAP_READY, variant), weight / total / len(self._variants(name)))
            for name, weight in weights.items()
            if weight > 0
            for variant in self._variants(name)
        ]

    def transitions(  # noqa: PLR0911 -- 分开确认页面、战斗完成与不推进的战斗页。
        self, state: _State, obs: FusionObservation
    ) -> list[tuple[_State, float, str, tuple[str, ...]]]:
        same = [(state, 1.0, 'same_encounter', ())]
        if obs.kind == 'action':
            if obs.action != 'encounter_complete' or obs.clicked is False:
                return same
            if state.stage in (_END, _TERMINAL) or (
                state.encounter_id is not None and state.encounter_id != obs.encounter_id
            ):
                return []
            successors = self.map_data.nodes[state.node].next_nodes
            if not successors:
                return [(replace(state, stage=_TERMINAL), 1.0, 'encounter_complete', ())]
            target = successors[0]
            variants = self._variants(target)
            return [
                (
                    _State(target, _MAP_READY, variant),
                    1 / len(variants),
                    'encounter_complete',
                    (state.node, target),
                )
                for variant in variants
            ]
        if obs.phase == 'DECISIVE_STAGE_CLEAR':
            return (
                [(replace(state, stage=_END), 1.0, 'stage_clear', ())]
                if state.stage in (_TERMINAL, _END)
                else []
            )
        if state.stage in (_TERMINAL, _END):
            return [] if obs.phase == 'DECISIVE_MAP_READY' or obs.phase in _PHASE_STAGE else same
        if state.encounter_id is not None and obs.encounter_id not in (None, state.encounter_id):
            return []
        current = replace(state, encounter_id=obs.encounter_id or state.encounter_id)
        if obs.phase == 'DECISIVE_MAP_READY':
            if current.stage != _MAP_READY:
                # 尚未提交战斗完成时不能把后继地图解释为原点再次开战。
                return []
            return [(current, 1.0, 'same_encounter', ())]
        stage = _PHASE_STAGE.get(obs.phase or '')
        if stage is None:
            return [(current, 1.0, 'same_encounter', ())]
        first = current.stage == _MAP_READY
        return [
            (
                replace(current, stage=stage),
                1.0,
                'new_encounter' if first else 'same_encounter',
                (current.node,) if first else (),
            )
        ]

    def confirmed_clear(self) -> list[tuple[_State, float, str, tuple[str, ...]]]:
        """只有独立页面确认才可覆盖滞后的进度，日志明确标明这次纠正。"""
        return [(_State(self.terminal, _END), 1.0, 'stage_clear_correction', (self.terminal,))]
