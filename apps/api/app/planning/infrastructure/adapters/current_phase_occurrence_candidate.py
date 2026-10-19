from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.models.entities import WorkoutSession
from app.planning.infrastructure.adapters.phase_occurrence_candidate import (
    capture_occurrence_execution_candidate,
)
from app.services.phase_reconciliation_read import (
    read_owned_phase_reconciliation,
)


class CurrentPhaseOccurrenceCandidateNotFound(LookupError):
    pass


def _uuid(value: str, *, field_name: str) -> UUID:
    try:
        return UUID(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{field_name} must be a UUID string."
        ) from exc


class CurrentAppPhaseOccurrenceCandidateProvider:
    """Resolve occurrence candidate evidence only from current server state.

    The request may identify an already exposed reconciliation hypothesis
    and stable source occurrence. Source hashes, candidate windows,
    captured occurrence provenance, clock domain, and verification flags
    are never accepted from the caller.
    """

    def __init__(
        self,
        db,
        *,
        athlete_id: str,
        workout_session_id: str,
    ) -> None:
        self._db = db
        self._athlete_id = _uuid(
            athlete_id,
            field_name="athlete_id",
        )
        self._workout_session_id = _uuid(
            workout_session_id,
            field_name="workout_session_id",
        )

    async def __call__(
        self,
        *,
        hypothesis_id: str,
        stable_source_occurrence_id: str,
    ):
        with self._db.no_autoflush:
            row = await self._db.scalar(
                select(WorkoutSession).where(
                    WorkoutSession.id
                    == self._workout_session_id,
                    WorkoutSession.user_id
                    == self._athlete_id,
                )
            )

        if row is None:
            raise CurrentPhaseOccurrenceCandidateNotFound(
                "Owned workout session not found."
            )

        reconciliation = await read_owned_phase_reconciliation(
            self._db,
            row,
            self._athlete_id,
            include_source=False,
        )

        return capture_occurrence_execution_candidate(
            reconciliation,
            hypothesis_id=hypothesis_id,
            stable_source_occurrence_id=(
                stable_source_occurrence_id
            ),
        )
