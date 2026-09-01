from __future__ import annotations

import json
import sys
import types
import zipfile
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import numpy as np
import pytest
from PIL import Image

from autowsgr.types import ShipType
from autowsgr.vision.ship_card_recognizer import (
    ShipCardRecognitionError,
    WsgNccShipCardRecognizer,
)


if TYPE_CHECKING:
    from pathlib import Path


def _metadata(tmp_path: Path) -> Path:
    path = tmp_path / 'gallery_meta.json'
    path.write_text(
        json.dumps(
            {
                '1/84/XM_NORMAL_84.png': {
                    'ship_id': 84,
                    'name': '天后',
                    'ship_type': '驱逐',
                }
            },
            ensure_ascii=False,
        ),
        encoding='utf-8',
    )
    return path


def _manifest(tmp_path: Path) -> Path:
    path = tmp_path / 'manifest.json'
    path.write_text(
        json.dumps(
            {
                'ships': [
                    {'id': 84, 'name': '天后', 'ship_type': 'dd'},
                    {'id': 83, 'name': '标枪', 'ship_type': 'dd'},
                ]
            },
            ensure_ascii=False,
        ),
        encoding='utf-8',
    )
    return path


def test_wsg_ncc_adapter_maps_confident_unique_match(tmp_path: Path) -> None:
    engine = MagicMock()
    engine.recognize.return_value = [
        [
            (None, 0.93, '1/84/XM_NORMAL_84.png'),
            (None, 0.60, '1/83/XM_NORMAL_83.png'),
        ]
    ]
    recognizer = WsgNccShipCardRecognizer('unused', _metadata(tmp_path), engine=engine)

    result = recognizer.recognize([np.zeros((405, 192, 3), dtype=np.uint8)])

    assert result[0] is not None
    assert result[0].ship_id == 84
    assert result[0].name == '天后'
    assert result[0].ship_type is ShipType.DD
    assert result[0].confidence == pytest.approx(0.93)
    engine.recognize.assert_called_once()
    assert engine.recognize.call_args.kwargs == {'k': 5, 'min_confidence': 0.7}


def test_wsg_ncc_adapter_accepts_build_metadata_match_tuple(tmp_path: Path) -> None:
    engine = MagicMock()
    engine.recognize.return_value = [[(None, 0.93, '1/84/XM_NORMAL_84.png', {'shipIndex': 84})]]
    recognizer = WsgNccShipCardRecognizer('unused', _metadata(tmp_path), engine=engine)

    identity = recognizer.recognize([np.zeros((405, 192, 3), dtype=np.uint8)])[0]

    assert identity is not None
    assert identity.ship_id == 84


def test_wsg_ncc_adapter_skips_noncanonical_top_match(tmp_path: Path) -> None:
    engine = MagicMock()
    engine.recognize.return_value = [
        [
            (None, 0.87, '1EB/496_1/XM_BROKEN_496_1.png', {'shipIndex': 4961}),
            (None, 0.82, '1/84/XM_NORMAL_84.png', {'shipIndex': 84}),
        ]
    ]
    recognizer = WsgNccShipCardRecognizer('unused', _metadata(tmp_path), engine=engine)

    identity = recognizer.recognize([np.zeros((405, 192, 3), dtype=np.uint8)])[0]

    assert identity is not None
    assert identity.ship_id == 84


def test_wsg_ncc_adapter_retries_all_unresolved_normal_results_with_masked_parameters(
    tmp_path: Path,
) -> None:
    engine = MagicMock()
    engine.recognize.side_effect = [
        [
            [(None, 0.93, '1/84/XM_NORMAL_84.png')],
            [],
            [(None, 0.91, 'unknown.png')],
        ],
        [
            [(None, 0.95, '1/84/XM_NORMAL_84.png')],
            [(None, 0.94, '1/84/XM_NORMAL_84.png')],
        ],
    ]
    recognizer = WsgNccShipCardRecognizer('unused', _metadata(tmp_path), engine=engine)
    images = [np.zeros((405, 192, 3), dtype=np.uint8) for _ in range(3)]

    result = recognizer.recognize(images)

    assert [item.ship_id if item is not None else None for item in result] == [84, 84, 84]
    assert engine.recognize.call_count == 2
    assert engine.recognize.call_args_list[0].args == (images,)
    assert engine.recognize.call_args_list[1].args == ([images[1], images[2]],)
    assert engine.recognize.call_args_list[1].kwargs == {
        'k': 5,
        'min_confidence': 0.7,
        'region': (0.0, 40.0, 0.0, 100.0),
        'unmask': 0.33,
    }


def test_wsg_ncc_adapter_keeps_none_when_masked_retry_is_still_empty(tmp_path: Path) -> None:
    engine = MagicMock()
    engine.recognize.side_effect = [[[]], [[]]]
    recognizer = WsgNccShipCardRecognizer('unused', _metadata(tmp_path), engine=engine)

    assert recognizer.recognize([np.zeros((405, 192, 3), dtype=np.uint8)]) == [None]


@pytest.mark.parametrize('matches', [[], [(None, 0.99, 'unknown.png')]])
def test_wsg_ncc_adapter_fails_closed_for_empty_or_unknown_match(
    tmp_path: Path,
    matches: list[tuple[None, float, str]],
) -> None:
    engine = MagicMock()
    engine.recognize.return_value = [matches]
    recognizer = WsgNccShipCardRecognizer('unused', _metadata(tmp_path), engine=engine)

    assert recognizer.recognize([np.zeros((405, 192, 3), dtype=np.uint8)]) == [None]


@pytest.mark.parametrize('score', [float('nan'), float('inf'), -0.1, 1.1, 'bad'])
def test_wsg_ncc_adapter_rejects_malformed_confidence(tmp_path: Path, score: object) -> None:
    engine = MagicMock()
    engine.recognize.return_value = [[(None, score, '1/84/XM_NORMAL_84.png')]]
    recognizer = WsgNccShipCardRecognizer('unused', _metadata(tmp_path), engine=engine)

    with pytest.raises(ShipCardRecognitionError, match='置信度'):
        recognizer.recognize([np.zeros((405, 192, 3), dtype=np.uint8)])


def test_wsg_ncc_adapter_rejects_engine_score_below_threshold(tmp_path: Path) -> None:
    engine = MagicMock()
    engine.recognize.return_value = [[(None, 0.69, '1/84/XM_NORMAL_84.png')]]
    recognizer = WsgNccShipCardRecognizer('unused', _metadata(tmp_path), engine=engine)

    assert recognizer.recognize([np.zeros((405, 192, 3), dtype=np.uint8)]) == [None]


def test_wsg_ncc_adapter_rejects_non_uint8_or_bgr_ambiguity(tmp_path: Path) -> None:
    recognizer = WsgNccShipCardRecognizer('unused', _metadata(tmp_path), engine=MagicMock())
    with pytest.raises(ShipCardRecognitionError, match='uint8 RGB/RGBA'):
        recognizer.recognize([np.zeros((10, 10, 3), dtype=np.float32)])


def test_wsg_ncc_adapter_normalizes_absolute_gallery_key(tmp_path: Path) -> None:
    engine = MagicMock()
    engine.recognize.return_value = [
        [
            (None, 0.93, '/developer/data/groups/group1/gallery/1/84/XM_NORMAL_84.png'),
            (None, 0.60, '/developer/data/groups/group1/gallery/1/83/XM_NORMAL_83.png'),
        ]
    ]
    recognizer = WsgNccShipCardRecognizer('unused', _metadata(tmp_path), engine=engine)

    identity = recognizer.recognize([np.zeros((405, 192, 3), dtype=np.uint8)])[0]

    assert identity is not None
    assert identity.ship_id == 84
    assert identity.match_key == '1/84/XM_NORMAL_84.png'


def test_wsg_ncc_adapter_uses_library_top_match(tmp_path: Path) -> None:
    metadata = tmp_path / 'gallery_meta.json'
    metadata.write_text(
        json.dumps(
            {
                '1/84/XM_NORMAL_84.png': {
                    'ship_id': 84,
                    'name': '天后',
                    'ship_type': '驱逐',
                },
                '1/84_1/XM_NORMAL_84_1.png': {
                    'ship_id': 84,
                    'name': '天后',
                    'ship_type': '驱逐',
                },
                '1/83/XM_NORMAL_83.png': {
                    'ship_id': 83,
                    'name': '标枪',
                    'ship_type': '驱逐',
                },
            },
            ensure_ascii=False,
        ),
        encoding='utf-8',
    )
    engine = MagicMock()
    engine.recognize.return_value = [
        [
            (None, 0.93, '1/84/XM_NORMAL_84.png'),
            (None, 0.93, '1/84_1/XM_NORMAL_84_1.png'),
            (None, 0.60, '1/83/XM_NORMAL_83.png'),
        ]
    ]
    recognizer = WsgNccShipCardRecognizer('unused', metadata, engine=engine)

    identity = recognizer.recognize([np.zeros((405, 192, 3), dtype=np.uint8)])[0]

    assert identity is not None
    assert identity.ship_id == 84


def test_wsg_ncc_adapter_enriches_private_metadata_from_manifest(tmp_path: Path) -> None:
    metadata = tmp_path / 'gallery_meta.json'
    metadata.write_text(
        json.dumps(
            {
                '1/84/XM_NORMAL_84.png': {'shipIndex': 84, 'title': '天后'},
            },
            ensure_ascii=False,
        ),
        encoding='utf-8',
    )
    engine = MagicMock()
    engine.recognize.return_value = [
        [
            (None, 0.93, '1/84/XM_NORMAL_84.png'),
            (None, 0.60, '1/9999/XM_NORMAL_9999.png'),
        ]
    ]
    recognizer = WsgNccShipCardRecognizer(
        'unused',
        metadata,
        manifest_path=_manifest(tmp_path),
        engine=engine,
    )

    identity = recognizer.recognize([np.zeros((405, 192, 3), dtype=np.uint8)])[0]

    assert identity is not None
    assert identity.ship_id == 84
    assert identity.name == '天后'
    assert identity.ship_type is ShipType.DD


def test_wsg_ncc_adapter_maps_costume_identity_to_canonical_ship(tmp_path: Path) -> None:
    metadata = tmp_path / 'gallery_meta.json'
    metadata.write_text(
        json.dumps(
            {
                '1/84_1/XM_NORMAL_84_1.png': {'shipIndex': 841, 'title': '天后'},
            },
            ensure_ascii=False,
        ),
        encoding='utf-8',
    )
    engine = MagicMock()
    engine.recognize.return_value = [[(None, 0.93, '1/84_1/XM_NORMAL_84_1.png')]]
    recognizer = WsgNccShipCardRecognizer(
        'unused',
        metadata,
        manifest_path=_manifest(tmp_path),
        engine=engine,
    )

    identity = recognizer.recognize([np.zeros((405, 192, 3), dtype=np.uint8)])[0]

    assert identity is not None
    assert identity.ship_id == 84
    assert identity.name == '天后'
    assert identity.ship_type is ShipType.DD


def test_wsg_ncc_adapter_uses_costume_key_when_title_is_legacy_alias(tmp_path: Path) -> None:
    metadata = tmp_path / 'gallery_meta.json'
    metadata.write_text(
        json.dumps(
            {'1/84_1/XM_NORMAL_84_1.png': {'shipIndex': 841, 'title': '标枪'}},
            ensure_ascii=False,
        ),
        encoding='utf-8',
    )

    engine = MagicMock()
    engine.recognize.return_value = [[(None, 0.93, '1/84_1/XM_NORMAL_84_1.png')]]
    recognizer = WsgNccShipCardRecognizer(
        'unused',
        metadata,
        manifest_path=_manifest(tmp_path),
        engine=engine,
    )

    identity = recognizer.recognize([np.zeros((405, 192, 3), dtype=np.uint8)])[0]

    assert identity is not None
    assert identity.ship_id == 84
    assert identity.name == '天后'


def test_wsg_ncc_metadata_rejects_costume_id_mismatching_resource_key(tmp_path: Path) -> None:
    metadata = tmp_path / 'gallery_meta.json'
    metadata.write_text(
        json.dumps({'1/84_1/XM_NORMAL_84_1.png': {'shipIndex': 842, 'title': '天后'}}),
        encoding='utf-8',
    )

    with pytest.raises(ShipCardRecognitionError, match='换装 ID 与资源 key 不一致'):
        WsgNccShipCardRecognizer(
            'unused',
            metadata,
            manifest_path=_manifest(tmp_path),
            engine=MagicMock(),
        )


def test_wsg_ncc_adapter_maps_special_identity_by_unique_exact_canonical_name(
    tmp_path: Path,
) -> None:
    metadata = tmp_path / 'gallery_meta.json'
    metadata.write_text(
        json.dumps({'1/8084/XM_NORMAL_8084.png': {'shipIndex': 8084, 'title': '天后'}}),
        encoding='utf-8',
    )
    engine = MagicMock()
    engine.recognize.return_value = [[(None, 0.93, '1/8084/XM_NORMAL_8084.png')]]
    recognizer = WsgNccShipCardRecognizer(
        'unused',
        metadata,
        manifest_path=_manifest(tmp_path),
        engine=engine,
    )

    identity = recognizer.recognize([np.zeros((405, 192, 3), dtype=np.uint8)])[0]

    assert identity is not None
    assert identity.ship_id == 84
    assert identity.name == '天后'


@pytest.mark.parametrize('title', [None, '未知'])
def test_wsg_ncc_metadata_ignores_non_ship_gallery_entries(
    tmp_path: Path,
    title: str | None,
) -> None:
    metadata = tmp_path / 'gallery_meta.json'
    metadata.write_text(
        json.dumps(
            {
                '1/9998/XM_NORMAL_9998.png': {'shipIndex': 9998, 'title': title},
                '1/84/XM_NORMAL_84.png': {'shipIndex': 84, 'title': '天后'},
            },
            ensure_ascii=False,
        ),
        encoding='utf-8',
    )
    engine = MagicMock()
    engine.recognize.return_value = [
        [
            (None, 0.95, '1/9998/XM_NORMAL_9998.png'),
            (None, 0.93, '1/84/XM_NORMAL_84.png'),
        ]
    ]
    recognizer = WsgNccShipCardRecognizer(
        'unused',
        metadata,
        manifest_path=_manifest(tmp_path),
        engine=engine,
    )

    identity = recognizer.recognize([np.zeros((405, 192, 3), dtype=np.uint8)])[0]

    assert identity is not None
    assert identity.ship_id == 84


def test_wsg_ncc_metadata_ignores_identity_missing_from_manifest(tmp_path: Path) -> None:
    metadata = tmp_path / 'gallery_meta.json'
    metadata.write_text(
        json.dumps(
            {
                '1/9999/XM_NORMAL_9999.png': {
                    'shipIndex': 9999,
                    'title': '调谐舰Ⅳ型',
                }
            },
            ensure_ascii=False,
        ),
        encoding='utf-8',
    )
    engine = MagicMock()
    engine.recognize.return_value = [[(None, 0.99, '1/9999/XM_NORMAL_9999.png')]]
    recognizer = WsgNccShipCardRecognizer(
        'unused',
        metadata,
        manifest_path=_manifest(tmp_path),
        engine=engine,
    )

    assert recognizer.recognize([np.zeros((405, 192, 3), dtype=np.uint8)]) == [None]


def test_wsg_ncc_data_directory_loader_adds_bundled_python_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / 'wsg-ncc'
    python_root = data_root / 'python'
    codebook_path = data_root / 'codebooks' / 'cascade.npz'
    metadata_path = data_root / 'gallery_meta.json'
    python_root.mkdir(parents=True)
    codebook_path.parent.mkdir(parents=True)
    codebook_path.write_bytes(b'codebook')
    metadata_path.write_text(
        json.dumps({'1/84/XM_NORMAL_84.png': {'shipIndex': 84, 'title': '天后'}}),
        encoding='utf-8',
    )
    cascade = MagicMock(return_value=MagicMock())
    cascade_module = types.ModuleType('cascade_ncc')
    cascade_module.CascadeRecognizer = cascade
    monkeypatch.setitem(sys.modules, 'cascade_ncc', cascade_module)
    monkeypatch.setattr(sys, 'path', [entry for entry in sys.path if entry != str(python_root)])

    WsgNccShipCardRecognizer.from_data_root(
        data_root,
        manifest_path=_manifest(tmp_path),
    )

    assert sys.path[0] == str(python_root)
    assert cascade.call_args.args[0] == codebook_path


def test_wsg_ncc_data_zip_loader_reads_codebook_and_metadata(tmp_path: Path) -> None:
    archive_path = tmp_path / 'data.zip'
    with zipfile.ZipFile(archive_path, 'w') as archive:
        archive.writestr('codebooks/cascade.npz', b'codebook')
        archive.writestr(
            'gallery_meta.json',
            json.dumps({'1/84/XM_NORMAL_84.png': {'shipIndex': 84, 'title': '天后'}}),
        )
    engine = MagicMock()
    with pytest.MonkeyPatch.context() as monkeypatch:
        cascade = MagicMock(return_value=engine)
        cascade_module = types.ModuleType('cascade_ncc')
        cascade_module.CascadeRecognizer = cascade
        monkeypatch.setitem(sys.modules, 'cascade_ncc', cascade_module)
        WsgNccShipCardRecognizer.from_data_root(
            archive_path,
            manifest_path=_manifest(tmp_path),
        )

    assert cascade.call_args.args[0] == b'codebook'
    assert set(cascade.call_args.args[1]) == {'1/84/XM_NORMAL_84.png'}
    assert cascade.call_args.kwargs == {
        'k': 5,
        'use_gpu': False,
        'region': (0.0, 60.0, 0.0, 100.0),
        'min_confidence': 0.7,
    }


def test_wsg_ncc_real_cpu_engine_rejects_low_confidence_rgb_numpy_card(
    tmp_path: Path,
) -> None:
    cascade_ncc = pytest.importorskip('cascade_ncc')
    gallery = tmp_path / 'gallery'
    first_dir = gallery / '84'
    second_dir = gallery / '83'
    first_dir.mkdir(parents=True)
    second_dir.mkdir(parents=True)
    first = np.random.RandomState(84).randint(0, 256, (240, 124, 3), dtype=np.uint8)
    second = np.random.RandomState(83).randint(0, 256, (240, 124, 3), dtype=np.uint8)
    first_path = first_dir / 'XM_NORMAL_84.png'
    second_path = second_dir / 'XM_NORMAL_83.png'
    Image.fromarray(first).save(first_path)
    Image.fromarray(second).save(second_path)
    codebook_path = tmp_path / 'cards.npz'
    cascade_ncc.build_cascade_codebook(
        [first_path, second_path],
        top_fraction=0.6,
        cache_path=codebook_path,
    )
    engine = cascade_ncc.CascadeRecognizer(
        codebook_path,
        k=2,
        use_gpu=False,
        region=(0, 60, 0, 100),
        min_confidence=0.7,
    )
    metadata = tmp_path / 'gallery_meta.json'
    metadata.write_text(
        json.dumps(
            {
                '84/XM_NORMAL_84.png': {
                    'ship_id': 84,
                    'name': '天后',
                    'ship_type': '驱逐',
                },
                '83/XM_NORMAL_83.png': {
                    'ship_id': 83,
                    'name': '标枪',
                    'ship_type': '驱逐',
                },
            },
            ensure_ascii=False,
        ),
        encoding='utf-8',
    )
    recognizer = WsgNccShipCardRecognizer(
        'unused',
        metadata,
        engine=engine,
    )

    identity = recognizer.recognize([first])[0]

    assert identity is None
