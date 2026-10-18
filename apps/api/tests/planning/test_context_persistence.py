from datetime import datetime, timezone

from app.planning.domain.common.enums import DecisionPurpose, PlanningScope
from app.planning.domain.common.refs import SourceSnapshotRef, VersionRef
from app.planning.domain.context.models import create_planning_context
from app.planning.domain.persistence.snapshot_codec import (
    decode_planning_context,
    encode_planning_context,
)


def _dt(hour: int) -> datetime:
    return datetime(2026, 10, 16, hour, tzinfo=timezone.utc)


def test_planning_context_record_round_trip() -> None:
    source = SourceSnapshotRef(
        domain="CURRENT_TRAINING_STATE",
        object_id="cts-1",
        object_version="cts_v0.1",
        as_of=_dt(18),
        information_cutoff_at=_dt(18),
        available_at=_dt(18),
        content_hash="a" * 64,
    )
    original = create_planning_context(
        context_id="apc-1",
        athlete_id="athlete-1",
        schema_version="apc_v0.1",
        as_of=_dt(18),
        information_cutoff_at=_dt(18),
        created_at=_dt(19),
        planning_scope=PlanningScope.MICROCYCLE,
        decision_purpose=DecisionPurpose.CREATE_MICROCYCLE,
        source_snapshot_refs=(source,),
        engine_version=VersionRef("engine", "v0.1"),
        rules_version=VersionRef("rules", "v0.1"),
        evidence_pack_version=VersionRef("evidence", "v0.1"),
    )
    record = encode_planning_context(original)
    restored = decode_planning_context(record)
    assert restored == original
    assert restored.verify_content_hash()
