from datetime import datetime, timezone

import pytest

from app.planning.domain.common.enums import (
    ConfidenceLevel,
    DecisionPurpose,
    DecisionRelevance,
    Freshness,
    PlanningScope,
)
from app.planning.domain.common.refs import (
    SourceSnapshotRef,
    VersionRef,
)
from app.planning.domain.context.models import (
    CriticalUnknown,
    DomainFreshness,
    create_planning_context,
)


def _dt(hour: int) -> datetime:
    return datetime(
        2026, 10, 16, hour, tzinfo=timezone.utc
    )


def _source(
    *,
    available: datetime | None = None,
    cutoff: datetime | None = None,
    as_of: datetime | None = None,
) -> SourceSnapshotRef:
    return SourceSnapshotRef(
        domain="CURRENT_TRAINING_STATE",
        object_id="cts-1",
        object_version="cts_v0.1",
        as_of=as_of or _dt(18),
        information_cutoff_at=cutoff or _dt(18),
        available_at=available or _dt(18),
        content_hash="a" * 64,
    )


def _context(**overrides):
    values = dict(
        context_id="apc-1",
        athlete_id="athlete-1",
        schema_version="apc_v0.1",
        as_of=_dt(18),
        information_cutoff_at=_dt(18),
        created_at=_dt(19),
        planning_scope=PlanningScope.MICROCYCLE,
        decision_purpose=DecisionPurpose.CREATE_MICROCYCLE,
        source_snapshot_refs=(_source(),),
        engine_version=VersionRef(
            "planner_engine", "planner_engine_v0.1"
        ),
        rules_version=VersionRef(
            "planning_rules", "planning_rules_v0.1"
        ),
        evidence_pack_version=VersionRef(
            "evidence_pack",
            "training_planning_evidence_v0.1",
        ),
        critical_unknowns=(
            CriticalUnknown(
                domain="MAX_STRENGTH",
                question="Reference strength unknown.",
                decision_relevance=DecisionRelevance.MODERATE,
                fallback_policy="reference_building_session",
            ),
        ),
        domain_freshness=(
            DomainFreshness(
                domain="GOALS",
                freshness=Freshness.CURRENT,
                confidence=ConfidenceLevel.HIGH,
            ),
        ),
    )
    values.update(overrides)
    return create_planning_context(**values)


def test_context_hash_verifies_and_frozen() -> None:
    context = _context()
    assert context.verify_content_hash()
    assert context.status.value == "frozen"


def test_context_deterministic() -> None:
    assert _context().content_hash == _context().content_hash


def test_not_yet_available_source_rejected() -> None:
    with pytest.raises(ValueError, match="not available"):
        _context(
            source_snapshot_refs=(
                _source(available=_dt(19)),
            )
        )


def test_future_source_information_rejected() -> None:
    future = _source(
        available=_dt(18),
        cutoff=_dt(19),
        as_of=_dt(19),
    )
    with pytest.raises(ValueError, match="after"):
        _context(source_snapshot_refs=(future,))


def test_context_cutoff_changes_hash() -> None:
    earlier_source = _source(
        available=_dt(17),
        cutoff=_dt(17),
        as_of=_dt(17),
    )
    earlier = _context(
        information_cutoff_at=_dt(17),
        source_snapshot_refs=(earlier_source,),
    )
    current = _context()
    assert earlier.content_hash != current.content_hash
