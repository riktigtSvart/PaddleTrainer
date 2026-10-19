from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
import math
from uuid import UUID

from ..common.serialization import canonical_json
from ..execution_link import AuthoritativePlanExecutionLink
from ..plan_revision.persistence_contract import (
    AuthoritativePlanRevision,
)


OCCURRENCE_EXECUTION_LINK_SCHEMA_VERSION = (
    "authoritative-occurrence-execution-link-v0.1"
)
CONTENT_HASH_ALGORITHM = "sha256"


class OccurrenceExecutionLinkBasis(StrEnum):
    USER_CONFIRMED_CANDIDATE_SEGMENT = (
        "user_confirmed_candidate_segment"
    )


class OccurrenceExecutionNotEligible(ValueError):
    pass


class OccurrenceExecutionConflictError(RuntimeError):
    pass


def _utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(
            f"{field_name} must be offset-aware."
        )
    return value.astimezone(timezone.utc)


def _uuid_text(value: str, *, field_name: str) -> str:
    try:
        return str(UUID(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{field_name} must be a UUID string."
        ) from exc


def _sha256(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _require_sha256(
    value: str,
    *,
    field_name: str,
) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(
            ch not in "0123456789abcdef"
            for ch in value
        )
    ):
        raise ValueError(
            f"{field_name} must be a lowercase SHA-256 "
            "hex digest."
        )
    return value


def _validate_window(
    value: tuple[float, float],
    *,
    field_name: str,
) -> None:
    if not isinstance(value, tuple) or len(value) != 2:
        raise ValueError(
            f"{field_name} must be a two-value tuple."
        )
    for item in value:
        if (
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not math.isfinite(item)
        ):
            raise ValueError(
                f"{field_name} must contain finite numbers."
            )
    if value[0] < 0 or value[1] < value[0]:
        raise ValueError(
            f"{field_name} must be a non-negative "
            "ordered interval."
        )


@dataclass(frozen=True)
class OccurrenceExecutionCandidateEvidence:
    phase_reconciliation_artifact_id: str
    phase_reconciliation_rules_version: str
    session_source_content_hash: str
    plan_source_content_hash: str
    stable_source_occurrence_id: str
    captured_contract_occurrence_id: str
    hypothesis_id: str
    candidate_start_window_s: tuple[float, float]
    candidate_completion_window_s: tuple[float, float]
    clock_domain: str
    provider_event_verified: bool = False
    clock_alignment_verified: bool = False
    actual_boundary_verified: bool = False

    def __post_init__(self) -> None:
        if not self.phase_reconciliation_artifact_id.startswith(
            "phase_reconciliation_"
        ):
            raise ValueError(
                "phase_reconciliation_artifact_id must use "
                "phase_reconciliation_ namespace."
            )
        if not self.phase_reconciliation_rules_version.strip():
            raise ValueError(
                "phase_reconciliation_rules_version must "
                "be non-empty."
            )
        _require_sha256(
            self.session_source_content_hash,
            field_name="session_source_content_hash",
        )
        _require_sha256(
            self.plan_source_content_hash,
            field_name="plan_source_content_hash",
        )
        if not self.stable_source_occurrence_id.startswith(
            "phase-source-occurrence_"
        ):
            raise ValueError(
                "stable_source_occurrence_id must use the "
                "phase-source-occurrence_ namespace."
            )
        if not self.captured_contract_occurrence_id.strip():
            raise ValueError(
                "captured_contract_occurrence_id must "
                "be non-empty."
            )
        if not self.hypothesis_id.startswith("phase_path_"):
            raise ValueError(
                "hypothesis_id must use phase_path_ namespace."
            )
        _validate_window(
            self.candidate_start_window_s,
            field_name="candidate_start_window_s",
        )
        _validate_window(
            self.candidate_completion_window_s,
            field_name="candidate_completion_window_s",
        )
        if not self.clock_domain.strip():
            raise ValueError("clock_domain must be non-empty.")

        # P1.6C1 deliberately consumes candidate evidence only.
        # None of these claims may be silently upgraded.
        if (
            self.provider_event_verified
            or self.clock_alignment_verified
            or self.actual_boundary_verified
        ):
            raise ValueError(
                "Candidate evidence cannot claim provider, "
                "clock, or actual-boundary verification."
            )


@dataclass(frozen=True)
class OccurrenceExecutionConfirmation:
    confirmation_id: str
    athlete_id: str
    workout_session_id: str
    authoritative_occurrence_id: str
    phase_reconciliation_artifact_id: str
    hypothesis_id: str
    stable_source_occurrence_id: str
    submitted_at: datetime
    acknowledges_candidate_boundaries: bool
    acknowledges_not_provider_verified: bool

    def __post_init__(self) -> None:
        if not self.confirmation_id.startswith(
            "pt-occ-exec-confirmation:"
        ):
            raise ValueError(
                "confirmation_id must use "
                "pt-occ-exec-confirmation: namespace."
            )
        _uuid_text(
            self.athlete_id,
            field_name="athlete_id",
        )
        _uuid_text(
            self.workout_session_id,
            field_name="workout_session_id",
        )
        if not self.authoritative_occurrence_id.startswith(
            "pt-occ:"
        ):
            raise ValueError(
                "authoritative_occurrence_id must use "
                "pt-occ: namespace."
            )
        if not self.phase_reconciliation_artifact_id.startswith(
            "phase_reconciliation_"
        ):
            raise ValueError(
                "phase_reconciliation_artifact_id must use "
                "phase_reconciliation_ namespace."
            )
        if not self.hypothesis_id.startswith("phase_path_"):
            raise ValueError(
                "hypothesis_id must use phase_path_ namespace."
            )
        if not self.stable_source_occurrence_id.startswith(
            "phase-source-occurrence_"
        ):
            raise ValueError(
                "stable_source_occurrence_id must use "
                "phase-source-occurrence_ namespace."
            )
        _utc(self.submitted_at, field_name="submitted_at")

        for field_name, value in (
            (
                "acknowledges_candidate_boundaries",
                self.acknowledges_candidate_boundaries,
            ),
            (
                "acknowledges_not_provider_verified",
                self.acknowledges_not_provider_verified,
            ),
        ):
            if type(value) is not bool:
                raise ValueError(
                    f"{field_name} must be boolean."
                )


@dataclass(frozen=True)
class AuthoritativeOccurrenceExecutionLink:
    link_id: str
    schema_version: str
    athlete_id: str
    plan_execution_link_id: str
    logical_plan_id: str
    observed_revision_id: str
    authoritative_occurrence_id: str
    workout_session_id: str
    link_basis: OccurrenceExecutionLinkBasis

    phase_reconciliation_artifact_id: str
    phase_reconciliation_rules_version: str
    session_source_content_hash: str
    plan_source_content_hash: str

    stable_source_occurrence_id: str
    captured_contract_occurrence_id: str
    hypothesis_id: str

    candidate_start_window_s: tuple[float, float]
    candidate_completion_window_s: tuple[float, float]
    clock_domain: str

    confirmation_id: str
    confirmation_submitted_at: datetime

    occurrence_alignment_status: str
    plan_content_at_execution_status: str
    provider_event_verified: bool
    clock_alignment_verified: bool
    actual_boundary_verified: bool
    temporal_match_used: bool

    created_at: datetime
    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            _occurrence_execution_link_content_hash(self)
            == self.content_hash
        )


def _occurrence_execution_link_payload(
    link: AuthoritativeOccurrenceExecutionLink,
) -> dict:
    return {
        "link_id": link.link_id,
        "schema_version": link.schema_version,
        "athlete_id": link.athlete_id,
        "plan_execution_link_id":
            link.plan_execution_link_id,
        "logical_plan_id": link.logical_plan_id,
        "observed_revision_id":
            link.observed_revision_id,
        "authoritative_occurrence_id":
            link.authoritative_occurrence_id,
        "workout_session_id":
            link.workout_session_id,
        "link_basis": link.link_basis.value,
        "phase_reconciliation_artifact_id":
            link.phase_reconciliation_artifact_id,
        "phase_reconciliation_rules_version":
            link.phase_reconciliation_rules_version,
        "session_source_content_hash":
            link.session_source_content_hash,
        "plan_source_content_hash":
            link.plan_source_content_hash,
        "stable_source_occurrence_id":
            link.stable_source_occurrence_id,
        "captured_contract_occurrence_id":
            link.captured_contract_occurrence_id,
        "hypothesis_id": link.hypothesis_id,
        "candidate_start_window_s":
            list(link.candidate_start_window_s),
        "candidate_completion_window_s":
            list(link.candidate_completion_window_s),
        "clock_domain": link.clock_domain,
        "confirmation_id": link.confirmation_id,
        "confirmation_submitted_at":
            link.confirmation_submitted_at.isoformat(),
        "occurrence_alignment_status":
            link.occurrence_alignment_status,
        "plan_content_at_execution_status":
            link.plan_content_at_execution_status,
        "provider_event_verified":
            link.provider_event_verified,
        "clock_alignment_verified":
            link.clock_alignment_verified,
        "actual_boundary_verified":
            link.actual_boundary_verified,
        "temporal_match_used":
            link.temporal_match_used,
        "created_at": link.created_at.isoformat(),
        "content_hash_algorithm":
            link.content_hash_algorithm,
    }


def _occurrence_execution_link_content_hash(
    link: AuthoritativeOccurrenceExecutionLink,
) -> str:
    return _sha256(
        canonical_json(
            _occurrence_execution_link_payload(link)
        )
    )


def finalize_authoritative_occurrence_execution_link(
    *,
    link_id: str,
    plan_execution_link: AuthoritativePlanExecutionLink,
    observed_revision: AuthoritativePlanRevision,
    candidate: OccurrenceExecutionCandidateEvidence,
    confirmation: OccurrenceExecutionConfirmation | None,
    created_at: datetime,
) -> AuthoritativeOccurrenceExecutionLink:
    """Promote only explicit user-confirmed candidate segmentation.

    The resulting link proves a user-confirmed occurrence/segment
    association. It does not prove provider phase events, precise
    clock alignment, exact boundaries, or historical plan content.
    """
    if confirmation is None:
        raise OccurrenceExecutionNotEligible(
            "Explicit occurrence execution confirmation is required."
        )

    if not link_id.startswith("pt-occ-exec-link:"):
        raise ValueError(
            "link_id must use pt-occ-exec-link: namespace."
        )

    if not plan_execution_link.verify_content_hash():
        raise OccurrenceExecutionNotEligible(
            "Authoritative plan execution link hash is invalid."
        )
    if (
        not observed_revision.verify_content_hash()
        or not observed_revision.verify_contract_hash()
    ):
        raise OccurrenceExecutionNotEligible(
            "Observed authoritative revision hash is invalid."
        )

    if (
        observed_revision.revision_id
        != plan_execution_link.observed_revision_id
    ):
        raise OccurrenceExecutionNotEligible(
            "Occurrence reconciliation must use the revision "
            "frozen by the plan execution link."
        )
    if (
        observed_revision.content_hash
        != plan_execution_link.observed_revision_content_hash
    ):
        raise OccurrenceExecutionNotEligible(
            "Observed revision content differs from the "
            "frozen execution-link revision hash."
        )
    if (
        observed_revision.logical_plan_id
        != plan_execution_link.logical_plan_id
        or observed_revision.athlete_id
        != plan_execution_link.athlete_id
    ):
        raise OccurrenceExecutionNotEligible(
            "Observed revision identity differs from the "
            "plan execution link."
        )

    if (
        confirmation.athlete_id
        != plan_execution_link.athlete_id
        or confirmation.workout_session_id
        != plan_execution_link.workout_session_id
    ):
        raise OccurrenceExecutionNotEligible(
            "Confirmation athlete/session differs from the "
            "plan execution link."
        )

    if (
        candidate.session_source_content_hash
        != plan_execution_link.session_source_content_hash
    ):
        raise OccurrenceExecutionNotEligible(
            "Session source changed after the authoritative "
            "plan execution link was established."
        )
    if (
        candidate.plan_source_content_hash
        != plan_execution_link.source_workout_content_hash
    ):
        raise OccurrenceExecutionNotEligible(
            "Plan source changed after the authoritative "
            "plan execution link was established."
        )

    if (
        confirmation.phase_reconciliation_artifact_id
        != candidate.phase_reconciliation_artifact_id
        or confirmation.hypothesis_id
        != candidate.hypothesis_id
        or confirmation.stable_source_occurrence_id
        != candidate.stable_source_occurrence_id
    ):
        raise OccurrenceExecutionNotEligible(
            "Confirmation does not identify the supplied "
            "phase candidate."
        )

    if not confirmation.acknowledges_candidate_boundaries:
        raise OccurrenceExecutionNotEligible(
            "Candidate-boundary acknowledgement is required."
        )
    if not confirmation.acknowledges_not_provider_verified:
        raise OccurrenceExecutionNotEligible(
            "Non-provider-verification acknowledgement "
            "is required."
        )

    occurrences = [
        occurrence
        for occurrence in observed_revision.occurrences
        if occurrence.occurrence_id
        == confirmation.authoritative_occurrence_id
    ]
    if len(occurrences) != 1:
        raise OccurrenceExecutionNotEligible(
            "Authoritative occurrence is not uniquely present "
            "in the observed revision."
        )

    occurrence = occurrences[0]
    if occurrence.source_capture_occurrence_id is None:
        raise OccurrenceExecutionNotEligible(
            "Authoritative occurrence has no source-capture "
            "identity mapping."
        )
    if (
        occurrence.source_capture_occurrence_id
        != candidate.captured_contract_occurrence_id
    ):
        raise OccurrenceExecutionNotEligible(
            "Phase candidate does not map to the "
            "authoritative occurrence source identity."
        )

    confirmation_at = _utc(
        confirmation.submitted_at,
        field_name="confirmation.submitted_at",
    )
    created = _utc(
        created_at,
        field_name="created_at",
    )
    if created < confirmation_at:
        raise ValueError(
            "created_at must not precede confirmation."
        )

    provisional = AuthoritativeOccurrenceExecutionLink(
        link_id=link_id,
        schema_version=(
            OCCURRENCE_EXECUTION_LINK_SCHEMA_VERSION
        ),
        athlete_id=plan_execution_link.athlete_id,
        plan_execution_link_id=(
            plan_execution_link.link_id
        ),
        logical_plan_id=(
            plan_execution_link.logical_plan_id
        ),
        observed_revision_id=(
            plan_execution_link.observed_revision_id
        ),
        authoritative_occurrence_id=(
            occurrence.occurrence_id
        ),
        workout_session_id=(
            plan_execution_link.workout_session_id
        ),
        link_basis=(
            OccurrenceExecutionLinkBasis
            .USER_CONFIRMED_CANDIDATE_SEGMENT
        ),
        phase_reconciliation_artifact_id=(
            candidate.phase_reconciliation_artifact_id
        ),
        phase_reconciliation_rules_version=(
            candidate.phase_reconciliation_rules_version
        ),
        session_source_content_hash=(
            candidate.session_source_content_hash
        ),
        plan_source_content_hash=(
            candidate.plan_source_content_hash
        ),
        stable_source_occurrence_id=(
            candidate.stable_source_occurrence_id
        ),
        captured_contract_occurrence_id=(
            candidate.captured_contract_occurrence_id
        ),
        hypothesis_id=candidate.hypothesis_id,
        candidate_start_window_s=(
            candidate.candidate_start_window_s
        ),
        candidate_completion_window_s=(
            candidate.candidate_completion_window_s
        ),
        clock_domain=candidate.clock_domain,
        confirmation_id=confirmation.confirmation_id,
        confirmation_submitted_at=confirmation_at,

        # This is deliberately narrower than provider/event
        # verification.
        occurrence_alignment_status=(
            "user_confirmed_candidate_segment"
        ),

        # P1.6C must never silently strengthen P1.6B's
        # historical-content claim.
        plan_content_at_execution_status=(
            plan_execution_link
            .plan_content_at_execution_status
        ),

        # Existing reconciliation candidates explicitly do not
        # establish any of these stronger facts.
        provider_event_verified=False,
        clock_alignment_verified=False,
        actual_boundary_verified=False,

        # Temporal proximity is never occurrence identity evidence.
        temporal_match_used=False,

        created_at=created,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )

    return AuthoritativeOccurrenceExecutionLink(
        **{
            **provisional.__dict__,
            "content_hash":
                _occurrence_execution_link_content_hash(
                    provisional
                ),
        }
    )

def restore_authoritative_occurrence_execution_link(
    *,
    link_id: str,
    schema_version: str,
    athlete_id: str,
    plan_execution_link_id: str,
    logical_plan_id: str,
    observed_revision_id: str,
    authoritative_occurrence_id: str,
    workout_session_id: str,
    link_basis: OccurrenceExecutionLinkBasis,
    phase_reconciliation_artifact_id: str,
    phase_reconciliation_rules_version: str,
    session_source_content_hash: str,
    plan_source_content_hash: str,
    stable_source_occurrence_id: str,
    captured_contract_occurrence_id: str,
    hypothesis_id: str,
    candidate_start_window_s: tuple[float, float],
    candidate_completion_window_s: tuple[float, float],
    clock_domain: str,
    confirmation_id: str,
    confirmation_submitted_at: datetime,
    occurrence_alignment_status: str,
    plan_content_at_execution_status: str,
    provider_event_verified: bool,
    clock_alignment_verified: bool,
    actual_boundary_verified: bool,
    temporal_match_used: bool,
    created_at: datetime,
    content_hash_algorithm: str,
    content_hash: str,
) -> AuthoritativeOccurrenceExecutionLink:
    """Restore one persisted link while rechecking immutable invariants."""
    if not link_id.startswith("pt-occ-exec-link:"):
        raise ValueError(
            "link_id must use pt-occ-exec-link: namespace."
        )
    if schema_version != OCCURRENCE_EXECUTION_LINK_SCHEMA_VERSION:
        raise ValueError(
            "Unsupported occurrence execution schema version."
        )

    athlete_id = _uuid_text(
        athlete_id,
        field_name="athlete_id",
    )
    workout_session_id = _uuid_text(
        workout_session_id,
        field_name="workout_session_id",
    )

    if not plan_execution_link_id.startswith("pt-exec-link:"):
        raise ValueError(
            "plan_execution_link_id must use pt-exec-link: namespace."
        )
    if not logical_plan_id.strip():
        raise ValueError("logical_plan_id must be non-empty.")
    if not observed_revision_id.startswith("pt-plan-rev:"):
        raise ValueError(
            "observed_revision_id must use pt-plan-rev: namespace."
        )
    if not authoritative_occurrence_id.startswith("pt-occ:"):
        raise ValueError(
            "authoritative_occurrence_id must use pt-occ: namespace."
        )
    if (
        link_basis
        != OccurrenceExecutionLinkBasis
        .USER_CONFIRMED_CANDIDATE_SEGMENT
    ):
        raise ValueError(
            "Unsupported occurrence execution link basis."
        )

    if not phase_reconciliation_artifact_id.startswith(
        "phase_reconciliation_"
    ):
        raise ValueError(
            "Invalid phase reconciliation artifact identity."
        )
    if not phase_reconciliation_rules_version.strip():
        raise ValueError(
            "phase_reconciliation_rules_version must be non-empty."
        )

    session_source_content_hash = _require_sha256(
        session_source_content_hash,
        field_name="session_source_content_hash",
    )
    plan_source_content_hash = _require_sha256(
        plan_source_content_hash,
        field_name="plan_source_content_hash",
    )

    if not stable_source_occurrence_id.startswith(
        "phase-source-occurrence_"
    ):
        raise ValueError(
            "Invalid stable source occurrence identity."
        )
    if not captured_contract_occurrence_id.strip():
        raise ValueError(
            "captured_contract_occurrence_id must be non-empty."
        )
    if not hypothesis_id.startswith("phase_path_"):
        raise ValueError("Invalid hypothesis identity.")

    _validate_window(
        candidate_start_window_s,
        field_name="candidate_start_window_s",
    )
    _validate_window(
        candidate_completion_window_s,
        field_name="candidate_completion_window_s",
    )

    if not clock_domain.strip():
        raise ValueError("clock_domain must be non-empty.")
    if not confirmation_id.startswith(
        "pt-occ-exec-confirmation:"
    ):
        raise ValueError(
            "Invalid occurrence execution confirmation identity."
        )

    confirmation_at = _utc(
        confirmation_submitted_at,
        field_name="confirmation_submitted_at",
    )
    created = _utc(created_at, field_name="created_at")
    if created < confirmation_at:
        raise ValueError(
            "created_at must not precede confirmation."
        )

    if occurrence_alignment_status != (
        "user_confirmed_candidate_segment"
    ):
        raise ValueError(
            "Unsupported occurrence alignment status."
        )
    if plan_content_at_execution_status != "unverified":
        raise ValueError(
            "Historical plan content must remain unverified."
        )

    if (
        provider_event_verified
        or clock_alignment_verified
        or actual_boundary_verified
        or temporal_match_used
    ):
        raise ValueError(
            "Stored P1.6C candidate link claims unsupported "
            "verification authority."
        )

    if content_hash_algorithm != CONTENT_HASH_ALGORITHM:
        raise ValueError(
            "Unsupported content hash algorithm."
        )
    _require_sha256(
        content_hash,
        field_name="content_hash",
    )

    provisional = AuthoritativeOccurrenceExecutionLink(
        link_id=link_id,
        schema_version=schema_version,
        athlete_id=athlete_id,
        plan_execution_link_id=plan_execution_link_id,
        logical_plan_id=logical_plan_id,
        observed_revision_id=observed_revision_id,
        authoritative_occurrence_id=authoritative_occurrence_id,
        workout_session_id=workout_session_id,
        link_basis=link_basis,
        phase_reconciliation_artifact_id=(
            phase_reconciliation_artifact_id
        ),
        phase_reconciliation_rules_version=(
            phase_reconciliation_rules_version
        ),
        session_source_content_hash=(
            session_source_content_hash
        ),
        plan_source_content_hash=plan_source_content_hash,
        stable_source_occurrence_id=(
            stable_source_occurrence_id
        ),
        captured_contract_occurrence_id=(
            captured_contract_occurrence_id
        ),
        hypothesis_id=hypothesis_id,
        candidate_start_window_s=(
            candidate_start_window_s
        ),
        candidate_completion_window_s=(
            candidate_completion_window_s
        ),
        clock_domain=clock_domain,
        confirmation_id=confirmation_id,
        confirmation_submitted_at=confirmation_at,
        occurrence_alignment_status=(
            occurrence_alignment_status
        ),
        plan_content_at_execution_status=(
            plan_content_at_execution_status
        ),
        provider_event_verified=False,
        clock_alignment_verified=False,
        actual_boundary_verified=False,
        temporal_match_used=False,
        created_at=created,
        content_hash_algorithm=content_hash_algorithm,
        content_hash="",
    )

    expected = _occurrence_execution_link_content_hash(
        provisional
    )
    if expected != content_hash:
        raise ValueError(
            "Stored authoritative occurrence execution "
            "link hash mismatch."
        )

    return AuthoritativeOccurrenceExecutionLink(
        **{
            **provisional.__dict__,
            "content_hash": content_hash,
        }
    )
