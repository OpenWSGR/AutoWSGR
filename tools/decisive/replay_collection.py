"""将决战原始采集快照转换成 v4 回放；只读完整行，不连接游戏或重新调用 native。"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import statistics
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from autowsgr.combat.node_fusion.calibration import recognition_mismatches
from autowsgr.combat.node_fusion.enemy import EnemyObservation
from autowsgr.combat.node_fusion.model import (
    MODEL_VERSION,
    FusionObservation,
    FusionProfile,
    FusionTracker,
)
from autowsgr.combat.node_fusion.replay import replay
from autowsgr.combat.plan import CombatMode
from autowsgr.ops.decisive.config import MapData
from autowsgr.ops.decisive.tracking import NodeSamplingPolicy


_INITIAL_SOURCES = frozenset(
    {
        'user_confirmed_start',
        'user_confirmed_start_and_entry_stage',
        'confirmed_chapter_reset',
        'confirmed_stage_clear',
    }
)
_PHASES = {
    'map': 'DECISIVE_MAP_READY',
    'enemy': 'SPOT_ENEMY_SUCCESS',
    'formation': 'FORMATION',
    'night_prompt': 'NIGHT_PROMPT',
    'result': 'RESULT',
    'stage_clear_after': 'DECISIVE_STAGE_CLEAR',
}
_NEXT_PHASES = frozenset({'PREPARE_COMBAT', 'CHOOSE_FLEET', 'ADVANCE_CHOICE', 'STAGE_CLEAR'})


def read_snapshot(source: Path) -> tuple[list[dict[str, Any]], bytes, int]:
    """一次读取固定字节前缀；末尾即使是合法 JSON，没有换行仍留给下次采集。"""
    content = source.read_bytes()
    boundary = content.rfind(b'\n') + 1
    complete = content[:boundary]
    rows = []
    for number, line in enumerate(complete.splitlines(), 1):
        try:
            row = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f'Invalid complete collection line {number}') from exc
        if not isinstance(row, dict):
            raise TypeError(f'Collection line {number} must be an object')
        rows.append(row)
    return rows, complete, len(content) - boundary


def _initial(
    rows: list[dict[str, Any]], nodes: set[str]
) -> tuple[dict[str, float] | None, str | None]:
    """只在第一条观测前读取流程起点；之后的标签不改变初始化或模型证据。"""
    initial, source = None, None
    for row in rows:
        if row['kind'] == 'stage_clear_after':
            break
        if row.get('label_source') in _INITIAL_SOURCES and row.get('label_node') in nodes:
            initial = {row['label_node']: 1.0}
            source = row['label_source']
        if row['kind'] in _PHASES or row['kind'] == 'combat_start':
            break
    return initial, source


def _enemy(raw: dict[str, Any]) -> EnemyObservation:
    values = dict(raw)
    values['raw_slots'] = tuple(values['raw_slots'])
    values['ships'] = tuple(values['ships'])
    return EnemyObservation(**values)


def _timestamp(row: dict[str, Any], *, action: bool = False) -> float:
    value = (
        row.get('recorded_monotonic')
        if action
        else row.get('captured_at', row.get('recorded_monotonic'))
    )
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'Missing finite timestamp in sample {row.get("sample_id")}')
    return float(value)


@dataclass
class _Encounter:
    sample_id: int | None
    enemy_reads: int = 0
    formation: bool = False
    progressed: bool = False
    result: str | None = None
    complete: bool = False
    explicit_missing: bool = False
    blocked: bool = False
    completion_source: str | None = None


@dataclass
class _Stage:
    """转换期的流程账本；标签仅用于单独验收，预测值不参与计步。"""

    tracker: FusionTracker
    truth_node: str | None
    records: list[dict[str, Any]] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)
    samples: dict[int, dict[str, Any]] = field(default_factory=dict)
    encounters: dict[str, _Encounter] = field(default_factory=dict)
    durations: list[float] = field(default_factory=list)
    pending: str | None = None
    pending_row: dict[str, Any] | None = None
    pending_observations: list[dict[str, Any]] = field(default_factory=list)
    duplicate_completions: int = 0
    stage_clear: bool = False

    def publish(self, observation: FusionObservation, row: dict[str, Any]) -> None:
        started = time.perf_counter()
        estimate = self.tracker.observe(observation)
        self.durations.append((time.perf_counter() - started) * 1000)
        event_id = len(self.records)
        self.samples[event_id] = {
            'sample_id': row.get('sample_id'),
            'frame': row.get('frame'),
            'recorded_at': row.get('recorded_at'),
        }
        self.records.append(
            {
                'kind': 'observation',
                'schema_version': 4,
                'observation': asdict(observation),
                'estimate': estimate.as_dict(),
                'source_sample': self.samples[event_id],
            }
        )
        if self.truth_node is not None:
            self.labels[str(event_id)] = self.truth_node

    def complete(self, row: dict[str, Any], observation: FusionObservation | None = None) -> bool:
        encounter_id = observation.encounter_id if observation is not None else self.pending
        if encounter_id is None:
            return False
        if encounter_id not in self.encounters:
            raise ValueError(f'Completion has no recorded battle: {encounter_id}')
        encounter = self.encounters[encounter_id]
        if encounter.complete:
            self.duplicate_completions += 1
            return False
        if (
            encounter.blocked
            or encounter.result != 'success'
            or (observation is None and row.get('phase') not in _NEXT_PHASES)
            or row.get('stopped')
        ):
            return False
        source = row if observation is not None else self.pending_row
        if source is None:
            raise ValueError('Legacy completion requires its node_result_before record')
        if observation is None:
            # 旧档案缺少真实完成事件；确认后将它重建在随后地图读取之前。
            # 此时间仅维持因果次序，不声称等于在线会话的实际完成时刻。
            observation = FusionObservation(
                'action',
                _timestamp(source, action=True),
                action='encounter_complete',
                clicked=True,
                encounter_id=encounter_id,
            )
            encounter.completion_source = 'legacy_before_timestamp'
        else:
            encounter.completion_source = 'recorded_observation'
        encounter.complete = True
        if self.truth_node is not None:
            successors = self.tracker.map_data.nodes[self.truth_node].next_nodes
            if successors:
                self.truth_node = successors[0]
        self.publish(observation, source)
        return True

    def _consume_progress(self, row: dict[str, Any]) -> bool:
        """先提交真实完成事件；旧格式必须等流程确认，再恢复中间地图观察。"""
        kind, encounter_id = row['kind'], row.get('encounter_id')
        if kind == 'encounter_complete':
            observation = FusionObservation(**row['observation'])
            if (
                observation.kind != 'action'
                or observation.action != 'encounter_complete'
                or observation.clicked is not True
                or observation.encounter_id != encounter_id
            ):
                raise ValueError('Invalid recorded encounter completion')
            self.complete(row, observation)
            self.pending = None
            self.pending_row = None
            return True
        if kind == 'node_result_after':
            completed = self.complete(row)
            self.pending_row = None
            pending, self.pending_observations = self.pending_observations, []
            if completed:
                for observation_row in pending:
                    self.consume(observation_row)
            return True
        if kind == 'node_result_before':
            self.pending = encounter_id if encounter_id in self.encounters else None
            self.pending_row = row if self.pending is not None else None
            self.pending_observations.clear()
            return True
        return False

    def consume(self, row: dict[str, Any]) -> None:
        if self._consume_progress(row):
            return
        kind, encounter_id = row['kind'], row.get('encounter_id')
        if kind in ('stopped', 'exception', 'dock_full', 'incomplete'):
            if encounter_id in self.encounters:
                self.encounters[encounter_id].blocked = True
            self.pending = None
            self.pending_row = None
            self.pending_observations.clear()
            return
        if encounter_id is not None and kind in {
            'combat_start',
            'combat_end',
            'enemy',
            'enemy_missing',
            'formation',
            'night_prompt',
            'result',
        }:
            encounter = self.encounters.setdefault(encounter_id, _Encounter(row.get('sample_id')))
            encounter.enemy_reads += kind == 'enemy'
            encounter.formation |= kind == 'formation'
            encounter.progressed |= kind in ('formation', 'night_prompt', 'result', 'combat_end')
            encounter.explicit_missing |= kind == 'enemy_missing'
            if kind == 'combat_end' and encounter.result is None:
                encounter.result = row.get('result') or 'unknown'
        if kind not in _PHASES:
            return
        if self.pending_row is not None:
            self.pending_observations.append(row)
            return
        # 旧采集的 stage_clear_before 只是预测；操作及返回入口确认成功后才接受通关。
        if kind == 'stage_clear_after':
            if row.get('label_source') != 'confirmed_stage_clear' and not row.get(
                'completion_confirmed'
            ):
                return
            self.stage_clear = True
            self.truth_node = next(
                name for name, node in self.tracker.map_data.nodes.items() if node.next_nodes == ()
            )
        raw_label = (
            row.get('raw_node') if kind == 'map' and row.get('used_for_tracking', True) else None
        )
        node_label = raw_label[:1] if isinstance(raw_label, str) and raw_label else None
        if node_label not in self.tracker.map_data.nodes:
            node_label = None
        self.publish(
            FusionObservation(
                'phase',
                _timestamp(row),
                frame_id=row.get('frame_sequence'),
                phase=_PHASES[kind],
                enemies=_enemy(row['observation']) if kind == 'enemy' else None,
                node_label=node_label,
                encounter_id=encounter_id,
                decision_node=row.get('predicted_node'),
            ),
            row,
        )

    def report(self) -> dict[str, Any]:
        missing = [
            {
                'encounter_id': name,
                'source_sample_id': item.sample_id,
                'formation_observed': item.formation,
                'completed': item.complete,
                'reason': 'no_spot_observation'
                if item.formation
                else 'direct_combat_without_spot_or_formation',
            }
            for name, item in self.encounters.items()
            if not item.enemy_reads and (item.progressed or item.explicit_missing)
        ]
        feedback = recognition_mismatches(self.tracker, combat_mode=CombatMode.DECISIVE)
        return {
            'completed_encounters': sum(item.complete for item in self.encounters.values()),
            'encounters': len(self.encounters),
            'enemy_missing': missing,
            'enemy_missing_count': len(missing),
            'duplicate_completions_ignored': self.duplicate_completions,
            'completion_sources': dict(
                Counter(
                    item.completion_source for item in self.encounters.values() if item.complete
                )
            ),
            'uncommitted_success': [
                name
                for name, item in self.encounters.items()
                if item.result == 'success' and not item.complete
            ],
            'failed_or_unknown_results': {
                name: item.result
                for name, item in self.encounters.items()
                if item.result not in (None, 'success')
            },
            'stage_clear_confirmed': self.stage_clear,
            'native_feedback': [
                {**asdict(item), 'source_sample': self.samples[item.event_id]} for item in feedback
            ],
            'incremental_timing_ms': {
                'count': len(self.durations),
                'total': sum(self.durations),
                'median': statistics.median(self.durations) if self.durations else None,
                'p95': sorted(self.durations)[math.ceil(len(self.durations) * 0.95) - 1]
                if self.durations
                else None,
            },
        }


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8'
    )


def convert_collection(source: Path, output: Path) -> dict[str, Any]:
    """每次创建独立快照目录；重跑不会覆盖上次报告或采集进程的输出。"""
    rows, frozen, trailing = read_snapshot(source)
    digest = hashlib.sha256(frozen).hexdigest()
    destination = output / f'snapshot-{len(rows):06d}-{digest[:8]}-{uuid4().hex[:8]}'
    destination.mkdir(parents=True, exist_ok=False)
    (destination / 'source-observations.jsonl').write_bytes(frozen)
    groups: dict[tuple[int, int, int], list[dict[str, Any]]] = {}
    for row in rows:
        key = tuple(row.get(name) for name in ('round', 'chapter', 'stage'))
        if all(type(value) is int and value > 0 for value in key) and key[2] <= 3:
            groups.setdefault(key, []).append(row)
    stages = []
    for (round_number, chapter, stage_number), group in groups.items():
        metadata = MapData.tracking_map(chapter, stage_number)
        initial, initial_source = _initial(group, set(metadata.nodes))
        profile = FusionProfile(min_travel_seconds=None)
        tracker = FusionTracker(metadata, profile, dynamics='decisive', initial=initial)
        stage = _Stage(tracker, next(iter(initial)) if initial else None)
        for row in group:
            stage.consume(row)
        if not stage.records:
            continue
        stem = f'round-{round_number:02d}-{chapter}-{stage_number}'
        log = destination / f'{stem}.jsonl.gz'
        start = {
            'kind': 'start',
            'schema_version': 4,
            'model_version': MODEL_VERSION,
            'combat_mode': CombatMode.DECISIVE,
            'dynamics': 'decisive',
            'initial': initial,
            'sampling': {**asdict(NodeSamplingPolicy()), 'collection_forced_map_samples': True},
            'map': [chapter, stage_number],
            'metadata_snapshot': metadata.to_dict(),
            'metadata_sha256': metadata.fingerprint,
            'capabilities': metadata.capabilities,
            'source_collection': str(source.resolve()),
            'source_sha256': digest,
            'native_version': group[0].get('native_version'),
            'initial_label_source': initial_source,
        }
        records = [start, {'kind': 'profile', 'profile': asdict(profile)}, *stage.records]
        log.write_bytes(
            gzip.compress(
                (
                    ''.join(
                        json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n'
                        for row in records
                    )
                ).encode('utf-8')
            )
        )
        summary = replay(log, stage.labels)
        _write_json(destination / f'{stem}.labels.json', stage.labels)
        _write_json(destination / f'{stem}.summary.json', summary)
        stages.append(
            {
                'round': round_number,
                'chapter': chapter,
                'stage': stage_number,
                'initial': initial,
                'initial_label_source': initial_source,
                'replay_log': str(log),
                'observation_count': len(stage.records),
                'comparison': summary['online_comparison'],
                'labels': summary['labels'],
                **stage.report(),
            }
        )
    report = {
        'source': str(source.resolve()),
        'output': str(destination),
        'source_sha256': digest,
        'complete_source_rows': len(rows),
        'ignored_unterminated_bytes': trailing,
        'last_sample_id': rows[-1].get('sample_id') if rows else None,
        'source_kind_counts': dict(Counter(row['kind'] for row in rows)),
        'comparison_basis': 'incremental_v4_reconstruction_vs_offline_v4',
        'label_basis': 'independent_initial_label_plus_verified_progress',
        'accuracy_calibration': False,
        'live_fusion_control_verified': False,
        'stages': stages,
        'all_replays_match': bool(stages)
        and all(not row['comparison']['mismatches'] for row in stages),
        'completed_encounters': sum(row['completed_encounters'] for row in stages),
        'enemy_missing_count': sum(row['enemy_missing_count'] for row in stages),
    }
    _write_json(destination / 'validation-report.json', report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='采集 observations.jsonl')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    report = convert_collection(args.source, args.output)
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    'output',
                    'complete_source_rows',
                    'completed_encounters',
                    'enemy_missing_count',
                    'all_replays_match',
                )
            },
            ensure_ascii=False,
        )
    )
    return 0 if report['all_replays_match'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
