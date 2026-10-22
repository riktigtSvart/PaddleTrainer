"""P2.4A storage/workflow contracts on an isolated, file-based SQLite DB.

Use the production SQLAlchemy audit adapter, real canonical evidence restore,
and the real planner. The sync-to-async bridge follows existing repository
contract tests. Independent sessions verify committed visibility; no real
athlete data or PostgreSQL connection is used.
"""

from dataclasses import replace
from datetime import timedelta, timezone
import json
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import Column, Table, Uuid, create_engine, func, select
from sqlalchemy.orm import Session

import app.planning.application.make_observed_planner_run as observed_run
import app.planning.application.persist_prospective_validation_evidence as persistence
import app.planning.application.register_planning_utility_observation as registration
from app.db.base import Base
from app.planning.domain.common.enums import DecisionPurpose, PlanningScope
from app.planning.domain.common.refs import VersionRef
from app.planning.domain.common.serialization import (
    CONTENT_HASH_ALGORITHM,
    canonical_json,
    compute_content_hash,
)
from app.planning.domain.context.models import (
    CurrentStateContextProjection,
    EntryGateContextProjection,
    RuntimePlanningProjection,
    TrainingSpaceProjection,
    TrainingSpaceStatus,
    UnresolvedPlanningDimension,
    create_planning_context,
)
from app.planning.domain.decision.models import PlannerDecisionRequest
from app.planning.domain.entry_gate.models import EntryMode, GlobalEntryGate
from app.planning.domain.persistence.audit import AuditArtifactKind, AuditArtifactRecord
from app.planning.domain.response_evidence import TrainingResponseTiming
from app.planning.domain.training_dynamics import (
    EffectEvidenceLevel,
    PersonalAssociationPredictorKey,
    ResponseMetricReferenceKey,
)
from app.planning.domain.training_dynamics.prospective_cohort import ProspectiveValidationFamilyKey
from app.planning.domain.training_dynamics.prospective_validation import ProspectiveValidationAssessmentStatus
from app.planning.domain.training_dynamics.prospective_validation_evidence import (
    PROSPECTIVE_VALIDATION_EVIDENCE_HASH_EXCLUDE_FIELDS,
    PROSPECTIVE_VALIDATION_EVIDENCE_RULES_V01,
    PROSPECTIVE_VALIDATION_EVIDENCE_SCHEMA_V01,
    ProspectiveValidationEvidence,
    ProspectiveValidationEvidenceStatus,
)
from app.planning.domain.training_state.models import EvidenceCoverage, LoadAnchorStatus
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.planning.infrastructure.repositories.postgres_planning_audit import SqlAlchemyPlanningAuditRepository


UTC = timezone.utc
ATHLETE = "11111111-1111-4111-8111-111111111111"
FAMILY = ProspectiveValidationFamilyKey(
    model_id="personal-monotonic-median-direction",
    model_version="0.1.0",
    predictor_key=PersonalAssociationPredictorKey(metric_key="training_load_index", unit="au"),
    response_key=ResponseMetricReferenceKey(
        metric_key="fatigue",
        unit="score_0_10",
        response_timing=TrainingResponseTiming.SAME_DAY,
        stimulus_modality_key="RUNNING",
    ),
)


class AsyncSQLiteBridge:
    def __init__(self, session):
        self.session = session
        self.commit_count = 0
        self.rollback_count = 0
        self.execute_count = 0
        self.events = []
        self.fail_commit = False
        self.skip_commit = False

    def get_bind(self):
        return self.session.get_bind()

    def in_transaction(self):
        return self.session.in_transaction()

    async def execute(self, statement):
        self.execute_count += 1
        return self.session.execute(statement)

    def add(self, row):
        self.session.add(row)

    async def flush(self):
        self.session.flush()

    async def commit(self):
        if self.fail_commit:
            self.events.append("commit_failed")
            raise RuntimeError("synthetic commit failure")
        if self.skip_commit:
            self.events.append("commit_skipped")
            return
        self.session.commit()
        self.commit_count += 1
        self.events.append("commit")

    async def rollback(self):
        self.session.rollback()
        self.rollback_count += 1
        self.events.append("rollback")


@pytest.fixture
def database(tmp_path):
    metadata = Base.metadata
    if "users" not in metadata.tables:
        Table("users", metadata, Column("id", Uuid(), primary_key=True))
    path = (tmp_path / "p24a-contract.sqlite3").as_posix()
    engine = create_engine(f"sqlite+pysqlite:///{path}")
    metadata.create_all(
        engine,
        tables=[metadata.tables["users"], PlanningAuditArtifactRow.__table__],
    )
    with engine.begin() as connection:
        users = metadata.tables["users"]
        values = {"id": UUID(ATHLETE)}
        if "email" in users.c:
            values["email"] = "p24a-synthetic@example.invalid"
        if "timezone" in users.c:
            values["timezone"] = "Europe/Budapest"
        if "created_at" in users.c:
            values["created_at"] = connection.scalar(select(func.current_timestamp()))
        connection.execute(users.insert().values(**values))
    try:
        yield engine
    finally:
        engine.dispose()


def _evidence(*, as_of, created_at):
    # The synthetic D contract mirrors the existing P2.3F fixture. D replay is
    # covered by P2.3D/F; these tests retain real F persistence and restoration.
    provisional = ProspectiveValidationEvidence(
        evidence_id="PENDING",
        schema_version=PROSPECTIVE_VALIDATION_EVIDENCE_SCHEMA_V01,
        rules_version=PROSPECTIVE_VALIDATION_EVIDENCE_RULES_V01,
        athlete_id=ATHLETE,
        family_key=FAMILY,
        as_of=as_of,
        source_cohort_id="synthetic-cohort",
        source_cohort_content_hash="a" * 64,
        source_cohort_schema_version="prospective-validation-cohort-v0.1",
        source_cohort_rules_version="prospective-validation-cohort-rules-v0.1",
        source_multiplicity_guard_id="synthetic-guard",
        source_multiplicity_guard_content_hash="b" * 64,
        source_multiplicity_guard_schema_version="prospective-multiplicity-guard-v0.1",
        source_multiplicity_guard_rules_version="prospective-multiplicity-guard-rules-v0.1",
        source_assessment_id="synthetic-assessment",
        source_assessment_content_hash="c" * 64,
        source_assessment_schema_version="prospective-validation-assessment-v0.1",
        source_assessment_rules_version="prospective-validation-assessment-rules-v0.1",
        issued_challenge_count=5,
        directionally_scored_count=5,
        matched_count=5,
        mismatched_count=0,
        tied_unscorable_count=0,
        exact_one_sided_p_numerator=1,
        exact_one_sided_p_denominator=32,
        adjusted_alpha_numerator=1,
        adjusted_alpha_denominator=20,
        assessment_status=ProspectiveValidationAssessmentStatus.VALIDATION_CRITERIA_MET,
        validation_criteria_met=True,
        status=ProspectiveValidationEvidenceStatus.PROSPECTIVELY_VALIDATED,
        evidence_level=EffectEvidenceLevel.PROSPECTIVELY_VALIDATED,
        association_supported=True,
        prospective_validation_established=True,
        causal_attribution_established=False,
        effect_inference_authorized=False,
        readiness_inference_authorized=False,
        performance_prediction_authorized=False,
        prescription_change_authorized=False,
        planning_authorized=False,
        created_at=created_at,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )
    digest = compute_content_hash(
        provisional, exclude_fields=PROSPECTIVE_VALIDATION_EVIDENCE_HASH_EXCLUDE_FIELDS
    )
    return replace(
        provisional,
        evidence_id="pt-prospective-validation-evidence:" + digest,
        content_hash=digest,
    )


async def _seed_evidence(engine, monkeypatch):
    with engine.connect() as connection:
        boundary = connection.scalar(select(func.current_timestamp()))
    if boundary.tzinfo is None:
        boundary = boundary.replace(tzinfo=UTC)
    source = _evidence(
        as_of=boundary - timedelta(minutes=3),
        created_at=boundary - timedelta(minutes=2),
    )

    async def assembled(**kwargs):
        assert kwargs["athlete_id"] == source.athlete_id
        assert kwargs["family_key"] == source.family_key
        assert kwargs["as_of"] == source.as_of
        assert kwargs["created_at"] == source.created_at
        return source

    monkeypatch.setattr(persistence, "assemble_prospective_validation_evidence", assembled)
    with Session(engine, expire_on_commit=False) as sync:
        bridge = AsyncSQLiteBridge(sync)
        durable = await persistence.persist_prospective_validation_evidence(
            athlete_id=ATHLETE,
            family_key=FAMILY,
            as_of=source.as_of,
            created_at=source.created_at,
            audit_repository=SqlAlchemyPlanningAuditRepository(bridge),
            session=bridge,
        )
        assert bridge.commit_count == 1
        assert bridge.in_transaction() is False
    return durable


def _context(boundary):
    observed_at = boundary - timedelta(minutes=4)
    as_of = boundary - timedelta(minutes=1)
    runtime = RuntimePlanningProjection(
        current_state=CurrentStateContextProjection(
            current_training_state_hash="s" * 64,
            load_anchor_status=LoadAnchorStatus.PARTIAL_EXPOSURE,
            recent_source_coverage=EvidenceCoverage.PARTIAL,
            recent_observed_session_count=1,
            recent_known_duration_s=0,
            recent_complete_window_duration_s=None,
            latest_training_observed_at=observed_at,
        ),
        entry_gate=EntryGateContextProjection(
            entry_gate_decision_hash="g" * 64,
            global_gate=GlobalEntryGate.OPEN_WITH_CONSTRAINTS,
            entry_mode=EntryMode.CONSERVATIVE_REANCHOR,
            reason_codes=("REANCHOR_REQUIRED",),
            stimulus_gates=(),
        ),
        workout_family_registry_version="workout_family_registry_v0.1",
        workout_family_registry_hash="w" * 64,
        training_space=TrainingSpaceProjection(
            projection_scope="ENTRY_GATE_FAMILY_SPACE_V0.1",
            status=TrainingSpaceStatus.ENTRY_GATE_CONSTRAINED,
            families=(),
            unresolved_dimensions=(UnresolvedPlanningDimension.PLANNING_AUTHORITY,),
            final_authorization=False,
        ),
    )
    return create_planning_context(
        context_id="utility-context",
        athlete_id=ATHLETE,
        schema_version="apc_v0.1",
        as_of=as_of,
        information_cutoff_at=boundary - timedelta(minutes=2),
        created_at=as_of,
        planning_scope=PlanningScope.MICROCYCLE,
        decision_purpose=DecisionPurpose.CREATE_MICROCYCLE,
        source_snapshot_refs=(),
        engine_version=VersionRef("engine", "v0.1"),
        rules_version=VersionRef("rules", "v0.1"),
        evidence_pack_version=VersionRef("evidence", "v0.1"),
        runtime_projection=runtime,
    )


def _kwargs(source, bridge):
    context = _context(source.durable_available_at)
    request = PlannerDecisionRequest(
        request_id="utility-request",
        context_id=context.context_id,
        context_hash=context.content_hash,
        decision_purpose=context.decision_purpose,
        planning_scope=context.planning_scope,
        requested_at=source.durable_available_at,
    )
    return dict(
        context=context,
        request=request,
        run_id="utility-run",
        decision_id="utility-decision",
        rationale_id="utility-rationale",
        observation_created_at=request.requested_at,
        audit_repository=SqlAlchemyPlanningAuditRepository(bridge),
        session=bridge,
    )


def _rows(engine, kind):
    with Session(engine, expire_on_commit=False) as reader:
        rows = reader.execute(
            select(PlanningAuditArtifactRow).where(
                PlanningAuditArtifactRow.artifact_kind == kind.value
            )
        ).scalars().all()
        return tuple(
            SimpleNamespace(
                artifact_id=row.artifact_id,
                contract_json=row.contract_json,
                persisted_at=row.persisted_at,
            )
            for row in rows
        )


@pytest.mark.asyncio
async def test_committed_registration_is_visible_before_real_planner(database, monkeypatch):
    source = await _seed_evidence(database, monkeypatch)
    original_make = observed_run.planner.make_auditable_planner_run
    original_clock = observed_run._utc_now
    with Session(database, expire_on_commit=False) as sync:
        bridge = AsyncSQLiteBridge(sync)
        kwargs = _kwargs(source, bridge)

        def clock():
            assert bridge.in_transaction() is False
            bridge.events.append("clock")
            return original_clock()

        def checked_planner(**arguments):
            bridge.events.append("planner")
            assert bridge.commit_count == 1
            assert bridge.in_transaction() is False
            rows = _rows(database, AuditArtifactKind.PLANNING_UTILITY_OBSERVATION)
            assert len(rows) == 1
            raw = json.loads(rows[0].contract_json)
            assert raw["request_id"] == kwargs["request"].request_id
            assert raw["predecision_registration_established"] is False
            assert raw["validation_evidence_refs"][0]["evidence_id"] == source.evidence.evidence_id
            persisted = rows[0].persisted_at
            if persisted.tzinfo is None:
                persisted = persisted.replace(tzinfo=UTC)
            assert source.durable_available_at <= persisted < arguments["decision_time"]
            return original_make(**arguments)

        monkeypatch.setattr(observed_run, "_utc_now", clock)
        monkeypatch.setattr(observed_run.planner, "make_auditable_planner_run", checked_planner)
        result = await observed_run.make_observed_planner_run(**kwargs)
        assert bridge.events == ["commit", "clock", "planner"]
        baseline = original_make(
            context=kwargs["context"],
            request=kwargs["request"],
            run_id=kwargs["run_id"],
            decision_id=kwargs["decision_id"],
            rationale_id=kwargs["rationale_id"],
            decision_time=result.planner_run.decision.decision_time,
            created_at=result.planner_run.decision.created_at,
        )
        assert result.planner_run == baseline
        row = _rows(database, AuditArtifactKind.PLANNING_UTILITY_OBSERVATION)[0]
        assert row.contract_json == canonical_json(result.registration.observation)
        assert result.registration.observation.candidate_set_snapshot == baseline.candidate_set
        assert result.predecision_registration_established is True
        assert result.planning_authorized is False
        assert result.prescription_change_authorized is False
        assert result.planner_runtime_modified is False
        assert result.candidate_authority_modified is False


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ("raise", "no_commit"))
async def test_failed_or_skipped_commit_rolls_back_real_row_before_planner(database, monkeypatch, failure):
    source = await _seed_evidence(database, monkeypatch)

    def unexpected_planner(**kwargs):
        pytest.fail("Planner must not run without a completed registration commit.")

    monkeypatch.setattr(observed_run.planner, "make_auditable_planner_run", unexpected_planner)
    with Session(database, expire_on_commit=False) as sync:
        bridge = AsyncSQLiteBridge(sync)
        bridge.fail_commit = failure == "raise"
        bridge.skip_commit = failure == "no_commit"
        error = RuntimeError if failure == "raise" else registration.PlanningUtilityObservationError
        with pytest.raises(error):
            await observed_run.make_observed_planner_run(**_kwargs(source, bridge))
        assert bridge.commit_count == 0
        assert bridge.rollback_count == 1
        assert bridge.in_transaction() is False
        assert _rows(database, AuditArtifactKind.PLANNING_UTILITY_OBSERVATION) == ()
        assert len(_rows(database, AuditArtifactKind.PROSPECTIVE_VALIDATION_EVIDENCE)) == 1


@pytest.mark.asyncio
async def test_mismatched_real_repository_session_fails_before_query(database, monkeypatch):
    source = await _seed_evidence(database, monkeypatch)
    with Session(database) as writer, Session(database) as other:
        bridge = AsyncSQLiteBridge(writer)
        other_bridge = AsyncSQLiteBridge(other)
        kwargs = _kwargs(source, bridge)
        kwargs["audit_repository"] = SqlAlchemyPlanningAuditRepository(other_bridge)
        with pytest.raises(registration.PlanningUtilityObservationError, match="same transaction-owning"):
            await observed_run.make_observed_planner_run(**kwargs)
        assert bridge.execute_count == other_bridge.execute_count == 0
        assert bridge.commit_count == other_bridge.commit_count == 0
        assert bridge.rollback_count == other_bridge.rollback_count == 0
        assert _rows(database, AuditArtifactKind.PLANNING_UTILITY_OBSERVATION) == ()


@pytest.mark.asyncio
@pytest.mark.parametrize("existing", ("read", "uncommitted_evidence"))
async def test_preexisting_transaction_is_preserved_and_not_committed(database, monkeypatch, existing):
    source = await _seed_evidence(database, monkeypatch)
    with Session(database, expire_on_commit=False) as sync:
        bridge = AsyncSQLiteBridge(sync)
        kwargs = _kwargs(source, bridge)
        if existing == "read":
            await bridge.execute(select(PlanningAuditArtifactRow))
        else:
            pending = _evidence(
                as_of=source.evidence.as_of - timedelta(seconds=1),
                created_at=source.evidence.created_at,
            )
            await kwargs["audit_repository"].save(AuditArtifactRecord(
                artifact_kind=AuditArtifactKind.PROSPECTIVE_VALIDATION_EVIDENCE,
                artifact_id=pending.evidence_id,
                athlete_id=ATHLETE,
                schema_version=pending.schema_version,
                created_at=pending.created_at,
                content_hash_algorithm=pending.content_hash_algorithm,
                content_hash=pending.content_hash,
                contract_json=canonical_json(pending),
            ))
            assert len(_rows(database, AuditArtifactKind.PROSPECTIVE_VALIDATION_EVIDENCE)) == 1
        assert bridge.in_transaction() is True
        calls = bridge.execute_count
        with pytest.raises(registration.PlanningUtilityObservationError, match="fresh session"):
            await observed_run.make_observed_planner_run(**kwargs)
        assert bridge.execute_count == calls
        assert bridge.commit_count == bridge.rollback_count == 0
        assert bridge.in_transaction() is True
        assert _rows(database, AuditArtifactKind.PLANNING_UTILITY_OBSERVATION) == ()
        await bridge.rollback()
        assert len(_rows(database, AuditArtifactKind.PROSPECTIVE_VALIDATION_EVIDENCE)) == 1


@pytest.mark.asyncio
async def test_real_registration_retry_preserves_original_artifact_and_db_time(database, monkeypatch):
    source = await _seed_evidence(database, monkeypatch)
    with Session(database, expire_on_commit=False) as sync:
        bridge = AsyncSQLiteBridge(sync)
        kwargs = _kwargs(source, bridge)
        registration_kwargs = dict(
            context=kwargs["context"],
            request=kwargs["request"],
            planned_run_id=kwargs["run_id"],
            planned_decision_id=kwargs["decision_id"],
            planned_rationale_id=kwargs["rationale_id"],
            created_at=kwargs["observation_created_at"],
            audit_repository=kwargs["audit_repository"],
            session=bridge,
        )
        first = await registration.register_planning_utility_observation(**registration_kwargs)
        registration_kwargs["created_at"] += timedelta(minutes=1)
        second = await registration.register_planning_utility_observation(**registration_kwargs)
        assert second.reused_durable_observation is True
        assert second.registration_committed is True
        assert second.observation == first.observation
        assert second.durable_registered_at == first.durable_registered_at
        assert bridge.commit_count == 2
        rows = _rows(database, AuditArtifactKind.PLANNING_UTILITY_OBSERVATION)
        assert len(rows) == 1
        assert rows[0].contract_json == canonical_json(first.observation)


@pytest.mark.asyncio
async def test_source_after_request_boundary_rolls_back_owned_read_transaction(database, monkeypatch):
    source = await _seed_evidence(database, monkeypatch)

    def unexpected_planner(**kwargs):
        pytest.fail("No evidence was durably available at this request boundary.")

    monkeypatch.setattr(observed_run.planner, "make_auditable_planner_run", unexpected_planner)
    with Session(database, expire_on_commit=False) as sync:
        bridge = AsyncSQLiteBridge(sync)
        kwargs = _kwargs(source, bridge)
        kwargs["request"] = replace(
            kwargs["request"],
            requested_at=kwargs["request"].requested_at - timedelta(seconds=1),
        )
        with pytest.raises(ValueError, match="at least one durable"):
            await observed_run.make_observed_planner_run(**kwargs)
        assert bridge.events == ["rollback"]
        assert bridge.commit_count == 0
        assert bridge.in_transaction() is False
        assert _rows(database, AuditArtifactKind.PLANNING_UTILITY_OBSERVATION) == ()
        assert len(_rows(database, AuditArtifactKind.PROSPECTIVE_VALIDATION_EVIDENCE)) == 1
