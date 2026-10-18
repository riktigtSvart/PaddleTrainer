from ..common.enums import KnowledgeStatus
from ..evidence.models import EvidenceItem
from .models import EvidenceDomain, TrainingExposureObservation


EXECUTED_TRAINING_SESSION = "EXECUTED_TRAINING_SESSION"
SESSION_FEEDBACK = "SESSION_FEEDBACK"
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


def training_exposure_from_evidence(
    item: EvidenceItem,
) -> TrainingExposureObservation | None:
    if item.evidence_type != EXECUTED_TRAINING_SESSION:
        return None

    payload = item.payload
    schema_version = payload.get("schema_version")
    if schema_version != "executed_training_session_evidence_v0.1":
        raise ValueError(
            "Unsupported executed training session evidence schema."
        )

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
        if isinstance(duration_s, bool) or not isinstance(duration_s, int):
            raise ValueError("duration_s must be an integer or null.")

    return TrainingExposureObservation(
        evidence_id=item.evidence_id,
        session_id=session_id,
        observed_at=item.observed_at,
        modality_key=modality_key,
        duration_status=duration_status,
        duration_s=duration_s,
    )
