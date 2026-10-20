from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import math
from uuid import UUID

from ..common.enums import (
    KnowledgeStatus,
    ProvenanceKind,
)
from ..common.serialization import (
    CONTENT_HASH_ALGORITHM,
    compute_content_hash,
)
from ..common.time import to_utc
from ..evidence.models import EvidenceQuality


TRAINING_RESPONSE_EVIDENCE_SCHEMA_V01 = (
    "authoritative-training-response-evidence-v0.1"
)

TRAINING_RESPONSE_EVIDENCE_SCHEMA_V02 = (
    "authoritative-training-response-evidence-v0.2"
)

TRAINING_RESPONSE_EVIDENCE_ID_PREFIX = (
    "pt-training-response-evidence:"
)

TRAINING_RESPONSE_EVIDENCE_HASH_EXCLUDE_FIELDS = (
    frozenset(
        {
            "artifact_id",
            "created_at",
            "content_hash",
        }
    )
)


class TrainingResponseKind(StrEnum):
    """What was actually observed about the session response."""

    SESSION_FEEDBACK = "session_feedback"
    PHYSIOLOGICAL_RESPONSE = "physiological_response"


class TrainingResponseTiming(StrEnum):
    """When the response was observed relative to the executed session.

    This is observation context, not a measurement and not evidence of
    causal attribution.
    """

    IMMEDIATE = "immediate"
    SAME_DAY = "same_day"
    NEXT_MORNING = "next_morning"
    FOLLOW_UP = "follow_up"


class TrainingResponseLinkBasis(StrEnum):
    """Authority for linking response evidence to one executed session.

    Temporal proximity is deliberately absent. Merely occurring near a
    workout does not establish that a response observation belongs to it.
    """

    SOURCE_EXPLICIT_SESSION_ID = (
        "source_explicit_session_id"
    )
    USER_CONFIRMED_SESSION_ID = (
        "user_confirmed_session_id"
    )


class TrainingResponseInterpretation(StrEnum):
    """Maximum interpretation granted by the P1.8A contract."""

    DESCRIPTIVE_ONLY = "descriptive_only"


ResponseScalar = str | int | float | bool


def _require_non_empty(
    value: str,
    *,
    field_name: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{field_name} must be a non-empty string."
        )
    return value


def _require_canonical_uuid(
    value: str,
    *,
    field_name: str,
) -> str:
    _require_non_empty(
        value,
        field_name=field_name,
    )

    try:
        parsed = UUID(value)
    except (TypeError, ValueError, AttributeError):
        raise ValueError(
            f"{field_name} must be a canonical UUID."
        ) from None

    canonical = str(parsed)

    if canonical != value:
        raise ValueError(
            f"{field_name} must be a canonical UUID."
        )

    return canonical


def _require_sha256(
    value: str,
    *,
    field_name: str,
) -> str:
    _require_non_empty(
        value,
        field_name=field_name,
    )

    if (
        len(value) != 64
        or any(
            char not in "0123456789abcdef"
            for char in value
        )
    ):
        raise ValueError(
            f"{field_name} must be a lowercase SHA-256 digest."
        )

    return value


@dataclass(frozen=True)
class TrainingResponseMeasurement:
    """One measured/reported response variable.

    UNKNOWN / NOT_MEASURED / NOT_ASKED / NOT_APPLICABLE remain null.
    They must never silently become numeric zero or a categorical answer.
    """

    metric_key: str
    knowledge_status: KnowledgeStatus
    value: ResponseScalar | None
    unit: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(
            self.metric_key,
            field_name="metric_key",
        )

        if self.unit is not None:
            _require_non_empty(
                self.unit,
                field_name="unit",
            )

        if self.knowledge_status == KnowledgeStatus.KNOWN:
            if self.value is None:
                raise ValueError(
                    "KNOWN response measurement requires a value."
                )

            if isinstance(self.value, str):
                if not self.value.strip():
                    raise ValueError(
                        "Known string response value "
                        "must be non-empty."
                    )

            elif isinstance(self.value, bool):
                pass

            elif isinstance(self.value, int):
                pass

            elif isinstance(self.value, float):
                if not math.isfinite(self.value):
                    raise ValueError(
                        "Numeric response value must be finite."
                    )

            else:
                raise ValueError(
                    "Response value must be string, integer, "
                    "float, boolean, or null."
                )

        elif self.value is not None:
            raise ValueError(
                "Non-KNOWN response measurement "
                "requires value=None."
            )


@dataclass(frozen=True)
class AuthoritativeTrainingResponseEvidence:
    """Immutable descriptive response evidence linked to one execution.

    The session association does not establish causality. This artifact
    cannot by itself diagnose fatigue/readiness, predict performance, or
    authorize prescription changes.
    """

    artifact_id: str
    schema_version: str

    athlete_id: str
    workout_session_id: str

    executed_training_evidence_id: str
    executed_training_evidence_hash: str

    response_kind: TrainingResponseKind
    response_timing: TrainingResponseTiming
    session_link_basis: TrainingResponseLinkBasis

    observed_at: datetime
    available_at: datetime

    source_system: str
    source_record_id: str
    source_record_version: str | None
    source_content_hash: str

    provenance: ProvenanceKind
    quality: EvidenceQuality

    measurements: tuple[
        TrainingResponseMeasurement,
        ...,
    ]

    interpretation: TrainingResponseInterpretation

    session_identity_linked: bool

    causal_attribution_established: bool
    readiness_inference_authorized: bool
    fatigue_diagnosis_authorized: bool
    performance_prediction_authorized: bool
    prescription_change_authorized: bool

    created_at: datetime

    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(
                self,
                exclude_fields=(
                    TRAINING_RESPONSE_EVIDENCE_HASH_EXCLUDE_FIELDS
                ),
            )
            == self.content_hash
        )


def build_authoritative_training_response_evidence(
    *,
    artifact_id: str,
    athlete_id: str,
    workout_session_id: str,
    executed_training_evidence_id: str,
    executed_training_evidence_hash: str,
    response_kind: TrainingResponseKind,
    response_timing: TrainingResponseTiming,
    session_link_basis: TrainingResponseLinkBasis,
    observed_at: datetime,
    available_at: datetime,
    source_system: str,
    source_record_id: str,
    source_record_version: str | None,
    source_content_hash: str,
    provenance: ProvenanceKind,
    quality: EvidenceQuality,
    measurements: tuple[
        TrainingResponseMeasurement,
        ...,
    ],
    created_at: datetime,
) -> AuthoritativeTrainingResponseEvidence:
    """Build one immutable, session-level response artifact."""

    _require_non_empty(
        artifact_id,
        field_name="artifact_id",
    )

    if not artifact_id.startswith(
        TRAINING_RESPONSE_EVIDENCE_ID_PREFIX
    ):
        raise ValueError(
            "artifact_id must use the training response "
            "evidence prefix."
        )

    canonical_athlete_id = _require_canonical_uuid(
        athlete_id,
        field_name="athlete_id",
    )
    canonical_session_id = _require_canonical_uuid(
        workout_session_id,
        field_name="workout_session_id",
    )

    _require_non_empty(
        executed_training_evidence_id,
        field_name="executed_training_evidence_id",
    )

    if not executed_training_evidence_id.startswith(
        "pt-executed-training-evidence:"
    ):
        raise ValueError(
            "executed_training_evidence_id must reference "
            "P1.7 authoritative executed-training evidence."
        )

    _require_sha256(
        executed_training_evidence_hash,
        field_name="executed_training_evidence_hash",
    )

    kind = TrainingResponseKind(
        response_kind
    )
    timing = TrainingResponseTiming(
        response_timing
    )
    link_basis = TrainingResponseLinkBasis(
        session_link_basis
    )

    observed = to_utc(
        observed_at,
        field_name="observed_at",
    )
    available = to_utc(
        available_at,
        field_name="available_at",
    )
    created = to_utc(
        created_at,
        field_name="created_at",
    )

    if available < observed:
        raise ValueError(
            "available_at must not be before observed_at."
        )

    if created < available:
        raise ValueError(
            "created_at must not be before available_at."
        )

    source_system_value = _require_non_empty(
        source_system,
        field_name="source_system",
    )
    source_record_id_value = _require_non_empty(
        source_record_id,
        field_name="source_record_id",
    )

    if source_record_version is not None:
        _require_non_empty(
            source_record_version,
            field_name="source_record_version",
        )

    _require_sha256(
        source_content_hash,
        field_name="source_content_hash",
    )

    provenance_value = ProvenanceKind(
        provenance
    )

    if provenance_value not in (
        ProvenanceKind.SOURCE,
        ProvenanceKind.DERIVED,
    ):
        raise ValueError(
            "Training response evidence provenance must "
            "be SOURCE or DERIVED."
        )

    quality_value = EvidenceQuality(
        quality
    )

    ordered_measurements = tuple(
        sorted(
            tuple(measurements),
            key=lambda measurement: (
                measurement.metric_key,
            ),
        )
    )

    if not ordered_measurements:
        raise ValueError(
            "Training response evidence requires at least "
            "one response measurement."
        )

    metric_keys = tuple(
        measurement.metric_key
        for measurement in ordered_measurements
    )

    if len(set(metric_keys)) != len(metric_keys):
        raise ValueError(
            "Training response measurement keys "
            "must be unique within one artifact."
        )

    provisional = AuthoritativeTrainingResponseEvidence(
        artifact_id=artifact_id,
        schema_version=(
            TRAINING_RESPONSE_EVIDENCE_SCHEMA_V02
        ),
        athlete_id=canonical_athlete_id,
        workout_session_id=canonical_session_id,
        executed_training_evidence_id=(
            executed_training_evidence_id
        ),
        executed_training_evidence_hash=(
            executed_training_evidence_hash
        ),
        response_kind=kind,
        response_timing=timing,
        session_link_basis=link_basis,
        observed_at=observed,
        available_at=available,
        source_system=source_system_value,
        source_record_id=source_record_id_value,
        source_record_version=source_record_version,
        source_content_hash=source_content_hash,
        provenance=provenance_value,
        quality=quality_value,
        measurements=ordered_measurements,

        interpretation=(
            TrainingResponseInterpretation.DESCRIPTIVE_ONLY
        ),

        session_identity_linked=True,

        # P1.8A records response evidence, not causal or planning authority.
        causal_attribution_established=False,
        readiness_inference_authorized=False,
        fatigue_diagnosis_authorized=False,
        performance_prediction_authorized=False,
        prescription_change_authorized=False,

        created_at=created,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )

    digest = compute_content_hash(
        provisional,
        exclude_fields=(
            TRAINING_RESPONSE_EVIDENCE_HASH_EXCLUDE_FIELDS
        ),
    )

    return AuthoritativeTrainingResponseEvidence(
        **{
            **provisional.__dict__,
            "content_hash": digest,
        }
    )
