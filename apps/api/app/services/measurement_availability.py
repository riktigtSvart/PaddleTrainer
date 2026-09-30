from datetime import datetime


AVAILABILITY_SCHEMA_VERSION = 1


def build_availability_metadata(
    *,
    period_start: datetime | None,
    period_end: datetime | None,
    total_observation_count: int | None = None,
    metric_observation_count: int | None = None,
    max_observation_gap_sec: float | None = None,
    max_metric_observation_gap_sec: float | None = None,
) -> dict:
    observation_span_sec = None

    if (
        period_start is not None
        and period_end is not None
        and period_end >= period_start
    ):
        observation_span_sec = (
            period_end - period_start
        ).total_seconds()

    return {
        "schema_version": AVAILABILITY_SCHEMA_VERSION,
        "observation_span_sec": observation_span_sec,
        "total_observation_count": total_observation_count,
        "metric_observation_count": metric_observation_count,
        "max_observation_gap_sec": max_observation_gap_sec,
        "max_metric_observation_gap_sec": (
            max_metric_observation_gap_sec
        ),
    }