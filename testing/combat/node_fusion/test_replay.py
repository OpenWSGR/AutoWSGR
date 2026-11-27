"""标量回放复现在线推断，不凭空生成真值。"""

from __future__ import annotations

import gzip
import json
from dataclasses import asdict, replace
from typing import TYPE_CHECKING

import pytest

from autowsgr.combat.node_fusion import (
    MODEL_VERSION,
    FusionObservation,
    FusionProfile,
    FusionTracker,
)
from autowsgr.combat.node_fusion.enemy import EnemyObservation
from autowsgr.combat.node_fusion.map import TrackingMap
from autowsgr.ops.decisive.config import MapData

from tools.node_fusion.replay import main, replay


if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def scalar_log(tmp_path: Path) -> Path:
    metadata = TrackingMap.load(2, 1)
    profile = FusionProfile(ship_accuracy=0.83, min_travel_seconds=None)
    tracker = FusionTracker(metadata, profile)
    enemy = EnemyObservation(
        raw_slots=('DD',) * 6,
        ships=('驱逐',) * 6,
        formation=2,
        formation_text='复纵阵',
        formation_confidence=0.9,
        detour=None,
        detour_score=None,
    )
    observations = [
        FusionObservation('motion', 1.0, frame_id=1, position=(0.2, 0.2), decision_node='Z'),
        FusionObservation('phase', 2.0, frame_id=2, phase='SPOT_ENEMY_SUCCESS', enemies=enemy),
        FusionObservation('action', 2.1, action='fight', clicked=True),
        FusionObservation('phase', 3.0, frame_id=3, phase='FORMATION'),
    ]
    records = [
        {
            'kind': 'start',
            'schema_version': 4,
            'model_version': MODEL_VERSION,
            'combat_mode': 'normal',
            'dynamics': 'map',
            'initial': None,
            'sampling': {},
            'map': [2, 1],
            'metadata_sha256': metadata.fingerprint,
            'metadata_snapshot': metadata.to_dict(),
        },
        {'kind': 'profile', 'profile': asdict(profile)},
    ]
    for observation in observations:
        estimate = tracker.observe(observation).as_dict()
        estimate.pop('history')
        if observation.kind != 'phase':
            estimate['state_count'] = len(estimate.pop('state_weights'))
        records.append(
            {'kind': 'observation', 'observation': asdict(observation), 'estimate': estimate}
        )
    path = tmp_path / 'sortie.jsonl'
    path.write_text(
        ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in records), encoding='utf-8'
    )
    return path


def test_replay_matches_online_and_requires_explicit_labels(scalar_log: Path):
    original = scalar_log.read_bytes()
    summary = replay(scalar_log)
    assert summary['online_comparison'] == {'compared': 4, 'matches': 4, 'mismatches': []}
    assert summary['profile']['ship_accuracy'] == 0.83
    assert summary['profile']['min_travel_seconds'] is None
    assert summary['labels'] == {'status': 'unlabelled', 'labelled_observations': 0}
    assert summary['metadata_verified']
    assert len(summary['phases']) == 2
    phase = summary['phases'][0]
    top_node = max(phase['node_weights'], key=phase['node_weights'].get)
    labelled = replay(scalar_log, {str(phase['event_id']): top_node})
    assert labelled['labels']['top1_accuracy'] == 1.0
    assert labelled['labels']['first_correction_observations'] == {phase['event_id']: 0}
    assert scalar_log.read_bytes() == original


def test_cli_writes_summary_and_preserves_log(scalar_log: Path, tmp_path: Path):
    original = scalar_log.read_bytes()
    output = tmp_path / 'summary.json'
    assert main([str(scalar_log), '--output', str(output)]) == 0
    assert json.loads(output.read_text(encoding='utf-8'))['observation_count'] == 4
    assert scalar_log.read_bytes() == original
    with pytest.raises(SystemExit):
        main([str(scalar_log), '--output', str(scalar_log)])


@pytest.mark.parametrize('tail', [b'{"kind": "obser', b'{"kind":'])
def test_truncated_final_line_is_reported(scalar_log: Path, tail: bytes):
    with scalar_log.open('ab') as stream:
        stream.write(tail)
    summary = replay(scalar_log)
    assert summary['observation_count'] == 4
    assert summary['warnings'] == ['Ignored truncated final line 7']


@pytest.mark.parametrize('tail', [b'{"kind":\n', b'{"kind": invalid}\n', b'{"kind": invalid}'])
def test_malformed_complete_record_is_rejected(scalar_log: Path, tail: bytes):
    with scalar_log.open('ab') as stream:
        stream.write(tail)
    with pytest.raises(ValueError, match='Invalid JSON on line 7'):
        replay(scalar_log)


def test_unknown_complete_record_is_not_silently_skipped(scalar_log: Path):
    with scalar_log.open('a', encoding='utf-8') as stream:
        stream.write('{"kind": "observaton"}\n')
    with pytest.raises(ValueError, match='Unknown record kind on line 7'):
        replay(scalar_log)


@pytest.mark.parametrize('field', ['metadata_sha256', 'profile'])
def test_incompatible_snapshot_is_rejected(scalar_log: Path, field: str):
    records = [json.loads(line) for line in scalar_log.read_text(encoding='utf-8').splitlines()]
    if field == 'metadata_sha256':
        records[0][field] = 'different'
    else:
        records[1]['profile'].pop('ship_accuracy')
    scalar_log.write_text(''.join(json.dumps(row) + '\n' for row in records), encoding='utf-8')
    with pytest.raises(ValueError, match=r'fingerprint|profile'):
        replay(scalar_log)


def test_metadata_fingerprint_ignores_dict_order_but_detects_content():
    metadata = TrackingMap.load(2, 1)
    reordered = TrackingMap(dict(reversed(list(metadata.nodes.items()))))
    assert reordered.fingerprint == metadata.fingerprint
    changed = dict(metadata.nodes)
    changed['0'] = replace(changed['0'], position=(0.01, 0.01))
    assert TrackingMap(changed).fingerprint != metadata.fingerprint


def test_event_log_uses_matching_event_metadata(tmp_path: Path) -> None:
    metadata = TrackingMap.load_event('20260930', 'E', 1)
    assert metadata is not None
    profile = FusionProfile(min_travel_seconds=None)
    tracker = FusionTracker(metadata, profile)
    variant = metadata.nodes['A'].enemy_formations[0]
    enemy = EnemyObservation(
        raw_slots=(),
        ships=variant.ships + (None,) * (6 - len(variant.ships)),
        formation=variant.formation,
        formation_text='',
        formation_confidence=None,
        detour=None,
        detour_score=None,
    )
    observations = [
        FusionObservation('motion', 1.0, frame_id=1, position=metadata.nodes['A'].position),
        FusionObservation('phase', 2.0, frame_id=2, phase='SPOT_ENEMY_SUCCESS', enemies=enemy),
        FusionObservation('action', 2.1, action='fight', clicked=True),
        FusionObservation('phase', 3.0, frame_id=3, phase='FORMATION'),
    ]
    records = [
        {
            'kind': 'start',
            'schema_version': 4,
            'model_version': MODEL_VERSION,
            'mode': 'fusion',
            'combat_mode': 'event',
            'dynamics': 'map',
            'initial': None,
            'sampling': {},
            'event_name': '20260930',
            'entrance': None,
            'map': ['E', 1],
            'metadata_sha256': metadata.fingerprint,
            'metadata_snapshot': metadata.to_dict(),
        },
        {'kind': 'profile', 'profile': asdict(profile)},
    ]
    records.extend(
        {
            'kind': 'observation',
            'observation': asdict(observation),
            'estimate': tracker.observe(observation).as_dict(),
        }
        for observation in observations
    )
    path = tmp_path / 'event.jsonl'
    path.write_text(
        ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in records), encoding='utf-8'
    )
    result = replay(path, {'1': 'A', '3': 'A'})
    assert result['map'] == ['E', 1]
    assert result['metadata_sha256'] == metadata.fingerprint
    assert result['profile']['min_travel_seconds'] is None
    assert result['online_comparison'] == {'compared': 4, 'matches': 4, 'mismatches': []}
    assert result['best_route'] == ('0', 'A')
    assert result['labels']['top1_correct'] == 2


def test_replay_rejects_previous_model_version(scalar_log: Path) -> None:
    assert MODEL_VERSION != 'history-fusion-1'
    rows = [json.loads(line) for line in scalar_log.read_text(encoding='utf-8').splitlines()]
    rows[2]['estimate']['model_version'] = 'history-fusion-1'
    scalar_log.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
    with pytest.raises(ValueError, match='model version differs'):
        replay(scalar_log)


def test_replay_preserves_each_diagnostic_channel(scalar_log: Path) -> None:
    rows = [json.loads(line) for line in scalar_log.read_text(encoding='utf-8').splitlines()]
    recorded = {
        row['estimate']['event_id']: row['estimate']['diagnostics']
        for row in rows
        if row['kind'] == 'observation' and row['observation']['kind'] == 'phase'
    }
    result = replay(scalar_log)
    for phase in result['phases']:
        assert {'distance', 'ray', 'history_prior', 'geometry', 'enemy', 'fusion'} <= set(
            phase['diagnostics']
        )
        assert json.loads(json.dumps(phase['diagnostics'])) == recorded[phase['event_id']]


def test_replay_rejects_legacy_observation_fields_in_v4(scalar_log: Path) -> None:
    rows = [json.loads(line) for line in scalar_log.read_text(encoding='utf-8').splitlines()]
    rows[2]['observation']['legacy_node'] = 'A'
    scalar_log.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
    with pytest.raises(ValueError, match='legacy_node'):
        replay(scalar_log)


def test_frozen_snapshot_survives_map_replacement(
    scalar_log: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    metadata = TrackingMap.load(2, 1)
    rows = [json.loads(line) for line in scalar_log.read_text(encoding='utf-8').splitlines()]
    rows[0].update(
        metadata_snapshot=metadata.to_dict(),
        metadata_source='已移动的地图.yaml',
        capabilities=metadata.capabilities,
    )
    scalar_log.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')

    def unavailable(*_args: object) -> None:
        raise AssertionError('存在冻结快照时，不应读取已被替换的地图文件')

    monkeypatch.setattr(TrackingMap, 'load', unavailable)
    result = replay(scalar_log)
    assert result['metadata_snapshot_used']
    assert result['metadata_source'] == '已移动的地图.yaml'
    assert result['online_comparison'] == {'compared': 4, 'matches': 4, 'mismatches': []}


@pytest.mark.parametrize('field', ['metadata_snapshot', 'capabilities'])
def test_frozen_snapshot_rejects_changed_data_or_capabilities(scalar_log: Path, field: str) -> None:
    metadata = TrackingMap.load(2, 1)
    rows = [json.loads(line) for line in scalar_log.read_text(encoding='utf-8').splitlines()]
    rows[0].update(metadata_snapshot=metadata.to_dict(), capabilities=metadata.capabilities)
    if field == 'metadata_snapshot':
        rows[0][field]['A']['detour'] = not rows[0][field]['A']['detour']
    else:
        rows[0][field]['enemy'] = False
    scalar_log.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
    with pytest.raises(ValueError, match=r'fingerprint|capabilities'):
        replay(scalar_log)


@pytest.mark.parametrize('schema', [None, 1, 2, 3])
def test_replay_legacy_schema_requires_matching_revision(
    scalar_log: Path, schema: int | None
) -> None:
    rows = [json.loads(line) for line in scalar_log.read_text(encoding='utf-8').splitlines()]
    if schema is None:
        rows[0].pop('schema_version')
    else:
        rows[0]['schema_version'] = schema
    scalar_log.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
    with pytest.raises(
        ValueError, match='schema version differs; use the matching backend revision'
    ):
        replay(scalar_log)


@pytest.mark.parametrize('field', ['initial', 'dynamics', 'sampling', 'metadata_snapshot'])
def test_replay_requires_scene_and_frozen_metadata(scalar_log: Path, field: str) -> None:
    rows = [json.loads(line) for line in scalar_log.read_text(encoding='utf-8').splitlines()]
    rows[0].pop(field)
    scalar_log.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
    with pytest.raises(ValueError, match=r'inconsistent|requires'):
        replay(scalar_log)


def test_replay_reads_gzip_directly_and_preserves_source_name(scalar_log: Path) -> None:
    compressed = scalar_log.with_suffix('.jsonl.gz')
    compressed.write_bytes(gzip.compress(scalar_log.read_bytes()))
    expected = replay(scalar_log)
    actual = replay(compressed)
    assert actual.pop('source') == str(compressed)
    expected.pop('source')
    assert actual == expected
    with pytest.raises(SystemExit):
        main([str(compressed), '--output', str(compressed)])


@pytest.mark.parametrize('missing_bytes', [1, 4, 8])
def test_replay_retains_complete_records_when_final_gzip_trailer_is_truncated(
    scalar_log: Path, missing_bytes: int
) -> None:
    members = [gzip.compress(line) for line in scalar_log.read_bytes().splitlines(keepends=True)]
    compressed = scalar_log.with_suffix('.jsonl.gz')
    original = b''.join(members[:-1]) + members[-1][:-missing_bytes]
    compressed.write_bytes(original)

    result = replay(compressed)

    assert result['observation_count'] == 4
    assert result['online_comparison'] == {'compared': 4, 'matches': 4, 'mismatches': []}
    assert result['warnings'] == [
        'Recovered truncated final gzip member; tail records lack a complete integrity check'
    ]
    assert compressed.read_bytes() == original


@pytest.mark.parametrize('header_only', [True, False])
def test_replay_recovers_complete_prefix_when_final_gzip_payload_is_truncated(
    scalar_log: Path, header_only: bool
) -> None:
    members = [gzip.compress(line) for line in scalar_log.read_bytes().splitlines(keepends=True)]
    cutoff = 10 if header_only else len(members[-1]) // 2
    compressed = scalar_log.with_suffix('.jsonl.gz')
    compressed.write_bytes(b''.join(members[:-1]) + members[-1][:cutoff])

    result = replay(compressed)

    assert result['observation_count'] == 3
    assert result['online_comparison'] == {'compared': 3, 'matches': 3, 'mismatches': []}
    assert result['warnings'][0] == (
        'Recovered truncated final gzip member; tail records lack a complete integrity check'
    )
    if not header_only:
        assert result['warnings'][1:] == ['Ignored truncated final line 6']


@pytest.mark.parametrize('member_index', [0, 2, -1])
@pytest.mark.parametrize('damage', ['payload', 'checksum'])
def test_replay_rejects_gzip_corruption_even_in_final_member(
    scalar_log: Path, member_index: int, damage: str
) -> None:
    members = [gzip.compress(line) for line in scalar_log.read_bytes().splitlines(keepends=True)]
    damaged = bytearray(members[member_index])
    if damage == 'checksum':
        damaged[-8] ^= 1
    else:
        # DEFLATE block type 3 is reserved, so this is corruption rather than a short write.
        damaged[10] |= 0b110
    members[member_index] = bytes(damaged)
    compressed = scalar_log.with_suffix('.jsonl.gz')
    compressed.write_bytes(b''.join(members))

    with pytest.raises(ValueError, match=r'Invalid.*gzip'):
        replay(compressed)


def test_replay_rejects_truncated_gzip_member_before_later_records(scalar_log: Path) -> None:
    members = [gzip.compress(line) for line in scalar_log.read_bytes().splitlines(keepends=True)]
    members[2] = members[2][:-3]
    compressed = scalar_log.with_suffix('.jsonl.gz')
    compressed.write_bytes(b''.join(members))

    with pytest.raises(ValueError, match=r'Invalid.*gzip'):
        replay(compressed)


@pytest.mark.parametrize('header_size', [1, 2, 3, 4, 9, 10])
def test_replay_recovers_after_partial_valid_gzip_header(
    scalar_log: Path, header_size: int
) -> None:
    compressed = scalar_log.with_suffix('.jsonl.gz')
    following_member = gzip.compress(b'{"kind": "disabled"}\n')
    compressed.write_bytes(gzip.compress(scalar_log.read_bytes()) + following_member[:header_size])

    result = replay(compressed)

    assert result['observation_count'] == 4
    assert result['warnings'] == [
        'Recovered truncated final gzip member; tail records lack a complete integrity check'
    ]


@pytest.mark.parametrize('tail', [b'x', b'\xff', b'\x1f\x00', b'\x1f\x8bx'])
def test_replay_rejects_non_gzip_trailing_bytes(scalar_log: Path, tail: bytes) -> None:
    compressed = scalar_log.with_suffix('.jsonl.gz')
    compressed.write_bytes(gzip.compress(scalar_log.read_bytes()) + tail)

    with pytest.raises(ValueError, match=r'Invalid.*gzip'):
        replay(compressed)


@pytest.mark.parametrize('initial', [None, {'A': 1.0}])
def test_decisive_replay_preserves_scene_initial_and_sampling(
    tmp_path: Path, initial: dict[str, float] | None
) -> None:
    metadata = MapData.tracking_map(6, 1)
    profile = FusionProfile()
    tracker = FusionTracker(metadata, profile, dynamics='decisive', initial=initial)
    observations = [
        FusionObservation('phase', 1.0, phase='DECISIVE_MAP_READY', node_label='A'),
        FusionObservation('phase', 2.0, phase='FORMATION', encounter_id='first'),
        FusionObservation('phase', 3.0, phase='RESULT', encounter_id='first'),
        FusionObservation('action', 4.0, action='encounter_complete', encounter_id='first'),
        FusionObservation('action', 5.0, action='encounter_complete', encounter_id='first'),
        FusionObservation('phase', 6.0, phase='DECISIVE_MAP_READY'),
        FusionObservation('phase', 7.0, phase='FORMATION', encounter_id='second'),
    ]
    sampling = {'pause_weight': 0.95, 'resume_weight': 0.80}
    records = [
        {
            'kind': 'start',
            'schema_version': 4,
            'model_version': MODEL_VERSION,
            'combat_mode': 'decisive',
            'dynamics': 'decisive',
            'initial': initial,
            'sampling': sampling,
            'map': [6, 1],
            'metadata_sha256': metadata.fingerprint,
            'metadata_snapshot': metadata.to_dict(),
            'capabilities': metadata.capabilities,
        },
        {'kind': 'profile', 'profile': asdict(profile)},
    ]
    records.extend(
        {
            'kind': 'observation',
            'observation': asdict(observation),
            'estimate': tracker.observe(observation).as_dict(),
        }
        for observation in observations
    )
    path = tmp_path / 'decisive.jsonl.gz'
    path.write_bytes(gzip.compress(''.join(json.dumps(row) + '\n' for row in records).encode()))
    summary = replay(path, {'1': 'A', '6': 'B'})
    assert summary['initial'] == initial
    assert summary['dynamics'] == 'decisive'
    assert summary['sampling'] == sampling
    assert summary['labels']['top1_correct'] == 2
    assert summary['online_comparison'] == {'compared': 7, 'matches': 7, 'mismatches': []}
