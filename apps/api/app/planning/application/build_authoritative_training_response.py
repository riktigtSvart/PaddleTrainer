from __future__ import annotations

from datetime import datetime

from ..domain.common.enums import ProvenanceKind
from ..domain.common.time import to_utc
from ..domain.evidence.models import EvidenceQuality
from ..domain.executed_training.models import (
    AUTHORITATIVE_EXECUTED_TRAINING_SCHEMA_VERSION,
    AuthoritativeExecutedTrainingEvidence,
)
from ..domain.response_evidence import (
    AuthoritativeTrainingResponseEvidence,
    TrainingResponseLinkBasis,
    build_authoritative_training_response_evidence,
)
from ..ports.training_response_source import (
    LockedTrainingResponseSourceProvider,
)


class AuthoritativeTrainingResponseExecutionInvalid(ValueError):
    """Referenced P1.7 execution evidence is missing required authority."""


class AuthoritativeTrainingResponseIdentityMismatch(ValueError):
    """Response source and authoritative execution identify different subjects."""


class AuthoritativeTrainingResponseTemporalInvalid(ValueError):
    """Response timing is inconsistent with available execution evidence."""


async def assemble_authoritative_training_response(
    *,
    athlete_id: str,
    response_source_id: str,
    executed_training: AuthoritativeExecutedTrainingEvidence,
    response_source: LockedTrainingResponseSourceProvider,
    session,
    created_at: datetime,
) -> AuthoritativeTrainingResponseEvidence:
    """Assemble one authoritative session-level response artifact.

    Transaction-neutral by design. The caller owns commit/rollback and must
    keep the response-source locks alive until any resulting durable writes
    are complete.

    The explicit AthleteResponse -> WorkoutSession identity is checked against
    an already-established P1.7 authoritative executed-training artifact.

    This establishes response-to-executed-session identity only. It does not
    establish causality, fatigue/readiness diagnosis, performance prediction,
    or prescription authority.
    """

    if not executed_training.verify_content_hash():
        raise AuthoritativeTrainingResponseExecutionInvalid(
            "Authoritative executed-training evidence hash "
            "does not verify."
        )

    if (
        executed_training.schema_version
        != AUTHORITATIVE_EXECUTED_TRAINING_SCHEMA_VERSION
    ):
        raise AuthoritativeTrainingResponseExecutionInvalid(
            "Unsupported authoritative executed-training "
            "schema version."
        )

    if executed_training.athlete_id != athlete_id:
        # Do not reinterpret another athlete's execution evidence.
        raise AuthoritativeTrainingResponseIdentityMismatch(
            "Response athlete does not match authoritative "
            "executed-training athlete."
        )

    if executed_training.plan_identity_linked is not True:
        raise AuthoritativeTrainingResponseExecutionInvalid(
            "Executed-training evidence does not establish "
            "session-level plan identity."
        )

    if (
        executed_training.plan_content_at_execution_status
        != "unverified"
    ):
        raise AuthoritativeTrainingResponseExecutionInvalid(
            "Unexpected stronger historical plan-content claim."
        )

    stronger_flags = (
        executed_training.occurrence_alignment_verified,
        executed_training.phase_alignment_verified,
        executed_training.provider_event_verified,
        executed_training.clock_alignment_verified,
        executed_training.actual_boundary_verified,
        executed_training.temporal_match_used,
    )

    if any(flag is not False for flag in stronger_flags):
        raise AuthoritativeTrainingResponseExecutionInvalid(
            "Executed-training evidence carries unsupported "
            "stronger execution authority."
        )

    capture = await response_source.lock_and_capture(
        session,
        athlete_id=athlete_id,
        response_source_id=response_source_id,
    )

    if capture.athlete_id != athlete_id:
        raise AuthoritativeTrainingResponseIdentityMismatch(
            "Response source athlete identity mismatch."
        )

    if (
        capture.workout_session_id
        != executed_training.workout_session_id
    ):
        raise AuthoritativeTrainingResponseIdentityMismatch(
            "Response source session does not match authoritative "
            "executed-training session."
        )

    executed_observed_at = to_utc(
        executed_training.observed_at,
        field_name="executed_training.observed_at",
    )

    executed_available_at = to_utc(
        executed_training.created_at,
        field_name="executed_training.created_at",
    )

    if capture.observed_at < executed_observed_at:
        raise AuthoritativeTrainingResponseTemporalInvalid(
            "Response observation cannot predate the executed "
            "training observation."
        )

    # The authoritative response is not knowable until BOTH:
    #   1. the response source was available, and
    #   2. the P1.7 execution authority existed.
    authoritative_available_at = max(
        capture.available_at,
        executed_available_at,
    )

    artifact_created_at = to_utc(
        created_at,
        field_name="created_at",
    )

    if artifact_created_at < authoritative_available_at:
        raise AuthoritativeTrainingResponseTemporalInvalid(
            "Authoritative response artifact cannot predate "
            "its required source authority."
        )

    artifact_id = (
        "pt-training-response-evidence:"
        f"athlete-response:{capture.response_source_id}"
    )

    return build_authoritative_training_response_evidence(
        artifact_id=artifact_id,
        athlete_id=athlete_id,
        workout_session_id=capture.workout_session_id,
        executed_training_evidence_id=(
            executed_training.artifact_id
        ),
        executed_training_evidence_hash=(
            executed_training.content_hash
        ),
        response_kind=capture.response_kind,
        response_timing=capture.response_timing,
        session_link_basis=(
            TrainingResponseLinkBasis
            .SOURCE_EXPLICIT_SESSION_ID
        ),
        observed_at=capture.observed_at,
        available_at=authoritative_available_at,
        source_system=capture.source_system,
        source_record_id=capture.source_record_id,
        source_record_version=(
            capture.source_record_version
        ),
        source_content_hash=(
            capture.source_content_hash
        ),
        provenance=ProvenanceKind.SOURCE,
        quality=EvidenceQuality.MODERATE,
        measurements=capture.measurements,
        created_at=artifact_created_at,
    )
