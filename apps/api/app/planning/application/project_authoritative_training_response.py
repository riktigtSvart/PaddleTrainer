from __future__ import annotations

from datetime import datetime

from ..domain.common.enums import (
    KnowledgeStatus,
    ProvenanceKind,
)
from ..domain.common.time import to_utc
from ..domain.evidence.models import (
    EvidenceItem,
    EvidenceQuality,
    SourceRecordRef,
    create_evidence_item,
)
from ..domain.response_evidence import (
    TRAINING_RESPONSE_EVIDENCE_SCHEMA_V02,
    AuthoritativeTrainingResponseEvidence,
    TrainingResponseInterpretation,
    TrainingResponseKind,
    TrainingResponseLinkBasis,
)
from ..domain.training_state.evidence import (
    SESSION_FEEDBACK,
    SESSION_FEEDBACK_SCHEMA_V01,
)


AUTHORITATIVE_TRAINING_RESPONSE_SOURCE_SYSTEM = (
    "planning_authoritative_training_response"
)


def project_authoritative_training_response_evidence(
    source: AuthoritativeTrainingResponseEvidence,
    *,
    created_at: datetime,
) -> EvidenceItem:
    """Project one authoritative response artifact into RESPONSE evidence.

    The projection remains descriptive. Session identity is preserved, but
    association with an executed session is not promoted into causality,
    readiness, fatigue diagnosis, performance prediction, or prescription
    authority.
    """

    if not source.verify_content_hash():
        raise ValueError(
            "Authoritative training-response evidence hash "
            "does not verify."
        )

    if (
        source.schema_version
        != TRAINING_RESPONSE_EVIDENCE_SCHEMA_V02
    ):
        raise ValueError(
            "Unsupported authoritative training-response schema."
        )

    if (
        source.response_kind
        != TrainingResponseKind.SESSION_FEEDBACK
    ):
        raise ValueError(
            "P1.8D1 projects SESSION_FEEDBACK responses only."
        )

    if (
        source.session_link_basis
        != TrainingResponseLinkBasis.SOURCE_EXPLICIT_SESSION_ID
    ):
        raise ValueError(
            "P1.8D1 requires explicit source session identity."
        )

    if (
        source.interpretation
        != TrainingResponseInterpretation.DESCRIPTIVE_ONLY
    ):
        raise ValueError(
            "Training response must remain descriptive only."
        )

    if source.session_identity_linked is not True:
        raise ValueError(
            "Training response must establish session identity."
        )

    if (
        source.causal_attribution_established is not False
        or source.readiness_inference_authorized is not False
        or source.fatigue_diagnosis_authorized is not False
        or source.performance_prediction_authorized is not False
        or source.prescription_change_authorized is not False
    ):
        raise ValueError(
            "Training response contains unsupported stronger authority."
        )

    if source.provenance != ProvenanceKind.SOURCE:
        raise ValueError(
            "Authoritative session feedback must retain source provenance."
        )

    if source.quality != EvidenceQuality.MODERATE:
        raise ValueError(
            "Unexpected authoritative session-feedback quality."
        )

    if not source.measurements:
        raise ValueError(
            "Authoritative session feedback requires measurements."
        )

    source_created_at = to_utc(
        source.created_at,
        field_name="source.created_at",
    )

    projected_created_at = to_utc(
        created_at,
        field_name="created_at",
    )

    if projected_created_at < source_created_at:
        raise ValueError(
            "Projected response evidence cannot predate its "
            "authoritative source artifact."
        )

    measurements = tuple(
        {
            "metric_key": measurement.metric_key,
            "knowledge_status":
                measurement.knowledge_status.value,
            "value": measurement.value,
            "unit": measurement.unit,
        }
        for measurement in source.measurements
    )

    payload = {
        "schema_version":
            SESSION_FEEDBACK_SCHEMA_V01,

        # Descriptive response identity.
        "session_id":
            source.workout_session_id,
        "response_timing":
            source.response_timing.value,
        "measurements":
            measurements,

        # Immutable authority provenance.
        "authoritative_response_evidence_id":
            source.artifact_id,
        "authoritative_response_evidence_hash":
            source.content_hash,

        "executed_training_evidence_id":
            source.executed_training_evidence_id,
        "executed_training_evidence_hash":
            source.executed_training_evidence_hash,

        "session_link_basis":
            source.session_link_basis.value,
        "session_identity_linked": True,

        # P1.8 response evidence remains descriptive.
        "interpretation":
            TrainingResponseInterpretation.DESCRIPTIVE_ONLY.value,
        "causal_attribution_established": False,
        "readiness_inference_authorized": False,
        "fatigue_diagnosis_authorized": False,
        "performance_prediction_authorized": False,
        "prescription_change_authorized": False,
    }

    return create_evidence_item(
        evidence_id=(
            "pt-evidence:session-feedback:"
            f"{source.content_hash}"
        ),
        athlete_id=source.athlete_id,
        evidence_type=SESSION_FEEDBACK,

        # When the athlete reported the response.
        observed_at=source.observed_at,

        # Important cutoff rule:
        # the generic evidence cannot exist for replay purposes before
        # the authoritative response artifact itself existed.
        available_at=source_created_at,

        created_at=projected_created_at,

        source_ref=SourceRecordRef(
            source_system=(
                AUTHORITATIVE_TRAINING_RESPONSE_SOURCE_SYSTEM
            ),
            source_record_id=source.artifact_id,
            source_version=source.schema_version,
            source_content_hash=source.content_hash,
        ),

        # This is a deterministic projection of an already-established
        # authoritative artifact.
        provenance=ProvenanceKind.DERIVED,

        # The response observation exists. Individual measurement
        # uncertainty remains inside payload.measurements.
        knowledge_status=KnowledgeStatus.KNOWN,

        # Do not upgrade source quality during projection.
        quality=source.quality,

        payload=payload,
    )
