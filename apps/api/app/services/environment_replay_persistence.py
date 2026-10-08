"""Owner-scoped immutable replay storage and verification against actual DB evidence."""

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, Uuid, column, func, select, table
from sqlalchemy.exc import IntegrityError

from app.models.entities import (
    RouteEnvironmentEvidenceSet,
    RouteEnvironmentHydrologyMeasurement,
    RouteEnvironmentRoute,
    RouteEnvironmentSegment,
    RouteEnvironmentWeatherSample,
    WorkoutSession,
)
from app.models.environment_replay_snapshot import EnvironmentReplaySnapshot
from app.services.environment_evidence_persistence import build_environment_persistence_plan
from app.services.environment_replay_snapshot import LINEAGE, verify_environment_replay_snapshot

LINEAGE_TABLES = {
    "water_identity": "route_water_environment_identity_snapshots",
    "hydrology_resolution": "route_hydrology_source_resolution_snapshots",
    "hydrology_trust": "route_hydrology_trust_decision_snapshots",
    "hydrology_relation": "route_hydrology_relation_decision_snapshots",
    "trusted_projection": "route_trusted_environment_context_snapshots",
}


async def _rows(db, model, evidence_set_id):
    return (
        (
            await db.execute(
                select(model)
                .where(model.evidence_set_id == evidence_set_id)
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )


def _same(actual, expected):
    if isinstance(expected, datetime):
        return isinstance(actual, datetime) and (
            actual if actual.tzinfo else actual.replace(tzinfo=UTC)
        ).astimezone(UTC) == (
            expected if expected.tzinfo else expected.replace(tzinfo=UTC)
        ).astimezone(UTC)
    return actual == expected


async def verify_database_environment_evidence(db, snapshot, *, user_id, workout_session_id):
    """Verify persisted normalized rows, links and pinned compact lineage before use."""
    if not verify_environment_replay_snapshot(snapshot):
        raise ValueError("REPLAY_SNAPSHOT_INTEGRITY_FAILED")
    evidence_id = UUID(snapshot["evidence_set_id"])
    evidence = (
        await db.execute(
            select(RouteEnvironmentEvidenceSet)
            .join(
                WorkoutSession, WorkoutSession.id == RouteEnvironmentEvidenceSet.workout_session_id
            )
            .where(
                RouteEnvironmentEvidenceSet.id == evidence_id,
                RouteEnvironmentEvidenceSet.user_id == user_id,
                RouteEnvironmentEvidenceSet.workout_session_id == workout_session_id,
                WorkoutSession.id == workout_session_id,
                WorkoutSession.user_id == user_id,
                WorkoutSession.external_provider == "POLAR",
                WorkoutSession.external_id == snapshot["session_external_id"],
            )
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if evidence is None or snapshot["athlete_id"] != str(user_id):
        raise ValueError("REPLAY_DATABASE_OWNER_OR_SESSION_MISMATCH")
    plan = build_environment_persistence_plan(snapshot["evidence_record"])
    if (
        plan["evidence_hash"] != snapshot["evidence_hash"]
        or evidence.evidence_hash != plan["evidence_hash"]
    ):
        raise ValueError("REPLAY_DATABASE_EVIDENCE_HASH_MISMATCH")
    for field in ("schema_version", "provider", "session_external_id", "scope"):
        if getattr(evidence, field) != plan[field]:
            raise ValueError("REPLAY_DATABASE_EVIDENCE_METADATA_MISMATCH")
    lookups = {}
    for label, model, key in (
        ("weather_samples", RouteEnvironmentWeatherSample, "source_sample_id"),
        ("hydrology_measurements", RouteEnvironmentHydrologyMeasurement, "source_measurement_id"),
    ):
        rows = await _rows(db, model, evidence_id)
        indexed = {(row.source_provider, getattr(row, key)): row for row in rows}
        expected = {(row["source_provider"], row[key]): row for row in plan[label]}
        if len(indexed) != len(rows) or indexed.keys() != expected.keys():
            raise ValueError("REPLAY_DATABASE_MEASUREMENT_SET_MISMATCH")
        for identity, expected_row in expected.items():
            row = indexed[identity]
            if any(not _same(getattr(row, field), value) for field, value in expected_row.items()):
                raise ValueError("REPLAY_DATABASE_MEASUREMENT_VALUE_MISMATCH")
        lookups[label] = {row.id: getattr(row, key) for row in rows}
    routes = await _rows(db, RouteEnvironmentRoute, evidence_id)
    indexed_routes = {row.route_key: row for row in routes}
    if len(indexed_routes) != len(routes) or indexed_routes.keys() != {
        r["route_key"] for r in plan["routes"]
    }:
        raise ValueError("REPLAY_DATABASE_ROUTE_SET_MISMATCH")
    segments = await _rows(db, RouteEnvironmentSegment, evidence_id)
    by_route = {row.id: [] for row in routes}
    for segment in segments:
        if segment.route_evidence_id not in by_route:
            raise ValueError("REPLAY_DATABASE_SEGMENT_ROUTE_LINK_MISMATCH")
        by_route[segment.route_evidence_id].append(segment)
    foreign_keys = {
        "weather_sample_key": ("weather_sample_id", "weather_samples"),
        "water_level_measurement_key": ("water_level_measurement_id", "hydrology_measurements"),
        "discharge_measurement_key": ("discharge_measurement_id", "hydrology_measurements"),
        "water_temperature_measurement_key": (
            "water_temperature_measurement_id",
            "hydrology_measurements",
        ),
    }
    for expected_route in plan["routes"]:
        row = indexed_routes[expected_route["route_key"]]
        if any(
            getattr(row, key) != value for key, value in expected_route.items() if key != "segments"
        ):
            raise ValueError("REPLAY_DATABASE_ROUTE_METADATA_MISMATCH")
        actual = {s.record_id: s for s in by_route[row.id]}
        expected = {s["record_id"]: s for s in expected_route["segments"]}
        if len(actual) != len(by_route[row.id]) or actual.keys() != expected.keys():
            raise ValueError("REPLAY_DATABASE_SEGMENT_SET_MISMATCH")
        for identity, expected_segment in expected.items():
            segment = actual[identity]
            for field, value in expected_segment.items():
                if field in foreign_keys:
                    fk, lookup = foreign_keys[field]
                    fk_value = getattr(segment, fk)
                    if fk_value is not None and fk_value not in lookups[lookup]:
                        raise ValueError("REPLAY_DATABASE_MEASUREMENT_LINK_MISMATCH")
                    stored = lookups[lookup].get(fk_value)
                else:
                    stored = getattr(segment, field)
                if not _same(stored, value):
                    raise ValueError("REPLAY_DATABASE_SEGMENT_VALUE_MISMATCH")
    for name, snapshot_value in snapshot["lineage"].items():
        if snapshot_value is None:
            continue
        hash_field, verifier = LINEAGE[name]
        if not verifier(snapshot_value):
            raise ValueError("REPLAY_LINEAGE_INTEGRITY_FAILED")
        source = table(
            LINEAGE_TABLES[name],
            column("evidence_set_id", Uuid()),
            column(hash_field),
            column("snapshot_json", JSON),
        )
        stored = (
            (
                await db.execute(
                    select(source.c.snapshot_json).where(
                        source.c.evidence_set_id == evidence_id,
                        source.c[hash_field] == snapshot_value[hash_field],
                    )
                )
            )
            .scalars()
            .all()
        )
        stored = [json.loads(item) if isinstance(item, str) else item for item in stored]
        if len(stored) != 1 or stored[0] != snapshot_value or not verifier(stored[0]):
            raise ValueError("REPLAY_DATABASE_LINEAGE_MISSING_OR_CHANGED")


def _statement(user_id, session_external_id):
    return (
        select(EnvironmentReplaySnapshot)
        .join(
            RouteEnvironmentEvidenceSet,
            RouteEnvironmentEvidenceSet.id == EnvironmentReplaySnapshot.evidence_set_id,
        )
        .join(WorkoutSession, WorkoutSession.id == EnvironmentReplaySnapshot.workout_session_id)
        .where(
            EnvironmentReplaySnapshot.user_id == user_id,
            WorkoutSession.user_id == user_id,
            RouteEnvironmentEvidenceSet.user_id == user_id,
            RouteEnvironmentEvidenceSet.workout_session_id == WorkoutSession.id,
            WorkoutSession.external_provider == "POLAR",
            WorkoutSession.external_id == session_external_id,
            RouteEnvironmentEvidenceSet.provider == "POLAR",
            RouteEnvironmentEvidenceSet.session_external_id == session_external_id,
        )
        .execution_options(populate_existing=True)
    )


def _check_row(row, user_id, session_external_id):
    payload = row.snapshot_json
    if (
        not verify_environment_replay_snapshot(payload)
        or row.snapshot_hash != payload["snapshot_hash"]
        or row.snapshot_schema_version != payload["snapshot_schema_version"]
        or str(row.evidence_set_id) != payload["evidence_set_id"]
        or payload["athlete_id"] != str(user_id)
        or payload["session_external_id"] != session_external_id
    ):
        raise ValueError("REPLAY_STORED_SNAPSHOT_BINDING_FAILED")


async def load_environment_replay_snapshot(db, *, user_id, session_external_id, snapshot_id):
    row = (
        await db.execute(
            _statement(user_id, session_external_id).where(
                EnvironmentReplaySnapshot.id == UUID(str(snapshot_id))
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    _check_row(row, user_id, session_external_id)
    await verify_database_environment_evidence(
        db, row.snapshot_json, user_id=user_id, workout_session_id=row.workout_session_id
    )
    return row


async def persist_environment_replay_snapshot(db, *, user_id, workout_session_id, snapshot):
    user_id, workout_session_id = UUID(str(user_id)), UUID(str(workout_session_id))
    await verify_database_environment_evidence(
        db, snapshot, user_id=user_id, workout_session_id=workout_session_id
    )
    statement = _statement(user_id, snapshot["session_external_id"]).where(
        EnvironmentReplaySnapshot.evidence_set_id == UUID(snapshot["evidence_set_id"]),
        EnvironmentReplaySnapshot.snapshot_hash == snapshot["snapshot_hash"],
    )
    existing = (await db.execute(statement)).scalar_one_or_none()
    status = "ALREADY_PRESENT"
    if existing is None:
        row = EnvironmentReplaySnapshot(
            id=uuid4(),
            user_id=user_id,
            workout_session_id=workout_session_id,
            evidence_set_id=UUID(snapshot["evidence_set_id"]),
            snapshot_schema_version=snapshot["snapshot_schema_version"],
            snapshot_hash=snapshot["snapshot_hash"],
            snapshot_json=snapshot,
        )
        try:
            async with db.begin_nested():
                db.add(row)
                await db.flush()
            await db.commit()
            status = "CREATED"
        except IntegrityError:
            if (await db.execute(statement)).scalar_one_or_none() is None:
                raise
        existing = (await db.execute(statement)).scalar_one_or_none()
    if existing is None or existing.snapshot_json != snapshot:
        raise ValueError("REPLAY_SNAPSHOT_ROUND_TRIP_FAILED")
    _check_row(existing, user_id, snapshot["session_external_id"])
    return {
        "status": status,
        "snapshot_id": str(existing.id),
        "snapshot_hash": existing.snapshot_hash,
        "evidence_set_id": snapshot["evidence_set_id"],
        "evidence_hash": snapshot["evidence_hash"],
        "round_trip_verified": True,
        "stores_full_environment_inputs": True,
        "training_authorized": False,
    }


async def list_environment_replay_snapshots(db, *, user_id, session_external_id, limit=25):
    statement = _statement(user_id, session_external_id)
    count = (await db.execute(select(func.count()).select_from(statement.subquery()))).scalar_one()
    rows = (
        (
            await db.execute(
                statement.order_by(
                    EnvironmentReplaySnapshot.created_at.desc(), EnvironmentReplaySnapshot.id
                ).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    items = []
    for row in rows:
        _check_row(row, user_id, session_external_id)
        items.append(
            {
                "snapshot_id": str(row.id),
                "snapshot_hash": row.snapshot_hash,
                "evidence_set_id": str(row.evidence_set_id),
                "evidence_hash": row.snapshot_json["evidence_hash"],
                "created_at": row.created_at.isoformat(),
                "captured_unassigned_package_hash": row.snapshot_json[
                    "unassigned_dataset_package_hash"
                ],
            }
        )
    return {
        "status": "AVAILABLE" if count else "CAPTURE_REQUIRED",
        "total_count": count,
        "returned_count": len(items),
        "truncated": count > len(items),
        "snapshots": items,
        "legacy_hash_only_snapshots_are_replayable": False,
        "training_authorized": False,
    }
