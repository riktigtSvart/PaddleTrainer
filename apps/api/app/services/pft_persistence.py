"""Owner-bound, append-only PFT recordings and processing revisions."""
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.models.pft_measurement import PftMeasurement, PftRecording
from app.services.pft_processing import (
    PftIntegrityError, canonical_hash, parse_recording, recording_hash,
)


def utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def verify_recording(row):
    if row.source_kind != "TCX_UPLOAD" or hashlib.sha256(row.raw_tcx).hexdigest() != row.raw_sha256:
        raise PftIntegrityError("PFT_STORED_RAW_SOURCE_HASH_MISMATCH")
    session = parse_recording(row.raw_tcx)
    if recording_hash(session) != row.recording_hash or len(session.samples) != row.sample_count:
        raise PftIntegrityError("PFT_STORED_RECORDING_HASH_MISMATCH")
    if utc(row.started_at) != session.started_at or utc(row.ended_at) != session.samples[-1].timestamp:
        raise PftIntegrityError("PFT_STORED_RECORDING_TIME_MISMATCH")
    return session


def verify_measurement(row):
    if canonical_hash(row.processing_manifest) != row.processing_key:
        raise PftIntegrityError("PFT_STORED_PROCESSING_KEY_MISMATCH")
    if canonical_hash(row.result_json) != row.result_hash:
        raise PftIntegrityError("PFT_STORED_RESULT_HASH_MISMATCH")
    result = row.result_json
    if result.get("declared_context") != row.processing_manifest.get("context"):
        raise PftIntegrityError("PFT_STORED_CONTEXT_MISMATCH")
    started = datetime.fromisoformat(result["processing_output"]["session"]["started_at"])
    ended = datetime.fromisoformat(result["observed_context"]["last_observed_sample_at_utc"])
    if utc(row.started_at) != utc(started) or utc(row.ended_at) != utc(ended):
        raise PftIntegrityError("PFT_STORED_MEASUREMENT_TIME_MISMATCH")
    for field in ("state_estimation_authorized", "training_plan_modification_authorized",
                  "causal_prediction_authorized"):
        if result.get(field) is not False:
            raise PftIntegrityError("PFT_STORED_UNSUPPORTED_AUTHORITY")
    return deepcopy(result)


async def find_recording(db, owner_id, source_hash):
    return (await db.execute(select(PftRecording).where(
        PftRecording.user_id == owner_id, PftRecording.recording_hash == source_hash
    ))).scalar_one_or_none()


async def get_measurement(db, owner_id, measurement_id):
    return (await db.execute(select(PftMeasurement).where(
        PftMeasurement.user_id == owner_id, PftMeasurement.id == measurement_id
    ))).scalar_one_or_none()


async def get_recording(db, owner_id, recording_id):
    return (await db.execute(select(PftRecording).where(
        PftRecording.user_id == owner_id, PftRecording.id == recording_id
    ))).scalar_one_or_none()


async def list_measurements(db, owner_id, limit, offset):
    result = await db.execute(select(PftMeasurement).where(
        PftMeasurement.user_id == owner_id
    ).order_by(PftMeasurement.started_at.desc(), PftMeasurement.created_at.desc(),
               PftMeasurement.id.desc()).limit(limit).offset(offset))
    return tuple(result.scalars().all())


async def save_measurement(db, *, owner_id, filename, raw, whole, selected, manifest, document):
    source_hash = recording_hash(whole)
    key = canonical_hash(manifest)
    now = datetime.now(UTC)
    for attempt in range(2):
        try:
            async with db.begin_nested():
                source = await find_recording(db, owner_id, source_hash)
                if source is None:
                    source = PftRecording(
                        id=uuid4(), user_id=owner_id, source_kind="TCX_UPLOAD",
                        source_filename=filename.replace("\\", "/").rsplit("/", 1)[-1][:200],
                        raw_sha256=hashlib.sha256(raw).hexdigest(), recording_hash=source_hash,
                        raw_tcx=raw, started_at=whole.started_at,
                        ended_at=whole.samples[-1].timestamp, sample_count=len(whole.samples),
                        created_at=now,
                    )
                    db.add(source)
                    await db.flush()
                else:
                    verify_recording(source)
                existing = (await db.execute(select(PftMeasurement).where(
                    PftMeasurement.user_id == owner_id, PftMeasurement.recording_id == source.id,
                    PftMeasurement.processing_key == key,
                ))).scalar_one_or_none()
                if existing is not None:
                    verify_measurement(existing)
                    return existing, source, "ALREADY_PRESENT"
                # Byte-different exports with identical timed samples share one
                # recording. Keep the first raw source as the source of truth.
                stored_document = deepcopy(document)
                stored_document["provenance"]["source_raw_sha256"] = source.raw_sha256
                stored_document["observed_context"]["raw_source_sha256"] = source.raw_sha256
                row = PftMeasurement(
                    id=uuid4(), user_id=owner_id, recording_id=source.id,
                    processing_key=key, processing_manifest=manifest,
                    result_hash=canonical_hash(stored_document), result_json=stored_document,
                    started_at=selected.started_at, ended_at=selected.samples[-1].timestamp,
                    created_at=now,
                )
                db.add(row)
                await db.flush()
                verify_measurement(row)
            await db.commit()
            return row, source, "CREATED"
        except IntegrityError:
            if attempt:
                raise
            # The savepoint rolled back only this attempt. A concurrent
            # successful insert can now be selected without replacing it.
    raise RuntimeError("PFT persistence retry exhausted.")


def response_document(row, source=None, *, status=None):
    result = verify_measurement(row)
    result.update({
        "measurement_id": str(row.id), "recording_id": str(row.recording_id),
        "processing_key": row.processing_key, "result_hash": row.result_hash,
        "available_at_utc": utc(row.created_at).isoformat(),
        "identity_scope": "APPLICATION_DEMO_USER",
        "measurement_count_scope": "PROCESSING_VERSIONS_NOT_INDEPENDENT_PFT_COUNT",
        "baseline_eligibility_scope": "FEATURE_NUMERICAL_COMPLETENESS_ONLY",
    })
    if source is not None:
        verify_recording(source)
        if source.id != row.recording_id or source.user_id != row.user_id:
            raise PftIntegrityError("PFT_RECORDING_OWNER_BINDING_MISMATCH")
        if result["provenance"]["recording_hash"] != source.recording_hash:
            raise PftIntegrityError("PFT_MEASUREMENT_RECORDING_BINDING_MISMATCH")
        result["source"] = {
            "source_kind": source.source_kind, "source_filename": source.source_filename,
            "raw_sha256": source.raw_sha256, "recording_hash": source.recording_hash,
            "raw_sample_count": source.sample_count,
        }
    if status is not None:
        result["persistence_status"] = status
    return result
