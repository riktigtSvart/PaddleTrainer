from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
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
from ..response_evidence import (
    TrainingResponseLinkBasis,
    TrainingResponseTiming,
)


REALIZED_TRAINING_STIMULUS_SCHEMA_V01 = (
    "realized-training-stimulus-v0.1"
)

OBSERVED_RESPONSE_ASSOCIATION_SCHEMA_V01 = (
    "observed-response-association-v0.1"
)

LATENT_TRAINING_EFFECT_ESTIMATE_SCHEMA_V01 = (
    "latent-training-effect-estimate-v0.1"
)

LONGITUDINAL_TRAINING_EFFECT_STATE_SCHEMA_V01 = (
    "longitudinal-training-effect-state-v0.1"
)

RETENTION_ESTIMATE_SCHEMA_V01 = (
    "retention-estimate-v0.1"
)


REALIZED_STIMULUS_HASH_EXCLUDE_FIELDS = frozenset(
    {
        "stimulus_id",
        "created_at",
        "content_hash",
    }
)

RESPONSE_ASSOCIATION_HASH_EXCLUDE_FIELDS = frozenset(
    {
        "association_id",
        "created_at",
        "content_hash",
    }
)

EFFECT_ESTIMATE_HASH_EXCLUDE_FIELDS = frozenset(
    {
        "estimate_id",
        "created_at",
        "content_hash",
    }
)

EFFECT_STATE_HASH_EXCLUDE_FIELDS = frozenset(
    {
        "state_id",
        "created_at",
        "content_hash",
    }
)

RETENTION_ESTIMATE_HASH_EXCLUDE_FIELDS = frozenset(
    {
        "retention_id",
        "created_at",
        "content_hash",
    }
)


Scalar = str | int | float | bool


class ExposureReferenceEndBasis(StrEnum):
    """Basis for a descriptive end reference, not an exact boundary claim."""

    UNKNOWN = "unknown"
    OBSERVED_AT_PLUS_KNOWN_DURATION = (
        "observed_at_plus_known_duration"
    )


class ResponseIsolationStatus(StrEnum):
    """Observed intervening-stimulus context.

    NO_INTERVENING_STIMULUS_OBSERVED does not claim complete source
    coverage. It only states what the supplied historical evidence shows.
    """

    UNKNOWN = "unknown"
    NO_INTERVENING_STIMULUS_OBSERVED = (
        "no_intervening_stimulus_observed"
    )
    INTERVENING_STIMULUS_OBSERVED = (
        "intervening_stimulus_observed"
    )


class TrainingEffectComponentKind(StrEnum):
    FATIGUE = "fatigue"
    ADAPTATION = "adaptation"


class EstimateStatus(StrEnum):
    UNKNOWN = "unknown"
    ESTIMATED = "estimated"


class EffectEvidenceLevel(StrEnum):
    UNKNOWN = "unknown"
    DESCRIPTIVE = "descriptive"
    ASSOCIATION_SUPPORTED = "association_supported"
    PROSPECTIVELY_VALIDATED = "prospectively_validated"
    PLANNING_AUTHORIZED = "planning_authorized"


class RetentionModelKind(StrEnum):
    UNESTABLISHED = "unestablished"
    EMPIRICAL = "empirical"


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


def _require_finite_number(
    value: object,
    *,
    field_name: str,
) -> float:
    if isinstance(value, bool) or not isinstance(
        value,
        (int, float),
    ):
        raise ValueError(
            f"{field_name} must be numeric."
        )

    numeric = float(value)

    if not math.isfinite(numeric):
        raise ValueError(
            f"{field_name} must be finite."
        )

    return numeric


def _ordered_unique_strings(
    values,
    *,
    field_name: str,
) -> tuple[str, ...]:
    normalized = tuple(
        _require_non_empty(
            value,
            field_name=field_name,
        )
        for value in values
    )

    if len(set(normalized)) != len(normalized):
        raise ValueError(
            f"{field_name} must not contain duplicates."
        )

    return tuple(sorted(normalized))


@dataclass(frozen=True)
class StimulusFeature:
    metric_key: str
    knowledge_status: KnowledgeStatus
    value: Scalar | None
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

        status = KnowledgeStatus(
            self.knowledge_status
        )

        object.__setattr__(
            self,
            "knowledge_status",
            status,
        )

        if status == KnowledgeStatus.KNOWN:
            if self.value is None:
                raise ValueError(
                    "KNOWN stimulus feature requires a value."
                )

            if isinstance(self.value, str):
                if not self.value.strip():
                    raise ValueError(
                        "Known string stimulus value "
                        "must be non-empty."
                    )

            elif isinstance(self.value, bool):
                pass

            elif isinstance(self.value, int):
                pass

            elif isinstance(self.value, float):
                if not math.isfinite(self.value):
                    raise ValueError(
                        "Numeric stimulus value must be finite."
                    )

            else:
                raise ValueError(
                    "Stimulus feature value must be string, integer, "
                    "float, boolean, or null."
                )

        elif self.value is not None:
            raise ValueError(
                "Non-KNOWN stimulus feature requires value=None."
            )


@dataclass(frozen=True)
class RealizedTrainingStimulus:
    """Descriptive realized training stimulus from executed evidence.

    reference_end_at is a derived time reference only. It deliberately does
    not establish an exact actual session boundary.
    """

    stimulus_id: str
    schema_version: str

    athlete_id: str
    workout_session_id: str

    executed_training_evidence_id: str
    executed_training_evidence_hash: str

    exposure_observed_at: datetime
    modality_key: str

    duration_status: KnowledgeStatus
    duration_s: int | None

    reference_end_basis: ExposureReferenceEndBasis
    reference_end_at: datetime | None

    features: tuple[StimulusFeature, ...]

    provenance: ProvenanceKind

    actual_start_boundary_verified: bool
    actual_end_boundary_verified: bool

    causal_effect_established: bool
    planning_authorized: bool

    created_at: datetime

    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(
                self,
                exclude_fields=(
                    REALIZED_STIMULUS_HASH_EXCLUDE_FIELDS
                ),
            )
            == self.content_hash
        )


def build_realized_training_stimulus(
    *,
    stimulus_id: str,
    athlete_id: str,
    workout_session_id: str,
    executed_training_evidence_id: str,
    executed_training_evidence_hash: str,
    exposure_observed_at: datetime,
    modality_key: str,
    duration_status: KnowledgeStatus,
    duration_s: int | None,
    features: tuple[StimulusFeature, ...] = (),
    created_at: datetime,
) -> RealizedTrainingStimulus:
    _require_non_empty(
        stimulus_id,
        field_name="stimulus_id",
    )

    if not stimulus_id.startswith(
        "pt-training-stimulus:"
    ):
        raise ValueError(
            "stimulus_id must use pt-training-stimulus: namespace."
        )

    canonical_athlete = _require_canonical_uuid(
        athlete_id,
        field_name="athlete_id",
    )

    canonical_session = _require_canonical_uuid(
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
            "authoritative executed-training evidence."
        )

    executed_hash = _require_sha256(
        executed_training_evidence_hash,
        field_name="executed_training_evidence_hash",
    )

    observed = to_utc(
        exposure_observed_at,
        field_name="exposure_observed_at",
    )

    created = to_utc(
        created_at,
        field_name="created_at",
    )

    if created < observed:
        raise ValueError(
            "Realized stimulus cannot be created before "
            "its observed exposure."
        )

    modality = _require_non_empty(
        modality_key,
        field_name="modality_key",
    ).strip()

    status = KnowledgeStatus(
        duration_status
    )

    if status == KnowledgeStatus.KNOWN:
        if (
            duration_s is None
            or isinstance(duration_s, bool)
            or not isinstance(duration_s, int)
            or duration_s < 0
        ):
            raise ValueError(
                "Known stimulus duration requires a "
                "non-negative integer."
            )

        duration = duration_s
        reference_end_basis = (
            ExposureReferenceEndBasis
            .OBSERVED_AT_PLUS_KNOWN_DURATION
        )
        reference_end_at = (
            observed
            + timedelta(seconds=duration)
        )

    else:
        if duration_s is not None:
            raise ValueError(
                "Non-KNOWN stimulus duration requires duration_s=None."
            )

        duration = None
        reference_end_basis = (
            ExposureReferenceEndBasis.UNKNOWN
        )
        reference_end_at = None

    ordered_features = tuple(
        sorted(
            tuple(features),
            key=lambda item: item.metric_key,
        )
    )

    feature_keys = tuple(
        item.metric_key
        for item in ordered_features
    )

    if len(set(feature_keys)) != len(feature_keys):
        raise ValueError(
            "Stimulus feature keys must be unique."
        )

    provisional = RealizedTrainingStimulus(
        stimulus_id=stimulus_id,
        schema_version=(
            REALIZED_TRAINING_STIMULUS_SCHEMA_V01
        ),
        athlete_id=canonical_athlete,
        workout_session_id=canonical_session,
        executed_training_evidence_id=(
            executed_training_evidence_id
        ),
        executed_training_evidence_hash=executed_hash,
        exposure_observed_at=observed,
        modality_key=modality,
        duration_status=status,
        duration_s=duration,
        reference_end_basis=reference_end_basis,
        reference_end_at=reference_end_at,
        features=ordered_features,

        # This record is derived from already-frozen executed evidence.
        provenance=ProvenanceKind.DERIVED,

        # P1.7 does not establish exact actual boundaries.
        actual_start_boundary_verified=False,
        actual_end_boundary_verified=False,

        # Realized exposure does not itself prove a biological effect.
        causal_effect_established=False,
        planning_authorized=False,

        created_at=created,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )

    digest = compute_content_hash(
        provisional,
        exclude_fields=(
            REALIZED_STIMULUS_HASH_EXCLUDE_FIELDS
        ),
    )

    return RealizedTrainingStimulus(
        **{
            **provisional.__dict__,
            "content_hash": digest,
        }
    )


@dataclass(frozen=True)
class ObservedResponseAssociation:
    """Historical stimulus-response association without causal attribution."""

    association_id: str
    schema_version: str

    athlete_id: str
    workout_session_id: str

    stimulus_id: str
    stimulus_content_hash: str

    response_evidence_id: str
    response_evidence_hash: str

    response_timing: TrainingResponseTiming
    session_link_basis: TrainingResponseLinkBasis

    response_observed_at: datetime
    response_available_at: datetime

    lag_from_reference_end_status: KnowledgeStatus
    lag_from_reference_end_s: float | None
    reference_end_basis: ExposureReferenceEndBasis

    isolation_status: ResponseIsolationStatus
    intervening_stimulus_ids: tuple[str, ...]

    causal_attribution_established: bool
    effect_inference_authorized: bool
    planning_authorized: bool

    created_at: datetime

    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(
                self,
                exclude_fields=(
                    RESPONSE_ASSOCIATION_HASH_EXCLUDE_FIELDS
                ),
            )
            == self.content_hash
        )


def build_observed_response_association(
    *,
    association_id: str,
    stimulus: RealizedTrainingStimulus,
    response_evidence_id: str,
    response_evidence_hash: str,
    response_workout_session_id: str,
    response_timing: TrainingResponseTiming,
    session_link_basis: TrainingResponseLinkBasis,
    response_observed_at: datetime,
    response_available_at: datetime,
    isolation_status: ResponseIsolationStatus,
    intervening_stimulus_ids: tuple[str, ...] = (),
    created_at: datetime,
) -> ObservedResponseAssociation:
    _require_non_empty(
        association_id,
        field_name="association_id",
    )

    if not association_id.startswith(
        "pt-response-association:"
    ):
        raise ValueError(
            "association_id must use "
            "pt-response-association: namespace."
        )

    if not stimulus.verify_content_hash():
        raise ValueError(
            "Realized training stimulus hash does not verify."
        )

    canonical_response_session = _require_canonical_uuid(
        response_workout_session_id,
        field_name="response_workout_session_id",
    )

    if (
        canonical_response_session
        != stimulus.workout_session_id
    ):
        raise ValueError(
            "Response session does not match realized stimulus session."
        )

    _require_non_empty(
        response_evidence_id,
        field_name="response_evidence_id",
    )

    if not response_evidence_id.startswith(
        "pt-evidence:session-feedback:"
    ):
        raise ValueError(
            "P2.1A1 response association requires durable "
            "SESSION_FEEDBACK evidence."
        )

    response_hash = _require_sha256(
        response_evidence_hash,
        field_name="response_evidence_hash",
    )

    timing = TrainingResponseTiming(
        response_timing
    )

    link_basis = TrainingResponseLinkBasis(
        session_link_basis
    )

    observed = to_utc(
        response_observed_at,
        field_name="response_observed_at",
    )

    available = to_utc(
        response_available_at,
        field_name="response_available_at",
    )

    created = to_utc(
        created_at,
        field_name="created_at",
    )

    if observed < stimulus.exposure_observed_at:
        raise ValueError(
            "Response cannot be observed before the realized "
            "stimulus observation."
        )

    if available < observed:
        raise ValueError(
            "response_available_at must not be before "
            "response_observed_at."
        )

    if created < available:
        raise ValueError(
            "Response association cannot predate response availability."
        )

    if created < stimulus.created_at:
        raise ValueError(
            "Response association cannot predate its stimulus artifact."
        )

    if (
        stimulus.reference_end_at is not None
        and observed >= stimulus.reference_end_at
    ):
        lag_status = KnowledgeStatus.KNOWN
        lag_s = (
            observed
            - stimulus.reference_end_at
        ).total_seconds()
    else:
        # Do not manufacture a negative lag when the descriptive end
        # reference is absent or temporally inconsistent.
        lag_status = KnowledgeStatus.UNKNOWN
        lag_s = None

    isolation = ResponseIsolationStatus(
        isolation_status
    )

    intervening = _ordered_unique_strings(
        intervening_stimulus_ids,
        field_name="intervening_stimulus_id",
    )

    if stimulus.stimulus_id in intervening:
        raise ValueError(
            "A stimulus cannot intervene between itself and its response."
        )

    if (
        isolation
        == ResponseIsolationStatus
        .INTERVENING_STIMULUS_OBSERVED
    ):
        if not intervening:
            raise ValueError(
                "Observed intervening stimulus status requires "
                "at least one intervening stimulus ID."
            )

    elif intervening:
        raise ValueError(
            "Intervening stimulus IDs require "
            "INTERVENING_STIMULUS_OBSERVED status."
        )

    provisional = ObservedResponseAssociation(
        association_id=association_id,
        schema_version=(
            OBSERVED_RESPONSE_ASSOCIATION_SCHEMA_V01
        ),
        athlete_id=stimulus.athlete_id,
        workout_session_id=stimulus.workout_session_id,
        stimulus_id=stimulus.stimulus_id,
        stimulus_content_hash=stimulus.content_hash,
        response_evidence_id=response_evidence_id,
        response_evidence_hash=response_hash,
        response_timing=timing,
        session_link_basis=link_basis,
        response_observed_at=observed,
        response_available_at=available,
        lag_from_reference_end_status=lag_status,
        lag_from_reference_end_s=lag_s,
        reference_end_basis=stimulus.reference_end_basis,
        isolation_status=isolation,
        intervening_stimulus_ids=intervening,

        # Association remains historical/descriptive.
        causal_attribution_established=False,
        effect_inference_authorized=False,
        planning_authorized=False,

        created_at=created,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )

    digest = compute_content_hash(
        provisional,
        exclude_fields=(
            RESPONSE_ASSOCIATION_HASH_EXCLUDE_FIELDS
        ),
    )

    return ObservedResponseAssociation(
        **{
            **provisional.__dict__,
            "content_hash": digest,
        }
    )


@dataclass(frozen=True)
class LatentTrainingEffectEstimate:
    """Estimated, never directly observed, training-effect component."""

    estimate_id: str
    schema_version: str

    athlete_id: str
    component_kind: TrainingEffectComponentKind

    estimated_at: datetime
    information_cutoff_at: datetime

    estimation_status: EstimateStatus
    estimated_value: float | None
    unit: str | None

    evidence_level: EffectEvidenceLevel

    model_id: str | None
    model_version: str | None

    source_stimulus_ids: tuple[str, ...]
    source_response_association_ids: tuple[str, ...]

    causal_attribution_established: bool
    performance_prediction_authorized: bool
    planning_authorized: bool

    created_at: datetime

    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(
                self,
                exclude_fields=(
                    EFFECT_ESTIMATE_HASH_EXCLUDE_FIELDS
                ),
            )
            == self.content_hash
        )


def build_latent_training_effect_estimate(
    *,
    estimate_id: str,
    athlete_id: str,
    component_kind: TrainingEffectComponentKind,
    estimated_at: datetime,
    information_cutoff_at: datetime,
    estimation_status: EstimateStatus,
    estimated_value: float | None = None,
    unit: str | None = None,
    model_id: str | None = None,
    model_version: str | None = None,
    source_stimulus_ids: tuple[str, ...] = (),
    source_response_association_ids: tuple[str, ...] = (),
    created_at: datetime,
) -> LatentTrainingEffectEstimate:
    _require_non_empty(
        estimate_id,
        field_name="estimate_id",
    )

    if not estimate_id.startswith(
        "pt-training-effect-estimate:"
    ):
        raise ValueError(
            "estimate_id must use "
            "pt-training-effect-estimate: namespace."
        )

    canonical_athlete = _require_canonical_uuid(
        athlete_id,
        field_name="athlete_id",
    )

    component = TrainingEffectComponentKind(
        component_kind
    )

    estimated = to_utc(
        estimated_at,
        field_name="estimated_at",
    )

    cutoff = to_utc(
        information_cutoff_at,
        field_name="information_cutoff_at",
    )

    created = to_utc(
        created_at,
        field_name="created_at",
    )

    if cutoff > estimated:
        raise ValueError(
            "information_cutoff_at must not be after estimated_at."
        )

    if created < estimated:
        raise ValueError(
            "Effect estimate cannot be created before estimated_at."
        )

    status = EstimateStatus(
        estimation_status
    )

    stimulus_ids = _ordered_unique_strings(
        source_stimulus_ids,
        field_name="source_stimulus_id",
    )

    association_ids = _ordered_unique_strings(
        source_response_association_ids,
        field_name="source_response_association_id",
    )

    if status == EstimateStatus.UNKNOWN:
        if (
            estimated_value is not None
            or unit is not None
            or model_id is not None
            or model_version is not None
        ):
            raise ValueError(
                "UNKNOWN effect estimate cannot contain numeric "
                "or model values."
            )

        value = None
        unit_value = None
        model_id_value = None
        model_version_value = None
        evidence_level = EffectEvidenceLevel.UNKNOWN

    else:
        if not stimulus_ids and not association_ids:
            raise ValueError(
                "ESTIMATED effect requires source evidence identities."
            )

        value = _require_finite_number(
            estimated_value,
            field_name="estimated_value",
        )

        unit_value = _require_non_empty(
            unit,
            field_name="unit",
        )

        model_id_value = _require_non_empty(
            model_id,
            field_name="model_id",
        )

        model_version_value = _require_non_empty(
            model_version,
            field_name="model_version",
        )

        # P2.1A1 supports descriptive estimates only. Stronger validation
        # levels require later contracts and explicit evidence.
        evidence_level = EffectEvidenceLevel.DESCRIPTIVE

    provisional = LatentTrainingEffectEstimate(
        estimate_id=estimate_id,
        schema_version=(
            LATENT_TRAINING_EFFECT_ESTIMATE_SCHEMA_V01
        ),
        athlete_id=canonical_athlete,
        component_kind=component,
        estimated_at=estimated,
        information_cutoff_at=cutoff,
        estimation_status=status,
        estimated_value=value,
        unit=unit_value,
        evidence_level=evidence_level,
        model_id=model_id_value,
        model_version=model_version_value,
        source_stimulus_ids=stimulus_ids,
        source_response_association_ids=association_ids,

        causal_attribution_established=False,
        performance_prediction_authorized=False,
        planning_authorized=False,

        created_at=created,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )

    digest = compute_content_hash(
        provisional,
        exclude_fields=(
            EFFECT_ESTIMATE_HASH_EXCLUDE_FIELDS
        ),
    )

    return LatentTrainingEffectEstimate(
        **{
            **provisional.__dict__,
            "content_hash": digest,
        }
    )


@dataclass(frozen=True)
class TrainingEffectStateComponent:
    component_kind: TrainingEffectComponentKind

    estimation_status: EstimateStatus
    estimated_value: float | None
    unit: str | None

    evidence_level: EffectEvidenceLevel

    effect_estimate_id: str
    effect_estimate_hash: str


@dataclass(frozen=True)
class LongitudinalTrainingEffectState:
    """Current latent effect state, separate from descriptive training state."""

    state_id: str
    schema_version: str

    athlete_id: str
    as_of: datetime
    information_cutoff_at: datetime

    components: tuple[
        TrainingEffectStateComponent,
        ...,
    ]

    readiness_inference_authorized: bool
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
                    EFFECT_STATE_HASH_EXCLUDE_FIELDS
                ),
            )
            == self.content_hash
        )


def build_longitudinal_training_effect_state(
    *,
    state_id: str,
    athlete_id: str,
    as_of: datetime,
    effect_estimates: tuple[
        LatentTrainingEffectEstimate,
        ...,
    ],
    created_at: datetime,
) -> LongitudinalTrainingEffectState:
    _require_non_empty(
        state_id,
        field_name="state_id",
    )

    if not state_id.startswith(
        "pt-training-effect-state:"
    ):
        raise ValueError(
            "state_id must use pt-training-effect-state: namespace."
        )

    canonical_athlete = _require_canonical_uuid(
        athlete_id,
        field_name="athlete_id",
    )

    state_as_of = to_utc(
        as_of,
        field_name="as_of",
    )

    created = to_utc(
        created_at,
        field_name="created_at",
    )

    if created < state_as_of:
        raise ValueError(
            "Longitudinal effect state cannot be created "
            "before as_of."
        )

    estimates = tuple(effect_estimates)

    if len(estimates) != 2:
        raise ValueError(
            "P2.1A1 effect state requires explicit FATIGUE "
            "and ADAPTATION components."
        )

    expected_components = {
        TrainingEffectComponentKind.FATIGUE,
        TrainingEffectComponentKind.ADAPTATION,
    }

    observed_components = {
        estimate.component_kind
        for estimate in estimates
    }

    if observed_components != expected_components:
        raise ValueError(
            "Effect state must contain exactly one FATIGUE "
            "and one ADAPTATION estimate."
        )

    components = []

    for estimate in estimates:
        if not estimate.verify_content_hash():
            raise ValueError(
                "Effect estimate hash does not verify."
            )

        if estimate.athlete_id != canonical_athlete:
            raise ValueError(
                "Effect estimate athlete differs from state athlete."
            )

        if estimate.estimated_at != state_as_of:
            raise ValueError(
                "Effect estimate time must match state as_of."
            )

        if created < estimate.created_at:
            raise ValueError(
                "Effect state cannot predate an included estimate."
            )

        components.append(
            TrainingEffectStateComponent(
                component_kind=estimate.component_kind,
                estimation_status=estimate.estimation_status,
                estimated_value=estimate.estimated_value,
                unit=estimate.unit,
                evidence_level=estimate.evidence_level,
                effect_estimate_id=estimate.estimate_id,
                effect_estimate_hash=estimate.content_hash,
            )
        )

    ordered_components = tuple(
        sorted(
            components,
            key=lambda item: item.component_kind.value,
        )
    )

    cutoff = max(
        estimate.information_cutoff_at
        for estimate in estimates
    )

    if cutoff > state_as_of:
        raise ValueError(
            "Effect state cutoff must not be after as_of."
        )

    provisional = LongitudinalTrainingEffectState(
        state_id=state_id,
        schema_version=(
            LONGITUDINAL_TRAINING_EFFECT_STATE_SCHEMA_V01
        ),
        athlete_id=canonical_athlete,
        as_of=state_as_of,
        information_cutoff_at=cutoff,
        components=ordered_components,

        # This state remains a bounded estimate, not readiness or policy.
        readiness_inference_authorized=False,
        performance_prediction_authorized=False,
        prescription_change_authorized=False,

        created_at=created,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )

    digest = compute_content_hash(
        provisional,
        exclude_fields=(
            EFFECT_STATE_HASH_EXCLUDE_FIELDS
        ),
    )

    return LongitudinalTrainingEffectState(
        **{
            **provisional.__dict__,
            "content_hash": digest,
        }
    )


@dataclass(frozen=True)
class RetentionEstimate:
    """Model-agnostic estimate of retained adaptation over an interval."""

    retention_id: str
    schema_version: str

    athlete_id: str

    source_state_id: str
    source_state_hash: str

    component_kind: TrainingEffectComponentKind

    from_at: datetime
    to_at: datetime
    elapsed_s: float

    information_cutoff_at: datetime

    estimation_status: EstimateStatus
    retained_effect_value: float | None
    unit: str | None

    model_kind: RetentionModelKind
    model_id: str | None
    model_version: str | None

    evidence_level: EffectEvidenceLevel

    causal_attribution_established: bool
    planning_authorized: bool

    created_at: datetime

    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(
                self,
                exclude_fields=(
                    RETENTION_ESTIMATE_HASH_EXCLUDE_FIELDS
                ),
            )
            == self.content_hash
        )


def build_retention_estimate(
    *,
    retention_id: str,
    source_state: LongitudinalTrainingEffectState,
    to_at: datetime,
    information_cutoff_at: datetime,
    estimation_status: EstimateStatus,
    retained_effect_value: float | None = None,
    unit: str | None = None,
    model_id: str | None = None,
    model_version: str | None = None,
    created_at: datetime,
) -> RetentionEstimate:
    _require_non_empty(
        retention_id,
        field_name="retention_id",
    )

    if not retention_id.startswith(
        "pt-retention-estimate:"
    ):
        raise ValueError(
            "retention_id must use pt-retention-estimate: namespace."
        )

    if not source_state.verify_content_hash():
        raise ValueError(
            "Source longitudinal effect state hash does not verify."
        )

    from_at = source_state.as_of

    target_at = to_utc(
        to_at,
        field_name="to_at",
    )

    cutoff = to_utc(
        information_cutoff_at,
        field_name="information_cutoff_at",
    )

    created = to_utc(
        created_at,
        field_name="created_at",
    )

    if target_at <= from_at:
        raise ValueError(
            "Retention interval to_at must be after from_at."
        )

    if cutoff < source_state.information_cutoff_at:
        raise ValueError(
            "Retention cutoff cannot predate source-state cutoff."
        )

    if cutoff > target_at:
        raise ValueError(
            "Retention cutoff must not be after to_at."
        )

    if created < target_at:
        raise ValueError(
            "P2.1A1 retention estimate cannot forecast a future interval."
        )

    if created < source_state.created_at:
        raise ValueError(
            "Retention estimate cannot predate its source state."
        )

    adaptation = next(
        component
        for component in source_state.components
        if (
            component.component_kind
            == TrainingEffectComponentKind.ADAPTATION
        )
    )

    status = EstimateStatus(
        estimation_status
    )

    if status == EstimateStatus.UNKNOWN:
        if (
            retained_effect_value is not None
            or unit is not None
            or model_id is not None
            or model_version is not None
        ):
            raise ValueError(
                "UNKNOWN retention estimate cannot contain "
                "numeric or model values."
            )

        value = None
        unit_value = None
        model_kind = RetentionModelKind.UNESTABLISHED
        model_id_value = None
        model_version_value = None
        evidence_level = EffectEvidenceLevel.UNKNOWN

    else:
        if (
            adaptation.estimation_status
            != EstimateStatus.ESTIMATED
        ):
            raise ValueError(
                "Retention cannot be numerically estimated from "
                "an UNKNOWN adaptation state."
            )

        value = _require_finite_number(
            retained_effect_value,
            field_name="retained_effect_value",
        )

        unit_value = _require_non_empty(
            unit,
            field_name="unit",
        )

        model_id_value = _require_non_empty(
            model_id,
            field_name="model_id",
        )

        model_version_value = _require_non_empty(
            model_version,
            field_name="model_version",
        )

        # No exponential-decay or fixed half-life assumption is encoded.
        model_kind = RetentionModelKind.EMPIRICAL
        evidence_level = EffectEvidenceLevel.DESCRIPTIVE

    provisional = RetentionEstimate(
        retention_id=retention_id,
        schema_version=RETENTION_ESTIMATE_SCHEMA_V01,
        athlete_id=source_state.athlete_id,
        source_state_id=source_state.state_id,
        source_state_hash=source_state.content_hash,

        # P2.1A1 retention is explicitly adaptation retention.
        component_kind=TrainingEffectComponentKind.ADAPTATION,

        from_at=from_at,
        to_at=target_at,
        elapsed_s=(
            target_at
            - from_at
        ).total_seconds(),
        information_cutoff_at=cutoff,
        estimation_status=status,
        retained_effect_value=value,
        unit=unit_value,
        model_kind=model_kind,
        model_id=model_id_value,
        model_version=model_version_value,
        evidence_level=evidence_level,

        causal_attribution_established=False,
        planning_authorized=False,

        created_at=created,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )

    digest = compute_content_hash(
        provisional,
        exclude_fields=(
            RETENTION_ESTIMATE_HASH_EXCLUDE_FIELDS
        ),
    )

    return RetentionEstimate(
        **{
            **provisional.__dict__,
            "content_hash": digest,
        }
    )
