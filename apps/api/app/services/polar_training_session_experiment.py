from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any


POLAR_DISCOVERY_MAX_DAYS = 90


def build_discovery_ranges(
    from_date: date,
    to_date: date,
    *,
    maximum_days: int = POLAR_DISCOVERY_MAX_DAYS,
) -> list[tuple[date, date]]:
    """Build non-overlapping [from, to) discovery ranges."""
    if maximum_days < 1:
        raise ValueError(
            "maximum_days must be >= 1"
        )

    if to_date <= from_date:
        raise ValueError(
            "to_date must be after from_date"
        )

    ranges = []
    cursor = from_date

    while cursor < to_date:
        chunk_to = min(
            cursor
            + timedelta(
                days=maximum_days
            ),
            to_date,
        )

        ranges.append(
            (
                cursor,
                chunk_to,
            )
        )

        cursor = chunk_to

    return ranges


def _integer(
    value: Any,
) -> int | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    if (
        isinstance(value, float)
        and math.isfinite(value)
        and value.is_integer()
    ):
        return int(value)

    if isinstance(value, str):
        stripped = value.strip()

        if (
            stripped
            and stripped.lstrip(
                "+-"
            ).isdigit()
        ):
            return int(
                stripped
            )

    return None


def _finite_number(
    value: Any,
) -> float | None:
    if isinstance(value, bool):
        return None

    if not isinstance(
        value,
        (int, float),
    ):
        return None

    result = float(value)

    if not math.isfinite(result):
        return None

    return result


def _sport_id(
    item: dict[str, Any],
) -> int | None:
    sport = item.get(
        "sport"
    )

    direct = _integer(
        sport
    )

    if direct is not None:
        return direct

    if not isinstance(
        sport,
        dict,
    ):
        return None

    identifier = sport.get(
        "id"
    )

    direct_identifier = _integer(
        identifier
    )

    if direct_identifier is not None:
        return direct_identifier

    if isinstance(
        identifier,
        dict,
    ):
        return _integer(
            identifier.get(
                "id"
            )
        )

    return None


def _external_id(
    item: dict[str, Any],
) -> str | None:
    identifier = item.get(
        "identifier"
    )

    if isinstance(
        identifier,
        dict,
    ):
        value = identifier.get(
            "id"
        )
    else:
        value = identifier

    if value is None:
        return None

    return str(
        value
    )


def _start_date(
    item: dict[str, Any],
) -> date | None:
    start_time = item.get(
        "startTime"
    )

    if not isinstance(
        start_time,
        str,
    ):
        return None

    try:
        return datetime.fromisoformat(
            start_time
        ).date()
    except ValueError:
        try:
            return date.fromisoformat(
                start_time[:10]
            )
        except (
            TypeError,
            ValueError,
        ):
            return None


def _compact_session(
    item: dict[str, Any],
) -> dict[str, Any]:
    return {
        "date": _start_date(
            item
        ),
        "external_id": _external_id(
            item
        ),
        "start_time": item.get(
            "startTime"
        ),
        "stop_time": item.get(
            "stopTime"
        ),
        "duration_ms": _integer(
            item.get(
                "durationMillis"
            )
        ),
        "distance_m": _finite_number(
            item.get(
                "distanceMeters"
            )
        ),
        "sport_id": _sport_id(
            item
        ),
        "name": item.get(
            "name"
        ),
    }


def _selection_indices(
    count: int,
) -> list[int]:
    if count <= 0:
        return []

    if count == 1:
        return [0]

    first = (
        math.ceil(
            count / 3
        )
        - 1
    )

    second = (
        math.ceil(
            2 * count / 3
        )
        - 1
    )

    indices = []

    for index in (
        first,
        second,
    ):
        bounded_index = min(
            max(
                index,
                0,
            ),
            count - 1,
        )

        if bounded_index not in indices:
            indices.append(
                bounded_index
            )

    return indices


def build_training_session_experiment_sample(
    catalog_payloads: list[dict[str, Any]],
    *,
    from_date: date,
    to_date: date,
    sport_id: int,
) -> dict[str, Any]:
    """Select deterministic monthly training-session candidates.

    The selection uses only catalog-level session metadata. It does not
    inspect routes, samples, rankings, or evidence values.
    """
    if to_date <= from_date:
        raise ValueError(
            "to_date must be after from_date"
        )

    sessions_by_external_id = {}
    sessions_without_external_id = []

    for payload in catalog_payloads:
        if not isinstance(
            payload,
            dict,
        ):
            continue

        for item in (
            payload.get(
                "trainingSessions"
            )
            or []
        ):
            if not isinstance(
                item,
                dict,
            ):
                continue

            item_date = _start_date(
                item
            )

            if (
                item_date is None
                or item_date < from_date
                or item_date >= to_date
            ):
                continue

            if _sport_id(
                item
            ) != sport_id:
                continue

            external_id = _external_id(
                item
            )

            if external_id is None:
                sessions_without_external_id.append(
                    item
                )
                continue

            sessions_by_external_id[
                external_id
            ] = item

    matching_sessions = (
        list(
            sessions_by_external_id.values()
        )
        + sessions_without_external_id
    )

    matching_sessions.sort(
        key=lambda item: (
            _start_date(
                item
            )
            or date.max,
            str(
                item.get(
                    "startTime"
                )
                or ""
            ),
            _external_id(
                item
            )
            or "",
        )
    )

    sessions_by_month: dict[
        str,
        list[dict[str, Any]],
    ] = {}

    for item in matching_sessions:
        item_date = _start_date(
            item
        )

        if item_date is None:
            continue

        month_key = (
            f"{item_date.year:04d}-"
            f"{item_date.month:02d}"
        )

        sessions_by_month.setdefault(
            month_key,
            [],
        ).append(
            item
        )

    month_results = []
    selected_sessions = []

    cursor = date(
        from_date.year,
        from_date.month,
        1,
    )

    final_month = date(
        (to_date - timedelta(days=1)).year,
        (to_date - timedelta(days=1)).month,
        1,
    )

    while cursor <= final_month:
        month_key = (
            f"{cursor.year:04d}-"
            f"{cursor.month:02d}"
        )

        month_sessions = (
            sessions_by_month.get(
                month_key,
                [],
            )
        )

        selection_indices = (
            _selection_indices(
                len(
                    month_sessions
                )
            )
        )

        selected = [
            _compact_session(
                month_sessions[
                    index
                ]
            )
            for index
            in selection_indices
        ]

        selected_sessions.extend(
            selected
        )

        month_results.append(
            {
                "month": month_key,
                "matching_session_count": (
                    len(
                        month_sessions
                    )
                ),
                "selection_indices_zero_based": (
                    selection_indices
                ),
                "selected_count": (
                    len(
                        selected
                    )
                ),
                "selected": selected,
            }
        )

        if cursor.month == 12:
            cursor = date(
                cursor.year + 1,
                1,
                1,
            )
        else:
            cursor = date(
                cursor.year,
                cursor.month + 1,
                1,
            )

    selected_dates = sorted(
        {
            item["date"]
            for item
            in selected_sessions
            if item.get(
                "date"
            )
            is not None
        }
    )

    return {
        "from": from_date,
        "to": to_date,
        "to_semantics": (
            "EXCLUSIVE"
        ),
        "sport_id": sport_id,
        "selection_method": (
            "SORT_BY_DATE_THEN_SELECT_APPROX_ONE_THIRD_AND_TWO_THIRDS"
        ),
        "matching_session_count": (
            len(
                matching_sessions
            )
        ),
        "selected_session_count": (
            len(
                selected_sessions
            )
        ),
        "selected_unique_date_count": (
            len(
                selected_dates
            )
        ),
        "selected_dates": (
            selected_dates
        ),
        "selected_sessions": (
            selected_sessions
        ),
        "months": month_results,
    }
