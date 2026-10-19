from contextlib import nullcontext
from datetime import date, datetime, timezone
import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Column, MetaData, Table, Uuid, create_engine, event, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.planning.application.plan_adoption import (
    PlanAdoptionStatus,
    adopt_with_repository,
    evaluate_current_state_adoption,
    prepare_current_state_adoption,
)
from app.planning.domain.common.serialization import canonical_json, compute_content_hash
from app.planning.domain.integration.models import finalize_existing_workout_plan_capture
from app.planning.domain.integration.polar_reconciliation import (
    FutureBaselineAdoptionSupport,
    POLAR_RECONCILIATION_HASH_EXCLUDE_FIELDS,
    PolarReconciliationStatus,
    PolarSourceReconciliationArtifact,
)
from app.planning.domain.plan_revision.reconciliation_audit import (
    PolarReconciliationAuditRecord,
    finalize_polar_reconciliation_audit,
)
from app.planning.domain.plan_revision.persistence_contract import (
    finalize_authoritative_plan_identity,
)
from app.planning.infrastructure.persistence.sqlalchemy_models import (
    PlanningPlanRevisionReconciliationAuditRow,
)
from app.planning.infrastructure.repositories.postgres_plan_reconciliation_audit import (
    SqlAlchemyPlanReconciliationAuditRepository,
)


UTC = timezone.utc
NOW = datetime(2026, 10, 18, 5, 0, tzinfo=UTC)
API_ROOT = Path(__file__).resolve().parents[2]


def capture(*, contract_start="2026-10-18T05:00:00+00:00", snapshot_start=None):
    plan = {
        "contract_type": "WorkoutPlanContract",
        "schema_version": "0.1",
        "plan_id": "polar-target:123:a01:hash",
        "plan_revision": 1,
        "athlete_id": "athlete-1",
        "planned_date": "2026-10-18",
        "planned_start_time": contract_start,
        "sport": "KAYAK",
        "session_type": "UNKNOWN",
        "title": "Polar current state",
        "description": None,
        "blocks": [{"block_id": "polar-block:one"}],
        "evidence": [],
    }
    source = {"status": "PLAN_CONTRACT_READ_WITH_LIMITATIONS", "adapter_result": {"plan": plan}}
    if snapshot_start is not None:
        source["source_snapshot"] = {"planned_start_time": snapshot_start}
    source_json = canonical_json(source)
    source_hash = compute_content_hash(source, exclude_fields=frozenset())
    return finalize_existing_workout_plan_capture(
        api_rules_version="plan-contract-read-api-0.1-draft1",
        contract_release="DRAFT1",
        capture_id="capture-polar-1",
        captured_at=NOW,
        source_workout_id="workout-1",
        athlete_id="athlete-1",
        source_kind="STORED_POLAR_TARGET",
        source_content_sha256="a" * 64,
        planning_logical_plan_id="planned-workout:workout-1",
        external_contract_plan_id=plan["plan_id"],
        external_contract_plan_revision=1,
        external_contract_schema_version="0.1",
        external_plan_content_hash="b" * 64,
        external_contract_snapshot_sha256="c" * 64,
        external_adapter_version="legacy-plan-adapter-0.1-draft1",
        contract_block_ids=("polar-block:one",),
        external_occurrence_ids=("external-occurrence-1",),
        source_limitations=("HISTORICAL_PLAN_CONTENT_UNVERIFIED",),
        provider_orm_basic_field_differences=(),
        source_read_json=source_json,
        source_read_content_hash=source_hash,
    )


def reconciliation(cap, *, compared_fields=("/title",)):
    provisional = PolarSourceReconciliationArtifact(
        schema_version="0.2",
        rules_version="polar-source-reconciliation-0.2",
        capture_id=cap.capture_id,
        captured_at=cap.captured_at,
        logical_plan_id=cap.planning_logical_plan_id,
        athlete_id=cap.athlete_id,
        source_workout_id=cap.source_workout_id,
        source_content_sha256=cap.source_content_sha256,
        source_read_content_hash=cap.source_read_content_hash,
        external_contract_plan_id=cap.external_contract_plan_id,
        external_contract_plan_revision=cap.external_contract_plan_revision,
        timezone_context_name="Europe/Budapest",
        timezone_context_source="CURRENT_USER_PROFILE",
        status=PolarReconciliationStatus.SYNC_PROJECTION_MATCH,
        future_baseline_adoption_support=(
            FutureBaselineAdoptionSupport.SUPPORTED_BY_RECONCILIATION
        ),
        semantic_equivalence_claimed=False,
        current_orm_edit_detected=False,
        provider_snapshot_selected_as_future_authority_candidate=True,
        adoption_gate_integrated=False,
        compared_fields=compared_fields,
        differences=(),
        normalization_notes=("TEST",),
        excluded_fields=("/status",),
        blockers=(),
        content_hash_algorithm="sha256-canonical-json-v0.1",
        content_hash="",
    )
    digest = compute_content_hash(
        provisional,
        exclude_fields=POLAR_RECONCILIATION_HASH_EXCLUDE_FIELDS,
    )
    return PolarSourceReconciliationArtifact(
        **{**provisional.__dict__, "content_hash": digest}
    )


def ids():
    values = iter(["revision", "occurrence"])
    return lambda: next(values)


def test_reconciled_current_start_is_promoted_into_authoritative_baseline():
    cap = capture(
        contract_start=None,
        snapshot_start="2026-10-18T05:00:00+00:00",
    )
    artifact = reconciliation(
        cap,
        compared_fields=("/title", "/planned_start_utc"),
    )

    prepared = prepare_current_state_adoption(
        capture=cap,
        authority_established_at=NOW,
        polar_reconciliation=artifact,
        polar_reconciliation_audit_persistence_ready=True,
        id_factory=ids(),
    )

    contract = json.loads(prepared.revision.canonical_contract_json)
    assert contract["planned_start_time"] == "2026-10-18T05:00:00+00:00"


def test_current_start_is_not_promoted_without_explicit_time_reconciliation():
    cap = capture(
        contract_start=None,
        snapshot_start="2026-10-18T05:00:00+00:00",
    )
    artifact = reconciliation(cap)

    prepared = prepare_current_state_adoption(
        capture=cap,
        authority_established_at=NOW,
        polar_reconciliation=artifact,
        polar_reconciliation_audit_persistence_ready=True,
        id_factory=ids(),
    )

    contract = json.loads(prepared.revision.canonical_contract_json)
    assert contract["planned_start_time"] is None

def test_migration_extends_current_single_head_without_sibling_branch():
    scripts = ScriptDirectory.from_config(Config(str(API_ROOT / "alembic.ini")))

    assert scripts.get_heads() == ["e2a7c4b9d310"]

    current = scripts.get_revision("e2a7c4b9d310")
    assert current is not None
    assert current.down_revision == "f14c7b2e9d01"
    assert scripts.get_revision("f14c7b2e9d01").down_revision == "da7e4c92b610"
    assert scripts.get_revision("da7e4c92b610").down_revision == "c91f7a3e2d40"


def test_polar_match_becomes_ready_only_when_audit_persistence_is_available():
    cap = capture()
    artifact = reconciliation(cap)
    blocked = evaluate_current_state_adoption(
        capture=cap,
        existing_plan=None,
        polar_reconciliation=artifact,
    )
    assert blocked.status == PlanAdoptionStatus.NOT_ELIGIBLE
    assert blocked.blockers == ("POLAR_RECONCILIATION_AUDIT_PERSISTENCE_REQUIRED",)

    ready = evaluate_current_state_adoption(
        capture=cap,
        existing_plan=None,
        polar_reconciliation=artifact,
        polar_reconciliation_audit_persistence_ready=True,
    )
    assert ready.status == PlanAdoptionStatus.READY
    assert ready.baseline_adoption_allowed is True
    assert ready.polar_reconciliation_gate_satisfied is True
    assert ready.polar_reconciliation_audit_persistence_ready is True
    assert ready.blockers == ()


def test_prepared_polar_adoption_contains_separate_hash_verified_audit_record():
    cap = capture()
    artifact = reconciliation(cap)
    prepared = prepare_current_state_adoption(
        capture=cap,
        authority_established_at=NOW,
        polar_reconciliation=artifact,
        polar_reconciliation_audit_persistence_ready=True,
        id_factory=ids(),
    )
    audit = prepared.polar_reconciliation_audit
    assert isinstance(audit, PolarReconciliationAuditRecord)
    assert audit.revision_id == prepared.revision.revision_id
    assert audit.reconciliation_content_hash == artifact.content_hash
    assert audit.source_content_sha256 == cap.source_content_sha256
    assert audit.timezone_context_name == "Europe/Budapest"
    assert audit.verify_reconciliation_artifact_hash()
    assert audit.verify_content_hash()


class FakePlanRepo:
    def __init__(self):
        self.plan = None
        self.adoptions = []

    async def get_plan(self, *, logical_plan_id):
        return self.plan

    async def adopt_current_state(self, *, binding, revision):
        self.adoptions.append((binding, revision))
        self.plan = finalize_authoritative_plan_identity(
            logical_plan_id=revision.logical_plan_id,
            athlete_id=revision.athlete_id,
            source_workout_id=binding.source_workout_id,
            current_revision_id=revision.revision_id,
            current_revision_number=1,
            authority_established_at=revision.authority_established_at,
        )
        return self.plan


class FakeAuditRepo:
    def __init__(self, *, fail=False):
        self.records = []
        self.fail = fail

    async def persist_polar_audit(self, *, record):
        if self.fail:
            raise RuntimeError("audit write failed")
        self.records.append(record)
        return record


class FakeSession:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


@pytest.mark.asyncio
async def test_polar_adoption_persists_revision_and_audit_before_single_commit():
    cap = capture()
    plan_repo = FakePlanRepo()
    audit_repo = FakeAuditRepo()
    session = FakeSession()
    result = await adopt_with_repository(
        capture=cap,
        expected_source_content_sha256=cap.source_content_sha256,
        repository=plan_repo,
        reconciliation_audit_repository=audit_repo,
        session=session,
        authority_established_at=NOW,
        polar_reconciliation=reconciliation(cap),
        id_factory=ids(),
    )
    assert result.status == PlanAdoptionStatus.ADOPTED
    assert len(plan_repo.adoptions) == 1
    assert len(audit_repo.records) == 1
    assert result.polar_reconciliation_audit == audit_repo.records[0]
    assert session.commits == 1
    assert session.rollbacks == 0


@pytest.mark.asyncio
async def test_audit_failure_rolls_back_transaction_and_never_commits():
    cap = capture()
    plan_repo = FakePlanRepo()
    session = FakeSession()
    with pytest.raises(RuntimeError, match="audit write failed"):
        await adopt_with_repository(
            capture=cap,
            expected_source_content_sha256=cap.source_content_sha256,
            repository=plan_repo,
            reconciliation_audit_repository=FakeAuditRepo(fail=True),
            session=session,
            authority_established_at=NOW,
            polar_reconciliation=reconciliation(cap),
            id_factory=ids(),
        )
    assert session.commits == 0
    assert session.rollbacks == 1


class AsyncSQLiteBridge:
    def __init__(self, session):
        self.session = session

    async def execute(self, statement):
        return self.session.execute(statement)

    def add(self, row):
        self.session.add(row)

    async def flush(self):
        self.session.flush()


@pytest.fixture
def audit_db():
    from app.models import entities as _entities  # noqa: F401 - register real ORM tables

    metadata = Base.metadata
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    metadata.create_all(engine)
    athlete = uuid4()
    workout = uuid4()
    with engine.begin() as connection:
        users = metadata.tables["users"]
        user_values = {"id": athlete}
        if "email" in users.c:
            user_values["email"] = f"p1-4c-{athlete}@example.invalid"
        if "timezone" in users.c:
            user_values["timezone"] = "Europe/Budapest"
        if "created_at" in users.c:
            user_values["created_at"] = NOW
        connection.execute(users.insert().values(**user_values))

        workouts = metadata.tables["planned_workouts"]
        workout_values = {"id": workout}
        if "user_id" in workouts.c:
            workout_values["user_id"] = athlete
        if "date" in workouts.c:
            workout_values["date"] = date(2026, 10, 18)
        if "sport" in workouts.c:
            workout_values["sport"] = "KAYAK"
        if "title" in workouts.c:
            workout_values["title"] = "P1.4C audit fixture"
        if "status" in workouts.c:
            workout_values["status"] = "PLANNED"
        if "source" in workouts.c:
            workout_values["source"] = "TEST"
        if "created_at" in workouts.c:
            workout_values["created_at"] = NOW
        if "updated_at" in workouts.c:
            workout_values["updated_at"] = NOW
        connection.execute(workouts.insert().values(**workout_values))

        connection.execute(
            metadata.tables["planning_logical_plans"].insert().values(
                logical_plan_id="planned-workout:test",
                athlete_id=athlete,
                source_workout_id=workout,
                current_revision_id=None,
                current_revision_number=0,
                authority_established_at=None,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        connection.execute(
            metadata.tables["planning_plan_revisions"].insert().values(
                revision_id="pt-plan-rev:test",
                logical_plan_id="planned-workout:test",
                athlete_id=athlete,
                revision_number=1,
                previous_revision_id=None,
                origin="adopted_current_state",
                history_claim="current_state_baseline_only",
                authority_established_at=NOW,
                effective_from=NOW,
                created_at=NOW,
                contract_schema_version="0.1",
                canonical_contract_json={},
                contract_content_hash="1" * 64,
                revision_content_hash="2" * 64,
                source_capture_id="capture-test",
                source_capture_hash="3" * 64,
                source_read_content_hash="b" * 64,
                source_content_sha256="a" * 64,
                source_external_contract_plan_id="polar-target:test",
                source_external_contract_plan_revision=1,
                context_hash=None,
                decision_hash=None,
                rationale_hash=None,
                instruction_hash=None,
            )
        )

    with Session(engine, expire_on_commit=False) as sync:
        yield AsyncSQLiteBridge(sync), str(athlete), str(workout)
    engine.dispose()


@pytest.mark.asyncio
async def test_sqlalchemy_audit_repository_round_trips_immutable_payload(audit_db):
    db, athlete, workout = audit_db
    artifact_json = canonical_json({
        "schema_version": "0.2",
        "rules_version": "polar-source-reconciliation-0.2",
        "content_hash": "e" * 64,
    })
    # This repository test focuses on storage round-trip. Use a record whose
    # own audit hash is computed after substituting a hash-consistent artifact.
    artifact_value = {
        "schema_version": "0.2",
        "rules_version": "polar-source-reconciliation-0.2",
        "content_hash": "",
    }
    artifact_hash = compute_content_hash(artifact_value, exclude_fields=frozenset({"content_hash"}))
    artifact_value["content_hash"] = artifact_hash
    artifact_json = canonical_json(artifact_value)
    provisional = PolarReconciliationAuditRecord(
        audit_schema_version="0.1",
        revision_id="pt-plan-rev:test",
        logical_plan_id="planned-workout:test",
        athlete_id=athlete,
        source_workout_id=workout,
        capture_id="capture-test",
        reconciliation_schema_version="0.2",
        reconciliation_rules_version="polar-source-reconciliation-0.2",
        reconciliation_content_hash_algorithm="sha256-canonical-json-v0.1",
        reconciliation_content_hash=artifact_hash,
        reconciliation_canonical_json=artifact_json,
        reconciliation_captured_at=NOW,
        source_content_sha256="a" * 64,
        source_read_content_hash="b" * 64,
        timezone_context_name="Europe/Budapest",
        timezone_context_source="CURRENT_USER_PROFILE",
        reconciliation_status="sync_projection_match",
        created_at=NOW,
        content_hash_algorithm="sha256-canonical-json-v0.1",
        content_hash="",
    )
    record = PolarReconciliationAuditRecord(
        **{
            **provisional.__dict__,
            "content_hash": compute_content_hash(provisional),
        }
    )
    repo = SqlAlchemyPlanReconciliationAuditRepository(db)
    await repo.persist_polar_audit(record=record)
    loaded = await repo.get_polar_audit(revision_id=record.revision_id)
    assert loaded == record
    assert loaded.verify_content_hash()
    assert loaded.verify_reconciliation_artifact_hash()
