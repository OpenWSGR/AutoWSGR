"""基于整次出征历史推断位置，并分别输出各路证据和历史修订。

稀疏状态图保留全部合法假设，前向权重、Viterbi 路径和后向平滑各自回答
不同问题。权重来自待校准的观测模型，不代表已经测得的正确率。
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import asdict, dataclass, field, replace
from typing import TYPE_CHECKING, Any

import numpy as np

from autowsgr.combat.node_fusion.geometry import combine_point_terms, reachable_paths
from autowsgr.combat.node_fusion.map import SHIP_TYPES


if TYPE_CHECKING:
    from autowsgr.combat.node_fusion.enemy import EnemyObservation
    from autowsgr.combat.node_fusion.map import EnemyVariant, TrackingMap


MODEL_VERSION = 'history-fusion-3'
_NAV = 'NAVIGATING'
_SPOT = 'SPOT'
_DETOUR = 'DETOUR_PENDING'
_DEPART = 'DEPART_PENDING'
_COMBAT = 'COMBAT'
_POST = 'POST_COMBAT'
_RETURN = 'RETURN_PENDING'
_END = 'END'
_SHIP_CLASSES = len(SHIP_TYPES) + 1  # 实际加载的 native 舰类加上潜在空槽。
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


@dataclass(frozen=True, slots=True)
class FusionProfile:
    """观测误差的保守初值；独立定位核对及人工样本可用于校准，不评价地图准确度。"""

    ship_accuracy: float = 0.9
    formation_accuracy: float = 0.9
    frame_outlier: float = 0.1
    detour_accuracy: float = 0.9
    absent_detour_accuracy: float = 0.65
    distance_scale: float = 20.0  # 以 960 x 540 分辨率下的像素为单位。
    ray_scale: float = 12.0
    ray_decay_seconds: float = 0.5
    motion_interval: float = 0.08
    motion_min_pixels: float = 2.0
    ambiguity_threshold: float = 0.8
    # 客户端 0.0.638.2 的普通航行使用一秒动画，只使用其下限。
    # 迟到帧不能证明已经成功离开原点。
    min_travel_seconds: float | None = 1.0
    travel_time_margin: float = 0.05

    def __post_init__(self) -> None:
        probabilities = (
            'ship_accuracy',
            'formation_accuracy',
            'frame_outlier',
            'detour_accuracy',
            'absent_detour_accuracy',
            'ambiguity_threshold',
        )
        for name, value in asdict(self).items():
            if name == 'min_travel_seconds' and value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f'Invalid fusion parameter {name}: {value!r}')
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f'Fusion parameter {name} must be finite and positive')
            if name in probabilities and value >= 1:
                raise ValueError(f'Fusion probability {name} must be less than one')


@dataclass(frozen=True, slots=True)
class FusionObservation:
    """按采集时刻保存的不可变证据；decision_node 仅记录当时使用的点。"""

    kind: str
    timestamp: float
    frame_id: int | str | None = None
    phase: str | None = None
    action: str | None = None
    position: tuple[float, float] | None = None
    enemies: EnemyObservation | None = None
    decision_node: str | None = None
    clicked: bool | None = None
    page_left: bool | None = None
    detector_status: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class NodeEstimate:
    """当前模型权重、各路证据与历史修订，不改写已执行操作。"""

    event_id: int
    node_weights: dict[str, float]
    target_weights: dict[str, float]
    state_weights: tuple[dict[str, Any], ...]
    best_route: tuple[str, ...]
    history: tuple[dict[str, Any], ...]
    revisions: tuple[dict[str, Any], ...]
    contributions: dict[str, float]
    ambiguous: bool
    anomaly: str | None = None
    ignored: str | None = None
    model_version: str = MODEL_VERSION
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def current_node(self) -> str | None:
        """只返回已到达且无歧义的当前点，航段及预测目的点不能用于决策。"""
        if self.anomaly or self.ambiguous or not self.node_weights:
            return None
        node = max(self.node_weights, key=self.node_weights.get)
        if node == '0' or '->' in node:
            return None
        states = [state for state in self.state_weights if state['location'] == node]
        confirmed_stages = {_SPOT, _DETOUR, _COMBAT, _POST}
        if not states or any(state['stage'] not in confirmed_stages for state in states):
            return None
        return node

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


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


@dataclass(frozen=True, slots=True)
class _Edge:
    source: int
    target: int
    weight: float
    label: str
    path: tuple[str, ...]
    geometry: float
    enemy: float


@dataclass(slots=True)
class _Layer:
    event_id: int
    states: tuple[_State, ...]
    forward: np.ndarray
    viterbi: np.ndarray
    edges: tuple[_Edge, ...]
    best_edges: tuple[int, ...]


def _pixels(position: tuple[float, float]) -> np.ndarray:
    return np.array((position[0] * 960, position[1] * 540), dtype=float)


def _logsum(values: np.ndarray) -> float:
    return float(np.logaddexp.reduce(values))


class FusionTracker:
    """在按观测时刻展开的稀疏状态图上进行精确前向及最优路径计算。"""

    def __init__(self, map_data: TrackingMap, profile: FusionProfile | None = None) -> None:
        self.map_data = map_data
        self.profile = profile or FusionProfile()
        self.observations: list[FusionObservation] = []
        self._geometric = not map_data.capabilities['encounter_history']
        self._routes = (
            {} if self._geometric else {name: map_data.paths_from(name) for name in map_data.nodes}
        )
        self._geometric_paths = (
            {name: reachable_paths(map_data, name) for name in {*map_data.nodes, '0'}}
            if self._geometric
            else {}
        )
        self._point_terms: dict[str, dict[str, Any]] = {}
        self._layers = [_Layer(-1, (_State('0', _NAV),), np.zeros(1), np.zeros(1), (), ())]
        self._seen_frames: set[tuple[str, int | str]] = set()
        self._seen_actions: set[tuple[float, str | None]] = set()
        self._frame_actions: dict[int | str, int] = {}
        self._action_generation = 0
        self._last_phase_key: tuple[Any, ...] | None = None
        self._all_variants = tuple(
            dict.fromkeys(
                variant
                for node in map_data.nodes.values()
                for variant in (node.enemy_formations or ())
            )
        )
        self._enemy_cache: dict[tuple[str, int, tuple[_EnemySignature, ...]], float] = {}
        self._background_cache: dict[tuple[_EnemySignature, ...], float] = {}
        self._last_motion: FusionObservation | None = None
        self._last_action_time = -math.inf
        self._last_observation_time = -math.inf
        self._smoothed_labels: dict[int, tuple[str, str]] = {}
        self._history: tuple[dict[str, Any], ...] = ()
        self._estimate = self._summarize(-1, smooth=False)

    @property
    def estimate(self) -> NodeEstimate:
        return self._estimate

    def observe(self, observation: FusionObservation) -> NodeEstimate:
        """记录证据、更新合法状态图，并重新估计历史节点。"""
        self._validate(observation)
        event_id = len(self.observations)
        self.observations.append(observation)
        ignored = self._ignore_reason(observation)
        if ignored is not None:
            return replace(
                self._estimate,
                event_id=event_id,
                ignored=ignored,
                revisions=(),
                diagnostics=self._inactive_diagnostics(event_id, ignored),
            )
        self._last_observation_time = observation.timestamp
        if observation.kind == 'action':
            self._action_generation += 1
            self._last_action_time = observation.timestamp
            if observation.action in ('proceed', 'detour'):
                self._last_motion = None
        layer = self._advance(observation, event_id)
        if layer is None:
            # 保留最后的合法分布，不添加跨地图跳跃来掩盖不一致。
            self._estimate = replace(
                self._estimate,
                event_id=event_id,
                ambiguous=True,
                revisions=(),
                ignored=None,
                anomaly='No legal transition explains this observation; metadata or event mismatch',
                diagnostics=self._inactive_diagnostics(event_id, '没有合法转移'),
            )
            return self._estimate
        self._layers.append(layer)
        self._estimate = self._summarize(event_id, smooth=observation.kind != 'motion')
        if observation.kind == 'motion':
            self._last_motion = observation
        return self._estimate

    @staticmethod
    def _validate(obs: FusionObservation) -> None:
        if obs.kind not in ('motion', 'phase', 'action'):
            raise ValueError(f'Unknown fusion observation kind: {obs.kind}')
        if not math.isfinite(obs.timestamp) or obs.timestamp < 0:
            raise ValueError('Observation time must be finite and nonnegative')
        if obs.position is not None and (
            len(obs.position) != 2
            or any(not math.isfinite(v) or not 0 <= v <= 1 for v in obs.position)
        ):
            raise ValueError('Position must contain two finite normalized coordinates')

    def _ignore_reason(  # noqa: PLR0911 -- 分别列出相互独立的证据拒绝原因。
        self, obs: FusionObservation
    ) -> str | None:
        if obs.kind != 'action' and obs.timestamp < self._last_action_time:
            return 'frame predates last action'
        if obs.timestamp < self._last_observation_time:
            return 'out-of-order acquisition time'
        if obs.kind == 'action':
            action_key = (obs.timestamp, obs.action)
            if action_key in self._seen_actions:
                return 'duplicate action event'
            self._seen_actions.add(action_key)
        if obs.frame_id is not None and obs.kind != 'action':
            generation = self._frame_actions.setdefault(obs.frame_id, self._action_generation)
            if generation != self._action_generation:
                return 'decoded frame predates action generation'
            key = (obs.kind, obs.frame_id)
            if key in self._seen_frames:
                return 'duplicate decoded frame'
            self._seen_frames.add(key)
        if obs.kind == 'motion':
            return self._ignore_motion(obs)
        if obs.kind == 'phase':
            return self._ignore_phase(obs)
        return None

    def _ignore_phase(self, obs: FusionObservation) -> str | None:
        enemy = obs.enemies
        signature = None if enemy is None else (enemy.ships, enemy.formation, enemy.detour)
        # 跨过已验证的航行下限会增加新的时间信息。
        # 其他重复索敌不能反复平分迂回先验，凭空增加已离开的权重。
        minimum = self.profile.min_travel_seconds
        bound = 0 if minimum is None else minimum - self.profile.travel_time_margin
        eligibility = frozenset(
            (state.node, state.pending_since, obs.timestamp - state.pending_since >= bound)
            for state in self._layers[-1].states
            if state.stage == _DETOUR and state.pending_since is not None
        )
        key = (
            self._action_generation,
            obs.phase,
            signature,
            eligibility,
            self._last_motion.timestamp if self._last_motion is not None else None,
        )
        if key == self._last_phase_key:
            return 'same phase evidence segment'
        self._last_phase_key = key
        return None

    def _ignore_motion(self, obs: FusionObservation) -> str | None:
        if obs.position is None:
            return 'missing fresh position'
        previous = self._last_motion
        if previous is not None:
            if obs.timestamp - previous.timestamp < self.profile.motion_interval:
                return 'same motion sampling window'
            assert previous.position is not None
            distance = np.linalg.norm(_pixels(obs.position) - _pixels(previous.position))
            if distance < self.profile.motion_min_pixels:
                return 'same spatial observation'
        return None

    def _advance(self, obs: FusionObservation, event_id: int) -> _Layer | None:
        previous = self._layers[-1]
        self._point_terms = {}
        if self._geometric and obs.kind == 'motion' and obs.position is not None:
            raw_terms = {
                name: self._geometry_terms(_State(name, _NAV), obs)
                for name in self.map_data.nodes
                if name != '0'
            }
            self._point_terms = combine_point_terms(raw_terms, self.profile.frame_outlier)
        targets: dict[_State, int] = {}
        edges: list[_Edge] = []
        for source, state in enumerate(previous.states):
            for target, probability, label, path in self._transitions(state, obs):
                updated, enemy = self._enemy_update(target, obs)
                geometry = self._geometry(updated, obs)
                target_id = targets.setdefault(updated, len(targets))
                edges.append(
                    _Edge(
                        source,
                        target_id,
                        math.log(probability) + enemy + geometry,
                        label,
                        path,
                        geometry,
                        enemy,
                    )
                )
        if not targets:
            return None
        forward = np.full(len(targets), -np.inf)
        viterbi = np.full(len(targets), -np.inf)
        best = [-1] * len(targets)
        for i, edge in enumerate(edges):
            candidate = previous.forward[edge.source] + edge.weight
            forward[edge.target] = np.logaddexp(forward[edge.target], candidate)
            candidate = previous.viterbi[edge.source] + edge.weight
            if candidate > viterbi[edge.target]:
                viterbi[edge.target], best[edge.target] = candidate, i
        forward -= _logsum(forward)
        viterbi -= np.max(viterbi)
        return _Layer(event_id, tuple(targets), forward, viterbi, tuple(edges), tuple(best))

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

    def _transitions(  # noqa: PLR0911 -- 分阶段列出转移，明确排除非法路径。
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

    def _enemy_update(self, state: _State, obs: FusionObservation) -> tuple[_State, float]:
        enemy = obs.enemies
        if enemy is None or state.stage not in (_SPOT, _DETOUR):
            return state, 0.0
        signature = _EnemySignature(
            enemy.ships if enemy.valid_slots and len(enemy.ships) == 6 else (None,) * 6,
            enemy.formation if enemy.formation in (1, 2, 3, 4, 5) else None,
            enemy.detour,
        )
        if not any(signature.ships) and signature.formation is None and signature.detour is None:
            return state, 0.0
        if signature in state.evidence:
            return state, 0.0
        updated = replace(state, evidence=(*state.evidence, signature))
        # 替换当前遭遇的聚合因子，避免对相关读数无限连乘；原始观测仍完整保留。
        return updated, self._enemy_factor(updated) - self._enemy_factor(state)

    def _enemy_factor(self, state: _State) -> float:
        if not state.evidence:
            return 0.0
        key = state.node, state.variant, state.evidence
        if key in self._enemy_cache:
            return self._enemy_cache[key]
        node = self.map_data.nodes[state.node]
        score = 0.0
        if state.variant >= 0 and node.enemy_formations:
            score = self._fleet_factor(node.enemy_formations[state.variant], state.evidence)
        detours = [obs.detour for obs in state.evidence if obs.detour is not None]
        if detours and node.detour is not None:
            values = []
            for observed in detours:
                accuracy = (
                    self.profile.detour_accuracy
                    if observed
                    else self.profile.absent_detour_accuracy
                )
                # 未知属性以等概率背景为中性，匹配证据不能反而惩罚资料齐全的点。
                likelihood = accuracy if observed == node.detour else 1 - accuracy
                values.append(math.log(likelihood / 0.5))
            score += sum(values) / len(values)
        self._enemy_cache[key] = score
        return score

    def _fleet_factor(self, fleet: EnemyVariant, evidence: tuple[_EnemySignature, ...]) -> float:
        """已知敌情变体使用联合似然；未知变体不调用此项。"""
        log_model = self._fleet_score(fleet, evidence)
        if evidence not in self._background_cache:
            # 异常帧可能整体像另一支舰队，不能把它当作各槽独立随机错误。
            # 整帧混合项限制这种一致错误带来的过大优势。
            scores = np.array([self._fleet_score(fleet, evidence) for fleet in self._all_variants])
            self._background_cache[evidence] = _logsum(scores) - math.log(len(scores))
        log_background = self._background_cache[evidence]
        bad = self.profile.frame_outlier
        score = float(np.logaddexp(math.log1p(-bad) + log_model, math.log(bad) + log_background))
        score -= log_background
        return score

    def _fleet_score(self, fleet: EnemyVariant, evidence: tuple[_EnemySignature, ...]) -> float:
        """逐项聚合实际存在的观察，缺失读数不稀释此前证据。"""
        return sum(self._fleet_components(fleet, evidence))

    def _fleet_components(
        self, fleet: EnemyVariant, evidence: tuple[_EnemySignature, ...]
    ) -> tuple[float, float]:
        """返回同一真实变体的舰类与阵型对数似然，分项日志不参与额外投票。"""
        ships_score = formation_score = 0.0
        for i in range(6):
            observations = [obs.ships[i] for obs in evidence if obs.ships[i] is not None]
            if observations:
                expected = fleet.ships[i] if i < len(fleet.ships) else None
                ships_score += self._categorical_score(
                    observations, expected, self.profile.ship_accuracy, _SHIP_CLASSES
                )
        formations = [obs.formation for obs in evidence if obs.formation is not None]
        if formations:
            formation_score = self._categorical_score(
                formations, fleet.formation, self.profile.formation_accuracy, 5
            )
        return ships_score, formation_score

    @staticmethod
    def _categorical_score(
        observed: list[Any], expected: Any, accuracy: float, classes: int
    ) -> float:
        return sum(
            math.log(accuracy if value == expected else (1 - accuracy) / (classes - 1))
            for value in observed
        ) / len(observed)

    def _geometry(self, state: _State, obs: FusionObservation) -> float:
        """同一船位的距离和方向只合成为一个观测因子。"""
        if self._geometric and obs.kind == 'motion':
            row = self._point_terms.get(state.node)
            return math.log(row['point_likelihood']) if row else 0.0
        terms = self._geometry_terms(state, obs)
        return terms['log_likelihood'] if terms['available'] else 0.0

    def _geometry_terms(self, state: _State, obs: FusionObservation) -> dict[str, Any]:
        """逐航段计算实际使用的几何量，供模型和调试共用。"""
        if obs.kind != 'motion' or obs.position is None:
            return {'available': False, 'reason': '本次不是带有效船位的运动观测'}
        position = _pixels(obs.position)
        origin = _pixels(self.map_data.nodes[state.node].position)
        destination = origin
        if state.stage == _NAV and state.route:
            origin = _pixels(self.map_data.nodes[state.route[state.edge]].position)
            destination = _pixels(self.map_data.nodes[state.route[state.edge + 1]].position)
        segment = destination - origin
        length_squared = float(segment @ segment)
        progress = (
            float(np.clip((position - origin) @ segment / length_squared, 0, 1))
            if length_squared
            else 0.0
        )
        distance = float(np.linalg.norm(position - origin - progress * segment))
        distance_likelihood = 1 / (1 + (distance / self.profile.distance_scale) ** 2)
        ray_weight = ray_likelihood = 0.0
        ray_distance = frame_gap = None
        ray_reason = '缺少上一有效船位'
        previous = self._last_motion
        if previous is not None and previous.position is not None:
            frame_gap = obs.timestamp - previous.timestamp
            direction = position - _pixels(previous.position)
            magnitude = float(np.linalg.norm(direction))
            if magnitude > 0:
                ray_reason = None
                delta = destination - position
                ray_distance = (
                    float(np.linalg.norm(delta))
                    if float(delta @ direction) <= 0
                    else abs(float(delta[0] * direction[1] - delta[1] * direction[0])) / magnitude
                )
                ray_likelihood = 1 / (1 + (ray_distance / self.profile.ray_scale) ** 2)
                gap = max(0.0, obs.timestamp - previous.timestamp - self.profile.motion_interval)
                ray_weight = 0.5 * math.exp(-gap / self.profile.ray_decay_seconds)
            else:
                ray_reason = '有效船位之间没有位移'
        combined = (1 - ray_weight) * distance_likelihood + ray_weight * ray_likelihood
        return {
            'available': True,
            'distance_px': distance,
            'distance_likelihood': distance_likelihood,
            'ray_distance_px': ray_distance,
            'ray_likelihood': ray_likelihood,
            'ray_unavailable_reason': ray_reason,
            'frame_gap_seconds': frame_gap,
            'ray_mixture_weight': ray_weight,
            'log_likelihood': math.log(
                self.profile.frame_outlier + (1 - self.profile.frame_outlier) * combined
            ),
        }

    @staticmethod
    def _normalized_logs(scores: dict[str, float]) -> dict[str, float]:
        """仅为日志展示归一化分数；不把权重解释为实测正确率。"""
        if not scores:
            return {}
        total = _logsum(np.array(list(scores.values())))
        return {name: math.exp(value - total) for name, value in scores.items()}

    def _distance_channels(self, obs: FusionObservation) -> dict[str, Any]:
        """全图距离和射线的独立观察结果，仅用于调试对照。"""
        if obs.kind != 'motion' or obs.position is None:
            missing = {'available': False, 'reason': '本次没有新的船位证据', 'weights': {}}
            return {'distance': dict(missing), 'ray': dict(missing)}
        terms = {
            name: self._geometry_terms(_State(name, _SPOT), obs)
            for name in self.map_data.nodes
            if name != '0'
        }
        distance_scores = {
            name: math.log(row['distance_likelihood']) for name, row in terms.items()
        }
        ray_scores = {
            name: math.log(row['ray_likelihood'])
            for name, row in terms.items()
            if row['ray_unavailable_reason'] is None
        }
        first = next(iter(terms.values()), {})
        return {
            'distance': {
                'available': bool(terms),
                'scope': '全图节点的距离对照；实际采用的混合项见 geometry',
                'raw_distance_px': {name: row['distance_px'] for name, row in terms.items()},
                'likelihoods': {name: row['distance_likelihood'] for name, row in terms.items()},
                'weights': self._normalized_logs(distance_scores),
            },
            'ray': {
                'available': bool(ray_scores),
                'scope': '全图节点，仅调试对照；不与距离进行独立投票',
                'reason': first.get('ray_unavailable_reason', '地图没有可比较节点'),
                'frame_gap_seconds': first.get('frame_gap_seconds'),
                'mixture_weight': first.get('ray_mixture_weight', 0.0),
                'raw_distance_px': {name: row['ray_distance_px'] for name, row in terms.items()},
                'likelihoods': {name: row['ray_likelihood'] for name, row in terms.items()},
                'weights': self._normalized_logs(ray_scores),
            },
        }

    def _enemy_diagnostics(self, obs: FusionObservation) -> dict[str, Any]:
        """按同一真实变体展示敌情支持度汇总；逐变体明细由重放复得。"""
        enemy = obs.enemies
        if enemy is None:
            return {'available': False, 'reason': '本次没有新的索敌证据', 'weights': {}}
        signature = _EnemySignature(
            enemy.ships if enemy.valid_slots and len(enemy.ships) == 6 else (None,) * 6,
            enemy.formation if enemy.formation in (1, 2, 3, 4, 5) else None,
            enemy.detour,
        )
        if not any(signature.ships) and signature.formation is None and signature.detour is None:
            return {'available': False, 'reason': '六槽、阵型及迂回信息均缺失', 'weights': {}}
        robust_scores: dict[str, float] = {}
        supported_nodes = []
        for name, node in self.map_data.nodes.items():
            if name == '0' or node.silent:
                continue
            if (node.enemy_formations and (any(signature.ships) or signature.formation)) or (
                node.detour is not None and signature.detour is not None
            ):
                supported_nodes.append(name)
            if not node.enemy_formations:
                robust_scores[name] = self._enemy_factor(
                    _State(name, _SPOT, -1, evidence=(signature,))
                )
                continue
            robust = [
                self._enemy_factor(_State(name, _SPOT, index, evidence=(signature,)))
                for index in range(len(node.enemy_formations))
            ]
            robust_scores[name] = _logsum(np.array(robust)) - math.log(len(robust))
        ranked = sorted(robust_scores.items(), key=lambda item: item[1], reverse=True)
        return {
            'available': bool(supported_nodes),
            'reason': None if supported_nodes else '地图缺少与本次观察对应的敌情或迂回资料',
            'supported_nodes': supported_nodes,
            'scope': '本次索敌独立支持度；实际模型共享同一次遭遇的变体和聚合因子',
            'ships': signature.ships,
            'formation': signature.formation,
            'detour': signature.detour,
            'robust_top': (
                {
                    'node': ranked[0][0],
                    'log_factor': ranked[0][1],
                    'lead_nats': ranked[0][1] - ranked[1][1] if len(ranked) > 1 else ranked[0][1],
                }
                if ranked
                else None
            ),
            'weights': self._normalized_logs(robust_scores),
        }

    def _diagnostics(self, event_id: int) -> dict[str, Any]:
        """展示实际历史先验、各路观测和逐段几何，所有分项均不反向修改推断。"""
        if event_id < 0:
            return {'observation_accepted': False, 'reason': '尚无观测'}
        obs = self.observations[event_id]
        layer = self._layers[-1]
        previous = self._layers[-2]
        prior: dict[str, float] = {}
        for edge in layer.edges:
            location = self._location(layer.states[edge.target])
            value = previous.forward[edge.source] + edge.weight - edge.geometry - edge.enemy
            prior[location] = float(np.logaddexp(prior.get(location, -math.inf), value))
        geometry = {
            self._location(state): self._geometry_terms(state, obs) for state in layer.states
        }
        geometry = {name: row for name, row in geometry.items() if row['available']}
        if self._geometric:
            geometry = {
                name: {**row, 'log_likelihood': math.log(row['point_likelihood'])}
                for name, row in self._point_terms.items()
                if name in geometry
            }
        channels = self._distance_channels(obs)
        if self._geometric:
            channels['distance']['scope'] = '资料不足时实际使用的全图节点距离分布'
            channels['ray']['scope'] = '按方向区分度及帧间隔衰减后，与距离混合'
            if self._point_terms:
                first = next(iter(self._point_terms.values()))
                channels['ray']['mixture_weight'] = first['ray_mixture_weight']
                channels['ray']['discrimination'] = first['ray_discrimination']
        return {
            'observation_accepted': True,
            'source_event_id': event_id,
            'mode': 'geometry' if self._geometric else 'history',
            'capabilities': self.map_data.capabilities,
            'degradation_reasons': self.map_data.degradation_reasons,
            'complete_encounter_route': not self._geometric,
            'history_prior': {
                'scope': '全部历史经本次合法转移得到的预测分布，不含本次新视觉证据',
                'weights': self._normalized_logs(prior),
            },
            **channels,
            'geometry': {
                'available': bool(geometry),
                'scope': (
                    '实际使用的节点几何混合项，中间经过顺序未由节点类型确认'
                    if self._geometric
                    else '模型实际使用的逐航段距离与射线混合项'
                ),
                'terms': geometry,
                'weights': self._normalized_logs(
                    {name: row['log_likelihood'] for name, row in geometry.items()}
                ),
            },
            'enemy': self._enemy_diagnostics(obs),
        }

    def _inactive_diagnostics(self, event_id: int, reason: str) -> dict[str, Any]:
        """被拒绝观测不重复展示旧视觉分数，明确保留候选所依据的历史时刻。"""
        missing = {'available': False, 'reason': reason, 'weights': {}}
        return {
            'observation_accepted': False,
            'mode': 'geometry' if self._geometric else 'history',
            'capabilities': self.map_data.capabilities,
            'degradation_reasons': self.map_data.degradation_reasons,
            'source_event_id': self._layers[-1].event_id,
            'observation_event_id': event_id,
            'history_prior': {
                'scope': '保留上一次有效分布',
                'weights': self._estimate.node_weights,
            },
            'distance': dict(missing),
            'ray': dict(missing),
            'geometry': dict(missing),
            'enemy': dict(missing),
            'fusion': {
                'weights': self._estimate.node_weights,
                'target_weights': self._estimate.target_weights,
                'best_route': self._estimate.best_route,
                'revisions': (),
            },
        }

    @staticmethod
    def _location(state: _State) -> str:
        if state.stage == _NAV and state.route:
            return f'{state.route[state.edge]}->{state.route[state.edge + 1]}'
        return state.node

    def _best_path(self) -> tuple[tuple[str, ...], list[tuple[_State, str]]]:
        index = int(np.argmax(self._layers[-1].viterbi))
        records = []
        route_parts: list[tuple[str, ...]] = []
        for layer in reversed(self._layers[1:]):
            edge = layer.edges[layer.best_edges[index]]
            records.append((layer.states[index], edge.label))
            if edge.path:
                route_parts.append(edge.path)
            index = edge.source
        route = ['0'] if '0' in self.map_data.nodes else []
        for part in reversed(route_parts):
            route.extend(part[1:] if route and route[-1] == part[0] else part)
        records.reverse()
        return tuple(route), records

    def _smooth(self, records: list[tuple[_State, str]]) -> tuple[dict[str, Any], ...]:
        beta = np.zeros(len(self._layers[-1].states))
        summaries: list[dict[str, Any]] = []
        for layer_index in range(len(self._layers) - 1, 0, -1):
            layer = self._layers[layer_index]
            weights = layer.forward + beta
            weights = np.exp(weights - _logsum(weights))
            node_weights: dict[str, float] = defaultdict(float)
            for state, weight in zip(layer.states, weights, strict=True):
                node_weights[self._location(state)] += float(weight)
            state, label = records[layer_index - 1]
            summaries.append(
                {
                    'event_id': layer.event_id,
                    'node_weights': dict(node_weights),
                    'best_node': max(node_weights, key=node_weights.get),
                    'viterbi_node': self._location(state),
                    'transition': label,
                    'decision_node': self.observations[layer.event_id].decision_node,
                }
            )
            previous = self._layers[layer_index - 1]
            earlier = np.full(len(previous.states), -np.inf)
            for edge in layer.edges:
                earlier[edge.source] = np.logaddexp(
                    earlier[edge.source], edge.weight + beta[edge.target]
                )
            finite = earlier[np.isfinite(earlier)]
            if finite.size:
                earlier -= np.max(finite)
            beta = earlier
        summaries.reverse()
        return tuple(summaries)

    def _summarize(self, event_id: int, *, smooth: bool) -> NodeEstimate:
        layer = self._layers[-1]
        nodes: dict[str, float] = defaultdict(float)
        targets: dict[str, float] = defaultdict(float)
        states = []
        for state, weight in zip(layer.states, np.exp(layer.forward), strict=True):
            value = float(weight)
            location = self._location(state)
            nodes[location] += value
            if state.stage == _NAV:
                if state.route:
                    targets[state.route[-1]] += value
                elif self._geometric and state.node != '0':
                    targets[state.node] += value
            states.append(
                {
                    'location': location,
                    'stage': state.stage,
                    'variant': state.variant,
                    'weight': value,
                }
            )
        route, records = self._best_path()
        revisions = []
        if smooth:
            self._history = self._smooth(records)
            for row in self._history:
                key = row['event_id']
                current = (row['viterbi_node'], row['transition'])
                old = self._smoothed_labels.get(key)
                if old is not None and old != current:
                    revisions.append({'event_id': key, 'before': old, 'after': current})
                self._smoothed_labels[key] = current
        contributions = {'geometry': 0.0, 'enemy': 0.0}
        if layer.edges:
            best_index = int(np.argmax(layer.viterbi))
            best = layer.edges[layer.best_edges[best_index]]
            contributions = {'geometry': best.geometry, 'enemy': best.enemy}
        diagnostics = self._diagnostics(event_id)
        diagnostics['fusion'] = {
            'weights': dict(nodes),
            'target_weights': dict(targets),
            'best_route': route,
            'revisions': tuple(revisions),
        }
        return NodeEstimate(
            event_id,
            dict(nodes),
            dict(targets),
            tuple(states),
            route,
            self._history,
            tuple(revisions),
            contributions,
            max(nodes.values(), default=0.0) < self.profile.ambiguity_threshold,
            diagnostics=diagnostics,
        )
