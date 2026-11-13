"""回放命令行入口对 gzip 压缩标量日志的透明解压。"""

from __future__ import annotations

import gzip
import json
from dataclasses import asdict
from typing import TYPE_CHECKING

from autowsgr.combat.node_fusion import MODEL_VERSION, FusionProfile
from autowsgr.combat.node_fusion.map import TrackingMap

from tools.node_fusion.replay import main


if TYPE_CHECKING:
    from pathlib import Path


def _write_log(path: Path) -> None:
    metadata = TrackingMap.load(2, 1)
    profile = FusionProfile(min_travel_seconds=None)
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
    with gzip.open(path, 'wt', encoding='utf-8') as stream:
        for row in records:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')


def test_cli_replays_gzip_log_without_leaving_temp_files(tmp_path: Path) -> None:
    gz_log = tmp_path / 'sortie.jsonl.gz'
    _write_log(gz_log)
    assert gz_log.read_bytes()[:2] == b'\x1f\x8b'

    output = tmp_path / 'summary.json'
    assert main([str(gz_log), '--output', str(output)]) == 0

    summary = json.loads(output.read_text(encoding='utf-8'))
    assert summary['metadata_verified']
    assert summary['observation_count'] == 0
    # 解压产生的临时明文已清理，目录中只留下输入与输出。
    assert {item.name for item in tmp_path.iterdir()} == {gz_log.name, output.name}

    # 压缩入口与明文入口给出一致的摘要（仅 source 记录的文件名不同）。
    plain_log = tmp_path / 'sortie.jsonl'
    plain_log.write_bytes(gzip.decompress(gz_log.read_bytes()))
    plain_output = tmp_path / 'summary_plain.json'
    assert main([str(plain_log), '--output', str(plain_output)]) == 0
    plain_summary = json.loads(plain_output.read_text(encoding='utf-8'))
    summary.pop('source')
    plain_summary.pop('source')
    assert plain_summary == summary
