"""Recognition-neutral planning and fail-closed execution for ship intensification.

Recognition is deliberately represented by protocols and immutable observations.
The workflow never performs OCR itself and can therefore consume observations from
the current name reader or a future portrait-recognition library.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
import uuid
from dataclasses import dataclass
from enum import StrEnum
from itertools import combinations
from typing import TYPE_CHECKING, Protocol


if TYPE_CHECKING:
    from collections.abc import Iterable


class IntensifyWorkflowError(RuntimeError):
    """Raised before further input when an intensify invariant is not proven."""


class IntensifyUiState(StrEnum):
    HOME = 'home'
    TARGET_SELECTOR = 'target_selector'
    MATERIAL_SELECTOR = 'material_selector'
    CONFIRMATION = 'confirmation'


@dataclass(frozen=True, slots=True)
class SelectionRef:
    """Opaque selector reference supplied and later resolved by a recognition backend."""

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError('选择引用不能为空')


@dataclass(frozen=True, slots=True)
class ShipStats:
    firepower: int = 0
    torpedo: int = 0
    armor: int = 0
    anti_air: int = 0

    def __post_init__(self) -> None:
        values = (self.firepower, self.torpedo, self.armor, self.anti_air)
        if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
            raise TypeError('强化属性和收益必须是整数')
        if min(self.firepower, self.torpedo, self.armor, self.anti_air) < 0:
            raise ValueError('强化属性和收益不能为负数')

    def __add__(self, other: ShipStats) -> ShipStats:
        return ShipStats(
            firepower=self.firepower + other.firepower,
            torpedo=self.torpedo + other.torpedo,
            armor=self.armor + other.armor,
            anti_air=self.anti_air + other.anti_air,
        )


@dataclass(frozen=True, slots=True)
class TargetObservation:
    ref: SelectionRef
    identity: str
    level: int | None
    stats: ShipStats


@dataclass(frozen=True, slots=True)
class MaterialOccurrence:
    """One exact selectable occurrence; duplicate identities keep distinct references."""

    ref: SelectionRef
    identity: str
    index: int
    contribution: ShipStats = ShipStats()
    rarity: int = 1

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError('素材 occurrence 索引不能为负数')
        if not self.identity:
            raise ValueError('素材 identity 不能为空')
        if (
            isinstance(self.rarity, bool)
            or not isinstance(self.rarity, int)
            or not 1 <= self.rarity <= 6
        ):
            raise ValueError('素材星级必须是 1 到 6 的整数')

    @property
    def requires_confirmation(self) -> bool:
        return self.rarity >= 4


@dataclass(frozen=True, slots=True)
class MaterialInventoryObservation:
    occurrences: tuple[MaterialOccurrence, ...]
    complete: bool
    revision: str

    def __post_init__(self) -> None:
        if not self.complete:
            raise ValueError('部分素材库存不能进入强化规划')
        if not self.revision:
            raise ValueError('素材库存 revision 不能为空')
        if tuple(item.index for item in self.occurrences) != tuple(range(len(self.occurrences))):
            raise ValueError('素材 occurrence 索引必须连续')
        refs = tuple(item.ref for item in self.occurrences)
        if len(set(refs)) != len(refs):
            raise ValueError('素材 occurrence 引用必须唯一')

    @property
    def fingerprint(self) -> str:
        payload = {
            'revision': self.revision,
            'occurrences': [
                {
                    'ref': item.ref.value,
                    'identity': item.identity,
                    'index': item.index,
                    'contribution': _stats_payload(item.contribution),
                    'rarity': item.rarity,
                }
                for item in self.occurrences
            ],
        }
        return _fingerprint(payload)


@dataclass(frozen=True, slots=True)
class IntensifyPolicy:
    allowed_material_identities: frozenset[str]
    maximum_materials: int | None = 1

    def __post_init__(self) -> None:
        if not self.allowed_material_identities:
            raise ValueError('必须显式配置可消耗素材 allowlist')
        if self.maximum_materials is None:
            return
        if isinstance(self.maximum_materials, bool) or not isinstance(self.maximum_materials, int):
            raise TypeError('maximum_materials 必须是正整数或 None')
        if self.maximum_materials < 1:
            raise ValueError('maximum_materials 必须大于零')


@dataclass(frozen=True, slots=True)
class IntensifyGoal:
    """Minimum material experience contribution the planner must satisfy."""

    minimum_gains: ShipStats

    def __post_init__(self) -> None:
        if self.minimum_gains == ShipStats():
            raise ValueError('强化目标收益不能全部为零')


@dataclass(frozen=True, slots=True)
class IntensifyPlan:
    target: TargetObservation
    materials: tuple[MaterialOccurrence, ...]
    material_contribution: ShipStats
    expected_gains: ShipStats
    inventory_fingerprint: str
    fingerprint: str
    validation_proof: str = ''


@dataclass(frozen=True, slots=True)
class IntensifyHomeObservation:
    target: TargetObservation | None
    materials: tuple[MaterialOccurrence, ...]
    gains: ShipStats
    can_intensify: bool


@dataclass(frozen=True, slots=True)
class ConfirmationObservation:
    target: TargetObservation
    material_refs: tuple[SelectionRef, ...]
    gains: ShipStats


@dataclass(frozen=True, slots=True)
class IntensifyOutcomeObservation:
    """Semantic result receipt for the strengthened target on the resulting home page."""

    target: TargetObservation


@dataclass(frozen=True, slots=True)
class DryRunEvidence:
    plan_fingerprint: str
    inventory_fingerprint: str
    cancelled: bool
    clean_after_cancel: bool
    proof: str = ''


@dataclass(frozen=True, slots=True)
class IntensifyAuthorization:
    """Explicit, single-use authorization bound to one plan and successful dry-run."""

    authorization_id: str
    plan_fingerprint: str
    inventory_fingerprint: str


@dataclass(frozen=True, slots=True)
class IntensifyResult:
    plan_fingerprint: str
    target_before: TargetObservation
    target_after: TargetObservation
    inventory_before: MaterialInventoryObservation
    inventory_after: MaterialInventoryObservation


class IntensifyRecognitionPort(Protocol):
    """Replaceable source of semantic observations; no recognition method is prescribed."""

    def state(self) -> IntensifyUiState: ...

    def home(self) -> IntensifyHomeObservation: ...

    def confirmation(self) -> ConfirmationObservation: ...

    def inventory(self) -> MaterialInventoryObservation: ...

    def outcome(self) -> IntensifyOutcomeObservation: ...


class IntensifyControlPort(Protocol):
    """UI actions with selector references resolved by the concrete adapter."""

    def open_target_selector(self) -> None: ...

    def select_target(self, ref: SelectionRef) -> None: ...

    def accept_target(self) -> None: ...

    def open_material_selector(self) -> None: ...

    def select_material(self, ref: SelectionRef) -> None: ...

    def accept_materials(self) -> None: ...

    def open_confirmation(self) -> None: ...

    def cancel_confirmation(self) -> None: ...

    def clear_materials(self) -> None: ...

    def confirm_irreversible_once(self) -> None: ...

    def execute_without_confirmation_once(self) -> None: ...


class SelectionOperator(Protocol):
    """Resolve and click one opaque reference in the active selector."""

    def select(self, ref: SelectionRef) -> None: ...


@dataclass(frozen=True, slots=True)
class ConfirmationCoordinates:
    """Version-specific dialog coordinates supplied after visual calibration."""

    cancel: tuple[float, float]
    confirm: tuple[float, float]


class VerifiedIntensifyControl:
    """Evidence-calibrated home actions with injected selection and dialog adapters."""

    _TARGET_SLOT = (0.1070, 0.5093)
    _MATERIAL_SLOT = (0.2630, 0.3380)
    _MATERIAL_ACCEPT = (0.9115, 0.9000)
    _CLEAR_MATERIALS = (0.8715, 0.7090)
    _INTENSIFY = (0.8715, 0.8220)

    def __init__(
        self,
        ctrl: object,
        recognition: IntensifyRecognitionPort,
        target_operator: SelectionOperator,
        material_operator: SelectionOperator,
        confirmation_coordinates: ConfirmationCoordinates,
        *,
        timeout: float = 6.0,
        interval: float = 0.25,
        stable_frames: int = 2,
    ) -> None:
        self._ctrl = ctrl
        self._recognition = recognition
        self._target_operator = target_operator
        self._material_operator = material_operator
        self._confirmation_coordinates = confirmation_coordinates
        self._timeout = timeout
        self._interval = interval
        self._stable_frames = stable_frames
        self._irreversible_clicked = False

    def _click(self, coord: tuple[float, float]) -> None:
        click = getattr(self._ctrl, 'click', None)
        if click is None:
            raise IntensifyWorkflowError('强化控制器不支持 click')
        click(*coord)

    def _require(self, expected: IntensifyUiState) -> None:
        if self._recognition.state() != expected:
            raise IntensifyWorkflowError(f'操作前页面状态不是 {expected}')

    def _wait(self, expected: IntensifyUiState) -> None:
        deadline = time.monotonic() + self._timeout
        stable = 0
        while time.monotonic() < deadline:
            if self._recognition.state() == expected:
                stable += 1
                if stable >= self._stable_frames:
                    return
            else:
                stable = 0
            time.sleep(self._interval)
        raise IntensifyWorkflowError(f'操作后未稳定到达页面: {expected}')

    def open_target_selector(self) -> None:
        self._require(IntensifyUiState.HOME)
        self._click(self._TARGET_SLOT)
        self._wait(IntensifyUiState.TARGET_SELECTOR)

    def select_target(self, ref: SelectionRef) -> None:
        self._require(IntensifyUiState.TARGET_SELECTOR)
        self._target_operator.select(ref)
        self._wait(IntensifyUiState.HOME)

    def accept_target(self) -> None:
        self._require(IntensifyUiState.HOME)

    def open_material_selector(self) -> None:
        self._require(IntensifyUiState.HOME)
        self._click(self._MATERIAL_SLOT)
        self._wait(IntensifyUiState.MATERIAL_SELECTOR)

    def select_material(self, ref: SelectionRef) -> None:
        self._require(IntensifyUiState.MATERIAL_SELECTOR)
        self._material_operator.select(ref)
        self._require(IntensifyUiState.MATERIAL_SELECTOR)

    def accept_materials(self) -> None:
        self._require(IntensifyUiState.MATERIAL_SELECTOR)
        self._click(self._MATERIAL_ACCEPT)
        self._wait(IntensifyUiState.HOME)

    def open_confirmation(self) -> None:
        self._require(IntensifyUiState.HOME)
        self._click(self._INTENSIFY)
        self._wait(IntensifyUiState.CONFIRMATION)

    def cancel_confirmation(self) -> None:
        self._require(IntensifyUiState.CONFIRMATION)
        self._click(self._confirmation_coordinates.cancel)
        self._wait(IntensifyUiState.HOME)

    def clear_materials(self) -> None:
        self._require(IntensifyUiState.HOME)
        self._click(self._CLEAR_MATERIALS)
        self._wait(IntensifyUiState.HOME)

    def confirm_irreversible_once(self) -> None:
        self._require(IntensifyUiState.CONFIRMATION)
        if self._irreversible_clicked:
            raise IntensifyWorkflowError('不可逆确认已由控制适配器点击过')
        self._irreversible_clicked = True
        self._click(self._confirmation_coordinates.confirm)
        self._wait(IntensifyUiState.HOME)

    def execute_without_confirmation_once(self) -> None:
        self._require(IntensifyUiState.HOME)
        if self._irreversible_clicked:
            raise IntensifyWorkflowError('不可逆强化已由控制适配器点击过')
        self._irreversible_clicked = True
        self._click(self._INTENSIFY)
        self._wait(IntensifyUiState.HOME)


def plan_intensify(
    inventory: MaterialInventoryObservation,
    target: TargetObservation,
    goal: IntensifyGoal,
    policy: IntensifyPolicy,
    *,
    projected_gains: ShipStats,
) -> IntensifyPlan:
    """Choose the smallest exact-occurrence combination satisfying contribution goals.

    ``MaterialOccurrence.contribution`` and ``IntensifyGoal.minimum_gains`` represent
    material-page strengthening experience, not direct final panel deltas.
    ``projected_gains`` is independently supplied by the semantic recognition adapter
    from the intensify-home ``+N`` preview for the selected combination.
    """
    candidates = tuple(
        item
        for item in inventory.occurrences
        if item.identity in policy.allowed_material_identities
        and item.contribution != ShipStats()
        and item.ref != target.ref
    )
    viable: list[tuple[tuple[object, ...], tuple[MaterialOccurrence, ...]]] = []
    maximum_materials = policy.maximum_materials or len(candidates)
    for size in range(1, min(maximum_materials, len(candidates)) + 1):
        for selected in combinations(candidates, size):
            gains = _sum_stats(item.contribution for item in selected)
            if not _meets(gains, goal.minimum_gains):
                continue
            excess = ShipStats(
                firepower=gains.firepower - goal.minimum_gains.firepower,
                torpedo=gains.torpedo - goal.minimum_gains.torpedo,
                armor=gains.armor - goal.minimum_gains.armor,
                anti_air=gains.anti_air - goal.minimum_gains.anti_air,
            )
            score = (
                size,
                excess.firepower + excess.torpedo + excess.armor + excess.anti_air,
                excess.firepower,
                excess.torpedo,
                excess.armor,
                excess.anti_air,
                tuple(item.index for item in selected),
            )
            viable.append((score, selected))
    if not viable:
        raise IntensifyWorkflowError('完整库存中没有满足目标收益和 allowlist 的素材组合')
    selected = min(viable, key=lambda item: item[0])[1]
    return create_intensify_plan(
        inventory,
        target,
        tuple(item.ref for item in selected),
        projected_gains,
        policy,
    )


def create_intensify_plan(
    inventory: MaterialInventoryObservation,
    target: TargetObservation,
    material_refs: tuple[SelectionRef, ...],
    expected_gains: ShipStats,
    policy: IntensifyPolicy,
) -> IntensifyPlan:
    """Resolve exact occurrences under an explicit destructive-operation policy."""
    if not material_refs:
        raise IntensifyWorkflowError('强化计划至少需要一个素材 occurrence')
    if policy.maximum_materials is not None and len(material_refs) > policy.maximum_materials:
        raise IntensifyWorkflowError('强化计划超过允许的素材数量')
    if len(set(material_refs)) != len(material_refs):
        raise IntensifyWorkflowError('强化计划包含重复 occurrence 引用')
    by_ref = {item.ref: item for item in inventory.occurrences}
    try:
        materials = tuple(by_ref[ref] for ref in material_refs)
    except KeyError as error:
        raise IntensifyWorkflowError(
            f'素材 occurrence 不在完整库存中: {error.args[0].value}'
        ) from error
    forbidden = [
        item.identity
        for item in materials
        if item.identity not in policy.allowed_material_identities
    ]
    if forbidden:
        raise IntensifyWorkflowError(f'素材不在显式 allowlist 中: {forbidden}')
    if target.ref in material_refs:
        raise IntensifyWorkflowError('强化目标不能同时作为素材')
    if expected_gains == ShipStats():
        raise IntensifyWorkflowError('预期强化收益不能全部为零')
    contributions = _sum_stats(item.contribution for item in materials)

    fingerprint = _plan_fingerprint(
        target,
        materials,
        expected_gains,
        inventory.fingerprint,
    )
    validation_proof = secrets.token_urlsafe(32)
    _VALIDATED_PLANS[validation_proof] = fingerprint
    return IntensifyPlan(
        target=target,
        materials=materials,
        material_contribution=contributions,
        expected_gains=expected_gains,
        inventory_fingerprint=inventory.fingerprint,
        fingerprint=fingerprint,
        validation_proof=validation_proof,
    )


def authorize_intensify(plan: IntensifyPlan, evidence: DryRunEvidence) -> IntensifyAuthorization:
    """Create an explicit one-shot authorization only from matching clean dry-run evidence."""
    if not evidence.cancelled or not evidence.clean_after_cancel:
        raise IntensifyWorkflowError('dry-run 未证明已取消并清空选择')
    if evidence.plan_fingerprint != plan.fingerprint:
        raise IntensifyWorkflowError('dry-run 与强化计划不匹配')
    if evidence.inventory_fingerprint != plan.inventory_fingerprint:
        raise IntensifyWorkflowError('dry-run 库存与强化计划不匹配')
    registered = _DRY_RUN_PROOFS.pop(evidence.proof, None)
    if registered != (plan.fingerprint, plan.inventory_fingerprint):
        raise IntensifyWorkflowError('dry-run 证据不是由工作流生成或已经使用')
    authorization = IntensifyAuthorization(
        authorization_id=uuid.uuid4().hex,
        plan_fingerprint=plan.fingerprint,
        inventory_fingerprint=plan.inventory_fingerprint,
    )
    _AUTHORIZATIONS[authorization.authorization_id] = (
        plan.fingerprint,
        plan.inventory_fingerprint,
    )
    return authorization


class IntensifyWorkflow:
    """Drive one verified dry-run or explicitly authorized irreversible operation."""

    def __init__(
        self, recognition: IntensifyRecognitionPort, control: IntensifyControlPort
    ) -> None:
        self._recognition = recognition
        self._control = control

    def dry_run(self, plan: IntensifyPlan) -> DryRunEvidence:
        _require_validated_plan(plan)
        self._require_inventory(plan.inventory_fingerprint)
        try:
            self._prepare_preview(plan)
            if _requires_confirmation(plan):
                self._control.open_confirmation()
                self._require_state(IntensifyUiState.CONFIRMATION)
                self._verify_confirmation(plan)
                self._control.cancel_confirmation()
                self._require_state(IntensifyUiState.HOME)
            self._control.clear_materials()
            clean = self._require_clean_home()
            self._require_inventory(plan.inventory_fingerprint)
        except Exception:
            self._recover_reversible_dry_run()
            raise
        proof = secrets.token_urlsafe(32)
        _DRY_RUN_PROOFS[proof] = (plan.fingerprint, plan.inventory_fingerprint)
        return DryRunEvidence(plan.fingerprint, plan.inventory_fingerprint, True, clean, proof)

    def _recover_reversible_dry_run(self) -> None:
        """Best-effort cleanup after evidence rejection; never confirms the operation."""
        try:
            state = self._recognition.state()
            if state == IntensifyUiState.CONFIRMATION:
                self._control.cancel_confirmation()
                state = self._recognition.state()
            if state == IntensifyUiState.HOME:
                self._control.clear_materials()
        except Exception:
            # Preserve the original evidence failure. A caller must treat cleanup
            # uncertainty as fail-closed and inspect the page before any new input.
            return

    def execute(
        self,
        plan: IntensifyPlan,
        authorization: IntensifyAuthorization,
    ) -> IntensifyResult:
        _require_validated_plan(plan)
        _claim_authorization(plan, authorization)
        inventory_before = self._require_inventory(plan.inventory_fingerprint)
        self._prepare_preview(plan)
        if _requires_confirmation(plan):
            self._control.open_confirmation()
            self._require_state(IntensifyUiState.CONFIRMATION)
            self._verify_confirmation(plan)
            self._require_inventory(plan.inventory_fingerprint)
            self._control.confirm_irreversible_once()
        else:
            self._require_inventory(plan.inventory_fingerprint)
            self._control.execute_without_confirmation_once()

        self._require_state(IntensifyUiState.HOME)
        home_after = self._recognition.home()
        inventory_after = self._recognition.inventory()
        outcome = self._recognition.outcome()
        self._verify_postconditions(plan, home_after, outcome, inventory_before, inventory_after)
        if home_after.target is None:
            raise IntensifyWorkflowError('强化后目标舰观测缺失')
        return IntensifyResult(
            plan.fingerprint,
            plan.target,
            home_after.target,
            inventory_before,
            inventory_after,
        )

    def _prepare_preview(self, plan: IntensifyPlan) -> None:
        self._require_state(IntensifyUiState.HOME)
        if self._recognition.home().materials:
            raise IntensifyWorkflowError('强化首页已有未授权素材选择')

        self._control.open_target_selector()
        self._require_state(IntensifyUiState.TARGET_SELECTOR)
        self._control.select_target(plan.target.ref)
        self._control.accept_target()
        self._require_state(IntensifyUiState.HOME)
        selected_target = self._recognition.home().target
        if selected_target != plan.target:
            raise IntensifyWorkflowError('无法证明已选择计划目标舰')

        self._control.open_material_selector()
        self._require_state(IntensifyUiState.MATERIAL_SELECTOR)
        for material in plan.materials:
            self._control.select_material(material.ref)
        self._control.accept_materials()
        self._require_state(IntensifyUiState.HOME)
        self._verify_home_preview(plan, self._recognition.home())

    @staticmethod
    def _verify_home_preview(plan: IntensifyPlan, home: IntensifyHomeObservation) -> None:
        expected_refs = tuple(item.ref for item in plan.materials)
        actual_refs = tuple(item.ref for item in home.materials)
        if home.target != plan.target:
            raise IntensifyWorkflowError('强化预览目标与计划不一致')
        if actual_refs != expected_refs:
            raise IntensifyWorkflowError('强化预览素材 occurrence 或顺序与计划不一致')
        if home.gains != plan.expected_gains:
            raise IntensifyWorkflowError('强化预览收益与计划不一致')
        if not home.can_intensify:
            raise IntensifyWorkflowError('强化预览未证明操作可执行')

    def _verify_confirmation(self, plan: IntensifyPlan) -> None:
        dialog = self._recognition.confirmation()
        if dialog.target != plan.target:
            raise IntensifyWorkflowError('确认弹窗目标与计划不一致')
        if dialog.material_refs != tuple(item.ref for item in plan.materials):
            raise IntensifyWorkflowError('确认弹窗素材与计划不一致')
        if dialog.gains != plan.expected_gains:
            raise IntensifyWorkflowError('确认弹窗收益与计划不一致')

    def _require_inventory(self, fingerprint: str) -> MaterialInventoryObservation:
        inventory = self._recognition.inventory()
        if inventory.fingerprint != fingerprint:
            raise IntensifyWorkflowError('素材库存已变化，计划过期')
        return inventory

    def _require_state(self, expected: IntensifyUiState) -> None:
        actual = self._recognition.state()
        if actual != expected:
            raise IntensifyWorkflowError(f'强化页面状态异常: expected={expected}, actual={actual}')

    def _require_clean_home(self) -> bool:
        home = self._recognition.home()
        if home.materials or home.gains != ShipStats() or home.can_intensify:
            raise IntensifyWorkflowError('dry-run 取消后未恢复无素材状态')
        return True

    @staticmethod
    def _verify_postconditions(
        plan: IntensifyPlan,
        home: IntensifyHomeObservation,
        outcome: IntensifyOutcomeObservation,
        before: MaterialInventoryObservation,
        after: MaterialInventoryObservation,
    ) -> None:
        if outcome.target != home.target:
            raise IntensifyWorkflowError('强化结果回执与首页目标不一致')
        if home.target is None or home.target.ref != plan.target.ref:
            raise IntensifyWorkflowError('强化后目标舰不一致')
        if home.target.stats != plan.target.stats + plan.expected_gains:
            raise IntensifyWorkflowError('强化后目标属性不符合预期')
        if home.materials:
            raise IntensifyWorkflowError('强化后素材槽未清空')
        if after.revision == before.revision:
            raise IntensifyWorkflowError('强化后素材库存 revision 未变化')
        consumed = {item.ref for item in plan.materials}
        expected_remaining = tuple(item for item in before.occurrences if item.ref not in consumed)
        expected_remaining_identities = tuple(item.identity for item in expected_remaining)
        actual_remaining_identities = tuple(item.identity for item in after.occurrences)
        if actual_remaining_identities != expected_remaining_identities:
            raise IntensifyWorkflowError('强化后素材库存变化与计划不一致')


def _stats_payload(stats: ShipStats) -> dict[str, int]:
    return {
        'firepower': stats.firepower,
        'torpedo': stats.torpedo,
        'armor': stats.armor,
        'anti_air': stats.anti_air,
    }


def _sum_stats(values: Iterable[ShipStats]) -> ShipStats:
    result = ShipStats()
    for value in values:
        result += value
    return result


def _meets(actual: ShipStats, minimum: ShipStats) -> bool:
    return (
        actual.firepower >= minimum.firepower
        and actual.torpedo >= minimum.torpedo
        and actual.armor >= minimum.armor
        and actual.anti_air >= minimum.anti_air
    )


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(encoded.encode()).hexdigest()


_DRY_RUN_PROOFS: dict[str, tuple[str, str]] = {}
_AUTHORIZATIONS: dict[str, tuple[str, str]] = {}
_CONSUMED_AUTHORIZATIONS: set[str] = set()
_AUTHORIZATION_LOCK = threading.Lock()
_VALIDATED_PLANS: dict[str, str] = {}


def _require_validated_plan(plan: IntensifyPlan) -> None:
    recomputed = _plan_fingerprint(
        plan.target,
        plan.materials,
        plan.expected_gains,
        plan.inventory_fingerprint,
    )
    if plan.fingerprint != recomputed or _VALIDATED_PLANS.get(plan.validation_proof) != recomputed:
        raise IntensifyWorkflowError('强化计划不是由安全规划器生成')


def _plan_fingerprint(
    target: TargetObservation,
    materials: tuple[MaterialOccurrence, ...],
    expected_gains: ShipStats,
    inventory_fingerprint: str,
) -> str:
    payload = {
        'target': {
            'ref': target.ref.value,
            'identity': target.identity,
            'level': target.level,
            'stats': _stats_payload(target.stats),
        },
        'materials': [
            {
                'ref': item.ref.value,
                'identity': item.identity,
                'index': item.index,
                'contribution': _stats_payload(item.contribution),
                'rarity': item.rarity,
            }
            for item in materials
        ],
        'material_contribution': _stats_payload(
            _sum_stats(item.contribution for item in materials)
        ),
        'gains': _stats_payload(expected_gains),
        'inventory': inventory_fingerprint,
    }
    return _fingerprint(payload)


def _requires_confirmation(plan: IntensifyPlan) -> bool:
    return any(item.requires_confirmation for item in plan.materials)


def _claim_authorization(
    plan: IntensifyPlan,
    authorization: IntensifyAuthorization,
) -> None:
    """Atomically validate and consume one authorization before any UI input."""
    with _AUTHORIZATION_LOCK:
        if authorization.authorization_id in _CONSUMED_AUTHORIZATIONS:
            raise IntensifyWorkflowError('不可逆强化授权已使用')
        expected = (plan.fingerprint, plan.inventory_fingerprint)
        if _AUTHORIZATIONS.get(authorization.authorization_id) != expected:
            raise IntensifyWorkflowError('不可逆强化授权不是由有效 dry-run 生成')
        if authorization.plan_fingerprint != plan.fingerprint:
            raise IntensifyWorkflowError('不可逆强化授权与计划不匹配')
        if authorization.inventory_fingerprint != plan.inventory_fingerprint:
            raise IntensifyWorkflowError('不可逆强化授权库存指纹不匹配')
        _CONSUMED_AUTHORIZATIONS.add(authorization.authorization_id)
