import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import JSON, Column, MetaData, String, Table, Uuid, create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from test_environment_replay_snapshot import OWNER, capture_inputs
from test_polar_hr_acquisition_api import APIBridge
from test_training_data_readiness_audit import sources as _sources_fixture

from app.models import (
    EnvironmentReplaySnapshot,
    HeartRateTimebaseSnapshot,
    HRAcquisitionDeclaration,
)
from app.models.entities import (
    ExternalConnection,
    RouteEnvironmentEvidenceSet,
    RouteEnvironmentHydrologyMeasurement,
    RouteEnvironmentRoute,
    RouteEnvironmentSegment,
    RouteEnvironmentWeatherSample,
    User,
    WorkoutSession,
)
from app.services.environment_evidence_persistence import persist_route_environment_evidence
from app.services.environment_replay_persistence import (
    LINEAGE_TABLES,
    list_environment_replay_snapshots,
    load_environment_replay_snapshot,
    persist_environment_replay_snapshot,
)
from app.services.environment_replay_snapshot import (
    LINEAGE,
    build_environment_replay_snapshot,
    canonical_hash,
)
from app.services.hr_timebase_persistence import (
    load_current_hr_timebase_snapshots,
    persist_hr_timebase_snapshot,
)

sources = _sources_fixture
legacy_metadata = MetaData()
legacy_tables = {
    name: Table(
        table_name,
        legacy_metadata,
        Column("id", Uuid(), primary_key=True),
        Column("evidence_set_id", Uuid(), nullable=False),
        Column(LINEAGE[name][0], String(64), nullable=False),
        Column("snapshot_json", JSON, nullable=False),
    )
    for name, table_name in LINEAGE_TABLES.items()
}
SCIENTIFIC_MODELS = (
    RouteEnvironmentEvidenceSet,
    RouteEnvironmentRoute,
    RouteEnvironmentSegment,
    RouteEnvironmentWeatherSample,
    RouteEnvironmentHydrologyMeasurement,
    HeartRateTimebaseSnapshot,
    HRAcquisitionDeclaration,
)


def scientific_state(env):
    return canonical_hash(
        {
            model.__tablename__: sorted(
                [
                    {
                        c.name: str(getattr(row, c.name))
                        if isinstance(getattr(row, c.name), UUID)
                        else getattr(row, c.name)
                        for c in model.__table__.columns
                    }
                    for row in env.db.session.scalars(select(model)).all()
                ],
                key=lambda r: str(r["id"]),
            )
            for model in SCIENTIFIC_MODELS
        }
    )


@pytest.fixture
def environment(sources):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    for model in (
        User,
        ExternalConnection,
        WorkoutSession,
        *SCIENTIFIC_MODELS,
        EnvironmentReplaySnapshot,
    ):
        model.__table__.create(engine)
    legacy_metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as sync:
        user = User(id=OWNER, email="replay-owner@example.test", created_at=datetime.now(UTC))
        workout = WorkoutSession(
            id=uuid4(),
            user_id=OWNER,
            external_provider="POLAR",
            external_id="session-1",
            started_at=datetime(2026, 9, 30, 15, tzinfo=UTC),
            created_at=datetime.now(UTC),
        )
        connection = ExternalConnection(
            user_id=OWNER,
            provider="POLAR",
            access_token_encrypted="unused-private-token",
            expires_at=datetime.now(UTC) + timedelta(days=1),
            scopes=["training_sessions:read"],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        sync.add_all([user, workout, connection])
        sync.commit()
        db = APIBridge(sync)

        async def initialize():
            first = capture_inputs(sources)
            persisted = await persist_route_environment_evidence(
                db, user=user, workout_session=workout, evidence_record=first["evidence_record"]
            )
            inputs = capture_inputs(sources, evidence_id=UUID(persisted["evidence_set_id"]))
            await persist_hr_timebase_snapshot(
                db,
                inputs["hr_timebase_snapshots"][0]["snapshot"]["verification"],
                inputs["sample_session"],
                athlete_id=str(OWNER),
                session_external_id="session-1",
                sample_session_match_count=1,
            )
            inputs["hr_timebase_snapshots"] = await load_current_hr_timebase_snapshots(
                db,
                inputs["sample_session"],
                athlete_id=str(OWNER),
                session_external_id="session-1",
                sample_session_match_count=1,
            )
            for name, value in inputs["lineage"].items():
                if value is not None:
                    sync.execute(
                        legacy_tables[name]
                        .insert()
                        .values(
                            id=uuid4(),
                            evidence_set_id=UUID(inputs["evidence_set_id"]),
                            **{LINEAGE[name][0]: value[LINEAGE[name][0]], "snapshot_json": value},
                        )
                    )
            sync.commit()
            return inputs

        inputs = asyncio.run(initialize())
        yield SimpleNamespace(
            db=db, inputs=inputs, user=user, workout=workout, connection=connection
        )
    engine.dispose()


async def save(env, inputs=None):
    snapshot = build_environment_replay_snapshot(**(inputs or env.inputs))
    return await persist_environment_replay_snapshot(
        env.db, user_id=env.user.id, workout_session_id=env.workout.id, snapshot=snapshot
    )


async def load(env, identity, **changes):
    kwargs = {"user_id": env.user.id, "session_external_id": "session-1", "snapshot_id": identity}
    return await load_environment_replay_snapshot(env.db, **(kwargs | changes))


@pytest.mark.asyncio
async def test_real_database_idempotence_preserves_all_scientific_rows(environment):
    env = environment
    before, commits = scientific_state(env), env.db.commit_count
    first, second = await save(env), await save(env)
    assert first["status"] == "CREATED" and second["status"] == "ALREADY_PRESENT"
    assert first["snapshot_id"] == second["snapshot_id"] and second["round_trip_verified"] is True
    assert env.db.commit_count == commits + 1
    assert scientific_state(env) == before
    assert (await load(env, first["snapshot_id"])).snapshot_hash == first["snapshot_hash"]
    with Session(env.db.session.get_bind(), expire_on_commit=False) as sync:
        other = SimpleNamespace(**{**vars(env), "db": APIBridge(sync)})
        assert (
            await load(other, first["snapshot_id"])
        ).snapshot_json == build_environment_replay_snapshot(**env.inputs)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["owner", "session", "unknown_id"])
async def test_owned_lookup_does_not_return_another_owner_or_session(environment, change):
    first = await save(environment)
    args = {
        "owner": {"user_id": UUID(int=999)},
        "session": {"session_external_id": "other-session"},
        "unknown_id": {"snapshot_id": str(UUID(int=777))},
    }[change]
    assert await load(environment, first["snapshot_id"], **args) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        "weather",
        "hydrology",
        "wind",
        "clock",
        "geometry",
        "route",
        "segment_missing",
        "weather_link",
        "foreign_route",
        "foreign_measurement",
        "lineage_missing",
        "lineage_payload",
    ],
)
async def test_changed_database_evidence_is_rejected_before_replay(environment, mutation):
    env = environment
    first = await save(env)
    sync = env.db.session
    if mutation == "weather":
        sync.scalar(select(RouteEnvironmentWeatherSample)).air_temperature_c = 999.0
    elif mutation == "hydrology":
        sync.scalar(select(RouteEnvironmentHydrologyMeasurement)).value = 999.0
    elif mutation == "wind":
        sync.scalar(select(RouteEnvironmentSegment)).headwind_component_mps = 999.0
    elif mutation == "clock":
        sync.scalar(select(RouteEnvironmentSegment)).end_exercise_elapsed_ms = 9999
    elif mutation == "geometry":
        sync.scalar(select(RouteEnvironmentSegment)).start_latitude_deg = 0.0
    elif mutation == "route":
        sync.scalar(select(RouteEnvironmentRoute)).route_semantics = {"changed": True}
    elif mutation == "segment_missing":
        sync.delete(sync.scalar(select(RouteEnvironmentSegment)))
    elif mutation == "weather_link":
        sync.scalar(select(RouteEnvironmentSegment)).weather_sample_id = None
    elif mutation == "foreign_route":
        sync.scalar(select(RouteEnvironmentSegment)).route_evidence_id = uuid4()
    elif mutation == "foreign_measurement":
        sync.scalar(select(RouteEnvironmentSegment)).water_level_measurement_id = uuid4()
    elif mutation == "lineage_missing":
        sync.execute(legacy_tables["trusted_projection"].delete())
    else:
        sync.execute(
            legacy_tables["trusted_projection"].update().values(snapshot_json={"corrupt": True})
        )
    sync.commit()
    commits = env.db.commit_count
    with pytest.raises(ValueError, match="REPLAY_DATABASE_"):
        await load(env, first["snapshot_id"])
    assert env.db.commit_count == commits


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation", ["payload", "column_hash", "schema", "evidence_hash", "workout_owner"]
)
async def test_corrupted_capsule_or_evidence_binding_is_withheld(environment, mutation):
    env = environment
    first = await save(env)
    row = env.db.session.scalar(select(EnvironmentReplaySnapshot))
    if mutation == "payload":
        row.snapshot_json = row.snapshot_json | {"athlete_id": str(UUID(int=999))}
    elif mutation == "column_hash":
        row.snapshot_hash = "0" * 64
    elif mutation == "schema":
        row.snapshot_schema_version = "0.2"
    elif mutation == "evidence_hash":
        env.db.session.scalar(select(RouteEnvironmentEvidenceSet)).evidence_hash = "0" * 64
    else:
        env.workout.user_id = UUID(int=999)
    env.db.session.commit()
    if mutation == "workout_owner":
        assert await load(env, first["snapshot_id"]) is None
    else:
        with pytest.raises(ValueError, match="REPLAY_"):
            await load(env, first["snapshot_id"])


@pytest.mark.asyncio
async def test_new_projection_never_silently_replaces_the_pinned_old_capture(environment):
    env = environment
    first = await save(env)
    changed = deepcopy(env.inputs)
    changed["weather_source"]["metadata"]["generationtime_ms"] = 99.99
    second = await save(env, changed)
    assert first["snapshot_id"] != second["snapshot_id"]
    assert (await load(env, first["snapshot_id"])).snapshot_hash == first["snapshot_hash"]
    listed = await list_environment_replay_snapshots(
        env.db, user_id=OWNER, session_external_id="session-1", limit=1
    )
    assert (
        listed["total_count"] == 2 and listed["returned_count"] == 1 and listed["truncated"] is True
    )
    assert all("snapshot_json" not in item and "inputs" not in item for item in listed["snapshots"])


@pytest.mark.asyncio
async def test_legacy_only_evidence_explicitly_requires_capture(environment):
    result = await list_environment_replay_snapshots(
        environment.db, user_id=OWNER, session_external_id="session-1"
    )
    assert result["status"] == "CAPTURE_REQUIRED"
    assert (
        result["snapshots"] == [] and result["legacy_hash_only_snapshots_are_replayable"] is False
    )


@pytest.mark.asyncio
async def test_invalid_capture_never_inserts_or_promotes_scientific_data(environment):
    env = environment
    bad = build_environment_replay_snapshot(**env.inputs)
    bad["evidence_hash"] = "0" * 64
    before, commits = scientific_state(env), env.db.commit_count
    with pytest.raises(ValueError, match="REPLAY_"):
        await persist_environment_replay_snapshot(
            env.db, user_id=OWNER, workout_session_id=env.workout.id, snapshot=bad
        )
    assert scientific_state(env) == before and env.db.commit_count == commits
    assert env.db.session.scalars(select(EnvironmentReplaySnapshot)).all() == []


@pytest.mark.asyncio
async def test_concurrent_identical_capture_recovers_only_the_exact_existing_row(environment):
    env = environment
    first = await save(env)

    class ConcurrentBridge(APIBridge):
        hidden = False

        async def execute(self, statement):
            if not self.hidden and any(
                d.get("entity") is EnvironmentReplaySnapshot
                for d in getattr(statement, "column_descriptions", [])
            ):
                self.hidden = True
                statement = statement.where(False)
            return await super().execute(statement)

    raced = SimpleNamespace(**{**vars(env), "db": ConcurrentBridge(env.db.session)})
    second = await save(raced)
    assert second["status"] == "ALREADY_PRESENT"
    assert second["snapshot_id"] == first["snapshot_id"]
    assert len(env.db.session.scalars(select(EnvironmentReplaySnapshot)).all()) == 1
