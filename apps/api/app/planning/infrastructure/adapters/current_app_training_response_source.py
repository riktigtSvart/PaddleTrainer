from __future__ import annotations

import copy
from collections.abc import Mapping
from datetime import datetime
from enum import Enum
from math import isfinite
from uuid import UUID

from sqlalchemy import select

from app.models.entities import (
    AthleteResponse,
    WorkoutSession,
)

from ...domain.common.enums import KnowledgeStatus
from ...domain.common.serialization import compute_content_hash
from ...domain.common.time import to_utc
from ...domain.response_evidence import (
    TrainingResponseKind,
    TrainingResponseMeasurement,
    TrainingResponseTiming,
)
from ...domain.response_evidence.source_capture import (
    TrainingResponseSourceCapture,
    build_training_response_source_capture,
)


ATHLETE_RESPONSE_SOURCE_SCHEMA_V01 = (
    "current-app-athlete-response-source-v0.1"
)

ATHLETE_RESPONSE_SOURCE_SYSTEM = (
    "current_app_athlete_response"
)


class TrainingResponseSourceNotFound(LookupError):
    """Owned response source or its owned session was not found."""


class TrainingResponseSourceUnlinked(ValueError):
    """Response source has no explicit WorkoutSession identity."""


class TrainingResponseSourceInvalid(ValueError):
    """Response source cannot be safely promoted into planning evidence."""


_SOURCE_TIMING_MAP = {
    "IMMEDIATE": TrainingResponseTiming.IMMEDIATE,
    "SAME_DAY": TrainingResponseTiming.SAME_DAY,
    "NEXT_MORNING": TrainingResponseTiming.NEXT_MORNING,
    "FOLLOW_UP": TrainingResponseTiming.FOLLOW_UP,
}

_PROMOTABLE_SCORE_FIELDS = (
    (
        "fatigue_score",
        "self_reported_fatigue_score",
    ),
    (
        "soreness_score",
        "self_reported_soreness_score",
    ),
    (
        "recovery_score",
        "self_reported_recovery_score",
    ),
    (
        "energy_score",
        "self_reported_energy_score",
    ),
)


def _uuid(
    value: str,
    *,
    field_name: str,
) -> UUID:
    try:
        parsed = UUID(value)
    except (TypeError, ValueError, AttributeError):
        raise ValueError(
            f"{field_name} must be a canonical UUID string."
        ) from None

    if str(parsed) != value:
        raise ValueError(
            f"{field_name} must be a canonical UUID string."
        )

    return parsed


def _enum_value(value: object) -> str:
    if isinstance(value, Enum):
        raw = value.value
    else:
        raw = value

    if not isinstance(raw, str) or not raw.strip():
        raise TrainingResponseSourceInvalid(
            "response_timing must be a non-empty enum/string value."
        )

    return raw


def _response_timing(
    value: object,
) -> TrainingResponseTiming:
    raw = _enum_value(value)

    try:
        return _SOURCE_TIMING_MAP[raw]
    except KeyError:
        raise TrainingResponseSourceInvalid(
            "Unsupported AthleteResponse response_timing."
        ) from None


def _numeric_score(
    value: object,
    *,
    field_name: str,
) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
    ):
        raise TrainingResponseSourceInvalid(
            f"{field_name} must be numeric or null."
        )

    normalized = float(value)

    if not isfinite(normalized):
        raise TrainingResponseSourceInvalid(
            f"{field_name} must be finite."
        )

    return normalized


def _measurements(
    response: AthleteResponse,
) -> tuple[TrainingResponseMeasurement, ...]:
    values: list[TrainingResponseMeasurement] = []

    for source_field, metric_key in _PROMOTABLE_SCORE_FIELDS:
        raw = getattr(
            response,
            source_field,
        )

        if raw is None:
            # The current AthleteResponse table has no answer-status field.
            # Null therefore cannot safely distinguish UNKNOWN, NOT_ASKED,
            # or NOT_MEASURED and is deliberately omitted.
            continue

        values.append(
            TrainingResponseMeasurement(
                metric_key=metric_key,
                knowledge_status=KnowledgeStatus.KNOWN,
                value=_numeric_score(
                    raw,
                    field_name=source_field,
                ),
                unit=None,
            )
        )

    if not values:
        raise TrainingResponseSourceInvalid(
            "AthleteResponse has no promotable "
            "self-reported response measurements."
        )

    return tuple(values)


def _source_snapshot(
    response: AthleteResponse,
    *,
    observed_at: datetime,
    created_at: datetime,
) -> dict[str, object]:
    extra_data = response.extra_data

    if not isinstance(extra_data, Mapping):
        raise TrainingResponseSourceInvalid(
            "AthleteResponse.extra_data must be an object."
        )

    # Performance fields and extra_data are intentionally hash-bound even
    # though P1.8B2 does not promote them into response measurements. This
    # preserves the identity of the complete source row that was inspected.
    return {
        "schema_version":
            ATHLETE_RESPONSE_SOURCE_SCHEMA_V01,
        "id": str(response.id),
        "user_id": str(response.user_id),
        "workout_session_id": (
            str(response.workout_session_id)
            if response.workout_session_id is not None
            else None
        ),
        "response_timing":
            _enum_value(response.response_timing),
        "recorded_at": observed_at,
        "fatigue_score": response.fatigue_score,
        "soreness_score": response.soreness_score,
        "recovery_score": response.recovery_score,
        "energy_score": response.energy_score,
        "performance_metric": response.performance_metric,
        "performance_delta_percent":
            response.performance_delta_percent,
        "extra_data": copy.deepcopy(
            dict(extra_data)
        ),
        "created_at": created_at,
    }


class CurrentAppLockedAthleteResponseSource:
    """Capture an owned AthleteResponse under source/session row locks.

    The AthleteResponse.workout_session_id foreign key is the only automatic
    session-link basis accepted here. No temporal matching or nearest-session
    search is performed.

    This adapter exposes self-reported response observations only. Performance
    fields remain source-hash provenance and are not promoted into P1.8
    response measurements.
    """

    async def lock_and_capture(
        self,
        session,
        *,
        athlete_id: str,
        response_source_id: str,
    ) -> TrainingResponseSourceCapture:
        athlete_uuid = _uuid(
            athlete_id,
            field_name="athlete_id",
        )

        response_uuid = _uuid(
            response_source_id,
            field_name="response_source_id",
        )

        response_result = await session.execute(
            select(AthleteResponse)
            .where(
                AthleteResponse.id == response_uuid,
                AthleteResponse.user_id == athlete_uuid,
            )
            .with_for_update()
        )

        response = response_result.scalar_one_or_none()

        # Cross-athlete rows are deliberately undisclosed.
        if response is None:
            raise TrainingResponseSourceNotFound(
                "Owned AthleteResponse not found."
            )

        if (
            str(response.id) != response_source_id
            or str(response.user_id) != athlete_id
        ):
            raise TrainingResponseSourceInvalid(
                "Locked AthleteResponse identity mismatch."
            )

        if response.workout_session_id is None:
            raise TrainingResponseSourceUnlinked(
                "AthleteResponse has no explicit workout_session_id."
            )

        workout_session_id = str(
            response.workout_session_id
        )

        session_uuid = _uuid(
            workout_session_id,
            field_name="workout_session_id",
        )

        workout_result = await session.execute(
            select(WorkoutSession)
            .where(
                WorkoutSession.id == session_uuid,
                WorkoutSession.user_id == athlete_uuid,
            )
            .with_for_update()
        )

        workout = workout_result.scalar_one_or_none()

        if workout is None:
            raise TrainingResponseSourceNotFound(
                "Owned WorkoutSession for AthleteResponse not found."
            )

        if (
            str(workout.id) != workout_session_id
            or str(workout.user_id) != athlete_id
        ):
            raise TrainingResponseSourceInvalid(
                "Locked WorkoutSession identity mismatch."
            )

        observed_at = to_utc(
            response.recorded_at,
            field_name="AthleteResponse.recorded_at",
        )

        created_at = to_utc(
            response.created_at,
            field_name="AthleteResponse.created_at",
        )

        available_at = max(
            observed_at,
            created_at,
        )

        timing = _response_timing(
            response.response_timing
        )

        measurements = _measurements(
            response
        )

        source_snapshot = _source_snapshot(
            response,
            observed_at=observed_at,
            created_at=created_at,
        )

        source_content_hash = compute_content_hash(
            source_snapshot
        )

        return build_training_response_source_capture(
            athlete_id=athlete_id,
            workout_session_id=workout_session_id,
            response_source_id=response_source_id,
            response_kind=(
                TrainingResponseKind.SESSION_FEEDBACK
            ),
            response_timing=timing,
            observed_at=observed_at,
            available_at=available_at,
            source_system=ATHLETE_RESPONSE_SOURCE_SYSTEM,
            source_record_id=response_source_id,
            source_record_version=(
                ATHLETE_RESPONSE_SOURCE_SCHEMA_V01
            ),
            source_content_hash=source_content_hash,
            measurements=measurements,
        )
