from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from ..domain.common.enums import KnowledgeStatus
from ..domain.executed_training import (
    AuthoritativeExecutedTrainingEvidence,
    build_authoritative_executed_training_evidence,
)
from ..ports.authoritative_occurrence_execution import (
    AuthoritativeOccurrenceExecutionLinkRepository,
)
from ..ports.authoritative_plan_execution import (
    AuthoritativePlanExecutionLinkRepository,
)
from ..ports.execution_source import (
    LockedExecutionSourceProvider,
)


class AuthoritativeExecutedTrainingNotFound(LookupError):
    pass


class AuthoritativeExecutedTrainingSourceDrift(ValueError):
    pass


class AuthoritativeExecutedTrainingSourceInvalid(ValueError):
    pass


def _snapshot_datetime(
    value,
    *,
    field_name: str,
) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise AuthoritativeExecutedTrainingSourceInvalid(
            f"{field_name} must be an ISO datetime string."
        )

    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise AuthoritativeExecutedTrainingSourceInvalid(
            f"{field_name} is not a valid ISO datetime."
        ) from exc

    if (
        parsed.tzinfo is None
        or parsed.utcoffset() is None
    ):
        raise AuthoritativeExecutedTrainingSourceInvalid(
            f"{field_name} must be offset-aware."
        )

    return parsed.astimezone(timezone.utc)


def _snapshot_duration(
    value,
) -> tuple[KnowledgeStatus, int | None]:
    if value is None:
        return KnowledgeStatus.UNKNOWN, None

    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
    ):
        raise AuthoritativeExecutedTrainingSourceInvalid(
            "duration_sec must be a non-negative integer or null."
        )

    return KnowledgeStatus.KNOWN, value


async def build_authoritative_executed_training_with_repository(
    *,
    athlete_id: str,
    workout_session_id: str,
    execution_link_repository:
        AuthoritativePlanExecutionLinkRepository,
    occurrence_execution_repository:
        AuthoritativeOccurrenceExecutionLinkRepository,
    execution_source: LockedExecutionSourceProvider,
    session,
    created_at: datetime | None = None,
    id_factory: Callable[[], object] = uuid4,
) -> AuthoritativeExecutedTrainingEvidence:
    """Assemble one authoritative executed-training evidence artifact.

    Current mutable source rows are locked and must still hash exactly
    to the source state frozen by P1.6B before any current session field
    is promoted into P1.7 evidence.

    P1.6C occurrence links are immutable optional associations. Their
    absence does not negate the session-level execution evidence.
    """
    try:
        plan_execution_link = (
            await execution_link_repository.get_by_session(
                workout_session_id=workout_session_id
            )
        )

        # Cross-athlete bindings are deliberately undisclosed.
        if (
            plan_execution_link is None
            or plan_execution_link.athlete_id
            != athlete_id
        ):
            raise AuthoritativeExecutedTrainingNotFound(
                "Authoritative execution evidence not found."
            )

        if not plan_execution_link.verify_content_hash():
            raise AuthoritativeExecutedTrainingSourceInvalid(
                "Authoritative plan execution-link hash "
                "does not verify."
            )

        locked = await execution_source.lock_and_capture(
            session,
            athlete_id=athlete_id,
            source_workout_id=(
                plan_execution_link.source_workout_id
            ),
            workout_session_id=workout_session_id,
        )

        if (
            locked.source_workout_content_hash
            != plan_execution_link.source_workout_content_hash
        ):
            raise AuthoritativeExecutedTrainingSourceDrift(
                "Plan source changed after the authoritative "
                "execution link was established."
            )

        if (
            locked.session_source_content_hash
            != plan_execution_link.session_source_content_hash
        ):
            raise AuthoritativeExecutedTrainingSourceDrift(
                "Workout session source changed after the "
                "authoritative execution link was established."
            )

        snapshot = locked.session_snapshot
        if not isinstance(snapshot, dict):
            raise AuthoritativeExecutedTrainingSourceInvalid(
                "Locked session snapshot must be a dictionary."
            )

        if (
            snapshot.get("id") != workout_session_id
            or snapshot.get("user_id") != athlete_id
        ):
            raise AuthoritativeExecutedTrainingSourceInvalid(
                "Locked session snapshot identity differs."
            )

        modality_key = snapshot.get("sport")
        if (
            not isinstance(modality_key, str)
            or not modality_key.strip()
        ):
            raise AuthoritativeExecutedTrainingSourceInvalid(
                "Locked session sport is unavailable."
            )

        observed_at = _snapshot_datetime(
            snapshot.get("started_at"),
            field_name="started_at",
        )

        duration_status, duration_s = _snapshot_duration(
            snapshot.get("duration_sec")
        )

        occurrence_links = (
            await occurrence_execution_repository
            .list_by_plan_execution_link(
                plan_execution_link_id=(
                    plan_execution_link.link_id
                )
            )
        )

        artifact = (
            build_authoritative_executed_training_evidence(
                artifact_id=(
                    "pt-executed-training-evidence:"
                    f"{id_factory()}"
                ),
                plan_execution_link=plan_execution_link,
                occurrence_execution_links=(
                    tuple(occurrence_links)
                ),
                observed_at=observed_at,
                modality_key=modality_key,
                duration_status=duration_status,
                duration_s=duration_s,
                created_at=(
                    created_at
                    or datetime.now(timezone.utc)
                ),
            )
        )

        # Read-only transaction boundary. This releases the row locks
        # acquired by LockedExecutionSourceProvider without mutating
        # source, plan, revision, or evidence history.
        await session.commit()
        return artifact

    except Exception:
        await session.rollback()
        raise
