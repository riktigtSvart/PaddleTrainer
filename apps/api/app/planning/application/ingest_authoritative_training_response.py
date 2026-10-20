from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from uuid import UUID

from ..domain.common.enums import (
    KnowledgeStatus,
    ProvenanceKind,
)
from ..domain.common.serialization import canonical_json
from ..domain.common.time import to_utc
from ..domain.evidence.models import (
    EvidenceItem,
    EvidenceQuality,
)
from ..domain.persistence.audit import (
    AuditArtifactKind,
    AuditArtifactRecord,
)
from ..domain.response_evidence import (
    TRAINING_RESPONSE_EVIDENCE_SCHEMA_V02,
    AuthoritativeTrainingResponseEvidence,
    TrainingResponseInterpretation,
    TrainingResponseKind,
    TrainingResponseLinkBasis,
    TrainingResponseMeasurement,
    TrainingResponseTiming,
)
from ..ports.audit import AsyncPlanningAuditRepository
from ..ports.evidence import AsyncEvidenceRepository
from ..ports.training_response_source import (
    LockedTrainingResponseSourceProvider,
)
from .build_authoritative_training_response import (
    assemble_authoritative_training_response_from_capture,
)
from .ingest_authoritative_executed_training import (
    authoritative_executed_training_artifact_id,
    restore_authoritative_executed_training_audit_artifact,
)
from .project_authoritative_training_response import (
    project_authoritative_training_response_evidence,
)


@dataclass(frozen=True)
class AuthoritativeTrainingResponseIngestionResult:
    artifact: AuthoritativeTrainingResponseEvidence
    evidence: EvidenceItem
    reused_durable_artifact: bool


class AuthoritativeTrainingResponseNotFound(LookupError):
    pass


class AuthoritativeTrainingResponseExecutionNotFound(LookupError):
    pass


def _uuid_text(
    value: str,
    *,
    field_name: str,
) -> str:
    try:
        parsed = UUID(value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(
            f"{field_name} must be a UUID string."
        ) from exc

    canonical = str(parsed)

    if canonical != value:
        raise ValueError(
            f"{field_name} must be a canonical UUID string."
        )

    return canonical


def authoritative_training_response_artifact_id(
    response_source_id: str,
) -> str:
    response_id = _uuid_text(
        response_source_id,
        field_name="response_source_id",
    )

    return (
        "pt-training-response-evidence:"
        f"athlete-response:{response_id}"
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


def _restore_measurement(
    raw: object,
) -> TrainingResponseMeasurement:
    if not isinstance(raw, dict):
        raise ValueError(
            "Training response measurement must be an object."
        )

    unit = raw.get("unit")

    if unit is not None:
        unit = _require_string(
            unit,
            field_name="measurement.unit",
        )

    return TrainingResponseMeasurement(
        metric_key=_require_string(
            raw.get("metric_key"),
            field_name="measurement.metric_key",
        ),
        knowledge_status=KnowledgeStatus(
            _require_string(
                raw.get("knowledge_status"),
                field_name="measurement.knowledge_status",
            )
        ),
        value=raw.get("value"),
        unit=unit,
    )


def restore_authoritative_training_response_audit_artifact(
    record: AuditArtifactRecord,
) -> AuthoritativeTrainingResponseEvidence:
    if (
        record.artifact_kind
        != AuditArtifactKind.AUTHORITATIVE_TRAINING_RESPONSE
    ):
        raise ValueError(
            "Unexpected training-response audit artifact kind."
        )

    try:
        raw = json.loads(record.contract_json)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Training-response audit contract is not valid JSON."
        ) from exc

    if not isinstance(raw, dict):
        raise ValueError(
            "Training-response audit contract must be an object."
        )

    raw_measurements = raw.get("measurements")

    if not isinstance(raw_measurements, list):
        raise ValueError(
            "measurements must be a list."
        )

    artifact = AuthoritativeTrainingResponseEvidence(
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
        executed_training_evidence_id=_require_string(
            raw.get("executed_training_evidence_id"),
            field_name="executed_training_evidence_id",
        ),
        executed_training_evidence_hash=_require_sha256(
            raw.get("executed_training_evidence_hash"),
            field_name="executed_training_evidence_hash",
        ),
        response_kind=TrainingResponseKind(
            _require_string(
                raw.get("response_kind"),
                field_name="response_kind",
            )
        ),
        response_timing=TrainingResponseTiming(
            _require_string(
                raw.get("response_timing"),
                field_name="response_timing",
            )
        ),
        session_link_basis=TrainingResponseLinkBasis(
            _require_string(
                raw.get("session_link_basis"),
                field_name="session_link_basis",
            )
        ),
        observed_at=_require_datetime(
            raw.get("observed_at"),
            field_name="observed_at",
        ),
        available_at=_require_datetime(
            raw.get("available_at"),
            field_name="available_at",
        ),
        source_system=_require_string(
            raw.get("source_system"),
            field_name="source_system",
        ),
        source_record_id=_require_string(
            raw.get("source_record_id"),
            field_name="source_record_id",
        ),
        source_record_version=_optional_string(
            raw.get("source_record_version"),
            field_name="source_record_version",
        ),
        source_content_hash=_require_sha256(
            raw.get("source_content_hash"),
            field_name="source_content_hash",
        ),
        provenance=ProvenanceKind(
            _require_string(
                raw.get("provenance"),
                field_name="provenance",
            )
        ),
        quality=EvidenceQuality(
            _require_string(
                raw.get("quality"),
                field_name="quality",
            )
        ),
        measurements=tuple(
            _restore_measurement(item)
            for item in raw_measurements
        ),
        interpretation=TrainingResponseInterpretation(
            _require_string(
                raw.get("interpretation"),
                field_name="interpretation",
            )
        ),
        session_identity_linked=_require_bool(
            raw.get("session_identity_linked"),
            field_name="session_identity_linked",
        ),
        causal_attribution_established=_require_bool(
            raw.get("causal_attribution_established"),
            field_name="causal_attribution_established",
        ),
        readiness_inference_authorized=_require_bool(
            raw.get("readiness_inference_authorized"),
            field_name="readiness_inference_authorized",
        ),
        fatigue_diagnosis_authorized=_require_bool(
            raw.get("fatigue_diagnosis_authorized"),
            field_name="fatigue_diagnosis_authorized",
        ),
        performance_prediction_authorized=_require_bool(
            raw.get("performance_prediction_authorized"),
            field_name="performance_prediction_authorized",
        ),
        prescription_change_authorized=_require_bool(
            raw.get("prescription_change_authorized"),
            field_name="prescription_change_authorized",
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
        != TRAINING_RESPONSE_EVIDENCE_SCHEMA_V02
    ):
        raise ValueError(
            "Unsupported persisted authoritative "
            "training-response schema."
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
            "Training-response audit record metadata does not "
            "match its canonical contract."
        )

    if artifact.available_at < artifact.observed_at:
        raise ValueError(
            "Persisted training response has invalid "
            "observation/availability ordering."
        )

    if artifact.created_at < artifact.available_at:
        raise ValueError(
            "Persisted training response predates its availability."
        )

    if (
        artifact.response_kind
        != TrainingResponseKind.SESSION_FEEDBACK
        or artifact.session_link_basis
        != TrainingResponseLinkBasis.SOURCE_EXPLICIT_SESSION_ID
        or artifact.provenance != ProvenanceKind.SOURCE
        or artifact.quality != EvidenceQuality.MODERATE
        or artifact.interpretation
        != TrainingResponseInterpretation.DESCRIPTIVE_ONLY
        or artifact.session_identity_linked is not True
        or artifact.causal_attribution_established is not False
        or artifact.readiness_inference_authorized is not False
        or artifact.fatigue_diagnosis_authorized is not False
        or artifact.performance_prediction_authorized is not False
        or artifact.prescription_change_authorized is not False
    ):
        raise ValueError(
            "Persisted training-response artifact claims "
            "unsupported authority."
        )

    if not artifact.verify_content_hash():
        raise ValueError(
            "Persisted authoritative training-response content "
            "hash does not verify."
        )

    if canonical_json(artifact) != record.contract_json:
        raise ValueError(
            "Persisted authoritative training-response contract "
            "does not round-trip canonically."
        )

    return artifact


def _audit_record(
    artifact: AuthoritativeTrainingResponseEvidence,
) -> AuditArtifactRecord:
    if not artifact.verify_content_hash():
        raise ValueError(
            "Authoritative training-response artifact hash "
            "does not verify."
        )

    return AuditArtifactRecord(
        artifact_kind=(
            AuditArtifactKind.AUTHORITATIVE_TRAINING_RESPONSE
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


async def _load_execution_artifact(
    *,
    audit_repository: AsyncPlanningAuditRepository,
    athlete_id: str,
    executed_artifact_id: str,
    expected_session_id: str,
    expected_content_hash: str | None = None,
):
    record = await audit_repository.get(
        artifact_kind=(
            AuditArtifactKind.AUTHORITATIVE_EXECUTED_TRAINING
        ),
        artifact_id=executed_artifact_id,
    )

    if (
        record is None
        or record.athlete_id != athlete_id
    ):
        raise AuthoritativeTrainingResponseExecutionNotFound(
            "Authoritative executed-training evidence not found."
        )

    executed = (
        restore_authoritative_executed_training_audit_artifact(
            record
        )
    )

    if (
        executed.athlete_id != athlete_id
        or executed.workout_session_id
        != expected_session_id
        or executed.artifact_id
        != executed_artifact_id
    ):
        raise ValueError(
            "Durable executed-training artifact identity does "
            "not match the response session."
        )

    if (
        expected_content_hash is not None
        and executed.content_hash
        != expected_content_hash
    ):
        raise ValueError(
            "Durable training response references a different "
            "executed-training content hash."
        )

    return executed


async def ingest_authoritative_training_response(
    *,
    athlete_id: str,
    response_source_id: str,
    response_source: LockedTrainingResponseSourceProvider,
    audit_repository: AsyncPlanningAuditRepository,
    evidence_repository: AsyncEvidenceRepository,
    session,
    created_at: datetime | None = None,
) -> AuthoritativeTrainingResponseIngestionResult:
    """Freeze one explicit session response exactly once.

    First durable response freeze wins. Retries restore the immutable
    response artifact without recapturing mutable AthleteResponse state.

    The authoritative audit artifact and its deterministic SESSION_FEEDBACK
    EvidenceItem projection share one transaction. Retries reuse the durable
    response freeze and idempotently restore the first persisted projection.
    """

    canonical_athlete_id = _uuid_text(
        athlete_id,
        field_name="athlete_id",
    )

    canonical_response_id = _uuid_text(
        response_source_id,
        field_name="response_source_id",
    )

    artifact_id = (
        authoritative_training_response_artifact_id(
            canonical_response_id
        )
    )

    materialized_at = to_utc(
        created_at or datetime.now(timezone.utc),
        field_name="created_at",
    )

    try:
        existing = await audit_repository.get(
            artifact_kind=(
                AuditArtifactKind.AUTHORITATIVE_TRAINING_RESPONSE
            ),
            artifact_id=artifact_id,
        )

        if existing is not None:
            if existing.athlete_id != canonical_athlete_id:
                raise AuthoritativeTrainingResponseNotFound(
                    "Authoritative training response not found."
                )

            artifact = (
                restore_authoritative_training_response_audit_artifact(
                    existing
                )
            )

            if (
                artifact.athlete_id != canonical_athlete_id
                or artifact.artifact_id != artifact_id
                or artifact.source_record_id
                != canonical_response_id
            ):
                raise ValueError(
                    "Durable training-response artifact identity "
                    "does not match the requested source."
                )

            await _load_execution_artifact(
                audit_repository=audit_repository,
                athlete_id=canonical_athlete_id,
                executed_artifact_id=(
                    artifact.executed_training_evidence_id
                ),
                expected_session_id=(
                    artifact.workout_session_id
                ),
                expected_content_hash=(
                    artifact.executed_training_evidence_hash
                ),
            )

            reused = True

        else:
            capture = await response_source.lock_and_capture(
                session,
                athlete_id=canonical_athlete_id,
                response_source_id=canonical_response_id,
            )

            if (
                capture.athlete_id
                != canonical_athlete_id
                or capture.response_source_id
                != canonical_response_id
            ):
                raise ValueError(
                    "Locked training-response source identity "
                    "does not match the request."
                )

            executed_artifact_id = (
                authoritative_executed_training_artifact_id(
                    capture.workout_session_id
                )
            )

            executed = await _load_execution_artifact(
                audit_repository=audit_repository,
                athlete_id=canonical_athlete_id,
                executed_artifact_id=executed_artifact_id,
                expected_session_id=(
                    capture.workout_session_id
                ),
            )

            artifact = (
                assemble_authoritative_training_response_from_capture(
                    athlete_id=canonical_athlete_id,
                    executed_training=executed,
                    capture=capture,
                    created_at=materialized_at,
                )
            )

            if artifact.artifact_id != artifact_id:
                raise ValueError(
                    "Training-response assembler did not preserve "
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
            project_authoritative_training_response_evidence(
                artifact,
                created_at=projection_created_at,
            )
        )

        persisted_evidence = await evidence_repository.save(
            projected
        )

        await session.commit()

        return AuthoritativeTrainingResponseIngestionResult(
            artifact=artifact,
            evidence=persisted_evidence,
            reused_durable_artifact=reused,
        )

    except Exception:
        await session.rollback()
        raise
