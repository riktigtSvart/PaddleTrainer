"""Immutable, idempotent storage of current-source, athlete-owned HR proof."""

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.hr_timebase_snapshot import HeartRateTimebaseSnapshot
from app.services.hr_timebase_snapshot import (
    MAX_CURRENT_SNAPSHOTS,
    build_hr_timebase_snapshot,
    current_hr_source_hash,
    resolve_hr_timebase_snapshots,
)


async def persist_hr_timebase_snapshot(
    db,
    verification,
    sample_session,
    *,
    athlete_id,
    session_external_id,
    sample_session_match_count,
):
    owner = UUID(str(athlete_id))
    snapshot = build_hr_timebase_snapshot(
        verification,
        sample_session,
        athlete_id=str(owner),
        session_external_id=session_external_id,
        sample_session_match_count=sample_session_match_count,
    )
    if any(len(snapshot[key]) > 200 for key in ("session_external_id", "exercise_external_id")):
        raise ValueError("Provider identity exceeds the supported storage length")
    predicate = (
        HeartRateTimebaseSnapshot.user_id == owner,
        HeartRateTimebaseSnapshot.source_provider == "POLAR",
        HeartRateTimebaseSnapshot.session_external_id == snapshot["session_external_id"],
        HeartRateTimebaseSnapshot.exercise_external_id == snapshot["exercise_external_id"],
        HeartRateTimebaseSnapshot.verification_decision_hash
        == snapshot["verification_decision_hash"],
    )
    statement = (
        select(HeartRateTimebaseSnapshot)
        .where(*predicate)
        .execution_options(populate_existing=True)
    )
    existing = (await db.execute(statement)).scalar_one_or_none()
    status = "ALREADY_PRESENT"
    if existing is None:
        row = HeartRateTimebaseSnapshot(
            id=uuid4(),
            user_id=owner,
            source_provider="POLAR",
            session_external_id=snapshot["session_external_id"],
            exercise_external_id=snapshot["exercise_external_id"],
            api_source_hash=snapshot["api_source_hash"],
            verification_decision_hash=snapshot["verification_decision_hash"],
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
            # A concurrent identical insert is safe only if the exact row exists.
            if (await db.execute(statement)).scalar_one_or_none() is None:
                raise
        existing = (await db.execute(statement)).scalar_one_or_none()
    if existing is None or existing.snapshot_json != snapshot:
        raise ValueError("Stored HR timebase snapshot failed exact round-trip verification")
    record = _record(existing)
    resolution = resolve_hr_timebase_snapshots(
        [record],
        sample_session,
        athlete_id=str(owner),
        session_external_id=session_external_id,
        sample_session_match_count=sample_session_match_count,
    )
    if resolution["verified_exercise_count"] != 1:
        raise ValueError("Stored HR timebase snapshot identity or source failed verification")
    return {
        "status": status,
        "snapshot_id": str(existing.id),
        "snapshot_hash": snapshot["snapshot_hash"],
        "round_trip_verified": True,
        "persists_timebase_evidence": True,
        "persists_uploaded_file": False,
        "training_authorized": False,
        "numeric_prediction_authorized": False,
    }


async def load_current_hr_timebase_snapshots(
    db,
    sample_session,
    *,
    athlete_id,
    session_external_id,
    sample_session_match_count,
):
    try:
        owner = UUID(str(athlete_id))
    except (ValueError, TypeError, AttributeError):
        return []
    source_hash = current_hr_source_hash(
        sample_session,
        session_external_id=session_external_id,
        sample_session_match_count=sample_session_match_count,
    )
    if source_hash is None:
        return []
    rows = (
        (
            await db.execute(
                select(HeartRateTimebaseSnapshot)
                .where(
                    HeartRateTimebaseSnapshot.user_id == owner,
                    HeartRateTimebaseSnapshot.source_provider == "POLAR",
                    HeartRateTimebaseSnapshot.session_external_id == str(session_external_id),
                    HeartRateTimebaseSnapshot.api_source_hash == source_hash,
                )
                .limit(MAX_CURRENT_SNAPSHOTS + 1)
            )
        )
        .scalars()
        .all()
    )
    return [_record(row) for row in rows]


def _record(row):
    return {
        "snapshot_id": str(row.id),
        "column_identity": {
            "athlete_id": str(row.user_id),
            "source_provider": row.source_provider,
            "session_external_id": row.session_external_id,
            "exercise_external_id": row.exercise_external_id,
            "api_source_hash": row.api_source_hash,
            "verification_decision_hash": row.verification_decision_hash,
            "snapshot_hash": row.snapshot_hash,
        },
        "snapshot": row.snapshot_json,
    }
