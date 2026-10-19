from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Protocol
from uuid import uuid4

from ..domain.occurrence_execution.models import (
    AuthoritativeOccurrenceExecutionLink,
    OccurrenceExecutionCandidateEvidence,
    OccurrenceExecutionConfirmation,
    OccurrenceExecutionConflictError,
    OccurrenceExecutionNotEligible,
    finalize_authoritative_occurrence_execution_link,
)
from ..ports.authoritative_occurrence_execution import (
    AuthoritativeOccurrenceExecutionLinkRepository,
)
from ..ports.authoritative_plan_execution import (
    AuthoritativePlanExecutionLinkRepository,
)
from ..ports.authoritative_plan_revision import (
    AuthoritativePlanRevisionRepository,
)


class AuthoritativeOccurrenceExecutionPlanLinkNotFound(LookupError):
    pass


class AuthoritativeOccurrenceExecutionStateError(ValueError):
    pass


class OccurrenceExecutionCandidateProvider(Protocol):
    async def __call__(
        self,
        *,
        hypothesis_id: str,
        stable_source_occurrence_id: str,
    ) -> OccurrenceExecutionCandidateEvidence:
        ...


async def link_authoritative_occurrence_execution_with_repository(
    *,
    athlete_id: str,
    logical_plan_id: str,
    workout_session_id: str,
    authoritative_occurrence_id: str,
    hypothesis_id: str,
    stable_source_occurrence_id: str,
    acknowledges_candidate_boundaries: bool,
    acknowledges_not_provider_verified: bool,
    execution_link_repository:
        AuthoritativePlanExecutionLinkRepository,
    revision_repository: AuthoritativePlanRevisionRepository,
    occurrence_execution_repository:
        AuthoritativeOccurrenceExecutionLinkRepository,
    candidate_provider: OccurrenceExecutionCandidateProvider,
    session,
    submitted_at: datetime | None = None,
    created_at: datetime | None = None,
    id_factory: Callable[[], object] = uuid4,
) -> AuthoritativeOccurrenceExecutionLink:
    """Persist one explicit occurrence-to-candidate execution binding.

    The client-facing selection identifies only an authoritative occurrence,
    one existing reconciliation hypothesis, and one stable source occurrence.

    Candidate windows, source hashes, captured occurrence provenance, clock
    domain, and verification limitations must come from candidate_provider,
    which is expected to be backed by server-produced reconciliation state.

    This operation does not establish provider phase events, exact execution
    boundaries, clock alignment, historical plan content, or temporal
    proximity.
    """
    try:
        if (
            acknowledges_candidate_boundaries is not True
            or acknowledges_not_provider_verified is not True
        ):
            raise OccurrenceExecutionNotEligible(
                "Explicit candidate-boundary and non-provider-verification "
                "acknowledgements are required."
            )

        plan_execution_link = (
            await execution_link_repository.get_by_session(
                workout_session_id=workout_session_id
            )
        )

        # Deliberately do not disclose cross-athlete execution bindings.
        if (
            plan_execution_link is None
            or plan_execution_link.athlete_id != athlete_id
            or plan_execution_link.logical_plan_id != logical_plan_id
        ):
            raise AuthoritativeOccurrenceExecutionPlanLinkNotFound(
                "Authoritative plan execution link not found."
            )

        if not plan_execution_link.verify_content_hash():
            raise AuthoritativeOccurrenceExecutionStateError(
                "Authoritative plan execution-link hash does not verify."
            )

        existing = (
            await occurrence_execution_repository.get_by_occurrence(
                plan_execution_link_id=plan_execution_link.link_id,
                authoritative_occurrence_id=(
                    authoritative_occurrence_id
                ),
            )
        )

        if existing is not None:
            # Cross-athlete state must remain undisclosed even if storage
            # integrity were compromised.
            if (
                existing.athlete_id != athlete_id
                or existing.workout_session_id
                != workout_session_id
            ):
                raise AuthoritativeOccurrenceExecutionPlanLinkNotFound(
                    "Authoritative occurrence execution link not found."
                )

            # Immutable idempotent retry is allowed only for the exact
            # candidate identity already confirmed. Do not recapture
            # mutable reconciliation state on that path.
            if (
                existing.hypothesis_id != hypothesis_id
                or existing.stable_source_occurrence_id
                != stable_source_occurrence_id
            ):
                raise OccurrenceExecutionConflictError(
                    "Authoritative occurrence is already bound to "
                    "different candidate evidence."
                )

            await session.commit()
            return existing

        observed_revision = await revision_repository.get_revision(
            revision_id=plan_execution_link.observed_revision_id
        )

        if observed_revision is None:
            raise AuthoritativeOccurrenceExecutionStateError(
                "Frozen observed authoritative revision is missing."
            )

        candidate = await candidate_provider(
            hypothesis_id=hypothesis_id,
            stable_source_occurrence_id=(
                stable_source_occurrence_id
            ),
        )

        now = datetime.now(timezone.utc)
        confirmation_time = submitted_at or now
        link_time = created_at or confirmation_time

        confirmation = OccurrenceExecutionConfirmation(
            confirmation_id=(
                "pt-occ-exec-confirmation:"
                f"{id_factory()}"
            ),
            athlete_id=athlete_id,
            workout_session_id=workout_session_id,
            authoritative_occurrence_id=(
                authoritative_occurrence_id
            ),
            phase_reconciliation_artifact_id=(
                candidate.phase_reconciliation_artifact_id
            ),
            hypothesis_id=candidate.hypothesis_id,
            stable_source_occurrence_id=(
                candidate.stable_source_occurrence_id
            ),
            submitted_at=confirmation_time,
            acknowledges_candidate_boundaries=(
                acknowledges_candidate_boundaries
            ),
            acknowledges_not_provider_verified=(
                acknowledges_not_provider_verified
            ),
        )

        link = finalize_authoritative_occurrence_execution_link(
            link_id=f"pt-occ-exec-link:{id_factory()}",
            plan_execution_link=plan_execution_link,
            observed_revision=observed_revision,
            candidate=candidate,
            confirmation=confirmation,
            created_at=link_time,
        )

        saved = await occurrence_execution_repository.save(link)
        await session.commit()
        return saved

    except Exception:
        await session.rollback()
        raise
