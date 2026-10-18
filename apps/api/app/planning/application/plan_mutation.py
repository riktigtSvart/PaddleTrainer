from datetime import datetime

from ..domain.decision.models import (
    PlannerActionType,
    PlannerDecision,
    PlannerDecisionStatus,
)
from ..domain.plan_revision.models import (
    OccurrenceIdentityPolicy,
    PlanMutationOperation,
    PlanRevisionApplyStatus,
    PlanRevisionLink,
    WorkoutPlanContractArtifact,
    finalize_plan_mutation_instruction,
    finalize_plan_revision_link,
)
from ..domain.rationale.models import DecisionRationale
from ..ports.workout_plan import WorkoutPlanRevisionGateway


class PlanMutationNotAuthorized(ValueError):
    pass


def build_plan_mutation_instruction(
    *,
    instruction_id: str,
    decision: PlannerDecision,
    rationale: DecisionRationale,
    operation: PlanMutationOperation,
    plan_id: str,
    expected_current_revision_id: str | None,
    new_plan_artifact: WorkoutPlanContractArtifact | None,
    effective_from: datetime,
    created_at: datetime,
) :
    if not decision.verify_content_hash():
        raise ValueError("PlannerDecision hash does not verify.")
    if not rationale.verify_content_hash():
        raise ValueError("DecisionRationale hash does not verify.")
    if rationale.decision_hash != decision.content_hash:
        raise ValueError("Rationale/decision hash mismatch.")
    if rationale.context_hash != decision.context_hash:
        raise ValueError("Rationale/decision context mismatch.")

    if operation == PlanMutationOperation.NO_CHANGE:
        if decision.status != PlannerDecisionStatus.NO_CHANGE:
            raise PlanMutationNotAuthorized(
                "NO_CHANGE mutation requires NO_CHANGE planner decision."
            )
        selected_action_id = (
            decision.selected_action.action_id
            if decision.selected_action is not None
            else None
        )
    else:
        if decision.status not in {
            PlannerDecisionStatus.DECIDED,
            PlannerDecisionStatus.DECIDED_WITH_CONSTRAINTS,
        }:
            raise PlanMutationNotAuthorized(
                "Planner decision status does not authorize plan mutation."
            )
        action = decision.selected_action
        if action is None:
            raise PlanMutationNotAuthorized(
                "Plan mutation requires a selected planner action."
            )
        if not action.plan_mutation_authorized:
            raise PlanMutationNotAuthorized(
                "Selected planner action is not authorized to mutate plan."
            )
        if action.action_type != PlannerActionType.SELECT_WORKOUT_FAMILY:
            raise PlanMutationNotAuthorized(
                "P0.10 only links selected workout-family actions to plan "
                "revisions."
            )
        selected_action_id = action.action_id

    return finalize_plan_mutation_instruction(
        instruction_id=instruction_id,
        operation=operation,
        decision_hash=decision.content_hash,
        rationale_hash=rationale.content_hash,
        context_hash=decision.context_hash,
        selected_action_id=selected_action_id,
        plan_id=plan_id,
        expected_current_revision_id=expected_current_revision_id,
        new_plan_artifact=new_plan_artifact,
        occurrence_identity_policy=(
            OccurrenceIdentityPolicy.PRESERVE_UNCHANGED
        ),
        effective_from=effective_from,
        created_at=created_at,
    )


def apply_plan_mutation(
    *,
    link_id: str,
    instruction,
    gateway: WorkoutPlanRevisionGateway,
    applied_at: datetime,
) -> tuple[object, PlanRevisionLink | None]:
    result = gateway.apply(instruction)

    if result.status == PlanRevisionApplyStatus.NO_CHANGE:
        return result, None

    if result.artifact is None:
        raise ValueError("Created plan revision requires an artifact.")

    link = finalize_plan_revision_link(
        link_id=link_id,
        instruction=instruction,
        plan_ref=result.artifact.ref,
        previous_revision_id=result.previous_revision_id,
        gateway_version=gateway.gateway_version,
        applied_at=applied_at,
    )
    return result, link
