from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..common.time import to_utc
from .models import (
    TrainingResponseKind,
    TrainingResponseMeasurement,
    TrainingResponseTiming,
    _require_canonical_uuid,
    _require_non_empty,
    _require_sha256,
)


@dataclass(frozen=True)
class TrainingResponseSourceCapture:
    """Hash-bound source observation explicitly linked to one session.

    This capture proves only what source row was read and which explicit
    WorkoutSession identity that row carries. It does not establish causal
    attribution, readiness, fatigue diagnosis, performance prediction, or
    prescription authority.
    """

    athlete_id: str
    workout_session_id: str
    response_source_id: str

    response_kind: TrainingResponseKind
    response_timing: TrainingResponseTiming

    observed_at: datetime
    available_at: datetime

    source_system: str
    source_record_id: str
    source_record_version: str | None
    source_content_hash: str

    measurements: tuple[
        TrainingResponseMeasurement,
        ...,
    ]


def build_training_response_source_capture(
    *,
    athlete_id: str,
    workout_session_id: str,
    response_source_id: str,
    response_kind: TrainingResponseKind,
    response_timing: TrainingResponseTiming,
    observed_at: datetime,
    available_at: datetime,
    source_system: str,
    source_record_id: str,
    source_record_version: str | None,
    source_content_hash: str,
    measurements: tuple[
        TrainingResponseMeasurement,
        ...,
    ],
) -> TrainingResponseSourceCapture:
    canonical_athlete_id = _require_canonical_uuid(
        athlete_id,
        field_name="athlete_id",
    )

    canonical_session_id = _require_canonical_uuid(
        workout_session_id,
        field_name="workout_session_id",
    )

    canonical_response_source_id = _require_canonical_uuid(
        response_source_id,
        field_name="response_source_id",
    )

    kind = TrainingResponseKind(
        response_kind
    )

    timing = TrainingResponseTiming(
        response_timing
    )

    observed = to_utc(
        observed_at,
        field_name="observed_at",
    )

    available = to_utc(
        available_at,
        field_name="available_at",
    )

    if available < observed:
        raise ValueError(
            "available_at must not be before observed_at."
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

    source_hash = _require_sha256(
        source_content_hash,
        field_name="source_content_hash",
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
            "Training response source capture requires "
            "at least one promotable measurement."
        )

    metric_keys = tuple(
        measurement.metric_key
        for measurement in ordered_measurements
    )

    if len(set(metric_keys)) != len(metric_keys):
        raise ValueError(
            "Training response source measurement keys "
            "must be unique."
        )

    return TrainingResponseSourceCapture(
        athlete_id=canonical_athlete_id,
        workout_session_id=canonical_session_id,
        response_source_id=canonical_response_source_id,
        response_kind=kind,
        response_timing=timing,
        observed_at=observed,
        available_at=available,
        source_system=source_system_value,
        source_record_id=source_record_id_value,
        source_record_version=source_record_version,
        source_content_hash=source_hash,
        measurements=ordered_measurements,
    )
