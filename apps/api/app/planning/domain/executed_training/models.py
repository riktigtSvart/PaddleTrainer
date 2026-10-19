from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..common.enums import KnowledgeStatus
from ..common.serialization import (
    CONTENT_HASH_ALGORITHM,
    compute_content_hash,
)
from ..common.time import to_utc
from ..execution_link import AuthoritativePlanExecutionLink
from ..occurrence_execution import (
    AuthoritativeOccurrenceExecutionLink,
    OccurrenceExecutionLinkBasis,
)


AUTHORITATIVE_EXECUTED_TRAINING_SCHEMA_VERSION = (
    "authoritative-executed-training-evidence-v0.1"
)

AUTHORITATIVE_EXECUTED_TRAINING_HASH_EXCLUDE_FIELDS = (
    frozenset(
        {
            "artifact_id",
            "created_at",
            "content_hash",
        }
    )
)


@dataclass(frozen=True)
class ExecutedOccurrenceAssociation:
    occurrence_execution_link_id: str
    occurrence_execution_link_content_hash: str

    authoritative_occurrence_id: str
    link_basis: str

    phase_reconciliation_artifact_id: str
    phase_reconciliation_rules_version: str

    stable_source_occurrence_id: str
    captured_contract_occurrence_id: str
    hypothesis_id: str

    candidate_start_window_s: tuple[float, float]
    candidate_completion_window_s: tuple[float, float]
    clock_domain: str

    confirmation_id: str
    confirmation_submitted_at: datetime

    occurrence_alignment_status: str

    provider_event_verified: bool
    clock_alignment_verified: bool
    actual_boundary_verified: bool
    temporal_match_used: bool


@dataclass(frozen=True)
class AuthoritativeExecutedTrainingEvidence:
    """Frozen execution evidence for planning-state consumption.

    This artifact proves that one execution is authoritatively linked
    to one logical plan identity. Optional occurrence associations are
    explicit user-confirmed candidate associations only.

    It does not prove exact phase boundaries, provider phase events,
    clock alignment, historical plan content, readiness, fatigue, or
    a prescription decision.
    """

    artifact_id: str
    schema_version: str

    athlete_id: str
    workout_session_id: str

    observed_at: datetime
    modality_key: str
    duration_status: KnowledgeStatus
    duration_s: int | None

    plan_execution_link_id: str
    plan_execution_link_content_hash: str

    logical_plan_id: str
    observed_revision_id: str
    observed_revision_content_hash: str

    source_workout_id: str
    source_workout_content_hash: str
    session_source_content_hash: str

    execution_link_basis: str
    provider_target_id: str | None

    plan_identity_linked: bool
    plan_content_at_execution_status: str

    occurrence_associations: tuple[
        ExecutedOccurrenceAssociation,
        ...
    ]

    occurrence_alignment_verified: bool
    phase_alignment_verified: bool
    provider_event_verified: bool
    clock_alignment_verified: bool
    actual_boundary_verified: bool
    temporal_match_used: bool

    created_at: datetime
    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(
                self,
                exclude_fields=(
                    AUTHORITATIVE_EXECUTED_TRAINING_HASH_EXCLUDE_FIELDS
                ),
            )
            == self.content_hash
        )


def _require_sha256(
    value: str,
    *,
    field_name: str,
) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(
            char not in "0123456789abcdef"
            for char in value
        )
    ):
        raise ValueError(
            f"{field_name} must be a lowercase SHA-256 hex digest."
        )
    return value


def _require_window(
    value: tuple[float, float],
    *,
    field_name: str,
) -> tuple[float, float]:
    if not isinstance(value, tuple) or len(value) != 2:
        raise ValueError(
            f"{field_name} must contain exactly two values."
        )

    start = float(value[0])
    end = float(value[1])

    if start < 0 or end < start:
        raise ValueError(
            f"{field_name} must be non-negative and ordered."
        )

    return (start, end)


def _duration(
    *,
    status: KnowledgeStatus,
    duration_s: int | None,
) -> int | None:
    if not isinstance(status, KnowledgeStatus):
        raise ValueError(
            "duration_status must be KnowledgeStatus."
        )

    if status == KnowledgeStatus.KNOWN:
        if (
            duration_s is None
            or isinstance(duration_s, bool)
            or not isinstance(duration_s, int)
            or duration_s < 0
        ):
            raise ValueError(
                "Known duration requires a non-negative integer."
            )
        return duration_s

    if duration_s is not None:
        raise ValueError(
            "Non-KNOWN duration requires duration_s=None."
        )

    return None


def build_authoritative_executed_training_evidence(
    *,
    artifact_id: str,
    plan_execution_link: AuthoritativePlanExecutionLink,
    occurrence_execution_links: tuple[
        AuthoritativeOccurrenceExecutionLink,
        ...
    ] = (),
    observed_at: datetime,
    modality_key: str,
    duration_status: KnowledgeStatus,
    duration_s: int | None,
    created_at: datetime,
) -> AuthoritativeExecutedTrainingEvidence:
    """Build one bounded session-level executed-training artifact."""

    if not artifact_id.startswith(
        "pt-executed-training-evidence:"
    ):
        raise ValueError(
            "artifact_id must use "
            "pt-executed-training-evidence: namespace."
        )

    if (
        not isinstance(modality_key, str)
        or not modality_key.strip()
    ):
        raise ValueError(
            "modality_key must be non-empty."
        )

    if not plan_execution_link.verify_content_hash():
        raise ValueError(
            "Authoritative plan execution-link hash "
            "does not verify."
        )

    if (
        plan_execution_link
        .plan_content_at_execution_status
        != "unverified"
    ):
        raise ValueError(
            "Unexpected stronger historical plan-content claim."
        )

    if plan_execution_link.temporal_match_used is not False:
        raise ValueError(
            "Temporal proximity cannot establish execution authority."
        )

    observed = to_utc(
        observed_at,
        field_name="observed_at",
    )
    created = to_utc(
        created_at,
        field_name="created_at",
    )

    if created < observed:
        raise ValueError(
            "created_at must not be before observed_at."
        )

    plan_created = to_utc(
        plan_execution_link.created_at,
        field_name="plan_execution_link.created_at",
    )
    if created < plan_created:
        raise ValueError(
            "Executed-training evidence cannot predate "
            "its plan execution link."
        )

    duration = _duration(
        status=duration_status,
        duration_s=duration_s,
    )

    plan_link_hash = _require_sha256(
        plan_execution_link.content_hash,
        field_name="plan_execution_link.content_hash",
    )
    source_workout_hash = _require_sha256(
        plan_execution_link.source_workout_content_hash,
        field_name="source_workout_content_hash",
    )
    session_hash = _require_sha256(
        plan_execution_link.session_source_content_hash,
        field_name="session_source_content_hash",
    )
    revision_hash = _require_sha256(
        plan_execution_link.observed_revision_content_hash,
        field_name="observed_revision_content_hash",
    )

    occurrence_ids: set[str] = set()
    occurrence_link_ids: set[str] = set()
    source_candidates: set[tuple[str, str]] = set()
    associations: list[ExecutedOccurrenceAssociation] = []

    for link in occurrence_execution_links:
        if not link.verify_content_hash():
            raise ValueError(
                "Occurrence execution-link hash does not verify."
            )

        if link.athlete_id != plan_execution_link.athlete_id:
            raise ValueError(
                "Occurrence link athlete differs from "
                "plan execution link."
            )

        if (
            link.workout_session_id
            != plan_execution_link.workout_session_id
        ):
            raise ValueError(
                "Occurrence link session differs from "
                "plan execution link."
            )

        if (
            link.plan_execution_link_id
            != plan_execution_link.link_id
        ):
            raise ValueError(
                "Occurrence link belongs to another "
                "plan execution link."
            )

        if (
            link.logical_plan_id
            != plan_execution_link.logical_plan_id
            or link.observed_revision_id
            != plan_execution_link.observed_revision_id
        ):
            raise ValueError(
                "Occurrence link authoritative plan identity differs."
            )

        if (
            link.session_source_content_hash
            != session_hash
            or link.plan_source_content_hash
            != source_workout_hash
        ):
            raise ValueError(
                "Occurrence link source hashes differ from "
                "the frozen plan execution evidence."
            )

        if (
            link.plan_content_at_execution_status
            != plan_execution_link
            .plan_content_at_execution_status
        ):
            raise ValueError(
                "Occurrence link historical-content status differs."
            )

        if (
            link.link_basis
            != OccurrenceExecutionLinkBasis
            .USER_CONFIRMED_CANDIDATE_SEGMENT
            or link.occurrence_alignment_status
            != "user_confirmed_candidate_segment"
        ):
            raise ValueError(
                "Unsupported occurrence association authority."
            )

        if (
            link.provider_event_verified is not False
            or link.clock_alignment_verified is not False
            or link.actual_boundary_verified is not False
            or link.temporal_match_used is not False
        ):
            raise ValueError(
                "Occurrence link contains an unsupported "
                "stronger execution claim."
            )

        if (
            link.authoritative_occurrence_id
            in occurrence_ids
        ):
            raise ValueError(
                "Duplicate authoritative occurrence association."
            )
        occurrence_ids.add(
            link.authoritative_occurrence_id
        )

        if link.link_id in occurrence_link_ids:
            raise ValueError(
                "Duplicate occurrence execution-link identity."
            )
        occurrence_link_ids.add(link.link_id)

        source_candidate = (
            link.phase_reconciliation_artifact_id,
            link.stable_source_occurrence_id,
        )
        if source_candidate in source_candidates:
            raise ValueError(
                "Duplicate reconciliation source candidate."
            )
        source_candidates.add(source_candidate)

        link_created = to_utc(
            link.created_at,
            field_name="occurrence_execution_link.created_at",
        )
        if created < link_created:
            raise ValueError(
                "Executed-training evidence cannot predate "
                "an included occurrence execution link."
            )

        association = ExecutedOccurrenceAssociation(
            occurrence_execution_link_id=link.link_id,
            occurrence_execution_link_content_hash=(
                _require_sha256(
                    link.content_hash,
                    field_name=(
                        "occurrence_execution_link.content_hash"
                    ),
                )
            ),
            authoritative_occurrence_id=(
                link.authoritative_occurrence_id
            ),
            link_basis=link.link_basis.value,
            phase_reconciliation_artifact_id=(
                link.phase_reconciliation_artifact_id
            ),
            phase_reconciliation_rules_version=(
                link.phase_reconciliation_rules_version
            ),
            stable_source_occurrence_id=(
                link.stable_source_occurrence_id
            ),
            captured_contract_occurrence_id=(
                link.captured_contract_occurrence_id
            ),
            hypothesis_id=link.hypothesis_id,
            candidate_start_window_s=_require_window(
                link.candidate_start_window_s,
                field_name="candidate_start_window_s",
            ),
            candidate_completion_window_s=_require_window(
                link.candidate_completion_window_s,
                field_name="candidate_completion_window_s",
            ),
            clock_domain=link.clock_domain,
            confirmation_id=link.confirmation_id,
            confirmation_submitted_at=to_utc(
                link.confirmation_submitted_at,
                field_name="confirmation_submitted_at",
            ),
            occurrence_alignment_status=(
                link.occurrence_alignment_status
            ),
            provider_event_verified=False,
            clock_alignment_verified=False,
            actual_boundary_verified=False,
            temporal_match_used=False,
        )
        associations.append(association)

    ordered_associations = tuple(
        sorted(
            associations,
            key=lambda item: (
                item.authoritative_occurrence_id,
                item.occurrence_execution_link_id,
            ),
        )
    )

    provisional = AuthoritativeExecutedTrainingEvidence(
        artifact_id=artifact_id,
        schema_version=(
            AUTHORITATIVE_EXECUTED_TRAINING_SCHEMA_VERSION
        ),
        athlete_id=plan_execution_link.athlete_id,
        workout_session_id=(
            plan_execution_link.workout_session_id
        ),
        observed_at=observed,
        modality_key=modality_key.strip(),
        duration_status=duration_status,
        duration_s=duration,
        plan_execution_link_id=(
            plan_execution_link.link_id
        ),
        plan_execution_link_content_hash=plan_link_hash,
        logical_plan_id=(
            plan_execution_link.logical_plan_id
        ),
        observed_revision_id=(
            plan_execution_link.observed_revision_id
        ),
        observed_revision_content_hash=revision_hash,
        source_workout_id=(
            plan_execution_link.source_workout_id
        ),
        source_workout_content_hash=source_workout_hash,
        session_source_content_hash=session_hash,
        execution_link_basis=(
            plan_execution_link.link_basis.value
        ),
        provider_target_id=(
            plan_execution_link.provider_target_id
        ),
        plan_identity_linked=True,
        plan_content_at_execution_status="unverified",
        occurrence_associations=ordered_associations,

        # P1.7A deliberately preserves the weaker authority
        # established by P1.6/P1.6C.
        occurrence_alignment_verified=False,
        phase_alignment_verified=False,
        provider_event_verified=False,
        clock_alignment_verified=False,
        actual_boundary_verified=False,
        temporal_match_used=False,

        created_at=created,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )

    digest = compute_content_hash(
        provisional,
        exclude_fields=(
            AUTHORITATIVE_EXECUTED_TRAINING_HASH_EXCLUDE_FIELDS
        ),
    )

    return AuthoritativeExecutedTrainingEvidence(
        **{
            **provisional.__dict__,
            "content_hash": digest,
        }
    )
