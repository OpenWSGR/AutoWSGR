"""Pure conversion from immutable scan snapshots to intensify domain observations."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol

from autowsgr.ui.intensify_workflow import (
    IntensifyPolicy,
    MaterialInventoryObservation,
    MaterialOccurrence,
    SelectionRef,
    ShipStats,
    TargetObservation,
)
from autowsgr.ui.live_intensify import GridSelectionRef
from autowsgr.ui.material_inventory_scanner import (
    MaterialInventoryScanError,
    MaterialInventorySnapshot,
)
from autowsgr.ui.target_strengthen_max import ShipStrengthenDataResolver


if TYPE_CHECKING:
    from autowsgr.ui.target_inventory_scanner import (
        TargetInventorySnapshot,
        TargetShipSnapshot,
    )


class MaterialContributionResolver(Protocol):
    def supply(self, ship_id: int) -> ShipStats | None: ...


class MaterialRarityResolver(Protocol):
    def rarity(self, ship_id: int) -> int | None: ...


@dataclass(frozen=True, slots=True)
class ShipLibraryRarityResolver:
    """Resolve authoritative ship rarity and type from the canonical manifest."""

    rarity_by_ship_id: dict[int, int]
    ship_type_by_ship_id: dict[int, str]

    @classmethod
    def from_manifest(cls, path: str | Path) -> ShipLibraryRarityResolver:
        raw = json.loads(Path(path).read_text(encoding='utf-8'))
        ships = raw.get('ships') if isinstance(raw, dict) else None
        if not isinstance(ships, list):
            raise TypeError('舰船资源 manifest 缺少 ships 列表')
        rarities: dict[int, int] = {}
        ship_types: dict[int, str] = {}
        for item in ships:
            if not isinstance(item, dict):
                continue
            ship_id = item.get('id')
            rarity = item.get('rarity')
            ship_type = item.get('ship_type')
            if (
                isinstance(ship_id, bool)
                or not isinstance(ship_id, int)
                or isinstance(rarity, bool)
                or not isinstance(rarity, int)
                or not 1 <= rarity <= 6
            ):
                continue
            if ship_id in rarities:
                raise ValueError(f'舰船资源 manifest 规范 ID 重复: {ship_id}')
            rarities[ship_id] = rarity
            if isinstance(ship_type, str) and ship_type.strip():
                ship_types[ship_id] = ship_type.strip().lower()
        return cls(rarities, ship_types)

    def rarity(self, ship_id: int) -> int | None:
        return self.rarity_by_ship_id.get(ship_id)

    def ship_type(self, ship_id: int) -> str | None:
        return self.ship_type_by_ship_id.get(ship_id)


class TargetMaximumResolver(Protocol):
    def maximum(self, ship_id: int) -> ShipStats | None: ...

    def experience_per_level(self, ship_id: int) -> int | None: ...


@dataclass(frozen=True, slots=True)
class TargetCandidatePreview:
    ref: SelectionRef
    ship_id: int
    identity: str
    occurrence: int
    current: ShipStats
    maximum: ShipStats
    deficit: ShipStats
    projected_gains: ShipStats
    projected: ShipStats
    needs_intensify: bool


@dataclass(frozen=True, slots=True)
class MaterialCandidatePreview:
    ref: SelectionRef
    identity: str
    index: int
    contribution: ShipStats
    rarity: int
    requires_confirmation: bool
    eligible: bool
    reason: str


@dataclass(frozen=True, slots=True)
class IntensifyCandidatePreview:
    targets: tuple[TargetCandidatePreview, ...]
    materials: tuple[MaterialCandidatePreview, ...]
    target_revision: str
    material_revision: str
    execution_path: Literal['direct', 'confirmation_required'] | None
    executable: bool = False


def assemble_offline_intensify_preview(
    targets: TargetInventorySnapshot,
    materials: MaterialInventorySnapshot,
    strengthen_path: str | Path,
    manifest_path: str | Path,
    policy: IntensifyPolicy,
    *,
    projected_material_refs: tuple[SelectionRef, ...] = (),
) -> IntensifyCandidatePreview:
    """Assemble one read-only preview from immutable snapshots and explicit data files."""
    strengthen = ShipStrengthenDataResolver.from_source(Path(strengthen_path))
    rarities = ShipLibraryRarityResolver.from_manifest(manifest_path)
    material_observation = material_inventory_observation(materials, strengthen, rarities)
    return intensify_candidate_preview(
        targets,
        material_observation,
        strengthen,
        policy,
        projected_material_refs=projected_material_refs,
    )


def target_observation(snapshot: TargetShipSnapshot) -> TargetObservation:
    """Preserve the exact scanned target occurrence as a domain observation."""
    GridSelectionRef.parse(snapshot.ref, 'target')
    return TargetObservation(
        ref=snapshot.ref,
        identity=snapshot.name,
        level=None,
        stats=snapshot.levels,
    )


def material_inventory_observation(
    snapshot: MaterialInventorySnapshot,
    contributions: MaterialContributionResolver,
    rarities: MaterialRarityResolver,
) -> MaterialInventoryObservation:
    """Join complete card identities with authoritative strengthenSupply data."""
    if not (snapshot.total == len(snapshot.names) == len(snapshot.ship_ids) == len(snapshot.refs)):
        raise MaterialInventoryScanError('素材快照名称、ID、引用和总数不一致')
    parsed = [GridSelectionRef.parse(SelectionRef(value), 'material') for value in snapshot.refs]
    revisions = {item.revision for item in parsed}
    if len(revisions) != 1:
        raise MaterialInventoryScanError('素材快照包含多个 revision')
    occurrences: list[MaterialOccurrence] = []
    for index, (name, ship_id, ref_value) in enumerate(
        zip(snapshot.names, snapshot.ship_ids, snapshot.refs, strict=True)
    ):
        contribution = contributions.supply(ship_id)
        if contribution is None or contribution == ShipStats():
            raise MaterialInventoryScanError(f'素材舰缺少非零 strengthenSupply: {ship_id}/{name}')
        rarity = rarities.rarity(ship_id)
        if isinstance(rarity, bool) or not isinstance(rarity, int) or not 1 <= rarity <= 6:
            raise MaterialInventoryScanError(f'素材舰缺少有效星级: {ship_id}/{name}')
        occurrences.append(
            MaterialOccurrence(
                ref=SelectionRef(ref_value),
                identity=name,
                index=index,
                contribution=contribution,
                rarity=rarity,
            )
        )
    return MaterialInventoryObservation(
        occurrences=tuple(occurrences),
        complete=True,
        revision=revisions.pop(),
    )


def intensify_candidate_preview(
    targets: TargetInventorySnapshot,
    materials: MaterialInventoryObservation,
    maxima: TargetMaximumResolver,
    policy: IntensifyPolicy,
    *,
    projected_material_refs: tuple[SelectionRef, ...] = (),
) -> IntensifyCandidatePreview:
    """Describe exact occurrences and an explicitly selected, non-executable projection."""
    selected_materials = _resolve_projected_materials(
        materials,
        policy,
        projected_material_refs,
    )
    total_contribution = sum(
        (item.contribution for item in selected_materials),
        start=ShipStats(),
    )
    target_candidates: list[TargetCandidatePreview] = []
    for target in targets.targets:
        maximum = maxima.maximum(target.ship_id)
        if maximum is None:
            raise MaterialInventoryScanError(
                f'目标舰缺少 strengthenMax: {target.ship_id}/{target.name}'
            )
        experience_per_level = maxima.experience_per_level(target.ship_id)
        if experience_per_level is None or experience_per_level <= 0:
            raise MaterialInventoryScanError(
                f'目标舰缺少有效每级强化经验: {target.ship_id}/{target.name}'
            )
        deficit = _nonnegative_difference(maximum, target.levels)
        projected_gains = _projected_gains(
            target.levels,
            maximum,
            total_contribution,
            experience_per_level,
        )
        target_candidates.append(
            TargetCandidatePreview(
                ref=target.ref,
                ship_id=target.ship_id,
                identity=target.name,
                occurrence=target.occurrence,
                current=target.levels,
                maximum=maximum,
                deficit=deficit,
                projected_gains=projected_gains,
                projected=target.levels + projected_gains,
                needs_intensify=deficit != ShipStats(),
            )
        )

    material_candidates = tuple(
        MaterialCandidatePreview(
            ref=item.ref,
            identity=item.identity,
            index=item.index,
            contribution=item.contribution,
            rarity=item.rarity,
            requires_confirmation=item.requires_confirmation,
            eligible=item.identity in policy.allowed_material_identities,
            reason=(
                'allowlisted_nonzero_contribution'
                if item.identity in policy.allowed_material_identities
                else 'identity_not_allowlisted'
            ),
        )
        for item in materials.occurrences
    )
    return IntensifyCandidatePreview(
        targets=tuple(target_candidates),
        materials=material_candidates,
        target_revision=targets.revision,
        material_revision=materials.revision,
        execution_path=(
            None
            if not selected_materials
            else (
                'confirmation_required'
                if any(item.requires_confirmation for item in selected_materials)
                else 'direct'
            )
        ),
    )


def _resolve_projected_materials(
    materials: MaterialInventoryObservation,
    policy: IntensifyPolicy,
    refs: tuple[SelectionRef, ...],
) -> tuple[MaterialOccurrence, ...]:
    if policy.maximum_materials is not None and len(refs) > policy.maximum_materials:
        raise MaterialInventoryScanError('预计强化素材超过策略数量上限')
    if len(set(refs)) != len(refs):
        raise MaterialInventoryScanError('预计强化素材包含重复 occurrence 引用')
    by_ref = {item.ref: item for item in materials.occurrences}
    try:
        selected = tuple(by_ref[ref] for ref in refs)
    except KeyError as error:
        raise MaterialInventoryScanError('预计强化素材不属于当前库存 revision') from error
    forbidden = tuple(
        item.identity
        for item in selected
        if item.identity not in policy.allowed_material_identities
    )
    if forbidden:
        raise MaterialInventoryScanError(f'预计强化素材不在显式 allowlist 中: {forbidden}')
    return selected


def _nonnegative_difference(maximum: ShipStats, current: ShipStats) -> ShipStats:
    return ShipStats(
        firepower=max(0, maximum.firepower - current.firepower),
        torpedo=max(0, maximum.torpedo - current.torpedo),
        armor=max(0, maximum.armor - current.armor),
        anti_air=max(0, maximum.anti_air - current.anti_air),
    )


def _projected_gains(
    current: ShipStats,
    maximum: ShipStats,
    contribution: ShipStats,
    experience_per_level: int,
) -> ShipStats:
    return ShipStats(
        firepower=(
            contribution.firepower // experience_per_level
            if current.firepower < maximum.firepower
            else 0
        ),
        torpedo=(
            contribution.torpedo // experience_per_level if current.torpedo < maximum.torpedo else 0
        ),
        armor=(contribution.armor // experience_per_level if current.armor < maximum.armor else 0),
        anti_air=(
            contribution.anti_air // experience_per_level
            if current.anti_air < maximum.anti_air
            else 0
        ),
    )
