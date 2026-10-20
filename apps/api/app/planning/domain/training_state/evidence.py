from ..common.enums import KnowledgeStatus
from ..evidence.models import EvidenceItem
from .models import EvidenceDomain, TrainingExposureObservation


EXECUTED_TRAINING_SESSION = "EXECUTED_TRAINING_SESSION"

EXECUTED_TRAINING_SESSION_SCHEMA_V01 = (
    "executed_training_session_evidence_v0.1"
)
EXECUTED_TRAINING_SESSION_SCHEMA_V02 = (
    "executed_training_session_evidence_v0.2"
)

SESSION_FEEDBACK = "SESSION_FEEDBACK"

SESSION_FEEDBACK_SCHEMA_V01 = (
    "session_feedback_evidence_v0.1"
)

PHYSIOLOGICAL_RESPONSE_OBSERVATION = "PHYSIOLOGICAL_RESPONSE_OBSERVATION"
PERFORMANCE_OBSERVATION = "PERFORMANCE_OBSERVATION"
MEASUREMENT_OBSERVATION = "MEASUREMENT_OBSERVATION"
AVAILABILITY_OBSERVATION = "AVAILABILITY_OBSERVATION"
HEALTH_SAFETY_OBSERVATION = "HEALTH_SAFETY_OBSERVATION"


EVIDENCE_TYPE_DOMAIN: dict[str, EvidenceDomain] = {
    EXECUTED_TRAINING_SESSION: EvidenceDomain.TRAINING_EXPOSURE,
    SESSION_FEEDBACK: EvidenceDomain.RESPONSE,
    PHYSIOLOGICAL_RESPONSE_OBSERVATION: EvidenceDomain.RESPONSE,
    PERFORMANCE_OBSERVATION: EvidenceDomain.PERFORMANCE,
    MEASUREMENT_OBSERVATION: EvidenceDomain.MEASUREMENT,
    AVAILABILITY_OBSERVATION: EvidenceDomain.AVAILABILITY,
    HEALTH_SAFETY_OBSERVATION: EvidenceDomain.HEALTH_SAFETY,
}


def evidence_domain(
    item: EvidenceItem,
) -> EvidenceDomain | None:
    return EVIDENCE_TYPE_DOMAIN.get(item.evidence_type)


def _require_v02_authority_metadata(payload) -> None:
    artifact_id = payload.get(
        "authoritative_execution_evidence_id"
    )
    artifact_hash = payload.get(
        "authoritative_execution_evidence_hash"
    )
    plan_execution_link_id = payload.get(
        "plan_execution_link_id"
    )
    occurrence_count = payload.get(
        "occurrence_association_count"
    )
    occurrence_status = payload.get(
        "occurrence_alignment_status"
    )

    if (
        not isinstance(artifact_id, str)
        or not artifact_id.strip()
    ):
        raise ValueError(
            "authoritative_execution_evidence_id "
            "must be a non-empty string."
        )

    if (
        not isinstance(artifact_hash, str)
        or len(artifact_hash) != 64
        or any(
            char not in "0123456789abcdef"
            for char in artifact_hash
        )
    ):
        raise ValueError(
            "authoritative_execution_evidence_hash "
            "must be a lowercase SHA-256 digest."
        )

    if (
        not isinstance(plan_execution_link_id, str)
        or not plan_execution_link_id.strip()
    ):
        raise ValueError(
            "plan_execution_link_id must be a non-empty string."
        )

    if payload.get("plan_identity_linked") is not True:
        raise ValueError(
            "v0.2 executed-training evidence requires "
            "plan_identity_linked=true."
        )

    if (
        isinstance(occurrence_count, bool)
        or not isinstance(occurrence_count, int)
        or occurrence_count < 0
    ):
        raise ValueError(
            "occurrence_association_count must be "
            "a non-negative integer."
        )

    if occurrence_count == 0:
        if occurrence_status != "none":
            raise ValueError(
                "Zero occurrence associations require "
                "occurrence_alignment_status=none."
            )
    else:
        if (
            occurrence_status
            != "user_confirmed_candidate_segment"
        ):
            raise ValueError(
                "Occurrence associations require "
                "user_confirmed_candidate_segment status."
            )

    if (
        payload.get("plan_content_at_execution_status")
        != "unverified"
    ):
        raise ValueError(
            "Unsupported stronger historical plan-content claim."
        )

    for field_name in (
        "occurrence_alignment_verified",
        "phase_alignment_verified",
        "provider_event_verified",
        "clock_alignment_verified",
        "actual_boundary_verified",
        "temporal_match_used",
    ):
        if payload.get(field_name) is not False:
            raise ValueError(
                f"{field_name} must remain false in v0.2."
            )


def _validate_v02_execution_authority(
    item: EvidenceItem,
) -> None:
    """Validate v0.2 authority metadata without promoting it into state."""

    payload = item.payload

    required_strings = (
        "authoritative_execution_evidence_id",
        "authoritative_execution_evidence_hash",
        "plan_execution_link_id",
    )

    for field_name in required_strings:
        value = payload.get(field_name)

        if (
            not isinstance(value, str)
            or not value.strip()
        ):
            raise ValueError(
                f"{field_name} must be a non-empty string."
            )

    artifact_id = payload.get(
        "authoritative_execution_evidence_id"
    )
    artifact_hash = payload.get(
        "authoritative_execution_evidence_hash"
    )

    if (
        len(artifact_hash) != 64
        or any(
            char not in "0123456789abcdef"
            for char in artifact_hash
        )
    ):
        raise ValueError(
            "authoritative_execution_evidence_hash must be "
            "a lowercase SHA-256 digest."
        )

    if item.source_ref.source_record_id != artifact_id:
        raise ValueError(
            "v0.2 source record identity does not match "
            "authoritative execution metadata."
        )

    if (
        item.source_ref.source_content_hash
        != artifact_hash
    ):
        raise ValueError(
            "v0.2 source content hash does not match "
            "authoritative execution metadata."
        )

    if payload.get("plan_identity_linked") is not True:
        raise ValueError(
            "v0.2 executed training requires plan identity linkage."
        )

    if (
        payload.get("plan_content_at_execution_status")
        != "unverified"
    ):
        raise ValueError(
            "v0.2 executed training cannot claim verified "
            "historical plan content."
        )

    for field_name in (
        "occurrence_alignment_verified",
        "phase_alignment_verified",
        "provider_event_verified",
        "clock_alignment_verified",
        "actual_boundary_verified",
        "temporal_match_used",
    ):
        if payload.get(field_name) is not False:
            raise ValueError(
                f"{field_name} must remain false in v0.2 "
                "training exposure evidence."
            )

    count = payload.get(
        "occurrence_association_count"
    )

    if (
        isinstance(count, bool)
        or not isinstance(count, int)
        or count < 0
    ):
        raise ValueError(
            "occurrence_association_count must be a "
            "non-negative integer."
        )

    status = payload.get(
        "occurrence_alignment_status"
    )

    if status not in (
        "none",
        "user_confirmed_candidate_segment",
    ):
        raise ValueError(
            "Unsupported occurrence_alignment_status."
        )

    if count == 0 and status != "none":
        raise ValueError(
            "Zero occurrence associations require status=none."
        )

    if (
        count > 0
        and status
        != "user_confirmed_candidate_segment"
    ):
        raise ValueError(
            "Occurrence associations require explicit "
            "user-confirmed candidate status."
        )


def training_exposure_from_evidence(
    item: EvidenceItem,
) -> TrainingExposureObservation | None:
    if item.evidence_type != EXECUTED_TRAINING_SESSION:
        return None

    payload = item.payload
    schema_version = payload.get("schema_version")

    if schema_version not in (
        EXECUTED_TRAINING_SESSION_SCHEMA_V01,
        EXECUTED_TRAINING_SESSION_SCHEMA_V02,
    ):
        raise ValueError(
            "Unsupported executed training session evidence schema."
        )

    if (
        schema_version
        == EXECUTED_TRAINING_SESSION_SCHEMA_V02
    ):
        _validate_v02_execution_authority(item)

    if (
        schema_version
        == EXECUTED_TRAINING_SESSION_SCHEMA_V02
    ):
        _require_v02_authority_metadata(payload)

    session_id = payload.get("session_id")
    modality_key = payload.get("modality_key")
    duration_status_raw = payload.get("duration_status")
    duration_s = payload.get("duration_s")

    if not isinstance(session_id, str):
        raise ValueError("session_id must be a string.")
    if not isinstance(modality_key, str):
        raise ValueError("modality_key must be a string.")
    if not isinstance(duration_status_raw, str):
        raise ValueError("duration_status must be a string.")

    duration_status = KnowledgeStatus(duration_status_raw)

    if duration_s is not None:
        if (
            isinstance(duration_s, bool)
            or not isinstance(duration_s, int)
        ):
            raise ValueError(
                "duration_s must be an integer or null."
            )

    return TrainingExposureObservation(
        evidence_id=item.evidence_id,
        session_id=session_id,
        observed_at=item.observed_at,
        modality_key=modality_key,
        duration_status=duration_status,
        duration_s=duration_s,
    )
