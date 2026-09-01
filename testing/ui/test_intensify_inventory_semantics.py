from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from autowsgr.types import ShipType
from autowsgr.ui.intensify_inventory_semantics import (
    ShipLibraryRarityResolver,
    assemble_offline_intensify_preview,
    intensify_candidate_preview,
    material_inventory_observation,
    target_observation,
)
from autowsgr.ui.intensify_workflow import (
    IntensifyPolicy,
    MaterialInventoryObservation,
    MaterialOccurrence,
    SelectionRef,
    ShipStats,
)
from autowsgr.ui.material_inventory_scanner import (
    MaterialInventoryScanError,
    MaterialInventorySnapshot,
)
from autowsgr.ui.target_inventory_scanner import (
    CardRect,
    TargetInventorySnapshot,
    TargetShipSnapshot,
)


if TYPE_CHECKING:
    from pathlib import Path


def _strengthen_record(
    ship_id: int,
    *,
    supply: tuple[int, int, int, int],
    maximum: tuple[int, int, int, int],
    level_up_exp: int = 20,
) -> dict[str, object]:
    return {
        'id': 10_000_000 + ship_id * 100 + 12,
        'title': f'No.{ship_id}',
        'strengthenLevelUpExp': level_up_exp,
        'strengthenSupply': dict(zip(('atk', 'torpedo', 'def', 'airDef'), supply, strict=True)),
        'strengthenMax': dict(zip(('atk', 'torpedo', 'def', 'airDef'), maximum, strict=True)),
    }


@pytest.mark.parametrize(
    ('second_rarity', 'expected_path'),
    [(3, 'direct'), (4, 'confirmation_required')],
)
def test_offline_preview_assembles_explicit_snapshots_and_data_sources(
    tmp_path: Path,
    second_rarity: int,
    expected_path: str,
) -> None:
    target_ref = SelectionRef('target:target-rev:0:0:0:0.1000:0.2000')
    target_snapshot = TargetInventorySnapshot(
        (
            TargetShipSnapshot(
                ref=target_ref,
                ship_id=7,
                name='目标舰',
                ship_type=ShipType.DD,
                levels=ShipStats(armor=4),
                card=CardRect(10, 10, 110, 210),
                visual_hash=1,
                identity_confidence=0.9,
                identity_match_key='gallery/7.png',
                global_index=0,
                occurrence=0,
            ),
        ),
        1,
        True,
        'target-rev',
    )
    material_refs = (
        'material:material-rev:0:0:0:0.1000:0.2000',
        'material:material-rev:0:0:1:0.2000:0.2000',
    )
    material_snapshot = MaterialInventorySnapshot(
        names=('素材甲', '素材乙'),
        ship_ids=(11, 12),
        total=2,
        viewport_count=1,
        refs=material_refs,
    )
    strengthen_path = tmp_path / 'strengthen.json'
    strengthen_path.write_text(
        json.dumps(
            [
                _strengthen_record(7, supply=(1, 1, 1, 1), maximum=(0, 0, 100, 0)),
                _strengthen_record(11, supply=(0, 0, 15, 0), maximum=(0, 0, 20, 0)),
                _strengthen_record(12, supply=(0, 0, 25, 0), maximum=(0, 0, 20, 0)),
            ]
        ),
        encoding='utf-8',
    )
    manifest_path = tmp_path / 'manifest.json'
    manifest_path.write_text(
        json.dumps(
            {
                'ships': [
                    {'id': 11, 'rarity': 3},
                    {'id': 12, 'rarity': second_rarity},
                ]
            }
        ),
        encoding='utf-8',
    )

    preview = assemble_offline_intensify_preview(
        target_snapshot,
        material_snapshot,
        strengthen_path,
        manifest_path,
        IntensifyPolicy(frozenset({'素材甲', '素材乙'}), maximum_materials=2),
        projected_material_refs=tuple(SelectionRef(value) for value in material_refs),
    )

    assert preview.executable is False
    assert preview.target_revision == 'target-rev'
    assert preview.material_revision == 'material-rev'
    assert preview.execution_path == expected_path
    assert [item.rarity for item in preview.materials] == [3, second_rarity]
    assert preview.targets[0].maximum == ShipStats(armor=5)
    assert preview.targets[0].projected_gains == ShipStats(armor=2)
    assert preview.targets[0].projected == ShipStats(armor=6)


def test_offline_preview_rejects_manifest_without_selected_material_rarity(
    tmp_path: Path,
) -> None:
    targets = TargetInventorySnapshot(
        (
            TargetShipSnapshot(
                ref=SelectionRef('target:target-rev:0:0:0:0.1000:0.2000'),
                ship_id=7,
                name='目标舰',
                ship_type=ShipType.DD,
                levels=ShipStats(),
                card=CardRect(10, 10, 110, 210),
                visual_hash=1,
                identity_confidence=0.9,
                identity_match_key='gallery/7.png',
                global_index=0,
                occurrence=0,
            ),
        ),
        1,
        True,
        'target-rev',
    )
    materials = MaterialInventorySnapshot(
        ('素材甲',),
        (11,),
        1,
        1,
        ('material:material-rev:0:0:0:0.1000:0.2000',),
    )
    strengthen_path = tmp_path / 'strengthen.json'
    strengthen_path.write_text(
        json.dumps(
            [
                _strengthen_record(7, supply=(1, 1, 1, 1), maximum=(20, 20, 20, 20)),
                _strengthen_record(11, supply=(1, 0, 0, 0), maximum=(20, 0, 0, 0)),
            ]
        ),
        encoding='utf-8',
    )
    manifest_path = tmp_path / 'manifest.json'
    manifest_path.write_text('{"ships":[]}', encoding='utf-8')

    with pytest.raises(MaterialInventoryScanError, match='缺少有效星级'):
        assemble_offline_intensify_preview(
            targets,
            materials,
            strengthen_path,
            manifest_path,
            IntensifyPolicy(frozenset({'素材甲'})),
        )


def test_target_snapshot_converts_without_copying_selector_state() -> None:
    snapshot = TargetShipSnapshot(
        ref=SelectionRef('target:revision:0:0:0:0.1000:0.2000'),
        ship_id=7,
        name='目标舰',
        ship_type=ShipType.DD,
        levels=ShipStats(1, 2, 3, 4),
        card=CardRect(10, 10, 110, 210),
        visual_hash=1,
        identity_confidence=0.9,
        identity_match_key='gallery/7.png',
    )

    observation = target_observation(snapshot)

    assert observation.ref is snapshot.ref
    assert observation.identity == '目标舰'
    assert observation.stats == ShipStats(1, 2, 3, 4)


def test_material_snapshot_joins_ship_ids_with_authoritative_supply() -> None:
    snapshot = MaterialInventorySnapshot(
        names=('素材甲', '素材乙'),
        ship_ids=(11, 12),
        total=2,
        viewport_count=1,
        refs=(
            'material:revision:0:0:0:0.1000:0.2000',
            'material:revision:0:0:1:0.2000:0.2000',
        ),
    )
    resolver = MagicMock()
    resolver.supply.side_effect = [ShipStats(1, 0, 2, 0), ShipStats(0, 3, 0, 4)]
    rarities = MagicMock()
    rarities.rarity.side_effect = [3, 4]

    observation = material_inventory_observation(snapshot, resolver, rarities)

    assert observation.complete is True
    assert tuple(item.rarity for item in observation.occurrences) == (3, 4)
    assert observation.revision == 'revision'
    assert [item.identity for item in observation.occurrences] == ['素材甲', '素材乙']
    assert [item.contribution for item in observation.occurrences] == [
        ShipStats(1, 0, 2, 0),
        ShipStats(0, 3, 0, 4),
    ]


def test_material_snapshot_rejects_missing_or_zero_supply() -> None:
    snapshot = MaterialInventorySnapshot(
        names=('素材甲',),
        ship_ids=(11,),
        total=1,
        viewport_count=1,
        refs=('material:revision:0:0:0:0.1000:0.2000',),
    )
    resolver = MagicMock()
    resolver.supply.return_value = ShipStats()
    rarities = MagicMock()
    rarities.rarity.return_value = 3

    with pytest.raises(MaterialInventoryScanError, match='非零 strengthenSupply'):
        material_inventory_observation(snapshot, resolver, rarities)


def test_candidate_preview_lists_exact_targets_and_policy_eligible_materials() -> None:
    targets = (
        TargetShipSnapshot(
            ref=SelectionRef('target:target-rev:0:0:0:0.1000:0.2000'),
            ship_id=7,
            name='目标甲',
            ship_type=ShipType.DD,
            levels=ShipStats(1, 2, 3, 4),
            card=CardRect(10, 10, 110, 210),
            visual_hash=1,
            identity_confidence=0.9,
            identity_match_key='gallery/7.png',
            global_index=0,
            occurrence=0,
        ),
        TargetShipSnapshot(
            ref=SelectionRef('target:target-rev:0:0:1:0.2000:0.2000'),
            ship_id=7,
            name='目标甲',
            ship_type=ShipType.DD,
            levels=ShipStats(5, 6, 7, 8),
            card=CardRect(120, 10, 220, 210),
            visual_hash=2,
            identity_confidence=0.9,
            identity_match_key='gallery/7.png',
            global_index=1,
            occurrence=1,
        ),
    )
    target_snapshot = TargetInventorySnapshot(targets, 2, True, 'target-rev')
    material_snapshot = MaterialInventorySnapshot(
        names=('安全素材', '受保护舰'),
        ship_ids=(11, 12),
        total=2,
        viewport_count=1,
        refs=(
            'material:material-rev:0:0:0:0.1000:0.2000',
            'material:material-rev:0:0:1:0.2000:0.2000',
        ),
    )
    resolver = MagicMock()
    resolver.supply.side_effect = [ShipStats(1, 0, 2, 0), ShipStats(3, 0, 0, 4)]
    resolver.maximum.return_value = ShipStats(5, 6, 7, 8)
    resolver.experience_per_level.return_value = 20
    resolver.rarity.return_value = 3
    materials = material_inventory_observation(material_snapshot, resolver, resolver)

    preview = intensify_candidate_preview(
        target_snapshot,
        materials,
        resolver,
        IntensifyPolicy(frozenset({'安全素材'}), maximum_materials=2),
    )

    assert preview.executable is False
    assert preview.target_revision == 'target-rev'
    assert preview.material_revision == 'material-rev'
    assert [item.ref for item in preview.targets] == [item.ref for item in targets]
    assert [item.deficit for item in preview.targets] == [
        ShipStats(4, 4, 4, 4),
        ShipStats(),
    ]
    assert [item.needs_intensify for item in preview.targets] == [True, False]
    assert [item.eligible for item in preview.materials] == [True, False]
    assert [item.rarity for item in preview.materials] == [3, 3]
    assert [item.requires_confirmation for item in preview.materials] == [False, False]
    assert preview.execution_path is None
    assert preview.materials[0].reason == 'allowlisted_nonzero_contribution'
    assert preview.materials[1].reason == 'identity_not_allowlisted'


@pytest.mark.parametrize(
    ('rarities', 'expected_path'),
    [((2, 3), 'direct'), ((3, 4), 'confirmation_required')],
)
def test_candidate_preview_derives_execution_path_from_explicit_materials(
    rarities: tuple[int, int], expected_path: str
) -> None:
    targets = TargetInventorySnapshot(
        (
            TargetShipSnapshot(
                ref=SelectionRef('target:target-rev:0:0:0:0.1000:0.2000'),
                ship_id=7,
                name='目标舰',
                ship_type=ShipType.DD,
                levels=ShipStats(),
                card=CardRect(10, 10, 110, 210),
                visual_hash=1,
                identity_confidence=0.9,
                identity_match_key='gallery/7.png',
                global_index=0,
                occurrence=0,
            ),
        ),
        1,
        True,
        'target-rev',
    )
    materials = MaterialInventoryObservation(
        tuple(
            MaterialOccurrence(
                SelectionRef(f'material:material-rev:0:0:{index}:0.{index + 1}000:0.2000'),
                '安全素材',
                index,
                ShipStats(armor=20),
                rarity=rarity,
            )
            for index, rarity in enumerate(rarities)
        ),
        True,
        'material-rev',
    )
    resolver = MagicMock()
    resolver.maximum.return_value = ShipStats(armor=10)
    resolver.experience_per_level.return_value = 20

    preview = intensify_candidate_preview(
        targets,
        materials,
        resolver,
        IntensifyPolicy(frozenset({'安全素材'}), maximum_materials=2),
        projected_material_refs=tuple(item.ref for item in materials.occurrences),
    )

    assert preview.execution_path == expected_path
    assert [item.rarity for item in preview.materials] == list(rarities)
    assert [item.requires_confirmation for item in preview.materials] == [
        rarity >= 4 for rarity in rarities
    ]


def test_candidate_preview_unlimited_policy_accepts_all_selected_material_refs() -> None:
    target = TargetShipSnapshot(
        ref=SelectionRef('target:target-rev:0:0:0:0.1000:0.2000'),
        ship_id=7,
        name='目标舰',
        ship_type=ShipType.DD,
        levels=ShipStats(),
        card=CardRect(10, 10, 110, 210),
        visual_hash=1,
        identity_confidence=0.9,
        identity_match_key='gallery/7.png',
        global_index=0,
        occurrence=0,
    )
    targets = TargetInventorySnapshot((target,), 1, True, 'target-rev')
    materials = MaterialInventoryObservation(
        tuple(
            MaterialOccurrence(
                SelectionRef(f'material:material-rev:0:0:{index}:0.1000:0.2000'),
                '安全素材',
                index,
                ShipStats(armor=1),
            )
            for index in range(13)
        ),
        True,
        'material-rev',
    )
    resolver = MagicMock()
    resolver.maximum.return_value = ShipStats(armor=13)
    resolver.experience_per_level.return_value = 1

    preview = intensify_candidate_preview(
        targets,
        materials,
        resolver,
        IntensifyPolicy(frozenset({'安全素材'}), maximum_materials=None),
        projected_material_refs=tuple(item.ref for item in materials.occurrences),
    )

    assert preview.targets[0].projected_gains == ShipStats(armor=13)
    assert preview.execution_path == 'direct'


def test_candidate_preview_fails_closed_when_target_maximum_is_missing() -> None:
    target = TargetShipSnapshot(
        ref=SelectionRef('target:target-rev:0:0:0:0.1000:0.2000'),
        ship_id=7,
        name='目标舰',
        ship_type=ShipType.DD,
        levels=ShipStats(),
        card=CardRect(10, 10, 110, 210),
        visual_hash=1,
        identity_confidence=0.9,
        identity_match_key='gallery/7.png',
        global_index=0,
        occurrence=0,
    )
    targets = TargetInventorySnapshot((target,), 1, True, 'target-rev')
    materials = MaterialInventorySnapshot(
        ('安全素材',),
        (11,),
        1,
        1,
        ('material:material-rev:0:0:0:0.1000:0.2000',),
    )
    contribution_resolver = MagicMock()
    contribution_resolver.supply.return_value = ShipStats(1, 0, 0, 0)
    contribution_resolver.rarity.return_value = 3
    maximum_resolver = MagicMock()
    maximum_resolver.maximum.return_value = None

    with pytest.raises(MaterialInventoryScanError, match='缺少 strengthenMax'):
        intensify_candidate_preview(
            targets,
            material_inventory_observation(materials, contribution_resolver, contribution_resolver),
            maximum_resolver,
            IntensifyPolicy(frozenset({'安全素材'})),
        )


def test_projected_gains_sum_supply_then_floor_and_allow_one_step_overflow() -> None:
    target = TargetShipSnapshot(
        ref=SelectionRef('target:target-rev:0:0:0:0.1000:0.2000'),
        ship_id=7,
        name='目标舰',
        ship_type=ShipType.DD,
        levels=ShipStats(4, 5, 5, 8),
        card=CardRect(10, 10, 110, 210),
        visual_hash=1,
        identity_confidence=0.9,
        identity_match_key='gallery/7.png',
        global_index=0,
        occurrence=0,
    )
    targets = TargetInventorySnapshot((target,), 1, True, 'target-rev')
    materials = MaterialInventoryObservation(
        (
            MaterialOccurrence(
                SelectionRef('material:material-rev:0:0:0:0.1000:0.2000'),
                '安全素材',
                0,
                ShipStats(15, 20, 39, 25),
            ),
            MaterialOccurrence(
                SelectionRef('material:material-rev:0:0:1:0.2000:0.2000'),
                '安全素材',
                1,
                ShipStats(15, 20, 1, 25),
            ),
        ),
        True,
        'material-rev',
    )
    resolver = MagicMock()
    resolver.maximum.return_value = ShipStats(5, 5, 5, 10)
    resolver.experience_per_level.return_value = 20

    preview = intensify_candidate_preview(
        targets,
        materials,
        resolver,
        IntensifyPolicy(frozenset({'安全素材'}), maximum_materials=2),
        projected_material_refs=tuple(item.ref for item in materials.occurrences),
    )

    candidate = preview.targets[0]
    assert candidate.projected_gains == ShipStats(1, 0, 0, 2)
    assert candidate.projected == ShipStats(5, 5, 5, 10)


def test_projected_gain_may_exceed_maximum_when_attribute_started_unfilled() -> None:
    target = TargetShipSnapshot(
        ref=SelectionRef('target:target-rev:0:0:0:0.1000:0.2000'),
        ship_id=7,
        name='目标舰',
        ship_type=ShipType.DD,
        levels=ShipStats(4, 0, 0, 0),
        card=CardRect(10, 10, 110, 210),
        visual_hash=1,
        identity_confidence=0.9,
        identity_match_key='gallery/7.png',
        global_index=0,
        occurrence=0,
    )
    targets = TargetInventorySnapshot((target,), 1, True, 'target-rev')
    materials = MaterialInventoryObservation(
        (
            MaterialOccurrence(
                SelectionRef('material:material-rev:0:0:0:0.1000:0.2000'),
                '安全素材',
                0,
                ShipStats(firepower=40),
            ),
        ),
        True,
        'material-rev',
    )
    resolver = MagicMock()
    resolver.maximum.return_value = ShipStats(firepower=5)
    resolver.experience_per_level.return_value = 20

    candidate = intensify_candidate_preview(
        targets,
        materials,
        resolver,
        IntensifyPolicy(frozenset({'安全素材'})),
        projected_material_refs=(materials.occurrences[0].ref,),
    ).targets[0]

    assert candidate.projected_gains.firepower == 2
    assert candidate.projected.firepower == 6


def test_ship_library_rarity_resolver_reads_canonical_manifest(tmp_path: Path) -> None:
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(
        '{"ships":[{"id":11,"rarity":3,"ship_type":"dd"},{"id":12,"rarity":4,"ship_type":"bb"}]}',
        encoding='utf-8',
    )

    resolver = ShipLibraryRarityResolver.from_manifest(manifest)

    assert resolver.rarity(11) == 3
    assert resolver.rarity(12) == 4
    assert resolver.ship_type(11) == 'dd'
    assert resolver.ship_type(12) == 'bb'
    assert resolver.rarity(13) is None
