"""Real HTTP graph and production adapters on isolated SQLite via async bridge."""

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select, update
from sqlalchemy.orm import Session

from app.api.routes import planning_goals as module
from app.db.base import Base
from app.models.entities import (
    Assessment,
    Measurement,
    ObjectiveType,
    PeriodType,
    PhysiologicalMeasurement,
    TrainingPeriod,
    TrainingPeriodObjective,
    User,
)
from app.planning.domain.common.serialization import canonical_json
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from tests.planning.test_p2_4a2_planning_utility_storage import AsyncSQLiteBridge
from tests.planning.test_p2_4c1_goal_protocol import (
    ATHLETE,
    NOW,
    macro_proposal,
    meso_proposal,
    sources,
)
from tests.planning.test_p2_4c3_goal_measurement import proposal_for

BASE = "/api/v1/planning/goals"
OWNER_EMAIL = "goal-api-owner@example.invalid"
OTHER_EMAIL = "goal-api-other@example.invalid"
OTHER = str(UUID(int=888))


class Clock:
    def __init__(self):
        self.current = NOW

    def tick(self):
        self.current += timedelta(microseconds=1)
        return self.current

    def sql_time(self):
        return self.tick().strftime("%Y-%m-%d %H:%M:%S.%f")


@pytest.fixture
def environment(tmp_path, monkeypatch):
    clock = Clock()
    path = (tmp_path / "goal-workflow-http.sqlite3").as_posix()
    engine = create_engine("sqlite+pysqlite:///" + path, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def configure(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.create_function("current_timestamp", 0, clock.sql_time)

    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            TrainingPeriod.__table__,
            TrainingPeriodObjective.__table__,
            PlanningAuditArtifactRow.__table__,
            Assessment.__table__,
            Measurement.__table__,
            PhysiologicalMeasurement.__table__,
        ],
    )
    with Session(engine) as sync:
        sync.add_all(
            [
                User(
                    id=UUID(ATHLETE), email=OWNER_EMAIL, timezone="Europe/Budapest", created_at=NOW
                ),
                User(id=UUID(OTHER), email=OTHER_EMAIL, timezone="Europe/Budapest", created_at=NOW),
            ]
        )
        sync.flush()
        for node in sources().hierarchy + sources().mesocycles:
            row = TrainingPeriod(
                id=UUID(node.period_id),
                user_id=UUID(ATHLETE),
                parent_id=UUID(node.parent_id) if node.parent_id else None,
                period_type=PeriodType(node.period_type.value),
                title=node.title,
                start_date=datetime.fromisoformat(node.start_date).date(),
                end_date=datetime.fromisoformat(node.end_date).date(),
                extra_data={},
            )
            sync.add(row)
            sync.flush()
            for objective in node.legacy_objectives:
                sync.add(
                    TrainingPeriodObjective(
                        period_id=row.id,
                        objective_type=ObjectiveType(objective.objective_type),
                        weight=float(objective.weight),
                    )
                )
        sync.commit()
    env = SimpleNamespace(engine=engine, clock=clock, email=OWNER_EMAIL, requests=[])
    monkeypatch.setattr(module, "get_settings", lambda: SimpleNamespace(demo_user_email=env.email))
    for service in (module.goals, module.measurements, module.assessments):
        monkeypatch.setattr(service, "_utc_now", clock.tick)
    monkeypatch.setattr(module, "_now", clock.tick)

    def dependency():
        with Session(engine, expire_on_commit=False) as sync:
            bridge = AsyncSQLiteBridge(sync)
            env.requests.append(bridge)
            yield bridge

    app = FastAPI()
    app.include_router(module.router, prefix="/api/v1")
    app.dependency_overrides[module.get_db] = dependency
    env.app = app
    with TestClient(app) as client:
        env.client = client
        yield env
    engine.dispose()


def count(env, model):
    with Session(env.engine) as sync:
        return sync.scalar(select(func.count()).select_from(model))


def post(env, resource, payload, expected=201):
    response = env.client.post(BASE + "/" + resource, json=payload)
    assert response.status_code == expected, response.text
    assert response.headers["Cache-Control"] == "no-store"
    return response.json()


def register_protocol(env):
    macro_input = json.loads(canonical_json(macro_proposal()))
    macro = post(env, "macrocycle-plans", macro_input)
    from app.planning.domain.goals.protocol import MacrocycleCapabilityPlan
    from app.planning.domain.planning_utility.decision_binding import restore_utility_contract

    macro_artifact = restore_utility_contract(
        canonical_json(macro["artifact"]), MacrocycleCapabilityPlan
    )
    proposal = json.loads(canonical_json(meso_proposal(macro_artifact)))
    for endpoint in proposal["endpoints"]:
        endpoint["change_requirement"]["measurement_error_estimate"] = "0"
        endpoint["change_requirement"]["measurement_error_source"] = (
            "synthetic:zero-error-assumption"
        )
    protocol = post(env, "mesocycle-protocols", proposal)
    return macro_input, macro, proposal, protocol


def measurement_payload(protocol, *, index=0, value="50", request_id=9001, followup=False):
    from app.planning.domain.goals.protocol import MesocycleGoalProtocol
    from app.planning.domain.planning_utility.decision_binding import restore_utility_contract

    artifact = restore_utility_contract(canonical_json(protocol["artifact"]), MesocycleGoalProtocol)
    if index:
        # Select a helper endpoint, retaining the actual parent identity/hash.
        from dataclasses import replace

        artifact = replace(
            artifact,
            proposal=replace(artifact.proposal, endpoints=(artifact.proposal.endpoints[index],)),
        )
    return json.loads(
        canonical_json(
            proposal_for(
                artifact,
                client_request_id=str(UUID(int=request_id)),
                value=value,
                followup=followup,
            )
        )
    )


def test_complete_http_workflow_through_registration_measurements_and_assessment(environment):
    env = environment
    _, macro, _, protocol = register_protocol(env)
    assert macro["measurement_schedule_preregistered"] is False
    assert protocol["measurement_schedule_preregistered"] is True
    recorded = []
    for followup in (False, True):
        env.clock.current = datetime(2030, 1, 25 if followup else 2, 9, 20, tzinfo=UTC)
        for index, endpoint in enumerate(protocol["artifact"]["proposal"]["endpoints"]):
            value = (
                "5"
                if endpoint["metric_key"] == "TECHNICAL_ERROR_COUNT"
                else ("55" if followup else "50")
            )
            payload = measurement_payload(
                protocol,
                index=index,
                value=value,
                request_id=1000 + index + 10 * int(followup),
                followup=followup,
            )
            recorded.append(post(env, "measurements", payload))
    assert count(env, Measurement) == count(env, Assessment) == 8
    env.clock.current = datetime(2030, 1, 27, 12, tzinfo=UTC)
    request = {
        "protocol_reference": {
            "artifact_id": protocol["artifact"]["artifact_id"],
            "content_hash": protocol["artifact"]["content_hash"],
        },
        "activity_cutoff_at": "2030-01-27T11:00:00Z",
    }
    result = post(env, "assessments", request)
    assert result["artifact"]["all_primary_criteria_status"] == "met_under_declared_error"
    assert len(result["artifact"]["census"]["sources"]) == 8
    assert result["artifact"]["source_availability_at_activity_cutoff_verified"] is False
    assert result["planning_authorized"] is result["physiological_adaptation_established"] is False
    repeated = post(env, "assessments", request, expected=200)
    assert repeated["artifact"] == result["artifact"]
    for resource, item in (
        ("macrocycle-plans", macro),
        ("mesocycle-protocols", protocol),
        ("measurements", recorded[0]),
        ("assessments", result),
    ):
        detail = env.client.get(BASE + "/" + resource + "/" + item["artifact"]["artifact_id"])
        assert detail.status_code == 200, detail.text
        assert detail.json()["artifact"] == item["artifact"]
        listed = env.client.get(BASE + "/" + resource)
        assert listed.status_code == 200, listed.text
        assert listed.json()["items"]
    assert all(bridge.in_transaction() is False for bridge in env.requests)


def test_plan_protocol_and_measurement_retries_are_idempotent(environment):
    env = environment
    macro_input, macro, proposal, protocol = register_protocol(env)
    assert post(env, "macrocycle-plans", macro_input, expected=200)["artifact"] == macro["artifact"]
    assert (
        post(env, "mesocycle-protocols", proposal, expected=200)["artifact"] == protocol["artifact"]
    )
    env.clock.current = datetime(2030, 1, 2, 9, 20, tzinfo=UTC)
    payload = measurement_payload(protocol)
    first = post(env, "measurements", payload)
    repeated = post(env, "measurements", payload, expected=200)
    assert repeated["artifact"] == first["artifact"]
    assert repeated["reused"] is True
    assert count(env, Measurement) == count(env, Assessment) == 1
    changed = deepcopy(payload)
    changed["value"] = "51"
    response = env.client.post(BASE + "/measurements", json=changed)
    assert response.status_code == 409
    assert count(env, Measurement) == 1


def test_catalogue_and_openapi_expose_the_workflow_and_strict_input_fields(environment):
    env = environment
    catalog = env.client.get(BASE + "/catalog")
    assert catalog.status_code == 200
    assert len(catalog.json()["capabilities"]) == 13
    assert len(catalog.json()["metrics"]) == 25
    assert len(catalog.json()["goal_roles"]) == 4
    assert env.requests == []
    schema = env.client.get("/openapi.json").json()
    assert sum(len(v) for k, v in schema["paths"].items() if k.startswith(BASE)) == 13
    assert schema["components"]["schemas"]["GoalMeasurementInput"]["additionalProperties"] is False
    properties = schema["components"]["schemas"]["GoalMeasurementInput"]["properties"]
    assert not {"athlete_id", "metric_key", "procedure", "planning_authorized"}.intersection(
        properties
    )


@pytest.mark.parametrize(
    "resource", ("macrocycle-plans", "mesocycle-protocols", "measurements", "assessments")
)
def test_lists_are_read_only_and_do_not_create_an_unconfigured_owner(environment, resource):
    env = environment
    before = count(env, User)
    env.email = "missing-goal-owner@example.invalid"
    response = env.client.get(BASE + "/" + resource)
    assert response.status_code == 404
    assert count(env, User) == before
    assert count(env, PlanningAuditArtifactRow) == 0


def test_other_owner_cannot_read_or_use_another_athletes_profile(environment):
    env = environment
    macro_input, macro, proposal, protocol = register_protocol(env)
    env.email = OTHER_EMAIL
    assert env.client.get(BASE + "/macrocycle-plans").json()["items"] == []
    for resource, artifact in (("macrocycle-plans", macro), ("mesocycle-protocols", protocol)):
        assert (
            env.client.get(
                BASE + "/" + resource + "/" + artifact["artifact"]["artifact_id"]
            ).status_code
            == 404
        )
    assert env.client.post(BASE + "/macrocycle-plans", json=macro_input).status_code == 404
    assert env.client.post(BASE + "/mesocycle-protocols", json=proposal).status_code == 404
    assert (
        env.client.post(BASE + "/measurements", json=measurement_payload(protocol)).status_code
        == 404
    )
    assert count(env, Measurement) == 0


@pytest.mark.parametrize(
    "field,value",
    (
        ("athlete_id", OTHER),
        ("planning_authorized", True),
        ("revision", True),
        ("revision", "1"),
        ("goals", []),
    ),
)
def test_invalid_plan_requests_have_no_writes(environment, field, value):
    env = environment
    payload = json.loads(canonical_json(macro_proposal()))
    payload[field] = value
    assert env.client.post(BASE + "/macrocycle-plans", json=payload).status_code == 422
    assert count(env, PlanningAuditArtifactRow) == 0


@pytest.mark.parametrize(
    "field,value",
    (
        ("athlete_id", OTHER),
        ("metric_key", "STRENGTH_1RM"),
        ("value", 50),
        ("value", "50.0"),
        ("execution_details_independently_verified", True),
    ),
)
def test_invalid_measurement_requests_have_no_source_or_audit_writes(environment, field, value):
    env = environment
    _, _, _, protocol = register_protocol(env)
    payload = measurement_payload(protocol)
    payload[field] = value
    assert env.client.post(BASE + "/measurements", json=payload).status_code == 422
    assert count(env, Measurement) == count(env, Assessment) == 0
    assert count(env, PlanningAuditArtifactRow) == 2


@pytest.mark.parametrize(
    "query", ("athlete_id=other", "limit=1&limit=2", "limit=0", "limit=51", "offset=-1")
)
def test_unknown_duplicate_and_out_of_bounds_query_fields_are_rejected(environment, query):
    response = environment.client.get(BASE + "/macrocycle-plans?" + query)
    assert response.status_code == 422


def test_actual_stream_size_limit_applies_without_a_content_length_header(environment, monkeypatch):
    env = environment
    monkeypatch.setattr(module, "GOAL_HTTP_BODY_LIMIT", 100)
    response = env.client.post(
        BASE + "/macrocycle-plans",
        content=iter([b"{" * 60, b"}" * 60]),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert env.requests == []


def test_list_pagination_does_not_hide_more_rows(environment):
    env = environment
    macro_input, _, _, _ = register_protocol(env)
    first = env.client.get(BASE + "/macrocycle-plans").json()["items"][0]
    proposal = deepcopy(macro_input)
    proposal["revision"] = 2
    proposal["supersedes"] = {
        "artifact_id": first["artifact"]["artifact_id"],
        "content_hash": first["artifact"]["content_hash"],
    }
    post(env, "macrocycle-plans", proposal)
    page1 = env.client.get(BASE + "/macrocycle-plans?limit=1").json()
    page2 = env.client.get(BASE + "/macrocycle-plans?limit=1&offset=1").json()
    assert page1["has_more"] is True and page2["has_more"] is False
    assert (
        page1["items"][0]["artifact"]["artifact_id"] != page2["items"][0]["artifact"]["artifact_id"]
    )


def test_tampered_stored_protocol_returns_integrity_conflict(environment):
    env = environment
    _, _, _, protocol = register_protocol(env)
    with Session(env.engine) as writer:
        writer.execute(
            update(PlanningAuditArtifactRow)
            .where(PlanningAuditArtifactRow.artifact_id == protocol["artifact"]["artifact_id"])
            .values(content_hash="0" * 64)
        )
        writer.commit()
    response = env.client.get(BASE + "/mesocycle-protocols/" + protocol["artifact"]["artifact_id"])
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "GOAL_CONTRACT_REJECTED"


@pytest.mark.parametrize("mode", ("fail", "skip", "uncertain"))
def test_measurement_commit_failures_are_atomic_and_uncertain_commit_is_recoverable(
    environment, monkeypatch, mode
):
    env = environment
    _, _, _, protocol = register_protocol(env)
    env.clock.current = datetime(2030, 1, 2, 9, 20, tzinfo=UTC)
    payload = measurement_payload(protocol)
    original = AsyncSQLiteBridge.commit

    async def failing_commit(bridge):
        if mode == "fail":
            raise RuntimeError("synthetic commit failure")
        if mode == "skip":
            return
        await original(bridge)
        raise RuntimeError("synthetic disconnect after commit")

    monkeypatch.setattr(AsyncSQLiteBridge, "commit", failing_commit)
    response = env.client.post(BASE + "/measurements", json=payload)
    assert response.status_code in {409, 503}, response.text
    expected_sources = 1 if mode == "uncertain" else 0
    assert count(env, Measurement) == count(env, Assessment) == expected_sources
    assert count(env, PlanningAuditArtifactRow) == 2 + expected_sources
    monkeypatch.setattr(AsyncSQLiteBridge, "commit", original)
    retry = post(env, "measurements", payload, expected=200 if mode == "uncertain" else 201)
    assert retry["committed"] is True
    assert retry["reused"] is (mode == "uncertain")
    assert count(env, Measurement) == count(env, Assessment) == 1


@pytest.mark.parametrize(
    "problem", ("no_source_write", "changed_value", "bad_audit_result", "missing_database_time")
)
def test_readback_rejects_incomplete_or_changed_atomic_persistence(
    environment, monkeypatch, problem
):
    env = environment
    _, _, _, protocol = register_protocol(env)
    env.clock.current = datetime(2030, 1, 2, 9, 20, tzinfo=UTC)
    payload = measurement_payload(protocol)
    if problem in {"no_source_write", "changed_value"}:
        original = module.SqlAlchemyGoalMeasurementWriter.save

        async def changed(writer, artifact):
            if problem == "no_source_write":
                return
            await original(writer, artifact)
            await writer.session.execute(
                update(Measurement)
                .where(Measurement.id == UUID(artifact.measurement_id))
                .values(value_float=999)
            )

        monkeypatch.setattr(module.SqlAlchemyGoalMeasurementWriter, "save", changed)
    elif problem == "bad_audit_result":
        from dataclasses import replace

        original = module.SqlAlchemyPlanningAuditRepository.save

        async def changed(repository, record):
            result = await original(repository, record)
            return replace(result, content_hash="0" * 64)

        monkeypatch.setattr(module.SqlAlchemyPlanningAuditRepository, "save", changed)
    else:
        from dataclasses import replace

        original = module.SqlAlchemyPlanningAuditRepository.get

        async def changed(repository, **kwargs):
            record = await original(repository, **kwargs)
            if record and record.artifact_kind == module.measurements.MEASUREMENT_KIND:
                return replace(record, persisted_at=None)
            return record

        monkeypatch.setattr(module.SqlAlchemyPlanningAuditRepository, "get", changed)
    response = env.client.post(BASE + "/measurements", json=payload)
    assert response.status_code == 409, response.text
    assert count(env, Measurement) == count(env, Assessment) == 0
    assert count(env, PlanningAuditArtifactRow) == 2


def test_measurement_retry_and_history_never_repair_deleted_or_edited_source_rows(environment):
    from sqlalchemy import delete

    env = environment
    _, _, _, protocol = register_protocol(env)
    env.clock.current = datetime(2030, 1, 2, 9, 20, tzinfo=UTC)
    payload = measurement_payload(protocol)
    first = post(env, "measurements", payload)
    with Session(env.engine) as writer:
        writer.execute(delete(Measurement))
        writer.execute(delete(Assessment))
        writer.commit()
    retry = post(env, "measurements", payload, expected=200)
    detail = env.client.get(BASE + "/measurements/" + first["artifact"]["artifact_id"])
    assert retry["artifact"] == first["artifact"] == detail.json()["artifact"]
    assert retry["artifact"]["source_rows_immutable"] is False
    assert count(env, Measurement) == count(env, Assessment) == 0


def test_profile_retries_keep_frozen_inputs_after_current_period_ownership_changes(environment):
    env = environment
    macro_input, macro, proposal, protocol = register_protocol(env)
    with Session(env.engine) as writer:
        writer.execute(
            update(TrainingPeriod).values(user_id=UUID(OTHER), title="changed current source")
        )
        writer.commit()
    assert post(env, "macrocycle-plans", macro_input, expected=200)["artifact"] == macro["artifact"]
    assert (
        post(env, "mesocycle-protocols", proposal, expected=200)["artifact"] == protocol["artifact"]
    )


def test_measurement_retries_normalize_equivalent_utc_offsets(environment):
    env = environment
    _, _, _, protocol = register_protocol(env)
    env.clock.current = datetime(2030, 1, 2, 9, 20, tzinfo=UTC)
    payload = measurement_payload(protocol)
    first = post(env, "measurements", payload)
    payload["observation"]["started_at"] = "2030-01-02T10:00:00+01:00"
    payload["observation"]["ended_at"] = "2030-01-02T10:10:00+01:00"
    assert post(env, "measurements", payload, expected=200)["artifact"] == first["artifact"]


def test_future_measurement_and_future_assessment_cutoffs_have_no_writes(environment):
    env = environment
    _, _, _, protocol = register_protocol(env)
    response = env.client.post(BASE + "/measurements", json=measurement_payload(protocol))
    assert response.status_code == 409
    assessment = {
        "protocol_reference": {
            "artifact_id": protocol["artifact"]["artifact_id"],
            "content_hash": protocol["artifact"]["content_hash"],
        },
        "activity_cutoff_at": "2040-01-01T00:00:00Z",
    }
    assert env.client.post(BASE + "/assessments", json=assessment).status_code == 422
    assert (
        env.client.get(
            BASE + "/mesocycle-protocols/" + protocol["artifact"]["artifact_id"],
            params={"available_by": "2040-01-01T00:00:00Z"},
        ).status_code
        == 422
    )
    assert count(env, PlanningAuditArtifactRow) == 2
    assert count(env, Measurement) == 0


def test_registration_after_baseline_start_cannot_be_called_preregistered(environment):
    env = environment
    macro_input = json.loads(canonical_json(macro_proposal()))
    macro = post(env, "macrocycle-plans", macro_input)
    from app.planning.domain.goals.protocol import MacrocycleCapabilityPlan
    from app.planning.domain.planning_utility.decision_binding import restore_utility_contract

    artifact = restore_utility_contract(canonical_json(macro["artifact"]), MacrocycleCapabilityPlan)
    proposal = json.loads(canonical_json(meso_proposal(artifact)))
    env.clock.current = datetime(2030, 1, 2, 9, 20, tzinfo=UTC)
    assert env.client.post(BASE + "/mesocycle-protocols", json=proposal).status_code == 409
    assert count(env, PlanningAuditArtifactRow) == 1


def test_unknown_execution_condition_remains_unknown_in_the_assessment(environment):
    env = environment
    _, _, _, protocol = register_protocol(env)
    env.clock.current = datetime(2030, 1, 2, 9, 20, tzinfo=UTC)
    payload = measurement_payload(protocol)
    payload["observation"]["conditions"][0]["status"] = "unknown"
    recorded = post(env, "measurements", payload)
    assert recorded["artifact"]["execution"]["conditions"][0]["status"] == "unknown"
    env.clock.current = datetime(2030, 1, 27, 12, tzinfo=UTC)
    assessment = {
        "protocol_reference": payload["protocol_reference"],
        "activity_cutoff_at": "2030-01-27T11:00:00Z",
    }
    result = post(env, "assessments", assessment)
    endpoint = result["artifact"]["endpoint_assessments"][0]
    assert endpoint["criterion_status"] == "withheld"
    assert "BASELINE_CANDIDATE_UNRESOLVED" in endpoint["reason_codes"]


def test_source_size_limit_prevents_a_measurement_that_c2_cannot_capture(environment):
    env = environment
    macro_input = json.loads(canonical_json(macro_proposal()))
    macro = post(env, "macrocycle-plans", macro_input)
    from app.planning.domain.goals.protocol import MacrocycleCapabilityPlan
    from app.planning.domain.planning_utility.decision_binding import restore_utility_contract

    artifact = restore_utility_contract(canonical_json(macro["artifact"]), MacrocycleCapabilityPlan)
    proposal = json.loads(canonical_json(meso_proposal(artifact)))
    proposal["endpoints"][0]["procedure"]["comparability_conditions"] = [
        f"condition-{i}" for i in range(20)
    ]
    protocol = post(env, "mesocycle-protocols", proposal)
    env.clock.current = datetime(2030, 1, 2, 9, 20, tzinfo=UTC)
    payload = measurement_payload(protocol)
    for condition in payload["observation"]["conditions"]:
        condition["observation"] = "x" * 4000
    assert env.client.post(BASE + "/measurements", json=payload).status_code == 409
    assert count(env, Measurement) == count(env, Assessment) == 0


def test_read_transaction_that_does_not_close_cannot_return_a_success(environment, monkeypatch):
    env = environment

    async def skipped(bridge):
        return None

    monkeypatch.setattr(AsyncSQLiteBridge, "rollback", skipped)
    response = env.client.get(BASE + "/macrocycle-plans")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "GOAL_TRANSACTION_NOT_CLOSED"


def test_rehashed_registration_authority_forgery_is_rejected(environment):
    env = environment
    _, _, _, protocol = register_protocol(env)
    env.clock.current = datetime(2030, 1, 2, 9, 20, tzinfo=UTC)
    first = post(env, "measurements", measurement_payload(protocol))
    from dataclasses import replace

    from app.planning.domain.common.serialization import compute_content_hash
    from app.planning.domain.goals.measurement_registration import GoalMeasurementRegistration
    from app.planning.domain.goals.protocol import GOAL_HASH_EXCLUDE
    from app.planning.domain.planning_utility.decision_binding import restore_utility_contract

    artifact = restore_utility_contract(
        canonical_json(first["artifact"]), GoalMeasurementRegistration
    )
    artifact = replace(artifact, authority=replace(artifact.authority, planning_authorized=True))
    artifact = replace(
        artifact, content_hash=compute_content_hash(artifact, exclude_fields=GOAL_HASH_EXCLUDE)
    )
    with Session(env.engine) as writer:
        writer.execute(
            update(PlanningAuditArtifactRow)
            .where(PlanningAuditArtifactRow.artifact_id == artifact.artifact_id)
            .values(contract_json=canonical_json(artifact), content_hash=artifact.content_hash)
        )
        writer.commit()
    assert env.client.get(BASE + "/measurements/" + artifact.artifact_id).status_code == 409


def test_existing_scalar_identity_collision_does_not_overwrite_source_data(environment):
    from uuid import NAMESPACE_URL, uuid5

    from app.planning.domain.goals.measurement_registration import goal_measurement_id

    env = environment
    _, _, _, protocol = register_protocol(env)
    env.clock.current = datetime(2030, 1, 2, 9, 20, tzinfo=UTC)
    payload = measurement_payload(protocol)
    identity = goal_measurement_id(ATHLETE, payload["client_request_id"])
    parent_id = uuid5(NAMESPACE_URL, "paddletrainer:goal-assessment-row:" + identity)
    from app.models.entities import AssessmentType

    with Session(env.engine) as writer:
        writer.add(
            Assessment(
                id=parent_id,
                user_id=UUID(ATHLETE),
                assessment_type=AssessmentType.OTHER,
                title="Preexisting source must survive",
                performed_at=env.clock.current,
                source="MANUAL",
                extra_data={},
                created_at=env.clock.current,
            )
        )
        writer.commit()
    response = env.client.post(BASE + "/measurements", json=payload)
    assert response.status_code == 409
    with Session(env.engine) as reader:
        assert reader.get(Assessment, parent_id).title == "Preexisting source must survive"
    assert count(env, Assessment) == 1 and count(env, Measurement) == 0
    assert count(env, PlanningAuditArtifactRow) == 2


def test_other_owner_cannot_read_measurement_or_assessment_registrations(environment):
    env = environment
    _, _, _, protocol = register_protocol(env)
    env.clock.current = datetime(2030, 1, 2, 9, 20, tzinfo=UTC)
    measurement = post(env, "measurements", measurement_payload(protocol))
    env.clock.current = datetime(2030, 1, 27, 12, tzinfo=UTC)
    request = {
        "protocol_reference": {
            "artifact_id": protocol["artifact"]["artifact_id"],
            "content_hash": protocol["artifact"]["content_hash"],
        },
        "activity_cutoff_at": "2030-01-27T11:00:00Z",
    }
    assessment = post(env, "assessments", request)
    env.email = OTHER_EMAIL
    for resource, receipt in (("measurements", measurement), ("assessments", assessment)):
        assert (
            env.client.get(
                BASE + "/" + resource + "/" + receipt["artifact"]["artifact_id"]
            ).status_code
            == 404
        )
        assert env.client.get(BASE + "/" + resource).json()["items"] == []
    assert env.client.post(BASE + "/assessments", json=request).status_code == 404
    assert count(env, Measurement) == 1


def test_request_with_a_borrowed_transaction_is_rejected_without_rolling_it_back(environment):
    env = environment
    with Session(env.engine) as sync:
        bridge = AsyncSQLiteBridge(sync)
        sync.execute(select(User))
        env.app.dependency_overrides[module.get_db] = lambda: bridge
        response = env.client.get(BASE + "/macrocycle-plans")
        assert response.status_code == 409
        assert sync.in_transaction() is True
        assert bridge.rollback_count == 0


def test_new_measurement_is_rejected_if_parent_protocol_is_missing(environment):
    env = environment
    _, _, _, protocol = register_protocol(env)
    payload = measurement_payload(protocol)
    payload["protocol_reference"]["artifact_id"] = "pt-goal:" + "0" * 64
    assert env.client.post(BASE + "/measurements", json=payload).status_code == 404
    assert count(env, Measurement) == 0


def test_goal_router_is_registered_in_the_existing_production_application():
    from app.main import app

    schema = app.openapi()
    paths = [path for path in schema["paths"] if path.startswith(BASE)]
    assert len(paths) == 9
    assert sum(len(schema["paths"][path]) for path in paths) == 13
