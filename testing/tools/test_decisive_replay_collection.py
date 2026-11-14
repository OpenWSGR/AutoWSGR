"""旧固定版本采集可转换回放，但不能把预测标签或停止误当定位与推进证据。"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

import pytest

from tools.decisive.replay_collection import convert_collection, read_snapshot


def _row(sample_id: int, kind: str, **fields: Any) -> dict[str, Any]:
    return {
        'sample_id': sample_id,
        'kind': kind,
        'round': 1,
        'chapter': 6,
        'stage': 1,
        'encounter_id': 'first',
        'recorded_monotonic': float(sample_id),
        'captured_at': float(sample_id),
        'frame_sequence': sample_id,
        'predicted_node': 'J',
        'label_node': None,
        'label_source': None,
        **fields,
    }


def _write(path: Path, rows: list[dict[str, Any]], tail: bytes = b'') -> None:
    path.write_bytes((''.join(json.dumps(row) + '\n' for row in rows)).encode() + tail)


def _known_start() -> list[dict[str, Any]]:
    return [
        _row(1, 'entry_after', label_node='A', label_source='user_confirmed_start_and_entry_stage'),
        _row(2, 'map', raw_node='J'),
        _row(3, 'combat_start'),
    ]


def _completion(offset: int = 4, **fields: Any) -> list[dict[str, Any]]:
    return [
        _row(offset, 'result', **fields),
        _row(offset + 1, 'combat_end', result='success', **fields),
        _row(offset + 2, 'node_result_before', **fields),
        _row(offset + 3, 'node_result_after', phase='ADVANCE_CHOICE', **fields),
    ]


def test_snapshot_skips_entire_unterminated_line_even_if_valid_json(tmp_path: Path) -> None:
    source = tmp_path / 'observations.jsonl'
    tail = json.dumps(_row(2, 'result')).encode()
    _write(source, [_row(1, 'map', raw_node='A')], tail)
    rows, frozen, skipped = read_snapshot(source)
    assert len(rows) == 1
    assert skipped == len(tail)
    assert frozen.endswith(b'\n')
    source.write_bytes(source.read_bytes() + b'\n')
    assert len(read_snapshot(source)[0]) == 2


def test_invalid_complete_line_is_not_silently_ignored(tmp_path: Path) -> None:
    source = tmp_path / 'observations.jsonl'
    source.write_bytes(b'{"kind":\n')
    with pytest.raises(ValueError, match='complete collection line'):
        read_snapshot(source)


def test_direct_combat_without_spot_or_formation_is_missing_and_advances_once(
    tmp_path: Path,
) -> None:
    source = tmp_path / 'observations.jsonl'
    rows = _known_start() + _completion()
    rows += [_row(8, 'node_result_after', phase='ADVANCE_CHOICE')]
    rows += [_row(9, 'map', encounter_id='second', raw_node='B')]
    _write(source, rows)
    original = source.read_bytes()
    report = convert_collection(source, tmp_path / 'replays')
    (stage,) = report['stages']
    assert report['all_replays_match']
    assert report['completed_encounters'] == 1
    assert report['enemy_missing_count'] == 1
    assert stage['enemy_missing'][0]['reason'] == 'direct_combat_without_spot_or_formation'
    assert stage['duplicate_completions_ignored'] == 1
    assert stage['initial'] == {'A': 1.0}
    assert stage['comparison']['mismatches'] == []
    assert not report['live_fusion_control_verified']
    assert source.read_bytes() == original
    again = convert_collection(source, tmp_path / 'replays')
    assert again['source_sha256'] == report['source_sha256']
    assert again['output'] != report['output']


@pytest.mark.parametrize('result', ['SL', 'fight_end', 'dock_full', None, 'unknown'])
def test_unsuccessful_results_do_not_advance(result: str | None, tmp_path: Path) -> None:
    source = tmp_path / 'observations.jsonl'
    rows = _known_start() + _completion()
    rows[4]['result'] = result
    _write(source, rows)
    report = convert_collection(source, tmp_path / 'replays')
    assert report['completed_encounters'] == 0


@pytest.mark.parametrize('last_phase', ['FINISHED', None])
def test_success_followed_by_stop_or_uncommitted_tail_does_not_advance(
    last_phase: str | None, tmp_path: Path
) -> None:
    source = tmp_path / 'observations.jsonl'
    rows = _known_start() + _completion()
    if last_phase is None:
        rows.pop()
    else:
        rows[-1]['phase'] = last_phase
    _write(source, rows)
    report = convert_collection(source, tmp_path / 'replays')
    assert report['completed_encounters'] == 0
    assert report['stages'][0]['uncommitted_success'] == ['first']


def test_later_flow_labels_are_not_initial_conditions_or_node_evidence(tmp_path: Path) -> None:
    source = tmp_path / 'observations.jsonl'
    rows = [
        _row(
            1,
            'map',
            raw_node='A',
            label_node='J',
            label_source='confirmed_start_and_completed_battles',
        ),
        _row(2, 'formation', label_node='A', label_source='user_confirmed_start'),
    ]
    _write(source, rows)
    report = convert_collection(source, tmp_path / 'replays')
    stage = report['stages'][0]
    assert stage['initial'] is None
    assert stage['labels']['status'] == 'unlabelled'
    records = [
        json.loads(line)
        for line in gzip.decompress(Path(stage['replay_log']).read_bytes()).splitlines()
    ]
    observations = [row['observation'] for row in records if row['kind'] == 'observation']
    assert [row['node_label'] for row in observations] == ['A', None]


def test_raw_enemy_slots_and_chinese_fields_survive_conversion(tmp_path: Path) -> None:
    source = tmp_path / 'observations.jsonl'
    enemy = {
        'raw_slots': ['Airfield', 'BB', 'DD', 'BB', 'BC', 'AV'],
        'ships': ['机场', '战列', '驱逐', '战列', '战巡', '装母'],
        'formation': 2,
        'formation_text': '复纵阵',
        'formation_confidence': 0.9,
        'detour': None,
        'detour_score': None,
        'valid_slots': True,
    }
    _write(
        source,
        [
            _row(1, 'map', raw_node='J', label_node='J', label_source='user_confirmed_start'),
            _row(2, 'enemy', observation=enemy),
            _row(3, 'formation'),
        ],
    )
    report = convert_collection(source, tmp_path / 'replays')
    stage = report['stages'][0]
    records = [
        json.loads(line)
        for line in gzip.decompress(Path(stage['replay_log']).read_bytes()).splitlines()
    ]
    assert records[3]['observation']['enemies'] == enemy
    assert stage['native_feedback'] == []
    assert report['enemy_missing_count'] == 0


def test_each_stage_has_its_own_initial_condition_and_clear_is_verified(tmp_path: Path) -> None:
    source = tmp_path / 'observations.jsonl'
    rows = _known_start() + _completion()
    rows += [
        _row(8, 'stage_clear_before', label_node='J'),
        _row(9, 'stage_clear_after', label_node='A', label_source='confirmed_stage_clear'),
        _row(10, 'entry_after', stage=2, label_node='A', label_source='confirmed_stage_clear'),
        _row(11, 'map', stage=2, encounter_id='second-stage', raw_node='A'),
    ]
    _write(source, rows)
    report = convert_collection(source, tmp_path / 'replays')
    first, second = report['stages']
    assert first['stage_clear_confirmed']
    assert first['observation_count'] == 4  # map, result, complete, actual clear
    assert second['initial'] == {'A': 1.0}
    assert second['initial_label_source'] == 'confirmed_stage_clear'
    assert report['all_replays_match']


def test_explicit_stop_blocks_later_completion_of_same_encounter(tmp_path: Path) -> None:
    source = tmp_path / 'observations.jsonl'
    rows = _known_start() + [
        _row(4, 'result'),
        _row(5, 'combat_end', result='success'),
        _row(6, 'stopped'),
        _row(7, 'node_result_before'),
        _row(8, 'node_result_after', phase='ADVANCE_CHOICE'),
    ]
    _write(source, rows)
    assert convert_collection(source, tmp_path / 'replays')['completed_encounters'] == 0


def test_clear_label_cannot_retroactively_initialize_a(tmp_path: Path) -> None:
    source = tmp_path / 'observations.jsonl'
    _write(
        source, [_row(1, 'stage_clear_after', label_node='A', label_source='confirmed_stage_clear')]
    )
    report = convert_collection(source, tmp_path / 'replays')
    assert report['stages'][0]['initial'] is None


def test_archived_but_unused_map_label_does_not_enter_model(tmp_path: Path) -> None:
    source = tmp_path / 'observations.jsonl'
    rows = _known_start()
    rows[1]['used_for_tracking'] = False
    _write(source, rows)
    report = convert_collection(source, tmp_path / 'replays')
    path = Path(report['stages'][0]['replay_log'])
    records = [json.loads(line) for line in gzip.decompress(path.read_bytes()).splitlines()]
    assert records[2]['observation']['node_label'] is None
