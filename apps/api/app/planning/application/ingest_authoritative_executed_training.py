from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from uuid import UUID

from ..domain.common.enums import KnowledgeStatus
from ..domain.common.serialization import canonical_json
from ..domain.common.time import to_utc
from ..domain.evidence.models import EvidenceItem
from ..domain.executed_training.models import (
    AUTHORITATIVE_EXECUTED_TRAINING_SCHEMA_VERSION,
    AuthoritativeExecutedTrainingEvidence,
    ExecutedOccurrenceAssociation,
)
from ..domain.persistence.audit import (
    AuditArtifactKind,
    AuditArtifactRecord,
)
from ..ports.audit import AsyncPlanningAuditRepository
from ..ports.authoritative_occurrence_execution import (
    AuthoritativeOccurrenceExecutionLinkRepository,
)
from ..ports.authoritative_plan_execution import (
    AuthoritativePlanExecutionLinkRepository,
)
from ..ports.evidence import AsyncEvidenceRepository
from ..ports.execution_source import LockedExecutionSourceProvider
from .build_authoritative_executed_training import (
    AuthoritativeExecutedTrainingNotFound,
    assemble_authoritative_executed_training_with_repository,
)
from .project_authoritative_executed_training import (
    project_authoritative_executed_training_evidence,
)


@dataclass(frozen=True)
class AuthoritativeExecutedTrainingIngestionResult:
    artifact: AuthoritativeExecutedTrainingEvidence
    evidence: EvidenceItem
    reused_durable_artifact: bool


def _uuid_text(
    value: str,
    *,
    field_name: str,
) -> str:
    try:
        return str(UUID(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(
            f"{field_name} must be a UUID string."
        ) from exc


def authoritative_executed_training_artifact_id(
    workout_session_id: str,
) -> str:
    session_id = _uuid_text(
        workout_session_id,
        field_name="workout_session_id",
    )
    return (
        "pt-executed-training-evidence:"
        f"session:{session_id}"
    )


def _require_string(
    value: object,
    *,
    field_name: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{field_name} must be a non-empty string."
        )
    return value


def _optional_string(
    value: object,
    *,
    field_name: str,
) -> str | None:
    if value is None:
        return None
    return _require_string(
        value,
        field_name=field_name,
    )


def _require_bool(
    value: object,
    *,
    field_name: str,
) -> bool:
    if not isinstance(value, bool):
        raise ValueError(
            f"{field_name} must be boolean."
        )
    return value


def _require_datetime(
    value: object,
    *,
    field_name: str,
) -> datetime:
    if not isinstance(value, str):
        raise ValueError(
            f"{field_name} must be an ISO datetime string."
        )

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            f"{field_name} must be an ISO datetime string."
        ) from exc

    return to_utc(
        parsed,
        field_name=field_name,
    )


def _require_sha256(
    value: object,
    *,
    field_name: str,
) -> str:
    digest = _require_string(
        value,
        field_name=field_name,
    )

    if (
        len(digest) != 64
        or any(
            char not in "0123456789abcdef"
            for char in digest
        )
    ):
        raise ValueError(
            f"{field_name} must be a lowercase SHA-256 digest."
        )

    return digest


def _require_window(
    value: object,
    *,
    field_name: str,
) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(
            f"{field_name} must contain two numeric values."
        )

    left = value[0]
    right = value[1]

    for item in (left, right):
        if (
            isinstance(item, bool)
            or not isinstance(item, (int, float))
        ):
            raise ValueError(
                f"{field_name} must contain numeric values."
            )

    if left > right:
        raise ValueError(
            f"{field_name} lower bound must not exceed upper bound."
        )

    # Preserve int-vs-float representation from the canonical contract.
    return (left, right)


def _restore_association(
    raw: object,
) -> ExecutedOccurrenceAssociation:
    if not isinstance(raw, dict):
        raise ValueError(
            "Executed occurrence association must be an object."
        )

    association = ExecutedOccurrenceAssociation(
        occurrence_execution_link_id=_require_string(
            raw.get("occurrence_execution_link_id"),
            field_name="occurrence_execution_link_id",
        ),
        occurrence_execution_link_content_hash=_require_sha256(
            raw.get(
                "occurrence_execution_link_content_hash"
            ),
            field_name=(
                "occurrence_execution_link_content_hash"
            ),
        ),
        authoritative_occurrence_id=_require_string(
            raw.get("authoritative_occurrence_id"),
            field_name="authoritative_occurrence_id",
        ),
        link_basis=_require_string(
            raw.get("link_basis"),
            field_name="link_basis",
        ),
        phase_reconciliation_artifact_id=_require_string(
            raw.get("phase_reconciliation_artifact_id"),
            field_name="phase_reconciliation_artifact_id",
        ),
        phase_reconciliation_rules_version=_require_string(
            raw.get("phase_reconciliation_rules_version"),
            field_name="phase_reconciliation_rules_version",
        ),
        stable_source_occurrence_id=_require_string(
            raw.get("stable_source_occurrence_id"),
            field_name="stable_source_occurrence_id",
        ),
        captured_contract_occurrence_id=_require_string(
            raw.get("captured_contract_occurrence_id"),
            field_name="captured_contract_occurrence_id",
        ),
        hypothesis_id=_require_string(
            raw.get("hypothesis_id"),
            field_name="hypothesis_id",
        ),
        candidate_start_window_s=_require_window(
            raw.get("candidate_start_window_s"),
            field_name="candidate_start_window_s",
        ),
        candidate_completion_window_s=_require_window(
            raw.get("candidate_completion_window_s"),
            field_name="candidate_completion_window_s",
        ),
        clock_domain=_require_string(
            raw.get("clock_domain"),
            field_name="clock_domain",
        ),
        confirmation_id=_require_string(
            raw.get("confirmation_id"),
            field_name="confirmation_id",
        ),
        confirmation_submitted_at=_require_datetime(
            raw.get("confirmation_submitted_at"),
            field_name="confirmation_submitted_at",
        ),
        occurrence_alignment_status=_require_string(
            raw.get("occurrence_alignment_status"),
            field_name="occurrence_alignment_status",
        ),
        provider_event_verified=_require_bool(
            raw.get("provider_event_verified"),
            field_name="provider_event_verified",
        ),
        clock_alignment_verified=_require_bool(
            raw.get("clock_alignment_verified"),
            field_name="clock_alignment_verified",
        ),
        actual_boundary_verified=_require_bool(
            raw.get("actual_boundary_verified"),
            field_name="actual_boundary_verified",
        ),
        temporal_match_used=_require_bool(
            raw.get("temporal_match_used"),
            field_name="temporal_match_used",
        ),
    )

    if (
        association.link_basis
        != "user_confirmed_candidate_segment"
        or association.occurrence_alignment_status
        != "user_confirmed_candidate_segment"
        or association.provider_event_verified is not False
        or association.clock_alignment_verified is not False
        or association.actual_boundary_verified is not False
        or association.temporal_match_used is not False
    ):
        raise ValueError(
            "Persisted occurrence association claims stronger "
            "authority than P1.7 permits."
        )

    return association


def _restore_audit_artifact(
    record: AuditArtifactRecord,
) -> AuthoritativeExecutedTrainingEvidence:
    if (
        record.artifact_kind
        != AuditArtifactKind.AUTHORITATIVE_EXECUTED_TRAINING
    ):
        raise ValueError(
            "Unexpected executed-training audit artifact kind."
        )

    try:
        raw = json.loads(record.contract_json)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Executed-training audit contract is not valid JSON."
        ) from exc

    if not isinstance(raw, dict):
        raise ValueError(
            "Executed-training audit contract must be an object."
        )

    raw_associations = raw.get("occurrence_associations")

    if not isinstance(raw_associations, list):
        raise ValueError(
            "occurrence_associations must be a list."
        )

    duration_s = raw.get("duration_s")

    if duration_s is not None:
        if (
            isinstance(duration_s, bool)
            or not isinstance(duration_s, int)
        ):
            raise ValueError(
                "duration_s must be an integer or null."
            )

    artifact = AuthoritativeExecutedTrainingEvidence(
        artifact_id=_require_string(
            raw.get("artifact_id"),
            field_name="artifact_id",
        ),
        schema_version=_require_string(
            raw.get("schema_version"),
            field_name="schema_version",
        ),
        athlete_id=_require_string(
            raw.get("athlete_id"),
            field_name="athlete_id",
        ),
        workout_session_id=_require_string(
            raw.get("workout_session_id"),
            field_name="workout_session_id",
        ),
        observed_at=_require_datetime(
            raw.get("observed_at"),
            field_name="observed_at",
        ),
        modality_key=_require_string(
            raw.get("modality_key"),
            field_name="modality_key",
        ),
        duration_status=KnowledgeStatus(
            _require_string(
                raw.get("duration_status"),
                field_name="duration_status",
            )
        ),
        duration_s=duration_s,
        plan_execution_link_id=_require_string(
            raw.get("plan_execution_link_id"),
            field_name="plan_execution_link_id",
        ),
        plan_execution_link_content_hash=_require_sha256(
            raw.get("plan_execution_link_content_hash"),
            field_name="plan_execution_link_content_hash",
        ),
        logical_plan_id=_require_string(
            raw.get("logical_plan_id"),
            field_name="logical_plan_id",
        ),
        observed_revision_id=_require_string(
            raw.get("observed_revision_id"),
            field_name="observed_revision_id",
        ),
        observed_revision_content_hash=_require_sha256(
            raw.get("observed_revision_content_hash"),
            field_name="observed_revision_content_hash",
        ),
        source_workout_id=_require_string(
            raw.get("source_workout_id"),
            field_name="source_workout_id",
        ),
        source_workout_content_hash=_require_sha256(
            raw.get("source_workout_content_hash"),
            field_name="source_workout_content_hash",
        ),
        session_source_content_hash=_require_sha256(
            raw.get("session_source_content_hash"),
            field_name="session_source_content_hash",
        ),
        execution_link_basis=_require_string(
            raw.get("execution_link_basis"),
            field_name="execution_link_basis",
        ),
        provider_target_id=_optional_string(
            raw.get("provider_target_id"),
            field_name="provider_target_id",
        ),
        plan_identity_linked=_require_bool(
            raw.get("plan_identity_linked"),
            field_name="plan_identity_linked",
        ),
        plan_content_at_execution_status=_require_string(
            raw.get("plan_content_at_execution_status"),
            field_name="plan_content_at_execution_status",
        ),
        occurrence_associations=tuple(
            _restore_association(item)
            for item in raw_associations
        ),
        occurrence_alignment_verified=_require_bool(
            raw.get("occurrence_alignment_verified"),
            field_name="occurrence_alignment_verified",
        ),
        phase_alignment_verified=_require_bool(
            raw.get("phase_alignment_verified"),
            field_name="phase_alignment_verified",
        ),
        provider_event_verified=_require_bool(
            raw.get("provider_event_verified"),
            field_name="provider_event_verified",
        ),
        clock_alignment_verified=_require_bool(
            raw.get("clock_alignment_verified"),
            field_name="clock_alignment_verified",
        ),
        actual_boundary_verified=_require_bool(
            raw.get("actual_boundary_verified"),
            field_name="actual_boundary_verified",
        ),
        temporal_match_used=_require_bool(
            raw.get("temporal_match_used"),
            field_name="temporal_match_used",
        ),
        created_at=_require_datetime(
            raw.get("created_at"),
            field_name="created_at",
        ),
        content_hash_algorithm=_require_string(
            raw.get("content_hash_algorithm"),
            field_name="content_hash_algorithm",
        ),
        content_hash=_require_sha256(
            raw.get("content_hash"),
            field_name="content_hash",
        ),
    )

    if (
        artifact.schema_version
        != AUTHORITATIVE_EXECUTED_TRAINING_SCHEMA_VERSION
    ):
        raise ValueError(
            "Unsupported persisted authoritative executed-training "
            "schema."
        )

    if (
        artifact.artifact_id != record.artifact_id
        or artifact.athlete_id != record.athlete_id
        or artifact.content_hash_algorithm
        != record.content_hash_algorithm
        or artifact.content_hash != record.content_hash
        or artifact.created_at
        != to_utc(
            record.created_at,
            field_name="record.created_at",
        )
    ):
        raise ValueError(
            "Executed-training audit record metadata does not "
            "match its canonical contract."
        )

    if (
        artifact.plan_identity_linked is not True
        or artifact.plan_content_at_execution_status
        != "unverified"
        or artifact.occurrence_alignment_verified is not False
        or artifact.phase_alignment_verified is not False
        or artifact.provider_event_verified is not False
        or artifact.clock_alignment_verified is not False
        or artifact.actual_boundary_verified is not False
        or artifact.temporal_match_used is not False
    ):
        raise ValueError(
            "Persisted executed-training artifact claims stronger "
            "authority than P1.7 permits."
        )

    if not artifact.verify_content_hash():
        raise ValueError(
            "Persisted authoritative executed-training content hash "
            "does not verify."
        )

    if canonical_json(artifact) != record.contract_json:
        raise ValueError(
            "Persisted authoritative executed-training contract "
            "does not round-trip canonically."
        )

    return artifact


def restore_authoritative_executed_training_audit_artifact(
    record: AuditArtifactRecord,
) -> AuthoritativeExecutedTrainingEvidence:
    """Restore and fully verify one durable P1.7 audit artifact."""

    return _restore_audit_artifact(record)


def _audit_record(
    artifact: AuthoritativeExecutedTrainingEvidence,
) -> AuditArtifactRecord:
    if not artifact.verify_content_hash():
        raise ValueError(
            "Authoritative executed-training artifact hash "
            "does not verify."
        )

    return AuditArtifactRecord(
        artifact_kind=(
            AuditArtifactKind.AUTHORITATIVE_EXECUTED_TRAINING
        ),
        artifact_id=artifact.artifact_id,
        athlete_id=artifact.athlete_id,
        schema_version=artifact.schema_version,
        created_at=artifact.created_at,
        content_hash_algorithm=(
            artifact.content_hash_algorithm
        ),
        content_hash=artifact.content_hash,
        contract_json=canonical_json(artifact),
    )


async def ingest_authoritative_executed_training(
    *,
    athlete_id: str,
    workout_session_id: str,
    execution_link_repository:
        AuthoritativePlanExecutionLinkRepository,
    occurrence_execution_repository:
        AuthoritativeOccurrenceExecutionLinkRepository,
    execution_source: LockedExecutionSourceProvider,
    audit_repository: AsyncPlanningAuditRepository,
    evidence_repository: AsyncEvidenceRepository,
    session,
    created_at: datetime | None = None,
) -> AuthoritativeExecutedTrainingIngestionResult:
    """Freeze one session exposure exactly once and persist it atomically.

    The first durable authoritative executed-training artifact wins for a
    workout session. Retries read that immutable freeze and never recapture
    mutable WorkoutSession or plan-source state.

    Artifact persistence and its EvidenceItem projection share one transaction.
    """

    canonical_athlete_id = _uuid_text(
        athlete_id,
        field_name="athlete_id",
    )
    canonical_session_id = _uuid_text(
        workout_session_id,
        field_name="workout_session_id",
    )

    artifact_id = (
        authoritative_executed_training_artifact_id(
            canonical_session_id
        )
    )

    materialized_at = to_utc(
        created_at or datetime.now(timezone.utc),
        field_name="created_at",
    )

    try:
        existing = await audit_repository.get(
            artifact_kind=(
                AuditArtifactKind.AUTHORITATIVE_EXECUTED_TRAINING
            ),
            artifact_id=artifact_id,
        )

        if existing is not None:
            # Do not disclose another athlete's durable session evidence.
            if existing.athlete_id != canonical_athlete_id:
                raise AuthoritativeExecutedTrainingNotFound(
                    "Authoritative execution evidence not found."
                )

            artifact = _restore_audit_artifact(existing)

            if (
                artifact.athlete_id != canonical_athlete_id
                or artifact.workout_session_id
                != canonical_session_id
                or artifact.artifact_id != artifact_id
            ):
                raise ValueError(
                    "Durable executed-training artifact identity "
                    "does not match the requested session."
                )

            reused = True

        else:
            artifact = await (
                assemble_authoritative_executed_training_with_repository(
                    athlete_id=canonical_athlete_id,
                    workout_session_id=canonical_session_id,
                    execution_link_repository=(
                        execution_link_repository
                    ),
                    occurrence_execution_repository=(
                        occurrence_execution_repository
                    ),
                    execution_source=execution_source,
                    session=session,
                    created_at=materialized_at,
                    id_factory=lambda: (
                        f"session:{canonical_session_id}"
                    ),
                )
            )

            if artifact.artifact_id != artifact_id:
                raise ValueError(
                    "Executed-training assembler did not preserve "
                    "the stable durable artifact identity."
                )

            await audit_repository.save(
                _audit_record(artifact)
            )

            reused = False

        projection_created_at = max(
            materialized_at,
            artifact.created_at,
        )

        projected = (
            project_authoritative_executed_training_evidence(
                artifact,
                created_at=projection_created_at,
            )
        )

        persisted_evidence = await evidence_repository.save(
            projected
        )

        await session.commit()

        return AuthoritativeExecutedTrainingIngestionResult(
            artifact=artifact,
            evidence=persisted_evidence,
            reused_durable_artifact=reused,
        )

    except Exception:
        await session.rollback()
        raise
