from datetime import datetime, timezone

from app.api.routes.planning_adoption import _revision_payload
from app.planning.domain.plan_revision.persistence_contract import (
    OccurrenceLineageKind,
    PlanHistoryClaim,
    PlanRevisionOrigin,
    RevisionDecisionLineage,
    RevisionOccurrence,
    finalize_authoritative_plan_revision,
)


UTC = timezone.utc


def dt(hour: int) -> datetime:
    return datetime(2026, 10, 19, hour, tzinfo=UTC)


def test_revision_payload_exposes_planner_decision_lineage():
    revision = finalize_authoritative_plan_revision(
        revision_id="pt-plan-rev:p1-5-api",
        logical_plan_id="planned-workout:w1",
        athlete_id="athlete-1",
        revision_number=2,
        previous_revision_id="pt-plan-rev:baseline",
        origin=PlanRevisionOrigin.PLANNER_CREATED,
        history_claim=PlanHistoryClaim.VERIFIED_FROM_AUTHORITY_START,
        authority_established_at=dt(8),
        effective_from=dt(10),
        created_at=dt(9),
        contract_schema_version="0.1",
        contract_json='{"blocks":[],"plan":"updated"}',
        occurrences=(
            RevisionOccurrence(
                occurrence_id="pt-occ:o1",
                ordinal=0,
                lineage_kind=OccurrenceLineageKind.PRESERVED,
            ),
        ),
        adoption_source=None,
        decision_lineage=RevisionDecisionLineage(
            context_hash="a" * 64,
            decision_hash="b" * 64,
            rationale_hash="c" * 64,
            instruction_hash="d" * 64,
        ),
    )

    payload = _revision_payload(revision)

    assert payload["decision_lineage"] == {
        "context_hash": "a" * 64,
        "decision_hash": "b" * 64,
        "rationale_hash": "c" * 64,
        "instruction_hash": "d" * 64,
    }


def test_revision_payload_keeps_adoption_revision_lineage_null():
    revision = finalize_authoritative_plan_revision(
        revision_id="pt-plan-rev:baseline",
        logical_plan_id="planned-workout:w1",
        athlete_id="athlete-1",
        revision_number=1,
        previous_revision_id=None,
        origin=PlanRevisionOrigin.ADOPTED_CURRENT_STATE,
        history_claim=PlanHistoryClaim.CURRENT_STATE_BASELINE_ONLY,
        authority_established_at=dt(8),
        effective_from=dt(8),
        created_at=dt(8),
        contract_schema_version="0.1",
        contract_json='{"blocks":[],"plan":"baseline"}',
        occurrences=(
            RevisionOccurrence(
                occurrence_id="pt-occ:o1",
                ordinal=0,
                lineage_kind=OccurrenceLineageKind.NEW,
                source_capture_occurrence_id="capture-o1",
            ),
        ),
        adoption_source=__import__(
            "app.planning.domain.plan_revision.persistence_contract",
            fromlist=["AdoptionSourceRef"],
        ).AdoptionSourceRef(
            capture_id="capture-1",
            capture_content_hash="a" * 64,
            source_read_content_hash="b" * 64,
            source_content_sha256="c" * 64,
            external_contract_plan_id="external-plan",
            external_contract_plan_revision=1,
        ),
        decision_lineage=None,
    )

    payload = _revision_payload(revision)

    assert payload["decision_lineage"] is None
