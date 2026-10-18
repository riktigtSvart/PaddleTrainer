from datetime import datetime, timezone

import pytest

from app.planning.domain.common.snapshot import create_domain_snapshot


def _dt(hour: int) -> datetime:
    return datetime(
        2026, 10, 16, hour, tzinfo=timezone.utc
    )


def _snapshot(**overrides):
    values = dict(
        snapshot_id="cts-1",
        athlete_id="athlete-1",
        domain_type="CURRENT_TRAINING_STATE",
        schema_version="cts_v0.1",
        as_of=_dt(18),
        information_cutoff_at=_dt(18),
        created_at=_dt(19),
        payload={
            "status": "open_with_constraints",
            "capability": "unknown",
        },
    )
    values.update(overrides)
    return create_domain_snapshot(**values)


def test_hash_verifies() -> None:
    snapshot = _snapshot()
    assert snapshot.verify_content_hash()
    assert len(snapshot.content_hash) == 64


def test_same_payload_different_mapping_order_same_hash() -> None:
    first = _snapshot(payload={"b": 2, "a": 1})
    second = _snapshot(payload={"a": 1, "b": 2})
    assert first.content_hash == second.content_hash


def test_changed_cutoff_changes_hash() -> None:
    first = _snapshot(information_cutoff_at=_dt(17))
    second = _snapshot(information_cutoff_at=_dt(18))
    assert first.content_hash != second.content_hash


def test_cutoff_after_as_of_rejected() -> None:
    with pytest.raises(ValueError):
        _snapshot(information_cutoff_at=_dt(19))


def test_payload_is_effectively_immutable() -> None:
    snapshot = _snapshot()
    with pytest.raises(TypeError):
        snapshot.payload["new"] = "x"
