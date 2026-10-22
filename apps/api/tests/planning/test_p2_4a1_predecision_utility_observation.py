from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest

import app.planning.application.register_planning_utility_observation as registration
import app.planning.application.make_observed_planner_run as observed_run

from app.planning.domain.common.serialization import canonical_json

from app.planning.domain.common.enums import (
    DecisionPurpose,
    PlanningScope,
)
from app.planning.domain.decision.models import (
    CandidateCoverageStatus,
    CandidateGenerationExclusion,
    PlannerActionCandidate,
    PlannerActionType,
    PlannerDecisionRequest,
    finalize_candidate_action_set,
)
from app.planning.domain.persistence.audit import (
    AuditArtifactConflictError,
    AuditArtifactKind,
    AuditArtifactRecord,
    AuditArtifactSaveResult,
    AuditArtifactSaveStatus,
)
from app.planning.domain.planning_utility.observation import (
    PlanningUtilityObservationStatus,
)
from app.planning.domain.response_evidence import (
    TrainingResponseTiming,
)
from app.planning.domain.training_dynamics import (
    EffectEvidenceLevel,
    PersonalAssociationPredictorKey,
    ResponseMetricReferenceKey,
)
from app.planning.domain.training_dynamics.prospective_cohort import (
    ProspectiveValidationFamilyKey,
)
from app.planning.domain.training_dynamics.prospective_validation_evidence import (
    PROSPECTIVE_VALIDATION_EVIDENCE_RULES_V01,
    PROSPECTIVE_VALIDATION_EVIDENCE_SCHEMA_V01,
    ProspectiveValidationEvidenceStatus,
)


UTC = timezone.utc

ATHLETE = "11111111-1111-4111-8111-111111111111"

CONTEXT_HASH = "a" * 64
ENVELOPE_HASH = "b" * 64
POLICY_HASH = "d" * 64


def dt(hour: int) -> datetime:
    return datetime(
        2026,
        10,
        21,
        hour,
        tzinfo=UTC,
    )


FAMILY = ProspectiveValidationFamilyKey(
    model_id="personal-monotonic-median-direction",
    model_version="0.1.0",
    predictor_key=PersonalAssociationPredictorKey(
        metric_key="training_load_index",
        unit="au",
    ),
    response_key=ResponseMetricReferenceKey(
        metric_key="fatigue",
        unit="score_0_10",
        response_timing=TrainingResponseTiming.SAME_DAY,
        stimulus_modality_key="RUNNING",
    ),
)


@dataclass(frozen=True)
class EvidenceStub:
    evidence_id: str
    content_hash: str

    as_of: datetime = dt(9)
    created_at: datetime = dt(10)

    schema_version: str = (
        PROSPECTIVE_VALIDATION_EVIDENCE_SCHEMA_V01
    )
    rules_version: str = (
        PROSPECTIVE_VALIDATION_EVIDENCE_RULES_V01
    )

    athlete_id: str = ATHLETE
    family_key: ProspectiveValidationFamilyKey = FAMILY

    status: ProspectiveValidationEvidenceStatus = (
        ProspectiveValidationEvidenceStatus
        .PROSPECTIVELY_VALIDATED
    )

    evidence_level: EffectEvidenceLevel = (
        EffectEvidenceLevel
        .PROSPECTIVELY_VALIDATED
    )

    association_supported: bool = True
    prospective_validation_established: bool = True

    causal_attribution_established: bool = False
    effect_inference_authorized: bool = False
    readiness_inference_authorized: bool = False
    performance_prediction_authorized: bool = False
    prescription_change_authorized: bool = False
    planning_authorized: bool = False

    def verify_content_hash(self):
        return True


@dataclass(frozen=True)
class ContextStub:
    athlete_id: str = ATHLETE
    context_id: str = "context-1"
    content_hash: str = CONTEXT_HASH
    as_of: datetime = dt(10)


@dataclass(frozen=True)
class EnvelopeStub:
    context_id: str
    context_hash: str
    decision_purpose: DecisionPurpose
    planning_scope: PlanningScope

    content_hash: str = ENVELOPE_HASH

    def verify_content_hash(self):
        return True


@dataclass(frozen=True)
class PolicySetStub:
    policy_set_version: str = (
        "minimal_planner_policy_set_v0.1"
    )
    content_hash: str = POLICY_HASH


class FakeSession:
    def __init__(self):
        self.commit_count = 0
        self.rollback_count = 0
        self.transaction_active = False

    def in_transaction(self):
        return self.transaction_active

    async def commit(self):
        self.commit_count += 1
        self.transaction_active = False

    async def rollback(self):
        self.rollback_count += 1
        self.transaction_active = False


class FakeAuditRepository:
    def __init__(
        self,
        *,
        session,
        records=(),
        database_clock=None,
    ):
        self.session = session
        self.records = {
            (
                record.artifact_kind,
                record.artifact_id,
            ): record
            for record in records
        }

        self.database_clock = (
            database_clock
            or (lambda: dt(14))
        )

    async def list_for_athlete(
        self,
        *,
        athlete_id,
        artifact_kind=None,
        limit=50,
    ):
        self.session.transaction_active = True
        values = tuple(
            record
            for record in self.records.values()
            if record.athlete_id == athlete_id
            and (
                artifact_kind is None
                or record.artifact_kind
                == artifact_kind
            )
        )

        return values[:limit]

    async def get(
        self,
        *,
        artifact_kind,
        artifact_id,
    ):
        self.session.transaction_active = True
        return self.records.get(
            (
                artifact_kind,
                artifact_id,
            )
        )

    async def save(
        self,
        record,
    ):
        self.session.transaction_active = True
        if record.persisted_at is not None:
            raise ValueError(
                "persisted_at must be database-assigned."
            )

        key = (
            record.artifact_kind,
            record.artifact_id,
        )

        existing = self.records.get(key)

        if existing is not None:
            if (
                existing.content_hash
                != record.content_hash
                or existing.contract_json
                != record.contract_json
                or existing.athlete_id
                != record.athlete_id
            ):
                raise AuditArtifactConflictError(
                    "immutable conflict"
                )

            return AuditArtifactSaveResult(
                status=(
                    AuditArtifactSaveStatus
                    .ALREADY_PRESENT
                ),
                artifact_kind=record.artifact_kind,
                artifact_id=record.artifact_id,
                content_hash=record.content_hash,
            )

        self.records[key] = replace(
            record,
            persisted_at=self.database_clock(),
        )

        return AuditArtifactSaveResult(
            status=AuditArtifactSaveStatus.CREATED,
            artifact_kind=record.artifact_kind,
            artifact_id=record.artifact_id,
            content_hash=record.content_hash,
        )


def request():
    return PlannerDecisionRequest(
        request_id="request-1",
        context_id="context-1",
        context_hash=CONTEXT_HASH,
        decision_purpose=(
            DecisionPurpose.REVISE_PLAN
        ),
        planning_scope=(
            PlanningScope.MICROCYCLE
        ),
        requested_at=dt(12),
    )


def envelope():
    return EnvelopeStub(
        context_id="context-1",
        context_hash=CONTEXT_HASH,
        decision_purpose=(
            DecisionPurpose.REVISE_PLAN
        ),
        planning_scope=(
            PlanningScope.MICROCYCLE
        ),
    )


def candidate_set():
    return finalize_candidate_action_set(
        envelope_hash=ENVELOPE_HASH,
        candidates=(
            PlannerActionCandidate(
                action_id="action:defer",
                action_type=PlannerActionType.DEFER,
                target_ref=None,
                plan_mutation_authorized=False,
                parameters=(),
                reason_codes=(
                    "SAFE_FALLBACK_AVAILABLE",
                ),
            ),
            PlannerActionCandidate(
                action_id=(
                    "action:select_family:easy@v1"
                ),
                action_type=(
                    PlannerActionType
                    .SELECT_WORKOUT_FAMILY
                ),
                target_ref=(
                    "workout_family:easy@v1"
                ),
                plan_mutation_authorized=True,
                parameters=(("fixture_parameter", "preserved"),),
                reason_codes=("FIXTURE_SELECTION_REASON",),
            ),
        ),
        excluded_during_generation=(
            CandidateGenerationExclusion(
                target_ref="workout_family:excluded@v1",
                reason_codes=("FIXTURE_EXCLUSION",),
            ),
        ),
        coverage_status=CandidateCoverageStatus.SUFFICIENT,
    )


def evidence_record(
    *,
    evidence_id,
    content_hash,
    persisted_at,
    athlete_id=ATHLETE,
):
    return AuditArtifactRecord(
        artifact_kind=(
            AuditArtifactKind
            .PROSPECTIVE_VALIDATION_EVIDENCE
        ),
        artifact_id=evidence_id,
        athlete_id=athlete_id,
        schema_version=(
            PROSPECTIVE_VALIDATION_EVIDENCE_SCHEMA_V01
        ),
        created_at=dt(10),
        content_hash_algorithm="sha256",
        content_hash=content_hash,
        contract_json="{}",
        persisted_at=persisted_at,
    )


def install_builders(
    monkeypatch,
    evidence_map,
):
    monkeypatch.setattr(
        registration,
        "build_planner_input_envelope",
        lambda **kwargs: envelope(),
    )

    monkeypatch.setattr(
        registration,
        "generate_candidate_action_set",
        lambda **kwargs: candidate_set(),
    )

    monkeypatch.setattr(
        registration,
        "build_minimal_planning_policy_set",
        lambda: PolicySetStub(),
    )

    monkeypatch.setattr(
        registration,
        "restore_prospective_validation_evidence_audit_artifact",
        lambda record: evidence_map[
            record.artifact_id
        ],
    )


@pytest.mark.asyncio
async def test_registration_captures_all_available_validated_evidence(
    monkeypatch,
):
    session = FakeSession()
    first = EvidenceStub(
        evidence_id="evidence-1",
        content_hash="1" * 64,
    )

    second = EvidenceStub(
        evidence_id="evidence-2",
        content_hash="2" * 64,
    )

    records = (
        evidence_record(
            evidence_id=first.evidence_id,
            content_hash=first.content_hash,
            persisted_at=dt(10),
        ),
        evidence_record(
            evidence_id=second.evidence_id,
            content_hash=second.content_hash,
            persisted_at=dt(11),
        ),
    )

    install_builders(
        monkeypatch,
        {
            first.evidence_id: first,
            second.evidence_id: second,
        },
    )


    result = await (
        registration
        .register_planning_utility_observation(
            context=ContextStub(),
            request=request(),

            planned_run_id="run-1",
            planned_decision_id="decision-1",
            planned_rationale_id="rationale-1",

            created_at=dt(13),

            audit_repository=FakeAuditRepository(
                session=session,
                records=records,
            ),
            session=session,
        )
    )

    observation = result.observation

    assert (
        observation.available_validation_evidence_count
        == 2
    )

    assert tuple(
        ref.evidence_id
        for ref in observation.validation_evidence_refs
    ) == (
        "evidence-1",
        "evidence-2",
    )

    assert observation.candidate_action_ids == (
        "action:defer",
        "action:select_family:easy@v1",
    )

    assert (
        observation.mutation_authorized_candidate_ids
        == (
            "action:select_family:easy@v1",
        )
    )

    assert (
        observation.status
        == PlanningUtilityObservationStatus
        .REGISTERED_SHADOW_ONLY
    )

    assert observation.shadow_only is True
    assert observation.shadow_action_selected is False

    assert (
        observation.utility_assessment_established
        is False
    )
    assert observation.planning_utility_supported is False

    assert (
        observation.prescription_change_authorized
        is False
    )
    assert observation.planning_authorized is False

    assert observation.verify_content_hash()

    assert result.durable_registered_at == dt(14)

    assert session.commit_count == 1
    assert session.rollback_count == 0


@pytest.mark.asyncio
async def test_evidence_persisted_after_request_boundary_is_excluded(
    monkeypatch,
):
    session = FakeSession()
    current = EvidenceStub(
        evidence_id="current",
        content_hash="3" * 64,
    )

    future = EvidenceStub(
        evidence_id="future",
        content_hash="4" * 64,
    )

    records = (
        evidence_record(
            evidence_id="current",
            content_hash=current.content_hash,
            persisted_at=dt(11),
        ),
        evidence_record(
            evidence_id="future",
            content_hash=future.content_hash,
            persisted_at=dt(13),
        ),
    )

    restored = []

    install_builders(
        monkeypatch,
        {
            "current": current,
            "future": future,
        },
    )

    original = (
        registration
        .restore_prospective_validation_evidence_audit_artifact
    )

    def tracking_restore(record):
        restored.append(
            record.artifact_id
        )
        return original(record)

    monkeypatch.setattr(
        registration,
        "restore_prospective_validation_evidence_audit_artifact",
        tracking_restore,
    )

    result = await (
        registration
        .register_planning_utility_observation(
            context=ContextStub(),
            request=request(),

            planned_run_id="run-1",
            planned_decision_id="decision-1",
            planned_rationale_id="rationale-1",

            created_at=dt(13),

            audit_repository=FakeAuditRepository(
                session=session,
                records=records,
            ),
            session=session,
        )
    )

    assert (
        result.observation
        .available_validation_evidence_count
        == 1
    )

    assert restored == [
        "current",
    ]


@pytest.mark.asyncio
async def test_no_available_validated_evidence_fails_closed(
    monkeypatch,
):
    session = FakeSession()
    install_builders(
        monkeypatch,
        {},
    )

    with pytest.raises(
        ValueError,
        match="at least one durable",
    ):
        await (
            registration
            .register_planning_utility_observation(
                context=ContextStub(),
                request=request(),

                planned_run_id="run-1",
                planned_decision_id="decision-1",
                planned_rationale_id="rationale-1",

                created_at=dt(13),

                audit_repository=FakeAuditRepository(session=session),
                session=session,
            )
        )


@pytest.mark.asyncio
async def test_evidence_scan_limit_fails_closed_before_restore(
    monkeypatch,
):
    session = FakeSession()
    records = tuple(
        evidence_record(
            evidence_id=f"evidence-{index}",
            content_hash=(
                f"{index + 1:064x}"[-64:]
            ),
            persisted_at=dt(11),
        )
        for index in range(500)
    )

    monkeypatch.setattr(
        registration,
        "build_planner_input_envelope",
        lambda **kwargs: envelope(),
    )

    monkeypatch.setattr(
        registration,
        "generate_candidate_action_set",
        lambda **kwargs: candidate_set(),
    )

    monkeypatch.setattr(
        registration,
        "build_minimal_planning_policy_set",
        lambda: PolicySetStub(),
    )

    monkeypatch.setattr(
        registration,
        "restore_prospective_validation_evidence_audit_artifact",
        lambda record: pytest.fail(
            "Incomplete census must fail before restore."
        ),
    )

    with pytest.raises(
        registration.PlanningUtilityObservationError,
        match="scan completeness is unknown",
    ):
        await (
            registration
            .register_planning_utility_observation(
                context=ContextStub(),
                request=request(),

                planned_run_id="run-1",
                planned_decision_id="decision-1",
                planned_rationale_id="rationale-1",

                created_at=dt(13),

                audit_repository=FakeAuditRepository(
                    session=session,
                    records=records,
                ),
                session=session,
            )
        )


@pytest.mark.asyncio
async def test_retry_reuses_original_durable_registration(
    monkeypatch,
):
    session = FakeSession()
    source = EvidenceStub(
        evidence_id="evidence-1",
        content_hash="5" * 64,
    )

    record = evidence_record(
        evidence_id=source.evidence_id,
        content_hash=source.content_hash,
        persisted_at=dt(11),
    )

    install_builders(
        monkeypatch,
        {
            source.evidence_id: source,
        },
    )

    repository = FakeAuditRepository(
        session=session,
        records=(record,),
        database_clock=lambda: dt(14),
    )

    first = await (
        registration
        .register_planning_utility_observation(
            context=ContextStub(),
            request=request(),

            planned_run_id="run-1",
            planned_decision_id="decision-1",
            planned_rationale_id="rationale-1",

            created_at=dt(13),

            audit_repository=repository,
            session=session,
        )
    )

    repository.database_clock = (
        lambda: dt(18)
    )

    second = await (
        registration
        .register_planning_utility_observation(
            context=ContextStub(),
            request=request(),

            planned_run_id="run-1",
            planned_decision_id="decision-1",
            planned_rationale_id="rationale-1",

            created_at=dt(17),

            audit_repository=repository,
            session=session,
        )
    )

    assert (
        first.observation.observation_id
        == second.observation.observation_id
    )

    assert (
        first.observation.content_hash
        == second.observation.content_hash
    )

    assert second.observation.created_at == dt(13)
    assert second.durable_registered_at == dt(14)

    assert second.reused_durable_observation is True


@pytest.mark.asyncio
async def test_same_request_cannot_be_reregistered_with_different_run_identity(
    monkeypatch,
):
    session = FakeSession()
    source = EvidenceStub(
        evidence_id="evidence-1",
        content_hash="6" * 64,
    )

    record = evidence_record(
        evidence_id=source.evidence_id,
        content_hash=source.content_hash,
        persisted_at=dt(11),
    )

    install_builders(
        monkeypatch,
        {
            source.evidence_id: source,
        },
    )

    repository = FakeAuditRepository(
        session=session,
        records=(record,),
    )

    first = await (
        registration
        .register_planning_utility_observation(
            context=ContextStub(),
            request=request(),

            planned_run_id="run-1",
            planned_decision_id="decision-1",
            planned_rationale_id="rationale-1",

            created_at=dt(13),

            audit_repository=repository,
            session=session,
        )
    )


    with pytest.raises(
        registration.PlanningUtilityObservationError,
        match="differs from",
    ):
        await (
            registration
            .register_planning_utility_observation(
                context=ContextStub(),
                request=request(),

                planned_run_id="run-2",
                planned_decision_id="decision-2",
                planned_rationale_id="rationale-2",

                created_at=dt(13),

                audit_repository=repository,
                session=session,
            )
        )

    assert first.observation.observation_id
    assert session.rollback_count == 1


@pytest.mark.asyncio
async def test_database_registration_time_cannot_predate_request(
    monkeypatch,
):
    session = FakeSession()
    source = EvidenceStub(
        evidence_id="evidence-1",
        content_hash="7" * 64,
    )

    record = evidence_record(
        evidence_id=source.evidence_id,
        content_hash=source.content_hash,
        persisted_at=dt(11),
    )

    install_builders(
        monkeypatch,
        {
            source.evidence_id: source,
        },
    )


    with pytest.raises(
        registration.PlanningUtilityObservationError,
        match="predates materialization",
    ):
        await (
            registration
            .register_planning_utility_observation(
                context=ContextStub(),
                request=request(),

                planned_run_id="run-1",
                planned_decision_id="decision-1",
                planned_rationale_id="rationale-1",

                created_at=dt(13),

                audit_repository=FakeAuditRepository(
                    session=session,
                    records=(record,),
                    database_clock=lambda: dt(11),
                ),
                session=session,
            )
        )

    assert session.commit_count == 0
    assert session.rollback_count == 1


@pytest.mark.asyncio
async def test_cross_athlete_evidence_record_fails_closed(
    monkeypatch,
):
    session = FakeSession()
    source = EvidenceStub(
        evidence_id="evidence-1",
        content_hash="8" * 64,
    )

    record = evidence_record(
        evidence_id=source.evidence_id,
        content_hash=source.content_hash,
        persisted_at=dt(11),
        athlete_id=(
            "99999999-9999-4999-8999-999999999999"
        ),
    )

    install_builders(
        monkeypatch,
        {
            source.evidence_id: source,
        },
    )

    # The repository should not normally return this record for ATHLETE.
    # Force that corruption explicitly.
    repository = FakeAuditRepository(session=session)

    async def bad_list(**kwargs):
        return (record,)

    repository.list_for_athlete = bad_list

    with pytest.raises(
        registration.PlanningUtilityObservationError,
        match="cross-athlete",
    ):
        await (
            registration
            .register_planning_utility_observation(
                context=ContextStub(),
                request=request(),

                planned_run_id="run-1",
                planned_decision_id="decision-1",
                planned_rationale_id="rationale-1",

                created_at=dt(13),

                audit_repository=repository,
                session=session,
            )
        )

def observed_harness(monkeypatch, *, fail_commit=False, fail_save=False):
    """Exercise the real registration service; replace only planner execution.

    The fake repository is an application seam, not a DB-rollback proof.
    Candidate snapshot hashing uses the real domain contract/finalizer.
    """
    events = []
    source = EvidenceStub(evidence_id="workflow-evidence", content_hash="8" * 64)
    record = evidence_record(
        evidence_id=source.evidence_id,
        content_hash=source.content_hash,
        persisted_at=dt(11),
    )
    install_builders(monkeypatch, {source.evidence_id: source})

    class RecordingRepository(FakeAuditRepository):
        async def save(self, record):
            events.append("save")
            if fail_save:
                raise RuntimeError("fixture save failure")
            return await super().save(record)

    class RecordingSession(FakeSession):
        async def commit(self):
            if fail_commit:
                events.append("commit_failed")
                raise RuntimeError("fixture commit failure")
            await super().commit()
            events.append("commit")

        async def rollback(self):
            events.append("rollback")
            await super().rollback()

    session = RecordingSession()
    harness = SimpleNamespace(
        events=events,
        source=source,
        source_record=record,
        repository=RecordingRepository(session=session, records=(record,)),
        session=session,
        planner_calls=[],
        runs=[],
    )
    monkeypatch.setattr(
        observed_run.planner, "build_planner_input_envelope", lambda **kwargs: envelope()
    )
    monkeypatch.setattr(
        observed_run.planner, "generate_candidate_action_set", lambda **kwargs: candidate_set()
    )
    monkeypatch.setattr(
        observed_run.planner, "build_minimal_planning_policy_set", lambda: PolicySetStub()
    )

    def clock():
        events.append("clock")
        assert harness.session.commit_count == 1
        return dt(15)

    def planner_call(**kwargs):
        events.append("planner")
        assert harness.session.commit_count == 1
        assert events.index("commit") < events.index("clock") < events.index("planner")
        harness.planner_calls.append(kwargs)
        candidates = candidate_set()
        decision = SimpleNamespace(
            decision_id=kwargs["decision_id"],
            request_id=kwargs["request"].request_id,
            context_id=kwargs["request"].context_id,
            context_hash=kwargs["request"].context_hash,
            envelope_hash=ENVELOPE_HASH,
            candidate_set_hash=candidates.content_hash,
            decision_time=kwargs["decision_time"],
            created_at=kwargs["created_at"],
            engine_version=kwargs["engine_version"],
            selected_action=candidates.candidates[1],
            verify_content_hash=lambda: True,
        )
        run = observed_run.planner.AuditablePlannerRun(
            envelope=envelope(),
            candidate_set=candidates,
            policy_set=PolicySetStub(),
            decision=decision,
            rationale=object(),
            run_record=object(),
        )
        harness.runs.append(run)
        return run

    monkeypatch.setattr(observed_run, "_utc_now", clock)
    monkeypatch.setattr(observed_run.planner, "make_auditable_planner_run", planner_call)
    return harness


def observed_kwargs(harness):
    return dict(
        context=ContextStub(),
        request=request(),
        run_id="run-1",
        decision_id="decision-1",
        rationale_id="rationale-1",
        observation_created_at=dt(13),
        audit_repository=harness.repository,
        session=harness.session,
    )


@pytest.mark.asyncio
async def test_complete_candidate_snapshot_is_in_the_durable_contract(monkeypatch):
    harness = observed_harness(monkeypatch)
    result = await observed_run.make_observed_planner_run(**observed_kwargs(harness))
    observation = result.registration.observation
    snapshot = observation.candidate_set_snapshot
    record = await harness.repository.get(
        artifact_kind=AuditArtifactKind.PLANNING_UTILITY_OBSERVATION,
        artifact_id=observation.observation_id,
    )
    raw = json.loads(record.contract_json)
    assert raw["candidate_set_snapshot"] == json.loads(canonical_json(candidate_set()))
    assert snapshot.verify_content_hash()
    assert snapshot.content_hash == observation.candidate_set_content_hash
    assert snapshot.candidates[1].action_type == PlannerActionType.SELECT_WORKOUT_FAMILY
    assert snapshot.candidates[1].target_ref == "workout_family:easy@v1"
    assert snapshot.candidates[1].plan_mutation_authorized is True
    assert snapshot.candidates[1].parameters == (("fixture_parameter", "preserved"),)
    assert snapshot.candidates[1].reason_codes == ("FIXTURE_SELECTION_REASON",)
    assert snapshot.excluded_during_generation[0].reason_codes == ("FIXTURE_EXCLUSION",)
    assert raw["predecision_registration_established"] is False
    assert raw["planner_runtime_modified"] is False
    assert raw["candidate_authority_modified"] is False


@pytest.mark.asyncio
async def test_workflow_commits_before_sampling_time_and_entering_planner(monkeypatch):
    harness = observed_harness(monkeypatch)
    result = await observed_run.make_observed_planner_run(**observed_kwargs(harness))
    assert harness.events == ["save", "commit", "clock", "planner"]
    assert result.registration.registration_committed is True
    assert result.registration.durable_registered_at == dt(14)
    assert harness.planner_calls[0]["decision_time"] == dt(15)
    assert harness.planner_calls[0]["created_at"] == dt(15)
    assert harness.planner_calls[0]["run_id"] == "run-1"
    assert harness.planner_calls[0]["decision_id"] == "decision-1"
    assert harness.planner_calls[0]["rationale_id"] == "rationale-1"
    assert result.planner_run is harness.runs[0]
    assert result.planner_run.decision.selected_action.plan_mutation_authorized is True
    assert result.predecision_registration_established is True
    assert result.utility_assessment_established is False
    assert result.planning_utility_supported is False
    assert result.prescription_change_authorized is False
    assert result.planning_authorized is False
    assert result.planner_runtime_modified is False
    assert result.candidate_authority_modified is False


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ("save", "commit"))
async def test_persistence_failure_prevents_planner_execution(monkeypatch, failure):
    harness = observed_harness(
        monkeypatch,
        fail_save=failure == "save",
        fail_commit=failure == "commit",
    )
    with pytest.raises(RuntimeError, match=f"fixture {failure} failure"):
        await observed_run.make_observed_planner_run(**observed_kwargs(harness))
    expected = ["save", "rollback"] if failure == "save" else ["save", "commit_failed", "rollback"]
    assert harness.events == expected
    assert harness.planner_calls == []
    assert harness.session.commit_count == 0
    assert harness.session.rollback_count == 1


@pytest.mark.asyncio
async def test_missing_database_registration_time_prevents_planner_execution(monkeypatch):
    harness = observed_harness(monkeypatch)
    harness.repository.database_clock = lambda: None
    with pytest.raises(registration.PlanningUtilityObservationError, match="no database persistence"):
        await observed_run.make_observed_planner_run(**observed_kwargs(harness))
    assert harness.events == ["save", "rollback"]
    assert harness.planner_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("hour", (13, 14))
async def test_clock_not_after_registration_prevents_planner_execution(monkeypatch, hour):
    harness = observed_harness(monkeypatch)

    def clock():
        harness.events.append("clock")
        return dt(hour)

    monkeypatch.setattr(observed_run, "_utc_now", clock)
    with pytest.raises(observed_run.ObservedPlannerRunError, match="strictly follow"):
        await observed_run.make_observed_planner_run(**observed_kwargs(harness))
    assert harness.events == ["save", "commit", "clock"]
    assert harness.planner_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("drift", ("envelope", "candidate", "policy"))
async def test_input_drift_is_rejected_before_entering_planner(monkeypatch, drift):
    harness = observed_harness(monkeypatch)
    if drift == "envelope":
        monkeypatch.setattr(
            observed_run.planner,
            "build_planner_input_envelope",
            lambda **kwargs: replace(envelope(), content_hash="e" * 64),
        )
    elif drift == "candidate":
        original = candidate_set()
        changed = finalize_candidate_action_set(
            envelope_hash=original.envelope_hash,
            candidates=(
                original.candidates[0],
                replace(original.candidates[1], parameters=(("fixture_parameter", "changed"),)),
            ),
            excluded_during_generation=original.excluded_during_generation,
            coverage_status=original.coverage_status,
        )
        monkeypatch.setattr(
            observed_run.planner, "generate_candidate_action_set", lambda **kwargs: changed
        )
    else:
        monkeypatch.setattr(
            observed_run.planner,
            "build_minimal_planning_policy_set",
            lambda: replace(PolicySetStub(), content_hash="e" * 64),
        )
    with pytest.raises(observed_run.ObservedPlannerRunError, match="inputs differ"):
        await observed_run.make_observed_planner_run(**observed_kwargs(harness))
    assert harness.events == ["save", "commit"]
    assert harness.planner_calls == []
    assert sum(
        record.artifact_kind == AuditArtifactKind.PLANNING_UTILITY_OBSERVATION
        for record in harness.repository.records.values()
    ) == 1


@pytest.mark.asyncio
async def test_wrong_request_on_returned_decision_fails_closed(monkeypatch):
    harness = observed_harness(monkeypatch)
    original = observed_run.planner.make_auditable_planner_run

    def wrong_decision(**kwargs):
        run = original(**kwargs)
        bad = SimpleNamespace(**{**vars(run.decision), "request_id": "different-request"})
        return replace(run, decision=bad)

    monkeypatch.setattr(observed_run.planner, "make_auditable_planner_run", wrong_decision)
    with pytest.raises(observed_run.ObservedPlannerRunError, match="decision does not bind"):
        await observed_run.make_observed_planner_run(**observed_kwargs(harness))
    assert harness.events == ["save", "commit", "clock", "planner"]


@pytest.mark.asyncio
async def test_existing_registration_is_retained_without_automatic_reexecution(monkeypatch):
    harness = observed_harness(monkeypatch)
    first = await observed_run.make_observed_planner_run(**observed_kwargs(harness))
    with pytest.raises(observed_run.ObservedPlannerRunError, match="explicit recovery"):
        await observed_run.make_observed_planner_run(**observed_kwargs(harness))
    assert harness.events == ["save", "commit", "clock", "planner", "commit"]
    assert len(harness.planner_calls) == 1
    record = await harness.repository.get(
        artifact_kind=AuditArtifactKind.PLANNING_UTILITY_OBSERVATION,
        artifact_id=first.registration.observation.observation_id,
    )
    assert record.persisted_at == dt(14)
    assert record.content_hash == first.registration.observation.content_hash


@pytest.mark.asyncio
async def test_changed_candidate_semantics_conflict_in_the_same_request_slot(monkeypatch):
    harness = observed_harness(monkeypatch)
    first = await observed_run.make_observed_planner_run(**observed_kwargs(harness))
    original = candidate_set()
    changed = finalize_candidate_action_set(
        envelope_hash=original.envelope_hash,
        candidates=(
            original.candidates[0],
            replace(original.candidates[1], reason_codes=("CHANGED_FIXTURE_REASON",)),
        ),
        excluded_during_generation=original.excluded_during_generation,
        coverage_status=original.coverage_status,
    )
    monkeypatch.setattr(registration, "generate_candidate_action_set", lambda **kwargs: changed)
    with pytest.raises(registration.PlanningUtilityObservationError, match="differs from"):
        await observed_run.make_observed_planner_run(**observed_kwargs(harness))
    assert len(harness.planner_calls) == 1
    assert harness.session.rollback_count == 1
    record = await harness.repository.get(
        artifact_kind=AuditArtifactKind.PLANNING_UTILITY_OBSERVATION,
        artifact_id=first.registration.observation.observation_id,
    )
    assert record.content_hash == first.registration.observation.content_hash


@pytest.mark.asyncio
async def test_evidence_persistence_cannot_predate_its_materialization(monkeypatch):
    harness = observed_harness(monkeypatch)
    key = (harness.source_record.artifact_kind, harness.source_record.artifact_id)
    harness.repository.records[key] = replace(harness.source_record, persisted_at=dt(9))
    with pytest.raises(ValueError, match="persistence predates"):
        await observed_run.make_observed_planner_run(**observed_kwargs(harness))
    assert harness.events == ["rollback"]
    assert harness.planner_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("authority", (True, None))
async def test_true_or_unknown_evidence_planning_authority_fails_closed(monkeypatch, authority):
    harness = observed_harness(monkeypatch)
    bad = replace(harness.source, planning_authorized=authority)
    monkeypatch.setattr(
        registration,
        "restore_prospective_validation_evidence_audit_artifact",
        lambda record: bad,
    )
    with pytest.raises(ValueError, match="unsupported stronger authority"):
        await observed_run.make_observed_planner_run(**observed_kwargs(harness))
    assert harness.events == ["rollback"]
    assert harness.planner_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "problem",
    ("different_session", "unbound_repository", "active_transaction", "unknown_state", "missing_api"),
)
async def test_session_ownership_guard_fails_before_audit_reads(monkeypatch, problem):
    harness = observed_harness(monkeypatch)
    if problem == "different_session":
        harness.repository.session = FakeSession()
    elif problem == "unbound_repository":
        del harness.repository.session
    elif problem == "active_transaction":
        harness.session.transaction_active = True
    elif problem == "unknown_state":
        harness.session.transaction_active = None
    else:
        harness.session.in_transaction = None
    with pytest.raises(registration.PlanningUtilityObservationError):
        await observed_run.make_observed_planner_run(**observed_kwargs(harness))
    assert harness.events == []
    assert harness.planner_calls == []
    assert harness.session.commit_count == 0
    assert harness.session.rollback_count == 0


@pytest.mark.asyncio
async def test_commit_that_keeps_transaction_open_prevents_planner(monkeypatch):
    harness = observed_harness(monkeypatch)

    async def skipped_commit():
        harness.events.append("commit_skipped")

    monkeypatch.setattr(harness.session, "commit", skipped_commit)
    with pytest.raises(registration.PlanningUtilityObservationError, match="left an active"):
        await observed_run.make_observed_planner_run(**observed_kwargs(harness))
    assert harness.events == ["save", "commit_skipped", "rollback"]
    assert harness.planner_calls == []
    assert harness.session.in_transaction() is False
