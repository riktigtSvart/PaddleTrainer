from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from ..domain.common.enums import (
    KnowledgeStatus,
    ProvenanceKind,
)
from ..domain.common.time import to_utc
from ..domain.evidence.models import (
    EvidenceItem,
    EvidenceQuality,
)
from ..domain.executed_training import (
    AUTHORITATIVE_EXECUTED_TRAINING_SCHEMA_VERSION,
    AuthoritativeExecutedTrainingEvidence,
)
from ..domain.response_evidence import (
    TRAINING_RESPONSE_EVIDENCE_SCHEMA_V02,
    TrainingResponseInterpretation,
    TrainingResponseLinkBasis,
    TrainingResponseTiming,
)
from ..domain.training_dynamics import (
    ObservedResponseAssociation,
    RealizedTrainingStimulus,
    ResponseIsolationStatus,
    build_observed_response_association,
    build_realized_training_stimulus,
)
from ..domain.training_state.evidence import (
    SESSION_FEEDBACK,
    SESSION_FEEDBACK_SCHEMA_V01,
)
from .project_authoritative_training_response import (
    AUTHORITATIVE_TRAINING_RESPONSE_SOURCE_SYSTEM,
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


def _payload(
    evidence: EvidenceItem,
) -> Mapping[str, object]:
    payload = evidence.payload

    if not isinstance(payload, Mapping):
        raise ValueError(
            "Training-response evidence payload must be a mapping."
        )

    return payload


def assemble_realized_training_stimulus(
    source: AuthoritativeExecutedTrainingEvidence,
    *,
    created_at: datetime,
) -> RealizedTrainingStimulus:
    """Assemble descriptive P2 stimulus from immutable P1.7 evidence.

    The P1.7 source proves session/exposure identity but does not establish
    exact actual boundaries or a biological effect.
    """

    if not source.verify_content_hash():
        raise ValueError(
            "Authoritative executed-training evidence hash "
            "does not verify."
        )

    if (
        source.schema_version
        != AUTHORITATIVE_EXECUTED_TRAINING_SCHEMA_VERSION
    ):
        raise ValueError(
            "Unsupported authoritative executed-training schema."
        )

    if source.plan_identity_linked is not True:
        raise ValueError(
            "Executed-training source must preserve plan identity."
        )

    if (
        source.plan_content_at_execution_status
        != "unverified"
    ):
        raise ValueError(
            "Executed-training source contains unsupported "
            "historical plan-content authority."
        )

    for field_name in (
        "occurrence_alignment_verified",
        "phase_alignment_verified",
        "provider_event_verified",
        "clock_alignment_verified",
        "actual_boundary_verified",
        "temporal_match_used",
    ):
        if getattr(source, field_name) is not False:
            raise ValueError(
                f"{field_name} must remain false."
            )

    materialized = to_utc(
        created_at,
        field_name="created_at",
    )

    source_created = to_utc(
        source.created_at,
        field_name="source.created_at",
    )

    if materialized < source_created:
        raise ValueError(
            "Realized stimulus cannot predate its authoritative "
            "executed-training artifact."
        )

    return build_realized_training_stimulus(
        stimulus_id=(
            "pt-training-stimulus:"
            f"session:{source.workout_session_id}"
        ),
        athlete_id=source.athlete_id,
        workout_session_id=source.workout_session_id,
        executed_training_evidence_id=source.artifact_id,
        executed_training_evidence_hash=source.content_hash,
        exposure_observed_at=source.observed_at,
        modality_key=source.modality_key,
        duration_status=source.duration_status,
        duration_s=source.duration_s,

        # P2.1A2 deliberately does not invent richer load/stimulus
        # descriptors from session-level P1.7 evidence.
        features=(),

        created_at=materialized,
    )


def _validated_session_feedback(
    evidence: EvidenceItem,
    *,
    stimulus: RealizedTrainingStimulus,
) -> tuple[
    TrainingResponseTiming,
    TrainingResponseLinkBasis,
]:
    if not evidence.verify_content_hash():
        raise ValueError(
            "SESSION_FEEDBACK evidence hash does not verify."
        )

    if evidence.evidence_type != SESSION_FEEDBACK:
        raise ValueError(
            "P2.1A2 response association requires "
            "SESSION_FEEDBACK evidence."
        )

    if evidence.athlete_id != stimulus.athlete_id:
        raise ValueError(
            "Response athlete does not match realized stimulus athlete."
        )

    if evidence.provenance != ProvenanceKind.DERIVED:
        raise ValueError(
            "P2.1A2 requires the durable derived response projection."
        )

    if evidence.knowledge_status != KnowledgeStatus.KNOWN:
        raise ValueError(
            "SESSION_FEEDBACK evidence observation must be KNOWN."
        )

    if evidence.quality != EvidenceQuality.MODERATE:
        raise ValueError(
            "Unexpected SESSION_FEEDBACK evidence quality."
        )

    payload = _payload(evidence)

    schema_version = _require_string(
        payload.get("schema_version"),
        field_name="payload.schema_version",
    )

    if schema_version != SESSION_FEEDBACK_SCHEMA_V01:
        raise ValueError(
            "Unsupported SESSION_FEEDBACK evidence schema."
        )

    session_id = _require_string(
        payload.get("session_id"),
        field_name="payload.session_id",
    )

    if session_id != stimulus.workout_session_id:
        raise ValueError(
            "Response session does not match realized stimulus session."
        )

    executed_id = _require_string(
        payload.get("executed_training_evidence_id"),
        field_name="payload.executed_training_evidence_id",
    )

    executed_hash = _require_string(
        payload.get("executed_training_evidence_hash"),
        field_name="payload.executed_training_evidence_hash",
    )

    if (
        executed_id != stimulus.executed_training_evidence_id
        or executed_hash
        != stimulus.executed_training_evidence_hash
    ):
        raise ValueError(
            "Response execution reference does not match "
            "the realized stimulus source."
        )

    response_artifact_id = _require_string(
        payload.get("authoritative_response_evidence_id"),
        field_name="payload.authoritative_response_evidence_id",
    )

    response_artifact_hash = _require_string(
        payload.get("authoritative_response_evidence_hash"),
        field_name="payload.authoritative_response_evidence_hash",
    )

    if (
        evidence.source_ref.source_system
        != AUTHORITATIVE_TRAINING_RESPONSE_SOURCE_SYSTEM
        or evidence.source_ref.source_record_id
        != response_artifact_id
        or evidence.source_ref.source_version
        != TRAINING_RESPONSE_EVIDENCE_SCHEMA_V02
        or evidence.source_ref.source_content_hash
        != response_artifact_hash
    ):
        raise ValueError(
            "SESSION_FEEDBACK source reference does not match "
            "its authoritative response provenance."
        )

    if (
        _require_bool(
            payload.get("session_identity_linked"),
            field_name="payload.session_identity_linked",
        )
        is not True
    ):
        raise ValueError(
            "Response evidence must preserve session identity."
        )

    interpretation = _require_string(
        payload.get("interpretation"),
        field_name="payload.interpretation",
    )

    if (
        interpretation
        != TrainingResponseInterpretation.DESCRIPTIVE_ONLY.value
    ):
        raise ValueError(
            "Response evidence must remain descriptive only."
        )

    for field_name in (
        "causal_attribution_established",
        "readiness_inference_authorized",
        "fatigue_diagnosis_authorized",
        "performance_prediction_authorized",
        "prescription_change_authorized",
    ):
        if (
            _require_bool(
                payload.get(field_name),
                field_name=f"payload.{field_name}",
            )
            is not False
        ):
            raise ValueError(
                f"{field_name} must remain false."
            )

    timing = TrainingResponseTiming(
        _require_string(
            payload.get("response_timing"),
            field_name="payload.response_timing",
        )
    )

    link_basis = TrainingResponseLinkBasis(
        _require_string(
            payload.get("session_link_basis"),
            field_name="payload.session_link_basis",
        )
    )

    if (
        link_basis
        != TrainingResponseLinkBasis.SOURCE_EXPLICIT_SESSION_ID
    ):
        raise ValueError(
            "P2.1A2 requires explicit source session identity."
        )

    return timing, link_basis


def assemble_observed_response_association(
    *,
    stimulus: RealizedTrainingStimulus,
    response_evidence: EvidenceItem,
    intervening_stimuli: tuple[
        RealizedTrainingStimulus,
        ...,
    ] = (),
    intervening_history_complete: bool = False,
    created_at: datetime,
) -> ObservedResponseAssociation:
    """Assemble one descriptive historical stimulus-response association.

    Intervening stimuli are supplied explicitly. Empty input does not imply
    isolation unless intervening_history_complete=True.
    """

    if not stimulus.verify_content_hash():
        raise ValueError(
            "Realized training stimulus hash does not verify."
        )

    if not isinstance(intervening_history_complete, bool):
        raise ValueError(
            "intervening_history_complete must be boolean."
        )

    timing, link_basis = _validated_session_feedback(
        response_evidence,
        stimulus=stimulus,
    )

    materialized = to_utc(
        created_at,
        field_name="created_at",
    )

    response_created = to_utc(
        response_evidence.created_at,
        field_name="response_evidence.created_at",
    )

    if materialized < response_created:
        raise ValueError(
            "Response association cannot predate its durable "
            "response evidence."
        )

    response_observed = to_utc(
        response_evidence.observed_at,
        field_name="response_evidence.observed_at",
    )

    ordered_intervening = tuple(
        sorted(
            tuple(intervening_stimuli),
            key=lambda item: (
                item.exposure_observed_at,
                item.stimulus_id,
            ),
        )
    )

    seen_ids: set[str] = set()

    for intervening in ordered_intervening:
        if not intervening.verify_content_hash():
            raise ValueError(
                "Intervening realized stimulus hash does not verify."
            )

        if intervening.athlete_id != stimulus.athlete_id:
            raise ValueError(
                "Intervening stimulus belongs to another athlete."
            )

        if intervening.stimulus_id == stimulus.stimulus_id:
            raise ValueError(
                "The source stimulus cannot intervene with itself."
            )

        if intervening.stimulus_id in seen_ids:
            raise ValueError(
                "Duplicate intervening stimulus identity."
            )

        seen_ids.add(intervening.stimulus_id)

        if not (
            stimulus.exposure_observed_at
            < intervening.exposure_observed_at
            < response_observed
        ):
            raise ValueError(
                "Intervening stimulus must be observed after the "
                "source stimulus and before the response."
            )

    if ordered_intervening:
        isolation_status = (
            ResponseIsolationStatus
            .INTERVENING_STIMULUS_OBSERVED
        )

    elif intervening_history_complete:
        isolation_status = (
            ResponseIsolationStatus
            .NO_INTERVENING_STIMULUS_OBSERVED
        )

    else:
        isolation_status = ResponseIsolationStatus.UNKNOWN

    return build_observed_response_association(
        association_id=(
            "pt-response-association:"
            f"session-feedback:{response_evidence.content_hash}"
        ),
        stimulus=stimulus,
        response_evidence_id=response_evidence.evidence_id,
        response_evidence_hash=response_evidence.content_hash,
        response_workout_session_id=(
            stimulus.workout_session_id
        ),
        response_timing=timing,
        session_link_basis=link_basis,
        response_observed_at=response_evidence.observed_at,
        response_available_at=response_evidence.available_at,
        isolation_status=isolation_status,
        intervening_stimulus_ids=tuple(
            item.stimulus_id
            for item in ordered_intervening
        ),
        created_at=materialized,
    )
