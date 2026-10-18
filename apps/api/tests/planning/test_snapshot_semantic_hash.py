from datetime import datetime, timezone

import pytest

from app.planning.domain.common.snapshot import create_domain_snapshot
from app.planning.domain.common.refs import SourceSnapshotRef, VersionRef
from app.planning.domain.common.enums import DecisionPurpose, PlanningScope
from app.planning.domain.context.models import create_planning_context


def _dt(hour: int) -> datetime:
    return datetime(2026, 10, 16, hour, tzinfo=timezone.utc)


def test_snapshot_hash_ignores_generated_id_and_created_at() -> None:
    first = create_domain_snapshot(
        snapshot_id="id-a",
        athlete_id="athlete-1",
        domain_type="STATE",
        schema_version="v0.1",
        as_of=_dt(18),
        information_cutoff_at=_dt(18),
        created_at=_dt(19),
        payload={"x": 1},
    )
    second = create_domain_snapshot(
        snapshot_id="id-b",
        athlete_id="athlete-1",
        domain_type="STATE",
        schema_version="v0.1",
        as_of=_dt(18),
        information_cutoff_at=_dt(18),
        created_at=_dt(20),
        payload={"x": 1},
    )
    assert first.content_hash == second.content_hash


def test_snapshot_payload_is_deeply_immutable() -> None:
    snapshot = create_domain_snapshot(
        snapshot_id="id-a",
        athlete_id="athlete-1",
        domain_type="STATE",
        schema_version="v0.1",
        as_of=_dt(18),
        information_cutoff_at=_dt(18),
        created_at=_dt(19),
        payload={"nested": {"values": [1, 2]}},
    )
    with pytest.raises(TypeError):
        snapshot.payload["new"] = 3  # type: ignore[index]
    nested = snapshot.payload["nested"]
    with pytest.raises(TypeError):
        nested["new"] = 3  # type: ignore[index]


def test_context_hash_ignores_context_id_and_created_at() -> None:
    source = SourceSnapshotRef(
        domain="STATE",
        object_id="state-1",
        object_version="v0.1",
        as_of=_dt(18),
        information_cutoff_at=_dt(18),
        available_at=_dt(18),
        content_hash="a" * 64,
    )
    common = dict(
        athlete_id="athlete-1",
        schema_version="apc_v0.1",
        as_of=_dt(18),
        information_cutoff_at=_dt(18),
        planning_scope=PlanningScope.MICROCYCLE,
        decision_purpose=DecisionPurpose.CREATE_MICROCYCLE,
        source_snapshot_refs=(source,),
        engine_version=VersionRef("engine", "v0.1"),
        rules_version=VersionRef("rules", "v0.1"),
        evidence_pack_version=VersionRef("evidence", "v0.1"),
    )
    first = create_planning_context(
        context_id="context-a",
        created_at=_dt(19),
        **common,
    )
    second = create_planning_context(
        context_id="context-b",
        created_at=_dt(20),
        **common,
    )
    assert first.content_hash == second.content_hash
