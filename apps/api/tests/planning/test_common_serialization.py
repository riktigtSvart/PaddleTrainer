from dataclasses import dataclass
from datetime import datetime, timezone
from math import nan

import pytest

from app.planning.domain.common.enums import KnowledgeStatus
from app.planning.domain.common.serialization import (
    CanonicalSerializationError,
    canonical_json,
    compute_content_hash,
)


@dataclass(frozen=True)
class Example:
    status: KnowledgeStatus
    value: float | None


def test_mapping_order_is_canonical() -> None:
    assert canonical_json({"b": 2, "a": 1}) == canonical_json(
        {"a": 1, "b": 2}
    )
    assert compute_content_hash(
        {"b": 2, "a": 1}
    ) == compute_content_hash({"a": 1, "b": 2})


def test_unknown_differs_from_not_applicable() -> None:
    unknown = Example(KnowledgeStatus.UNKNOWN, None)
    not_applicable = Example(
        KnowledgeStatus.NOT_APPLICABLE,
        None,
    )
    assert canonical_json(unknown) != canonical_json(not_applicable)
    assert compute_content_hash(unknown) != compute_content_hash(
        not_applicable
    )


def test_equivalent_timezones_are_identical() -> None:
    utc_value = datetime(
        2026, 10, 16, 20, 0, tzinfo=timezone.utc
    )
    plus_two = datetime.fromisoformat(
        "2026-10-16T22:00:00+02:00"
    )
    assert canonical_json(utc_value) == canonical_json(plus_two)


def test_naive_datetime_rejected() -> None:
    with pytest.raises(CanonicalSerializationError):
        canonical_json(datetime(2026, 10, 16, 20, 0))


def test_nan_rejected() -> None:
    with pytest.raises(CanonicalSerializationError):
        canonical_json({"value": nan})
