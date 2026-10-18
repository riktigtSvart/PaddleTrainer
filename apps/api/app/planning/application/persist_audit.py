from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ..domain.common.serialization import canonical_json
from ..domain.context.models import AthletePlanningContextAggregate
from ..domain.persistence.audit import (
    AuditArtifactKind,
    AuditArtifactRecord,
    AuditArtifactSaveResult,
)
from ..domain.persistence.models import SnapshotSaveResult
from ..domain.persistence.snapshot_codec import encode_planning_context
from ..domain.plan_revision.models import (
    PlanMutationInstruction,
    PlanRevisionLink,
)
from ..ports.audit import PlanningAuditRepository
from ..ports.snapshots import PlanningSnapshotRepository
from .auditable_planner_run import AuditablePlannerRun


class HashVerifiableArtifact(Protocol):
    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        ...


@dataclass(frozen=True)
class PersistedPlannerRun:
    context: SnapshotSaveResult
    artifacts: tuple[AuditArtifactSaveResult, ...]


def _record(
    *,
    artifact_kind: AuditArtifactKind,
    artifact_id: str,
    athlete_id: str,
    schema_version: str,
    created_at: datetime,
    artifact: HashVerifiableArtifact,
) -> AuditArtifactRecord:
    if not artifact.verify_content_hash():
        raise ValueError(
            f"{artifact_kind.value} content hash does not verify."
        )
    return AuditArtifactRecord(
        artifact_kind=artifact_kind,
        artifact_id=artifact_id,
        athlete_id=athlete_id,
        schema_version=schema_version,
        created_at=created_at,
        content_hash_algorithm=artifact.content_hash_algorithm,
        content_hash=artifact.content_hash,
        contract_json=canonical_json(artifact),
    )


def persist_auditable_planner_run(
    *,
    context: AthletePlanningContextAggregate,
    run: AuditablePlannerRun,
    snapshots: PlanningSnapshotRepository,
    audit: PlanningAuditRepository,
) -> PersistedPlannerRun:
    if run.decision.context_hash != context.content_hash:
        raise ValueError("Run/Context hash mismatch.")
    if run.run_record.context_hash != context.content_hash:
        raise ValueError("RunRecord/Context hash mismatch.")

    context_result = snapshots.save(encode_planning_context(context))
    created_at = run.run_record.created_at
    athlete_id = context.athlete_id

    records = (
        _record(
            artifact_kind=AuditArtifactKind.PLANNER_INPUT_ENVELOPE,
            artifact_id=f"envelope:{run.envelope.content_hash}",
            athlete_id=athlete_id,
            schema_version="planner_input_envelope_v0.1",
            created_at=created_at,
            artifact=run.envelope,
        ),
        _record(
            artifact_kind=AuditArtifactKind.CANDIDATE_ACTION_SET,
            artifact_id=f"candidate_set:{run.candidate_set.content_hash}",
            athlete_id=athlete_id,
            schema_version="candidate_action_set_v0.1",
            created_at=created_at,
            artifact=run.candidate_set,
        ),
        _record(
            artifact_kind=AuditArtifactKind.PLANNING_POLICY_SET,
            artifact_id=(
                f"policy_set:{run.policy_set.policy_set_version}:"
                f"{run.policy_set.content_hash}"
            ),
            athlete_id=athlete_id,
            schema_version="planning_policy_set_v0.1",
            created_at=created_at,
            artifact=run.policy_set,
        ),
        _record(
            artifact_kind=AuditArtifactKind.PLANNER_DECISION,
            artifact_id=run.decision.decision_id,
            athlete_id=athlete_id,
            schema_version="planner_decision_v0.1",
            created_at=run.decision.created_at,
            artifact=run.decision,
        ),
        _record(
            artifact_kind=AuditArtifactKind.DECISION_RATIONALE,
            artifact_id=run.rationale.rationale_id,
            athlete_id=athlete_id,
            schema_version=run.rationale.rationale_version,
            created_at=run.rationale.created_at,
            artifact=run.rationale,
        ),
        _record(
            artifact_kind=AuditArtifactKind.PLANNER_RUN_RECORD,
            artifact_id=run.run_record.run_id,
            athlete_id=athlete_id,
            schema_version="planner_run_record_v0.1",
            created_at=run.run_record.created_at,
            artifact=run.run_record,
        ),
    )
    results = tuple(audit.save(record) for record in records)
    return PersistedPlannerRun(
        context=context_result,
        artifacts=results,
    )


def persist_plan_revision_audit(
    *,
    athlete_id: str,
    instruction: PlanMutationInstruction,
    link: PlanRevisionLink,
    audit: PlanningAuditRepository,
) -> tuple[AuditArtifactSaveResult, AuditArtifactSaveResult]:
    if link.instruction_hash != instruction.content_hash:
        raise ValueError("PlanRevisionLink/Instruction hash mismatch.")
    instruction_record = _record(
        artifact_kind=AuditArtifactKind.PLAN_MUTATION_INSTRUCTION,
        artifact_id=instruction.instruction_id,
        athlete_id=athlete_id,
        schema_version="plan_mutation_instruction_v0.1",
        created_at=instruction.created_at,
        artifact=instruction,
    )
    link_record = _record(
        artifact_kind=AuditArtifactKind.PLAN_REVISION_LINK,
        artifact_id=link.link_id,
        athlete_id=athlete_id,
        schema_version="plan_revision_link_v0.1",
        created_at=link.applied_at,
        artifact=link,
    )
    return audit.save(instruction_record), audit.save(link_record)
