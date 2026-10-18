from datetime import datetime, timezone


class TimeValidationError(ValueError):
    pass


def require_aware_datetime(
    value: datetime,
    *,
    field_name: str = "datetime",
) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise TimeValidationError(
            f"{field_name} must be timezone-aware."
        )
    return value


def to_utc(
    value: datetime,
    *,
    field_name: str = "datetime",
) -> datetime:
    require_aware_datetime(value, field_name=field_name)
    return value.astimezone(timezone.utc)
