"""各路证据输出候选状态的对数因子，历史平滑只由 FusionTracker 执行。"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import TYPE_CHECKING, Any

import numpy as np

from autowsgr.combat.node_fusion.geometry import combine_point_terms
from autowsgr.combat.node_fusion.map import SHIP_TYPES
from autowsgr.combat.node_fusion.state import _DETOUR, _NAV, _SPOT, _EnemySignature, _State


if TYPE_CHECKING:
    from autowsgr.combat.node_fusion.map import EnemyVariant, TrackingMap
    from autowsgr.combat.node_fusion.model import FusionObservation, FusionProfile

_SHIP_CLASSES = len(SHIP_TYPES) + 1


def _pixels(position: tuple[float, float]) -> np.ndarray:
    return np.array((position[0] * 960, position[1] * 540), dtype=float)


def _logsum(values: np.ndarray) -> float:
    return float(np.logaddexp.reduce(values))


def _normalized_logs(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    total = _logsum(np.array(list(scores.values())))
    return {name: math.exp(value - total) for name, value in scores.items()}


class EnemyFactor:
    """同遭遇联合变体评分；相关读数先聚合，整帧异常作为一个混合分量。"""

    def __init__(self, map_data: TrackingMap, profile: FusionProfile) -> None:
        self.map_data = map_data
        self.profile = profile
        self._all_variants = tuple(
            dict.fromkeys(
                variant
                for node in map_data.nodes.values()
                for variant in (node.enemy_formations or ())
            )
        )
        self._enemy_cache: dict[tuple[str, int, tuple[_EnemySignature, ...]], float] = {}
        self._background_cache: dict[tuple[_EnemySignature, ...], float] = {}

    def update(self, state: _State, obs: FusionObservation) -> tuple[_State, float]:
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
        return updated, self.score(updated) - self.score(state)

    def score(self, state: _State) -> float:
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
        if formations and fleet.formation is not None:
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

    def diagnostics(self, obs: FusionObservation) -> dict[str, Any]:
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
                robust_scores[name] = self.score(_State(name, _SPOT, -1, evidence=(signature,)))
                continue
            robust = [
                self.score(_State(name, _SPOT, index, evidence=(signature,)))
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
            'weights': _normalized_logs(robust_scores),
        }


class GeometryFactor:
    """保存上一有效船位等局部运动上下文，不复制跨事件的状态图历史。"""

    def __init__(self, map_data: TrackingMap, profile: FusionProfile, *, geometric: bool) -> None:
        self.map_data = map_data
        self.profile = profile
        self._geometric = geometric
        self.point_terms: dict[str, dict[str, Any]] = {}
        self.last_motion: FusionObservation | None = None

    def prepare(self, obs: FusionObservation) -> None:
        self.point_terms = {}
        if self._geometric and obs.kind == 'motion' and obs.position is not None:
            raw = {
                name: self.terms(_State(name, _NAV), obs)
                for name, node in self.map_data.nodes.items()
                if name != '0' and node.position is not None
            }
            self.point_terms = combine_point_terms(raw, self.profile.frame_outlier)

    def score(self, state: _State, obs: FusionObservation) -> float:
        """同一船位的距离和方向只合成为一个观测因子。"""
        if self._geometric and obs.kind == 'motion':
            row = self.point_terms.get(state.node)
            return math.log(row['point_likelihood']) if row else 0.0
        terms = self.terms(state, obs)
        return terms['log_likelihood'] if terms['available'] else 0.0

    def terms(self, state: _State, obs: FusionObservation) -> dict[str, Any]:
        """逐航段计算实际使用的几何量，供模型和调试共用。"""
        if obs.kind != 'motion' or obs.position is None:
            return {'available': False, 'reason': '本次不是带有效船位的运动观测'}
        names = (
            state.route[state.edge : state.edge + 2]
            if state.stage == _NAV and state.route
            else (state.node,)
        )
        if any(self.map_data.nodes[name].position is None for name in names):
            return {'available': False, 'reason': '地图没有提供本节点或航段的坐标'}
        position = _pixels(obs.position)
        origin = _pixels(self.map_data.nodes[names[0]].position)
        destination = _pixels(self.map_data.nodes[names[-1]].position)
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
        previous = self.last_motion
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

    def channels(self, obs: FusionObservation) -> dict[str, Any]:
        """全图距离和射线的独立观察结果，仅用于调试对照。"""
        if obs.kind != 'motion' or obs.position is None:
            missing = {'available': False, 'reason': '本次没有新的船位证据', 'weights': {}}
            return {'distance': dict(missing), 'ray': dict(missing)}
        terms = {
            name: self.terms(_State(name, _SPOT), obs)
            for name, node in self.map_data.nodes.items()
            if name != '0' and node.position is not None
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
                'weights': _normalized_logs(distance_scores),
            },
            'ray': {
                'available': bool(ray_scores),
                'scope': '全图节点，仅调试对照；不与距离进行独立投票',
                'reason': first.get('ray_unavailable_reason', '地图没有可比较节点'),
                'frame_gap_seconds': first.get('frame_gap_seconds'),
                'mixture_weight': first.get('ray_mixture_weight', 0.0),
                'raw_distance_px': {name: row['ray_distance_px'] for name, row in terms.items()},
                'likelihoods': {name: row['ray_likelihood'] for name, row in terms.items()},
                'weights': _normalized_logs(ray_scores),
            },
        }


class NodeLabelFactor:
    """字母读数是软证据；同遭遇的相同读数只计一次，不将轮询次数当置信度。"""

    def __init__(self, map_data: TrackingMap, profile: FusionProfile) -> None:
        self.map_data = map_data
        self.profile = profile

    def update(self, state: _State, obs: FusionObservation) -> tuple[_State, float]:
        label = obs.node_label
        if label not in self.map_data.nodes or label in state.labels:
            return state, 0.0
        updated = replace(state, labels=(*state.labels, label))
        return updated, self.score(updated) - self.score(state)

    def score(self, state: _State) -> float:
        if not state.labels or len(self.map_data.nodes) <= 1:
            return 0.0
        accuracy = self.profile.node_label_accuracy
        count = len(self.map_data.nodes)
        return sum(
            math.log((accuracy if label == state.node else (1 - accuracy) / (count - 1)) * count)
            for label in state.labels
        ) / len(state.labels)

    def diagnostics(self, obs: FusionObservation) -> dict[str, Any]:
        scores = (
            {
                name: self.score(_State(name, 'MAP_READY', labels=(obs.node_label,)))
                for name in self.map_data.nodes
            }
            if obs.node_label in self.map_data.nodes
            else {}
        )
        return {
            'available': bool(scores),
            'label': obs.node_label,
            'weights': _normalized_logs(scores),
        }
