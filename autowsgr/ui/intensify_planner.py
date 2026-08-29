"""Deterministic pure planning for ordered intensify inventory snapshots."""

from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import combinations

from autowsgr.ui.intensify_workflow import (
    IntensifyPolicy,
    MaterialInventoryObservation,
    MaterialOccurrence,
    SelectionRef,
    ShipStats,
    TargetObservation,
)


@dataclass(frozen=True, slots=True)
class IntensifyPlanningTarget:
    """One ordered target and its remaining material-experience requirement."""

    target: TargetObservation
    index: int
    required_contribution: ShipStats

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError('强化目标索引不能为负数')


@dataclass(frozen=True, slots=True)
class IntensifyPlanBatch:
    """All materials selected together for one target in one strengthening action."""

    target: TargetObservation
    target_index: int
    materials: tuple[MaterialOccurrence, ...]
    contribution: ShipStats


@dataclass(frozen=True, slots=True)
class IntensifyPlanningResult:
    batches: tuple[IntensifyPlanBatch, ...]
    remaining_materials: tuple[MaterialOccurrence, ...]


def plan_ordered_intensify_batches(
    targets: tuple[IntensifyPlanningTarget, ...],
    inventory: MaterialInventoryObservation,
    policy: IntensifyPolicy,
    *,
    maximum_rarity: int = 3,
) -> IntensifyPlanningResult:
    """Allocate ordered material occurrences once across ordered targets.

    Complete combinations are preferred by material count and excess contribution.
    If the remaining inventory cannot complete a target in one batch, the most useful
    deterministic batch is emitted and the target's remaining requirement is planned
    again. Unallocated occurrences preserve their relative order and receive fresh
    contiguous indices for theoretical-position calculation.
    """
    if isinstance(maximum_rarity, bool) or not isinstance(maximum_rarity, int):
        raise TypeError('最高允许素材星级必须是整数')
    if not 1 <= maximum_rarity <= 6:
        raise ValueError('最高允许素材星级必须是 1 到 6')
    if tuple(item.index for item in targets) != tuple(sorted(item.index for item in targets)):
        raise ValueError('强化目标必须按库存顺序传入')
    target_refs = tuple(item.target.ref for item in targets)
    if len(set(target_refs)) != len(target_refs):
        raise ValueError('强化目标引用必须唯一')

    available = [
        item
        for item in inventory.occurrences
        if item.identity in policy.allowed_material_identities
        and item.rarity <= maximum_rarity
        and item.contribution != ShipStats()
        and item.ref not in target_refs
    ]
    allocated: set[SelectionRef] = set()
    batches: list[IntensifyPlanBatch] = []

    for planned_target in targets:
        need = planned_target.required_contribution
        while need != ShipStats():
            candidates = tuple(
                item
                for item in available
                if item.ref not in allocated and _useful(item.contribution, need) > 0
            )
            selected = _select_batch(candidates, need, policy.maximum_materials)
            if not selected:
                break
            contribution = _sum_stats(item.contribution for item in selected)
            batches.append(
                IntensifyPlanBatch(
                    target=planned_target.target,
                    target_index=planned_target.index,
                    materials=selected,
                    contribution=contribution,
                )
            )
            allocated.update(item.ref for item in selected)
            need = _remaining_need(need, contribution)

    remaining = tuple(
        replace(item, index=index)
        for index, item in enumerate(
            item for item in inventory.occurrences if item.ref not in allocated
        )
    )
    return IntensifyPlanningResult(tuple(batches), remaining)


def _select_batch(
    candidates: tuple[MaterialOccurrence, ...],
    need: ShipStats,
    maximum_materials: int,
) -> tuple[MaterialOccurrence, ...]:
    if not candidates:
        return ()
    limit = min(maximum_materials, len(candidates))
    complete: list[tuple[tuple[object, ...], tuple[MaterialOccurrence, ...]]] = []
    partial: list[tuple[tuple[object, ...], tuple[MaterialOccurrence, ...]]] = []
    for size in range(1, limit + 1):
        for selected in combinations(candidates, size):
            contribution = _sum_stats(item.contribution for item in selected)
            indices = tuple(item.index for item in selected)
            if _meets(contribution, need):
                excess = _excess(contribution, need)
                complete.append(
                    (
                        (
                            size,
                            _total(excess),
                            excess.firepower,
                            excess.torpedo,
                            excess.armor,
                            excess.anti_air,
                            indices,
                        ),
                        selected,
                    )
                )
                continue
            useful = _useful(contribution, need)
            if useful == 0:
                continue
            waste = _total(contribution) - useful
            partial.append(((-useful, waste, size, indices), selected))
    if complete:
        return min(complete, key=lambda item: item[0])[1]
    if partial:
        return min(partial, key=lambda item: item[0])[1]
    return ()


def _sum_stats(values: object) -> ShipStats:
    total = ShipStats()
    for value in values:
        total += value
    return total


def _meets(actual: ShipStats, required: ShipStats) -> bool:
    return (
        actual.firepower >= required.firepower
        and actual.torpedo >= required.torpedo
        and actual.armor >= required.armor
        and actual.anti_air >= required.anti_air
    )


def _remaining_need(required: ShipStats, contribution: ShipStats) -> ShipStats:
    return ShipStats(
        firepower=max(0, required.firepower - contribution.firepower),
        torpedo=max(0, required.torpedo - contribution.torpedo),
        armor=max(0, required.armor - contribution.armor),
        anti_air=max(0, required.anti_air - contribution.anti_air),
    )


def _excess(contribution: ShipStats, need: ShipStats) -> ShipStats:
    return ShipStats(
        firepower=max(0, contribution.firepower - need.firepower),
        torpedo=max(0, contribution.torpedo - need.torpedo),
        armor=max(0, contribution.armor - need.armor),
        anti_air=max(0, contribution.anti_air - need.anti_air),
    )


def _useful(contribution: ShipStats, need: ShipStats) -> int:
    return (
        min(contribution.firepower, need.firepower)
        + min(contribution.torpedo, need.torpedo)
        + min(contribution.armor, need.armor)
        + min(contribution.anti_air, need.anti_air)
    )


def _total(stats: ShipStats) -> int:
    return stats.firepower + stats.torpedo + stats.armor + stats.anti_air
