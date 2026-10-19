from __future__ import annotations

from dataclasses import dataclass

from ..domain.plan_revision.models import (
    OccurrenceIdentityPolicy,
    PlanMutationInstruction,
    PlanMutationOperation,
)
from ..domain.plan_revision.persistence_contract import (
    AuthoritativePlanIdentity,
    AuthoritativePlanRevision,
    OccurrenceLineageKind,
    PlanHistoryClaim,
    PlanRevisionOrigin,
    RevisionDecisionLineage,
    RevisionOccurrence,
    finalize_authoritative_plan_revision,
    validate_revision_transition,
)
from ..ports.authoritative_plan_revision import (
    AuthoritativePlanRevisionRepository,
)


@dataclass(frozen=True)
class AppliedAuthoritativePlanRevision:
    identity: AuthoritativePlanIdentity
    revision: AuthoritativePlanRevision


class AuthoritativePlanRevisionNoChange(ValueError):
    pass


class AuthoritativePlanRevisionStaleCurrent(ValueError):
    pass


def prepare_authoritative_plan_revision(
    *,
    current_revision: AuthoritativePlanRevision,
    instruction: PlanMutationInstruction,
    revision_id: str,
) -> AuthoritativePlanRevision:
    if (
        not current_revision.verify_content_hash()
        or not current_revision.verify_contract_hash()
    ):
        raise ValueError("Current authoritative revision hash does not verify.")

    if not instruction.verify_content_hash():
        raise ValueError("PlanMutationInstruction hash does not verify.")

    if (
        instruction.occurrence_identity_policy
        != OccurrenceIdentityPolicy.PRESERVE_UNCHANGED
    ):
        raise ValueError(
            "P1.5 authoritative revision only supports "
            "PRESERVE_UNCHANGED occurrence identity policy."
        )

    if instruction.plan_id != current_revision.logical_plan_id:
        raise ValueError(
            "PlanMutationInstruction plan_id does not match logical plan."
        )

    if (
        instruction.expected_current_revision_id
        != current_revision.revision_id
    ):
        raise AuthoritativePlanRevisionStaleCurrent(
            "Expected current revision does not match authoritative current."
        )

    if instruction.operation == PlanMutationOperation.NO_CHANGE:
        raise AuthoritativePlanRevisionNoChange(
            "Planner instruction explicitly requests no plan change."
        )

    artifact = instruction.new_plan_artifact
    if artifact is None:
        raise ValueError(
            "Planner-created authoritative revision requires new_plan_artifact."
        )

    if not artifact.verify_integration_hash():
        raise ValueError("WorkoutPlanContractArtifact hash does not verify.")

    if (
        artifact.canonical_contract_json
        == current_revision.canonical_contract_json
    ):
        raise AuthoritativePlanRevisionNoChange(
            "Candidate contract is identical to the current authoritative contract."
        )

    previous_occurrence_ids = {
        item.occurrence_id for item in current_revision.occurrences
    }
    occurrences = tuple(
        RevisionOccurrence(
            occurrence_id=occurrence_id,
            ordinal=ordinal,
            lineage_kind=(
                OccurrenceLineageKind.PRESERVED
                if occurrence_id in previous_occurrence_ids
                else OccurrenceLineageKind.NEW
            ),
        )
        for ordinal, occurrence_id in enumerate(
            artifact.stable_occurrence_ids
        )
    )

    candidate = finalize_authoritative_plan_revision(
        revision_id=revision_id,
        logical_plan_id=current_revision.logical_plan_id,
        athlete_id=current_revision.athlete_id,
        revision_number=current_revision.revision_number + 1,
        previous_revision_id=current_revision.revision_id,
        origin=PlanRevisionOrigin.PLANNER_CREATED,
        history_claim=PlanHistoryClaim.VERIFIED_FROM_AUTHORITY_START,
        authority_established_at=current_revision.authority_established_at,
        effective_from=instruction.effective_from,
        created_at=instruction.created_at,
        contract_schema_version=artifact.ref.contract_schema_version,
        contract_json=artifact.canonical_contract_json,
        occurrences=occurrences,
        adoption_source=None,
        decision_lineage=RevisionDecisionLineage(
            context_hash=instruction.context_hash,
            decision_hash=instruction.decision_hash,
            rationale_hash=instruction.rationale_hash,
            instruction_hash=instruction.content_hash,
        ),
    )

    validate_revision_transition(
        previous=current_revision,
        candidate=candidate,
    )
    return candidate

async def apply_authoritative_plan_revision(
    *,
    current_revision: AuthoritativePlanRevision,
    instruction: PlanMutationInstruction,
    revision_id: str,
    repository: AuthoritativePlanRevisionRepository,
) -> AppliedAuthoritativePlanRevision:
    candidate = prepare_authoritative_plan_revision(
        current_revision=current_revision,
        instruction=instruction,
        revision_id=revision_id,
    )

    identity = await repository.append_revision(
        expected_current_revision_id=current_revision.revision_id,
        revision=candidate,
    )

    return AppliedAuthoritativePlanRevision(
        identity=identity,
        revision=candidate,
    )

async def apply_authoritative_plan_revision_with_repository(
    *,
    instruction: PlanMutationInstruction,
    revision_id: str,
    repository: AuthoritativePlanRevisionRepository,
    session,
) -> AppliedAuthoritativePlanRevision:
    current_revision = await repository.get_current_revision(
        logical_plan_id=instruction.plan_id,
    )
    if current_revision is None:
        raise AuthoritativePlanRevisionStaleCurrent(
            "Authoritative current revision does not exist."
        )

    prepared = prepare_authoritative_plan_revision(
        current_revision=current_revision,
        instruction=instruction,
        revision_id=revision_id,
    )

    try:
        identity = await repository.append_revision(
            expected_current_revision_id=current_revision.revision_id,
            revision=prepared,
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    return AppliedAuthoritativePlanRevision(
        identity=identity,
        revision=prepared,
    )
