"""使用不含敌情观测的历史定位，统计 native 敌舰类别识别；不自动调整算法。

参照节点仍是独立证据形成的估计，并非人工真值。只比较所有合法敌情变体均一致的
字段，避免用待测识别结果选择最相似的模板，再把它当作正确答案。
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
from importlib.metadata import version
from threading import Lock
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from autowsgr_native.vessel_type import VesselType

from autowsgr.combat.node_fusion.map import SHIP_TYPES, TrackingMap
from autowsgr.combat.node_fusion.model import MODEL_VERSION, FusionTracker


if TYPE_CHECKING:
    from autowsgr.combat.node_fusion.enemy import EnemyObservation
    from autowsgr.combat.node_fusion.map import TrackingNode


REFERENCE_THRESHOLD = 0.95
_NATIVE_SHIPS = {
    value.as_english(): value.as_chinese()
    for name in dir(VesselType)
    if isinstance(value := getattr(VesselType, name), VesselType) and value.as_english() != 'NO'
}


@dataclass
class RecognitionCount:
    """互斥的样本去向；已核对数等于 correct + errors，缺失另计。"""

    total: int = 0
    correct: int = 0
    errors: int = 0
    missing: int = 0
    ambiguous: int = 0
    no_reference: int = 0
    not_attempted: int = 0
    empty: int = 0

    def observe(
        self,
        value: object,
        expected: set[object] | None,
        *,
        attempted: bool = True,
    ) -> None:
        self.total += 1
        if not attempted:
            self.not_attempted += 1
        elif not expected:
            self.no_reference += 1
        elif len(expected) != 1:
            self.ambiguous += 1
        elif expected == {None}:
            # NO 不能可靠区分漏检与空槽，不把它等同于正确识别空槽。
            self.empty += 1
        elif value is None:
            self.missing += 1
        elif value in expected:
            self.correct += 1
        else:
            self.errors += 1


@dataclass
class RecognitionStats:
    """首次索敌的 native 舰类计数；槽号从 1 开始，混淆表保留原始英文识别码。"""

    samples: int = 0
    located: int = 0
    repeated: int = 0
    ignored: int = 0
    ships: RecognitionCount = field(default_factory=RecognitionCount)
    ship_slots: dict[str, RecognitionCount] = field(
        default_factory=lambda: {str(index): RecognitionCount() for index in range(1, 7)}
    )
    ship_confusion: dict[str, dict[str, int]] = field(default_factory=dict)
    ship_slot_confusion: dict[str, dict[str, dict[str, int]]] = field(
        default_factory=lambda: {str(index): {} for index in range(1, 7)}
    )

    def observe(self, enemy: EnemyObservation | None, node: TrackingNode | None) -> None:
        self.samples += 1
        self.located += node is not None
        variants = node.enemy_formations if node is not None else None
        raw_slots = (
            enemy.raw_slots
            if enemy is not None and enemy.valid_slots and len(enemy.raw_slots) == 6
            else None
        )
        for index in range(6):
            expected = (
                {item.ships[index] if index < len(item.ships) else None for item in variants}
                if variants
                else None
            )
            code = raw_slots[index] if raw_slots is not None else None
            # 统计 native 原始结果，不能用已转换的 ships 补救 NO、未知码或非法槽数。
            value = _NATIVE_SHIPS.get(code) if isinstance(code, str) else None
            slot = str(index + 1)
            self.ships.observe(value, expected)
            self.ship_slots[slot].observe(value, expected)
            if expected is None or len(expected) != 1:
                continue
            true_ship = next(iter(expected))
            if true_ship not in SHIP_TYPES:
                continue
            if enemy is None:
                column = 'MISSING'
            elif raw_slots is None:
                column = 'INVALID_SLOTS'
            elif code == 'NO' or value is not None:
                column = code
            else:
                column = 'UNKNOWN'
            # 缺失列仍计 missing；未知原始字符串合并，防止异常内容无限扩张键名。
            # 仅在独立定位且所有模板对该槽一致时记录，不用识别结果选择参照模板。
            for matrix in (self.ship_confusion, self.ship_slot_confusion[slot]):
                row = matrix.setdefault(true_ship, {})
                row[column] = row.get(column, 0) + 1


def _add_counts(total: dict[str, Any], delta: dict[str, Any]) -> None:
    """递归相加计数，支持新出现的参照舰类和原始识别码。"""
    for key, count in delta.items():
        if isinstance(count, dict):
            _add_counts(total.setdefault(key, {}), count)
        else:
            total[key] = total.get(key, 0) + count


def _reference_history(
    tracker: FusionTracker,
) -> tuple[dict[int, dict[str, Any]], dict[int, int | None], set[int]]:
    """去掉全部敌情重新平滑；原始敌情读数不参与参照节点或遭遇归属。"""
    metadata = TrackingMap(
        {
            name: replace(node, enemy_formations=None, detour=None)
            for name, node in tracker.map_data.nodes.items()
        }
    )
    reference = FusionTracker(metadata, tracker.profile)
    anchors: dict[int, int | None] = {}
    invalid = set()
    last_phase = None
    for event_id, observation in enumerate(tracker.observations):
        estimate = reference.observe(replace(observation, enemies=None, decision_node=None))
        if observation.kind != 'phase':
            continue
        if estimate.ignored == 'same phase evidence segment':
            # 被参照模型合并的同页读数仍对应原始首次截图，不能选择后来成功的读数。
            anchors[event_id] = last_phase
        elif estimate.ignored:
            invalid.add(event_id)
        else:
            last_phase = event_id if estimate.anomaly is None else None
            anchors[event_id] = last_phase
    return {row['event_id']: row for row in reference.estimate.history}, anchors, invalid


def recognition_stats(tracker: FusionTracker) -> RecognitionStats:
    """每个独立推断遭遇只取最早索敌帧；不要求该帧成功识别或成功定位。"""
    stats = RecognitionStats()
    if not any(obs.phase == 'SPOT_ENEMY_SUCCESS' for obs in tracker.observations):
        return stats
    history, anchors, invalid = _reference_history(tracker)
    encounters: dict[int, int] = {}
    encounter = 0
    for event_id, row in sorted(history.items()):
        if row['transition'] in ('new_encounter', 'geometric_arrival'):
            encounter += 1
        encounters[event_id] = encounter
    seen = set()
    action_generation = 0
    for event_id, observation in enumerate(tracker.observations):
        if (
            observation.kind == 'action'
            and observation.action in ('proceed', 'detour')
            and observation.clicked is not False
        ):
            action_generation += 1
        if observation.kind != 'phase' or observation.phase != 'SPOT_ENEMY_SUCCESS':
            continue
        if event_id in invalid:
            stats.ignored += 1
            continue
        anchor = anchors.get(event_id)
        key = (
            ('encounter', encounters[anchor])
            if anchor in encounters
            else ('unknown', action_generation)
        )
        if key in seen or ('unknown', action_generation) in seen:
            # 同一航行段中由无法定位恢复为已定位，仍保留首次原始读数。
            # 将新获得的遭遇编号并入去重集合，后续重试也不能补选成功帧。
            seen.add(key)
            stats.repeated += 1
            continue
        seen.add(key)
        row = history.get(anchor, {})
        weights = row.get('node_weights', {})
        best = max(weights, key=weights.get) if weights else None
        node = tracker.map_data.nodes.get(best)
        if (
            best == '0'
            or node is None
            or node.silent
            or weights[best] < REFERENCE_THRESHOLD
            or row.get('viterbi_node') != best
        ):
            node = None
        stats.observe(observation.enemies, node)
    return stats


class CalibrationTotals:
    """进程累计快照与每趟唯一增量，日志合并时不得重复累加快照。"""

    def __init__(self) -> None:
        self.run_id = uuid4().hex
        native_mapping = {
            name: value.as_chinese()
            for name in dir(VesselType)
            if isinstance(value := getattr(VesselType, name), VesselType)
        }
        self.native_mapping_sha256 = hashlib.sha256(
            json.dumps(native_mapping, ensure_ascii=False, sort_keys=True).encode('utf-8')
        ).hexdigest()
        self._lock = Lock()
        self._sorties: set[str] = set()
        self._total = asdict(RecognitionStats())

    def add(self, sortie_id: str, stats: RecognitionStats) -> dict[str, Any] | None:
        with self._lock:
            if sortie_id in self._sorties:
                return None
            self._sorties.add(sortie_id)
            delta = asdict(stats)
            _add_counts(self._total, delta)
            return {
                'schema_version': 2,
                'basis': 'enemy_excluded_history_consensus',
                'reference_threshold': REFERENCE_THRESHOLD,
                'model_version': MODEL_VERSION,
                'native_version': version('autowsgr-native'),
                'native_mapping_sha256': self.native_mapping_sha256,
                'run_id': self.run_id,
                'sortie_id': sortie_id,
                'completed_sorties': len(self._sorties),
                'delta': delta,
                'cumulative': deepcopy(self._total),
            }


CALIBRATION_TOTALS = CalibrationTotals()
