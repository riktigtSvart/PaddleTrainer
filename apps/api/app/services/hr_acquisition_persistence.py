"""Append-only, owner-scoped storage of HR sensor declarations and corrections."""

from datetime import UTC
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.hr_acquisition_declaration import HRAcquisitionDeclaration
from app.services.hr_acquisition_declarations import (
    MAX_DECLARATIONS,
    HRAcquisitionDeclarationError,
    build_hr_acquisition_declaration,
    resolve_hr_acquisition_declarations,
)
from app.services.hr_timebase_snapshot import current_hr_source_hash


async def load_current_hr_acquisition_declarations(
    db, sample_session, *, athlete_id, session_external_id, sample_session_match_count
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
                select(HRAcquisitionDeclaration)
                .where(
                    HRAcquisitionDeclaration.user_id == owner,
                    HRAcquisitionDeclaration.source_provider == "POLAR",
                    HRAcquisitionDeclaration.session_external_id == str(session_external_id),
                    HRAcquisitionDeclaration.api_source_hash == source_hash,
                )
                .order_by(HRAcquisitionDeclaration.created_at, HRAcquisitionDeclaration.id)
                .limit(MAX_DECLARATIONS + 1)
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )
    return [_record(row) for row in rows]


async def persist_hr_acquisition_declaration(
    db, payload, sample_session, *, athlete_id, session_external_id, sample_session_match_count
):
    try:
        owner = UUID(str(athlete_id))
    except (ValueError, TypeError, AttributeError):
        raise HRAcquisitionDeclarationError("HR_ACQUISITION_OWNER_INVALID") from None
    kwargs = {
        "athlete_id": str(owner),
        "session_external_id": session_external_id,
        "sample_session_match_count": sample_session_match_count,
    }
    declaration = build_hr_acquisition_declaration(payload, sample_session, **kwargs)
    records = await load_current_hr_acquisition_declarations(db, sample_session, **kwargs)
    context = resolve_hr_acquisition_declarations(records, sample_session, **kwargs)
    if context["status"] == "WITHHELD":
        raise HRAcquisitionDeclarationError("HR_ACQUISITION_EXISTING_RECORDS_UNUSABLE")
    existing = next(
        (
            record
            for record in records
            if record["declaration"]["declaration_hash"] == declaration["declaration_hash"]
        ),
        None,
    )
    status = "ALREADY_PRESENT"
    if existing is None:
        predecessors = declaration["supersedes_declaration_ids"]
        active = context["by_exercise"][declaration["exercise_external_id"]][
            "active_declaration_ids"
        ]
        if predecessors and predecessors != active:
            raise HRAcquisitionDeclarationError("HR_ACQUISITION_CORRECTION_TARGETS_NOT_CURRENT")
        if len(records) >= MAX_DECLARATIONS:
            raise HRAcquisitionDeclarationError("HR_ACQUISITION_DECLARATION_LIMIT_REACHED")
        row = HRAcquisitionDeclaration(
            id=uuid4(),
            user_id=owner,
            source_provider="POLAR",
            session_external_id=declaration["session_external_id"],
            exercise_external_id=declaration["exercise_external_id"],
            api_source_hash=declaration["api_source_hash"],
            declaration_hash=declaration["declaration_hash"],
            declaration_json=declaration,
        )
        try:
            async with db.begin_nested():
                db.add(row)
                await db.flush()
            await db.commit()
            status = "CREATED"
        except IntegrityError:
            # Reload after a concurrent insert. Only the identical statement may recover.
            pass
        records = await load_current_hr_acquisition_declarations(db, sample_session, **kwargs)
        existing = next(
            (
                record
                for record in records
                if record["declaration"]["declaration_hash"] == declaration["declaration_hash"]
            ),
            None,
        )
        context = resolve_hr_acquisition_declarations(records, sample_session, **kwargs)
    if (
        existing is None
        or existing["declaration"] != declaration
        or context["status"] == "WITHHELD"
    ):
        raise HRAcquisitionDeclarationError("HR_ACQUISITION_ROUND_TRIP_VERIFICATION_FAILED")
    active = context["by_exercise"][declaration["exercise_external_id"]]["active_declaration_ids"]
    return {
        "status": status,
        "declaration_id": existing["declaration_id"],
        "declaration_hash": declaration["declaration_hash"],
        "recorded_at_utc": existing["recorded_at_utc"],
        "declaration_active": existing["declaration_id"] in active,
        "round_trip_verified": True,
        "source_kind": "USER_DECLARATION",
        "sensor_identity_verified": False,
        "acquisition_quality_verified": False,
        "training_authorized": False,
        "numeric_prediction_authorized": False,
    }


def _record(row):
    timestamp = row.created_at
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return {
        "declaration_id": str(row.id),
        "recorded_at_utc": timestamp.astimezone(UTC).isoformat(),
        "column_identity": {
            "athlete_id": str(row.user_id),
            "source_provider": row.source_provider,
            "session_external_id": row.session_external_id,
            "exercise_external_id": row.exercise_external_id,
            "api_source_hash": row.api_source_hash,
            "declaration_hash": row.declaration_hash,
        },
        "declaration": row.declaration_json,
    }
