from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ..common.enums import KnowledgeStatus
from ..common.serialization import (
    CONTENT_HASH_ALGORITHM,
    compute_content_hash,
)
from ..common.time import to_utc


CURRENT_STATE_HASH_EXCLUDE_FIELDS = frozenset(
    {"content_hash", "state_id", "created_at"}
)


class EvidenceCoverage(StrEnum):
    """Declared source coverage, not inferred from observed record count."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class EvidenceDomain(StrEnum):
    TRAINING_EXPOSURE = "training_exposure"
    RESPONSE = "response"
    PERFORMANCE = "performance"
    MEASUREMENT = "measurement"
    AVAILABILITY = "availability"
    HEALTH_SAFETY = "health_safety"


class LoadAnchorStatus(StrEnum):
    """Descriptive current-exposure anchor status.

    VERIFIED_EXPOSURE means the configured anchor window has declared complete
    source coverage and every observed session has a known duration.
    It does not mean that the exposure is optimal, safe to progress, or a
    prescription target.
    """

    VERIFIED_EXPOSURE = "verified_exposure"
    PARTIAL_EXPOSURE = "partial_exposure"
    VERIFIED_ZERO_EXPOSURE = "verified_zero_exposure"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ObservationWindow:
    start_at: datetime
    end_at: datetime

    def __post_init__(self) -> None:
        start = to_utc(self.start_at, field_name="start_at")
        end = to_utc(self.end_at, field_name="end_at")
        if start > end:
            raise ValueError(
                "ObservationWindow start_at must not exceed end_at."
            )
        object.__setattr__(self, "start_at", start)
        object.__setattr__(self, "end_at", end)


@dataclass(frozen=True)
class DomainCoverageDeclaration:
    domain: EvidenceDomain
    coverage: EvidenceCoverage


@dataclass(frozen=True)
class TrainingExposureObservation:
    evidence_id: str
    session_id: str
    observed_at: datetime
    modality_key: str
    duration_status: KnowledgeStatus
    duration_s: int | None

    def __post_init__(self) -> None:
        observed = to_utc(self.observed_at, field_name="observed_at")
        object.__setattr__(self, "observed_at", observed)

        if not self.evidence_id.strip():
            raise ValueError("evidence_id must be non-empty.")
        if not self.session_id.strip():
            raise ValueError("session_id must be non-empty.")
        if not self.modality_key.strip():
            raise ValueError("modality_key must be non-empty.")

        if self.duration_status == KnowledgeStatus.KNOWN:
            if self.duration_s is None:
                raise ValueError(
                    "Known session duration requires duration_s."
                )
            if self.duration_s < 0:
                raise ValueError("duration_s must be non-negative.")
        elif self.duration_s is not None:
            raise ValueError(
                "Non-KNOWN duration status requires duration_s=None."
            )


@dataclass(frozen=True)
class ModalityExposureSummary:
    modality_key: str
    observed_session_count: int
    known_duration_session_count: int
    observed_known_duration_s: int
    source_evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class TrainingExposureWindowSummary:
    window: ObservationWindow
    source_coverage: EvidenceCoverage

    observed_session_count: int
    known_duration_session_count: int
    observed_known_duration_s: int

    # Only populated when source coverage is COMPLETE and every observed
    # session duration is known. Otherwise actual total exposure is UNKNOWN.
    complete_window_total_duration_s: int | None

    active_days_observed: int
    first_training_observed_at: datetime | None
    last_training_observed_at: datetime | None

    modality_summaries: tuple[ModalityExposureSummary, ...]
    source_evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class LoadAnchorState:
    """Current descriptive exposure anchor; never a prescription target."""

    status: LoadAnchorStatus
    exposure: TrainingExposureWindowSummary
    prescription_target: bool = False


@dataclass(frozen=True)
class EvidenceDomainSummary:
    domain: EvidenceDomain
    source_coverage: EvidenceCoverage
    observed_item_count: int
    first_observed_at: datetime | None
    latest_observed_at: datetime | None
    latest_available_at: datetime | None
    age_s_at_cutoff: int | None
    source_evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class CurrentTrainingState:
    state_id: str
    athlete_id: str
    schema_version: str
    as_of: datetime
    information_cutoff_at: datetime
    created_at: datetime

    recent_exposure: TrainingExposureWindowSummary
    load_anchor: LoadAnchorState
    evidence_domains: tuple[EvidenceDomainSummary, ...]

    source_evidence_bundle_hash: str
    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(
                self,
                exclude_fields=CURRENT_STATE_HASH_EXCLUDE_FIELDS,
            )
            == self.content_hash
        )


def finalize_current_training_state(
    *,
    state_id: str,
    athlete_id: str,
    schema_version: str,
    as_of: datetime,
    information_cutoff_at: datetime,
    created_at: datetime,
    recent_exposure: TrainingExposureWindowSummary,
    load_anchor: LoadAnchorState,
    evidence_domains: tuple[EvidenceDomainSummary, ...],
    source_evidence_bundle_hash: str,
) -> CurrentTrainingState:
    as_of_utc = to_utc(as_of, field_name="as_of")
    cutoff = to_utc(
        information_cutoff_at,
        field_name="information_cutoff_at",
    )
    created = to_utc(created_at, field_name="created_at")

    if cutoff > as_of_utc:
        raise ValueError(
            "information_cutoff_at must not be after as_of."
        )
    if recent_exposure.window.end_at > cutoff:
        raise ValueError(
            "recent exposure window must not extend after information cutoff."
        )
    if load_anchor.exposure.window.end_at > cutoff:
        raise ValueError(
            "load anchor window must not extend after information cutoff."
        )

    provisional = CurrentTrainingState(
        state_id=state_id,
        athlete_id=athlete_id,
        schema_version=schema_version,
        as_of=as_of_utc,
        information_cutoff_at=cutoff,
        created_at=created,
        recent_exposure=recent_exposure,
        load_anchor=load_anchor,
        evidence_domains=tuple(evidence_domains),
        source_evidence_bundle_hash=source_evidence_bundle_hash,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )
    digest = compute_content_hash(
        provisional,
        exclude_fields=CURRENT_STATE_HASH_EXCLUDE_FIELDS,
    )
    return CurrentTrainingState(
        state_id=provisional.state_id,
        athlete_id=provisional.athlete_id,
        schema_version=provisional.schema_version,
        as_of=provisional.as_of,
        information_cutoff_at=provisional.information_cutoff_at,
        created_at=provisional.created_at,
        recent_exposure=provisional.recent_exposure,
        load_anchor=provisional.load_anchor,
        evidence_domains=provisional.evidence_domains,
        source_evidence_bundle_hash=provisional.source_evidence_bundle_hash,
        content_hash_algorithm=provisional.content_hash_algorithm,
        content_hash=digest,
    )
