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
    maximum_rarity: int = 6,
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


def _select_complete_batch(
    candidates: tuple[MaterialOccurrence, ...],
    need: ShipStats,
    limit: int,
) -> tuple[MaterialOccurrence, ...]:
    for size in range(1, limit + 1):
        best: tuple[tuple[object, ...], tuple[MaterialOccurrence, ...]] | None = None
        for selected in combinations(candidates, size):
            contribution = _sum_stats(item.contribution for item in selected)
            if not _meets(contribution, need):
                continue
            excess = _excess(contribution, need)
            score = (
                _total(excess),
                excess.firepower,
                excess.torpedo,
                excess.armor,
                excess.anti_air,
                tuple(item.index for item in selected),
            )
            if best is None or score < best[0]:
                best = (score, selected)
        if best is not None:
            return best[1]
    return ()


def _select_partial_batch(
    candidates: tuple[MaterialOccurrence, ...],
    need: ShipStats,
    limit: int,
) -> tuple[MaterialOccurrence, ...]:
    best: tuple[tuple[object, ...], tuple[MaterialOccurrence, ...]] | None = None
    for size in range(1, limit + 1):
        for selected in combinations(candidates, size):
            contribution = _sum_stats(item.contribution for item in selected)
            useful = _useful(contribution, need)
            if useful == 0:
                continue
            waste = _total(contribution) - useful
            score = (-useful, waste, size, tuple(item.index for item in selected))
            if best is None or score < best[0]:
                best = (score, selected)
    return best[1] if best is not None else ()


def _select_batch(
    candidates: tuple[MaterialOccurrence, ...],
    need: ShipStats,
    maximum_materials: int | None,
) -> tuple[MaterialOccurrence, ...]:
    if not candidates:
        return ()
    limit = (
        len(candidates) if maximum_materials is None else min(maximum_materials, len(candidates))
    )
    if limit <= 6:
        complete = _select_complete_batch(candidates, need, limit)
        return complete or _select_partial_batch(candidates, need, limit)

    selected_list: list[MaterialOccurrence] = []
    current_need = need
    remaining_candidates = list(candidates)

    while remaining_candidates and len(selected_list) < limit and current_need != ShipStats():
        best_cand = None
        best_score = None
        for cand in remaining_candidates:
            u = _useful(cand.contribution, current_need)
            if u == 0:
                continue
            w = _total(cand.contribution) - u
            score = (-u, w, cand.index)
            if best_score is None or score < best_score:
                best_score = score
                best_cand = cand
        if best_cand is None:
            break
        selected_list.append(best_cand)
        remaining_candidates.remove(best_cand)
        current_need = _remaining_need(current_need, best_cand.contribution)

    return tuple(sorted(selected_list, key=lambda item: item.index))


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
