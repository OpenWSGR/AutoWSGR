from __future__ import annotations

from autowsgr.ui.intensify_planner import (
    IntensifyPlanningTarget,
    plan_ordered_intensify_batches,
)
from autowsgr.ui.intensify_workflow import (
    IntensifyPolicy,
    MaterialInventoryObservation,
    MaterialOccurrence,
    SelectionRef,
    ShipStats,
    TargetObservation,
)


def _material(
    index: int,
    identity: str,
    contribution: ShipStats,
    *,
    rarity: int = 1,
) -> MaterialOccurrence:
    return MaterialOccurrence(
        SelectionRef(f'material:{index}'),
        identity,
        index,
        contribution,
        rarity,
    )


def _target(index: int, required: ShipStats) -> IntensifyPlanningTarget:
    return IntensifyPlanningTarget(
        TargetObservation(SelectionRef(f'target:{index}'), f'目标{index}', None, ShipStats()),
        index,
        required,
    )


def _inventory(*materials: MaterialOccurrence) -> MaterialInventoryObservation:
    return MaterialInventoryObservation(materials, True, 'material-revision')


def test_planner_uses_duplicate_identity_occurrences_at_most_once() -> None:
    result = plan_ordered_intensify_batches(
        (_target(0, ShipStats(armor=4)), _target(1, ShipStats(armor=2))),
        _inventory(
            _material(0, '同名素材', ShipStats(armor=2)),
            _material(1, '同名素材', ShipStats(armor=2)),
            _material(2, '同名素材', ShipStats(armor=2)),
        ),
        IntensifyPolicy(frozenset({'同名素材'}), maximum_materials=2),
    )

    refs = [item.ref for batch in result.batches for item in batch.materials]
    assert len(refs) == len(set(refs)) == 3
    assert [len(batch.materials) for batch in result.batches] == [2, 1]
    assert result.remaining_materials == ()


def test_planner_skips_full_targets_and_excludes_high_rarity_or_protected_materials() -> None:
    result = plan_ordered_intensify_batches(
        (_target(0, ShipStats()), _target(1, ShipStats(firepower=2))),
        _inventory(
            _material(0, '允许', ShipStats(firepower=2)),
            _material(1, '允许', ShipStats(firepower=9), rarity=4),
            _material(2, '受保护', ShipStats(firepower=9)),
        ),
        IntensifyPolicy(frozenset({'允许'}), maximum_materials=3),
    )

    assert [batch.target_index for batch in result.batches] == [1]
    assert [item.ref.value for item in result.batches[0].materials] == ['material:0']
    assert [item.identity for item in result.remaining_materials] == ['允许', '受保护']
    assert [item.index for item in result.remaining_materials] == [0, 1]


def test_planner_prefers_smallest_complete_combination_then_stable_order() -> None:
    inventory = _inventory(
        _material(0, '允许', ShipStats(armor=2)),
        _material(1, '允许', ShipStats(armor=2)),
        _material(2, '允许', ShipStats(armor=4)),
        _material(3, '允许', ShipStats(armor=4)),
    )
    policy = IntensifyPolicy(frozenset({'允许'}), maximum_materials=3)

    first = plan_ordered_intensify_batches((_target(0, ShipStats(armor=4)),), inventory, policy)
    second = plan_ordered_intensify_batches((_target(0, ShipStats(armor=4)),), inventory, policy)

    assert first == second
    assert [item.index for item in first.batches[0].materials] == [2]


def test_planner_keeps_one_target_in_one_batch_when_within_capacity() -> None:
    result = plan_ordered_intensify_batches(
        (_target(0, ShipStats(armor=6)),),
        _inventory(
            _material(0, '允许', ShipStats(armor=2)),
            _material(1, '允许', ShipStats(armor=2)),
            _material(2, '允许', ShipStats(armor=2)),
        ),
        IntensifyPolicy(frozenset({'允许'}), maximum_materials=3),
    )

    assert len(result.batches) == 1
    assert [item.index for item in result.batches[0].materials] == [0, 1, 2]


def test_planner_splits_only_when_target_requires_more_than_batch_capacity() -> None:
    result = plan_ordered_intensify_batches(
        (_target(0, ShipStats(armor=6)),),
        _inventory(
            _material(0, '允许', ShipStats(armor=2)),
            _material(1, '允许', ShipStats(armor=2)),
            _material(2, '允许', ShipStats(armor=2)),
        ),
        IntensifyPolicy(frozenset({'允许'}), maximum_materials=2),
    )

    assert [len(batch.materials) for batch in result.batches] == [2, 1]
    assert [item.index for batch in result.batches for item in batch.materials] == [0, 1, 2]


def test_planner_preserves_and_reindexes_remaining_material_order() -> None:
    result = plan_ordered_intensify_batches(
        (_target(0, ShipStats(torpedo=3)),),
        _inventory(
            _material(0, '保留甲', ShipStats(armor=1)),
            _material(1, '使用', ShipStats(torpedo=3)),
            _material(2, '保留乙', ShipStats(anti_air=1)),
            _material(3, '高星', ShipStats(torpedo=9), rarity=5),
        ),
        IntensifyPolicy(frozenset({'使用', '保留甲', '保留乙', '高星'}), maximum_materials=2),
    )

    assert [item.ref.value for item in result.remaining_materials] == [
        'material:0',
        'material:2',
        'material:3',
    ]
    assert [item.index for item in result.remaining_materials] == [0, 1, 2]
