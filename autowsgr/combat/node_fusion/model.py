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

from autowsgr.combat.node_fusion.dynamics import DecisiveDynamics, MapDynamics
from autowsgr.combat.node_fusion.factors import EnemyFactor, GeometryFactor, NodeLabelFactor
from autowsgr.combat.node_fusion.map import TrackingMap
from autowsgr.combat.node_fusion.state import (
    _COMBAT,
    _DETOUR,
    _MAP_READY,
    _NAV,
    _POST,
    _SPOT,
    _Edge,
    _Layer,
    _State,
)


if TYPE_CHECKING:
    from autowsgr.combat.node_fusion.enemy import EnemyObservation


MODEL_VERSION = 'history-fusion-4'


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
    node_label_accuracy: float = 0.9
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
            'node_label_accuracy',
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
    node_label: str | None = None
    encounter_id: str | None = None

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
        ready_stages = {_SPOT, _DETOUR, _COMBAT, _POST, _MAP_READY}
        if not states or any(
            not state.get('decision_ready', state['stage'] in ready_stages) for state in states
        ):
            return None
        return node

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _pixels(position: tuple[float, float]) -> np.ndarray:
    return np.array((position[0] * 960, position[1] * 540), dtype=float)


def _logsum(values: np.ndarray) -> float:
    return float(np.logaddexp.reduce(values))


class FusionTracker:
    """在按观测时刻展开的稀疏状态图上进行精确前向及最优路径计算。"""

    def __init__(
        self,
        map_data: TrackingMap,
        profile: FusionProfile | None = None,
        *,
        dynamics: str = 'map',
        initial: dict[str, float] | None = None,
    ) -> None:
        self.map_data = map_data
        self.profile = profile or FusionProfile()
        self.observations: list[FusionObservation] = []
        if dynamics not in ('map', 'decisive'):
            raise ValueError(f'Unknown fusion dynamics: {dynamics}')
        self.dynamics = dynamics
        self.initial = dict(initial) if initial is not None else None
        strategy = DecisiveDynamics if dynamics == 'decisive' else MapDynamics
        self._dynamics = strategy(map_data, self.profile)
        self._geometric = self._dynamics._geometric
        self.enemy_factor = EnemyFactor(map_data, self.profile)
        self.geometry_factor = GeometryFactor(map_data, self.profile, geometric=self._geometric)
        self.node_label_factor = NodeLabelFactor(map_data, self.profile)
        starts = self._dynamics.initial_states(self.initial)
        weights = np.log(np.array([weight for _, weight in starts]))
        self._layers = [
            _Layer(-1, tuple(state for state, _ in starts), weights, weights.copy(), (), ())
        ]
        self._completed_encounters: dict[str, int] = {}
        self._seen_frames: set[tuple[str, int | str]] = set()
        self._seen_actions: set[tuple[float, str | None]] = set()
        self._frame_actions: dict[int | str, int] = {}
        self._action_generation = 0
        self._last_phase_key: tuple[Any, ...] | None = None
        self._last_action_time = -math.inf
        self._last_observation_time = -math.inf
        self._smoothed_labels: dict[int, tuple[str, str]] = {}
        self._history: tuple[dict[str, Any], ...] = ()
        self._estimate = self._summarize(-1, smooth=False)

    @property
    def estimate(self) -> NodeEstimate:
        return self._estimate

    def completed_encounter(self, encounter_id: str) -> FusionObservation | None:
        """查询首次被接受的完成事件；原始历史中的拒绝尝试不属于完成事实。"""
        event_id = self._completed_encounters.get(encounter_id)
        return self.observations[event_id] if event_id is not None else None

    def clone_without_enemy(self) -> FusionTracker:
        """独立定位校验从原场景和初始条件重放，避免敌情自证。"""
        metadata = TrackingMap(
            {
                name: replace(node, enemy_formations=None)
                for name, node in self.map_data.nodes.items()
            },
            source=self.map_data.source,
        )
        return FusionTracker(metadata, self.profile, dynamics=self.dynamics, initial=self.initial)

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
                self.geometry_factor.last_motion = None
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
        if observation.action == 'encounter_complete' and observation.clicked is not False:
            assert observation.encounter_id is not None
            self._completed_encounters[observation.encounter_id] = event_id
        self._estimate = self._summarize(event_id, smooth=observation.kind != 'motion')
        if observation.kind == 'motion':
            self.geometry_factor.last_motion = observation
        return self._estimate

    @staticmethod
    def _validate(obs: FusionObservation) -> None:
        if obs.kind not in ('motion', 'phase', 'action'):
            raise ValueError(f'Unknown fusion observation kind: {obs.kind}')
        if not math.isfinite(obs.timestamp) or obs.timestamp < 0:
            raise ValueError('Observation time must be finite and nonnegative')
        if obs.node_label is not None and (
            not isinstance(obs.node_label, str) or not obs.node_label
        ):
            raise ValueError('Node label must be a nonempty string')
        if obs.encounter_id is not None and (
            not isinstance(obs.encounter_id, str) or not obs.encounter_id
        ):
            raise ValueError('Encounter identifier must be a nonempty string')
        if obs.action == 'encounter_complete' and not obs.encounter_id:
            raise ValueError('Completing an encounter requires a unique identifier')
        if obs.position is not None and (
            len(obs.position) != 2
            or any(not math.isfinite(v) or not 0 <= v <= 1 for v in obs.position)
        ):
            raise ValueError('Position must contain two finite normalized coordinates')

    def _ignore_reason(  # noqa: PLR0911 -- 分别列出相互独立的证据拒绝原因。
        self, obs: FusionObservation
    ) -> str | None:
        if obs.action == 'encounter_complete' and obs.encounter_id in self._completed_encounters:
            return 'duplicate encounter completion'
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
            obs.encounter_id,
            obs.node_label,
            signature,
            eligibility,
            self.geometry_factor.last_motion.timestamp
            if self.geometry_factor.last_motion is not None
            else None,
        )
        if key == self._last_phase_key:
            return 'same phase evidence segment'
        self._last_phase_key = key
        return None

    def _ignore_motion(self, obs: FusionObservation) -> str | None:
        if obs.position is None:
            return 'missing fresh position'
        previous = self.geometry_factor.last_motion
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
        self.geometry_factor.prepare(obs)
        targets: dict[_State, int] = {}
        edges: list[_Edge] = []
        transitions = [self._dynamics.transitions(state, obs) for state in previous.states]
        if (
            isinstance(self._dynamics, DecisiveDynamics)
            and obs.phase == 'DECISIVE_STAGE_CLEAR'
            and not any(transitions)
        ):
            transitions = [self._dynamics.confirmed_clear() for _ in previous.states]
        for source in range(len(previous.states)):
            for target, probability, label, path in transitions[source]:
                updated, enemy = self.enemy_factor.update(target, obs)
                updated, node_label = self.node_label_factor.update(updated, obs)
                geometry = self.geometry_factor.score(updated, obs)
                target_id = targets.setdefault(updated, len(targets))
                edges.append(
                    _Edge(
                        source,
                        target_id,
                        math.log(probability) + enemy + geometry + node_label,
                        label,
                        path,
                        geometry,
                        enemy,
                        node_label,
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

    @staticmethod
    def _normalized_logs(scores: dict[str, float]) -> dict[str, float]:
        """仅为日志展示归一化分数；不把权重解释为实测正确率。"""
        if not scores:
            return {}
        total = _logsum(np.array(list(scores.values())))
        return {name: math.exp(value - total) for name, value in scores.items()}

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
            value = (
                previous.forward[edge.source]
                + edge.weight
                - edge.geometry
                - edge.enemy
                - edge.node_label
            )
            prior[location] = float(np.logaddexp(prior.get(location, -math.inf), value))
        geometry = {
            self._location(state): self.geometry_factor.terms(state, obs) for state in layer.states
        }
        geometry = {name: row for name, row in geometry.items() if row['available']}
        if self._geometric:
            geometry = {
                name: {**row, 'log_likelihood': math.log(row['point_likelihood'])}
                for name, row in self.geometry_factor.point_terms.items()
                if name in geometry
            }
        channels = self.geometry_factor.channels(obs)
        if self._geometric:
            channels['distance']['scope'] = '资料不足时实际使用的全图节点距离分布'
            channels['ray']['scope'] = '按方向区分度及帧间隔衰减后，与距离混合'
            if self.geometry_factor.point_terms:
                first = next(iter(self.geometry_factor.point_terms.values()))
                channels['ray']['mixture_weight'] = first['ray_mixture_weight']
                channels['ray']['discrimination'] = first['ray_discrimination']
        return {
            'observation_accepted': True,
            'source_event_id': event_id,
            'mode': 'geometry' if self._geometric else 'history',
            'dynamics': self.dynamics,
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
            'enemy': self.enemy_factor.diagnostics(obs),
            'node_label': self.node_label_factor.diagnostics(obs),
            'page_correction': any(edge.label == 'stage_clear_correction' for edge in layer.edges),
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
            'node_label': dict(missing),
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
        route = (
            [self._layers[0].states[index].node]
            if self.dynamics == 'decisive'
            else ['0']
            if '0' in self.map_data.nodes
            else []
        )
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
                    'decision_ready': state.stage in self._dynamics.decision_stages,
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
            if self.dynamics == 'decisive' or best.node_label:
                contributions['node_label'] = best.node_label
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
