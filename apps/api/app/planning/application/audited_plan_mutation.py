from __future__ import annotations

import json
from datetime import datetime

from ..domain.common.serialization import canonical_json
from ..domain.persistence.audit import AuditArtifactKind
from ..domain.plan_revision.models import (
    OccurrenceIdentityPolicy,
    PlanMutationInstruction,
    PlanMutationOperation,
    create_workout_plan_contract_artifact,
    finalize_plan_mutation_instruction,
)
from ..ports.audit import AsyncPlanningAuditRepository


EXPECTED_INSTRUCTION_SCHEMA = "plan_mutation_instruction_v0.1"


class AuditedPlanMutationInstructionError(ValueError):
    pass


class AuditedPlanMutationInstructionNotFound(LookupError):
    pass


def _datetime_from_contract(
    value,
    *,
    field_name: str,
) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise AuditedPlanMutationInstructionError(
            f"{field_name} must be an ISO-8601 datetime string."
        )

    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise AuditedPlanMutationInstructionError(
            f"{field_name} is not a valid ISO-8601 datetime."
        ) from exc

    if parsed.tzinfo is None:
        raise AuditedPlanMutationInstructionError(
            f"{field_name} must be timezone-aware."
        )

    return parsed


def _artifact_from_contract(raw):
    if raw is None:
        return None

    if not isinstance(raw, dict):
        raise AuditedPlanMutationInstructionError(
            "new_plan_artifact must be an object or null."
        )

    ref = raw.get("ref")
    if not isinstance(ref, dict):
        raise AuditedPlanMutationInstructionError(
            "new_plan_artifact.ref must be an object."
        )

    try:
        artifact = create_workout_plan_contract_artifact(
            plan_id=ref["plan_id"],
            revision_id=ref["revision_id"],
            contract_schema_version=(
                ref["contract_schema_version"]
            ),
            contract_json=raw["canonical_contract_json"],
            stable_occurrence_ids=tuple(
                raw["stable_occurrence_ids"]
            ),
            external_content_hash=raw.get(
                "external_content_hash"
            ),
        )
    except (
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise AuditedPlanMutationInstructionError(
            "Audited workout plan artifact is invalid."
        ) from exc

    if (
        artifact.ref.integration_content_hash
        != ref.get("integration_content_hash")
    ):
        raise AuditedPlanMutationInstructionError(
            "Audited workout plan artifact hash does not verify."
        )

    return artifact


async def load_audited_plan_mutation_instruction(
    *,
    instruction_id: str,
    expected_athlete_id: str,
    expected_plan_id: str,
    audit_repository: AsyncPlanningAuditRepository,
) -> PlanMutationInstruction:
    record = await audit_repository.get(
        artifact_kind=(
            AuditArtifactKind.PLAN_MUTATION_INSTRUCTION
        ),
        artifact_id=instruction_id,
    )

    if record is None:
        raise AuditedPlanMutationInstructionNotFound(
            "Plan mutation instruction audit artifact not found."
        )

    # Owner-scoped lookup: do not expose another athlete's artifact.
    if record.athlete_id != expected_athlete_id:
        raise AuditedPlanMutationInstructionNotFound(
            "Plan mutation instruction audit artifact not found."
        )

    if record.schema_version != EXPECTED_INSTRUCTION_SCHEMA:
        raise AuditedPlanMutationInstructionError(
            "Unsupported plan mutation instruction schema."
        )

    try:
        raw = json.loads(record.contract_json)
    except json.JSONDecodeError as exc:
        raise AuditedPlanMutationInstructionError(
            "Audited plan mutation instruction JSON is invalid."
        ) from exc

    if not isinstance(raw, dict):
        raise AuditedPlanMutationInstructionError(
            "Audited plan mutation instruction must be an object."
        )

    if raw.get("instruction_id") != instruction_id:
        raise AuditedPlanMutationInstructionError(
            "Audit artifact ID/instruction ID mismatch."
        )

    if raw.get("plan_id") != expected_plan_id:
        raise AuditedPlanMutationInstructionError(
            "Audited instruction targets a different logical plan."
        )

    try:
        instruction = finalize_plan_mutation_instruction(
            instruction_id=raw["instruction_id"],
            operation=PlanMutationOperation(
                raw["operation"]
            ),
            decision_hash=raw["decision_hash"],
            rationale_hash=raw["rationale_hash"],
            context_hash=raw["context_hash"],
            selected_action_id=raw.get(
                "selected_action_id"
            ),
            plan_id=raw["plan_id"],
            expected_current_revision_id=raw.get(
                "expected_current_revision_id"
            ),
            new_plan_artifact=_artifact_from_contract(
                raw.get("new_plan_artifact")
            ),
            occurrence_identity_policy=(
                OccurrenceIdentityPolicy(
                    raw["occurrence_identity_policy"]
                )
            ),
            effective_from=_datetime_from_contract(
                raw["effective_from"],
                field_name="effective_from",
            ),
            created_at=_datetime_from_contract(
                raw["created_at"],
                field_name="created_at",
            ),
        )
    except AuditedPlanMutationInstructionError:
        raise
    except (
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise AuditedPlanMutationInstructionError(
            "Audited plan mutation instruction cannot be reconstructed."
        ) from exc

    if (
        raw.get("content_hash_algorithm")
        != instruction.content_hash_algorithm
        or record.content_hash_algorithm
        != instruction.content_hash_algorithm
    ):
        raise AuditedPlanMutationInstructionError(
            "Plan mutation instruction hash algorithm mismatch."
        )

    if (
        raw.get("content_hash")
        != instruction.content_hash
        or record.content_hash
        != instruction.content_hash
    ):
        raise AuditedPlanMutationInstructionError(
            "Plan mutation instruction content hash does not verify."
        )

    # Strongest round-trip check: reconstructed canonical contract must be
    # byte-for-byte equivalent to the immutable audit representation.
    if canonical_json(instruction) != record.contract_json:
        raise AuditedPlanMutationInstructionError(
            "Plan mutation instruction audit contract does not round-trip."
        )

    return instruction
