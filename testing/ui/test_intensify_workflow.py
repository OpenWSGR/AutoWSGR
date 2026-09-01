from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from unittest.mock import MagicMock

import pytest

from autowsgr.ui.intensify_workflow import (
    ConfirmationCoordinates,
    ConfirmationObservation,
    DryRunEvidence,
    IntensifyGoal,
    IntensifyHomeObservation,
    IntensifyOutcomeObservation,
    IntensifyPlan,
    IntensifyPolicy,
    IntensifyUiState,
    IntensifyWorkflow,
    IntensifyWorkflowError,
    MaterialInventoryObservation,
    MaterialOccurrence,
    SelectionRef,
    ShipStats,
    TargetObservation,
    VerifiedIntensifyControl,
    authorize_intensify,
    create_intensify_plan,
    plan_intensify,
)


TARGET_REF = SelectionRef('target:570:lv110')
MAT_A_REF = SelectionRef('material:0')
MAT_B_REF = SelectionRef('material:1')
GAINS = ShipStats(armor=1, anti_air=3)
TARGET = TargetObservation(TARGET_REF, 'No.570', 110, ShipStats(armor=16, anti_air=28))
MAT_A = MaterialOccurrence(MAT_A_REF, 'No.474', 0, rarity=3)
MAT_B = MaterialOccurrence(MAT_B_REF, 'No.474', 1, rarity=4)


def _inventory(
    *items: MaterialOccurrence, revision: str = 'scan-1'
) -> MaterialInventoryObservation:
    normalized = tuple(replace(item, index=index) for index, item in enumerate(items))
    return MaterialInventoryObservation(normalized, complete=True, revision=revision)


def _plan(inventory: MaterialInventoryObservation, *refs: SelectionRef) -> IntensifyPlan:
    return create_intensify_plan(
        inventory,
        TARGET,
        tuple(refs),
        GAINS,
        IntensifyPolicy(frozenset({'No.474'}), maximum_materials=2),
    )


def test_planner_preserves_and_selects_exact_duplicate_occurrence() -> None:
    inventory = _inventory(MAT_A, MAT_B)

    plan = _plan(inventory, MAT_B_REF)

    assert plan.materials == (replace(MAT_B, index=1),)
    assert plan.inventory_fingerprint == inventory.fingerprint


def test_planner_rejects_unlisted_or_missing_material() -> None:
    inventory = _inventory(MAT_A)
    policy = IntensifyPolicy(frozenset({'safe'}))

    with pytest.raises(IntensifyWorkflowError, match='allowlist'):
        create_intensify_plan(inventory, TARGET, (MAT_A_REF,), GAINS, policy)
    with pytest.raises(IntensifyWorkflowError, match='不在完整库存'):
        _plan(inventory, MAT_B_REF)


def test_directly_constructed_plan_cannot_enter_workflow() -> None:
    inventory = _inventory(MAT_A)
    valid = _plan(inventory, MAT_A_REF)
    forged = replace(valid, validation_proof='')
    recognition = MagicMock()
    control = MagicMock()

    with pytest.raises(IntensifyWorkflowError, match='安全规划器'):
        IntensifyWorkflow(recognition, control).dry_run(forged)

    control.assert_not_called()


def test_valid_plan_proof_cannot_be_copied_to_mutated_materials() -> None:
    inventory = _inventory(MAT_A, MAT_B)
    valid = _plan(inventory, MAT_A_REF)
    forged = replace(valid, materials=(replace(MAT_B, index=1),))

    with pytest.raises(IntensifyWorkflowError, match='安全规划器'):
        IntensifyWorkflow(MagicMock(), MagicMock()).dry_run(forged)


def test_partial_or_non_contiguous_inventory_cannot_be_planned() -> None:
    with pytest.raises(ValueError, match='部分素材库存'):
        MaterialInventoryObservation((MAT_A,), complete=False, revision='scan')
    with pytest.raises(ValueError, match='索引必须连续'):
        MaterialInventoryObservation((replace(MAT_A, index=2),), complete=True, revision='scan')


@pytest.mark.parametrize('value', [True, 1.5, float('nan'), float('inf')])
def test_ship_stats_reject_non_integer_values(value: object) -> None:
    with pytest.raises(TypeError, match='必须是整数'):
        ShipStats(armor=value)  # type: ignore[arg-type]


def test_plan_fingerprint_changes_with_exact_occurrence_or_inventory_revision() -> None:
    first = _inventory(MAT_A, MAT_B, revision='one')
    second = _inventory(MAT_A, MAT_B, revision='two')

    assert _plan(first, MAT_A_REF).fingerprint != _plan(first, MAT_B_REF).fingerprint
    assert _plan(first, MAT_A_REF).fingerprint != _plan(second, MAT_A_REF).fingerprint


def test_planner_chooses_smallest_allowlisted_exact_occurrence_combination() -> None:
    weak = replace(MAT_A, identity='safe', contribution=ShipStats(armor=1))
    strong = replace(MAT_B, identity='safe', contribution=ShipStats(armor=2, anti_air=3))
    extra = MaterialOccurrence(
        SelectionRef('material:2'),
        'safe',
        2,
        ShipStats(armor=1, anti_air=3),
    )
    inventory = _inventory(weak, strong, extra)

    plan = plan_intensify(
        inventory,
        TARGET,
        IntensifyGoal(ShipStats(armor=2, anti_air=3)),
        IntensifyPolicy(frozenset({'safe'}), maximum_materials=2),
        projected_gains=ShipStats(armor=1, anti_air=1),
    )

    assert tuple(item.ref for item in plan.materials) == (MAT_B_REF,)
    assert plan.material_contribution == ShipStats(armor=2, anti_air=3)
    assert plan.expected_gains == ShipStats(armor=1, anti_air=1)


def test_planner_fails_when_no_allowlisted_combination_meets_goal() -> None:
    inventory = _inventory(replace(MAT_A, contribution=ShipStats(armor=1)))

    with pytest.raises(IntensifyWorkflowError, match='没有满足'):
        plan_intensify(
            inventory,
            TARGET,
            IntensifyGoal(ShipStats(armor=2)),
            IntensifyPolicy(frozenset({'No.474'})),
            projected_gains=ShipStats(armor=1),
        )


def test_unlimited_policy_allows_explicit_plan_beyond_finite_ui_limit() -> None:
    materials = tuple(
        MaterialOccurrence(
            SelectionRef(f'material:{index}'),
            'safe',
            index,
            ShipStats(armor=1),
        )
        for index in range(13)
    )
    inventory = _inventory(*materials)
    policy = IntensifyPolicy(frozenset({'safe'}), maximum_materials=None)

    plan = create_intensify_plan(
        inventory,
        TARGET,
        tuple(item.ref for item in inventory.occurrences),
        GAINS,
        policy,
    )

    assert len(plan.materials) == 13


@pytest.mark.parametrize('maximum_materials', [0, -1])
def test_policy_rejects_non_positive_finite_maximum(maximum_materials: int) -> None:
    with pytest.raises(ValueError, match='必须大于零'):
        IntensifyPolicy(frozenset({'safe'}), maximum_materials=maximum_materials)


class _Rig:
    def __init__(self, inventory: MaterialInventoryObservation) -> None:
        self.inventory_value = inventory
        self.state_value = IntensifyUiState.HOME
        self.home_value = IntensifyHomeObservation(None, (), ShipStats(), False)
        self.confirmation_value: ConfirmationObservation | None = None
        self.control = MagicMock()
        self.control.open_target_selector.side_effect = self._open_target
        self.control.select_target.side_effect = self._select_target
        self.control.accept_target.side_effect = self._accept_target
        self.control.open_material_selector.side_effect = self._open_material
        self.control.select_material.side_effect = self._select_material
        self.control.accept_materials.side_effect = self._accept_materials
        self.control.open_confirmation.side_effect = self._open_confirmation
        self.control.cancel_confirmation.side_effect = self._cancel
        self.control.clear_materials.side_effect = self._clear
        self.control.confirm_irreversible_once.side_effect = self._confirm
        self.control.execute_without_confirmation_once.side_effect = self._confirm
        self.pending_materials: list[MaterialOccurrence] = []
        self.selected_target: TargetObservation | None = None
        self.plan = _plan(inventory, inventory.occurrences[0].ref)

    def state(self) -> IntensifyUiState:
        return self.state_value

    def home(self) -> IntensifyHomeObservation:
        return self.home_value

    def confirmation(self) -> ConfirmationObservation:
        assert self.confirmation_value is not None
        return self.confirmation_value

    def outcome(self) -> IntensifyOutcomeObservation:
        assert self.home_value.target is not None
        return IntensifyOutcomeObservation(self.home_value.target)

    def inventory(self) -> MaterialInventoryObservation:
        return self.inventory_value

    def _open_target(self) -> None:
        self.state_value = IntensifyUiState.TARGET_SELECTOR

    def _select_target(self, ref: SelectionRef) -> None:
        assert ref == TARGET_REF
        self.selected_target = TARGET

    def _accept_target(self) -> None:
        self.state_value = IntensifyUiState.HOME
        self.home_value = IntensifyHomeObservation(self.selected_target, (), ShipStats(), False)

    def _open_material(self) -> None:
        self.state_value = IntensifyUiState.MATERIAL_SELECTOR

    def _select_material(self, ref: SelectionRef) -> None:
        self.pending_materials.append(next(item for item in self.plan.materials if item.ref == ref))

    def _accept_materials(self) -> None:
        self.state_value = IntensifyUiState.HOME
        self.home_value = IntensifyHomeObservation(
            TARGET, tuple(self.pending_materials), GAINS, True
        )

    def _open_confirmation(self) -> None:
        self.state_value = IntensifyUiState.CONFIRMATION
        self.confirmation_value = ConfirmationObservation(
            TARGET,
            tuple(item.ref for item in self.pending_materials),
            GAINS,
        )

    def _cancel(self) -> None:
        self.state_value = IntensifyUiState.HOME

    def _clear(self) -> None:
        self.pending_materials.clear()
        self.home_value = IntensifyHomeObservation(TARGET, (), ShipStats(), False)

    def _confirm(self) -> None:
        self.state_value = IntensifyUiState.HOME
        consumed = {item.ref for item in self.plan.materials}
        remaining = tuple(
            replace(item, index=index)
            for index, item in enumerate(
                item for item in self.inventory_value.occurrences if item.ref not in consumed
            )
        )
        self.inventory_value = MaterialInventoryObservation(remaining, True, 'scan-2')
        self.home_value = IntensifyHomeObservation(
            replace(TARGET, stats=TARGET.stats + GAINS),
            (),
            ShipStats(),
            False,
        )


def test_high_rarity_dry_run_opens_and_cancels_confirmation_then_clears_materials() -> None:
    rig = _Rig(_inventory(MAT_B))
    rig.plan = _plan(rig.inventory_value, MAT_B_REF)

    evidence = IntensifyWorkflow(rig, rig.control).dry_run(rig.plan)

    assert evidence.cancelled
    assert evidence.clean_after_cancel
    rig.control.confirm_irreversible_once.assert_not_called()
    rig.control.cancel_confirmation.assert_called_once_with()
    rig.control.clear_materials.assert_called_once_with()


def test_low_rarity_dry_run_verifies_preview_without_clicking_intensify() -> None:
    rig = _Rig(_inventory(MAT_A))

    evidence = IntensifyWorkflow(rig, rig.control).dry_run(rig.plan)

    assert evidence.cancelled
    assert evidence.clean_after_cancel
    rig.control.open_confirmation.assert_not_called()
    rig.control.confirm_irreversible_once.assert_not_called()
    rig.control.execute_without_confirmation_once.assert_not_called()
    rig.control.clear_materials.assert_called_once_with()


def test_low_rarity_execute_clicks_directly_without_waiting_for_confirmation() -> None:
    rig = _Rig(_inventory(MAT_A))
    workflow = IntensifyWorkflow(rig, rig.control)
    authorization = authorize_intensify(rig.plan, workflow.dry_run(rig.plan))

    result = workflow.execute(rig.plan, authorization)

    rig.control.open_confirmation.assert_not_called()
    rig.control.confirm_irreversible_once.assert_not_called()
    rig.control.execute_without_confirmation_once.assert_called_once_with()
    assert result.target_after.stats == TARGET.stats + GAINS


def test_high_rarity_execute_requires_confirmation_path() -> None:
    rig = _Rig(_inventory(MAT_B))
    rig.plan = _plan(rig.inventory_value, MAT_B_REF)
    workflow = IntensifyWorkflow(rig, rig.control)
    authorization = authorize_intensify(rig.plan, workflow.dry_run(rig.plan))

    workflow.execute(rig.plan, authorization)

    assert rig.control.open_confirmation.call_count == 2
    rig.control.confirm_irreversible_once.assert_called_once_with()
    rig.control.execute_without_confirmation_once.assert_not_called()


def test_dry_run_fails_before_input_when_inventory_is_stale() -> None:
    rig = _Rig(_inventory(MAT_A))
    rig.inventory_value = _inventory(MAT_A, revision='changed')

    with pytest.raises(IntensifyWorkflowError, match='计划过期'):
        IntensifyWorkflow(rig, rig.control).dry_run(rig.plan)

    rig.control.open_target_selector.assert_not_called()


def test_preview_mismatch_never_opens_confirmation() -> None:
    rig = _Rig(_inventory(MAT_A))
    original = rig.control.accept_materials.side_effect

    def wrong_gain() -> None:
        original()
        rig.home_value = replace(rig.home_value, gains=ShipStats(armor=99))

    rig.control.accept_materials.side_effect = wrong_gain

    with pytest.raises(IntensifyWorkflowError, match='收益'):
        IntensifyWorkflow(rig, rig.control).dry_run(rig.plan)

    rig.control.open_confirmation.assert_not_called()
    rig.control.confirm_irreversible_once.assert_not_called()
    rig.control.clear_materials.assert_called_once_with()


def test_confirmation_mismatch_is_cancelled_and_materials_are_cleared() -> None:
    rig = _Rig(_inventory(MAT_B))
    original = rig.control.open_confirmation.side_effect

    def wrong_confirmation() -> None:
        original()
        assert rig.confirmation_value is not None
        rig.confirmation_value = replace(
            rig.confirmation_value,
            gains=ShipStats(armor=99),
        )

    rig.control.open_confirmation.side_effect = wrong_confirmation

    with pytest.raises(IntensifyWorkflowError, match='确认弹窗收益'):
        IntensifyWorkflow(rig, rig.control).dry_run(rig.plan)

    rig.control.cancel_confirmation.assert_called_once_with()
    rig.control.clear_materials.assert_called_once_with()
    rig.control.confirm_irreversible_once.assert_not_called()


def test_authorization_requires_matching_clean_dry_run() -> None:
    inventory = _inventory(MAT_A)
    plan = _plan(inventory, MAT_A_REF)

    with pytest.raises(IntensifyWorkflowError, match='取消并清空'):
        authorize_intensify(
            plan,
            DryRunEvidence(plan.fingerprint, inventory.fingerprint, True, False),
        )


def test_clean_but_forged_dry_run_evidence_cannot_authorize() -> None:
    inventory = _inventory(MAT_A)
    plan = _plan(inventory, MAT_A_REF)

    with pytest.raises(IntensifyWorkflowError, match='不是由工作流生成'):
        authorize_intensify(
            plan,
            DryRunEvidence(plan.fingerprint, inventory.fingerprint, True, True, 'forged'),
        )


def test_execute_confirms_once_and_validates_exact_consumption() -> None:
    rig = _Rig(_inventory(MAT_A, MAT_B))
    rig.plan = _plan(rig.inventory_value, MAT_B_REF)
    workflow = IntensifyWorkflow(rig, rig.control)
    evidence = workflow.dry_run(rig.plan)
    authorization = authorize_intensify(rig.plan, evidence)

    result = workflow.execute(rig.plan, authorization)

    rig.control.confirm_irreversible_once.assert_called_once_with()
    assert result.target_after.stats == TARGET.stats + GAINS
    assert result.inventory_after.occurrences == (replace(MAT_A, index=0),)

    with pytest.raises(IntensifyWorkflowError, match='授权已使用'):
        workflow.execute(rig.plan, authorization)
    rig.control.confirm_irreversible_once.assert_called_once_with()


def test_authorization_is_marked_used_before_postcondition_failure() -> None:
    rig = _Rig(_inventory(MAT_B))
    workflow = IntensifyWorkflow(rig, rig.control)
    authorization = authorize_intensify(rig.plan, workflow.dry_run(rig.plan))
    original_confirm = rig.control.confirm_irreversible_once.side_effect

    def wrong_result() -> None:
        original_confirm()
        assert rig.home_value.target is not None
        rig.home_value = replace(
            rig.home_value,
            target=replace(rig.home_value.target, stats=TARGET.stats),
        )

    rig.control.confirm_irreversible_once.side_effect = wrong_result

    with pytest.raises(IntensifyWorkflowError, match='目标属性'):
        workflow.execute(rig.plan, authorization)
    with pytest.raises(IntensifyWorkflowError, match='授权已使用'):
        workflow.execute(rig.plan, authorization)
    rig.control.confirm_irreversible_once.assert_called_once_with()


def test_authorization_cannot_replay_through_fresh_workflow_instance() -> None:
    rig = _Rig(_inventory(MAT_B))
    evidence = IntensifyWorkflow(rig, rig.control).dry_run(rig.plan)
    authorization = authorize_intensify(rig.plan, evidence)
    IntensifyWorkflow(rig, rig.control).execute(rig.plan, authorization)

    with pytest.raises(IntensifyWorkflowError, match='授权已使用'):
        IntensifyWorkflow(rig, rig.control).execute(rig.plan, authorization)


def test_authorization_is_atomically_claimed_across_concurrent_workflows() -> None:
    rig = _Rig(_inventory(MAT_B))
    authorization = authorize_intensify(
        rig.plan,
        IntensifyWorkflow(rig, rig.control).dry_run(rig.plan),
    )
    workflows = [
        IntensifyWorkflow(rig, rig.control),
        IntensifyWorkflow(rig, rig.control),
    ]

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(
            executor.map(
                lambda workflow: _execute_outcome(workflow, rig.plan, authorization),
                workflows,
            )
        )

    assert outcomes.count('claimed') == 1
    assert outcomes.count('used') == 1


def test_changed_target_observation_fails_before_material_selection() -> None:
    rig = _Rig(_inventory(MAT_A))
    original = rig.control.accept_target.side_effect

    def stale_target() -> None:
        original()
        assert rig.home_value.target is not None
        rig.home_value = replace(
            rig.home_value,
            target=replace(rig.home_value.target, level=109),
        )

    rig.control.accept_target.side_effect = stale_target

    with pytest.raises(IntensifyWorkflowError, match='选择计划目标舰'):
        IntensifyWorkflow(rig, rig.control).dry_run(rig.plan)

    rig.control.open_material_selector.assert_not_called()


def test_post_scan_inventory_must_match_removal_at_planned_occurrence() -> None:
    distinct = replace(MAT_A, identity='No.100')
    rig = _Rig(_inventory(MAT_A, MAT_B))
    rig.inventory_value = _inventory(distinct, MAT_B)
    rig.plan = _plan(rig.inventory_value, MAT_B_REF)
    workflow = IntensifyWorkflow(rig, rig.control)
    authorization = authorize_intensify(rig.plan, workflow.dry_run(rig.plan))
    original_confirm = rig.control.confirm_irreversible_once.side_effect

    def wrong_removal() -> None:
        original_confirm()
        rig.inventory_value = MaterialInventoryObservation(
            (replace(MAT_B, index=0),),
            True,
            'scan-2',
        )

    rig.control.confirm_irreversible_once.side_effect = wrong_removal

    with pytest.raises(IntensifyWorkflowError, match='库存变化'):
        workflow.execute(rig.plan, authorization)


def test_post_scan_duplicate_identity_proves_count_but_not_physical_card() -> None:
    rig = _Rig(_inventory(MAT_A, MAT_B))
    rig.plan = _plan(rig.inventory_value, MAT_B_REF)
    workflow = IntensifyWorkflow(rig, rig.control)
    authorization = authorize_intensify(rig.plan, workflow.dry_run(rig.plan))

    result = workflow.execute(rig.plan, authorization)

    assert tuple(item.identity for item in result.inventory_after.occurrences) == ('No.474',)
    assert result.inventory_after.revision != result.inventory_before.revision


def test_post_scan_inventory_requires_fresh_revision() -> None:
    rig = _Rig(_inventory(MAT_A))
    workflow = IntensifyWorkflow(rig, rig.control)
    authorization = authorize_intensify(rig.plan, workflow.dry_run(rig.plan))
    original_confirm = rig.control.execute_without_confirmation_once.side_effect

    def stale_rescan() -> None:
        original_confirm()
        rig.inventory_value = replace(rig.inventory_value, revision='scan-1')

    rig.control.execute_without_confirmation_once.side_effect = stale_rescan

    with pytest.raises(IntensifyWorkflowError, match='revision 未变化'):
        workflow.execute(rig.plan, authorization)


def _execute_outcome(
    workflow: IntensifyWorkflow,
    plan: IntensifyPlan,
    authorization: object,
) -> str:
    try:
        workflow.execute(plan, authorization)  # type: ignore[arg-type]
    except IntensifyWorkflowError as error:
        return 'used' if '授权已使用' in str(error) else 'claimed'
    return 'claimed'


class _AdapterRecognition:
    def __init__(self) -> None:
        self.state_value = IntensifyUiState.HOME

    def state(self) -> IntensifyUiState:
        return self.state_value


class _AdapterController:
    def __init__(self, recognition: _AdapterRecognition) -> None:
        self.recognition = recognition
        self.clicks: list[tuple[float, float]] = []
        self.direct_intensify = False

    def click(self, x: float, y: float) -> None:
        self.clicks.append((x, y))
        transitions = {
            (0.1070, 0.5093): IntensifyUiState.TARGET_SELECTOR,
            (0.2630, 0.3380): IntensifyUiState.MATERIAL_SELECTOR,
            (0.9115, 0.9000): IntensifyUiState.HOME,
            (0.8715, 0.8220): (
                IntensifyUiState.HOME if self.direct_intensify else IntensifyUiState.CONFIRMATION
            ),
            (0.4, 0.7): IntensifyUiState.HOME,
            (0.6, 0.7): IntensifyUiState.HOME,
        }
        self.recognition.state_value = transitions.get((x, y), self.recognition.state_value)


class _AdapterOperator:
    def __init__(
        self,
        recognition: _AdapterRecognition,
        resulting_state: IntensifyUiState,
    ) -> None:
        self.recognition = recognition
        self.resulting_state = resulting_state
        self.refs: list[SelectionRef] = []

    def select(self, ref: SelectionRef) -> None:
        self.refs.append(ref)
        self.recognition.state_value = self.resulting_state


def test_verified_control_uses_evidenced_home_coordinates_and_injected_selectors() -> None:
    recognition = _AdapterRecognition()
    ctrl = _AdapterController(recognition)
    target = _AdapterOperator(recognition, IntensifyUiState.HOME)
    material = _AdapterOperator(recognition, IntensifyUiState.MATERIAL_SELECTOR)
    adapter = VerifiedIntensifyControl(
        ctrl,
        recognition,  # type: ignore[arg-type]
        target,
        material,
        ConfirmationCoordinates(cancel=(0.4, 0.7), confirm=(0.6, 0.7)),
        interval=0,
        stable_frames=1,
    )

    adapter.open_target_selector()
    adapter.select_target(TARGET_REF)
    adapter.accept_target()
    adapter.open_material_selector()
    adapter.select_material(MAT_A_REF)
    adapter.accept_materials()
    adapter.open_confirmation()
    adapter.cancel_confirmation()

    assert ctrl.clicks == [
        (0.1070, 0.5093),
        (0.2630, 0.3380),
        (0.9115, 0.9000),
        (0.8715, 0.8220),
        (0.4, 0.7),
    ]
    assert target.refs == [TARGET_REF]
    assert material.refs == [MAT_A_REF]


def test_verified_control_refuses_second_irreversible_click() -> None:
    recognition = _AdapterRecognition()
    recognition.state_value = IntensifyUiState.CONFIRMATION
    ctrl = _AdapterController(recognition)
    operator = _AdapterOperator(recognition, IntensifyUiState.HOME)
    adapter = VerifiedIntensifyControl(
        ctrl,
        recognition,  # type: ignore[arg-type]
        operator,
        operator,
        ConfirmationCoordinates(cancel=(0.4, 0.7), confirm=(0.6, 0.7)),
        interval=0,
        stable_frames=1,
    )

    adapter.confirm_irreversible_once()
    recognition.state_value = IntensifyUiState.CONFIRMATION
    with pytest.raises(IntensifyWorkflowError, match='点击过'):
        adapter.confirm_irreversible_once()

    assert ctrl.clicks == [(0.6, 0.7)]


def test_verified_control_executes_low_rarity_path_from_home_once() -> None:
    recognition = _AdapterRecognition()
    ctrl = _AdapterController(recognition)
    ctrl.direct_intensify = True
    operator = _AdapterOperator(recognition, IntensifyUiState.HOME)
    adapter = VerifiedIntensifyControl(
        ctrl,
        recognition,  # type: ignore[arg-type]
        operator,
        operator,
        ConfirmationCoordinates(cancel=(0.4, 0.7), confirm=(0.6, 0.7)),
        interval=0,
        stable_frames=1,
    )

    adapter.execute_without_confirmation_once()

    assert ctrl.clicks == [(0.8715, 0.8220)]
    recognition.state_value = IntensifyUiState.HOME
    with pytest.raises(IntensifyWorkflowError, match='点击过'):
        adapter.execute_without_confirmation_once()
