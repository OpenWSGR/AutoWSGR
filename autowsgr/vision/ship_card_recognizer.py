"""Shared ship-card identity port and optional WSG-NCC adapter."""

from __future__ import annotations

import json
import math
import os
import re
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

import numpy as np


if TYPE_CHECKING:
    from autowsgr.types import ShipType


class ShipCardRecognitionError(RuntimeError):
    """Raised when a ship-card recognizer cannot be configured safely."""


@dataclass(frozen=True, slots=True)
class ShipCardIdentity:
    """Canonical identity returned for one complete ship card."""

    ship_id: int
    name: str
    ship_type: ShipType
    confidence: float
    match_key: str
    masked: bool = False


class ShipCardRecognizer(Protocol):
    """Recognize complete RGB ship-card crops in one batch."""

    def recognize(self, images: list[np.ndarray]) -> list[ShipCardIdentity | None]: ...


_SHIP_TYPE_CODES = {
    'aadg': '防驱',
    'ap': '补给',
    'asdg': '导驱',
    'av': '装母',
    'bb': '战列',
    'bbg': '导战',
    'bbv': '航战',
    'bc': '战巡',
    'bg': '大巡',
    'bm': '重炮',
    'ca': '重巡',
    'cav': '航巡',
    'cg': '防巡',
    'cl': '轻巡',
    'clt': '雷巡',
    'cv': '航母',
    'cvl': '轻母',
    'dd': '驱逐',
    'kp': '导巡',
    'nap': '补给',
    'sc': '炮潜',
    'ss': '潜艇',
    'ssg': '导潜',
}


def _read_json(source: Path, member: str | None = None) -> object:
    if member is None:
        return json.loads(source.read_text(encoding='utf-8'))
    with zipfile.ZipFile(source) as archive:
        return json.loads(archive.read(member).decode('utf-8'))


def _canonical_ships(manifest_path: Path) -> dict[int, tuple[str, str, ShipType]]:
    from autowsgr.types import ShipType

    raw = _read_json(manifest_path)
    if not isinstance(raw, dict) or not isinstance(raw.get('ships'), list):
        raise ShipCardRecognitionError('规范舰船 manifest 缺少 ships 列表')
    result: dict[int, tuple[str, str, ShipType]] = {}
    for index, ship in enumerate(raw['ships']):
        if not isinstance(ship, dict):
            raise ShipCardRecognitionError(f'规范舰船 manifest 条目格式错误: {index}')
        ship_id = ship.get('id')
        name = ship.get('name')
        search_name = ship.get('search_name', name)
        type_code = ship.get('ship_type')
        type_value = _SHIP_TYPE_CODES.get(str(type_code).lower())
        if (
            isinstance(ship_id, bool)
            or not isinstance(ship_id, int)
            or ship_id < 0
            or not isinstance(name, str)
            or not name.strip()
            or not isinstance(search_name, str)
            or not search_name.strip()
            or type_value is None
        ):
            raise ShipCardRecognitionError(f'规范舰船 manifest 条目无效: {index}')
        if ship_id in result:
            raise ShipCardRecognitionError(f'规范舰船 manifest ID 重复: {ship_id}')
        result[ship_id] = (name.strip(), search_name.strip(), ShipType(type_value))
    if not result:
        raise ShipCardRecognitionError('规范舰船 manifest 没有有效舰船')
    return result


def _load_metadata(  # noqa: PLR0912
    path: Path,
    *,
    archive_member: str | None = None,
    manifest_path: Path | None = None,
) -> dict[str, ShipCardIdentity]:
    from autowsgr.types import ShipType

    raw = _read_json(path, archive_member)
    if not isinstance(raw, dict):
        raise ShipCardRecognitionError('WSG-NCC metadata 顶层必须是对象')
    canonical = {} if manifest_path is None else _canonical_ships(manifest_path)
    result: dict[str, ShipCardIdentity] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            raise ShipCardRecognitionError('WSG-NCC metadata 条目格式错误')
        ship_id = value.get('ship_id', value.get('shipIndex'))
        if not isinstance(ship_id, int):
            raise ShipCardRecognitionError(f'WSG-NCC metadata 缺少规范身份: {key}')
        name = value.get('name', value.get('title'))
        ship_type_value = value.get('ship_type', value.get('shipType'))
        if ship_type_value is None:
            canonical_identity = canonical.get(ship_id)
            if canonical_identity is None:
                costume_match = re.search(r'(?:^|/)(\d+)_(\d+)(?:/|$)', key.replace('\\', '/'))
                canonical_ship_id = int(costume_match.group(1)) if costume_match else None
                canonical_identity = canonical.get(canonical_ship_id)
                if canonical_identity is None and isinstance(name, str):
                    exact_name_matches = tuple(
                        (candidate_id, identity)
                        for candidate_id, identity in canonical.items()
                        if identity[0] == name.strip()
                    )
                    if len(exact_name_matches) == 1:
                        canonical_ship_id, canonical_identity = exact_name_matches[0]
                if canonical_identity is None:
                    continue
                encoded_costume_id = (
                    int(''.join(costume_match.groups())) if costume_match else ship_id
                )
                if costume_match and ship_id != encoded_costume_id:
                    raise ShipCardRecognitionError(
                        f'WSG-NCC 换装 ID 与资源 key 不一致: {key}/{ship_id}'
                    )
                canonical_name, _canonical_search_name, ship_type = canonical_identity
                ship_id = canonical_ship_id
                name = canonical_name
                result[key.replace('\\', '/')] = ShipCardIdentity(
                    ship_id=ship_id,
                    name=name,
                    ship_type=ship_type,
                    confidence=0.0,
                    match_key=key,
                )
                continue
            canonical_name, _canonical_search_name, ship_type = canonical_identity
            name = canonical_name
        else:
            if not isinstance(name, str) or not name:
                raise ShipCardRecognitionError(f'WSG-NCC metadata 缺少规范身份: {key}')
            try:
                ship_type = ShipType(ship_type_value)
            except (TypeError, ValueError) as exc:
                raise ShipCardRecognitionError(f'WSG-NCC metadata 舰种无效: {key}') from exc
        result[key.replace('\\', '/')] = ShipCardIdentity(
            ship_id=ship_id,
            name=name,
            ship_type=ship_type,
            confidence=0.0,
            match_key=key,
        )
    return result


class WsgNccShipCardRecognizer:
    """Fail-closed adapter around the external ``cascade_ncc`` package.

    The privately licensed codebook and metadata remain external runtime assets
    and are deliberately excluded from this project's distribution.
    """

    _CANDIDATE_COUNT = 5
    _MIN_CONFIDENCE = 0.7
    _DEFAULT_REGION = (0.0, 60.0, 0.0, 100.0)
    _MASKED_REGION = (0.0, 40.0, 0.0, 100.0)
    _MASKED_UNMASK = 0.33

    def __init__(
        self,
        codebook: str | Path | bytes,
        metadata_path: str | Path,
        *,
        metadata_member: str | None = None,
        manifest_path: str | Path | None = None,
        use_gpu: bool = False,
        engine: Any | None = None,
    ) -> None:
        self._metadata = _load_metadata(
            Path(metadata_path),
            archive_member=metadata_member,
            manifest_path=None if manifest_path is None else Path(manifest_path),
        )
        if engine is None:
            try:
                from cascade_ncc import CascadeRecognizer
            except ImportError as exc:
                raise ShipCardRecognitionError(
                    '未安装 WSG-NCC cascade_ncc；请显式提供已授权的运行时包'
                ) from exc
            engine = CascadeRecognizer(
                codebook,
                self._metadata,
                k=self._CANDIDATE_COUNT,
                use_gpu=use_gpu,
                region=self._DEFAULT_REGION,
                min_confidence=self._MIN_CONFIDENCE,
            )
        self._engine = engine

    @staticmethod
    def _validate_image(image: np.ndarray) -> np.ndarray:
        array = np.asarray(image)
        if array.dtype != np.uint8 or array.ndim != 3 or array.shape[2] not in (3, 4):
            raise ShipCardRecognitionError('船卡必须是 HxWx3/4 uint8 RGB/RGBA numpy 数组')
        if array.shape[0] < 2 or array.shape[1] < 2:
            raise ShipCardRecognitionError('船卡裁切尺寸过小')
        return array

    @staticmethod
    def _normalize_match_key(key: object) -> str:
        normalized = str(key).replace('\\', '/')
        gallery_marker = '/gallery/'
        if gallery_marker in normalized:
            return normalized.split(gallery_marker, 1)[1]
        return normalized.lstrip('/')

    def _identity_from_matches(
        self,
        matches: object,
        *,
        masked: bool = False,
    ) -> ShipCardIdentity | None:
        if not isinstance(matches, list) or not matches:
            return None
        for match in matches:
            if not isinstance(match, (list, tuple)) or len(match) not in (3, 4):
                raise ShipCardRecognitionError('WSG-NCC 匹配结果格式错误')
            _value, score, key = match[:3]
            try:
                confidence = float(score)
            except (TypeError, ValueError) as exc:
                raise ShipCardRecognitionError('WSG-NCC 匹配置信度格式错误') from exc
            if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
                raise ShipCardRecognitionError('WSG-NCC 匹配置信度必须是有限的 0..1 数值')
            if confidence < self._MIN_CONFIDENCE:
                continue
            normalized_key = self._normalize_match_key(key)
            metadata = self._metadata.get(normalized_key)
            if metadata is None:
                continue
            return ShipCardIdentity(
                ship_id=metadata.ship_id,
                name=metadata.name,
                ship_type=metadata.ship_type,
                confidence=confidence,
                match_key=normalized_key,
                masked=masked,
            )
        return None

    def recognize(self, images: list[np.ndarray]) -> list[ShipCardIdentity | None]:
        if not images:
            return []
        arrays = [self._validate_image(image) for image in images]
        raw_results = self._engine.recognize(
            arrays,
            k=self._CANDIDATE_COUNT,
            min_confidence=self._MIN_CONFIDENCE,
        )
        if len(raw_results) != len(arrays):
            raise ShipCardRecognitionError('WSG-NCC 返回数量与船卡数量不一致')
        identities = [self._identity_from_matches(matches, masked=False) for matches in raw_results]
        retry_indices = [index for index, identity in enumerate(identities) if identity is None]
        if retry_indices:
            masked_results = self._engine.recognize(
                [arrays[index] for index in retry_indices],
                k=self._CANDIDATE_COUNT,
                min_confidence=self._MIN_CONFIDENCE,
                region=self._MASKED_REGION,
                unmask=self._MASKED_UNMASK,
            )
            if len(masked_results) != len(retry_indices):
                raise ShipCardRecognitionError('WSG-NCC 蒙版重试返回数量与船卡数量不一致')
            for index, matches in zip(retry_indices, masked_results, strict=True):
                identities[index] = self._identity_from_matches(matches, masked=True)
        return identities

    @classmethod
    def from_data_root(
        cls,
        data_root: str | Path,
        *,
        manifest_path: str | Path,
        use_gpu: bool = False,
    ) -> WsgNccShipCardRecognizer:
        root = Path(data_root)
        python_pkg = root / 'python'
        if python_pkg.is_dir() and str(python_pkg) not in sys.path:
            sys.path.insert(0, str(python_pkg))
        if root.is_file() and root.suffix.lower() == '.zip':
            with zipfile.ZipFile(root) as archive:
                try:
                    codebook = archive.read('codebooks/cascade.npz')
                    archive.getinfo('gallery_meta.json')
                except KeyError as exc:
                    raise ShipCardRecognitionError('WSG-NCC data.zip 缺少码本或 metadata') from exc
            return cls(
                codebook,
                root,
                metadata_member='gallery_meta.json',
                manifest_path=manifest_path,
                use_gpu=use_gpu,
            )
        codebook_path = root / 'codebooks' / 'cascade.npz'
        metadata_path = root / 'gallery_meta.json'
        if not codebook_path.is_file() or not metadata_path.is_file():
            raise ShipCardRecognitionError(f'WSG-NCC 数据目录不完整: {root}')
        return cls(
            codebook_path,
            metadata_path,
            manifest_path=manifest_path,
            use_gpu=use_gpu,
        )


def load_default_ship_card_recognizer(*, use_gpu: bool = False) -> WsgNccShipCardRecognizer:
    """Load WSG-NCC runtime assets with the caller's authoritative GPU setting."""
    data_root = os.getenv('AUTOWSGR_WSG_NCC_DATA', '').strip()
    library_root = os.getenv('AUTOWSGR_SHIP_LIBRARY', '').strip()
    if not data_root:
        default_ncc = Path(r'E:\wsgrgui\resource\wsg-ncc')
        if default_ncc.is_dir():
            data_root = str(default_ncc)
        else:
            raise ShipCardRecognitionError('未设置 AUTOWSGR_WSG_NCC_DATA')
    if not library_root:
        default_lib = Path(r'E:\wsgrgui\resource\ship-library')
        if default_lib.is_dir():
            library_root = str(default_lib)
        else:
            raise ShipCardRecognitionError('未设置 AUTOWSGR_SHIP_LIBRARY')
    return WsgNccShipCardRecognizer.from_data_root(
        data_root,
        manifest_path=Path(library_root) / 'manifest.json',
        use_gpu=use_gpu,
    )
