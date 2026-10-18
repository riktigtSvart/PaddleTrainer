from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ..common.serialization import (
    CONTENT_HASH_ALGORITHM,
    compute_content_hash,
)
from ..common.time import to_utc


ENTRY_GATE_HASH_EXCLUDE_FIELDS = frozenset(
    {"content_hash", "decision_id", "created_at"}
)


class GlobalEntryGate(StrEnum):
    OPEN = "open"
    OPEN_WITH_CONSTRAINTS = "open_with_constraints"
    HOLD = "hold"
    BLOCKED = "blocked"
    REVIEW_REQUIRED = "review_required"


class EntryMode(StrEnum):
    NORMAL_START = "normal_start"
    CONSERVATIVE_REANCHOR = "conservative_reanchor"
    RECOVERY_FIRST = "recovery_first"
    RETURN_FROM_INTERRUPTION = "return_from_interruption"
    CONSTRAINT_LIMITED = "constraint_limited"
    DATA_LIMITED = "data_limited"


class StimulusGateStatus(StrEnum):
    BUILD_ALLOWED = "build_allowed"
    HOLD_ONLY = "hold_only"
    CONSOLIDATE = "consolidate"
    REDUCE_REQUIRED = "reduce_required"
    SUSPEND = "suspend"
    UNKNOWN = "unknown"


class ParticipationConstraintStatus(StrEnum):
    READY = "ready"
    READY_WITH_CONSTRAINTS = "ready_with_constraints"
    OBSERVATION_FIRST = "observation_first"
    PROFESSIONAL_REVIEW_REQUIRED = "professional_review_required"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


class RecoveryConstraintStatus(StrEnum):
    NONE = "none"
    REDUCE_REQUIRED = "reduce_required"
    RECOVERY_FIRST_REQUIRED = "recovery_first_required"
    UNKNOWN = "unknown"


class AvailabilityConstraintStatus(StrEnum):
    AVAILABLE = "available"
    LIMITED = "limited"
    NO_TRAINING_WINDOW = "no_training_window"
    UNKNOWN = "unknown"


class InterruptionStatus(StrEnum):
    NONE = "none"
    RETURNING = "returning"
    UNKNOWN = "unknown"


class EntryGateReasonCode(StrEnum):
    PARTICIPATION_READY_WITH_CONSTRAINTS = (
        "participation_ready_with_constraints"
    )
    PARTICIPATION_OBSERVATION_FIRST = "participation_observation_first"
    PARTICIPATION_REVIEW_REQUIRED = "participation_review_required"
    PARTICIPATION_BLOCKED = "participation_blocked"
    PARTICIPATION_UNKNOWN = "participation_unknown"

    RECOVERY_REDUCTION_REQUIRED = "recovery_reduction_required"
    RECOVERY_FIRST_REQUIRED = "recovery_first_required"
    RECOVERY_UNKNOWN = "recovery_unknown"

    AVAILABILITY_LIMITED = "availability_limited"
    NO_TRAINING_WINDOW = "no_training_window"
    AVAILABILITY_UNKNOWN = "availability_unknown"

    RETURN_FROM_INTERRUPTION = "return_from_interruption"
    INTERRUPTION_UNKNOWN = "interruption_unknown"

    RECENT_EXPOSURE_STALE = "recent_exposure_stale"
    RECENT_EXPOSURE_UNKNOWN = "recent_exposure_unknown"
    LOAD_ANCHOR_PARTIAL = "load_anchor_partial"
    LOAD_ANCHOR_UNKNOWN = "load_anchor_unknown"
    VERIFIED_ZERO_EXPOSURE = "verified_zero_exposure"
    NORMAL_START_SUPPORTED = "normal_start_supported"

    GLOBAL_BLOCK_APPLIED_TO_STIMULUS = (
        "global_block_applied_to_stimulus"
    )
    STIMULUS_SIGNAL_CONFLICT = "stimulus_signal_conflict"
    STIMULUS_SIGNAL_UNKNOWN = "stimulus_signal_unknown"


@dataclass(frozen=True)
class EntryGatePolicy:
    """Versioned interpretation policy; no hidden freshness constant."""

    policy_version: str
    recent_exposure_max_age_s_for_normal_start: int
    require_verified_load_anchor_for_normal_start: bool = True

    def __post_init__(self) -> None:
        if not self.policy_version.strip():
            raise ValueError("policy_version must be non-empty.")
        if self.recent_exposure_max_age_s_for_normal_start < 0:
            raise ValueError(
                "recent_exposure_max_age_s_for_normal_start must be "
                "non-negative."
            )


@dataclass(frozen=True)
class StimulusGateSignal:
    stimulus_key: str
    status: StimulusGateStatus
    reason_code: str
    source_ref: str | None = None

    def __post_init__(self) -> None:
        if not self.stimulus_key.strip():
            raise ValueError("stimulus_key must be non-empty.")
        if not self.reason_code.strip():
            raise ValueError("reason_code must be non-empty.")


@dataclass(frozen=True)
class StimulusGateDecision:
    stimulus_key: str
    status: StimulusGateStatus
    reason_codes: tuple[str, ...]
    source_refs: tuple[str, ...]


@dataclass(frozen=True)
class EntryGateDecision:
    decision_id: str
    athlete_id: str
    schema_version: str
    as_of: datetime
    information_cutoff_at: datetime
    created_at: datetime

    global_gate: GlobalEntryGate
    entry_mode: EntryMode
    stimulus_gates: tuple[StimulusGateDecision, ...]
    reason_codes: tuple[EntryGateReasonCode, ...]

    current_training_state_hash: str
    policy_version: str

    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(
                self,
                exclude_fields=ENTRY_GATE_HASH_EXCLUDE_FIELDS,
            )
            == self.content_hash
        )


def finalize_entry_gate_decision(
    *,
    decision_id: str,
    athlete_id: str,
    schema_version: str,
    as_of: datetime,
    information_cutoff_at: datetime,
    created_at: datetime,
    global_gate: GlobalEntryGate,
    entry_mode: EntryMode,
    stimulus_gates: tuple[StimulusGateDecision, ...],
    reason_codes: tuple[EntryGateReasonCode, ...],
    current_training_state_hash: str,
    policy_version: str,
) -> EntryGateDecision:
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

    provisional = EntryGateDecision(
        decision_id=decision_id,
        athlete_id=athlete_id,
        schema_version=schema_version,
        as_of=as_of_utc,
        information_cutoff_at=cutoff,
        created_at=created,
        global_gate=global_gate,
        entry_mode=entry_mode,
        stimulus_gates=tuple(stimulus_gates),
        reason_codes=tuple(reason_codes),
        current_training_state_hash=current_training_state_hash,
        policy_version=policy_version,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )
    digest = compute_content_hash(
        provisional,
        exclude_fields=ENTRY_GATE_HASH_EXCLUDE_FIELDS,
    )
    return EntryGateDecision(
        decision_id=provisional.decision_id,
        athlete_id=provisional.athlete_id,
        schema_version=provisional.schema_version,
        as_of=provisional.as_of,
        information_cutoff_at=provisional.information_cutoff_at,
        created_at=provisional.created_at,
        global_gate=provisional.global_gate,
        entry_mode=provisional.entry_mode,
        stimulus_gates=provisional.stimulus_gates,
        reason_codes=provisional.reason_codes,
        current_training_state_hash=provisional.current_training_state_hash,
        policy_version=provisional.policy_version,
        content_hash_algorithm=provisional.content_hash_algorithm,
        content_hash=digest,
    )
