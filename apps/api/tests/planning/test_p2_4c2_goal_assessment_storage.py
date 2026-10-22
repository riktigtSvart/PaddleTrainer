"""Real measurement/audit adapters on isolated SQLite with a synthetic clock."""

import json
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import delete, event, select, update
from sqlalchemy.orm import Session

import app.planning.application.assess_mesocycle_goals as service
import app.planning.infrastructure.adapters.current_goal_measurements as source_adapter
from app.db.base import Base
from app.models.entities import Assessment, AssessmentType, Measurement, PhysiologicalMeasurement
from app.planning.domain.common.serialization import canonical_json, compute_content_hash
from app.planning.domain.goals.assessment import (
    GoalCriterionStatus,
    GoalMeasurementSourceKind,
)
from app.planning.domain.goals.protocol import GOAL_HASH_EXCLUDE, GoalVersionReference
from app.planning.domain.persistence.audit import AuditArtifactKind
from app.planning.infrastructure.adapters.current_goal_measurements import (
    SqlAlchemyGoalMeasurementSource,
)
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from tests.planning.test_p2_4a2_planning_utility_storage import (
    database as database,  # noqa: PLC0414 -- shared isolated fixture
)
from tests.planning.test_p2_4b1_planning_utility_decision_binding import (
    precise_database as precise_database,  # noqa: PLC0414 -- C1 database-time fixture
)
from tests.planning.test_p2_4c1_goal_protocol_storage import (
    goal_database as goal_database,  # noqa: PLC0414 -- actual cycle tables and hierarchy
)
from tests.planning.test_p2_4c1_goal_protocol_storage import (
    register_macro,
    register_meso,
    repositories,
)
from tests.planning.test_p2_4c2_goal_assessment import (
    ATHLETE,
    CAPTURE,
    CUTOFF,
    measurement_source,
)

KIND = AuditArtifactKind.MESOCYCLE_GOAL_ASSESSMENT


class SyntheticClock:
    def __init__(self):
        self.current = CAPTURE

    def tick(self):
        self.current += timedelta(microseconds=1)
        return self.current

    def sql_time(self):
        return self.tick().strftime("%Y-%m-%d %H:%M:%S.%f")


def measurement_row(engine, source, *, physiological=False):
    packet = json.loads(source.source_json)
    from datetime import datetime

    with Session(engine) as sync:
        values = {
            "id": UUID(packet["source_id"]),
            "metric_key": packet["metric_key"],
            "value_float": float(packet["value_float_text"])
            if packet["value_float_text"] is not None
            else None,
            "value_text": packet["value_text"],
            "unit": packet["unit"],
            "extra_data": packet["extra_data"],
            "created_at": datetime.fromisoformat(packet["created_at"]),
        }
        if physiological:
            row = PhysiologicalMeasurement(
                **values,
                user_id=UUID(packet["athlete_id"]),
                provider="SYNTHETIC",
                measured_at=datetime.fromisoformat(packet["measured_at"]),
                period_start=datetime.fromisoformat(
                    packet["extra_data"]["goal_measurement_execution"]["started_at"]
                ),
                period_end=datetime.fromisoformat(
                    packet["extra_data"]["goal_measurement_execution"]["ended_at"]
                ),
                device_id="synthetic-device",
                device_model="synthetic-model",
                quality="declared",
                source_record_id="synthetic:" + packet["source_id"],
            )
        else:
            parent = Assessment(
                id=UUID(packet["parent_id"]),
                user_id=UUID(packet["athlete_id"]),
                assessment_type=AssessmentType.OTHER,
                title="Synthetic completed assessment",
                performed_at=datetime.fromisoformat(packet["measured_at"]),
                source="SYNTHETIC",
                extra_data={"retained_parent_context": "synthetic"},
                created_at=datetime.fromisoformat(packet["parent_created_at"]),
            )
            sync.add(parent)
            sync.flush()
            row = Measurement(**values, assessment_id=parent.id)
        sync.add(row)
        sync.commit()


@pytest_asyncio.fixture
async def prepared(goal_database, monkeypatch):
    Base.metadata.create_all(
        goal_database,
        tables=[
            Assessment.__table__,
            Measurement.__table__,
            PhysiologicalMeasurement.__table__,
        ],
    )
    with Session(goal_database, expire_on_commit=False) as sync:
        repo = repositories(sync)
        macro = await register_macro(repo)
        from tests.planning.test_p2_4c1_goal_protocol import meso_proposal

        proposal = meso_proposal(macro.artifact)
        proposal = replace(
            proposal,
            endpoints=tuple(
                replace(
                    e,
                    change_requirement=replace(
                        e.change_requirement,
                        measurement_error_estimate="0",
                        measurement_error_source="synthetic:zero-error-assumption",
                    ),
                )
                for e in proposal.endpoints
            ),
        )
        protocol = await register_meso(repo, macro, proposal)
    for index, endpoint in enumerate(protocol.artifact.proposal.endpoints):
        base, end = ("5", "5") if endpoint.metric_key == "TECHNICAL_ERROR_COUNT" else ("50", "55")
        for followup, value in ((False, base), (True, end)):
            source = measurement_source(
                endpoint, value, followup=followup, identity=101 + 2 * index + int(followup)
            )
            measurement_row(goal_database, source, physiological=(index == 0 and followup))
    clock = SyntheticClock()

    def install_clock(connection, _record):
        connection.create_function("current_timestamp", 0, clock.sql_time)

    event.listen(goal_database, "connect", install_clock)
    with goal_database.connect() as connection:
        install_clock(connection.connection.driver_connection, None)
    monkeypatch.setattr(service, "_utc_now", clock.tick)
    yield SimpleNamespace(engine=goal_database, protocol=protocol.artifact, clock=clock)
    event.remove(goal_database, "connect", install_clock)


def repo_for(sync):
    repo = repositories(sync)
    repo.source = SqlAlchemyGoalMeasurementSource(repo.session)
    return repo


async def run_assessment(repo, prepared, *, reference=None, cutoff=CUTOFF):
    return await service.assess_mesocycle_goal_protocol(
        athlete_id=ATHLETE,
        protocol_reference=reference
        or GoalVersionReference(prepared.protocol.artifact_id, prepared.protocol.content_hash),
        activity_cutoff_at=cutoff,
        source_repository=repo.source,
        audit_repository=repo.audit,
        session=repo.session,
    )


async def load_assessment(repo, prepared, result, *, athlete_id=ATHLETE, available_by=None):
    return await service.load_mesocycle_goal_assessment(
        athlete_id=athlete_id,
        artifact_id=result.artifact.artifact_id,
        available_by=available_by or prepared.clock.tick(),
        audit_repository=repo.audit,
        session=repo.session,
    )


def assessment_rows(engine):
    with Session(engine) as sync:
        return list(
            sync.scalars(
                select(PlanningAuditArtifactRow).where(
                    PlanningAuditArtifactRow.artifact_kind == KIND.value
                )
            )
        )


@pytest.mark.asyncio
async def test_real_adapter_captures_both_families_in_one_statement(prepared):
    with Session(prepared.engine) as sync:
        repo = repo_for(sync)
        endpoints = prepared.protocol.proposal.endpoints
        sources = await repo.source.capture(
            athlete_id=ATHLETE,
            starts_at=endpoints[0].baseline_window.starts_at,
            ends_at=endpoints[0].followup_window.ends_at,
            recorded_before=prepared.clock.tick(),
        )
        assert repo.session.execute_count == 1
        assert len(sources) == 8
        assert {s.source_kind for s in sources} == set(GoalMeasurementSourceKind)
        physiological = next(
            s
            for s in sources
            if s.source_kind == GoalMeasurementSourceKind.PHYSIOLOGICAL_MEASUREMENT
        )
        assert json.loads(physiological.source_json)["device_model"] == "synthetic-model"
        assert json.loads(physiological.source_json)["period_end"].endswith("Z")
        await repo.session.rollback()


@pytest.mark.asyncio
async def test_commit_and_independent_reload_use_real_c1_and_measurement_adapters(prepared):
    with Session(prepared.engine, expire_on_commit=False) as sync:
        repo = repo_for(sync)
        result = await run_assessment(repo, prepared)
        assert result.assessment_committed and result.measurement_schedule_preregistered
        assert result.reused_assessment is False
        assert (
            result.artifact.all_primary_criteria_status
            == GoalCriterionStatus.MET_UNDER_DECLARED_ERROR
        )
        assert len(result.artifact.census.sources) == 8
        assert repo.session.commit_count == 1 and repo.session.in_transaction() is False
        assert result.physiological_adaptation_established is False
        assert result.planning_utility_supported is False
        assert result.planning_authorized is False
    with Session(prepared.engine, expire_on_commit=False) as sync:
        repo = repo_for(sync)
        restored = await load_assessment(repo, prepared, result)
        assert restored.artifact == result.artifact
        assert restored.durable_available_at == result.durable_available_at
        assert repo.session.commit_count == 0 and repo.session.in_transaction() is False
    assert len(assessment_rows(prepared.engine)) == 1


@pytest.mark.asyncio
async def test_retry_and_history_freeze_values_and_missing_results(prepared, monkeypatch):
    with Session(prepared.engine) as writer:
        writer.execute(delete(PhysiologicalMeasurement))
        writer.commit()
    with Session(prepared.engine) as sync:
        repo = repo_for(sync)
        first = await run_assessment(repo, prepared)
        assert first.artifact.endpoint_assessments[0].followup_value is None
        endpoint = prepared.protocol.proposal.endpoints[0]
        measurement_row(
            prepared.engine, measurement_source(endpoint, "55", followup=True, identity=900)
        )
        with Session(prepared.engine) as writer:
            writer.execute(
                update(Measurement).where(Measurement.id == UUID(int=101)).values(value_float=1)
            )
            writer.commit()

        async def forbidden(**_kwargs):
            raise AssertionError("Retry/history must not recapture mutable source rows.")

        monkeypatch.setattr(repo.source, "capture", forbidden)
        retry = await run_assessment(repo, prepared)
        history = await load_assessment(repo, prepared, first)
        assert retry.reused_assessment and retry.artifact == first.artifact == history.artifact
        assert retry.artifact.endpoint_assessments[0].baseline_value == "50"
        assert len(assessment_rows(prepared.engine)) == 1
    with Session(prepared.engine) as sync:
        later = await run_assessment(repo_for(sync), prepared, cutoff=CUTOFF + timedelta(seconds=1))
        assert later.artifact.endpoint_assessments[0].baseline_value == "1"
        assert later.artifact.endpoint_assessments[0].followup_value == "55"
        assert later.artifact.source_availability_at_activity_cutoff_verified is False
        assert later.artifact.artifact_id != first.artifact.artifact_id


@pytest.mark.asyncio
async def test_capture_reads_fresh_columns_despite_retained_orm_identity_map(prepared):
    with Session(prepared.engine, expire_on_commit=False) as sync:
        stale = sync.get(Measurement, UUID(int=101))
        sync.commit()
        with Session(prepared.engine) as writer:
            writer.execute(
                update(Measurement).where(Measurement.id == stale.id).values(value_float=44)
            )
            writer.commit()
        assert stale.value_float == 50
        result = await run_assessment(repo_for(sync), prepared)
        assert result.artifact.endpoint_assessments[0].baseline_value == "44"


@pytest.mark.asyncio
async def test_complete_census_retains_ordinary_and_ambiguous_results(prepared):
    endpoint = prepared.protocol.proposal.endpoints[0]
    measurement_row(prepared.engine, measurement_source(endpoint, "51", identity=901))
    measurement_row(
        prepared.engine,
        measurement_source(
            endpoint,
            "123",
            identity=902,
            metric_key="ordinary_unknown_metric",
            extra_data={"preserved": "routine observation"},
        ),
    )
    with Session(prepared.engine) as sync:
        result = await run_assessment(repo_for(sync), prepared)
        assert len(result.artifact.census.sources) == 10
        endpoint_result = result.artifact.endpoint_assessments[0]
        assert "BASELINE_RESULT_AMBIGUOUS" in endpoint_result.reason_codes
        assert len(endpoint_result.candidates) == 10
        assert any("routine observation" in s.source_json for s in result.artifact.census.sources)


@pytest.mark.asyncio
async def test_source_scope_filters_other_athletes_activity_and_recording_times(prepared):
    endpoint = prepared.protocol.proposal.endpoints[0]
    measurement_row(
        prepared.engine,
        measurement_source(endpoint, "900", identity=901, athlete_id=str(UUID(int=999))),
    )
    measurement_row(
        prepared.engine,
        measurement_source(
            endpoint,
            "900",
            identity=902,
            measured_at=endpoint.baseline_window.starts_at - timedelta(days=1),
        ),
    )
    measurement_row(
        prepared.engine,
        measurement_source(endpoint, "900", identity=903, created_at=CAPTURE + timedelta(days=1)),
    )
    with Session(prepared.engine) as sync:
        result = await run_assessment(repo_for(sync), prepared)
        assert len(result.artifact.census.sources) == 8


@pytest.mark.asyncio
async def test_source_limit_blocks_partial_assessment(prepared, monkeypatch):
    monkeypatch.setattr(source_adapter, "GOAL_MEASUREMENT_CENSUS_LIMIT", 4)
    with Session(prepared.engine) as sync:
        repo = repo_for(sync)
        with pytest.raises(ValueError, match="partial assessment"):
            await run_assessment(repo, prepared)
        assert repo.session.in_transaction() is False
    assert assessment_rows(prepared.engine) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ("fail_commit", "skip_commit"))
async def test_failed_or_skipped_commit_never_returns_a_receipt(prepared, mode):
    with Session(prepared.engine) as sync:
        repo = repo_for(sync)
        setattr(repo.session, mode, True)
        with pytest.raises(RuntimeError):
            await run_assessment(repo, prepared)
        assert repo.session.in_transaction() is False
        assert repo.session.rollback_count == 1
    assert assessment_rows(prepared.engine) == []


@pytest.mark.asyncio
async def test_uncertain_commit_recovers_exact_assessment_without_recapture(prepared, monkeypatch):
    with Session(prepared.engine) as sync:
        repo = repo_for(sync)
        commit = repo.session.commit

        async def commit_then_raise():
            await commit()
            raise RuntimeError("synthetic disconnect after commit")

        monkeypatch.setattr(repo.session, "commit", commit_then_raise)
        with pytest.raises(RuntimeError, match="disconnect"):
            await run_assessment(repo, prepared)
        assert len(assessment_rows(prepared.engine)) == 1

        async def forbidden(**_kwargs):
            raise AssertionError("Committed uncertain result must be recovered unchanged.")

        monkeypatch.setattr(repo.source, "capture", forbidden)
        result = await run_assessment(repo, prepared)
        assert result.assessment_committed and result.reused_assessment
        assert len(assessment_rows(prepared.engine)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("problem", ("borrowed", "unknown", "different_source_session"))
async def test_session_ownership_is_explicit(prepared, monkeypatch, problem):
    with Session(prepared.engine) as sync:
        repo = repo_for(sync)
        if problem == "borrowed":
            sync.execute(select(Measurement))
        elif problem == "unknown":
            monkeypatch.setattr(repo.session, "in_transaction", lambda: None)
        else:
            repo.source.session = object()
        with pytest.raises(RuntimeError, match="session"):
            await run_assessment(repo, prepared)
        assert repo.session.rollback_count == 0
    assert assessment_rows(prepared.engine) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field",
    (
        "athlete_id",
        "schema_version",
        "content_hash",
        "content_hash_algorithm",
        "created_at",
        "persisted_at",
        "artifact_id",
    ),
)
async def test_load_rejects_tampered_record_metadata(prepared, monkeypatch, field):
    with Session(prepared.engine) as sync:
        repo = repo_for(sync)
        first = await run_assessment(repo, prepared)
        get = repo.audit.get

        async def changed(**kwargs):
            record = await get(**kwargs)
            if record is None or record.artifact_kind != KIND:
                return record
            value = (
                None
                if field == "persisted_at"
                else (
                    record.created_at - timedelta(seconds=1)
                    if field == "created_at"
                    else "tampered"
                )
            )
            return replace(record, **{field: value})

        monkeypatch.setattr(repo.audit, "get", changed)
        with pytest.raises((ValueError, service.GoalAssessmentError)):
            await load_assessment(repo, prepared, first)
        assert repo.session.in_transaction() is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "problem", ("criterion", "authority", "historical_availability", "source_json")
)
async def test_rehashed_forgery_fails_domain_replay(prepared, problem):
    with Session(prepared.engine) as sync:
        repo = repo_for(sync)
        first = await run_assessment(repo, prepared)
        artifact = first.artifact
        if problem == "criterion":
            artifact = replace(
                artifact,
                all_primary_criteria_status=GoalCriterionStatus.NOT_MET_UNDER_DECLARED_ERROR,
            )
        elif problem == "authority":
            artifact = replace(
                artifact, authority=replace(artifact.authority, planning_authorized=True)
            )
        elif problem == "historical_availability":
            artifact = replace(artifact, source_availability_at_activity_cutoff_verified=True)
        else:
            source = replace(
                artifact.census.sources[0], source_json=artifact.census.sources[0].source_json + " "
            )
            artifact = replace(
                artifact,
                census=replace(artifact.census, sources=(source,) + artifact.census.sources[1:]),
            )
        artifact = replace(
            artifact, content_hash=compute_content_hash(artifact, exclude_fields=GOAL_HASH_EXCLUDE)
        )
        with Session(prepared.engine) as writer:
            writer.execute(
                update(PlanningAuditArtifactRow)
                .where(PlanningAuditArtifactRow.artifact_id == artifact.artifact_id)
                .values(contract_json=canonical_json(artifact), content_hash=artifact.content_hash)
            )
            writer.commit()
        with pytest.raises((ValueError, service.GoalAssessmentError)):
            await load_assessment(repo, prepared, first)
        assert repo.session.in_transaction() is False


@pytest.mark.asyncio
async def test_full_protocol_digest_protects_hash_excluded_creation_time(prepared):
    with Session(prepared.engine) as sync:
        repo = repo_for(sync)
        first = await run_assessment(repo, prepared)
        changed = replace(
            prepared.protocol, created_at=prepared.protocol.created_at - timedelta(microseconds=1)
        )
        assert changed.verify_content_hash()
        with Session(prepared.engine) as writer:
            writer.execute(
                update(PlanningAuditArtifactRow)
                .where(PlanningAuditArtifactRow.artifact_id == changed.artifact_id)
                .values(contract_json=canonical_json(changed), created_at=changed.created_at)
            )
            writer.commit()
        with pytest.raises(service.GoalAssessmentError, match="protocol source changed"):
            await load_assessment(repo, prepared, first)


@pytest.mark.asyncio
async def test_missing_parent_never_uses_current_sources(prepared, monkeypatch):
    with Session(prepared.engine) as sync:
        repo = repo_for(sync)
        first = await run_assessment(repo, prepared)
        get = repo.audit.get

        async def missing(**kwargs):
            return (
                None
                if kwargs["artifact_kind"] == AuditArtifactKind.MESOCYCLE_GOAL_PROTOCOL
                else await get(**kwargs)
            )

        monkeypatch.setattr(repo.audit, "get", missing)
        with pytest.raises(LookupError):
            await load_assessment(repo, prepared, first)


@pytest.mark.asyncio
async def test_same_slot_wrong_protocol_hash_is_a_conflict(prepared):
    with Session(prepared.engine) as sync:
        repo = repo_for(sync)
        await run_assessment(repo, prepared)
        with pytest.raises(service.GoalAssessmentError, match="different protocol"):
            await run_assessment(
                repo,
                prepared,
                reference=GoalVersionReference(prepared.protocol.artifact_id, "0" * 64),
            )


@pytest.mark.asyncio
async def test_wrong_athlete_and_unavailable_or_future_cutoffs_are_rejected(prepared):
    with Session(prepared.engine) as sync:
        repo = repo_for(sync)
        first = await run_assessment(repo, prepared)
        with pytest.raises(service.GoalAssessmentError):
            await load_assessment(repo, prepared, first, athlete_id=str(UUID(int=999)))
        with pytest.raises(service.GoalAssessmentError, match="availability"):
            await load_assessment(
                repo,
                prepared,
                first,
                available_by=first.durable_available_at - timedelta(microseconds=1),
            )
        with pytest.raises(service.GoalAssessmentError, match="future"):
            await run_assessment(repo, prepared, cutoff=CAPTURE + timedelta(days=1))


@pytest.mark.asyncio
async def test_skipped_read_rollback_does_not_return_success(prepared, monkeypatch):
    with Session(prepared.engine) as sync:
        repo = repo_for(sync)
        first = await run_assessment(repo, prepared)

        async def skip():
            return None

        monkeypatch.setattr(repo.session, "rollback", skip)
        with pytest.raises(RuntimeError, match="did not close"):
            await load_assessment(repo, prepared, first)
