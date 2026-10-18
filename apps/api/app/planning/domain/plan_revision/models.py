from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import json

from ..common.serialization import (
    CONTENT_HASH_ALGORITHM,
    canonical_json,
    compute_content_hash,
)
from ..common.time import to_utc


PLAN_ARTIFACT_HASH_EXCLUDE_FIELDS = frozenset({"integration_content_hash"})
PLAN_MUTATION_HASH_EXCLUDE_FIELDS = frozenset(
    {"content_hash", "instruction_id", "created_at"}
)
PLAN_REVISION_LINK_HASH_EXCLUDE_FIELDS = frozenset(
    {"content_hash", "link_id", "applied_at"}
)


class PlanMutationOperation(StrEnum):
    ADD = "add"
    REMOVE = "remove"
    REPLACE = "replace"
    MOVE = "move"
    MODIFY = "modify"
    NO_CHANGE = "no_change"


class OccurrenceIdentityPolicy(StrEnum):
    PRESERVE_UNCHANGED = "preserve_unchanged"
    NEW_FOR_NEW_OCCURRENCES = "new_for_new_occurrences"


class PlanRevisionApplyStatus(StrEnum):
    CREATED = "created"
    NO_CHANGE = "no_change"


class PlanRevisionConflictError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkoutPlanContractRef:
    plan_id: str
    revision_id: str
    contract_schema_version: str
    integration_content_hash: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("plan_id", self.plan_id),
            ("revision_id", self.revision_id),
            ("contract_schema_version", self.contract_schema_version),
            ("integration_content_hash", self.integration_content_hash),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must be non-empty.")


@dataclass(frozen=True)
class WorkoutPlanContractArtifact:
    """Planning-side immutable wrapper around an external WorkoutPlanContract.

    The planning core does not redefine the WorkoutPlanContract schema. The
    canonical contract JSON is treated as the boundary artifact. The
    integration hash is local to this bridge and can coexist with any content
    hash owned by the workout-contract implementation itself.
    """

    ref: WorkoutPlanContractRef
    canonical_contract_json: str
    stable_occurrence_ids: tuple[str, ...]
    external_content_hash: str | None

    def verify_integration_hash(self) -> bool:
        parsed = json.loads(self.canonical_contract_json)
        normalized = canonical_json(parsed)
        expected = compute_content_hash(
            {
                "plan_id": self.ref.plan_id,
                "revision_id": self.ref.revision_id,
                "contract_schema_version": self.ref.contract_schema_version,
                "canonical_contract_json": normalized,
                "stable_occurrence_ids": self.stable_occurrence_ids,
                "external_content_hash": self.external_content_hash,
            }
        )
        return expected == self.ref.integration_content_hash


def create_workout_plan_contract_artifact(
    *,
    plan_id: str,
    revision_id: str,
    contract_schema_version: str,
    contract_json: str,
    stable_occurrence_ids: tuple[str, ...],
    external_content_hash: str | None = None,
) -> WorkoutPlanContractArtifact:
    for field_name, value in (
        ("plan_id", plan_id),
        ("revision_id", revision_id),
        ("contract_schema_version", contract_schema_version),
    ):
        if not value.strip():
            raise ValueError(f"{field_name} must be non-empty.")

    parsed = json.loads(contract_json)
    normalized = canonical_json(parsed)

    if len(stable_occurrence_ids) != len(set(stable_occurrence_ids)):
        raise ValueError("stable_occurrence_ids must be unique.")
    if any(not item.strip() for item in stable_occurrence_ids):
        raise ValueError("stable_occurrence_ids must be non-empty strings.")

    digest = compute_content_hash(
        {
            "plan_id": plan_id,
            "revision_id": revision_id,
            "contract_schema_version": contract_schema_version,
            "canonical_contract_json": normalized,
            "stable_occurrence_ids": tuple(stable_occurrence_ids),
            "external_content_hash": external_content_hash,
        }
    )
    ref = WorkoutPlanContractRef(
        plan_id=plan_id,
        revision_id=revision_id,
        contract_schema_version=contract_schema_version,
        integration_content_hash=digest,
    )
    return WorkoutPlanContractArtifact(
        ref=ref,
        canonical_contract_json=normalized,
        stable_occurrence_ids=tuple(stable_occurrence_ids),
        external_content_hash=external_content_hash,
    )


@dataclass(frozen=True)
class PlanMutationInstruction:
    instruction_id: str
    operation: PlanMutationOperation

    decision_hash: str
    rationale_hash: str
    context_hash: str
    selected_action_id: str | None

    plan_id: str
    expected_current_revision_id: str | None
    new_plan_artifact: WorkoutPlanContractArtifact | None

    occurrence_identity_policy: OccurrenceIdentityPolicy
    effective_from: datetime
    created_at: datetime

    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(
                self,
                exclude_fields=PLAN_MUTATION_HASH_EXCLUDE_FIELDS,
            )
            == self.content_hash
        )


def finalize_plan_mutation_instruction(
    *,
    instruction_id: str,
    operation: PlanMutationOperation,
    decision_hash: str,
    rationale_hash: str,
    context_hash: str,
    selected_action_id: str | None,
    plan_id: str,
    expected_current_revision_id: str | None,
    new_plan_artifact: WorkoutPlanContractArtifact | None,
    occurrence_identity_policy: OccurrenceIdentityPolicy,
    effective_from: datetime,
    created_at: datetime,
) -> PlanMutationInstruction:
    if not instruction_id.strip():
        raise ValueError("instruction_id must be non-empty.")
    if not plan_id.strip():
        raise ValueError("plan_id must be non-empty.")
    for name, value in (
        ("decision_hash", decision_hash),
        ("rationale_hash", rationale_hash),
        ("context_hash", context_hash),
    ):
        if not value.strip():
            raise ValueError(f"{name} must be non-empty.")

    if operation == PlanMutationOperation.NO_CHANGE:
        if new_plan_artifact is not None:
            raise ValueError("NO_CHANGE must not carry new_plan_artifact.")
    elif operation == PlanMutationOperation.REMOVE:
        if new_plan_artifact is not None:
            raise ValueError("REMOVE must not carry new_plan_artifact.")
    else:
        if new_plan_artifact is None:
            raise ValueError(
                f"{operation.value} requires new_plan_artifact in P0.10."
            )
        if new_plan_artifact.ref.plan_id != plan_id:
            raise ValueError("new_plan_artifact plan_id mismatch.")
        if not new_plan_artifact.verify_integration_hash():
            raise ValueError("WorkoutPlanContractArtifact hash does not verify.")

    effective = to_utc(effective_from, field_name="effective_from")
    created = to_utc(created_at, field_name="created_at")

    provisional = PlanMutationInstruction(
        instruction_id=instruction_id,
        operation=operation,
        decision_hash=decision_hash,
        rationale_hash=rationale_hash,
        context_hash=context_hash,
        selected_action_id=selected_action_id,
        plan_id=plan_id,
        expected_current_revision_id=expected_current_revision_id,
        new_plan_artifact=new_plan_artifact,
        occurrence_identity_policy=occurrence_identity_policy,
        effective_from=effective,
        created_at=created,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )
    digest = compute_content_hash(
        provisional,
        exclude_fields=PLAN_MUTATION_HASH_EXCLUDE_FIELDS,
    )
    return PlanMutationInstruction(
        instruction_id=provisional.instruction_id,
        operation=provisional.operation,
        decision_hash=provisional.decision_hash,
        rationale_hash=provisional.rationale_hash,
        context_hash=provisional.context_hash,
        selected_action_id=provisional.selected_action_id,
        plan_id=provisional.plan_id,
        expected_current_revision_id=provisional.expected_current_revision_id,
        new_plan_artifact=provisional.new_plan_artifact,
        occurrence_identity_policy=provisional.occurrence_identity_policy,
        effective_from=provisional.effective_from,
        created_at=provisional.created_at,
        content_hash_algorithm=provisional.content_hash_algorithm,
        content_hash=digest,
    )


@dataclass(frozen=True)
class PlanRevisionLink:
    link_id: str
    instruction_hash: str
    decision_hash: str
    rationale_hash: str
    context_hash: str
    plan_ref: WorkoutPlanContractRef
    previous_revision_id: str | None
    gateway_version: str
    applied_at: datetime
    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(
                self,
                exclude_fields=PLAN_REVISION_LINK_HASH_EXCLUDE_FIELDS,
            )
            == self.content_hash
        )


def finalize_plan_revision_link(
    *,
    link_id: str,
    instruction: PlanMutationInstruction,
    plan_ref: WorkoutPlanContractRef,
    previous_revision_id: str | None,
    gateway_version: str,
    applied_at: datetime,
) -> PlanRevisionLink:
    if not instruction.verify_content_hash():
        raise ValueError("PlanMutationInstruction hash does not verify.")
    if not link_id.strip():
        raise ValueError("link_id must be non-empty.")
    if not gateway_version.strip():
        raise ValueError("gateway_version must be non-empty.")

    applied = to_utc(applied_at, field_name="applied_at")
    provisional = PlanRevisionLink(
        link_id=link_id,
        instruction_hash=instruction.content_hash,
        decision_hash=instruction.decision_hash,
        rationale_hash=instruction.rationale_hash,
        context_hash=instruction.context_hash,
        plan_ref=plan_ref,
        previous_revision_id=previous_revision_id,
        gateway_version=gateway_version,
        applied_at=applied,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )
    digest = compute_content_hash(
        provisional,
        exclude_fields=PLAN_REVISION_LINK_HASH_EXCLUDE_FIELDS,
    )
    return PlanRevisionLink(
        link_id=provisional.link_id,
        instruction_hash=provisional.instruction_hash,
        decision_hash=provisional.decision_hash,
        rationale_hash=provisional.rationale_hash,
        context_hash=provisional.context_hash,
        plan_ref=provisional.plan_ref,
        previous_revision_id=provisional.previous_revision_id,
        gateway_version=provisional.gateway_version,
        applied_at=provisional.applied_at,
        content_hash_algorithm=provisional.content_hash_algorithm,
        content_hash=digest,
    )


@dataclass(frozen=True)
class PlanRevisionApplyResult:
    status: PlanRevisionApplyStatus
    artifact: WorkoutPlanContractArtifact | None
    previous_revision_id: str | None
