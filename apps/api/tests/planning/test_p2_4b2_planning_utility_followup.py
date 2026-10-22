"""B2 census/lineage contracts with real audit and revision repositories.

All data is synthetic. Reuse B1's isolated file SQLite and microsecond database
clock fixture. Source artifacts use the real P1.7/P1.8 builders, and revisions
are adopted/appended through the production SQLAlchemy adapter. No mutable
provider source or application database is accessed by the B2 workflow.

Positive selected-family cases supply a controlled receipt at the B1 reader
boundary: the current minimal policy deliberately returns HUMAN_DECISION_REQUIRED
for a family plus defer. Separate cases exercise the real B1 reader with its
actual missing/fallback action. The fixture never alters stored B1 artifacts.
"""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import Column, Table, Uuid, select
from sqlalchemy.orm import Session

import app.planning.application.bind_planning_utility_decision as decision_service
import app.planning.application.bind_planning_utility_followup as followup_service
from app.db.base import Base
from app.planning.application.apply_plan_revision import (
    apply_authoritative_plan_revision,
)
from app.planning.application.ingest_authoritative_executed_training import (
    _audit_record as execution_record,
)
from app.planning.application.ingest_authoritative_executed_training import (
    authoritative_executed_training_artifact_id,
)
from app.planning.application.ingest_authoritative_training_response import (
    _audit_record as response_record,
)
from app.planning.application.plan_mutation import build_plan_mutation_instruction
from app.planning.domain.common.enums import KnowledgeStatus, ProvenanceKind
from app.planning.domain.common.serialization import canonical_json, compute_content_hash
from app.planning.domain.context.models import (
    CONTEXT_HASH_EXCLUDE_FIELDS,
    TrainingSpaceStatus,
    WorkoutFamilySpaceItem,
)
from app.planning.domain.decision.models import (
    PLANNER_DECISION_HASH_EXCLUDE_FIELDS,
    PlannerDecisionStatus,
)
from app.planning.domain.evidence.models import EvidenceQuality
from app.planning.domain.executed_training.models import (
    AUTHORITATIVE_EXECUTED_TRAINING_HASH_EXCLUDE_FIELDS,
    build_authoritative_executed_training_evidence,
)
from app.planning.domain.execution_link.models import (
    ExecutionLinkBasis,
    finalize_authoritative_plan_execution_link,
)
from app.planning.domain.persistence.audit import AuditArtifactKind
from app.planning.domain.plan_revision.models import (
    PlanMutationOperation,
    create_workout_plan_contract_artifact,
)
from app.planning.domain.plan_revision.persistence_contract import (
    finalize_current_state_adoption_binding,
)
from app.planning.domain.planning_utility.decision_binding import (
    DECISION_BINDING_HASH_EXCLUDE_FIELDS,
)
from app.planning.domain.planning_utility.followup import (
    FOLLOWUP_HASH_EXCLUDE_FIELDS,
    PlanningUtilityResponseAvailability,
)
from app.planning.domain.replay.models import RUN_RECORD_HASH_EXCLUDE_FIELDS
from app.planning.domain.response_evidence.models import (
    TRAINING_RESPONSE_EVIDENCE_HASH_EXCLUDE_FIELDS,
    TrainingResponseKind,
    TrainingResponseLinkBasis,
    TrainingResponseMeasurement,
    TrainingResponseTiming,
    build_authoritative_training_response_evidence,
)
from app.planning.domain.workout_family.models import FamilyEntryGateStatus
from app.planning.infrastructure.persistence.sqlalchemy_models import (
    PlanningAuditArtifactRow,
    PlanningLogicalPlanRow,
    PlanningPlanOccurrenceIdentityRow,
    PlanningPlanRevisionOccurrenceRow,
    PlanningPlanRevisionRow,
)
from app.planning.infrastructure.repositories.postgres_authoritative_plan_revision import (
    SqlAlchemyAuthoritativePlanRevisionRepository,
)
from tests.planning.test_p1_2_postgres_authoritative_revision_repository import (
    StaticHashProvider,
    baseline,
)
from tests.planning.test_p2_4a2_planning_utility_storage import (
    ATHLETE,
    AsyncSQLiteBridge,
    _kwargs,
    _rows,
    _seed_evidence,
)
from tests.planning.test_p2_4a2_planning_utility_storage import (
    database as database,  # noqa: PLC0414 -- re-export the existing pytest fixture
)
from tests.planning.test_p2_4b1_planning_utility_decision_binding import (
    precise_database as precise_database,  # noqa: PLC0414 -- re-export the existing pytest fixture
)

SOURCE = "33333333-3333-4333-8333-333333333333"
FOLLOWUP_KIND = AuditArtifactKind.PLANNING_UTILITY_FOLLOWUP


def _rehash(value, excluded):
    return replace(value, content_hash=compute_content_hash(value, exclude_fields=excluded))


@pytest_asyncio.fixture
async def case(precise_database, monkeypatch):
    source = await _seed_evidence(precise_database, monkeypatch)
    metadata = Base.metadata
    if "planned_workouts" not in metadata.tables:
        Table("planned_workouts", metadata, Column("id", Uuid(), primary_key=True))
    tables = [
        metadata.tables["planned_workouts"],
        PlanningLogicalPlanRow.__table__,
        PlanningPlanRevisionRow.__table__,
        PlanningPlanOccurrenceIdentityRow.__table__,
        PlanningPlanRevisionOccurrenceRow.__table__,
    ]
    metadata.create_all(precise_database, tables=tables)
    with precise_database.begin() as connection:
        table = metadata.tables["planned_workouts"]
        values = {"id": UUID(SOURCE)}
        optional = {
            "user_id": UUID(ATHLETE),
            "date": date(2026, 10, 17),
            "sport": "RUNNING",
            "title": "Synthetic B2 plan",
            "status": "PLANNED",
            "source": "TEST",
            "created_at": datetime(2026, 10, 17, tzinfo=UTC),
            "updated_at": datetime(2026, 10, 17, tzinfo=UTC),
        }
        values.update({name: value for name, value in optional.items() if name in table.c})
        connection.execute(table.insert().values(**values))
    with Session(precise_database, expire_on_commit=False) as sync:
        bridge = AsyncSQLiteBridge(sync)
        kwargs = _kwargs(source, bridge)
        original_context = kwargs["context"]
        space = replace(
            original_context.runtime_projection.training_space,
            status=TrainingSpaceStatus.ENTRY_GATE_OPEN,
            families=(
                WorkoutFamilySpaceItem(
                    family_key="RUN_EASY",
                    family_version="v0.1",
                    modality_key="RUNNING",
                    sport_key="RUNNING",
                    entry_gate_status=FamilyEntryGateStatus.ELIGIBLE,
                    build_authorized_by_entry_gate=True,
                    dose_reduction_required=False,
                    reason_codes=("SYNTHETIC_AUTHORIZED_FAMILY",),
                ),
            ),
            unresolved_dimensions=(),
            final_authorization=True,
        )
        context = _rehash(
            replace(
                original_context,
                runtime_projection=replace(
                    original_context.runtime_projection, training_space=space
                ),
            ),
            CONTEXT_HASH_EXCLUDE_FIELDS,
        )
        request = replace(kwargs["request"], context_hash=context.content_hash)
        kwargs.update(context=context, request=request)
        real_decision = await decision_service.make_durable_observed_planner_run(**kwargs)
        assert real_decision.planner_run.decision.selected_action is None
        assert (
            real_decision.planner_run.decision.status
            == PlannerDecisionStatus.HUMAN_DECISION_REQUIRED
        )
        decision = _controlled_selected_receipt(real_decision)

        async def controlled_reader(**arguments):
            assert arguments["context"] == context
            assert arguments["request"] == request
            return decision

        monkeypatch.setattr(followup_service, "load_planning_utility_decision", controlled_reader)
        revisions = SqlAlchemyAuthoritativePlanRevisionRepository(
            bridge, source_hash_provider=StaticHashProvider("c" * 64)
        )
        previous = baseline({"athlete": ATHLETE, "source": SOURCE})
        await revisions.adopt_current_state(
            binding=finalize_current_state_adoption_binding(
                logical_plan_id=previous.logical_plan_id,
                source_workout_id=SOURCE,
                expected_source_content_sha256="c" * 64,
                adopted_revision_id=previous.revision_id,
                authority_established_at=previous.authority_established_at,
            ),
            revision=previous,
        )
        await bridge.commit()
        result = SimpleNamespace(
            engine=precise_database,
            bridge=bridge,
            audit=kwargs["audit_repository"],
            revisions=revisions,
            decision=decision,
            real_decision=real_decision,
            kwargs=kwargs,
            previous=previous,
            original_context=original_context,
            counter=0,
        )
        result.instruction, result.revision = await _append_revision(
            result, previous=previous, number=2
        )
        yield result


def _controlled_selected_receipt(real):
    run = real.planner_run
    chosen = next(item for item in run.candidate_set.candidates if item.plan_mutation_authorized)
    decision = _rehash(
        replace(run.decision, selected_action=chosen, status=PlannerDecisionStatus.DECIDED),
        PLANNER_DECISION_HASH_EXCLUDE_FIELDS,
    )
    rationale = decision_service.planner.build_decision_rationale(
        rationale_id=run.rationale.rationale_id,
        decision=decision,
        envelope=run.envelope,
        candidate_set=run.candidate_set,
        policy_set=run.policy_set,
        created_at=run.rationale.created_at,
    )
    record = _rehash(
        replace(
            run.run_record,
            decision_hash=decision.content_hash,
            rationale_hash=rationale.content_hash,
        ),
        RUN_RECORD_HASH_EXCLUDE_FIELDS,
    )
    hashes = {
        AuditArtifactKind.PLANNER_DECISION: decision.content_hash,
        AuditArtifactKind.DECISION_RATIONALE: rationale.content_hash,
        AuditArtifactKind.PLANNER_RUN_RECORD: record.content_hash,
    }
    binding = _rehash(
        replace(
            real.binding,
            decision_status=decision.status,
            selected_action=chosen,
            artifact_refs=tuple(
                replace(ref, content_hash=hashes.get(ref.artifact_kind, ref.content_hash))
                for ref in real.binding.artifact_refs
            ),
        ),
        DECISION_BINDING_HASH_EXCLUDE_FIELDS,
    )
    return replace(
        real,
        binding=binding,
        planner_run=replace(run, decision=decision, rationale=rationale, run_record=record),
    )


async def _append_revision(case, *, previous, number, wrong_action=False):
    instant = case.decision.binding.decision_time + timedelta(microseconds=number)
    artifact = create_workout_plan_contract_artifact(
        plan_id=previous.logical_plan_id,
        revision_id=f"artifact-r{number}",
        contract_schema_version="0.1",
        contract_json=canonical_json({"blocks": [], "revision": number}),
        stable_occurrence_ids=(previous.occurrences[0].occurrence_id,),
    )
    instruction = build_plan_mutation_instruction(
        instruction_id=f"b2-instruction-{number}",
        decision=case.decision.planner_run.decision,
        rationale=case.decision.planner_run.rationale,
        operation=PlanMutationOperation.MODIFY,
        plan_id=previous.logical_plan_id,
        expected_current_revision_id=previous.revision_id,
        new_plan_artifact=artifact,
        effective_from=instant,
        created_at=instant,
    )
    if wrong_action:
        from app.planning.domain.plan_revision.models import PLAN_MUTATION_HASH_EXCLUDE_FIELDS

        instruction = _rehash(
            replace(instruction, selected_action_id="unrelated-action"),
            PLAN_MUTATION_HASH_EXCLUDE_FIELDS,
        )
    await case.audit.save(
        decision_service._record(
            artifact_kind=AuditArtifactKind.PLAN_MUTATION_INSTRUCTION,
            artifact_id=instruction.instruction_id,
            athlete_id=ATHLETE,
            schema_version="plan_mutation_instruction_v0.1",
            created_at=instruction.created_at,
            artifact=instruction,
        )
    )
    applied = await apply_authoritative_plan_revision(
        current_revision=previous,
        instruction=instruction,
        revision_id=f"pt-plan-rev:b2-r{number}",
        repository=case.revisions,
    )
    await case.bridge.commit()
    return instruction, applied.revision


async def _add_execution(case, *, revision=None, duration=None, observed_at=None):
    case.counter += 1
    session_id = str(UUID(int=case.counter + 100))
    chosen = case.revision if revision is None else revision
    instant = case.decision.binding.decision_time + timedelta(microseconds=100 + case.counter)
    link = finalize_authoritative_plan_execution_link(
        link_id=f"pt-exec-link:b2-{case.counter}",
        athlete_id=ATHLETE,
        logical_plan_id=chosen.logical_plan_id,
        observed_revision_id=chosen.revision_id,
        workout_session_id=session_id,
        source_workout_id=SOURCE,
        link_basis=ExecutionLinkBasis.MANUAL_CONFIRMED,
        provider_target_id=None,
        source_workout_content_hash="a" * 64,
        session_source_content_hash="b" * 64,
        observed_revision_content_hash=chosen.content_hash,
        created_at=instant,
    )
    executed = build_authoritative_executed_training_evidence(
        artifact_id=authoritative_executed_training_artifact_id(session_id),
        plan_execution_link=link,
        observed_at=observed_at or instant,
        modality_key="RUNNING",
        duration_status=(KnowledgeStatus.UNKNOWN if duration is None else KnowledgeStatus.KNOWN),
        duration_s=duration,
        created_at=instant + timedelta(microseconds=1),
    )
    await case.audit.save(execution_record(executed))
    await case.bridge.commit()
    return executed


async def _add_response(case, executed, *, timing=TrainingResponseTiming.SAME_DAY):
    case.counter += 1
    source_id = str(UUID(int=case.counter + 1000))
    instant = max(executed.created_at, executed.observed_at) + timedelta(
        microseconds=10 + case.counter
    )
    response = build_authoritative_training_response_evidence(
        artifact_id="pt-training-response-evidence:athlete-response:" + source_id,
        athlete_id=ATHLETE,
        workout_session_id=executed.workout_session_id,
        executed_training_evidence_id=executed.artifact_id,
        executed_training_evidence_hash=executed.content_hash,
        response_kind=TrainingResponseKind.SESSION_FEEDBACK,
        response_timing=timing,
        session_link_basis=TrainingResponseLinkBasis.SOURCE_EXPLICIT_SESSION_ID,
        observed_at=instant,
        available_at=instant,
        source_system="SYNTHETIC",
        source_record_id=source_id,
        source_record_version=None,
        source_content_hash="e" * 64,
        provenance=ProvenanceKind.SOURCE,
        quality=EvidenceQuality.MODERATE,
        measurements=(
            TrainingResponseMeasurement("fatigue", KnowledgeStatus.UNKNOWN, None, "score_0_10"),
            TrainingResponseMeasurement("pain", KnowledgeStatus.KNOWN, 0, "score_0_10"),
        ),
        created_at=instant,
    )
    await case.audit.save(response_record(response))
    await case.bridge.commit()
    return response


def _kwargs_followup(case, *, as_of=None):
    return {
        "context": case.kwargs["context"],
        "request": case.kwargs["request"],
        "as_of": datetime.now(UTC) if as_of is None else as_of,
        "audit_repository": case.audit,
        "revision_repository": case.revisions,
        "session": case.bridge,
    }


async def _source_row(case, kind, identity):
    record = await case.audit.get(artifact_kind=kind, artifact_id=identity)
    await case.bridge.rollback()
    return record


@pytest.mark.asyncio
async def test_complete_census_binds_all_related_executions_and_all_response_timings(case):
    first = await _add_execution(case)
    second = await _add_execution(case, duration=0)
    response1 = await _add_response(case, first)
    response2 = await _add_response(case, first, timing=TrainingResponseTiming.FOLLOW_UP)
    result = await followup_service.bind_planning_utility_followup(**_kwargs_followup(case))
    snapshot = result.followup
    assert snapshot.source_census_complete is True
    assert snapshot.matched_execution_source_count == 2
    assert snapshot.established_execution_lineage_count == 2
    assert snapshot.response_source_count == 2
    assert len(snapshot.census_sources) == 5  # two executions, two responses, one instruction
    assert snapshot.executions[0].workout_session_id == first.workout_session_id
    assert snapshot.executions[0].duration_status == KnowledgeStatus.UNKNOWN
    assert snapshot.executions[0].duration_s is None
    assert snapshot.executions[1].workout_session_id == second.workout_session_id
    assert snapshot.executions[1].duration_status == KnowledgeStatus.KNOWN
    assert snapshot.executions[1].duration_s == 0
    assert {item.source.artifact_id for item in snapshot.executions[0].responses} == {
        response1.artifact_id,
        response2.artifact_id,
    }
    for response in snapshot.executions[0].responses:
        assert response.known_measurement_count == response.non_known_measurement_count == 1
    assert snapshot.executions[1].responses == ()
    assert (
        snapshot.executions[1].response_availability
        == PlanningUtilityResponseAvailability.NO_SOURCE_AVAILABLE_AS_OF
    )
    assert all(row.plan_content_at_execution_status == "unverified" for row in snapshot.executions)
    assert result.followup_committed is True
    assert result.reused_durable_followup is False
    assert result.durable_available_at >= snapshot.created_at >= snapshot.as_of
    for name in (
        "selected_action_execution_verified",
        "plan_content_at_execution_verified",
        "utility_endpoint_preregistered",
        "utility_assessment_established",
        "planning_utility_supported",
        "causal_attribution_established",
        "readiness_inference_authorized",
        "fatigue_diagnosis_authorized",
        "performance_prediction_authorized",
        "prescription_change_authorized",
        "planning_authorized",
        "planner_runtime_modified",
        "candidate_authority_modified",
    ):
        assert getattr(snapshot, name) is False
    assert len(_rows(case.engine, FOLLOWUP_KIND)) == 1
    assert case.bridge.in_transaction() is False


@pytest.mark.asyncio
async def test_same_athlete_and_time_do_not_replace_exact_decision_revision_lineage(case):
    related = await _add_execution(case)
    unrelated = await _add_execution(case, revision=case.previous)
    response = await _add_response(case, unrelated)
    result = await followup_service.bind_planning_utility_followup(**_kwargs_followup(case))
    assert result.followup.matched_execution_source_count == 1
    assert result.followup.executions[0].source.artifact_id == related.artifact_id
    assert result.followup.unrelated_execution_source_ids == (unrelated.artifact_id,)
    assert result.followup.unrelated_response_source_ids == (response.artifact_id,)
    assert result.followup.response_source_count == 0
    assert len(result.followup.census_sources) == 4


@pytest.mark.asyncio
async def test_no_source_is_an_empty_census_without_zero_exposure_or_utility_claim(case):
    result = await followup_service.bind_planning_utility_followup(**_kwargs_followup(case))
    assert result.followup.executions == ()
    assert result.followup.matched_execution_source_count == 0
    assert result.followup.response_source_count == 0
    assert result.followup.planning_utility_supported is False


@pytest.mark.asyncio
async def test_same_cutoff_retry_and_load_do_not_rescan_or_issue_a_decision(case, monkeypatch):
    await _add_execution(case)
    kwargs = _kwargs_followup(case)
    first = await followup_service.bind_planning_utility_followup(**kwargs)

    async def no_scan(*args, **kwargs):
        pytest.fail("Existing follow-up must restore its original exact census.")

    def no_decision(*args, **kwargs):
        pytest.fail("Follow-up must not issue a planner decision.")

    monkeypatch.setattr(case.audit, "list_for_athlete", no_scan)
    monkeypatch.setattr(decision_service, "make_observed_planner_run", no_decision)
    second = await followup_service.bind_planning_utility_followup(**kwargs)
    assert second.reused_durable_followup is True
    assert second.followup == first.followup
    assert second.durable_available_at == first.durable_available_at
    commits = case.bridge.commit_count
    monkeypatch.setattr(case.audit, "save", no_scan)
    loaded = await followup_service.load_planning_utility_followup(**kwargs)
    assert loaded.followup == first.followup
    assert loaded.durable_available_at == first.durable_available_at
    assert case.bridge.commit_count == commits
    assert case.bridge.in_transaction() is False


@pytest.mark.asyncio
async def test_late_response_preserves_old_absence_and_appears_in_new_cutoff_snapshot(case):
    executed = await _add_execution(case)
    kwargs = _kwargs_followup(case)
    first = await followup_service.bind_planning_utility_followup(**kwargs)
    response = await _add_response(case, executed)
    assert response.created_at < kwargs["as_of"]  # backdated materialization is insufficient
    old = await followup_service.load_planning_utility_followup(**kwargs)
    assert old.followup == first.followup
    assert old.followup.response_source_count == 0
    latest = await followup_service.bind_planning_utility_followup(**_kwargs_followup(case))
    assert latest.followup.response_source_count == 1
    assert latest.followup.decision_binding_id == old.followup.decision_binding_id
    assert latest.followup.followup_id != old.followup.followup_id


@pytest.mark.asyncio
async def test_missing_audited_instruction_remains_an_unknown_row(case, monkeypatch):
    await _add_execution(case)
    original = case.audit.list_for_athlete

    async def without_instruction(**kwargs):
        return (
            ()
            if kwargs["artifact_kind"] == AuditArtifactKind.PLAN_MUTATION_INSTRUCTION
            else await original(**kwargs)
        )

    monkeypatch.setattr(case.audit, "list_for_athlete", without_instruction)
    result = await followup_service.bind_planning_utility_followup(**_kwargs_followup(case))
    assert result.followup.matched_execution_source_count == 1
    assert result.followup.established_execution_lineage_count == 0
    assert result.followup.executions[0].lineage_blockers == ("AUDITED_INSTRUCTION_MISSING",)
    assert result.followup.executions[0].instruction_source is None


@pytest.mark.asyncio
async def test_missing_parent_absence_is_frozen_and_later_snapshot_can_resolve_it(
    case, monkeypatch
):
    await _add_execution(case)
    original = case.revisions.get_revision

    async def without_parent(**kwargs):
        return (
            None if kwargs["revision_id"] == case.previous.revision_id else await original(**kwargs)
        )

    kwargs = _kwargs_followup(case)
    monkeypatch.setattr(case.revisions, "get_revision", without_parent)
    first = await followup_service.bind_planning_utility_followup(**kwargs)
    assert first.followup.unavailable_revision_ids == (case.previous.revision_id,)
    assert first.followup.executions[0].lineage_blockers == ("PREVIOUS_REVISION_UNAVAILABLE",)
    monkeypatch.setattr(case.revisions, "get_revision", original)
    loaded = await followup_service.load_planning_utility_followup(**kwargs)
    assert loaded.followup == first.followup
    later = await followup_service.bind_planning_utility_followup(**_kwargs_followup(case))
    assert later.followup.established_execution_lineage_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", tuple(followup_service.FOLLOWUP_SOURCE_KINDS))
async def test_repository_cap_makes_completeness_unknown_without_saving_partial_snapshot(
    case, monkeypatch, kind
):
    await _add_execution(case)
    original = case.audit.list_for_athlete

    async def capped(**kwargs):
        rows = await original(**kwargs)
        return (SimpleNamespace(),) * 500 if kwargs["artifact_kind"] == kind else rows

    monkeypatch.setattr(case.audit, "list_for_athlete", capped)
    with pytest.raises(followup_service.PlanningUtilityFollowupCompletenessUnknown, match="limit"):
        await followup_service.bind_planning_utility_followup(**_kwargs_followup(case))
    assert _rows(case.engine, FOLLOWUP_KIND) == ()
    assert case.bridge.in_transaction() is False


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ("raise", "no_commit"))
async def test_commit_failure_rolls_back_only_followup_and_retains_all_source_artifacts(
    case, failure
):
    await _add_execution(case)
    kwargs = _kwargs_followup(case)
    source_before = {
        kind: _rows(case.engine, kind) for kind in followup_service.FOLLOWUP_SOURCE_KINDS
    }
    case.bridge.fail_commit = failure == "raise"
    case.bridge.skip_commit = failure == "no_commit"
    with pytest.raises(RuntimeError):
        await followup_service.bind_planning_utility_followup(**kwargs)
    assert _rows(case.engine, FOLLOWUP_KIND) == ()
    assert {kind: _rows(case.engine, kind) for kind in source_before} == source_before
    assert case.bridge.in_transaction() is False
    case.bridge.fail_commit = case.bridge.skip_commit = False
    result = await followup_service.bind_planning_utility_followup(**kwargs)
    assert result.followup_committed is True


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ("bind", "load"))
@pytest.mark.parametrize("problem", ("audit_session", "revision_session", "existing_transaction"))
async def test_session_guard_preserves_unrelated_callers_transaction(case, operation, problem):
    kwargs = _kwargs_followup(case)
    if problem == "audit_session":
        kwargs["session"] = SimpleNamespace(in_transaction=lambda: False)
    elif problem == "revision_session":
        kwargs["revision_repository"] = SimpleNamespace(session=SimpleNamespace())
    else:
        await case.bridge.execute(select(PlanningAuditArtifactRow))
    calls, commits, rollbacks = (
        case.bridge.execute_count,
        case.bridge.commit_count,
        case.bridge.rollback_count,
    )
    function = (
        followup_service.bind_planning_utility_followup
        if operation == "bind"
        else followup_service.load_planning_utility_followup
    )
    with pytest.raises(RuntimeError, match="session"):
        await function(**kwargs)
    assert (case.bridge.execute_count, case.bridge.commit_count, case.bridge.rollback_count) == (
        calls,
        commits,
        rollbacks,
    )
    assert case.bridge.in_transaction() is (problem == "existing_transaction")
    if case.bridge.in_transaction():
        await case.bridge.rollback()


@pytest.mark.asyncio
async def test_wrong_selected_action_in_an_otherwise_consistent_revision_chain_is_rejected(case):
    _, bad_revision = await _append_revision(
        case, previous=case.revision, number=3, wrong_action=True
    )
    await _add_execution(case, revision=bad_revision)
    with pytest.raises(followup_service.PlanningUtilityFollowupError, match="replay"):
        await followup_service.bind_planning_utility_followup(**_kwargs_followup(case))
    assert _rows(case.engine, FOLLOWUP_KIND) == ()


@pytest.mark.asyncio
async def test_historical_session_linked_after_decision_remains_unknown(case):
    await _add_execution(
        case, observed_at=case.decision.binding.decision_time - timedelta(seconds=1)
    )
    result = await followup_service.bind_planning_utility_followup(**_kwargs_followup(case))
    row = result.followup.executions[0]
    assert row.decision_execution_lineage_established is False
    assert "EXECUTION_NOT_AFTER_DECISION" in row.lineage_blockers
    assert result.followup.selected_action_execution_verified is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    (
        ("planning_authorized", True),
        ("utility_endpoint_preregistered", True),
        ("selected_action_execution_verified", True),
        ("plan_content_at_execution_verified", True),
        ("source_census_complete", False),
    ),
)
async def test_rehashed_snapshot_cannot_add_stronger_authority_or_change_completeness(
    case, field, value
):
    await _add_execution(case)
    kwargs = _kwargs_followup(case)
    result = await followup_service.bind_planning_utility_followup(**kwargs)
    changed = _rehash(replace(result.followup, **{field: value}), FOLLOWUP_HASH_EXCLUDE_FIELDS)
    with Session(case.engine) as editor:
        row = editor.execute(
            select(PlanningAuditArtifactRow).where(
                PlanningAuditArtifactRow.artifact_kind == FOLLOWUP_KIND.value
            )
        ).scalar_one()
        row.content_hash = changed.content_hash
        row.contract_json = canonical_json(changed)
        editor.commit()
    with pytest.raises(RuntimeError, match="differs"):
        await followup_service.load_planning_utility_followup(**kwargs)
    assert case.bridge.in_transaction() is False


@pytest.mark.asyncio
async def test_real_b1_human_decision_does_not_acquire_the_controlled_selected_family_lineage(
    case, monkeypatch
):
    executed = await _add_execution(case)
    monkeypatch.setattr(
        followup_service,
        "load_planning_utility_decision",
        decision_service.load_planning_utility_decision,
    )
    assert case.real_decision.planner_run.decision.selected_action is None
    result = await followup_service.bind_planning_utility_followup(**_kwargs_followup(case))
    assert result.followup.decision_binding_content_hash == case.real_decision.binding.content_hash
    assert result.followup.matched_execution_source_count == 0
    assert result.followup.unrelated_execution_source_ids == (executed.artifact_id,)
    assert result.followup.selected_action_execution_verified is False


@pytest.mark.asyncio
async def test_real_b1_defer_does_not_turn_later_athlete_training_into_its_outcome(
    case, monkeypatch
):
    executed = await _add_execution(case)
    kwargs = dict(case.kwargs)
    context = case.original_context
    request = replace(
        kwargs["request"], request_id="fallback-request", context_hash=context.content_hash
    )
    kwargs.update(
        context=context,
        request=request,
        run_id="fallback-run",
        decision_id="fallback-decision",
        rationale_id="fallback-rationale",
    )
    real = await decision_service.make_durable_observed_planner_run(**kwargs)
    assert real.planner_run.decision.status == PlannerDecisionStatus.DEFERRED_PENDING_CONTEXT
    monkeypatch.setattr(
        followup_service,
        "load_planning_utility_decision",
        decision_service.load_planning_utility_decision,
    )
    followup_kwargs = _kwargs_followup(case)
    followup_kwargs.update(context=context, request=request)
    result = await followup_service.bind_planning_utility_followup(**followup_kwargs)
    assert result.followup.executions == ()
    assert result.followup.unrelated_execution_source_ids == (executed.artifact_id,)
    assert result.followup.planning_utility_supported is False


@pytest.mark.asyncio
async def test_ambiguous_hash_identical_instruction_ids_do_not_select_a_favorable_alias(case):
    await _add_execution(case)
    alias = replace(case.instruction, instruction_id="another-instruction-identity")
    assert alias.verify_content_hash()
    await case.audit.save(
        decision_service._record(
            artifact_kind=AuditArtifactKind.PLAN_MUTATION_INSTRUCTION,
            artifact_id=alias.instruction_id,
            athlete_id=ATHLETE,
            schema_version="plan_mutation_instruction_v0.1",
            created_at=alias.created_at,
            artifact=alias,
        )
    )
    await case.bridge.commit()
    result = await followup_service.bind_planning_utility_followup(**_kwargs_followup(case))
    assert result.followup.executions[0].lineage_blockers == (
        "AUDITED_INSTRUCTION_IDENTITY_AMBIGUOUS",
    )
    assert result.followup.executions[0].instruction_source is None
    assert result.followup.established_execution_lineage_count == 0
    assert (
        len(
            [
                ref
                for ref in result.followup.census_sources
                if ref.artifact_kind == AuditArtifactKind.PLAN_MUTATION_INSTRUCTION
            ]
        )
        == 2
    )


@pytest.mark.asyncio
async def test_missing_observed_revision_is_unknown_membership_and_not_an_empty_census(
    case, monkeypatch
):
    await _add_execution(case)
    original = case.revisions.get_revision

    async def missing(**kwargs):
        return (
            None if kwargs["revision_id"] == case.revision.revision_id else await original(**kwargs)
        )

    monkeypatch.setattr(case.revisions, "get_revision", missing)
    with pytest.raises(
        followup_service.PlanningUtilityFollowupCompletenessUnknown, match="membership"
    ):
        await followup_service.bind_planning_utility_followup(**_kwargs_followup(case))
    assert _rows(case.engine, FOLLOWUP_KIND) == ()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", tuple(followup_service.FOLLOWUP_SOURCE_KINDS))
async def test_missing_database_source_time_makes_census_completeness_unknown(
    case, monkeypatch, kind
):
    executed = await _add_execution(case)
    await _add_response(case, executed)
    original = case.audit.list_for_athlete

    async def missing_time(**kwargs):
        records = await original(**kwargs)
        return (
            tuple(replace(record, persisted_at=None) for record in records)
            if kwargs["artifact_kind"] == kind
            else records
        )

    monkeypatch.setattr(case.audit, "list_for_athlete", missing_time)
    with pytest.raises(
        followup_service.PlanningUtilityFollowupCompletenessUnknown, match="timestamp"
    ):
        await followup_service.bind_planning_utility_followup(**_kwargs_followup(case))
    assert _rows(case.engine, FOLLOWUP_KIND) == ()


@pytest.mark.asyncio
async def test_frozen_full_contract_hash_protects_metadata_excluded_from_semantic_hash(case):
    executed = await _add_execution(case)
    kwargs = _kwargs_followup(case)
    await followup_service.bind_planning_utility_followup(**kwargs)
    changed = replace(executed, created_at=executed.created_at + timedelta(microseconds=1))
    assert changed.verify_content_hash() and changed.content_hash == executed.content_hash
    with Session(case.engine) as editor:
        row = editor.execute(
            select(PlanningAuditArtifactRow).where(
                PlanningAuditArtifactRow.artifact_kind
                == AuditArtifactKind.AUTHORITATIVE_EXECUTED_TRAINING.value,
                PlanningAuditArtifactRow.artifact_id == executed.artifact_id,
            )
        ).scalar_one()
        row.contract_json = canonical_json(changed)
        row.created_at = changed.created_at
        editor.commit()
    with pytest.raises(followup_service.PlanningUtilityFollowupError, match="changed"):
        await followup_service.load_planning_utility_followup(**kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ("execution", "response"))
async def test_rehashed_source_with_mismatched_revision_or_execution_hash_is_rejected(case, source):
    executed = await _add_execution(case)
    if source == "execution":
        changed = _rehash(
            replace(executed, observed_revision_content_hash="f" * 64),
            AUTHORITATIVE_EXECUTED_TRAINING_HASH_EXCLUDE_FIELDS,
        )
        kind, identity = AuditArtifactKind.AUTHORITATIVE_EXECUTED_TRAINING, executed.artifact_id
    else:
        response = await _add_response(case, executed)
        changed = _rehash(
            replace(response, executed_training_evidence_hash="f" * 64),
            TRAINING_RESPONSE_EVIDENCE_HASH_EXCLUDE_FIELDS,
        )
        kind, identity = AuditArtifactKind.AUTHORITATIVE_TRAINING_RESPONSE, response.artifact_id
    with Session(case.engine) as editor:
        row = editor.execute(
            select(PlanningAuditArtifactRow).where(
                PlanningAuditArtifactRow.artifact_kind == kind.value,
                PlanningAuditArtifactRow.artifact_id == identity,
            )
        ).scalar_one()
        row.contract_json, row.content_hash = canonical_json(changed), changed.content_hash
        editor.commit()
    with pytest.raises(followup_service.PlanningUtilityFollowupError, match="bind"):
        await followup_service.bind_planning_utility_followup(**_kwargs_followup(case))
    assert _rows(case.engine, FOLLOWUP_KIND) == ()


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ("execution", "response"))
async def test_duplicate_execution_session_or_response_source_aliases_are_rejected(case, source):
    executed = await _add_execution(case)
    if source == "execution":
        alias = replace(executed, artifact_id="pt-executed-training-evidence:duplicate-alias")
        record = execution_record(alias)
    else:
        response = await _add_response(case, executed)
        alias = replace(response, artifact_id="pt-training-response-evidence:duplicate-alias")
        record = response_record(alias)
    assert alias.verify_content_hash()
    await case.audit.save(record)
    await case.bridge.commit()
    with pytest.raises(
        followup_service.PlanningUtilityFollowupError, match="same session|duplicated"
    ):
        await followup_service.bind_planning_utility_followup(**_kwargs_followup(case))
    assert _rows(case.engine, FOLLOWUP_KIND) == ()


@pytest.mark.asyncio
async def test_future_cutoff_is_rejected_before_any_owned_source_read(case):
    calls = case.bridge.execute_count
    with pytest.raises(ValueError, match="future"):
        await followup_service.bind_planning_utility_followup(
            **_kwargs_followup(case, as_of=datetime.now(UTC) + timedelta(days=1))
        )
    assert case.bridge.execute_count == calls
    assert case.bridge.in_transaction() is False


@pytest.mark.asyncio
async def test_cutoff_preceding_committed_decision_binding_is_rejected(case):
    with pytest.raises(ValueError, match="chronology"):
        await followup_service.bind_planning_utility_followup(
            **_kwargs_followup(
                case, as_of=case.decision.durable_bound_at - timedelta(microseconds=1)
            )
        )
    assert _rows(case.engine, FOLLOWUP_KIND) == ()


@pytest.mark.asyncio
async def test_load_missing_snapshot_is_read_only_and_does_not_materialize_it(case):
    commits = case.bridge.commit_count
    with pytest.raises(followup_service.PlanningUtilityFollowupNotFound):
        await followup_service.load_planning_utility_followup(**_kwargs_followup(case))
    assert case.bridge.commit_count == commits
    assert case.bridge.in_transaction() is False
    assert _rows(case.engine, FOLLOWUP_KIND) == ()
