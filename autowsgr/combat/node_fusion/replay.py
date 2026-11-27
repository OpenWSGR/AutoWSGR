"""离线重放标量 JSONL，不改写原始日志，也不连接模拟器。

用法：python -m tools.node_fusion.replay LOG.jsonl --output summary.json
可选 --labels labels.json 接收显式的 {"event_id": "真实节点"} 标签。
"""

from __future__ import annotations

import argparse
import json
import sys
import zlib
from dataclasses import fields
from pathlib import Path
from typing import Any

from autowsgr.combat.node_fusion import (
    MODEL_VERSION,
    FusionObservation,
    FusionProfile,
    FusionTracker,
)
from autowsgr.combat.node_fusion.enemy import EnemyObservation
from autowsgr.combat.node_fusion.map import TrackingMap
from autowsgr.combat.plan import CombatMode


SCHEMA_VERSION = 4


def _decompress_gzip(content: bytes) -> tuple[bytes, list[str]]:
    """逐个校验 gzip member，仅恢复最后一个短写 member 已解出的 JSON 前缀。"""
    parts = []
    while content:
        prefix = content[:3]
        if prefix != b'\x1f\x8b\x08'[: len(prefix)]:
            raise ValueError('Invalid gzip log: invalid member header')
        decoder = zlib.decompressobj(wbits=16 + zlib.MAX_WBITS)
        try:
            parts.append(decoder.decompress(content))
        except zlib.error as exc:
            raise ValueError(f'Invalid gzip log: {exc}') from exc
        if not decoder.eof:
            # trailer 短写也保留完整末条记录，但不能声称尾记录已通过完整性校验。
            return b''.join(parts), [
                'Recovered truncated final gzip member; tail records lack a complete integrity check'
            ]
        content = decoder.unused_data.lstrip(b'\x00')
    return b''.join(parts), []


def _read_records(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    records, warnings = [], []
    content = path.read_bytes()
    if content.startswith(b'\x1f\x8b'):
        content, warnings = _decompress_gzip(content)
    lines = content.splitlines(keepends=True)
    for index, line in enumerate(lines):
        final_unterminated = index == len(lines) - 1 and not line.endswith(b'\n')
        try:
            decoded = line.decode('utf-8')
            record = json.loads(decoded)
        except UnicodeDecodeError as exc:
            if final_unterminated and exc.reason == 'unexpected end of data':
                warnings.append(f'Ignored truncated final line {index + 1}')
                break
            raise ValueError(f'Invalid UTF-8 on line {index + 1}') from exc
        except json.JSONDecodeError as exc:
            incomplete = exc.pos >= len(decoded.rstrip()) or exc.msg.startswith('Unterminated')
            if final_unterminated and incomplete:
                warnings.append(f'Ignored truncated final line {index + 1}')
                break
            raise ValueError(f'Invalid JSON on line {index + 1}: {exc.msg}') from exc
        if not isinstance(record, dict):
            raise TypeError(f'Line {index + 1} must contain an object')
        if record.get('kind') not in ('start', 'profile', 'observation', 'disabled'):
            raise ValueError(f'Unknown record kind on line {index + 1}: {record.get("kind")!r}')
        records.append(record)
    return records, warnings


def _observation(raw: dict[str, Any]) -> FusionObservation:
    values = dict(raw)
    if values.get('position') is not None:
        values['position'] = tuple(values['position'])
    if values.get('enemies') is not None:
        enemy = dict(values['enemies'])
        enemy['raw_slots'] = tuple(enemy['raw_slots'])
        enemy['ships'] = tuple(enemy['ships'])
        values['enemies'] = EnemyObservation(**enemy)
    return FusionObservation(**values)


def _top_node(weights: dict[str, float]) -> str | None:
    return max(weights, key=weights.get) if weights else None


def _labels(raw: dict[str, str] | None, observations: int, metadata: TrackingMap) -> dict[int, str]:
    result = {}
    for key, node in (raw or {}).items():
        if not isinstance(key, str) or not key.isdecimal():
            raise ValueError(f'Label event_id must be a nonnegative decimal string: {key!r}')
        event_id = int(key)
        if event_id >= observations or node not in metadata.nodes:
            raise ValueError(f'Invalid ground-truth label: {key!r}: {node!r}')
        result[event_id] = node
    return result


def _metadata(start: dict[str, Any]) -> TrackingMap:
    """使用冻结中文地图，并核对身份；不读取可能已经改变的当前资料。"""
    if 'metadata_snapshot' not in start or 'metadata_sha256' not in start:
        raise ValueError('Replay v4 requires a frozen metadata snapshot and fingerprint')
    metadata = TrackingMap.from_dict(start['metadata_snapshot'])
    if start['metadata_sha256'] != metadata.fingerprint:
        raise ValueError('Tracking metadata fingerprint differs from the recorded sortie')
    if 'capabilities' in start and start['capabilities'] != metadata.capabilities:
        raise ValueError('Recorded map capabilities differ from the metadata snapshot')
    return metadata


def _context(start: dict[str, Any]) -> tuple[str, dict[str, float] | None]:
    """恢复场景与初始条件，旧模型日志必须由对应提交回放。"""
    if start.get('schema_version') != SCHEMA_VERSION:
        raise ValueError('Recorded schema version differs; use the matching backend revision')
    if start.get('model_version') != MODEL_VERSION:
        raise ValueError('Recorded model version differs; use the matching backend revision')
    mode = start.get('combat_mode')
    expected = {
        CombatMode.NORMAL: 'map',
        CombatMode.EVENT: 'map',
        CombatMode.DECISIVE: 'decisive',
    }
    dynamics = start.get('dynamics')
    if mode not in expected or dynamics != expected[mode]:
        raise ValueError('Recorded combat mode and scene dynamics are missing or inconsistent')
    if 'initial' not in start or not isinstance(start.get('sampling'), dict):
        raise ValueError('Replay v4 requires explicit initial conditions and sampling parameters')
    return dynamics, start['initial']


def replay(log_path: Path, labels: dict[str, str] | None = None) -> dict[str, Any]:
    """使用日志内冻结的模型参数重建推断，并核对在线估计。"""
    records, warnings = _read_records(log_path)
    starts = [row for row in records if row.get('kind') == 'start']
    profiles = [row for row in records if row.get('kind') == 'profile']
    if len(starts) != 1 or len(profiles) != 1:
        raise ValueError('Replay requires exactly one start and one complete profile record')
    start, raw_profile = starts[0], profiles[0]['profile']
    dynamics, initial = _context(start)
    required = {field.name for field in fields(FusionProfile)}
    if not isinstance(raw_profile, dict) or set(raw_profile) != required:
        raise ValueError(
            'Recorded profile is incomplete or incompatible; current defaults are not used'
        )
    profile = FusionProfile(**raw_profile)
    metadata = _metadata(start)

    tracker = FusionTracker(metadata, profile, dynamics=dynamics, initial=initial)
    raw_observations = [row for row in records if row.get('kind') == 'observation']
    truth = _labels(labels, len(raw_observations), metadata)
    phases, revisions, mismatches, samples = [], [], [], {}
    corrections = dict.fromkeys(truth)
    final_estimate = None
    compared = 0
    for event_id, row in enumerate(raw_observations):
        try:
            observation = _observation(row['observation'])
            estimate = tracker.observe(observation)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f'Invalid observation {event_id}: {exc}') from exc
        final_estimate = estimate
        saved = row.get('estimate')
        if saved is not None:
            if saved.get('model_version', MODEL_VERSION) != MODEL_VERSION:
                raise ValueError(
                    'Recorded model version differs; use the matching backend revision'
                )
            current = json.loads(json.dumps(estimate.as_dict(), ensure_ascii=False))
            current['state_count'] = len(estimate.state_weights)
            compared += 1
            different = [key for key, value in saved.items() if current.get(key) != value]
            if different:
                mismatches.append({'event_id': event_id, 'fields': different})
        samples[event_id] = {
            'top1': _top_node(estimate.node_weights),
            'ambiguous': estimate.ambiguous,
        }
        if event_id in truth and samples[event_id]['top1'] == truth[event_id]:
            corrections[event_id] = 0
        for history in estimate.history:
            old_id = history['event_id']
            if (
                old_id in truth
                and corrections[old_id] is None
                and history['best_node'] == truth[old_id]
            ):
                corrections[old_id] = event_id - old_id
        revisions.extend({'observed_at': event_id, **change} for change in estimate.revisions)
        if observation.kind == 'phase':
            phases.append(
                {
                    'event_id': event_id,
                    'timestamp': observation.timestamp,
                    'phase': observation.phase,
                    'node_weights': estimate.node_weights,
                    'target_weights': estimate.target_weights,
                    'best_route': estimate.best_route,
                    'ambiguous': estimate.ambiguous,
                    'anomaly': estimate.anomaly,
                    'ignored': estimate.ignored,
                    'revisions': estimate.revisions,
                    'diagnostics': estimate.diagnostics,
                }
            )
    metrics: dict[str, Any] = {'status': 'unlabelled', 'labelled_observations': 0}
    if truth:
        correct = sum(samples[key]['top1'] == node for key, node in truth.items())
        metrics = {
            'status': 'labelled',
            'labelled_observations': len(truth),
            'top1_correct': correct,
            'top1_accuracy': correct / len(truth),
            'ambiguous_observations': sum(samples[key]['ambiguous'] for key in truth),
            'first_correction_observations': corrections,
            'uncorrected_observations': sum(delay is None for delay in corrections.values()),
        }
    return {
        'source': str(log_path),
        'map': start['map'],
        'schema_version': SCHEMA_VERSION,
        'model_version': MODEL_VERSION,
        'combat_mode': start['combat_mode'],
        'dynamics': dynamics,
        'initial': initial,
        'sampling': start['sampling'],
        'profile': raw_profile,
        'metadata_sha256': metadata.fingerprint,
        'metadata_verified': start.get('metadata_sha256') is not None,
        'metadata_source': start.get('metadata_source'),
        'metadata_snapshot_used': 'metadata_snapshot' in start,
        'capabilities': metadata.capabilities,
        'degradation_reasons': metadata.degradation_reasons,
        'observation_count': len(raw_observations),
        'phase_count': len(phases),
        'phases': phases,
        'best_route': final_estimate.best_route if final_estimate else (),
        'history_revisions': revisions,
        'online_comparison': {
            'compared': compared,
            'matches': compared - len(mismatches),
            'mismatches': mismatches,
        },
        'labels': metrics,
        'warnings': warnings,
        'disabled': [row['reason'] for row in records if row.get('kind') == 'disabled'],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    parser.add_argument('--labels', type=Path, help='Explicit JSON event_id -> ground-truth node')
    parser.add_argument('--output', type=Path, help='Write a UTF-8 JSON summary')
    args = parser.parse_args(argv)
    if args.output is not None and args.output.resolve() in {
        args.log.resolve(),
        args.labels.resolve() if args.labels else None,
    }:
        parser.error('Output must not overwrite source observations or labels')
    try:
        labels = json.loads(args.labels.read_text(encoding='utf-8')) if args.labels else None
        if labels is not None and not isinstance(labels, dict):
            raise ValueError('Labels must be a JSON object')
        summary = replay(args.log, labels)
        output = json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
        if args.output is None:
            sys.stdout.write(output)
        else:
            args.output.write_text(output, encoding='utf-8')
    except (OSError, KeyError, TypeError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
